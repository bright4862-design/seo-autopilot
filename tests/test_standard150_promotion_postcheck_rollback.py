"""Offline regression: unhandled post-promotion failures must attempt traffic restore.

Execute the actual GitHub Actions Bash body with PATH-local fake cloud tools.
Never invoke GCP, Base44, a customer scan or real credentials.
"""
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
PROMOTE = "      - name: Promote exact candidate with automatic rollback on failed post-check"
FOLLOWING = "      - name: Publish exact promotion status"


def promotion_step() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(PROMOTE) == 1
    assert source.count(FOLLOWING) == 1
    section = source.split(PROMOTE, 1)[1].split(FOLLOWING, 1)[0]
    return textwrap.dedent(section.split("        run: |\n", 1)[1]).strip() + "\n"


def simulate(tmp_path: Path, failure: str = "", fail_rollback: bool = False):
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    scriptdir = tmp_path / "scripts"
    scriptdir.mkdir()
    log = tmp_path / "calls.txt"

    gcloud = fakebin / "gcloud"
    gcloud.write_text(
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
failure = os.environ.get("FAIL_STAGE", "")
with Path(os.environ["CALL_LOG"]).open("a") as out:
    if a[:3] == ["run", "services", "update-traffic"]:
        out.write("rollback\\n")
        Path(os.environ["ROLLBACK_MARKER"]).write_text("yes")
        sys.exit(13 if os.environ.get("FAIL_ROLLBACK") == "1" else 0)
    if a[:3] == ["run", "services", "describe"]:
        if "--format=json" in a:
            out.write("service-json\\n")
            if failure == "service-json": sys.exit(9)
            rolled_back = Path(os.environ["ROLLBACK_MARKER"]).exists()
            current = os.environ["ROLLBACK_REVISION"] if rolled_back else os.environ["REVISION"]
            observed = [{"revisionName": current,
                         "percent": 99 if failure == "wrong-traffic" and not rolled_back else 100}]
            desired = [{"revisionName":
                        os.environ["ROLLBACK_REVISION"] if failure == "desired-stale" and not rolled_back else current,
                        "percent": 100}]
            generation = 8
            observed_generation = 7 if failure == "reconciling" and not rolled_back else 8
            ready = "False" if failure == "not-ready" and not rolled_back else "True"
            print(json.dumps({
                "metadata": {"generation": generation},
                "spec": {"traffic": desired},
                "status": {"observedGeneration": observed_generation,
                           "conditions": [{"type": "Ready", "status": ready}],
                           "traffic": observed},
            }))
            sys.exit(0)
        out.write("service-url\\n")
        if failure == "service-url": sys.exit(9)
        print("https://worker.example.invalid")
        sys.exit(0)
    if a[:3] == ["tasks", "queues", "describe"]:
        out.write("queue-read\\n")
        if failure == "queue-read": sys.exit(9)
        print("RUNNING")
        sys.exit(0)
    out.write("unexpected-gcloud-command\\n")
    sys.exit(20)
""",
        encoding="utf-8",
    )
    gcloud.chmod(0o755)

    curl = fakebin / "curl"
    curl.write_text('#!/usr/bin/env bash\nprintf "403"\n', encoding="utf-8")
    curl.chmod(0o755)

    operator = scriptdir / "fixlist-cloud-operator.sh"
    operator.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$OPERATION" >> "$CALL_LOG"
if [[ "$OPERATION" == "promote-worker" && "$FAIL_STAGE" == "operator-promote" ]]; then
  exit 8
fi
if [[ "$OPERATION" == "verify-worker-runtime-revision" && "$FAIL_STAGE" == "runtime" ]]; then
  exit 8
fi
""",
        encoding="utf-8",
    )
    operator.chmod(0o755)
    # Exercise the actual shared readback predicate from the workflow body.
    shutil.copy2(ROOT / "scripts/assert_standard150_rollback_readback.py",
                 scriptdir / "assert_standard150_rollback_readback.py")

    env = {
        **os.environ,
        "PATH": str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
        "REVISION": "worker-00125-test",
        "ROLLBACK_REVISION": "worker-00100-prior",
        "QUEUE_STATE_BEFORE": "RUNNING",
        "SOURCE_SHA": "a" * 40,
        "CLOUD_RUN_SERVICE": "fake-worker",
        "CLOUD_TASKS_QUEUE": "fake-queue",
        "GCP_REGION": "fake-region",
        "GCP_PROJECT": "fake-project",
        "FAIL_STAGE": failure,
        "FAIL_ROLLBACK": "1" if fail_rollback else "0",
        "CALL_LOG": str(log),
        "ROLLBACK_MARKER": str(tmp_path / "rollback-marker"),
        "RUNNER_TEMP": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", "-c", promotion_step()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    return result, log.read_text().splitlines() if log.exists() else []


def test_baseline_promotes_without_rollback(tmp_path):
    result, calls = simulate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert calls.count("promote-worker") == 1
    assert calls.count("verify-worker-runtime-revision") == 1
    assert "rollback" not in calls
    assert "PROMOTION_TRAFFIC_READBACK_OK revision=worker-00125-test" in result.stdout
    assert "promoted_revision=worker-00125-test" in result.stdout


@pytest.mark.parametrize("failure", ["service-json", "service-url", "queue-read"])
def test_unhandled_postcheck_failures_attempt_rollback_once(tmp_path, failure):
    result, calls = simulate(tmp_path, failure)
    assert result.returncode != 0
    assert calls.count("promote-worker") == 1
    assert calls.count("rollback") == 1
    assert "Unhandled promotion/post-check failure" in result.stderr
    assert "promoted_revision=" not in result.stdout


@pytest.mark.parametrize("failure", ["operator-promote", "wrong-traffic", "runtime"])
def test_existing_explicit_failure_paths_still_rollback_once(tmp_path, failure):
    result, calls = simulate(tmp_path, failure)
    assert result.returncode != 0
    assert calls.count("rollback") == 1
    assert "promoted_revision=" not in result.stdout


def test_failed_restore_is_unverified_not_success(tmp_path):
    result, calls = simulate(tmp_path, "queue-read", fail_rollback=True)
    assert result.returncode != 0
    assert calls.count("rollback") == 1
    assert "ROLLBACK_UNVERIFIED" in result.stderr


def test_exit_guard_armed_before_promotion_and_disarmed_after_final_check():
    body = promotion_step()
    assert body.index("trap rollback_on_unhandled_exit EXIT") < body.index(
        "export OPERATION=promote-worker"
    )
    assert body.index("promotion_started=1") < body.index(
        "bash ./scripts/fixlist-cloud-operator.sh"
    )
    assert body.rindex("promotion_started=0") > body.index("queue_state_after=")


@pytest.mark.parametrize("failure", ["desired-stale", "reconciling", "not-ready"])
def test_observed_candidate_100_without_converged_service_rolls_back(tmp_path, failure):
    # These synthetic states fooled the previous status.traffic-only check.
    # A wrong desired route, stale generation or non-Ready service must not
    # make it as far as the authenticated runtime probe or success signal.
    result, calls = simulate(tmp_path, failure)
    assert result.returncode != 0
    assert "POST_PROMOTION_TRAFFIC_UNVERIFIED" in result.stderr
    assert calls.count("promote-worker") == 1
    assert calls.count("rollback") == 1
    assert "verify-worker-runtime-revision" not in calls
    assert "promoted_revision=" not in result.stdout
