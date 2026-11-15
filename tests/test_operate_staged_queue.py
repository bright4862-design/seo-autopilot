"""Guarded stage-queue activation/recovery across its real shell/Python boundary.

A stateful fake gcloud stands in for Cloud Run and Cloud Tasks; the existing
read-only infrastructure verifier is replaced by a logging stub, as in
test_staged_rollout_operator.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import staged_queue_guard as guard  # noqa: E402
from staged_candidate_cloudbuild import digest_for, environment as inactive_environment  # noqa: E402

ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
SOURCE = "4274ac453e93fe2e161e01c88d31823bd5134795"
TAG = f"staged-{SOURCE[:12]}"
TARGET = f"https://{TAG}---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
SERVING = "fixlist-standard150-worker-00097-lvl"
CANDIDATE = "fixlist-standard150-worker-00104-l79"
QUEUE_PATH = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages"


def env_list(values):
    return [{"name": k, "value": v} for k, v in values.items()]


def target_for(source):
    return f"https://staged-{source[:12]}---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"


def candidate_env(source=SOURCE, **overrides):
    """A revision built by the reviewed inactive Cloud Build path, then cohorted."""
    reviewed = inactive_environment(source, guard.PROJECT, guard.REGION, guard.WORKSPACE_BUCKET, QUEUE_PATH, ORIGIN)
    values = {
        **reviewed,
        "FIXLIST_STAGED_CONFIG_SHA256": digest_for(source, reviewed),
        "FIXLIST_WORKER_SOURCE_SHA": source,
        "TASKS_INVOKER_SERVICE_ACCOUNT": guard.INVOKER_SA,
        "SCAN_PIPELINE_MODE": "staged",
        "SCAN_STAGED_OWNER_IDS": "owner_canary_01",
    }
    values.update(overrides)
    return {k: v for k, v in values.items() if v is not None}


def revision(name, env, sa=guard.WORKER_SA):
    return {"metadata": {"name": name},
            "spec": {"serviceAccountName": sa, "containers": [{"env": env_list(env)}]}}


def service(candidate_percent=0, tag=None, url=None, source=SOURCE):
    tag = f"staged-{source[:12]}" if tag is None else tag
    url = target_for(source) if url is None else url
    return {"status": {"url": ORIGIN, "traffic": [
        {"revisionName": SERVING, "percent": 100 - candidate_percent},
        {"revisionName": CANDIDATE, "percent": candidate_percent, "tag": tag, "url": url},
    ]}}


# --- pure guard ---------------------------------------------------------------

def revisions(candidate=None, serving=None, source=SOURCE):
    return {CANDIDATE: revision(CANDIDATE, candidate or candidate_env(source)),
            SERVING: revision(SERVING, serving or {"SCAN_PIPELINE_MODE": "monolith"})}


def test_activation_accepts_exact_tagged_zero_traffic_candidate():
    found = guard.check_activation_candidate(service(), revisions(), CANDIDATE, SOURCE)
    assert found["target"] == TARGET and found["audience"] == ORIGIN and found["owner_count"] == "1"


def test_inactive_candidate_with_no_cohort_can_activate():
    env = candidate_env(SCAN_PIPELINE_MODE="monolith", SCAN_STAGED_OWNER_IDS="")
    assert guard.check_activation_candidate(service(), revisions(env), CANDIDATE, SOURCE)["owner_count"] == "0"


@pytest.mark.parametrize("change, message", [
    (dict(SCAN_STAGED_OWNER_IDS="*"), "Wildcard"),
    (dict(SCAN_STAGED_OWNER_IDS="a,b"), "exact owner IDs"),
    (dict(SCAN_STAGED_OWNER_IDS=",".join(f"owner_{i:04d}" for i in range(6))), "exact owner IDs"),
    (dict(SCAN_STAGE_TARGET_URL=ORIGIN), "own source-bound tag"),
    (dict(SCAN_STAGE_TOKEN_AUDIENCE=TARGET), "canonical service origin"),
    (dict(SCAN_STAGE_TASKS_QUEUE_PATH=QUEUE_PATH.replace("fixlist-scan-stages", "other")), "fixed stage queue"),
    (dict(TASKS_INVOKER_SERVICE_ACCOUNT="x@y.iam.gserviceaccount.com"), "invoker"),
    (dict(SCAN_WORKSPACE_BUCKET=None), "workspace bucket"),
    (dict(SCAN_WORKSPACE_BUCKET="unverified-workspace-other-tenant"), "fixed workspace bucket"),
    (dict(SCAN_WORKSPACE_BUCKET=""), "fixed workspace bucket"),
    (dict(FIXLIST_WORKER_SOURCE_SHA="abc"), "SOURCE_SHA"),
    (dict(SCAN_PIPELINE_MODE="hybrid"), "monolith or staged"),
])
def test_activation_refuses_misconfigured_candidate(change, message):
    with pytest.raises(guard.GuardError, match=message):
        guard.check_activation_candidate(service(), revisions(candidate_env(**change)), CANDIDATE, SOURCE)


def test_activation_refuses_traffic_wrong_tag_wrong_sa_and_other_admitters():
    with pytest.raises(guard.GuardError, match="production traffic"):
        guard.check_activation_candidate(service(candidate_percent=10), revisions(), CANDIDATE, SOURCE)
    with pytest.raises(guard.GuardError, match="source-bound tag"):
        guard.check_activation_candidate(service(tag="candidate", url=TARGET), revisions(), CANDIDATE, SOURCE)
    bad_sa = revisions()
    bad_sa[CANDIDATE] = revision(CANDIDATE, candidate_env(), sa="other@x.iam.gserviceaccount.com")
    with pytest.raises(guard.GuardError, match="service account"):
        guard.check_activation_candidate(service(), bad_sa, CANDIDATE, SOURCE)
    with pytest.raises(guard.GuardError, match="Other revision"):
        guard.check_activation_candidate(
            service(), revisions(serving={"SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": "owner_canary_01"}),
            CANDIDATE, SOURCE)
    with pytest.raises(guard.GuardError, match="exact worker revision"):
        guard.check_activation_candidate(service(), revisions(), "latest", SOURCE)


@pytest.mark.parametrize("percent", [0.9, False, "0", None, -0.9, 101, -1, 0.0])
def test_ambiguous_traffic_percentages_are_refused(percent):
    for target in (CANDIDATE, SERVING):
        svc = service()
        entry = next(e for e in svc["status"]["traffic"] if e["revisionName"] == target)
        entry["percent"] = percent
        with pytest.raises(guard.GuardError, match="Ambiguous traffic percentage"):
            guard.check_activation_candidate(svc, revisions(), CANDIDATE, SOURCE)
        with pytest.raises(guard.GuardError, match="Ambiguous traffic percentage"):
            guard.check_intake_disabled(svc, revisions(), {})


def test_omitted_percent_is_the_protobuf_zero_and_untagged_zero_is_still_validated():
    svc = service()
    del next(e for e in svc["status"]["traffic"] if e["revisionName"] == CANDIDATE)["percent"]
    assert guard.check_activation_candidate(svc, revisions(), CANDIDATE, SOURCE)["target"] == TARGET
    svc = service()
    svc["status"]["traffic"].append({"revisionName": "fixlist-standard150-worker-00001-old", "percent": "0"})
    with pytest.raises(guard.GuardError, match="Ambiguous traffic percentage"):
        guard.addressable_revisions(svc)
    assert guard.serving_revision(service()) == SERVING
    with pytest.raises(guard.GuardError, match="Ambiguous"):
        guard.serving_revision({"status": {"traffic": [{"revisionName": "gw", "percent": 100.0}]}})


OTHER_SOURCE = "0123456789abcdef0123456789abcdef01234567"


def test_valid_candidate_from_a_different_source_is_refused():
    # Fully valid, tagged and digest-bound, but built from another commit.
    other = service(source=OTHER_SOURCE)
    assert guard.check_activation_candidate(other, revisions(source=OTHER_SOURCE), CANDIDATE, OTHER_SOURCE)
    with pytest.raises(guard.GuardError, match="not the confirmed source"):
        guard.check_activation_candidate(other, revisions(source=OTHER_SOURCE), CANDIDATE, SOURCE)


@pytest.mark.parametrize("change, message", [
    (dict(FIXLIST_STAGED_CONFIG_SHA256=None), "digest"),
    (dict(FIXLIST_STAGED_CONFIG_SHA256="0" * 64), "digest"),
    (dict(SCAN_TASKS_PROJECT="other-project"), "drifted.*SCAN_TASKS_PROJECT"),
    (dict(SCAN_STAGE_QUEUE="fixlist-standard150"), "drifted.*SCAN_STAGE_QUEUE"),
    (dict(SCAN_TASKS_LOCATION=None), "drifted.*SCAN_TASKS_LOCATION"),
])
def test_configuration_digest_and_drift_are_refused(change, message):
    with pytest.raises(guard.GuardError, match=message):
        guard.check_activation_candidate(service(), revisions(candidate_env(**change)), CANDIDATE, SOURCE)


@pytest.mark.parametrize("change", [
    dict(SCAN_STAGED_OWNER_IDS="", SCAN_PIPELINE_OWNER_IDS="owner_canary_01"),
    dict(SCAN_STAGED_OWNER_IDS="owner_canary_01", SCAN_PIPELINE_OWNER_IDS="owner_other_02"),
    dict(SCAN_STAGED_OWNER_IDS="owner_canary_01", SCAN_PIPELINE_OWNER_IDS="owner_canary_01"),
])
def test_legacy_cohort_alias_is_refused_so_worker_and_base44_cannot_disagree(change):
    # The worker reads the alias when the primary is empty; Base44 V9 never does.
    with pytest.raises(guard.GuardError, match="Legacy SCAN_PIPELINE_OWNER_IDS"):
        guard.check_activation_candidate(service(), revisions(candidate_env(**change)), CANDIDATE, SOURCE)


def test_primary_only_cohort_activates_and_an_empty_alias_is_tolerated():
    for env in (candidate_env(), candidate_env(SCAN_PIPELINE_OWNER_IDS=""),
                candidate_env(SCAN_PIPELINE_OWNER_IDS="  ")):
        found = guard.check_activation_candidate(service(), revisions(env), CANDIDATE, SOURCE)
        assert found["owner_count"] == "1"


def test_activate_shell_refuses_a_candidate_carrying_the_legacy_alias(operator):
    sha, write_state, run = operator
    write_state(candidate=dict(SCAN_STAGED_OWNER_IDS="", SCAN_PIPELINE_OWNER_IDS="owner_canary_01"))
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and "Legacy SCAN_PIPELINE_OWNER_IDS" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def barrier_line(mode="closed", generation=7, ready="true", active=0, bound=0, live=0, snapshot="snap-1"):
    return (f"ADMISSION_BARRIER_STATUS mode={mode} generation={generation} drain_ready={ready} "
            f"active={active} bound={bound} expired_diagnostic=0 live_reconciliation={live} snapshot={snapshot}")


def test_barrier_proof_requires_closed_generation_and_terminal_obligations():
    assert guard.check_barrier(barrier_line(), "7", True).startswith("generation=7 snapshot=snap-1")
    # Recovery only needs new admissions closed: outstanding scans are the point.
    assert "active=2" in guard.check_barrier(barrier_line(ready="false", active=2), "7", False)
    for line, message in [
        (barrier_line(mode="open"), "barrier is open"),
        (barrier_line(mode="acceptance_only"), "barrier is acceptance_only"),
        (barrier_line(generation=8), "generation changed"),
        (barrier_line(ready="false"), "not all terminal"),
        (barrier_line(active=1), "not all terminal"),
        (barrier_line(bound=1), "not all terminal"),
        (barrier_line(live=1), "not all terminal"),
        ("", "No single"),
        (barrier_line() + "\n" + barrier_line(), "No single"),
        (barrier_line() + " extra=1", "malformed"),
    ]:
        with pytest.raises(guard.GuardError, match=message):
            guard.check_barrier(line, "7", True)
    with pytest.raises(guard.GuardError, match="barrier is open"):
        guard.check_barrier(barrier_line(mode="open"), "7", False)


def test_intake_disabled_checks_every_addressable_revision_and_gateway():
    off = candidate_env(SCAN_PIPELINE_MODE="monolith")
    assert guard.check_intake_disabled(service(), revisions(off), {}) == sorted([CANDIDATE, SERVING])
    with pytest.raises(guard.GuardError, match=CANDIDATE):
        guard.check_intake_disabled(service(), revisions(), {})
    with pytest.raises(guard.GuardError, match="gateway"):
        guard.check_intake_disabled(service(), revisions(off),
                                    {"SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": "owner_canary_01"})
    with pytest.raises(guard.GuardError, match="Missing revision readback"):
        guard.check_intake_disabled(service(), {SERVING: revisions(off)[SERVING]}, {})
    # Staged mode with an empty cohort admits nobody, exactly like the worker.
    empty = candidate_env(SCAN_STAGED_OWNER_IDS="")
    assert guard.check_intake_disabled(service(), revisions(empty), {})


# --- shell wrapper ------------------------------------------------------------

ACTIVATE = "ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:" + CANDIDATE + ":7"
ACT = {"STAGED_REVISION": CANDIDATE, "BARRIER_EXPECTED_GENERATION": "7"}

FAKE_GCLOUD = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FAKE_STATE"]
state = json.load(open(state_path))
args = sys.argv[1:]
with open(os.environ["TEST_CALL_LOG"], "a") as f:
    f.write(json.dumps(["gcloud", *args]) + "\n")
def out(value):
    print(json.dumps(value) if not isinstance(value, str) else value)
def save():
    json.dump(state, open(state_path, "w"))
if args[:3] == ["run", "services", "describe"]:
    svc = state["services"][args[3]]
    if "FAKE_CANDIDATE_PERCENT" in os.environ:
        for entry in svc["status"]["traffic"]:
            if entry.get("tag"):
                entry["percent"] = json.loads(os.environ["FAKE_CANDIDATE_PERCENT"])
    out(svc)
elif args[:3] == ["run", "revisions", "describe"]:
    out(state["revisions"][args[3]])
elif args[:3] == ["tasks", "queues", "describe"]:
    out(state["queues"][args[3]]["state"])
elif args[:3] == ["tasks", "queues", "pause"]:
    state["queues"][args[3]]["state"] = "PAUSED"
    reads = state.get("tasks_after_pause")
    if reads:
        state["queues"][args[3]]["tasks"] = reads
    if state.get("barrier_after_pause"):
        state["barrier"] = state["barrier_after_pause"]
    save()
elif args[:3] == ["tasks", "queues", "resume"]:
    state["queues"][args[3]]["state"] = "RUNNING"; save()
elif args[:2] == ["tasks", "describe"]:
    queue = [a.split("=", 1)[1] for a in args if a.startswith("--queue=")][0]
    prefix = f"projects/seo-autopilot-501517/locations/europe-west1/queues/{queue}/tasks/"
    for t in state["queues"][queue]["tasks"]:
        task = t if isinstance(t, dict) else {"id": t}
        if task["id"] == args[2]:
            if state.get("describe_fails"):
                sys.exit("ERROR: (gcloud.tasks.describe) PERMISSION_DENIED")
            out({"name": prefix + task["id"], **{k: v for k, v in task.items() if k != "id"}})
            break
    else:
        sys.exit("NOT_FOUND")
elif args[:2] == ["tasks", "list"]:
    queue = [a.split("=", 1)[1] for a in args if a.startswith("--queue=")][0]
    tasks = state["queues"][queue]["tasks"]
    drained = state.get("drain_after_reads", {}).get(queue)
    if drained is not None:
        state["drain_after_reads"][queue] = drained - 1
        if drained <= 1:
            state["queues"][queue]["tasks"] = []
        save()
    ids = [t["id"] if isinstance(t, dict) else t for t in tasks]
    ids += state.get("phantom_listing", {}).get(queue, [])
    out([{"name": f"projects/seo-autopilot-501517/locations/europe-west1/queues/{queue}/tasks/{t}"} for t in ids])
else:
    sys.exit(f"unexpected gcloud {args}")
'''


@pytest.fixture
def operator(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts/lib").mkdir(parents=True)
    for name in ("operate-staged-queue.sh", "staged_queue_guard.py", "staged_candidate_cloudbuild.py",
                 "prepare_staged_scan_infra.py", "lib/release-source-guard.sh"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    # Keep the verifier's real per-task predicate (the guard imports it) and
    # stub only its gcloud-reading main.
    real_verifier = (ROOT / "scripts/verify_staged_scan_infra.py").read_text().split("\ndef describe(")[0]
    # Stands in for the operator's signed barrier-status readback.
    (repo / "scripts/fixlist-cloud-operator.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nexec python3 - <<'PY'\n"
        "import json,os,sys\n"
        "with open(os.environ['TEST_CALL_LOG'],'a') as f: f.write(json.dumps(['barrier',os.environ['OPERATION'],"
        "os.environ['SOURCE_SHA'],os.environ['BARRIER_EXPECTED_GENERATION'],os.environ['BARRIER_EXPECTED_PRIOR_MODE'],"
        "os.environ['CHANGE_TICKET'],os.environ.get('CLOUDSDK_AUTH_ACCESS_TOKEN_FILE',''),"
        "os.environ.get('GCP_OPERATOR_SERVICE_ACCOUNT','')])+'\\n')\n"
        "b=json.load(open(os.environ['FAKE_STATE']))['barrier']\n"
        "if b is None: sys.exit('Refusing: barrier snapshot signature invalid')\n"
        "print('ADMISSION_BARRIER_STATUS mode={mode} generation={generation} drain_ready={ready} active={active} "
        "bound={bound} expired_diagnostic=0 live_reconciliation={live} snapshot=snap-{generation}'.format(**b))\n"
        "PY\n")
    (repo / "scripts/verify_staged_scan_infra.py").write_text(
        real_verifier + "\n\nif __name__ == '__main__':\n" + textwrap.indent(
        "import json,os,sys\n"
        "with open(os.environ['TEST_CALL_LOG'],'a') as f: f.write(json.dumps(['verify',*sys.argv[1:]])+'\\n')\n"
        "state=json.load(open(os.environ['FAKE_STATE']))\n"
        "want=sys.argv[sys.argv.index('--expected-queue-state')+1]\n"
        "fail=os.environ.get('FAKE_VERIFY_FAIL')==want\n"
        # Lets a test model a producer acting while the slow checks run.
        "late=state.pop('during_paused_verify',None) if want=='PAUSED' else None\n"
        "if late:\n"
        "    for k,v in late.items():\n"
        "        if k=='stage_tasks': state['queues']['fixlist-scan-stages']['tasks']=v\n"
        "        else: state[k]=v\n"
        "    json.dump(state,open(os.environ['FAKE_STATE'],'w'))\n"
        "sys.exit(0 if state['queues']['fixlist-scan-stages']['state']==want and not fail else 'FAIL: state')\n",
        "    "))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gcloud").write_text(FAKE_GCLOUD)
    (bin_dir / "gcloud").chmod(0o755)
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "sleep").chmod(0o755)
    for args in (("init", "-q"), ("config", "user.name", "Test"), ("config", "user.email", "t@example.invalid"),
                 ("add", "."), ("commit", "-qm", "fixture")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    state_path, log = tmp_path / "state.json", tmp_path / "calls.jsonl"

    def write_state(stage_state="PAUSED", candidate=None, serving=None, gateway=None,
                    stage_tasks=(), entry_tasks=(), drain_tasks=(), barrier=None, source=None,
                    earlier_sources=(), **extra):
        gateway_env = gateway or {"SCAN_PIPELINE_MODE": "monolith"}
        source = source or sha
        state = {
            "barrier": barrier_state(**(barrier or {})) if barrier is not False else None,
            "services": {
                "fixlist-standard150-worker": service(source=source),
                "fixlist-dispatch-gateway": {"status": {"traffic": [{"revisionName": "gw-00009-abc", "percent": 100}]}},
            },
            "revisions": {**revisions(candidate_env(source, **(candidate or {})), serving, source),
                          "gw-00009-abc": revision("gw-00009-abc", gateway_env, sa="gw@x")},
            "queues": {"fixlist-scan-stages": {"state": stage_state, "tasks": list(stage_tasks)},
                       "fixlist-standard150": {"state": "RUNNING", "tasks": list(entry_tasks)},
                       "fixlist-standard150-drain": {"state": "RUNNING", "tasks": list(drain_tasks)}},
            **extra,
        }
        for index, earlier in enumerate(earlier_sources):
            name = f"fixlist-standard150-worker-0009{index}-old"
            state["services"]["fixlist-standard150-worker"]["status"]["traffic"].append(
                {"revisionName": name, "percent": 0, "tag": f"staged-{earlier[:12]}", "url": target_for(earlier)})
            state["revisions"][name] = revision(name, candidate_env(earlier))
        state_path.write_text(json.dumps(state))

    def run(operation, confirm="", **env_overrides):
        log.write_text("")
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GITHUB_ACTIONS": "true",
               "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha, "SOURCE_SHA": sha,
               "TEST_CALL_LOG": str(log), "FAKE_STATE": str(state_path), "OPERATION": operation,
               "CONFIRM": confirm, "STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS": "5",
               "STAGED_QUEUE_DRAIN_POLL_SECONDS": "0", "STAGED_QUEUE_DRAIN_STABLE_READS": "2",
               # The real repo ignores __pycache__/; this bare fixture repo does not.
               "PYTHONDONTWRITEBYTECODE": "1", **env_overrides}
        result = subprocess.run(["bash", "scripts/operate-staged-queue.sh"], cwd=repo, env=env,
                                text=True, capture_output=True, timeout=30)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        final = json.loads(state_path.read_text())
        return result, calls, final

    return sha, write_state, run


def stage_task(task_id, source, path="/scan-batch", **change):
    task = {"id": task_id, "dispatchDeadline": "480s", "httpRequest": {
        "url": target_for(source) + path, "httpMethod": "POST",
        "oidcToken": {"serviceAccountEmail": guard.INVOKER_SA, "audience": ORIGIN}}}
    for key, value in change.items():
        if key == "deadline":
            task["dispatchDeadline"] = value
        elif key in ("url", "httpMethod"):
            task["httpRequest"][key] = value
        else:
            task["httpRequest"]["oidcToken"][key] = value
    return task


def barrier_state(mode="closed", generation=7, ready="true", active=0, bound=0, live=0):
    return dict(mode=mode, generation=generation, ready=ready, active=active, bound=bound, live=live)


def mutations(calls):
    return [c for c in calls if c[0] == "gcloud" and c[1:3] in (["tasks", "queues"],)
            and c[3] in ("pause", "resume", "delete", "purge", "create", "update")]


def test_activate_requires_exact_confirmation_bound_to_revision(operator):
    sha, write_state, run = operator
    write_state()
    for confirm in ("", f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages",
                    f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{CANDIDATE}",
                    f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{SERVING}:7",
                    f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{CANDIDATE}:8"):
        result, calls, final = run("activate", confirm, **ACT)
        assert result.returncode == 2 and "confirmation required" in result.stderr
        assert calls == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"
    result, calls, _ = run("activate", ACTIVATE.format(sha=sha), STAGED_REVISION=CANDIDATE)
    assert result.returncode == 2 and "BARRIER_EXPECTED_GENERATION" in result.stderr and calls == []


@pytest.mark.parametrize("during, message", [
    (dict(stage_tasks=["late-plan-batch"]), "use recover"),
    (dict(barrier=barrier_state(mode="acceptance_only")), "barrier is acceptance_only"),
    (dict(barrier=barrier_state(ready="false", active=1)), "not all terminal"),
])
def test_activate_rereads_queue_and_barrier_after_the_slow_checks(operator, during, message):
    sha, write_state, run = operator
    # A producer acts while the candidate and infrastructure checks run.
    write_state(during_paused_verify=during)
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and message in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


@pytest.mark.parametrize("barrier, message", [
    (dict(mode="acceptance_only"), "barrier is acceptance_only"),
    (dict(mode="open"), "barrier is open"),
    (dict(ready="false", active=1), "not all terminal"),
    (dict(generation=8), "generation changed"),
    (False, "snapshot could not be read"),
])
def test_activate_requires_closed_drained_admissions_first(operator, barrier, message):
    sha, write_state, run = operator
    write_state(barrier=barrier)
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and message in result.stderr
    assert mutations(calls) == [] and not any(c[0] == "verify" for c in calls)


def test_activate_resumes_only_after_full_readback(operator):
    sha, write_state, run = operator
    write_state()
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode == 0, result.stderr
    assert final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"
    verifies = [c for c in calls if c[0] == "verify"]
    assert [v[v.index("--expected-queue-state") + 1] for v in verifies] == ["PAUSED", "RUNNING"]
    assert verifies[0][verifies[0].index("--worker-url") + 1] == target_for(sha)
    assert verifies[0][verifies[0].index("--token-audience") + 1] == ORIGIN
    resume = [i for i, c in enumerate(calls) if c[1:4] == ["tasks", "queues", "resume"]]
    assert len(resume) == 1 and calls.index(verifies[0]) < resume[0] < calls.index(verifies[1])
    # Barrier and queue are re-read after the slow checks, right before resume.
    barriers = [i for i, c in enumerate(calls) if c[0] == "barrier"]
    lists = [i for i, c in enumerate(calls) if c[1:3] == ["tasks", "list"]]
    assert len(barriers) == 2 and barriers[0] < calls.index(verifies[0]) < barriers[1] < resume[0]
    assert any(calls.index(verifies[0]) < i < resume[0] for i in lists)
    assert "STAGED_QUEUE_ACTIVATION_PROOF generation=7" in result.stdout
    assert [c[3] for c in mutations(calls)] == ["resume"]
    assert "STAGED_QUEUE_ACTIVATED" in result.stdout


def test_activate_refuses_misconfigured_candidate_without_mutation(operator):
    sha, write_state, run = operator
    write_state(candidate=dict(SCAN_STAGED_OWNER_IDS="*"))
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and "Wildcard" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


@pytest.mark.parametrize("percent", [0.9, False, "0", None, -0.9])
def test_activate_makes_no_mutation_on_ambiguous_candidate_traffic(operator, percent):
    sha, write_state, run = operator
    write_state()
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT, FAKE_CANDIDATE_PERCENT=json.dumps(percent))
    assert result.returncode != 0 and "Ambiguous traffic percentage" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_activate_refuses_paused_queue_holding_tasks(operator):
    sha, write_state, run = operator
    write_state(stage_tasks=["t1"])
    result, calls, _ = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode == 2 and "use recover" in result.stderr and mutations(calls) == []


def test_activate_refuses_a_valid_candidate_built_from_another_source(operator):
    sha, write_state, run = operator
    write_state(source=OTHER_SOURCE)
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and "not the confirmed source" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_activate_refuses_configuration_drift(operator):
    sha, write_state, run = operator
    write_state(candidate=dict(SCAN_STAGE_QUEUE="fixlist-standard150"))
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT)
    assert result.returncode != 0 and "drifted" in result.stderr and mutations(calls) == []


def test_activate_reports_partial_activation_when_post_resume_verification_fails(operator):
    sha, write_state, run = operator
    write_state()
    result, calls, final = run("activate", ACTIVATE.format(sha=sha), **ACT, FAKE_VERIFY_FAIL="RUNNING")
    assert result.returncode == 3
    assert "STAGED_QUEUE_PARTIAL_ACTIVATION observed_state=RUNNING tasks=0" in result.stderr
    assert "STAGED_QUEUE_ACTIVATED" not in result.stdout
    # Reported, not blindly paused: a scan may already depend on the queue.
    assert [c[3] for c in mutations(calls)] == ["resume"]


DRAIN = "DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:7"
RECOVER = "RECOVER-STAGED-QUEUE:{sha}:fixlist-scan-stages:7"


def test_barrier_reads_use_the_admission_identity_only_when_a_token_file_is_given(operator, tmp_path):
    sha, write_state, run = operator
    token = tmp_path / "barrier-token"
    token.write_text("opaque")
    write_state(stage_tasks=[stage_task("b1", sha)])
    result, calls, _ = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7",
                           STAGED_BARRIER_ACCESS_TOKEN_FILE=str(token),
                           GCP_OPERATOR_SERVICE_ACCOUNT="fixlist-github-operator@seo-autopilot-501517.iam.gserviceaccount.com")
    assert result.returncode == 0, result.stderr
    barriers = [c for c in calls if c[0] == "barrier"]
    assert barriers and all(c[6] == str(token) for c in barriers)
    assert all(c[7] == "fixlist-admission-operator@seo-autopilot-501517.iam.gserviceaccount.com" for c in barriers)
    # Without a token file nothing is overridden (local operator runs).
    write_state(stage_tasks=[stage_task("b1", sha)])
    result, calls, _ = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 0 and all(c[6] == "" for c in calls if c[0] == "barrier")
    token.write_text("")
    write_state(stage_tasks=[stage_task("b1", sha)])
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7",
                               STAGED_BARRIER_ACCESS_TOKEN_FILE=str(token))
    assert result.returncode != 0 and "token file is empty" in result.stderr and mutations(calls) == []


def test_cloud_operator_workflow_wires_every_staged_queue_operation():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text())
    options = workflow[True]["workflow_dispatch"]["inputs"]["operation"]["options"]
    ops = ["staged-queue-status", "staged-queue-activate", "staged-queue-drain-pause", "staged-queue-recover"]
    assert all(op in options for op in ops)
    steps = {step.get("name"): step for step in workflow["jobs"]["operate"]["steps"]}
    run_step = steps["Operate staged scan queue"]
    assert run_step["if"] == "startsWith(inputs.operation, 'staged-queue-')"
    assert "scripts/operate-staged-queue.sh" in run_step["run"]
    for op, local in zip(ops, ["status", "activate", "drain-pause", "recover"]):
        assert f"{op}) export OPERATION={local} ;;" in run_step["run"]
    assert run_step["env"]["SOURCE_SHA"] == "${{ github.sha }}"
    # The generic operator step must never also receive these operations.
    assert "!startsWith(inputs.operation, 'staged-queue-')" in steps["Run allowlisted worker operation"]["if"]
    for name in ("Mint coordinator operator identity token", "Mint admission access token for staged-queue barrier reads"):
        for op in ops[1:]:
            assert f'"{op}"' in steps[name]["if"]
    barrier_auth = steps["Mint admission access token for staged-queue barrier reads"]["with"]
    assert barrier_auth["token_format"] == "access_token" and barrier_auth["create_credentials_file"] is False
    assert barrier_auth["service_account"] == "${{ env.GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT }}"
    # Queue calls keep the GitHub operator as the active gcloud identity.
    auth = steps["Authenticate to Google Cloud"]["with"]["service_account"]
    assert not any(op in auth for op in ops)


def test_drain_pause_and_recover_confirmations_bind_the_barrier_generation(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING")
    for confirm in (f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF",
                    f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:8"):
        result, calls, _ = run("drain-pause", confirm, BARRIER_EXPECTED_GENERATION="7")
        assert result.returncode == 2 and "confirmation required" in result.stderr and calls == []
    result, calls, _ = run("drain-pause", DRAIN.format(sha=sha))
    assert result.returncode == 2 and "BARRIER_EXPECTED_GENERATION" in result.stderr and calls == []


@pytest.mark.parametrize("barrier, message", [
    (dict(mode="open"), "barrier is open"),
    (dict(mode="acceptance_only"), "barrier is acceptance_only"),
    (dict(generation=8), "generation changed"),
    (dict(ready="false", active=1), "not all terminal"),
    (dict(bound=1), "not all terminal"),
    (dict(live=1), "not all terminal"),
    (False, "snapshot could not be read"),
])
def test_drain_pause_refuses_without_a_closed_drained_barrier_even_with_empty_queues(operator, barrier, message):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", barrier=barrier)
    result, calls, final = run("drain-pause", DRAIN.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode != 0 and message in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_drain_pause_needs_the_barrier_proof_then_empty_feeders_then_pauses(operator):
    sha, write_state, run = operator
    # A still-cohorted worker no longer blocks: the barrier is the intake proof.
    write_state(stage_state="RUNNING", stage_tasks=["b1"], drain_tasks=["w1"],
                drain_after_reads={"fixlist-scan-stages": 2, "fixlist-standard150-drain": 3})
    result, calls, final = run("drain-pause", DRAIN.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 0, result.stderr
    assert final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"
    reads = [line for line in result.stdout.splitlines() if line.startswith("STAGED_QUEUE_DRAIN_READ")]
    assert reads[-2:] == ["STAGED_QUEUE_DRAIN_READ stage=0 entry=0 drain=0"] * 2
    assert "stage=1" in reads[0]
    assert "STAGED_QUEUE_PAUSE_PROOF generation=7 snapshot=snap-7" in result.stdout
    barriers = [i for i, c in enumerate(calls) if c[0] == "barrier"]
    pause = [i for i, c in enumerate(calls) if c[1:4] == ["tasks", "queues", "pause"]][0]
    assert len(barriers) == 3 and barriers[1] < pause < barriers[2]
    assert all(calls[i][1] == "barrier-status" and calls[i][2] == sha and calls[i][3:5] == ["7", "closed"]
               for i in barriers)
    assert [c[3] for c in mutations(calls)] == ["pause"]


def test_drain_pause_times_out_and_leaves_queue_running(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", entry_tasks=["e1"])
    result, calls, final = run("drain-pause", DRAIN.format(sha=sha), BARRIER_EXPECTED_GENERATION="7",
                               STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS="0")
    assert result.returncode == 1 and "STAGED_QUEUE_DRAIN_INCOMPLETE" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_drain_pause_compensates_a_task_that_races_the_pause(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", tasks_after_pause=["late"])
    result, calls, final = run("drain-pause", DRAIN.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 1 and "COMPENSATED" in result.stderr
    assert [c[3] for c in mutations(calls)] == ["pause", "resume"]
    assert final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


@pytest.mark.parametrize("after", [dict(active=1, ready="false"), dict(mode="open"), dict(generation=8)])
def test_drain_pause_compensates_an_admission_that_races_the_pause(operator, after):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", barrier_after_pause=barrier_state(**after))
    result, calls, final = run("drain-pause", DRAIN.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 1 and "COMPENSATED" in result.stderr
    assert [c[3] for c in mutations(calls)] == ["pause", "resume"]
    assert final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_recover_resumes_a_stranded_scan_on_a_still_cohorted_tagged_worker(operator):
    sha, write_state, run = operator
    # The exact scan recovery exists for: admitted, obligations outstanding,
    # its tagged worker revision still cohorted, new admissions closed. Its
    # tasks belong to an EARLIER verified tag, not the current main.
    tasks = [stage_task("b1", OTHER_SOURCE), stage_task("f1", OTHER_SOURCE, "/scan-finalize"), stage_task("b2", sha)]
    write_state(stage_tasks=tasks, earlier_sources=[OTHER_SOURCE], barrier=dict(ready="false", active=1, bound=1))
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 0, result.stderr
    # The guard serializes tag counts in lexical order, not task/source order.
    # A temporary Git SHA can sort either side of OTHER_SOURCE; assert the
    # actual wire-order contract rather than depending on random fixture SHA.
    expected_tags = ",".join(f"{tag}:{count}" for tag, count in sorted([
        (f"staged-{OTHER_SOURCE[:12]}", 2), (f"staged-{sha[:12]}", 1),
    ]))
    assert f"verified=3 tags={expected_tags}" in result.stdout
    assert "pending_tasks=3 generation=7" in result.stdout and "active=1" in result.stdout
    assert [c[3] for c in mutations(calls)] == ["resume"]
    describes = [c for c in calls if c[1:3] == ["tasks", "describe"]]
    assert sorted(c[3] for c in describes) == ["b1", "b2", "f1"]
    verify = [c for c in calls if c[0] == "verify"][0]
    assert verify[verify.index("--expected-queue-state") + 1] == "PAUSED"
    assert verify[verify.index("--task") + 1] == "b1"
    assert verify[verify.index("--worker-url") + 1] == target_for(OTHER_SOURCE)
    assert calls.index(verify) < calls.index(mutations(calls)[0])
    assert [t["id"] for t in final["queues"]["fixlist-scan-stages"]["tasks"]] == ["b1", "f1", "b2"]


@pytest.mark.parametrize("during, message", [
    ("late_task", "task set changed"),
    ("drained_task", "task set changed"),
    (dict(barrier=barrier_state(mode="open")), "barrier is open"),
    (dict(barrier=barrier_state(generation=8)), "generation changed"),
    (dict(barrier=None), "snapshot could not be read"),
])
def test_recover_rereads_tasks_and_barrier_after_the_slow_checks(operator, during, message):
    sha, write_state, run = operator
    valid = stage_task("b1", sha)
    if during == "late_task":
        # An already-admitted producer enqueues an unvalidated task meanwhile.
        during = dict(stage_tasks=[valid, stage_task("late", sha, url="https://evil.example.com/scan-batch")])
    elif during == "drained_task":
        during = dict(stage_tasks=[])
    write_state(stage_tasks=[valid], barrier=dict(ready="false", active=1), during_paused_verify=during)
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode != 0 and message in result.stderr, result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_recover_rereads_barrier_and_inventory_after_verify_before_resume(operator):
    sha, write_state, run = operator
    write_state(stage_tasks=[stage_task("b1", sha)], barrier=dict(ready="false", active=1))
    result, calls, _ = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 0, result.stderr
    verify = next(i for i, c in enumerate(calls) if c[0] == "verify")
    resume = next(i for i, c in enumerate(calls) if c[1:4] == ["tasks", "queues", "resume"])
    assert any(verify < i < resume for i, c in enumerate(calls) if c[0] == "barrier")
    assert any(verify < i < resume for i, c in enumerate(calls) if c[1:3] == ["tasks", "list"])


def test_recover_with_no_pending_tasks_stays_possible_and_says_unverified(operator):
    sha, write_state, run = operator
    # An admitted frontier may be committed before its next task is enqueued.
    write_state(barrier=dict(ready="false", active=1))
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode == 0, result.stderr
    assert "verified=0; no pending tasks, per-task identity unverified" in result.stdout
    assert [c[3] for c in mutations(calls)] == ["resume"]


@pytest.mark.parametrize("bad, message", [
    (dict(url="https://evil.example.com/scan-batch"), "source-tagged revision"),
    (dict(url=target_for("f" * 40) + "/scan-batch"), "no longer an addressable tag"),
    (dict(url=target_for(SOURCE) + "/scan-job"), "pinned worker stage endpoint"),
    (dict(httpMethod="GET"), "POST"),
    (dict(serviceAccountEmail="other@seo-autopilot-501517.iam.gserviceaccount.com"), "OIDC identity"),
    (dict(audience=TARGET), "OIDC audience"),
    (dict(deadline="30s"), "480s"),
])
def test_recover_refuses_any_task_with_a_wrong_delivery_identity(operator, bad, message):
    sha, write_state, run = operator
    url = bad.pop("url", None)
    if url is not None:
        bad["url"] = url.replace(target_for(SOURCE), target_for(sha))
    # Mixed: one valid task does not excuse an invalid one.
    write_state(stage_tasks=[stage_task("good", sha), stage_task("bad", sha, **bad)])
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode != 0 and message in result.stderr, result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


@pytest.mark.parametrize("state", [
    dict(describe_fails=True),
    dict(phantom_listing={"fixlist-scan-stages": ["vanished"]}),
])
def test_recover_refuses_an_unreadable_or_inconsistent_task_inventory(operator, state):
    sha, write_state, run = operator
    write_state(stage_tasks=[stage_task("b1", sha)], **state)
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode != 0
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_recover_refuses_a_possibly_truncated_inventory_and_a_retargeted_tag():
    svc = service()
    revs = revisions()
    task = {"name": "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages/tasks/t",
            **{k: v for k, v in stage_task("t", SOURCE).items() if k != "id"}}
    listing = [{"name": task["name"]}]
    assert guard.check_recoverable_tasks(svc, revs, listing, [task]) == {TAG: 1}
    big = [{"name": task["name"][:-1] + f"t{i}"} for i in range(guard.TASK_LIST_LIMIT)]
    with pytest.raises(guard.GuardError, match="truncated"):
        guard.check_recoverable_tasks(svc, revs, big, [task])
    with pytest.raises(guard.GuardError, match="complete task inventory"):
        guard.check_recoverable_tasks(svc, revs, listing, [])
    # A tag whose revision no longer declares the source the tag names.
    moved = revisions(candidate_env(OTHER_SOURCE))
    with pytest.raises(guard.GuardError, match="not built from the source its tag names"):
        guard.check_recoverable_tasks(svc, moved, listing, [task])
    with pytest.raises(guard.GuardError, match="unexpected service account"):
        wrong = revisions()
        wrong[CANDIDATE] = revision(CANDIDATE, candidate_env(), sa="x@y.iam.gserviceaccount.com")
        guard.check_recoverable_tasks(svc, wrong, listing, [task])


@pytest.mark.parametrize("barrier, message", [
    (dict(mode="open"), "barrier is open"),
    (dict(mode="acceptance_only"), "barrier is acceptance_only"),
    (dict(generation=6), "generation changed"),
    (False, "snapshot could not be read"),
])
def test_recover_refuses_while_new_admissions_are_possible(operator, barrier, message):
    sha, write_state, run = operator
    write_state(stage_tasks=["b1"], barrier=barrier)
    result, calls, final = run("recover", RECOVER.format(sha=sha), BARRIER_EXPECTED_GENERATION="7")
    assert result.returncode != 0 and message in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_status_is_read_only_and_verifies_an_existing_task(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", stage_tasks=["batch-1"])
    result, calls, _ = run("status", STAGED_REVISION=CANDIDATE)
    assert result.returncode == 0, result.stderr
    assert mutations(calls) == []
    verify = [c for c in calls if c[0] == "verify"][0]
    assert verify[verify.index("--task") + 1] == "batch-1"
    assert verify[verify.index("--expected-queue-state") + 1] == "RUNNING"
    assert "STAGED_QUEUE_STATE state=RUNNING tasks=1" in result.stdout


def test_fixed_resources_and_exact_source_are_enforced(operator):
    sha, write_state, run = operator
    write_state()
    result, calls, _ = run("status", STAGED_QUEUE="fixlist-standard150")
    assert result.returncode == 2 and "STAGED_QUEUE must be fixlist-scan-stages" in result.stderr and calls == []
    result, calls, _ = run("status", SOURCE_SHA="0" * 40, GITHUB_SHA="0" * 40)
    assert result.returncode != 0 and calls == []
    result, calls, _ = run("delete")
    assert result.returncode == 2 and "unsupported operation" in result.stderr


def test_shell_verifies_the_same_bucket_activation_requires():
    text = (ROOT / "scripts/operate-staged-queue.sh").read_text()
    assert f'BUCKET="{guard.WORKSPACE_BUCKET}"' in text


def test_script_never_deletes_or_purges():
    text = (ROOT / "scripts/operate-staged-queue.sh").read_text()
    for forbidden in ("queues delete", "queues purge", "tasks delete", "update-traffic", "add-iam-policy-binding",
                      "gcloud secrets", "storage rm", "buckets delete"):
        assert forbidden not in text
