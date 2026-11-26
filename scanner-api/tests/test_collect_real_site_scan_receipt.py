"""Exercise real-site checks without contacting any scanned or cloud host."""

import hashlib
import hmac
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from scripts import collect_real_site_scan_receipt as real
from scripts import collect_staged_scan_receipts as receipt
from scripts.collect_published_paid_500 import stable_json
from tests.test_collect_staged_scan_receipts import Reader, simulated_canary


CLAIM_KEY = b"claim-signing-fixture"
ROUTE = "getCustomerScanResultV9Bexample"


@pytest.mark.asyncio
@pytest.mark.parametrize(("cap", "count", "outcome"), [
    (150, 150, "complete_at_cap"),
    (500, 120, "complete_queue_exhausted"),
    (500, 120, "limited"),
])
async def test_joins_the_real_worker_chain_and_reports_actual_usable_html(monkeypatch, cap, count, outcome):
    limited = outcome == "limited"
    harness, prior, _, _ = await simulated_canary(monkeypatch, page_cap=cap, limited=limited)
    canary = replace(receipt.canary_identity(prior), project_id=harness.job["project_id"], target_url=harness.job["website_url"])
    storage = Reader(harness.store)
    original = storage.read_evidence
    # Adapt the fixture's page payloads and scanner diagnostics while retaining
    # the exact producer generations and all actual staged writer receipts.
    async def read_evidence(key):
        observed = await original(key)
        value = observed.value
        for page_index, page in enumerate(value.get("pages", [])):
            page.update(status_code=404 if page_index == 0 else 200,
                        content_type="application/pdf" if page_index == 1 else "text/html")
            page["canonical"] = "https://example.com/other"
        if key.endswith("result.json.gz"):
            value.update(pages_found=count, inventory_capped=False, crawl_timing={"queue_exhausted": count < cap})
            if limited:
                value["pipeline_limit_reason"] = "rate_limit"
        return observed

    monkeypatch.setattr(storage, "read_evidence", read_evidence)
    scope = real.ReviewedScope("S01-" + str(cap), outcome, "/", ("https://example.com/",), "d" * 64,
                               "rate_limit" if limited else "")
    verified = await real.collect_reviewed_site(canary, scope, storage)
    assert verified["receipt_evidence_verified"] is True
    assert verified["terminal_outcome"] == outcome
    assert verified["checked_distinct_url_count"] == count
    assert verified["usable_html_count"] == count - 2
    assert verified["rate_limit_observed"] is limited


def captured_packet():
    now = datetime.now(timezone.utc)
    started, completed = now - timedelta(minutes=2), now - timedelta(minutes=1)
    owner, project, scan, request, fix_list = "owner_test", "project_test", "scan_test", "request_test", "fix_list_test"
    source, fingerprint = "a" * 40, "b" * 16
    scope = {
        "row_id": "S01-150", "page_cap": 150, "target_url": "https://example.com/guide",
        "path_prefix": "/guide", "allowed_url_prefixes": ["https://example.com/guide"],
        "authorization_reference_sha256": "c" * 64, "owner_user_id": owner, "project_id": project,
        "authorized_from": (now - timedelta(minutes=3)).isoformat(),
        "authorized_until": (now + timedelta(minutes=1)).isoformat(), "expected_outcome": "complete_queue_exhausted",
    }
    claim = {
        "version": "admission_claim_evidence_v1", "owner_user_id": owner, "request_id": request,
        "barrier_generation": 40, "claim_sequence": 42, "admission_mode": "acceptance_only",
        "acceptance_cohort_id": "cohort_test", "acceptance_release_id": "release_test",
        "acceptance_source_sha": source, "acceptance_expires_at": int(now.timestamp()) + 60,
    }
    key = hmac.new(CLAIM_KEY, b"fixlist-admission-claim-evidence-v1", hashlib.sha256).digest()
    run = {
        "id": scan, "owner_user_id": owner, "project_id": project, "request_id": request,
        "idempotency_key": request, "fix_list_id": fix_list, "attempt_count": 1, "last_committed_batch": 2,
        "website_url": scope["target_url"], "page_cap": 150, "scan_mode": "standard_150", "pipeline_mode": "staged",
        "status": "complete", "pages_crawled": 120, "pages_planned": 130,
        "release_gate_eligible": True, "authority_proof": "a" * 64,
        "beta_revision_fingerprint": fingerprint, "started_at": started.isoformat(), "completed_at": completed.isoformat(),
        "admission_release_state": "released", "admission_release_outcome": "released",
        "admission_release_coordinator_request_id": request, "admission_release_reconciled_at": completed.isoformat(),
        "admission_cohort_evidence_version": claim["version"],
        "admission_cohort_evidence_proof": hmac.new(key, stable_json(claim), hashlib.sha256).hexdigest(),
        **{f"admission_{k}": v for k, v in claim.items() if k.startswith("acceptance_") or
           k in {"barrier_generation", "claim_sequence"}},
        "admission_mode": claim["admission_mode"],
    }
    projection = {
        "success": True, "access": "full", "authority_verified": True, "result_integrity_verified": False,
        "release_contract_current": True, "scan_id": scan, "fix_list_id": fix_list,
        "run": {k: run[k] for k in ("id", "project_id", "website_url", "page_cap", "scan_mode", "pipeline_mode",
                                    "status", "pages_crawled", "pages_planned", "beta_revision_fingerprint",
                                    "started_at", "completed_at")},
    }
    return {
        "schema_version": "real_site_qa_receipt_input_v1", "approved_scope": scope,
        "worker_runtime": {
            "source_sha": source, "release_fingerprint": fingerprint, "service": receipt.WORKER_SERVICE,
            "revision": receipt.WORKER_SERVICE + "-00011-abc", "pipeline_mode": "staged",
            "staged_config_sha256": "d" * 64, "staged_owner_cohort_sha256": "e" * 64,
        },
        "saved_run": run,
        "browser": {
            "owner_user_id": owner, "role": "user", "result_route": ROUTE,
            "history_url": f"https://getfixlist.com/dashboard?scan_id={scan}",
            "history_reopened_at": now.isoformat(), "projection": projection,
        },
    }


def test_binds_the_exact_signed_attempt_to_reopened_published_projection():
    packet = captured_packet()
    canary, scope = real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)
    assert (canary.scan_id, canary.pages, canary.planned, scope.row_id) == ("scan_test", 120, 130, "S01-150")
    packet["saved_run"]["admission_claim_sequence"] += 1
    with pytest.raises(receipt.EvidenceError, match="qa_admission_claim_signature_invalid"):
        real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)


def test_rejects_a_readback_outside_reviewed_path():
    packet = captured_packet()
    packet["approved_scope"]["allowed_url_prefixes"] = ["https://example.com/guides"]
    with pytest.raises(receipt.EvidenceError, match="qa_target_outside_reviewed_scope"):
        real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)


@pytest.mark.parametrize("escaped", ["/guide/%2e%2e/private", "/guide/text%2fsecret", "/guide/%252e%252e"])
def test_rejects_ambiguous_scoped_paths(escaped):
    with pytest.raises(receipt.EvidenceError, match="qa_scope_url_invalid"):
        real.within_scope("https://example.com" + escaped, ["https://example.com/guide"])


def test_reopened_limited_record_cannot_claim_authority_or_another_reason():
    packet = captured_packet()
    packet["approved_scope"].update(expected_outcome="limited", expected_limit_reason="rate_limit")
    run = packet["saved_run"]
    del run["authority_proof"]
    run.update(status="limited", release_gate_eligible=False, result_integrity_proof="e" * 64)
    projection = packet["browser"]["projection"]
    projection.update(authority_verified=False, result_integrity_verified=True)
    projection["run"].update(status="limited", coverage_reasons=["staged_rate_limit"])
    dynamic, _ = real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)
    assert dynamic.terminal_status == "limited"
    projection["run"]["coverage_reasons"] = ["staged_wall_budget"]
    with pytest.raises(receipt.EvidenceError, match="qa_limited_readback_reason_mismatch"):
        real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)


def test_rejects_a_page_identity_aliased_under_two_checked_rows():
    packet = captured_packet()
    canary, scope = real.validate_readbacks(packet, expected_result_route=ROUTE, claim_key=CLAIM_KEY)
    data = {"pages": [
        {"url": "https://example.com/guide/first", "final_url": "https://example.com/guide/final"},
        {"url": "https://example.com/guide/second", "final_url": "https://example.com/guide/final"},
    ]}
    with pytest.raises(receipt.EvidenceError, match="qa_page_identity_duplicate"):
        real.page_sets(data, canary, scope)
