"""Connect the named paid 500 contract to the real staged evidence writer."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import pytest

from app import staged_telemetry
from scripts import collect_published_paid_500 as paid
from tests.test_collect_staged_scan_receipts import Reader
from tests.test_staged_workspace import Harness, State


EXPECTED = {
    "owner_user_id": "owner_test", "source_sha": "a" * 40, "fingerprint": "a" * 16,
    "grant_id": "approved_grant", "cohort_id": "cohort_test", "release_id": "release_test",
    "operator_id": "operator_test", "public_150": None, "worker_config_sha256": "b" * 64,
}
OPERATOR_KEY = b"offline-operator-key"
CLAIM_KEY = b"offline-claim-key"
ROUTES = json.loads((paid.SCANNER_ROOT.parent / "data/generated-staged-v9-routes.json").read_text())["functions"]


def sign(value, root, label):
    return hmac.new(hmac.new(root, label, hashlib.sha256).digest(), paid.stable_json(value), hashlib.sha256).hexdigest()


@pytest.fixture
def observations():
    now = datetime.now(timezone.utc)
    time_at = lambda seconds: (now + timedelta(seconds=seconds)).isoformat()
    source, owner, fingerprint = (EXPECTED[key] for key in ("source_sha", "owner_user_id", "fingerprint"))
    worker = paid.receipt.WORKER_SERVICE + "-a1b2c3.europe-west1.run.app"
    worker_revision = paid.receipt.WORKER_SERVICE + "-00100-abc"
    gateway = "https://fixlist-dispatch-gateway-a1b2c3.europe-west1.run.app"
    launcher = ROUTES["startStandardScanJobV9"]
    expiry = int(now.timestamp()) + 1000
    pilot_fields = {"staged_rollout_scope": "paid", "staged_500_entitled_enabled": False,
                    "staged_pilot_owner_count": 1, "staged_pilot_owner_cohort_sha256": paid.digest([owner]),
                    "staged_owner_count": 0, "staged_owner_cohort_sha256": paid.EMPTY_COHORT}
    snapshot = {
        "snapshot_id": "snapshot_test", "version": paid.ACTIVATION_VERSION, "created_at": int(now.timestamp()) - 35,
        "operator_id": "operator_test", "drain_ready": False,
        "barrier": {"generation": 6, "mode": "open", "current_snapshot_id": "snapshot_test", "claim_sequence": 51},
        "boundary": {"published_500_pilot": {
            "state": "configured", "page_cap": 500, "cohort_id": "cohort_test", "release_id": "release_test",
            "source_sha": source, "expires_at": expiry, "owner_count": 1, "owner_cohort_sha256": paid.digest([owner]),
            "required_launcher_build_id": launcher["build_id"],
        }},
    }
    snapshot["proof"] = sign(snapshot, OPERATOR_KEY, b"fixlist-admission-drain-snapshot-v1")
    packet = {
        "schema_version": paid.PREREQUISITE_VERSION, "base44_app_id": paid.APP_ID, "source_sha": source,
        "release_fingerprint": fingerprint, "observed_at": time_at(-20),
        "worker": {
            "origin": "https://" + worker, "service": paid.receipt.WORKER_SERVICE, "source_sha": source,
            "release_fingerprint": fingerprint, "staged_config_sha256": EXPECTED["worker_config_sha256"], "ready": True,
            "pipeline_mode": "monolith", "revision": worker_revision, "stage_tag_revision": worker_revision,
            "stage_target": f"https://staged-{source[:12]}---{worker}", "stage_token_audience": "https://" + worker,
            "stage_queue": paid.STAGE_QUEUE, "workspace_bucket": paid.receipt.BUCKET,
            "traffic": [{"revision": worker_revision, "percent": 100}], "staged_owner_ids": "", "legacy_owner_ids": "",
        },
        "gateway": {
            **pilot_fields, "origin": gateway, "ok": True, "service": "fixlist-dispatch-gateway",
            "revision": "fixlist-dispatch-gateway-00100-abc", "source_sha": source, "worker_origin": "https://" + worker,
            "pipeline_mode": "staged", "canary_owner_count": 0, "canary_worker_origin": None,
            "staged_pilot_configuration_valid": True, "queue": paid.QUEUE_PREFIX + "fixlist-standard150",
            "drain_queue": paid.QUEUE_PREFIX + "fixlist-standard150-drain",
        },
        "intake": {
            **pilot_fields, **launcher, "success": True, "schema_version": "fixlist_staged_v9_intake_readback_v1",
            "release_fingerprint": fingerprint, "configured_pipeline_mode": "staged", "paid_dispatch_gateway_origin": gateway,
            "intake_gate": "enabled", "admission_gate": "enabled", "public_pilot_expires_at": expiry,
            "observed_at": time_at(-21),
        },
        "pilot_snapshot": snapshot,
        "coordinator": {
            "ok": True, "service": "fixlist-admission-coordinator", "source_sha": source,
            "claim_evidence_version": paid.CLAIM_VERSION, "published_500_pilot_admission": True,
            "published_pilot_launcher_binding": True,
        },
        "account": {"id": owner, "role": "user", "email": "pilot@example.com"},
        "matching_grants": [{
            "id": EXPECTED["grant_id"], "owner_user_id": owner, "user_email": "pilot@example.com", "page_cap": 500,
            "has_full_access": True, "access_status": "active", "app_id": paid.APP_ID, "plan_id": "standard150_lifetime",
            "grant_source": "manual_grant", "granted_at": time_at(-100),
        }],
    }
    terminal = {
        "id": "scan_test", "project_id": "project_test", "website_url": paid.FIXTURE, "scan_mode": "standard_500",
        "page_cap": 500, "pipeline_mode": "staged", "status": "complete", "pages_crawled": 500, "pages_planned": 500,
        "started_at": time_at(-10), "completed_at": time_at(1), "beta_revision_fingerprint": fingerprint,
    }
    projection = {
        "success": True, "access": "full", "authority_verified": True, "release_contract_current": True,
        "scan_id": "scan_test", "fix_list_id": "list_test", "run": terminal.copy(),
    }
    claim = {
        "version": paid.CLAIM_VERSION, "owner_user_id": owner, "request_id": "request_test",
        "barrier_generation": 6, "claim_sequence": 52, "admission_mode": "acceptance_only",
        "acceptance_cohort_id": "cohort_test", "acceptance_release_id": "release_test",
        "acceptance_source_sha": source, "acceptance_expires_at": expiry,
    }
    run = {
        **terminal, "request_id": "request_test", "idempotency_key": "request_test", "fix_list_id": "list_test",
        "owner_user_id": owner, "attempt_count": 1, "last_committed_batch": 9, "admission_release_state": "released",
        "admission_release_outcome": "released", "admission_release_reconciled_at": time_at(2),
        "admission_release_coordinator_request_id": "request_test",
        "release_gate_eligible": True, "authority_proof": "c" * 64, "admission_mode": "acceptance_only",
        "admission_cohort_evidence_version": paid.CLAIM_VERSION,
        "admission_cohort_evidence_proof": sign(claim, CLAIM_KEY, b"fixlist-admission-claim-evidence-v1"),
        **{f"admission_{key}": value for key, value in claim.items()
           if key.startswith("acceptance_") or key in ("barrier_generation", "claim_sequence")},
    }
    browser = {
        "schema_version": paid.BROWSER_VERSION, "source_sha": source, "owner_user_id": owner, "role": "user",
        "launch_url": paid.PUBLIC_ORIGIN + "/onboarding", "launched_by_form": True, "displayed_page_cap": 500,
        "launch_route": launcher["route_name"], "refreshed_during_progress": True,
        "history_url": paid.PUBLIC_ORIGIN + "/dashboard?scan_id=scan_test", "reopened_from_history": True,
        "reopened_after_sign_in": True, "result_route": ROUTES["getCustomerScanResultV9"]["route_name"],
        "observed_at": time_at(3), "history_reopened_at": time_at(2),
        "options": {"success": True, "version": "published_scan_options_v1", "launch": "pilot",
                    "page_cap": 500, "release_fingerprint": fingerprint},
        "launch": {"success": True, "accepted": True, "status": "queued", "scan_id": "scan_test", "request_id": "request_test", "page_cap": 500,
                   "scan_mode": "standard_500", "pipeline_mode": "staged"},
        "saved_projection": projection, "history_projection": {**projection, "run": terminal.copy()},
    }
    return packet, run, browser, int((now + timedelta(seconds=5)).timestamp() * 1000)


def check(observations, expected=EXPECTED):
    packet, run, browser, now = observations
    context = paid.validate_prerequisites(packet, expected, ROUTES, OPERATOR_KEY, now)
    return paid.validate_browser(browser, run, context, expected, ROUTES, CLAIM_KEY, now)


def test_paid_readback_keeps_worker_environment_distinct_from_the_frozen_500_run(observations):
    canary = check(observations)
    assert canary.scan_id == "scan_test"
    assert canary.runtime["staged_owner_cohort_sha256"] == paid.EMPTY_COHORT
    assert canary.runtime["pipeline_mode"] == "monolith"


@pytest.mark.parametrize(("part", "update", "error"), [
    ("worker", {"traffic": [{"revision": "different", "percent": 100}]}, "canonical_worker"),
    ("gateway", {"staged_500_entitled_enabled": True}, "gateway_mismatch"),
    ("intake", {"staged_rollout_scope": "off"}, "intake_mismatch"),
    ("coordinator", {"published_pilot_launcher_binding": False}, "coordinator_mismatch"),
    ("account", {"role": "admin"}, "account_mismatch"),
    ("pilot_snapshot", {"created_at": 12345}, "snapshot_signature"),
])
def test_requires_exact_configuration(observations, part, update, error):
    observations[0][part].update(update)
    with pytest.raises(paid.receipt.EvidenceError, match=error):
        check(observations)


def test_rejects_duplicate_grants_and_cross_bound_reports(observations):
    packet, _, browser, _ = observations
    packet["matching_grants"] *= 2
    with pytest.raises(paid.receipt.EvidenceError, match="grant_ambiguous"):
        check(observations)
    packet["matching_grants"].pop()
    browser["history_projection"]["scan_id"] = "another_scan"
    with pytest.raises(paid.receipt.EvidenceError, match="report_mismatch"):
        check(observations)


def test_rejects_unreleased_slots_or_forged_claims(observations):
    run = observations[1]
    run["admission_release_state"] = "pending"
    with pytest.raises(paid.receipt.EvidenceError, match="saved_run_mismatch"):
        check(observations)
    run["admission_release_state"] = "released"
    run["admission_claim_sequence"] += 1
    with pytest.raises(paid.receipt.EvidenceError, match="claim_signature"):
        check(observations)


def resign_snapshot(snapshot):
    unsigned = {key: value for key, value in snapshot.items() if key != "proof"}
    snapshot["proof"] = sign(unsigned, OPERATOR_KEY, b"fixlist-admission-drain-snapshot-v1")


def bounded_public_150(observations, *, state="configured"):
    packet, _, _, now = observations
    owners = ["second_customer", "first_customer"]
    approved = {
        "state": state, "cohort_id": "public_150_wave", "release_id": "standard150_release",
        "owner_user_ids": owners, "expires_at": now // 1000 + 500,
        "total_claim_budget": 3, "per_owner_claim_budget": 2,
    }
    expected = {**EXPECTED, "public_150": approved}
    snapshot = packet["pilot_snapshot"]
    snapshot["boundary"]["public_150"] = {
        **{key: value for key, value in approved.items() if key != "owner_user_ids"},
        "page_cap": 150, "source_sha": EXPECTED["source_sha"], "owner_count": 2,
        "owner_cohort_sha256": paid.digest(sorted(owners)),
        "required_launcher_build_id": ROUTES["startStandardScanJobV9"]["build_id"],
        "total_claims_used": 1,
    }
    resign_snapshot(snapshot)
    return expected, snapshot


@pytest.mark.parametrize("state", ["configured", "held"])
def test_accepts_independently_approved_signed_bounded_150_lane(observations, state):
    expected, snapshot = bounded_public_150(observations, state=state)
    assert check(observations, expected).pages == 500
    packet, _, _, now = observations
    context = paid.validate_prerequisites(packet, expected, ROUTES, OPERATOR_KEY, now)
    assert context["public_150_boundary"] == snapshot["boundary"]["public_150"]


def test_requires_explicit_choice_and_rejects_unbounded_signature_for_a_bounded_rollout(observations):
    unspecified = {name: value for name, value in EXPECTED.items() if name != "public_150"}
    with pytest.raises(paid.receipt.EvidenceError, match="public_150_expectation_required"):
        check(observations, unspecified)
    expected, snapshot = bounded_public_150(observations)
    with pytest.raises(paid.receipt.EvidenceError, match="unexpected_public_150_boundary"):
        check(observations)
    del snapshot["boundary"]["public_150"]
    resign_snapshot(snapshot)
    with pytest.raises(paid.receipt.EvidenceError, match="public_150_boundary_mismatch"):
        check(observations, expected)


@pytest.mark.parametrize(("field", "value", "error"), [
    ("source_sha", "d" * 40, "public_150_boundary_mismatch"),
    ("required_launcher_build_id", "d" * 64, "public_150_boundary_mismatch"),
    ("owner_cohort_sha256", "d" * 64, "public_150_boundary_mismatch"),
    ("state", "held", "public_150_boundary_mismatch"),
    ("total_claims_used", 4, "public_150_budget_invalid"),
])
def test_rejects_signed_150_boundary_with_wrong_release_policy(observations, field, value, error):
    expected, snapshot = bounded_public_150(observations)
    snapshot["boundary"]["public_150"][field] = value
    resign_snapshot(snapshot)
    with pytest.raises(paid.receipt.EvidenceError, match=error):
        check(observations, expected)


def test_requires_claim_generation_to_match_the_signed_two_lane_boundary(observations):
    expected, snapshot = bounded_public_150(observations)
    snapshot["barrier"]["generation"] += 1
    resign_snapshot(snapshot)
    with pytest.raises(paid.receipt.EvidenceError, match="paid_500_claim_mismatch"):
        check(observations, expected)


class PinnedReader(Reader):
    async def read_pinned(self, key, generation):
        body = await self.workspace.read(key)
        assert str(body.generation) == generation
        return body.value


@pytest.mark.asyncio
async def test_real_stage_writer_rechecks_ten_pinned_batches_and_full_result(monkeypatch, observations):
    _, run, _, _ = observations
    canary = check(observations)
    harness = Harness(monkeypatch)
    harness.scan.update(scan_mode="standard_500", page_cap=500, website_url=paid.FIXTURE)
    harness.job.update(scan_mode="standard_500", page_cap=500, website_url=paid.FIXTURE)
    for key, value in {
        "FIXLIST_WORKER_SOURCE_SHA": canary.runtime["source_sha"],
        "FIXLIST_STAGED_CONFIG_SHA256": canary.runtime["staged_config_sha256"],
        "K_SERVICE": canary.runtime["service"], "K_REVISION": canary.runtime["revision"],
        "SCAN_PIPELINE_MODE": "monolith", "SCAN_STAGED_OWNER_IDS": "", "SCAN_PIPELINE_OWNER_IDS": "",
    }.items():
        monkeypatch.setenv(key, value)
    fingerprint = canary.runtime["release_fingerprint"]
    monkeypatch.setattr(staged_telemetry, "live_revision", lambda: {"fingerprint": fingerprint})
    monkeypatch.setattr("app.beta_revision.live_revision", lambda: {"fingerprint": fingerprint})
    monkeypatch.setattr(staged_telemetry, "measure_worker_peak_memory_bytes", lambda: 140_000_000)
    monkeypatch.setattr(staged_telemetry, "_kernel_memory_bound", lambda: {
        "scope": "cgroup_lifetime", "peak_bytes": 480_000_000, "limit_bytes": 1_073_741_824,
    })

    async def plan(**kwargs):
        return State(queue=sorted(paid.FIXTURE_URLS)[:500])

    async def crawl(state, *, max_pages):
        for _ in range(min(len(state.queue), max_pages)):
            url = state.queue.pop(0)
            state.pages.append({"url": url, "canonical": url, "status_code": 200})

    async def review(result):
        staged_telemetry.active_delivery.get().observe_review_memory(350_000_000)
        return {"evidence": "fixture"}

    async def complete(client, scan, result, key, *, review):
        active = staged_telemetry.active_delivery.get()
        active.observe_completion_request("persistDurableScanAuthorityV9", b'{"test":"fixture"}')
        active.observe_completion_response(200)
        return await harness.complete(client, scan, result, key)

    harness.deps.plan, harness.deps.crawl = plan, crawl
    harness.deps.review, harness.deps.complete = review, complete
    await harness.run("plan")
    for batch in range(10):
        await harness.run("batch", batch=batch)
    await harness.run("finalize", batch=10)
    reader = PinnedReader(harness.store)
    evidence = await paid.collect_published_receipts(canary, run, reader)
    assert evidence["committed_delivery_count"] == 12
    assert evidence["verified_committed_batch_sizes"] == [50] * 10
    assert evidence["checked_distinct_page_count"] == 500

    original = reader.read_pinned

    async def duplicate(key, generation):
        value = await original(key, generation)
        if key.endswith(".pages.json.gz") and len(value["pages"]) == 500:
            return {"pages": value["pages"][:-1] + value["pages"][:1]}
        return value

    reader.read_pinned = duplicate
    with pytest.raises(paid.receipt.EvidenceError, match="duplicate_page"):
        await paid.collect_published_receipts(canary, run, reader)
