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


def run_rollback(tmp_path, *, control_revision=OLD, runtime_revision=OLD, failed_deploy=False,
                 env_check_failed=False, rollback_url="https://gateway.run.app"):
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
    # Answers only the previous gateway's exact health URL, so a rollback that
    # lost its target URL cannot pass by accident.
    curl.write_text('#!/bin/sh\nfor last; do :; done\n'
                    'case "$last" in https://gateway.run.app/health) cat "$FIXTURE/runtime.json" ;; '
                    '*) echo "curl: (3) bad URL $last" >&2; exit 3 ;; esac\n')
    curl.chmod(0o755)
    env = {**os.environ, "PATH": str(bindir)+os.pathsep+os.environ["PATH"], "FIXTURE": str(tmp_path),
           "REPO_ROOT": str(ROOT), "PRE_DEPLOY_REVISION": OLD, "GATEWAY_ROLLBACK_SOURCE_SHA": SHA,
           "GATEWAY_ROLLBACK_BASELINE": str(baseline), "GATEWAY_URL": "https://gateway.run.app",
           "GATEWAY_ROLLBACK_URL": rollback_url,
           "GATEWAY": "fixlist-dispatch-gateway", "PROJECT": "test", "REGION": "test",
           "GATEWAY_ROLLBACK_TIMEOUT_SECONDS": "0"}
    shell = 'source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"; rollback_gateway'
    if failed_deploy:
        shell = '''source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"
GATEWAY_PROMOTION_ATTEMPTED=1
trap 'rc=$?; trap - EXIT; gateway_rollback_on_failure "$rc"' EXIT
exit 42
'''
    if env_check_failed:
        # The publisher's post-promotion environment check reassigns
        # GATEWAY_URL from a command substitution; when it fails, the variable
        # is already empty by the time the EXIT trap runs.
        shell = '''source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"
GATEWAY_PROMOTION_ATTEMPTED=1
trap 'rc=$?; trap - EXIT; gateway_rollback_on_failure "$rc"' EXIT
GATEWAY_URL="$(python3 -c 'raise SystemExit("Gateway environment mismatch: SCAN_WORKER_URL")')"
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


def test_failed_post_promotion_env_check_still_verifies_rollback(tmp_path):
    # Regression: the failed check empties GATEWAY_URL before the trap runs.
    # Rollback must still prove the previous gateway's live health, and the
    # deploy must still report the original failure, never success.
    result = run_rollback(tmp_path, env_check_failed=True)
    assert result.returncode == 1, result.stderr
    assert "Gateway environment mismatch" in result.stderr
    assert f"GATEWAY_ROLLBACK_VERIFIED revision={OLD}" in result.stdout
    assert "GATEWAY_ROLLBACK_FAILED" not in result.stderr


def test_rollback_without_verified_previous_url_refuses(tmp_path):
    result = run_rollback(tmp_path, rollback_url="")
    assert result.returncode != 0
    assert "GATEWAY_ROLLBACK_FAILED: no verified previous gateway URL." in result.stderr


def test_publisher_pins_rollback_url_before_promotion():
    deploy = (ROOT / "scripts/deploy_dispatch_gateway.sh").read_text()
    library = (ROOT / "scripts/lib/gateway-rollback.sh").read_text()
    assert deploy.index('GATEWAY_ROLLBACK_URL="$GATEWAY_URL"') < deploy.index("GATEWAY_PROMOTION_ATTEMPTED=1")
    assert '"$GATEWAY_URL/health"' not in library
    assert '"$GATEWAY_ROLLBACK_URL/health"' in library
