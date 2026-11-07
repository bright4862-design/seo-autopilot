"""Exercise the real canary preflight with only cloud/probe boundaries faked."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = "fixlist-standard150-worker-00102-nn7"
ORIGIN = "https://fixlist-standard150-worker.example.a.run.app"


def run_preflight(tmp_path, *, bad_runtime=False, conflicting_tag=False, token="test-token", generic_tag=False):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/assert_tagged_zero_traffic_worker.py", scripts)
    probe = scripts / "fixlist-cloud-operator.sh"
    probe.write_text('printf "probe:%s:%s\\n" "$OPERATION" "$FIXLIST_WORKER_PROBE_URL" >> "$CALLS"\n'
                     'if [[ "$OPERATION" == verify-worker-runtime-revision && "${BAD_RUNTIME:-0}" == 1 ]]; then exit 1; fi\n')
    state = {"status": {"url": ORIGIN, "traffic": [
        {"revisionName": "fixlist-standard150-worker-00097-lvl", "percent": 100},
        {"revisionName": REVISION, "tag": "candidate", "url": ORIGIN.replace("https://", "https://candidate---")},
    ]}}
    if conflicting_tag:
        state["status"]["traffic"].append({"revisionName": "fixlist-standard150-worker-00103-abc", "tag": "canary-00102-nn7", "url": ORIGIN.replace("https://", "https://canary-00102-nn7---")})
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    calls = tmp_path / "calls"
    calls.write_text("")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cloud = bindir / "gcloud"
    cloud.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ['STATE']); s=json.loads(p.read_text())
with open(os.environ['CALLS'],'a') as f: f.write('cloud:'+ ' '.join(sys.argv[1:])+'\\n')
tagarg=next((a for a in sys.argv if a.startswith('--update-tags=')),None)
if tagarg:
 tag,rev=tagarg.split('=',1)[1].split('=')
 s['status']['traffic']=[e for e in s['status']['traffic'] if e.get('tag')!=tag]
 s['status']['traffic'].append({'revisionName':rev,'tag':tag,'url':'https://'+tag+'---fixlist-standard150-worker.example.a.run.app'})
 p.write_text(json.dumps(s))
else: print(json.dumps(s))
''')
    cloud.chmod(0o755)
    env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
           "REPO_ROOT": str(tmp_path), "GCP_PROJECT": "test", "GCP_REGION": "test",
           "CLOUD_RUN_SERVICE": "fixlist-standard150-worker", "SOURCE_SHA": "a" * 40,
           "GATEWAY_CANARY_REVISION": REVISION, "FIXLIST_WORKER_ID_TOKEN": token,
           "FIXLIST_WORKER_TOKEN_AUDIENCE": ORIGIN, "STATE": str(state_path),
           "CALLS": str(calls), "BAD_RUNTIME": "1" if bad_runtime else "0"}
    command = ROOT / "scripts/prepare_gateway_canary.sh"
    if generic_tag:
        command = ROOT / "scripts/fixlist-cloud-operator.sh"
        env.update(OPERATION="tag-worker-candidate", TARGET_REVISION=REVISION,
                   CONFIRM=REVISION, WORKER_CANDIDATE_TAG="canary-00102-nn7",
                   CLOUD_TASKS_QUEUE="queue", TASKS_INVOKER_SERVICE_ACCOUNT="invoker")
    result = subprocess.run(["bash", str(command)], env=env, capture_output=True, text=True)
    return result, calls.read_text(), json.loads(state_path.read_text())


def test_live_identity_precedes_pinned_tag_creation(tmp_path):
    result, calls, state = run_preflight(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "GATEWAY_CANARY_WORKER_ORIGIN=https://canary-00102-nn7---" in result.stdout
    assert calls.index("probe:verify-worker-runtime-revision") < calls.index("--update-tags=")
    assert calls.count("probe:verify-worker-runtime-revision") == 2
    assert state["status"]["traffic"][0]["percent"] == 100


def test_wrong_runtime_identity_refuses_before_mutating_tags(tmp_path):
    result, calls, _ = run_preflight(tmp_path, bad_runtime=True)
    assert result.returncode != 0
    assert "probe:" in calls
    assert "--update-tags=" not in calls


def test_conflicting_revision_specific_tag_is_never_reassigned(tmp_path):
    result, calls, _ = run_preflight(tmp_path, conflicting_tag=True)
    assert result.returncode != 0
    assert "canary_tag_reassigned" in result.stderr
    assert "--update-tags=" not in calls


def test_missing_invoker_token_refuses_before_cloud_mutation(tmp_path):
    result, calls, _ = run_preflight(tmp_path, token="")
    assert result.returncode != 0
    assert "identity token" in result.stderr
    assert "--update-tags=" not in calls


def test_generic_tag_operator_cannot_reassign_a_canary_tag(tmp_path):
    result, calls, _ = run_preflight(tmp_path, generic_tag=True)
    assert result.returncode != 0
    assert "reserved canary" in result.stderr
    assert "--update-tags=" not in calls
