"""Staged gateway activation must bind the exact routed owner cohort."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
OWNER = "owner_acceptance_01"
OTHER = "owner_acceptance_02"
ORIGIN = "https://canary-00104-l79---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"


def cohort_hash(owners):
    return hashlib.sha256(json.dumps(sorted(owners), separators=(",", ":")).encode()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scanner-api"))
    for key, value in {
        "SCAN_TASKS_QUEUE_PATH": "projects/test/locations/eu/queues/scan",
        "SCAN_DRAIN_QUEUE_PATH": "projects/test/locations/eu/queues/drain",
        "SCAN_WORKER_URL": "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app/scan-job",
        "TASKS_INVOKER_SERVICE_ACCOUNT": "test@example.invalid",
        "SCAN_EVIDENCE_SIGNING_KEY": "fixture-only-key",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS", "SCAN_CANARY_WORKER_ORIGIN", "SCAN_CANARY_OWNER_USER_IDS"):
        monkeypatch.delenv(key, raising=False)
    return load_module("dispatch-gateway/main.py", "staged_gateway_fixture")


def enable(gateway, monkeypatch, owners=OWNER):
    monkeypatch.setattr(gateway, "CANARY_WORKER_ORIGIN", ORIGIN)
    monkeypatch.setattr(gateway, "CANARY_OWNER_USER_IDS", frozenset(owners.split(",")))
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "staged")
    monkeypatch.setenv("SCAN_STAGED_OWNER_IDS", owners)


def test_health_attests_off_configuration_without_exposing_owner_ids(gateway):
    health = gateway.app.test_client().get("/health").get_json()
    assert health["pipeline_mode"] == "monolith"
    assert health["staged_owner_count"] == 0
    assert health["staged_owner_cohort_sha256"] == cohort_hash([])


def test_health_binds_exact_staged_cohort(gateway, monkeypatch):
    enable(gateway, monkeypatch, f"{OTHER},{OWNER}")
    health = gateway.app.test_client().get("/health").get_json()
    assert health["pipeline_mode"] == "staged"
    assert health["staged_owner_count"] == 2
    assert health["staged_owner_cohort_sha256"] == cohort_hash([OWNER, OTHER])
    assert OWNER not in json.dumps(health)


@pytest.mark.parametrize("mode,owners,routed", [
    ("staged", "*", OWNER), ("staged", "", OWNER),
    ("staged", OTHER, OWNER), ("other", OWNER, OWNER),
    ("monolith", OWNER, OWNER), ("staged", OWNER, ""),
])
def test_invalid_or_unrouted_staging_cannot_authorize_500(gateway, monkeypatch, mode, owners, routed):
    monkeypatch.setenv("SCAN_PIPELINE_MODE", mode)
    monkeypatch.setenv("SCAN_STAGED_OWNER_IDS", owners)
    monkeypatch.setattr(gateway, "CANARY_WORKER_ORIGIN", ORIGIN if routed else "")
    monkeypatch.setattr(gateway, "CANARY_OWNER_USER_IDS", frozenset(routed.split(",")) if routed else frozenset())
    job = {"scan_mode": "standard_500", "page_cap": 500, "pipeline_mode": "staged", "owner_user_id": owners}
    assert gateway._valid_scan_mode(job) is False


def test_entitled_500_only_passes_with_matching_owner_route(gateway, monkeypatch):
    enable(gateway, monkeypatch)
    job = {"scan_mode": "standard_500", "page_cap": 500, "pipeline_mode": "staged", "owner_user_id": OWNER}
    assert gateway._valid_scan_mode(job) is True
    assert gateway._valid_scan_mode({**job, "owner_user_id": OTHER}) is False
    assert gateway._valid_scan_mode({**job, "page_cap": True}) is False


def test_verifier_rejects_same_count_different_cohort(gateway, monkeypatch):
    enable(gateway, monkeypatch)
    health = gateway.app.test_client().get("/health").get_json()
    verifier = load_module("scripts/verify_gateway_deployment.py", "staged_gateway_verifier")
    args = (health, gateway.GATEWAY_RUNTIME_REVISION, gateway.GATEWAY_SOURCE_SHA,
            gateway.GATEWAY_CONTRACT_VERSION, gateway.QUEUE_PATH, gateway.DRAIN_QUEUE_PATH, gateway.WORKER_ORIGIN)
    verifier.verify_runtime_health(*args, pipeline_mode="staged", staged_owner_ids=OWNER)
    with pytest.raises(verifier.VerificationError, match="cohort"):
        verifier.verify_runtime_health(*args, pipeline_mode="staged", staged_owner_ids=OTHER)


def test_rollback_requires_previous_staging_configuration(gateway, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    rollback = load_module("scripts/verify_gateway_rollback.py", "staged_gateway_rollback")
    enable(gateway, monkeypatch)
    baseline = gateway.app.test_client().get("/health").get_json()
    revision_name, source = "gateway-fixture", "a" * 40
    baseline.update(revision=revision_name, source_sha=source)
    revision = {"metadata": {"name": revision_name}, "status": {"imageDigest": "img@sha256:" + "a" * 64,
                "conditions": [{"type": "Ready", "status": "True"}]},
                "spec": {"containers": [{"env": [{"name": "FIXLIST_GATEWAY_SOURCE_SHA", "value": source}]}]}}
    service = {"status": {"traffic": [{"revisionName": revision_name, "percent": 100}]}}
    rollback.verify(service, revision, baseline, baseline, revision_name, source)
    wrong = {**baseline, "staged_owner_cohort_sha256": cohort_hash([OTHER])}
    with pytest.raises(rollback.VerificationError, match="cohort"):
        rollback.verify(service, revision, wrong, baseline, revision_name, source)
    wrong = {**baseline, "staged_500_entitled_enabled": True}
    with pytest.raises(rollback.VerificationError, match="500-page launch flag"):
        rollback.verify(service, revision, wrong, baseline, revision_name, source)


@pytest.mark.parametrize("config,owners,canary,ok", [
    ("off", "", "", True), ("owner-canary", OWNER, OWNER, True),
    ("owner-canary", OWNER, OTHER, False), ("owner-canary", "*", "*", False),
    ("owner-canary", "", OWNER, False), ("off", OWNER, OWNER, False),
    ("all", OWNER, OWNER, False), ("owner-canary", f"{OWNER},{OWNER}", OWNER, False),
    ("paid", "", "", True), ("paid-500", "", "", True),
    ("paid", OWNER, "", False), ("paid-500", "", OWNER, False),
])
def test_deploy_config_planner_is_bounded(config, owners, canary, ok):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/gateway_staged_config.py"),
                             "--config", config, "--owners", owners, "--canary-owners", canary],
                            text=True, capture_output=True)
    assert (result.returncode == 0) is ok, result.stderr
    if ok:
        plan = json.loads(result.stdout)
        assert plan["pipeline_mode"] == ("monolith" if config == "off" else "staged")
        assert plan["owner_ids"] == owners
        assert plan["staged_rollout_scope"] == ("paid" if config.startswith("paid") else "off")
        assert plan["staged_500_entitled_enabled"] is (config == "paid-500")


def test_paid_pilot_planner_binds_a_separate_sorted_cohort():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/gateway_staged_config.py"),
                             "--config", "paid-pilot-500", "--pilot-owners", f"{OTHER},{OWNER}"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    planned = json.loads(result.stdout)
    assert planned["pipeline_mode"] == "staged"
    assert planned["staged_rollout_scope"] == "paid"
    assert planned["staged_500_entitled_enabled"] is False
    assert planned["owner_ids"] == ""
    assert planned["pilot_owner_ids"] == f"{OWNER},{OTHER}"
    assert planned["staged_pilot_owner_count"] == 2
    assert planned["staged_pilot_owner_cohort_sha256"] == cohort_hash([OWNER, OTHER])


@pytest.mark.parametrize("config,pilot,owners,canary", [
    ("paid-pilot-500", "", "", ""), ("paid-pilot-500", "*", "", ""),
    ("paid-pilot-500", f"{OWNER},{OWNER}", "", ""),
    ("paid-pilot-500", OWNER, OWNER, ""), ("paid-pilot-500", OWNER, "", OWNER),
    ("off", OWNER, "", ""), ("paid", OWNER, "", ""), ("paid-500", OWNER, "", ""),
    ("owner-canary", OWNER, OWNER, OWNER),
])
def test_paid_pilot_planner_refuses_missing_malformed_or_mixed_cohorts(config, pilot, owners, canary):
    planner = load_module("scripts/gateway_staged_config.py", "gateway_pilot_planner")
    with pytest.raises(ValueError):
        planner.plan(config, owners, canary, pilot)


def paid_baseline(*, pilot="", broad=False):
    return {"source_sha": "a" * 40, "pipeline_mode": "staged", "staged_rollout_scope": "paid",
            "staged_owner_count": 0, "staged_owner_cohort_sha256": cohort_hash([]),
            "canary_owner_count": 0, "canary_worker_origin": None,
            "staged_500_entitled_enabled": broad,
            "staged_pilot_owner_count": 1 if pilot else 0,
            "staged_pilot_owner_cohort_sha256": cohort_hash([pilot] if pilot else [])}


def test_pilot_activation_and_backtrack_bind_the_same_source_paid_baseline():
    planner = load_module("scripts/gateway_staged_config.py", "gateway_pilot_baseline")
    pilot = planner.plan("paid-pilot-500", "", "", OWNER)
    paid = planner.plan("paid", "", "")
    planner.verify_activation_baseline(paid_baseline(), "a" * 40, pilot)
    planner.verify_activation_baseline(paid_baseline(pilot=OWNER), "a" * 40, pilot)
    planner.verify_activation_baseline(paid_baseline(pilot=OWNER), "a" * 40, paid)
    for baseline in (
        {**paid_baseline(), "source_sha": "b" * 40},
        paid_baseline(broad=True), paid_baseline(pilot=OTHER),
        {**paid_baseline(), "canary_worker_origin": ORIGIN},
        {**paid_baseline(), "staged_pilot_owner_count": True},
    ):
        with pytest.raises(ValueError):
            planner.verify_activation_baseline(baseline, "a" * 40, pilot)
    broad = planner.plan("paid-500", "", "")
    with pytest.raises(ValueError):
        planner.verify_activation_baseline(paid_baseline(pilot=OWNER), "a" * 40, broad)


def test_pilot_health_verifier_binds_count_and_cohort_and_requires_empty_when_disabled(gateway, monkeypatch):
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "staged")
    monkeypatch.setenv("SCAN_STAGED_ROLLOUT_SCOPE", "paid")
    monkeypatch.setenv("SCAN_STAGED_PILOT_OWNER_IDS", OWNER)
    health = gateway.app.test_client().get("/health").get_json()
    verifier = load_module("scripts/verify_gateway_deployment.py", "paid_pilot_verifier")
    args = (health, gateway.GATEWAY_RUNTIME_REVISION, gateway.GATEWAY_SOURCE_SHA,
            gateway.GATEWAY_CONTRACT_VERSION, gateway.QUEUE_PATH, gateway.DRAIN_QUEUE_PATH, gateway.WORKER_ORIGIN)
    verifier.verify_runtime_health(*args, staged_pilot_owner_ids=OWNER)
    for expected in (OTHER, ""):
        with pytest.raises(verifier.VerificationError, match="pilot"):
            verifier.verify_runtime_health(*args, staged_pilot_owner_ids=expected)
    for change in ({"staged_pilot_owner_count": True}, {"staged_pilot_owner_cohort_sha256": cohort_hash([OTHER])}):
        with pytest.raises(verifier.VerificationError, match="pilot"):
            verifier.verify_runtime_health({**health, **change}, *args[1:], staged_pilot_owner_ids=OWNER)


def test_rollback_requires_the_original_paid_pilot_cohort(gateway, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    rollback = load_module("scripts/verify_gateway_rollback.py", "paid_pilot_rollback")
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "staged")
    monkeypatch.setenv("SCAN_STAGED_ROLLOUT_SCOPE", "paid")
    monkeypatch.setenv("SCAN_STAGED_PILOT_OWNER_IDS", OWNER)
    baseline = gateway.app.test_client().get("/health").get_json()
    revision_name, source = "gateway-fixture", "a" * 40
    baseline.update(revision=revision_name, source_sha=source)
    revision = {"metadata": {"name": revision_name}, "status": {"imageDigest": "img@sha256:" + "a" * 64,
                "conditions": [{"type": "Ready", "status": "True"}]},
                "spec": {"containers": [{"env": [{"name": "FIXLIST_GATEWAY_SOURCE_SHA", "value": source}]}]}}
    service = {"status": {"traffic": [{"revisionName": revision_name, "percent": 100}]}}
    rollback.verify(service, revision, baseline, baseline, revision_name, source)
    for change in ({"staged_pilot_owner_count": 0}, {"staged_pilot_owner_cohort_sha256": cohort_hash([OTHER])}):
        with pytest.raises(rollback.VerificationError, match="pilot"):
            rollback.verify(service, revision, {**baseline, **change}, baseline, revision_name, source)


def test_pilot_environment_verification_refuses_missing_extra_or_ambiguous_settings():
    verifier = load_module("scripts/verify_gateway_deployment.py", "pilot_environment_verifier")
    def revision(entries):
        return {"spec": {"containers": [{"env": entries}]}}
    entry = {"name": "SCAN_STAGED_PILOT_OWNER_IDS", "value": OWNER}
    verifier.verify_pilot_environment(revision([entry]), OWNER)
    verifier.verify_pilot_environment(revision([]), "")
    for entries, expected in (([], OWNER), ([entry], OTHER), ([entry], ""), ([entry, entry], OWNER),
                              ([{**entry, "valueFrom": {"secretKeyRef": {"name": "unexpected"}}}], OWNER)):
        with pytest.raises(verifier.VerificationError, match="pilot"):
            verifier.verify_pilot_environment(revision(entries), expected)


@pytest.mark.parametrize("valid_confirmation", [True, False])
def test_pilot_deploy_binds_confirmation_to_source_worker_and_sorted_cohort(tmp_path, valid_confirmation):
    text = (ROOT / "scripts/deploy_dispatch_gateway.sh").read_text()
    setup = text[text.index('STAGED_PLAN='):text.index('\n# The gateway uses')]
    source = "a" * 40
    worker = "fixlist-standard150-worker-00123-abc"
    confirm = f"ENABLE-PAID-PILOT-STAGED-GATEWAY:{source}:{worker}:{cohort_hash([OWNER])}"
    credential = tmp_path / "fixture-credential"
    credential.write_text("fixture")
    env = {**os.environ, "REPO_ROOT": str(ROOT), "SOURCE_SHA": source,
           "GATEWAY_STAGED_CONFIG": "paid-pilot-500", "GATEWAY_STAGED_PILOT_OWNER_IDS": OWNER,
           "GATEWAY_STAGED_SERVING_REVISION": worker, "WORKER": "fixlist-standard150-worker",
           "GATEWAY_STAGED_CONFIRM": confirm if valid_confirmation else confirm[:-1] + "0",
           "GATEWAY_ADMISSION_ACCESS_TOKEN_FILE": str(credential), "GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT": "fixture"}
    command = setup + '\nprintf "%s\\n" "$STAGED_500_ENABLED" "$STAGED_PILOT_OWNER_IDS"\n'
    result = subprocess.run(["bash", "-euo", "pipefail", "-c", command], env=env, text=True, capture_output=True)
    assert (result.returncode == 0) is valid_confirmation, result.stderr
    if valid_confirmation:
        assert result.stdout.splitlines() == ["false", OWNER]


@pytest.mark.parametrize("queue_target", ["null", '{"uriOverride":{"host":"other.example"}}'])
def test_paid_cutover_checks_barrier_queue_targets_and_worker_runtime(tmp_path, queue_target):
    (tmp_path / "scripts").mkdir()
    helpers = tmp_path / "scripts"
    (helpers / "staged_candidate_cloudbuild.py").write_text(
        (ROOT / "scripts/staged_candidate_cloudbuild.py").read_text()
    )
    (helpers / "fixlist-cloud-operator.sh").write_text("""set -eu
case "$OPERATION" in
  verify-zero-admission-obligations)
    test "$CLOUDSDK_AUTH_ACCESS_TOKEN_FILE" = "$GATEWAY_ADMISSION_ACCESS_TOKEN_FILE"
    test "$CONFIRM" = "VERIFY-ZERO-ADMISSION:$SOURCE_SHA:19"
    echo barrier ;;
  verify-worker-runtime-revision)
    test -z "${CLOUDSDK_AUTH_ACCESS_TOKEN_FILE:-}"
    test "$TARGET_REVISION" = "$GATEWAY_STAGED_SERVING_REVISION"
    test "$FIXLIST_WORKER_PROBE_URL" = "$WORKER_ORIGIN"
    test "$FIXLIST_VERIFY_STAGED_BASE44_RUNTIME" = 1
    echo worker ;;
  *) exit 70 ;;
esac
""")
    (helpers / "verify-standard150-reconciler.sh").write_text("""set -eu
test "$CLOUDSDK_AUTH_ACCESS_TOKEN_FILE" = "$GATEWAY_ADMISSION_ACCESS_TOKEN_FILE"
test "$RECONCILER_EXPECTED_REVISION" = "$GATEWAY_STAGED_SERVING_REVISION"
echo scheduler
""")
    text = (ROOT / "scripts/deploy_dispatch_gateway.sh").read_text()
    cutover = text[text.index("verify_paid_cutover()"):text.index("\nverify_paid_cutover\n")]
    command = """
gcloud() {
  test -z "${CLOUDSDK_AUTH_ACCESS_TOKEN_FILE:-}"
  case "$*" in
    'tasks queues describe '*) printf '{"state":"RUNNING","httpTarget":%s}\n' "$QUEUE_TARGET" ;;
    'tasks list '*) printf '[]\n' ;;
    *) return 70 ;;
  esac
}
""" + cutover + "\nverify_paid_cutover\n"
    env = {
        **os.environ,
        "REPO_ROOT": str(tmp_path), "STAGED_ROLLOUT_SCOPE": "paid", "QUEUE_TARGET": queue_target,
        "SOURCE_SHA": "a" * 40, "BARRIER_EXPECTED_GENERATION": "19", "PROJECT": "seo-autopilot-501517",
        "REGION": "europe-west1", "WORKER": "fixlist-standard150-worker", "INVOKER_SA": "fixture",
        "WORKER_ORIGIN": "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app",
        "QUEUE": "fixlist-standard150", "DRAIN_QUEUE": "fixlist-standard150-drain",
        "GATEWAY_STAGED_SERVING_REVISION": "fixlist-standard150-worker-00123-test",
        "GATEWAY_ADMISSION_ACCESS_TOKEN_FILE": str(tmp_path / "fixture-token"),
        "GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT": "fixture",
    }
    env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN_FILE", None)
    result = subprocess.run(["/bin/bash", "-euo", "pipefail", "-c", command],
                            env=env, capture_output=True, text=True)
    if queue_target == "null":
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ["barrier", "scheduler", "worker"]
    else:
        assert result.returncode != 0
        assert result.stdout.splitlines() == ["barrier"]
        assert "without HTTP overrides" in result.stderr
