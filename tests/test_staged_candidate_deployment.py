"""Execute the candidate controls with local Git and a credential-free gcloud fake."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECT, REGION = "example-project", "europe-west1"
CANONICAL = "https://worker-abc-ew.a.run.app"
QUEUE = f"projects/{PROJECT}/locations/{REGION}/queues/fixlist-scan-stages"


FAKE_GCLOUD = r'''
import json, os, pathlib, re, subprocess, sys
import yaml
args = sys.argv[1:]
state_path = pathlib.Path(os.environ['FAKE_STATE'])
state = json.loads(state_path.read_text())
with open(os.environ['FAKE_CALLS'],'a') as output: output.write(json.dumps(args)+'\n')
def save(): state_path.write_text(json.dumps(state))
def option(name): return next(value.split('=',1)[1] for value in args if value.startswith(name+'='))
if args[:3] == ['config','set','project']: pass
elif args[:3] == ['run','services','describe']: print(json.dumps(state['service']))
elif args[:2] == ['builds','get-default-service-account']: print('build@example-project.iam.gserviceaccount.com')
elif args[:3] == ['iam','service-accounts','describe']: print('{}')
elif args[:2] == ['builds','submit']:
    context = pathlib.Path(args[2])
    raw = option('--substitutions')
    delimiter = ','
    if raw.startswith('^'):
        delimiter, raw = raw[1:].split('^',1)
    substitutions = dict(item.split('=',1) for item in raw.split(delimiter))
    manifest = yaml.safe_load(pathlib.Path(option('--config')).read_text())
    values = {**manifest['substitutions'], **substitutions, 'PROJECT_ID':os.environ['GCP_PROJECT']}
    def render(value): return re.sub(r'\$\{([A-Z_0-9]+)\}', lambda match:values[match[1]], value)
    first = next(step for step in manifest['steps'] if step['id']=='require-substitutions')
    env = {**os.environ, **dict(render(item).split('=',1) for item in first.get('env',[]))}
    script = render(first['args'][1]).replace('/workspace/.fixlist-source-sha',str(context/'.fixlist-source-sha'))
    checked = subprocess.run(['bash','-c',script],cwd=context,env=env,text=True,capture_output=True)
    if checked.returncode:
        print(checked.stderr,file=sys.stderr); sys.exit(checked.returncode)
    current = {'FIXLIST_WORKER_SOURCE_SHA':os.environ['SOURCE_SHA']}
    suffix = values.get('_STAGED_ENV_SUFFIX','')
    if suffix: current.update(item.split('=',1) for item in suffix[1:].split(','))
    if '_EGRESS_NETWORK' in values:
        current['FIXLIST_EGRESS_MODE']='static-canary'
    if os.environ.get('FAKE_FAILURE')=='environment': current.pop('SCAN_WORKSPACE_BUCKET',None)
    revision = {'metadata':{'name':'fixlist-standard150-worker-00105-abc','creationTimestamp':'2026-11-11T12:00:00Z'},'spec':{'containerConcurrency':1,'timeoutSeconds':480,'containers':[{'env':[{'name':key,'value':value} for key,value in current.items()]}]},'status':{'conditions':[{'type':'Ready','status':'True'}]}}
    if '_EGRESS_NETWORK' in values:
        revision['metadata']['annotations']={'run.googleapis.com/network-interfaces':json.dumps([{'network':values['_EGRESS_NETWORK'],'subnetwork':values['_EGRESS_SUBNET']}]),'run.googleapis.com/vpc-access-egress':'all-traffic'}
    state.update({'revision':revision,'substitutions':substitutions}); save()
    step = next(step for step in manifest['steps'] if step['id']=='tag-staged-worker-candidate')
    command = [sys.executable, *[render(arg) for arg in step['args']]]
    tagged = subprocess.run(command,cwd=context,text=True,capture_output=True)
    if tagged.returncode:
        print(tagged.stderr,file=sys.stderr); sys.exit(tagged.returncode)
elif args[:3] == ['run','revisions','list']: print(json.dumps([state['revision']]))
elif args[:3] == ['run','revisions','describe']: print(json.dumps(state['revision']))
elif args[:3] == ['run','services','update-traffic']:
    tag, revision = option('--update-tags').split('=',1)
    canonical = state['service']['status']['url']
    state['service']['status']['traffic'].append({'tag':tag,'revisionName':revision,'percent':0,'url':'https://'+tag+'---'+canonical.removeprefix('https://')})
    save(); print(json.dumps(state['service']))
else: raise SystemExit('Unexpected cloud command '+repr(args))
'''


@pytest.fixture
def candidate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in ("scripts/build-worker-candidate.sh", "scripts/lib/release-source-guard.sh", "scripts/staged_candidate_cloudbuild.py", "cloudbuild.durable-worker.yaml", "cloudbuild.durable-worker-static-egress-canary.yaml"):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    verifier = repo / "scripts/verify-fixlist-static-egress-canary.sh"
    verifier.write_text("#!/bin/sh\nexit 0\n")
    verifier.chmod(0o755)
    for args in (["init", "-b", "main"], ["config", "user.email", "test@example.invalid"], ["config", "user.name", "Fixture"], ["add", "."], ["commit", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", sha], cwd=repo, check=True)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable = binaries / "gcloud"
    executable.write_text(f"#!{sys.executable}\n" + FAKE_GCLOUD)
    executable.chmod(0o755)
    state_path, calls = tmp_path / "state.json", tmp_path / "calls.jsonl"
    worker = {"spec": {"template": {"spec": {"serviceAccountName": f"worker@{PROJECT}.iam.gserviceaccount.com", "containers": [{"image": "europe-west1-docker.pkg.dev/example-project/workers/scanner:old", "env": [
        {"name": "TASKS_INVOKER_SERVICE_ACCOUNT", "value": f"invoker@{PROJECT}.iam.gserviceaccount.com"},
        {"name": "BASE44_APP_ID", "value": "app-test"}, {"name": "BASE44_API_URL", "value": "https://base44.app"},
        {"name": "SCAN_EVIDENCE_SIGNING_KEY", "valueFrom": {"secretKeyRef": {"name": "scan-evidence", "key": "7"}}}]}]}}},
        "status": {"url": CANONICAL, "traffic": [{"revisionName": "serving", "percent": 100}, {"tag": "candidate", "revisionName": "older-candidate", "percent": 0, "url": "https://candidate---worker-abc-ew.a.run.app"}]}}
    state_path.write_text(json.dumps({"service": worker}))
    env = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"], "GCP_PROJECT": PROJECT, "GCP_REGION": REGION,
           "SOURCE_SHA": sha, "CONFIRM": sha, "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha,
           "FAKE_STATE": str(state_path), "FAKE_CALLS": str(calls), "FIXLIST_EGRESS_MODE": "none"}
    for key in ("FIXLIST_STAGED_SCAN_MODE", "SCAN_WORKSPACE_BUCKET", "SCAN_STAGE_TASKS_QUEUE_PATH", "SCAN_STAGED_OWNER_IDS", "SCAN_PIPELINE_OWNER_IDS", "SCAN_PIPELINE_MODE"):
        env.pop(key, None)

    def run(**overrides):
        return subprocess.run(["bash", "scripts/build-worker-candidate.sh"], cwd=repo, env={**env, **overrides}, capture_output=True, text=True, timeout=30)

    return run, state_path, calls, sha


def inactive():
    return {"FIXLIST_STAGED_SCAN_MODE": "inactive", "SCAN_WORKSPACE_BUCKET": "example-workspaces", "SCAN_STAGE_TASKS_QUEUE_PATH": QUEUE}


def test_default_build_preserves_legacy_environment_and_does_not_add_tags(candidate):
    run, state, calls, sha = candidate
    result = run()
    assert result.returncode == 0, result.stderr
    saved = json.loads(state.read_text())
    assert "_STAGED_SCAN_MODE" not in saved["substitutions"]
    assert all("--update-tags=" not in " ".join(args) for args in map(json.loads, calls.read_text().splitlines()))
    assert "WORKER_CANDIDATE_STAGE_MODE=off" in result.stdout


@pytest.mark.parametrize("static", [False, True])
def test_inactive_build_uses_immutable_tag_preserves_empty_owners_and_serving_traffic(candidate, static):
    run, state, calls, sha = candidate
    options = inactive()
    if static:
        options.update({"FIXLIST_EGRESS_MODE": "static-canary", "FIXLIST_EGRESS_NETWORK": "fixlist-scanner-egress", "FIXLIST_EGRESS_SUBNET": "fixlist-scanner-egress-euw1"})
    result = run(**options)
    assert result.returncode == 0, result.stderr
    saved = json.loads(state.read_text())
    env = {item["name"]: item["value"] for item in saved["revision"]["spec"]["containers"][0]["env"]}
    assert env["FIXLIST_WORKER_SOURCE_SHA"] == sha
    assert env["SCAN_PIPELINE_MODE"] == "monolith" and env["SCAN_STAGED_OWNER_IDS"] == ""
    assert env["SCAN_STAGE_TARGET_URL"] == "https://staged-" + sha[:12] + "---worker-abc-ew.a.run.app"
    assert env["SCAN_STAGE_TOKEN_AUDIENCE"] == CANONICAL
    traffic = saved["service"]["status"]["traffic"]
    assert traffic[0] == {"revisionName": "serving", "percent": 100}
    assert traffic[1]["tag"] == "candidate" and traffic[1]["revisionName"] == "older-candidate"
    assert traffic[2]["tag"] == "staged-" + sha[:12] and traffic[2]["percent"] == 0
    submits = [args for args in map(json.loads, calls.read_text().splitlines()) if args[:2] == ["builds", "submit"]]
    assert next(arg for arg in submits[0] if arg.startswith("--substitutions=")).startswith("--substitutions=^|^")
    assert not any(arg.startswith(("--set-tags=", "--to-revisions=")) for args in map(json.loads, calls.read_text().splitlines()) for arg in args)


@pytest.mark.parametrize("overrides,reason", [
    ({"SCAN_WORKSPACE_BUCKET": ""}, "workspace bucket"),
    ({"SCAN_STAGE_TASKS_QUEUE_PATH": QUEUE.replace(PROJECT, "another-project")}, "selected project"),
    ({"SCAN_STAGE_TASKS_QUEUE_PATH": QUEUE.replace(REGION, "us-central1")}, "selected project"),
    ({"SCAN_STAGED_OWNER_IDS": "owner-id"}, "empty owner cohort"),
    ({"SCAN_PIPELINE_MODE": "staged"}, "empty owner cohort"),
    ({"FIXLIST_STAGED_SCAN_MODE": "owner-canary"}, "exactly one exact owner ID"),
])
def test_invalid_or_active_configuration_fails_before_build(candidate, overrides, reason):
    run, state, calls, sha = candidate
    result = run(**{**inactive(), **overrides})
    assert result.returncode != 0
    assert reason in result.stderr
    assert "revision" not in json.loads(state.read_text())


def test_existing_source_tag_cannot_be_rebound_even_if_source_is_unchanged(candidate):
    run, state, calls, sha = candidate
    assert run(**inactive()).returncode == 0
    before = state.read_text()
    result = run(**inactive())
    assert result.returncode != 0 and "must never be rebound" in result.stderr
    assert state.read_text() == before


def test_postdeploy_rejects_missing_staged_environment(candidate):
    run, state, calls, sha = candidate
    result = run(**inactive(), FAKE_FAILURE="environment")
    assert result.returncode != 0 and "environment does not match" in result.stderr


def test_source_tag_must_fit_real_dns_labels(candidate):
    run, state, calls, sha = candidate
    saved = json.loads(state.read_text())
    saved["service"]["status"]["url"] = "https://" + "x" * 60 + ".a.run.app"
    state.write_text(json.dumps(saved))
    result = run(**inactive())
    assert result.returncode != 0 and "DNS label limit" in result.stderr
    assert "revision" not in json.loads(state.read_text())


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", ["source_stamp", "owner_activation", "owner_list", "digest", "extra_variable", "wrong_target"])
def test_cloudbuild_itself_rejects_unaccepted_or_mismatched_configuration(tmp_path, failure):
    helper = load_script("staged_candidate_cloudbuild")
    sha = "a" * 40
    stamp = tmp_path / "source-sha"
    stamp.write_text(sha if failure != "source_stamp" else "b" * 40)
    env = helper.environment(sha, PROJECT, REGION, "example-workspaces", QUEUE, CANONICAL)
    if failure == "owner_list": env["SCAN_STAGED_OWNER_IDS"] = "owner-id"
    if failure == "extra_variable": env["UNREVIEWED_VARIABLE"] = "true"
    if failure == "wrong_target": env["SCAN_STAGE_TARGET_URL"] = "https://other-service.run.app"
    digest = helper.digest_for(sha, env) if failure != "digest" else "0" * 64
    env["FIXLIST_STAGED_CONFIG_SHA256"] = digest
    execution_env = {**os.environ, "STAGED_SCAN_MODE": "owner-canary" if failure == "owner_activation" else "inactive",
                     "STAGED_ENV_SUFFIX": "," + ",".join(key + "=" + value for key, value in sorted(env.items())),
                     "STAGED_TAG": helper.source_tag(sha), "STAGED_CONFIG_SHA256": digest, "STAGED_SOURCE_SHA": sha,
                     "STAGED_PROJECT": PROJECT, "STAGED_REGION": REGION}
    checked = subprocess.run([sys.executable, str(ROOT / "scripts/staged_candidate_cloudbuild.py"), "validate", "--source-stamp", str(stamp)], env=execution_env, capture_output=True, text=True)
    assert checked.returncode != 0 and "STAGED_CANDIDATE_BLOCKED" in checked.stderr


def test_infra_preparation_pauses_new_queue_before_granting_enqueue_access():
    prepare = load_script("prepare_staged_scan_infra")
    args = prepare.arguments(["--project", PROJECT, "--region", REGION, "--bucket", "example-workspaces", "--worker-sa", f"worker@{PROJECT}.iam.gserviceaccount.com", "--invoker-sa", f"invoker@{PROJECT}.iam.gserviceaccount.com", "--worker-url", CANONICAL])
    commands = prepare.plan(args, "/tmp/lifecycle.json")
    creation = next(i for i, command in enumerate(commands) if command[1:4] == ["tasks", "queues", "create"])
    assert commands[creation + 1][1:5] == ["tasks", "queues", "pause", "fixlist-scan-stages"]
    assert next(i for i, command in enumerate(commands) if command[1:4] == ["tasks", "queues", "add-iam-policy-binding"]) > creation + 1
    assert not any("resume" in command for command in commands)
    assert prepare.worker_environment(args)["SCAN_PIPELINE_MODE"] == "monolith"
    assert prepare.worker_environment(args)["SCAN_STAGED_OWNER_IDS"] == ""


def test_inactive_infrastructure_verification_requires_paused_queue_explicitly():
    load_script("prepare_staged_scan_infra")
    verify = load_script("verify_staged_scan_infra")
    queue = {"name": QUEUE, "state": "PAUSED", "rateLimits": {"maxConcurrentDispatches": 40}, "retryConfig": {"maxAttempts": 10, "minBackoff": "10s", "maxBackoff": "120s", "maxDoublings": 4, "maxRetryDuration": "1800s"}}
    verify.validate_queue(queue, QUEUE, 40, "PAUSED")
    with pytest.raises(verify.VerificationError, match="RUNNING"):
        verify.validate_queue(queue, QUEUE, 40)
    queue["state"] = "RUNNING"
    with pytest.raises(verify.VerificationError, match="PAUSED"):
        verify.validate_queue(queue, QUEUE, 40, "PAUSED")


OWNER = "owner_canary_01"


def owner_canary(sha, owner=OWNER, **extra):
    helper = load_script("staged_candidate_cloudbuild")
    confirm = f"STAGE-WORKER-OWNER-CANARY:{sha}:{helper.cohort_sha256(owner)}"
    return {**inactive(), "FIXLIST_STAGED_SCAN_MODE": "owner-canary", "SCAN_STAGED_OWNER_IDS": owner,
            "STAGED_COHORT_CONFIRM": confirm, **extra}


def test_owner_canary_build_stages_one_owner_on_the_reviewed_configuration(candidate):
    run, state, calls, sha = candidate
    result = run(**owner_canary(sha))
    assert result.returncode == 0, result.stderr
    saved = json.loads(state.read_text())
    env = {item["name"]: item["value"] for item in saved["revision"]["spec"]["containers"][0]["env"]}
    assert env["SCAN_PIPELINE_MODE"] == "staged" and env["SCAN_STAGED_OWNER_IDS"] == OWNER
    assert "SCAN_PIPELINE_OWNER_IDS" not in env
    # The digest is the reviewed inactive configuration's: the cohort is the only difference.
    helper = load_script("staged_candidate_cloudbuild")
    reviewed = helper.environment(sha, PROJECT, REGION, "example-workspaces", QUEUE, CANONICAL)
    assert env["FIXLIST_STAGED_CONFIG_SHA256"] == helper.digest_for(sha, reviewed)
    assert {k: v for k, v in env.items() if k in reviewed and k not in helper.COHORT_KEYS} == \
        {k: v for k, v in reviewed.items() if k not in helper.COHORT_KEYS}
    traffic = saved["service"]["status"]["traffic"]
    assert traffic[0] == {"revisionName": "serving", "percent": 100}
    assert traffic[2]["tag"] == "staged-" + sha[:12] and traffic[2]["percent"] == 0
    assert saved["substitutions"]["_STAGED_SCAN_MODE"] == "owner-canary"
    assert saved["substitutions"]["_STAGED_OWNER_IDS"] == OWNER
    assert "WORKER_CANDIDATE_STAGE_MODE=owner-canary" in result.stdout


@pytest.mark.parametrize("change,reason", [
    (dict(STAGED_COHORT_CONFIRM=""), "STAGE-WORKER-OWNER-CANARY"),
    (dict(STAGED_COHORT_CONFIRM="STAGE-WORKER-OWNER-CANARY:{sha}:" + "0" * 64), "STAGE-WORKER-OWNER-CANARY"),
    (dict(SCAN_STAGED_OWNER_IDS="owner_canary_01,owner_canary_02"), "exactly one exact owner ID"),
    (dict(SCAN_STAGED_OWNER_IDS="*"), "exactly one exact owner ID"),
    (dict(SCAN_STAGED_OWNER_IDS="short"), "exactly one exact owner ID"),
    (dict(SCAN_PIPELINE_OWNER_IDS=OWNER), "legacy aliases"),
    (dict(SCAN_PIPELINE_MODE="staged"), "legacy aliases"),
])
def test_owner_canary_refuses_unbound_or_ambiguous_cohorts_before_build(candidate, change, reason):
    run, state, calls, sha = candidate
    options = owner_canary(sha)
    options.update({k: v.format(sha=sha) for k, v in change.items()})
    result = run(**options)
    assert result.returncode != 0 and reason in result.stderr, result.stderr
    assert "revision" not in json.loads(state.read_text())
    made = calls.read_text().splitlines() if calls.exists() else []
    assert not any(args[:2] == ["builds", "submit"] for args in map(json.loads, made))


def test_owner_canary_confirmation_is_bound_to_the_exact_owner(candidate):
    run, state, calls, sha = candidate
    helper = load_script("staged_candidate_cloudbuild")
    other = f"STAGE-WORKER-OWNER-CANARY:{sha}:{helper.cohort_sha256('owner_canary_02')}"
    result = run(**owner_canary(sha, STAGED_COHORT_CONFIRM=other))
    assert result.returncode != 0 and "STAGE-WORKER-OWNER-CANARY" in result.stderr


def validate(tmp_path, mode, env, digest=None, sha="a" * 40):
    helper = load_script("staged_candidate_cloudbuild")
    stamp = tmp_path / "source-sha"
    stamp.write_text(sha)
    reviewed = helper.environment(sha, PROJECT, REGION, "example-workspaces", QUEUE, CANONICAL)
    digest = digest or helper.digest_for(sha, reviewed)
    env = {**env, "FIXLIST_STAGED_CONFIG_SHA256": digest}
    execution_env = {**os.environ, "STAGED_SCAN_MODE": mode,
                     "STAGED_ENV_SUFFIX": "," + ",".join(key + "=" + value for key, value in sorted(env.items())),
                     "STAGED_TAG": helper.source_tag(sha), "STAGED_CONFIG_SHA256": digest, "STAGED_SOURCE_SHA": sha,
                     "STAGED_PROJECT": PROJECT, "STAGED_REGION": REGION}
    return subprocess.run([sys.executable, str(ROOT / "scripts/staged_candidate_cloudbuild.py"), "validate", "--source-stamp", str(stamp)],
                          env=execution_env, capture_output=True, text=True), helper, reviewed


def test_cloudbuild_accepts_owner_canary_only_as_reviewed_config_plus_one_owner(tmp_path):
    helper = load_script("staged_candidate_cloudbuild")
    reviewed = helper.environment("a" * 40, PROJECT, REGION, "example-workspaces", QUEUE, CANONICAL)
    checked, _, _ = validate(tmp_path, "owner-canary", helper.cohorted(reviewed, OWNER))
    assert checked.returncode == 0, checked.stderr
    for env in (
        {**helper.cohorted(reviewed, OWNER), "SCAN_STAGE_QUEUE": "fixlist-standard150"},
        {**reviewed, "SCAN_STAGED_OWNER_IDS": OWNER},
        {**helper.cohorted(reviewed, OWNER), "SCAN_STAGED_OWNER_IDS": "*"},
        {**helper.cohorted(reviewed, OWNER), "SCAN_PIPELINE_OWNER_IDS": OWNER},
    ):
        checked, _, _ = validate(tmp_path, "owner-canary", env)
        assert checked.returncode != 0 and "STAGED_CANDIDATE_BLOCKED" in checked.stderr
    # The inactive mode still refuses any cohort.
    checked, _, _ = validate(tmp_path, "inactive", helper.cohorted(reviewed, OWNER))
    assert checked.returncode != 0 and "monolith mode" in checked.stderr


def test_owner_canary_build_satisfies_the_stage_queue_activation_guard():
    """The cohorted build must pass the merged activation guard without edits."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import staged_queue_guard as guard
    helper = load_script("staged_candidate_cloudbuild")
    sha = "b" * 40
    origin = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
    reviewed = helper.environment(sha, guard.PROJECT, guard.REGION, guard.WORKSPACE_BUCKET, guard.STAGE_QUEUE_PATH, origin)
    env = {**helper.cohorted(reviewed, OWNER), "FIXLIST_STAGED_CONFIG_SHA256": helper.digest_for(sha, reviewed),
           "FIXLIST_WORKER_SOURCE_SHA": sha, "TASKS_INVOKER_SERVICE_ACCOUNT": guard.INVOKER_SA}
    name = "fixlist-standard150-worker-00110-abc"
    service = {"status": {"url": origin, "traffic": [
        {"revisionName": "fixlist-standard150-worker-00097-lvl", "percent": 100},
        {"revisionName": name, "percent": 0, "tag": helper.source_tag(sha), "url": reviewed["SCAN_STAGE_TARGET_URL"]}]}}
    revisions = {name: {"metadata": {"name": name}, "spec": {"serviceAccountName": guard.WORKER_SA,
                 "containers": [{"env": [{"name": k, "value": v} for k, v in env.items()]}]}},
                 "fixlist-standard150-worker-00097-lvl": {"metadata": {"name": "fixlist-standard150-worker-00097-lvl"},
                 "spec": {"containers": [{"env": [{"name": "SCAN_PIPELINE_MODE", "value": "monolith"}]}]}}}
    found = guard.check_activation_candidate(service, revisions, name, sha)
    assert found["mode"] == "staged" and found["owner_count"] == "1"
    assert helper.cohort_sha256(OWNER) == __import__("hashlib").sha256(json.dumps(sorted([OWNER]), separators=(",", ":")).encode()).hexdigest()


def test_workflow_routes_owner_canary_inputs_only_for_that_mode():
    workflow = yaml.safe_load((ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text())
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["stage_config"]["options"] == ["off", "inactive", "owner-canary"]
    assert "worker_cohort_confirm" in inputs and len(inputs) <= 25
    step = next(s for s in workflow["jobs"]["operate"]["steps"] if s.get("name") == "Build isolated Standard 150 worker candidate")
    assert step["env"]["SCAN_STAGED_OWNER_IDS"] == "${{ inputs.stage_config == 'owner-canary' && inputs.acceptance_owner_user_ids || '' }}"
    assert step["env"]["STAGED_COHORT_CONFIRM"] == "${{ inputs.stage_config == 'owner-canary' && inputs.worker_cohort_confirm || '' }}"
    for key in ("SCAN_WORKSPACE_BUCKET", "SCAN_STAGE_TASKS_QUEUE_PATH"):
        assert "inputs.stage_config == 'owner-canary'" in step["env"][key]
