"""Offline regression: unhandled post-promotion failures must attempt traffic restore.

Execute the actual GitHub Actions Bash body with PATH-local fake cloud tools.
Never invoke GCP, Base44, a customer scan or real credentials.
"""
import os
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
    # Run the real strict traffic-readback helper in this hermetic temp repo.
    # Previously this harness only stubbed the operator and therefore had no
    # helper at the relative path that promotion now invokes.
    (scriptdir / "assert_standard150_rollback_readback.py").write_text(
        (ROOT / "scripts/assert_standard150_rollback_readback.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (scriptdir / "assert_standard150_rollback_ownership.py").write_text(
        (ROOT / "scripts/assert_standard150_rollback_ownership.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
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
        sys.exit(13 if os.environ.get("FAIL_ROLLBACK") == "1" else 0)
    if a[:3] == ["run", "services", "describe"]:
        if "--format=json" in a:
            out.write("service-json\\n")
            if failure == "service-json": sys.exit(9)
            # The fake service reconciles to the candidate after promotion,
            # or to the prior revision after a rollback command. Return both
            # desired and observed routing, Ready and generation identity.
            rollback = "rollback" in Path(os.environ["CALL_LOG"]).read_text().splitlines()
            revision = os.environ["ROLLBACK_REVISION"] if rollback or failure == "operator-promote" else os.environ["REVISION"]
            if failure == "intervening-traffic" and not rollback:
                revision = "worker-00999-foreign"
            percent = 99 if failure == "wrong-traffic" and not rollback else 100
            traffic = [{"revisionName": revision, "percent": percent}]
            if failure == "wrong-traffic" and not rollback:
                traffic.append({"revisionName": os.environ["ROLLBACK_REVISION"], "percent": 1})
            print(json.dumps({
                "metadata": {"generation": 7},
                "spec": {"traffic": [{"revisionName": revision, "percent": 100}]},
                "status": {"observedGeneration": 7,
                           "conditions": [{"type": "Ready", "status": "True"}],
                           "traffic": traffic},
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
    assert "promoted_revision=worker-00125-test" in result.stdout


@pytest.mark.parametrize("failure", ["service-url", "queue-read"])
def test_unhandled_postcheck_failures_attempt_rollback_once(tmp_path, failure):
    result, calls = simulate(tmp_path, failure)
    assert result.returncode != 0
    assert calls.count("promote-worker") == 1
    assert calls.count("rollback") == 1
    assert "Unhandled promotion/post-check failure" in result.stderr
    assert "promoted_revision=" not in result.stdout


@pytest.mark.parametrize("failure", ["wrong-traffic", "runtime"])
def test_existing_explicit_failure_paths_still_rollback_once(tmp_path, failure):
    result, calls = simulate(tmp_path, failure)
    assert result.returncode != 0
    assert calls.count("rollback") == 1
    assert "promoted_revision=" not in result.stdout


def test_rejected_promotion_does_not_overwrite_untouched_prior(tmp_path):
    result, calls = simulate(tmp_path, "operator-promote")
    assert result.returncode != 0
    assert "rollback" not in calls
    assert "ROLLBACK_ALREADY_RESTORED" in result.stderr


def test_intervening_operator_change_is_not_overwritten(tmp_path):
    result, calls = simulate(tmp_path, "intervening-traffic")
    assert result.returncode != 0
    assert "rollback" not in calls
    assert "ROLLBACK_CONFLICT" in result.stderr
    assert "ROLLBACK_UNVERIFIED" in result.stderr
    assert "promoted_revision=" not in result.stdout


def test_missing_service_state_must_not_trigger_blind_rollback(tmp_path):
    result, calls = simulate(tmp_path, "service-json")
    assert result.returncode != 0
    assert "rollback" not in calls
    assert "ROLLBACK_UNVERIFIED" in result.stderr


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
