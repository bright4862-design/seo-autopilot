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

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import staged_queue_guard as guard  # noqa: E402

ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
SOURCE = "4274ac453e93fe2e161e01c88d31823bd5134795"
TAG = f"staged-{SOURCE[:12]}"
TARGET = f"https://{TAG}---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
SERVING = "fixlist-standard150-worker-00097-lvl"
CANDIDATE = "fixlist-standard150-worker-00104-l79"
QUEUE_PATH = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages"


def env_list(values):
    return [{"name": k, "value": v} for k, v in values.items()]


def candidate_env(**overrides):
    values = {
        "FIXLIST_WORKER_SOURCE_SHA": SOURCE,
        "SCAN_WORKSPACE_BUCKET": "fixlist-scan-workspaces-seo-autopilot-501517",
        "SCAN_STAGE_TASKS_QUEUE_PATH": QUEUE_PATH,
        "SCAN_STAGE_TARGET_URL": TARGET,
        "SCAN_STAGE_TOKEN_AUDIENCE": ORIGIN,
        "TASKS_INVOKER_SERVICE_ACCOUNT": guard.INVOKER_SA,
        "SCAN_PIPELINE_MODE": "staged",
        "SCAN_STAGED_OWNER_IDS": "owner_canary_01",
    }
    values.update(overrides)
    return {k: v for k, v in values.items() if v is not None}


def revision(name, env, sa=guard.WORKER_SA):
    return {"metadata": {"name": name},
            "spec": {"serviceAccountName": sa, "containers": [{"env": env_list(env)}]}}


def service(candidate_percent=0, tag=TAG, url=TARGET):
    return {"status": {"url": ORIGIN, "traffic": [
        {"revisionName": SERVING, "percent": 100 - candidate_percent},
        {"revisionName": CANDIDATE, "percent": candidate_percent, "tag": tag, "url": url},
    ]}}


# --- pure guard ---------------------------------------------------------------

def revisions(candidate=None, serving=None):
    return {CANDIDATE: revision(CANDIDATE, candidate or candidate_env()),
            SERVING: revision(SERVING, serving or {"SCAN_PIPELINE_MODE": "monolith"})}


def test_activation_accepts_exact_tagged_zero_traffic_candidate():
    found = guard.check_activation_candidate(service(), revisions(), CANDIDATE)
    assert found["target"] == TARGET and found["audience"] == ORIGIN and found["owner_count"] == "1"


def test_inactive_candidate_with_no_cohort_can_activate():
    env = candidate_env(SCAN_PIPELINE_MODE="monolith", SCAN_STAGED_OWNER_IDS="")
    assert guard.check_activation_candidate(service(), revisions(env), CANDIDATE)["owner_count"] == "0"


@pytest.mark.parametrize("change, message", [
    (dict(SCAN_STAGED_OWNER_IDS="*"), "Wildcard"),
    (dict(SCAN_STAGED_OWNER_IDS="a,b"), "exact owner IDs"),
    (dict(SCAN_STAGED_OWNER_IDS=",".join(f"owner_{i:04d}" for i in range(6))), "exact owner IDs"),
    (dict(SCAN_STAGE_TARGET_URL=ORIGIN), "own source-bound tag"),
    (dict(SCAN_STAGE_TOKEN_AUDIENCE=TARGET), "canonical service origin"),
    (dict(SCAN_STAGE_TASKS_QUEUE_PATH=QUEUE_PATH.replace("fixlist-scan-stages", "other")), "fixed stage queue"),
    (dict(TASKS_INVOKER_SERVICE_ACCOUNT="x@y.iam.gserviceaccount.com"), "invoker"),
    (dict(SCAN_WORKSPACE_BUCKET=None), "workspace bucket"),
    (dict(FIXLIST_WORKER_SOURCE_SHA="abc"), "SOURCE_SHA"),
    (dict(SCAN_PIPELINE_MODE="hybrid"), "monolith or staged"),
])
def test_activation_refuses_misconfigured_candidate(change, message):
    with pytest.raises(guard.GuardError, match=message):
        guard.check_activation_candidate(service(), revisions(candidate_env(**change)), CANDIDATE)


def test_activation_refuses_traffic_wrong_tag_wrong_sa_and_other_admitters():
    with pytest.raises(guard.GuardError, match="production traffic"):
        guard.check_activation_candidate(service(candidate_percent=10), revisions(), CANDIDATE)
    with pytest.raises(guard.GuardError, match="source-bound tag"):
        guard.check_activation_candidate(service(tag="candidate", url=TARGET), revisions(), CANDIDATE)
    bad_sa = revisions()
    bad_sa[CANDIDATE] = revision(CANDIDATE, candidate_env(), sa="other@x.iam.gserviceaccount.com")
    with pytest.raises(guard.GuardError, match="service account"):
        guard.check_activation_candidate(service(), bad_sa, CANDIDATE)
    with pytest.raises(guard.GuardError, match="Other revision"):
        guard.check_activation_candidate(
            service(), revisions(serving={"SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": "owner_canary_01"}),
            CANDIDATE)
    with pytest.raises(guard.GuardError, match="exact worker revision"):
        guard.check_activation_candidate(service(), revisions(), "latest")


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
    out(state["services"][args[3]])
elif args[:3] == ["run", "revisions", "describe"]:
    out(state["revisions"][args[3]])
elif args[:3] == ["tasks", "queues", "describe"]:
    out(state["queues"][args[3]]["state"])
elif args[:3] == ["tasks", "queues", "pause"]:
    state["queues"][args[3]]["state"] = "PAUSED"
    reads = state.get("tasks_after_pause")
    if reads:
        state["queues"][args[3]]["tasks"] = reads
    save()
elif args[:3] == ["tasks", "queues", "resume"]:
    state["queues"][args[3]]["state"] = "RUNNING"; save()
elif args[:2] == ["tasks", "list"]:
    queue = [a.split("=", 1)[1] for a in args if a.startswith("--queue=")][0]
    tasks = state["queues"][queue]["tasks"]
    drained = state.get("drain_after_reads", {}).get(queue)
    if drained is not None:
        state["drain_after_reads"][queue] = drained - 1
        if drained <= 1:
            state["queues"][queue]["tasks"] = []
        save()
    out([{"name": f"projects/seo-autopilot-501517/locations/europe-west1/queues/{queue}/tasks/{t}"} for t in tasks])
else:
    sys.exit(f"unexpected gcloud {args}")
'''


@pytest.fixture
def operator(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts/lib").mkdir(parents=True)
    for name in ("operate-staged-queue.sh", "staged_queue_guard.py", "lib/release-source-guard.sh"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    (repo / "scripts/verify_staged_scan_infra.py").write_text(
        "import json,os,sys\n"
        "with open(os.environ['TEST_CALL_LOG'],'a') as f: f.write(json.dumps(['verify',*sys.argv[1:]])+'\\n')\n"
        "state=json.load(open(os.environ['FAKE_STATE']))\n"
        "want=sys.argv[sys.argv.index('--expected-queue-state')+1]\n"
        "sys.exit(0 if state['queues']['fixlist-scan-stages']['state']==want else 'FAIL: state')\n")
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
                    stage_tasks=(), entry_tasks=(), drain_tasks=(), **extra):
        gateway_env = gateway or {"SCAN_PIPELINE_MODE": "monolith"}
        state = {
            "services": {
                "fixlist-standard150-worker": service(),
                "fixlist-dispatch-gateway": {"status": {"traffic": [{"revisionName": "gw-00009-abc", "percent": 100}]}},
            },
            "revisions": {**revisions(candidate, serving),
                          "gw-00009-abc": revision("gw-00009-abc", gateway_env, sa="gw@x")},
            "queues": {"fixlist-scan-stages": {"state": stage_state, "tasks": list(stage_tasks)},
                       "fixlist-standard150": {"state": "RUNNING", "tasks": list(entry_tasks)},
                       "fixlist-standard150-drain": {"state": "RUNNING", "tasks": list(drain_tasks)}},
            **extra,
        }
        state_path.write_text(json.dumps(state))

    def run(operation, confirm="", **env_overrides):
        log.write_text("")
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GITHUB_ACTIONS": "true",
               "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha, "SOURCE_SHA": sha,
               "TEST_CALL_LOG": str(log), "FAKE_STATE": str(state_path), "OPERATION": operation,
               "CONFIRM": confirm, "STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS": "5",
               "STAGED_QUEUE_DRAIN_POLL_SECONDS": "0", "STAGED_QUEUE_DRAIN_STABLE_READS": "2", **env_overrides}
        result = subprocess.run(["bash", "scripts/operate-staged-queue.sh"], cwd=repo, env=env,
                                text=True, capture_output=True, timeout=30)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        final = json.loads(state_path.read_text())
        return result, calls, final

    return sha, write_state, run


def mutations(calls):
    return [c for c in calls if c[0] == "gcloud" and c[1:3] in (["tasks", "queues"],)
            and c[3] in ("pause", "resume", "delete", "purge", "create", "update")]


def test_activate_requires_exact_confirmation_bound_to_revision(operator):
    sha, write_state, run = operator
    write_state()
    for confirm in ("", f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages",
                    f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{SERVING}"):
        result, calls, final = run("activate", confirm, STAGED_REVISION=CANDIDATE)
        assert result.returncode == 2 and "confirmation required" in result.stderr
        assert calls == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_activate_resumes_only_after_full_readback(operator):
    sha, write_state, run = operator
    write_state()
    result, calls, final = run("activate", f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{CANDIDATE}",
                               STAGED_REVISION=CANDIDATE)
    assert result.returncode == 0, result.stderr
    assert final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"
    verifies = [c for c in calls if c[0] == "verify"]
    assert [v[v.index("--expected-queue-state") + 1] for v in verifies] == ["PAUSED", "RUNNING"]
    assert verifies[0][verifies[0].index("--worker-url") + 1] == TARGET
    assert verifies[0][verifies[0].index("--token-audience") + 1] == ORIGIN
    resume = [i for i, c in enumerate(calls) if c[1:4] == ["tasks", "queues", "resume"]]
    assert len(resume) == 1 and calls.index(verifies[0]) < resume[0] < calls.index(verifies[1])
    assert [c[3] for c in mutations(calls)] == ["resume"]
    assert "STAGED_QUEUE_ACTIVATED" in result.stdout


def test_activate_refuses_misconfigured_candidate_without_mutation(operator):
    sha, write_state, run = operator
    write_state(candidate=candidate_env(SCAN_STAGED_OWNER_IDS="*"))
    result, calls, final = run("activate", f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{CANDIDATE}",
                               STAGED_REVISION=CANDIDATE)
    assert result.returncode != 0 and "Wildcard" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"


def test_activate_refuses_paused_queue_holding_tasks(operator):
    sha, write_state, run = operator
    write_state(stage_tasks=["t1"])
    result, calls, _ = run("activate", f"ACTIVATE-STAGED-QUEUE:{sha}:fixlist-scan-stages:{CANDIDATE}",
                           STAGED_REVISION=CANDIDATE)
    assert result.returncode == 2 and "use recover" in result.stderr and mutations(calls) == []


def test_drain_pause_refuses_while_intake_is_enabled(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING")
    result, calls, final = run("drain-pause", f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF")
    assert result.returncode != 0 and "Staged intake still enabled" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_drain_pause_waits_for_every_feeder_then_pauses(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", candidate=candidate_env(SCAN_PIPELINE_MODE="monolith"),
                stage_tasks=["b1"], drain_tasks=["w1"],
                drain_after_reads={"fixlist-scan-stages": 2, "fixlist-standard150-drain": 3})
    result, calls, final = run("drain-pause", f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF")
    assert result.returncode == 0, result.stderr
    assert final["queues"]["fixlist-scan-stages"]["state"] == "PAUSED"
    reads = [line for line in result.stdout.splitlines() if line.startswith("STAGED_QUEUE_DRAIN_READ")]
    assert reads[-2:] == ["STAGED_QUEUE_DRAIN_READ stage=0 entry=0 drain=0"] * 2
    assert "stage=1" in reads[0]
    assert [c[3] for c in mutations(calls)] == ["pause"]


def test_drain_pause_times_out_and_leaves_queue_running(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", candidate=candidate_env(SCAN_PIPELINE_MODE="monolith"), entry_tasks=["e1"])
    result, calls, final = run("drain-pause", f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF",
                               STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS="0")
    assert result.returncode == 1 and "STAGED_QUEUE_DRAIN_INCOMPLETE" in result.stderr
    assert mutations(calls) == [] and final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_drain_pause_compensates_a_task_that_races_the_pause(operator):
    sha, write_state, run = operator
    write_state(stage_state="RUNNING", candidate=candidate_env(SCAN_PIPELINE_MODE="monolith"),
                tasks_after_pause=["late"])
    result, calls, final = run("drain-pause", f"DRAIN-PAUSE-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF")
    assert result.returncode == 1 and "COMPENSATED" in result.stderr
    assert [c[3] for c in mutations(calls)] == ["pause", "resume"]
    assert final["queues"]["fixlist-scan-stages"]["state"] == "RUNNING"


def test_recover_resumes_stranded_tasks_only_after_intake_is_off(operator):
    sha, write_state, run = operator
    confirm = f"RECOVER-STAGED-QUEUE:{sha}:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF"
    write_state(stage_tasks=["b1", "f1"])
    result, calls, final = run("recover", confirm)
    assert result.returncode != 0 and mutations(calls) == []
    write_state(stage_tasks=["b1", "f1"], candidate=candidate_env(SCAN_STAGED_OWNER_IDS=""))
    result, calls, final = run("recover", confirm)
    assert result.returncode == 0, result.stderr
    assert "pending_tasks=2" in result.stdout
    assert [c[3] for c in mutations(calls)] == ["resume"]
    assert final["queues"]["fixlist-scan-stages"]["tasks"] == ["b1", "f1"]


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


def test_script_never_deletes_or_purges():
    text = (ROOT / "scripts/operate-staged-queue.sh").read_text()
    for forbidden in ("queues delete", "queues purge", "tasks delete", "update-traffic", "add-iam-policy-binding",
                      "gcloud secrets", "storage rm", "buckets delete"):
        assert forbidden not in text
