"""A successful traffic command is insufficient: verify control and runtime."""
import json
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD = "fixlist-dispatch-gateway-00005-xt8"
NEW = "fixlist-dispatch-gateway-00006-abc"
SHA = "a" * 40


def run_rollback(tmp_path, *, control_revision=OLD, runtime_revision=OLD, failed_deploy=False):
    base = {"ok": True, "service": "fixlist-dispatch-gateway", "revision": OLD,
            "source_sha": SHA, "contract_version": "contract", "queue": "queue",
            "drain_queue": "drain", "worker_origin": "https://worker.run.app"}
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(base))
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps({**base, "revision": runtime_revision}))
    # Desired template still names the failed new build after traffic rollback.
    service = {"spec": {"template": {"spec": {"containers": [{"image": "image@sha256:" + "c"*64}]}}},
               "status": {"traffic": [{"revisionName": control_revision, "percent": 100}]}}
    revision = {"metadata": {"name": OLD}, "status": {"imageDigest": "image@sha256:" + "b"*64,
                "conditions": [{"type": "Ready", "status": "True"}]},
                "spec": {"containers": [{"env": [{"name": "FIXLIST_GATEWAY_SOURCE_SHA", "value": SHA}]}]}}
    for name, value in [("service", service), ("revision", revision)]:
        (tmp_path / (name + ".json")).write_text(json.dumps(value))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cloud = bindir / "gcloud"
    cloud.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['FIXTURE'])
with open(root/'calls','a') as f: f.write(' '.join(sys.argv[1:])+'\\n')
if 'describe' in sys.argv:
 print((root/('revision.json' if 'revisions' in sys.argv else 'service.json')).read_text())
''')
    cloud.chmod(0o755)
    curl = bindir / "curl"
    curl.write_text('#!/bin/sh\ncat "$FIXTURE/runtime.json"\n')
    curl.chmod(0o755)
    env = {**os.environ, "PATH": str(bindir)+os.pathsep+os.environ["PATH"], "FIXTURE": str(tmp_path),
           "REPO_ROOT": str(ROOT), "PRE_DEPLOY_REVISION": OLD, "GATEWAY_ROLLBACK_SOURCE_SHA": SHA,
           "GATEWAY_ROLLBACK_BASELINE": str(baseline), "GATEWAY_URL": "https://gateway.run.app",
           "GATEWAY": "fixlist-dispatch-gateway", "PROJECT": "test", "REGION": "test",
           "GATEWAY_ROLLBACK_TIMEOUT_SECONDS": "0"}
    shell = 'source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"; rollback_gateway'
    if failed_deploy:
        shell = '''source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"
GATEWAY_PROMOTION_ATTEMPTED=1
trap 'rc=$?; trap - EXIT; gateway_rollback_on_failure "$rc"' EXIT
exit 42
'''
    return subprocess.run(["bash", "-euo", "pipefail", "-c", shell], env=env, capture_output=True, text=True)


def test_rollback_proves_previous_control_and_runtime_identity(tmp_path):
    result = run_rollback(tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"GATEWAY_ROLLBACK_VERIFIED revision={OLD}" in result.stdout


@pytest.mark.parametrize("kwargs", [{"control_revision": NEW}, {"runtime_revision": NEW}])
def test_command_success_cannot_hide_failed_rollback(tmp_path, kwargs):
    result = run_rollback(tmp_path, **kwargs)
    assert result.returncode != 0
    assert "GATEWAY_ROLLBACK_FAILED" in result.stderr


def test_failure_after_promotion_runs_rollback_from_exit_trap(tmp_path):
    # The same cleanup function is used for every post-promotion failure,
    # including explicit exit, command errors and failed tag-mapping checks.
    result = run_rollback(tmp_path, failed_deploy=True)
    assert result.returncode == 42
    assert f"GATEWAY_ROLLBACK_VERIFIED revision={OLD}" in result.stdout
