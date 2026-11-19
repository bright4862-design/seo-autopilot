"""Exercise the bounded workflow helper across its real shell/Python boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rollout(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts/lib").mkdir(parents=True)
    for name in ("operate-staged-scan-infra.sh", "lib/release-source-guard.sh"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    log = tmp_path / "calls.jsonl"
    for name in ("prepare_staged_scan_infra.py", "verify_staged_scan_infra.py"):
        (repo / "scripts" / name).write_text(
            "import json,os,sys\n"
            "with open(os.environ['TEST_CALL_LOG'],'a') as f: "
            "f.write(json.dumps([__file__.rsplit('/',1)[-1],*sys.argv[1:]])+'\\n')\n"
        )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(
        "#!/usr/bin/env python3\nimport json,os,sys\n"
        "with open(os.environ['TEST_CALL_LOG'],'a') as f: f.write(json.dumps(['gcloud',*sys.argv[1:]])+'\\n')\n"
        "print(json.dumps({'status':{'url':os.environ.get('TEST_WORKER_URL','https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app')},"
        "'spec':{'template':{'spec':{'serviceAccountName':os.environ.get('TEST_WORKER_SA','fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com')}}}}))\n"
    )
    gcloud.chmod(0o755)
    for args in (("init", "-q"), ("config", "user.name", "Test"),
                 ("config", "user.email", "test@example.invalid"),
                 ("add", "."), ("commit", "-qm", "fixture")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    # The release guard now checks the live remote tip, not an Actions
    # event SHA or a fabricated tracking ref. Keep this fixture fully offline.
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo,
                   check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD:refs/heads/main"], cwd=repo,
                   check=True, capture_output=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha,
           "SOURCE_SHA": sha, "TEST_CALL_LOG": str(log)}

    def run(operation="verify-staged-scan-infra", **overrides):
        result = subprocess.run(["bash", "scripts/operate-staged-scan-infra.sh"], cwd=repo,
                                env={**env, "OPERATION": operation, **overrides},
                                text=True, capture_output=True, timeout=10)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    return sha, run


def test_read_only_operation_only_verifies_inactive_fixed_resources(rollout):
    sha, run = rollout
    result, calls = run()
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    assert calls[0][:5] == ["gcloud", "run", "services", "describe", "fixlist-standard150-worker"]
    command = calls[1]
    assert command[0] == "verify_staged_scan_infra.py"
    assert command[-2:] == ["--expected-queue-state", "PAUSED"]
    assert command[command.index("--bucket") + 1] == "fixlist-scan-workspaces-seo-autopilot-501517"
    assert command[command.index("--queue") + 1] == "fixlist-scan-stages"
    assert command[command.index("--worker-url") + 1] == (
        f"https://staged-{sha[:12]}---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
    )
    assert command[command.index("--token-audience") + 1] == "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
    assert "--apply" not in command


def test_provisioning_requires_exact_confirmation_and_verifies_paused_queue(rollout):
    sha, run = rollout
    result, calls = run("prepare-staged-scan-infra", CONFIRM=f"PREPARE-STAGED-SCAN-INFRA:{sha}")
    assert result.returncode == 0, result.stderr
    assert [call[0] for call in calls] == ["gcloud", "prepare_staged_scan_infra.py", "verify_staged_scan_infra.py"]
    assert calls[1][-1] == "--apply"
    assert calls[2][-2:] == ["--expected-queue-state", "PAUSED"]


@pytest.mark.parametrize("changes", [
    {"CONFIRM": "PREPARE-STAGED-SCAN-INFRA:" + "f" * 40},
    {"GCP_PROJECT": "another-project"},
    {"GCP_REGION": "us-central1"},
    {"CLOUD_RUN_SERVICE": "other-worker"},
    {"SOURCE_SHA": "f" * 40},
])
def test_invalid_confirmation_scope_or_source_cannot_touch_cloud(rollout, changes):
    sha, run = rollout
    result, calls = run("prepare-staged-scan-infra", **{"CONFIRM": f"PREPARE-STAGED-SCAN-INFRA:{sha}", **changes})
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize("changes", [
    {"TEST_WORKER_SA": "other@seo-autopilot-501517.iam.gserviceaccount.com"},
    {"TEST_WORKER_URL": "https://candidate---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"},
    {"TEST_WORKER_URL": "https://unexpected.example.com"},
    {"TEST_WORKER_URL": "https://worker.example.run.app/path"},
])
def test_unexpected_live_identity_or_origin_cannot_provision(rollout, changes):
    sha, run = rollout
    result, calls = run("prepare-staged-scan-infra", CONFIRM=f"PREPARE-STAGED-SCAN-INFRA:{sha}", **changes)
    assert result.returncode != 0
    assert len(calls) == 1
    assert calls[0][0] == "gcloud"
