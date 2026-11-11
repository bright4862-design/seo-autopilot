"""Infrastructure contract checks run without credentials or cloud mutations."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prepare = load("prepare_staged_scan_infra")
verify = load("verify_staged_scan_infra")

WORKER = "scan-worker@example-project.iam.gserviceaccount.com"
INVOKER = "scan-invoker@example-project.iam.gserviceaccount.com"
ORIGIN = "https://worker-example.run.app"
ARGS = ["--project", "example-project", "--region", "europe-west1", "--bucket", "example-workspaces",
        "--worker-sa", WORKER, "--invoker-sa", INVOKER, "--worker-url", ORIGIN]


def binding(role, email):
    return {"bindings": [{"role": role, "members": [f"serviceAccount:{email}"]}]}


def bucket():
    return {"iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True},
                                 "publicAccessPrevention": "enforced"}, "lifecycle": prepare.lifecycle()}


def queue():
    return {"name": "projects/example-project/locations/europe-west1/queues/fixlist-scan-stages",
            "state": "RUNNING", "rateLimits": {"maxConcurrentDispatches": 40},
            "retryConfig": {"maxAttempts": 10, "minBackoff": "10s", "maxBackoff": "120s",
                            "maxDoublings": 4, "maxRetryDuration": "1800s"}}


def test_default_preparation_prints_plan_without_running_gcloud(monkeypatch, capsys):
    monkeypatch.setattr(prepare.subprocess, "run", lambda *a, **kw: pytest.fail("dry run invoked gcloud"))
    assert prepare.main(ARGS) == 0
    output = capsys.readouterr().out
    assert "Dry run only" in output
    assert "SCAN_STAGE_TASKS_QUEUE_PATH" in output
    assert "--uniform-bucket-level-access" in output
    assert "--public-access-prevention" in output


def test_grants_are_bucket_queue_and_invoker_scoped():
    commands = prepare.plan(prepare.arguments(ARGS), "/tmp/lifecycle.json")
    grants = [command for command in commands if "add-iam-policy-binding" in command]
    assert [command[1:3] for command in grants] == [["storage", "buckets"], ["tasks", "queues"], ["iam", "service-accounts"]]
    assert all(f"--member=serviceAccount:{WORKER}" in command for command in grants)
    assert "gs://example-workspaces" in grants[0]
    assert "fixlist-scan-stages" in grants[1]
    assert INVOKER in grants[2]
    assert not any("projects" in command[1:3] for command in grants)


def test_tagged_canary_uses_canonical_service_audience():
    target = "https://canary-00104-abc---worker-example.run.app"
    args = prepare.arguments(ARGS[:-1] + [target, "--token-audience", ORIGIN])
    env = prepare.worker_environment(args)
    assert env["SCAN_STAGE_TARGET_URL"] == target
    assert env["SCAN_STAGE_TOKEN_AUDIENCE"] == ORIGIN
    with pytest.raises(SystemExit):
        prepare.arguments(ARGS[:-1] + [target])
    with pytest.raises(SystemExit):
        prepare.arguments(ARGS[:-1] + [target, "--token-audience", "https://other.run.app"])
    task = {"dispatchDeadline": "480s", "httpRequest": {
        "url": target + "/scan-batch", "httpMethod": "POST",
        "oidcToken": {"audience": ORIGIN, "serviceAccountEmail": INVOKER}}}
    verify.validate_task(task, target, INVOKER, ORIGIN)
    task["httpRequest"]["oidcToken"]["audience"] = target
    with pytest.raises(verify.VerificationError, match="audience"):
        verify.validate_task(task, target, INVOKER, ORIGIN)


@pytest.mark.parametrize("url", ["http://worker.run.app", "https://worker.run.app/scan-batch",
                                    "https://user:password@worker.run.app", "https://worker.run.app?x=1"])
def test_worker_target_must_be_a_pinned_https_origin(url):
    with pytest.raises(SystemExit):
        prepare.arguments(ARGS[:-1] + [url])


def test_private_bucket_contract_and_public_principal_rejection():
    policy = binding("roles/storage.objectUser", WORKER)
    verify.validate_bucket(bucket(), policy, WORKER)
    policy["bindings"].append({"role": "roles/storage.objectViewer", "members": ["allUsers"]})
    with pytest.raises(verify.VerificationError, match="public principals"):
        verify.validate_bucket(bucket(), policy, WORKER)


def test_lifecycle_must_delete_all_evidence_not_only_selected_objects():
    value = bucket()
    value["lifecycle"]["rule"][0]["condition"]["matchesPrefix"] = ["only-some/"]
    with pytest.raises(verify.VerificationError, match="unconditional"):
        verify.validate_bucket(value, binding("roles/storage.objectUser", WORKER), WORKER)


def test_queue_retry_contract_and_paused_queue_rejection():
    value = queue()
    verify.validate_queue(value, value["name"], 40)
    value["state"] = "PAUSED"
    with pytest.raises(verify.VerificationError, match="RUNNING"):
        verify.validate_queue(value, value["name"], 40)


def test_queue_retries_outlast_a_450_second_crashed_worker_lease():
    args = prepare.arguments(ARGS)
    command = next(command for command in prepare.plan(args, "/tmp/lifecycle.json")
                   if command[1:4] == ["tasks", "queues", "create"])
    assert "--max-attempts=10" in command
    assert "--max-doublings=4" in command
    assert "--max-retry-duration=1800s" in command
    # Cloud Tasks caps exponential backoff at120s. Even without Retry-After,
    # the eighth delivery remains available after the lease expires at450s.
    scheduled = [0]
    for retry in range(9):
        scheduled.append(scheduled[-1] + min(10 * 2 ** min(retry, 4), 120))
    assert scheduled[7] == 510
    assert any(450 < delivery < 1800 for delivery in scheduled)
    value = queue()
    value["retryConfig"]["maxAttempts"] = 3
    with pytest.raises(verify.VerificationError, match="outlast"):
        verify.validate_queue(value, value["name"], 40)


def test_queue_verifier_pins_retry_window_and_doubling_policy():
    for field, wrong in [("maxDoublings", 0), ("maxRetryDuration", "60s")]:
        value = queue()
        value["retryConfig"][field] = wrong
        with pytest.raises(verify.VerificationError, match="maxDoublings"):
            verify.validate_queue(value, value["name"], 40)


def test_queue_cannot_override_per_task_identity_or_url():
    value = queue()
    value["httpTarget"] = {"uriOverride": {"host": "other.example"}}
    with pytest.raises(verify.VerificationError, match="overrides"):
        verify.validate_queue(value, value["name"], 40)


@pytest.mark.parametrize("field,value", [("url", "https://attacker.example/scan-batch"),
                                        ("httpMethod", "GET")])
def test_task_target_contract_rejects_unreviewed_destinations(field, value):
    task = {"dispatchDeadline": "480s", "httpRequest": {"url": f"{ORIGIN}/scan-batch", "httpMethod": "POST",
            "oidcToken": {"audience": ORIGIN, "serviceAccountEmail": INVOKER}}}
    verify.validate_task(task, ORIGIN, INVOKER)
    task["httpRequest"][field] = value
    with pytest.raises(verify.VerificationError):
        verify.validate_task(task, ORIGIN, INVOKER)


def test_task_requires_oidc_origin_audience_and_existing_deadline():
    task = {"dispatchDeadline": "480s", "httpRequest": {"url": f"{ORIGIN}/scan-finalize", "httpMethod": "POST",
            "oidcToken": {"audience": f"{ORIGIN}/scan-finalize", "serviceAccountEmail": INVOKER}}}
    with pytest.raises(verify.VerificationError, match="audience"):
        verify.validate_task(task, ORIGIN, INVOKER)
    task["httpRequest"]["oidcToken"]["audience"] = ORIGIN
    task["dispatchDeadline"] = "720s"
    with pytest.raises(verify.VerificationError, match="480s"):
        verify.validate_task(task, ORIGIN, INVOKER)


def test_verifier_never_claims_per_task_settings_without_observing_task(monkeypatch, capsys):
    snapshots = [bucket(), binding("roles/storage.objectUser", WORKER), queue(),
                 binding("roles/cloudtasks.enqueuer", WORKER), binding("roles/iam.serviceAccountUser", WORKER)]
    commands = []
    def describe(command):
        commands.append(command)
        return snapshots.pop(0)
    monkeypatch.setattr(verify, "describe", describe)
    assert verify.main(ARGS) == 0
    assert "UNVERIFIED: per-task OIDC" in capsys.readouterr().out
    assert all("create" not in command and "update" not in command for command in commands)
