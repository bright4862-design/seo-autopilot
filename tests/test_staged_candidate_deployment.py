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
    if os.environ.get('FAKE_FAILURE')=='alias': current['SCAN_PIPELINE_OWNER_IDS']='owner_canary_01'
    if os.environ.get('FAKE_FAILURE')=='bucket_drift': current['SCAN_WORKSPACE_BUCKET']='other-tenant-workspaces'
    image = values['_IMAGE'] + ':' + values['_RELEASE_SHA']
    digest = 'sha256:' + 'd' * 64
    deployed = values['_IMAGE'] + '@' + ('sha256:' + 'e' * 64 if os.environ.get('FAKE_FAILURE') == 'digest_mismatch' else digest)
    revision = {'metadata':{'name':'fixlist-standard150-worker-00105-abc','creationTimestamp':'2026-11-11T12:00:00Z'},'spec':{'containerConcurrency':1,'timeoutSeconds':480,'containers':[{'image':image,'env':[{'name':key,'value':value} for key,value in current.items()]}]},'status':{'imageDigest':deployed,'conditions':[{'type':'Ready','status':'True'}]}}
    if '_EGRESS_NETWORK' in values:
        revision['metadata']['annotations']={'run.googleapis.com/network-interfaces':json.dumps([{'network':values['_EGRESS_NETWORK'],'subnetwork':values['_EGRESS_SUBNET']}]),'run.googleapis.com/vpc-access-egress':'all-traffic'}
    # Cloud Build rejects a user substitution the config never references.
    unused = [key for key in substitutions if '${'+key+'}' not in pathlib.Path(option('--config')).read_text()]
    if unused: raise SystemExit('Unused Cloud Build substitutions: '+repr(unused))
    state.update({'revision':revision,'substitutions':substitutions})
    if os.environ.get('FAKE_FAILURE') == 'ambiguous_revision':
        twin = json.loads(json.dumps(revision)); twin['metadata']['name'] = 'fixlist-standard150-worker-00106-abd'
        state['twin'] = twin
    save()
    record = {'id': '7e3157ff-0913-4a6d-9aaf-bf476015c2b2', 'status': 'SUCCESS', 'results': {'images': [{'name': image, 'digest': digest}]}}
    failure = os.environ.get('FAKE_FAILURE')
    if failure == 'digest_missing': record['results'] = {'images': []}
    if failure == 'build_not_success': record['status'] = 'FAILURE'
    if failure == 'digest_malformed': record['results']['images'][0]['digest'] = 'latest'
    if '--format=json' in args and '--suppress-logs' in args: print(json.dumps(record))
elif args[:3] == ['run','revisions','list']: print(json.dumps([state['revision'], *([state['twin']] if 'twin' in state else [])]))
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
        {"name": "BASE44_APP_ID", "value": "6a498732ec779dfaaeab0e53"}, {"name": "BASE44_API_URL", "value": "https://base44.app"},
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


@pytest.mark.parametrize("mode", ["inactive", "owner-canary"])
@pytest.mark.parametrize("failure,reason", [
    ("environment", "environment does not match"),
    ("bucket_drift", "environment does not match"),
    ("alias", "legacy SCAN_PIPELINE_OWNER_IDS"),
])
def test_drifted_candidate_is_refused_before_any_immutable_tag_exists(candidate, mode, failure, reason):
    run, state, calls, sha = candidate
    options = inactive() if mode == "inactive" else owner_canary(sha)
    result = run(**options, FAKE_FAILURE=failure)
    assert result.returncode != 0 and reason in result.stderr, result.stderr
    made = [json.loads(line) for line in calls.read_text().splitlines()]
    assert not any(args[:3] == ["run", "services", "update-traffic"] for args in made)
    assert all(item.get("tag") != "staged-" + sha[:12] for item in json.loads(state.read_text())["service"]["status"]["traffic"])


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
    assert "_STAGED_OWNER_IDS" not in saved["substitutions"]
    tags = [args for args in map(json.loads, calls.read_text().splitlines()) if args[:3] == ["run", "services", "update-traffic"]]
    assert len(tags) == 1 and "--update-tags=staged-" + sha[:12] + "=fixlist-standard150-worker-00105-abc" in tags[0]
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


BUILD_CONFIGS = ("cloudbuild.durable-worker.yaml", "cloudbuild.durable-worker-static-egress-canary.yaml")


@pytest.mark.parametrize("config", BUILD_CONFIGS)
def test_cloud_build_steps_use_only_tools_their_images_provide(config):
    """No step may depend on python3 in the unpinned Cloud SDK image.

    Build 7e3157ff deployed, then failed tagging: that image no longer puts
    python3 on PATH. Tagging now runs in the preflighted wrapper. python3 is
    used only by the gcr.io/cloud-builders/gcloud substitution check, which
    verifies its tools before using them.
    """
    manifest = yaml.safe_load((ROOT / config).read_text())
    text = (ROOT / config).read_text()
    assert not any(step["id"] == "tag-staged-worker-candidate" for step in manifest["steps"])
    assert "staged_candidate_cloudbuild.py tag" not in text and '"tag",' not in text
    for step in manifest["steps"]:
        body = " ".join(map(str, step.get("args", [])))
        uses_python = step.get("entrypoint") == "python3" or "python3 " in body
        if uses_python:
            assert step["name"] == "gcr.io/cloud-builders/gcloud", (step["id"], step["name"])
            assert 'for tool in python3 gcloud; do' in body and body.index("command -v") < body.index("python3 scripts/")
        if step["name"].startswith("gcr.io/google.com/cloudsdktool/cloud-sdk"):
            assert step.get("entrypoint") == "gcloud", step["id"]
    # Every user substitution is referenced, or Cloud Build rejects the submit.
    for key in manifest["substitutions"]:
        assert "${" + key + "}" in text, key


def test_wrapper_refuses_before_any_cloud_call_when_a_required_tool_is_missing(candidate, tmp_path):
    run, state, calls, sha = candidate
    tools = tmp_path / "only-some-tools"
    tools.mkdir()
    for name in ("bash", "git", "env", "dirname", "cat", "mktemp", "rm", "tar", "printf"):
        found = shutil.which(name)
        if found:
            (tools / name).symlink_to(found)
    (tools / "gcloud").symlink_to(tmp_path / "bin" / "gcloud")
    result = run(**owner_canary(sha), PATH=str(tools))
    assert result.returncode == 2 and "required tool python3 is not on PATH" in result.stderr
    assert not calls.exists() and "revision" not in json.loads(state.read_text())


def test_wrapper_tags_after_build_with_the_same_guarded_helper(candidate):
    run, state, calls, sha = candidate
    result = run(**inactive())
    assert result.returncode == 0, result.stderr
    made = [json.loads(line) for line in calls.read_text().splitlines()]
    submit = next(i for i, args in enumerate(made) if args[:2] == ["builds", "submit"])
    tag = next(i for i, args in enumerate(made) if args[:3] == ["run", "services", "update-traffic"])
    assert submit < tag
    assert "_STAGED_OWNER_IDS" not in json.loads(state.read_text())["substitutions"]


@pytest.mark.parametrize("failure,reason", [
    ("digest_missing", "no single exact digest"),
    ("digest_malformed", "no single exact digest"),
    ("build_not_success", "not an exact successful build"),
    ("digest_mismatch", "exactly one revision of this source running the built image digest, found 0"),
    ("ambiguous_revision", "found 2"),
])
def test_no_tag_is_created_unless_one_ready_revision_runs_the_built_digest(candidate, failure, reason):
    run, state, calls, sha = candidate
    result = run(**owner_canary(sha), FAKE_FAILURE=failure)
    assert result.returncode != 0 and reason in result.stderr, result.stderr
    made = [json.loads(line) for line in calls.read_text().splitlines()]
    assert not any(args[:3] == ["run", "services", "update-traffic"] for args in made)
    assert all(item.get("tag") != "staged-" + sha[:12] for item in json.loads(state.read_text())["service"]["status"]["traffic"])


def test_build_record_digest_is_bound_and_reported(candidate):
    run, state, calls, sha = candidate
    result = run(**owner_canary(sha))
    assert result.returncode == 0, result.stderr
    assert "WORKER_CANDIDATE_IMAGE_DIGEST=sha256:" + "d" * 64 in result.stdout
    assert "WORKER_CANDIDATE_BUILD_ID=7e3157ff-0913-4a6d-9aaf-bf476015c2b2" in result.stdout
    submit = next(json.loads(line) for line in calls.read_text().splitlines() if json.loads(line)[:2] == ["builds", "submit"])
    assert "--suppress-logs" in submit and "--format=json" in submit


def test_tag_helper_refuses_a_revision_other_than_the_digest_bound_one(tmp_path):
    helper = load_script("staged_candidate_cloudbuild")
    sha = "c" * 40
    env = [{"name": "FIXLIST_WORKER_SOURCE_SHA", "value": sha}, {"name": "FIXLIST_STAGED_CONFIG_SHA256", "value": "f" * 64},
           {"name": "SCAN_PIPELINE_MODE", "value": "staged"}, {"name": "SCAN_STAGED_OWNER_IDS", "value": OWNER}]
    image = "europe-west1-docker.pkg.dev/example-project/workers/scanner@sha256:"
    rows = [{"metadata": {"name": "fixlist-standard150-worker-00107-aaa", "creationTimestamp": "2026-11-14T00:00:00Z"},
             "spec": {"containers": [{"env": env}]},
             "status": {"imageDigest": image + "1" * 64, "conditions": [{"type": "Ready", "status": "True"}]}}]
    calls = []
    def cloud(*arguments):
        calls.append(arguments)
        if arguments[:3] == ("run", "revisions", "list"):
            return rows
        raise AssertionError("no service read or tag update may happen")
    helper.cloud = cloud
    args = helper.argparse.Namespace(mode="owner-canary", source_sha=sha, tag=helper.source_tag(sha), digest="f" * 64,
                                     owners=OWNER, revision="fixlist-standard150-worker-00108-bbb",
                                     image_ref=image + "1" * 64, worker_service="w", region=REGION, project=PROJECT)
    with pytest.raises(ValueError, match="exact revision bound to the built image digest"):
        helper.tag_candidate(args)
    args.revision, args.image_ref = "fixlist-standard150-worker-00107-aaa", image + "2" * 64
    with pytest.raises(ValueError, match="No exact source/configuration"):
        helper.tag_candidate(args)
    # The bound revision exists but is not Ready: nothing is tagged.
    args.image_ref = image + "1" * 64
    rows[0]["status"]["conditions"] = [{"type": "Ready", "status": "False"}]
    with pytest.raises(ValueError, match="not Ready"):
        helper.tag_candidate(args)
    assert all(call[:3] == ("run", "revisions", "list") for call in calls)
    # Without both bindings the helper refuses before any cloud call.
    calls.clear()
    for missing in ("revision", "image_ref"):
        unbound = helper.argparse.Namespace(**{**vars(args), missing: ""})
        with pytest.raises(ValueError, match="exact digest-bound --revision|exact --image-ref"):
            helper.tag_candidate(unbound)
    unbound = helper.argparse.Namespace(**{**vars(args), "image_ref": "scanner:latest"})
    with pytest.raises(ValueError, match="exact --image-ref"):
        helper.tag_candidate(unbound)
    assert calls == []


def test_tag_cli_requires_both_bindings_for_staged_modes(tmp_path):
    base = [sys.executable, str(ROOT / "scripts/staged_candidate_cloudbuild.py"), "tag", "--mode=inactive",
            "--source-sha=" + "a" * 40, "--tag=staged-" + "a" * 12, "--digest=" + "f" * 64,
            "--worker-service=w", "--region=" + REGION, "--project=" + PROJECT]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gcloud").write_text("#!/bin/sh\necho called >> \"$0.calls\"\nexit 1\n")
    (bin_dir / "gcloud").chmod(0o755)
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    for extra in ([], ["--revision=fixlist-standard150-worker-00107-aaa"], ["--image-ref=reg.example/scanner@sha256:" + "1" * 64]):
        checked = subprocess.run(base + extra, env=env, capture_output=True, text=True)
        assert checked.returncode != 0 and "STAGED_CANDIDATE_BLOCKED" in checked.stderr
    assert not (bin_dir / "gcloud.calls").exists()
    off = subprocess.run([*base[:3], "--mode=off", *base[4:]], env=env, capture_output=True, text=True)
    assert off.returncode == 0


@pytest.mark.parametrize("failure,message", [
    ("foreign_app", "Base44 app routing"),
    ("foreign_origin", "Base44 API origin"),
    ("missing_app", "Base44 app routing"),
    ("duplicate_app", "duplicate worker template environment name"),
    ("duplicate_container", "exactly one container"),
])
def test_candidate_build_refuses_foreign_or_ambiguous_base44_routing_before_cloudbuild(candidate, failure, message):
    """A source-matching worker must not inherit a foreign persistence destination."""
    run, state, calls, sha = candidate
    saved = json.loads(state.read_text())
    containers = saved["service"]["spec"]["template"]["spec"]["containers"]
    env = containers[0]["env"]
    if failure == "foreign_app":
        next(row for row in env if row["name"] == "BASE44_APP_ID")["value"] = "foreign-app"
    elif failure == "foreign_origin":
        next(row for row in env if row["name"] == "BASE44_API_URL")["value"] = "https://other-base44.example"
    elif failure == "missing_app":
        env[:] = [row for row in env if row["name"] != "BASE44_APP_ID"]
    elif failure == "duplicate_app":
        env.append({"name": "BASE44_APP_ID", "value": "foreign-app"})
    else:
        containers.append(dict(containers[0]))
    state.write_text(json.dumps(saved))

    result = run(**inactive())
    assert result.returncode != 0 and message in result.stderr, result.stderr
    after = json.loads(state.read_text())
    assert "revision" not in after, "candidate revision must not be built from a foreign route"
    commands = [json.loads(row) for row in calls.read_text().splitlines()]
    assert not any(command[:2] == ["builds", "submit"] for command in commands)
    assert not any(command[:3] == ["run", "services", "update-traffic"] for command in commands)
