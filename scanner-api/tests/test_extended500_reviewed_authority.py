"""Reviewed Extended 500 authority contract (NON-OPERATIONAL); fully offline.

Covers the Python producer/verifier, adversarial refusals, and a cross-runtime
test where Python-signed envelopes are verified by the JavaScript verifier with
identical reason codes for every adversarial case.
"""
import copy
import hashlib
import hmac
import json
import subprocess
from pathlib import Path

import pytest

from app.authority_seal import create_authority_seal
from app.extended500_evidence_handoff import build_extended500_evidence_handoff
from app.extended500_reviewed_authority import (
    EXTENDED500_REVIEWED_MAX_BYTES,
    EXTENDED500_REVIEWED_PURPOSE,
    EXTENDED500_REVIEWED_RESTRICTED_FIELDS,
    EXTENDED500_REVIEWED_VERSION,
    Extended500ReviewedAuthorityError,
    build_extended500_reviewed_authority,
    canonical_reviewed_bytes,
    verify_extended500_reviewed_authority,
)
from app.scan_job import build_completion_envelope

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_KEY = "fixture-secret-not-for-production"
REVIEWED_ROOT = "fixture-reviewed-root-not-for-production-500"
RECORD = json.loads((ROOT / "data" / "beta-crawler-revision.json").read_text())
SOURCE_SHA = "a" * 40
EXPECTED_RELEASE = {
    "scanner_source_sha": SOURCE_SHA,
    "beta_revision_fingerprint": RECORD["fingerprint"],
    "review_version": RECORD["component_versions"]["review_version"],
}


def _scan():
    return {
        "scan_mode": "extended_500", "status": "reviewing",
        "owner_user_id": "owner-500", "id": "scan-500", "project_id": "project-500",
        "request_id": "req-500", "idempotency_key": "idem-500",
        "normalized_domain": "example.com", "website_url": "https://example.com/",
        "attempt_count": 2, "release_gate_eligible": False,
    }


def _url(i):
    return f"https://example.com/page-{i:04d}"


def _result(size):
    pages = [
        {"url": _url(i), "final_url": _url(i), "status_code": 200, "title": f"Page {i}",
         "main_text": "secret internal text", "_reachability_links": [{"href": _url(0)}]}
        for i in range(size)
    ]
    return {
        "scan_mode": "extended_500", "canonical_mode": "extended_500",
        "scan_id": "scan-500", "request_id": "req-500", "idempotency_key": "idem-500",
        "normalized_domain": "example.com", "pages_found": size + 40, "pages_crawled": size,
        "pages": pages, "crawled_pages": copy.deepcopy(pages),
        "scan_coverage": {"urls_attempted": size + 7, "usable_html_pages": size,
                          "unique_retained_destinations": size},
        "scanner_source_sha": SOURCE_SHA,
        "beta_revision_fingerprint": RECORD["fingerprint"],
    }


def _handoff(size=6, scan=None):
    return build_extended500_evidence_handoff(scan or _scan(), _result(size), HANDOFF_KEY)


def _finding(fix_id, pages, *, action="fix_first", score=4380, priority="high", scope="family"):
    return {
        "fix_id": fix_id, "rule": f"rule_{fix_id}", "category": "Metadata",
        "issue_title": f"Fix {fix_id}", "plain_english_explanation": "Explained.",
        "simple_next_step": "Do the next step.", "priority": "medium", "base_severity": priority,
        "evidence_class": "confirmed_problem", "action_priority": action,
        "action_priority_score": score, "page_scope": scope, "page_template_family": "article",
        "affected_pages": pages, "evidence_status": "confirmed", "verification_state": "verified",
        "confidence_score": 88.0, "repair_fingerprint": f"fp_{fix_id}",
        # Ignored producer-only fields never reach the signed contract.
        "priority_context": {"version": "x"}, "raw_finding": {"verified_urls": pages},
    }


def _review(size=6, reviewed=None, findings=None):
    reviewed_urls = [_url(i) for i in range(size)] if reviewed is None else reviewed
    return {
        "review_status": "reviewed",
        "review_version": EXPECTED_RELEASE["review_version"],
        "sampling_policy_version": "extended500_review_all_assessed_v1",
        "reviewed_page_urls": reviewed_urls,
        "review_confidence_state": "complete",
        "score_is_provisional": False,
        "health_score": 72,
        "findings": findings if findings is not None else [
            _finding("f1", [_url(0), _url(1)]),
            _finding("f2", [_url(2)], action="important", score=3210, priority="medium", scope="page"),
        ],
    }


def _ctx(**overrides):
    base = {
        "scan_run": _scan(), "expected_release": dict(EXPECTED_RELEASE),
        "signing_root": REVIEWED_ROOT, "handoff_signing_key": HANDOFF_KEY,
    }
    base.update(overrides)
    return base


def _build(size=6, review=None, handoff=None, **overrides):
    ctx = _ctx(**overrides)
    handoff = handoff or _handoff(size, ctx["scan_run"])
    envelope = build_extended500_reviewed_authority(
        scan_run=ctx["scan_run"], evidence_handoff=handoff,
        handoff_signing_key=ctx["handoff_signing_key"], review=review or _review(size),
        expected_release=ctx["expected_release"], signing_root=ctx["signing_root"],
    )
    return envelope, handoff


def _verify(envelope, handoff, **overrides):
    ctx = _ctx(**overrides)
    return verify_extended500_reviewed_authority(
        envelope, scan_run=ctx["scan_run"], expected_release=ctx["expected_release"],
        signing_root=ctx["signing_root"], evidence_handoff=handoff,
        handoff_signing_key=ctx["handoff_signing_key"],
    )


def _independent_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _resign(envelope, root=REVIEWED_ROOT):
    signed = {k: v for k, v in envelope.items() if k != "proof"}
    derived = hmac.new(root.encode(), EXTENDED500_REVIEWED_PURPOSE.encode(), hashlib.sha256).digest()
    return {**signed, "proof": hmac.new(derived, _independent_bytes(signed), hashlib.sha256).hexdigest()}


# --------------------------------------------------------------- good case --

def test_minimal_reviewed_case_is_valid_but_never_publishable():
    envelope, handoff = _build()
    assert envelope["version"] == EXTENDED500_REVIEWED_VERSION
    assert envelope["operational_status"] == "non_operational_no_verified_terminal_issuer"
    assert envelope["review"]["release_gate_eligible"] is False
    assert envelope["review"]["terminal_receipt_state"] == "not_issued"
    assert envelope["review"]["review_coverage_state"] == "all_assessed_pages_reviewed"
    assert envelope["coverage"] == {
        "pages_found": 46, "urls_attempted": 13, "usable_html_pages": 6, "pages_assessed": 6,
        "pages_reviewed": 6, "pages_not_reviewed": 0, "review_coverage_basis_points": 10000,
        "pages_with_findings": 3,
    }
    assert envelope["evidence_binding"] == {
        "handoff_version": "extended500_evidence_handoff_v1_unreviewed", "handoff_proof": handoff["proof"],
    }
    first = envelope["findings"][0]
    assert first["affected_page_ids"] == ["p001", "p002"] and first["page_url"] == _url(0)
    assert first["priority"] == "high" and first["confidence_score"] == 88
    assert first["user_status"] == "open" and first["repair_verification_state"] == "not_compared"
    assert "priority_context" not in first and "raw_finding" not in first
    assert envelope["fix_list_summary"]["completed_count"] == 0
    assert envelope["fix_list_summary"]["canonical_action_fix_ids"] == ["f1", "f2"]
    assert "main_text" not in json.dumps(envelope)
    # Independent HMAC (purpose-derived key over independent canonical bytes).
    assert _resign(envelope)["proof"] == envelope["proof"]
    assert _verify(envelope, handoff) == {
        "valid": True, "state": "reviewed_authority_candidate_non_operational",
        "operational": False, "customer_publishable": False, "release_gate_eligible": False,
        "pages_assessed": 6, "pages_reviewed": 6, "total_fixes": 2,
    }


def test_bounded_sample_is_explicit_and_forces_provisional_score():
    review = _review(10, reviewed=[_url(i) for i in range(3)], findings=[_finding("f1", [_url(0)], scope="page")])
    envelope, handoff = _build(10, review=review)
    assert envelope["review"]["review_coverage_state"] == "bounded_sample_reviewed"
    assert envelope["review"]["score_is_provisional"] is True
    assert envelope["coverage"]["review_coverage_basis_points"] == 3000
    assert [p["review_state"] for p in envelope["pages"]][:4] == ["reviewed"] * 3 + ["not_reviewed"]
    assert _verify(envelope, handoff)["valid"] is True


def test_full_500_page_reviewed_envelope_and_zero_findings_state():
    review = _review(500, reviewed=[_url(i) for i in range(60)], findings=[])
    review["review_confidence_state"] = "no_high_confidence_findings"
    envelope, handoff = _build(500, review=review)
    assert envelope["coverage"]["pages_assessed"] == 500
    assert envelope["review"]["no_high_confidence_findings"] is True
    assert len(canonical_reviewed_bytes({k: v for k, v in envelope.items() if k != "proof"})) < EXTENDED500_REVIEWED_MAX_BYTES
    assert _verify(envelope, handoff)["pages_reviewed"] == 60


# ------------------------------------------------------- producer refusals --

@pytest.mark.parametrize("mutate,reason", [
    (lambda r: r.update(review_status="not_reviewed"), "review_not_reviewed"),
    (lambda r: r.update(release_gate_eligible=True), "premature_release_gate"),
    (lambda r: r["findings"][0].update(user_status="done"), "false_fix_claim"),
    (lambda r: r["findings"][0].update(repair_verification_state="verified_fixed"), "false_fix_claim"),
    (lambda r: r["findings"][0].update(status="fixed"), "false_fix_claim"),
    (lambda r: r["findings"][0].update(affected_pages=[]), "finding_evidence_missing"),
    (lambda r: r["findings"][0].update(affected_pages=["https://example.com/not-retained"]), "finding_evidence_missing"),
    (lambda r: r["findings"][0].update(main_text="raw page text"), "restricted_field_present"),
    (lambda r: r.update(raw_html="<html></html>"), "restricted_field_present"),
    (lambda r: r["findings"][0].update(confidence_score=88.5), "finding_field_invalid"),
    (lambda r: r.update(reviewed_page_urls=["https://example.com/never-crawled"]), "page_index_invalid"),
    (lambda r: r.update(reviewed_page_urls=[]), "review_not_reviewed"),
    (lambda r: r.update(review_version="python_review_v1_old"), "release_mismatch"),
    (lambda r: r["findings"].reverse(), "priority_order_invalid"),
    (lambda r: r.update(findings=[]), "review_confidence_invalid"),
    (lambda r: r.update(no_high_confidence_findings=True), "review_confidence_invalid"),
])
def test_producer_refuses_unreviewed_false_or_unevidenced_authority(mutate, reason):
    review = _review()
    mutate(review)
    with pytest.raises(Extended500ReviewedAuthorityError) as caught:
        _build(review=review)
    assert caught.value.reason == reason


def test_producer_refuses_reviewed_findings_on_unreviewed_pages():
    review = _review(6, reviewed=[_url(0)], findings=[_finding("f1", [_url(0), _url(3)])])
    with pytest.raises(Extended500ReviewedAuthorityError) as caught:
        _build(review=review)
    assert caught.value.reason == "finding_evidence_not_reviewed"


@pytest.mark.parametrize("overrides,reason", [
    ({"scan_run": {**_scan(), "scan_mode": "standard_150"}}, "mode_invalid"),
    ({"scan_run": {**_scan(), "status": "complete"}}, "scan_state_invalid"),
    ({"scan_run": {**_scan(), "release_gate_eligible": True}}, "scan_state_invalid"),
    ({"signing_root": "short-root"}, "signing_root_invalid"),
    ({"expected_release": {**EXPECTED_RELEASE, "scanner_source_sha": "b" * 40}}, "release_mismatch"),
    ({"expected_release": {}}, "release_expectation_missing"),
])
def test_producer_refuses_foreign_stale_or_misconfigured_context(overrides, reason):
    handoff = _handoff()
    with pytest.raises(Extended500ReviewedAuthorityError) as caught:
        _build(handoff=handoff, **overrides)
    assert caught.value.reason == reason


def test_producer_refuses_same_root_for_handoff_and_reviewed_authority():
    long_key = "x" * 40
    scan = _scan()
    handoff = build_extended500_evidence_handoff(scan, _result(6), long_key)
    with pytest.raises(Extended500ReviewedAuthorityError) as caught:
        _build(handoff=handoff, signing_root=long_key, handoff_signing_key=long_key)
    assert caught.value.reason == "signing_root_not_distinct"


def test_producer_refuses_stale_attempt_and_foreign_tenant_handoff():
    handoff = _handoff()
    for scan, reason in (
        ({**_scan(), "attempt_count": 3}, "attempt_mismatch"),
        ({**_scan(), "owner_user_id": "other-owner"}, "identity_mismatch"),
        ({**_scan(), "project_id": "other-project"}, "identity_mismatch"),
    ):
        with pytest.raises(Extended500ReviewedAuthorityError) as caught:
            _build(handoff=handoff, scan_run=scan)
        assert caught.value.reason == reason
    forged = {**handoff, "proof": "0" * 64}
    with pytest.raises(Extended500ReviewedAuthorityError) as caught:
        _build(handoff=forged)
    assert caught.value.reason == "evidence_handoff_invalid"


def test_501_pages_cannot_be_collected_or_reviewed():
    with pytest.raises(ValueError, match="assessed page count"):
        _handoff(501)


def test_standard150_signer_still_refuses_extended500_and_contracts_are_disjoint():
    envelope, handoff = _build()
    with pytest.raises(ValueError, match="foreign scan mode"):
        build_completion_envelope(_scan(), _result(6), {}, HANDOFF_KEY)
    # A raw-secret Standard 150 style seal over the reviewed payload is not a reviewed proof.
    signed = {k: v for k, v in envelope.items() if k != "proof"}
    raw_seal = {**signed, "proof": create_authority_seal(signed, REVIEWED_ROOT)}
    assert _verify(raw_seal, handoff) == {"valid": False, "reason": "hmac_invalid"}


def test_canonical_serialization_is_strict():
    assert canonical_reviewed_bytes({"b": 1, "a": [True, None, "é\n 😀"]}) == \
        '{"a":[true,null,"é\\n 😀"],"b":1}'.encode()
    for bad in (1.5, 2**53, {"é": 1}, ("tuple",), "\ud800", {"k": float("nan")}):
        with pytest.raises(Extended500ReviewedAuthorityError) as caught:
            canonical_reviewed_bytes(bad)
        assert caught.value.reason == "canonical_value_invalid"


# ---------------------------------------- adversarial verifier battery --

def _cases():
    """(name, mutate(envelope, handoff) -> (envelope, handoff, ctx_overrides), resign, reason)."""
    def env(fn):
        def apply(e, h):
            fn(e)
            return e, h, {}
        return apply

    def ctx(**overrides):
        return lambda e, h: (e, h, overrides)

    def finding(fn):
        return env(lambda e: fn(e["findings"][0]))

    big_text = "€" * 2000
    return [
        ("tampered_without_resign", finding(lambda f: f.update(issue_title="Tampered title")), False, "hmac_invalid"),
        ("tampered_health_score", env(lambda e: e["review"].update(health_score=99)), False, "hmac_invalid"),
        ("tampered_proof", env(lambda e: e.update(proof="f" * 64)), False, "hmac_invalid"),
        ("uppercase_proof", env(lambda e: e.update(proof=e["proof"].upper())), False, "hmac_invalid"),
        ("wrong_root", ctx(signing_root="another-reviewed-root-not-for-production"), False, "hmac_invalid"),
        ("short_root", ctx(signing_root="short"), False, "signing_root_invalid"),
        ("same_roots", ctx(signing_root=HANDOFF_KEY + "-extended", handoff_signing_key=HANDOFF_KEY + "-extended"), False, "signing_root_not_distinct"),
        ("unreviewed_handoff_as_reviewed", lambda e, h: (copy.deepcopy(h), h, {}), False, "unreviewed_handoff_not_promotable"),
        ("standard150_version", env(lambda e: e.update(version="durable_standard150_completion_v1")), True, "version_invalid"),
        ("extra_top_level_key", env(lambda e: e.update(extra=1)), True, "shape_invalid"),
        ("wrong_purpose", env(lambda e: e.update(purpose="scan_evidence_hmac_sha256_v1")), True, "purpose_invalid"),
        ("operational_claim", env(lambda e: e.update(operational_status="operational")), True, "non_operational_marker_invalid"),
        ("frozen_standard150", ctx(scan_run={**_scan(), "scan_mode": "standard_150"}), False, "mode_invalid"),
        ("identity_standard150", env(lambda e: e["identity"].update(canonical_mode="standard_150")), True, "mode_invalid"),
        ("frozen_terminal", ctx(scan_run={**_scan(), "status": "complete"}), False, "scan_state_invalid"),
        ("frozen_already_sealed", ctx(scan_run={**_scan(), "authority_proof": "c" * 64}), False, "scan_state_invalid"),
        ("frozen_release_gate_live", ctx(scan_run={**_scan(), "release_gate_eligible": True}), False, "scan_state_invalid"),
        ("foreign_owner", ctx(scan_run={**_scan(), "owner_user_id": "tenant-b"}), False, "identity_mismatch"),
        ("foreign_project_resigned", env(lambda e: e["identity"].update(project_id="project-b")), True, "identity_mismatch"),
        ("foreign_domain", ctx(scan_run={**_scan(), "normalized_domain": "evil.com"}), False, "domain_mismatch"),
        ("stale_attempt", ctx(scan_run={**_scan(), "attempt_count": 3}), False, "attempt_mismatch"),
        ("premature_release_gate", env(lambda e: e["review"].update(release_gate_eligible=True)), True, "premature_release_gate"),
        ("premature_terminal_receipt", env(lambda e: e["review"].update(terminal_receipt_state="issued")), True, "premature_release_gate"),
        ("review_not_reviewed", env(lambda e: e["review"].update(review_status="not_reviewed")), True, "review_not_reviewed"),
        ("missing_release_expectation", ctx(expected_release=None), False, "release_expectation_missing"),
        ("stale_source_sha", ctx(expected_release={**EXPECTED_RELEASE, "scanner_source_sha": "d" * 40}), False, "release_mismatch"),
        ("stale_fingerprint_marker", ctx(expected_release={**EXPECTED_RELEASE, "beta_revision_fingerprint": "0" * 16}), False, "release_mismatch"),
        ("stale_review_version", ctx(expected_release={**EXPECTED_RELEASE, "review_version": "python_review_v1"}), False, "release_mismatch"),
        ("forged_handoff", lambda e, h: (e, {**h, "proof": "0" * 64}, {}), False, "evidence_handoff_invalid"),
        ("handoff_wrong_key", ctx(handoff_signing_key="a-different-handoff-key"), False, "evidence_handoff_invalid"),
        ("binding_foreign_proof", env(lambda e: e["evidence_binding"].update(handoff_proof="e" * 64)), True, "evidence_binding_mismatch"),
        ("binding_version", env(lambda e: e["evidence_binding"].update(handoff_version=EXTENDED500_REVIEWED_VERSION)), True, "evidence_binding_mismatch"),
        ("dropped_page", env(lambda e: e["pages"].pop()), True, "page_count_invalid"),
        ("page_501", env(lambda e: e["pages"].extend({"page_id": f"p{i:03d}", "final_url": _url(i), "review_state": "reviewed"} for i in range(7, 502))), True, "page_count_invalid"),
        ("page_reordered", env(lambda e: e["pages"].reverse()), True, "page_index_invalid"),
        ("page_url_swapped", env(lambda e: e["pages"][5].update(final_url="https://example.com/other")), True, "page_index_invalid"),
        ("page_state_unknown", env(lambda e: e["pages"][5].update(review_state="sampled")), True, "page_index_invalid"),
        ("contradictory_reviewed_total", env(lambda e: e["coverage"].update(pages_reviewed=5)), True, "denominator_mismatch"),
        ("contradictory_not_reviewed", env(lambda e: e["coverage"].update(pages_not_reviewed=1)), True, "denominator_mismatch"),
        ("contradictory_basis_points", env(lambda e: e["coverage"].update(review_coverage_basis_points=9999)), True, "denominator_mismatch"),
        ("inflated_discovery", env(lambda e: e["coverage"].update(pages_found=900)), True, "denominator_mismatch"),
        ("inflated_assessed", env(lambda e: e["coverage"].update(pages_assessed=500)), True, "denominator_mismatch"),
        ("float_denominator", env(lambda e: e["coverage"].update(pages_found=46.5)), True, "denominator_mismatch"),
        ("pages_with_findings", env(lambda e: e["coverage"].update(pages_with_findings=6)), True, "denominator_mismatch"),
        ("zero_reviewed", env(lambda e: [p.update(review_state="not_reviewed") for p in e["pages"]]), True, "review_not_reviewed"),
        ("coverage_overclaim", env(lambda e: [e["pages"][5].update(review_state="not_reviewed"), e["coverage"].update(pages_reviewed=5, pages_not_reviewed=1, review_coverage_basis_points=8333)]), True, "review_coverage_invalid"),
        ("sampling_policy_missing", env(lambda e: e["review"].update(sampling_policy_version="")), True, "review_coverage_invalid"),
        ("confidence_unknown", env(lambda e: e["review"].update(review_confidence_state="verified")), True, "review_confidence_invalid"),
        ("provisional_hidden", env(lambda e: e["review"].update(review_confidence_state="partial_access_needs_verification")), True, "review_confidence_invalid"),
        ("health_score_float", env(lambda e: e["review"].update(health_score=72.5)), True, "review_confidence_invalid"),
        ("no_high_conf_with_findings", env(lambda e: e["review"].update(no_high_confidence_findings=True)), True, "review_confidence_invalid"),
        ("finding_extra_field", finding(lambda f: f.update(raw_finding={})), True, "finding_shape_invalid"),
        ("finding_raw_main_text", finding(lambda f: f.update(main_text_signature="x")), True, "restricted_field_present"),
        ("page_raw_html", env(lambda e: e["pages"][0].update(raw_html="<html>")), True, "restricted_field_present"),
        ("false_fix_user_done", finding(lambda f: f.update(user_status="done")), True, "false_fix_claim"),
        ("false_fix_verified_fixed", finding(lambda f: f.update(repair_verification_state="verified_fixed")), True, "false_fix_claim"),
        ("false_fix_evidence_resolved", finding(lambda f: f.update(evidence_status="resolved")), True, "false_fix_claim"),
        ("false_fix_completed_count", env(lambda e: e["fix_list_summary"].update(completed_count=1)), True, "false_fix_claim"),
        ("comparison_state_unsupported", finding(lambda f: f.update(repair_verification_state="still_detected")), True, "finding_field_invalid"),
        ("finding_bad_priority", finding(lambda f: f.update(priority="urgent")), True, "finding_field_invalid"),
        ("finding_float_score", finding(lambda f: f.update(confidence_score=88.5)), True, "finding_field_invalid"),
        ("finding_title_padding", finding(lambda f: f.update(issue_title=" Fix ")), True, "finding_field_invalid"),
        ("finding_page_count", finding(lambda f: f.update(page_count=3)), True, "finding_field_invalid"),
        ("finding_page_url_foreign", finding(lambda f: f.update(page_url="https://evil.com/")), True, "finding_field_invalid"),
        ("finding_no_evidence", finding(lambda f: f.update(affected_page_ids=[], page_count=0)), True, "finding_evidence_missing"),
        ("finding_unknown_page", finding(lambda f: f.update(affected_page_ids=["p999", "p002"])), True, "finding_evidence_missing"),
        ("finding_unreviewed_page", env(lambda e: [e["pages"][1].update(review_state="not_reviewed"), e["coverage"].update(pages_reviewed=5, pages_not_reviewed=1, review_coverage_basis_points=8333), e["review"].update(review_coverage_state="bounded_sample_reviewed", score_is_provisional=True)]), True, "finding_evidence_not_reviewed"),
        ("duplicate_fix_id", env(lambda e: e["findings"][1].update(fix_id="f1")), True, "duplicate_finding"),
        ("priority_order", env(lambda e: e["findings"][1].update(action_priority_score=9999, action_priority="fix_first")), True, "priority_order_invalid"),
        ("rank_gap", finding(lambda f: f.update(canonical_action_rank=2)), True, "priority_order_invalid"),
        ("summary_counts", env(lambda e: e["fix_list_summary"].update(high_count=0)), True, "aggregation_mismatch"),
        ("summary_bool_count", env(lambda e: e["fix_list_summary"].update(total_fixes=True)), True, "aggregation_mismatch"),
        ("summary_order", env(lambda e: e["fix_list_summary"].update(canonical_action_fix_ids=["f2", "f1"])), True, "aggregation_mismatch"),
        ("oversized", env(lambda e: _oversize(e, big_text)), True, "byte_budget_exceeded"),
    ]


def _oversize(envelope, text):
    findings = []
    for index in range(200):
        findings.append({
            **envelope["findings"][0], "fix_id": f"z{index:03d}", "repair_fingerprint": f"fpz{index:03d}",
            "canonical_action_rank": index + 1, "plain_english_explanation": text,
            "simple_next_step": text, "affected_page_ids": ["p001"], "page_count": 1, "page_url": _url(0),
            "page_scope": "page",
        })
    envelope["findings"] = findings
    ids = [f["fix_id"] for f in findings]
    envelope["fix_list_summary"].update(
        total_fixes=200, high_count=200, medium_count=0, fix_first_count=200, important_count=0,
        top_action_fix_ids=ids[:3], canonical_action_fix_ids=ids,
    )
    envelope["coverage"]["pages_with_findings"] = 1


def _materialize():
    base, handoff = _build()
    rows = []
    for name, mutate, resign, reason in _cases():
        envelope, case_handoff, overrides = mutate(copy.deepcopy(base), copy.deepcopy(handoff))
        if resign:
            envelope = _resign(envelope)
        rows.append((name, envelope, case_handoff, overrides, reason))
    return base, handoff, rows


def test_adversarial_battery_has_dozens_of_distinct_refusals():
    _, _, rows = _materialize()
    assert len(rows) >= 60
    assert len({reason for *_, reason in rows}) >= 30


@pytest.mark.parametrize("index", range(len(_cases())))
def test_python_verifier_refuses_each_adversarial_case(index):
    _, _, rows = _materialize()
    name, envelope, handoff, overrides, reason = rows[index]
    assert _verify(envelope, handoff, **overrides) == {"valid": False, "reason": reason}, name


# ------------------------------------------------------ cross runtime --

_NODE = """
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import {
  verifyExtended500ReviewedAuthority, canonicalReviewedJson,
  EXTENDED500_REVIEWED_RESTRICTED_FIELDS,
} from './src/lib/extended500ReviewedAuthority.js';
const input = JSON.parse(readFileSync(0, 'utf8'));
const run = (envelope, handoff, ctx) => verifyExtended500ReviewedAuthority(envelope, {
  frozenScan: ctx.scan_run, expectedRelease: ctx.expected_release, secret: ctx.signing_root,
  evidenceHandoff: handoff, handoffSecret: ctx.handoff_signing_key,
});
const out = { accepted: await run(input.envelope, input.handoff, input.ctx), cases: {} };
out.tampered = await run({ ...input.envelope, review: { ...input.envelope.review, health_score: 99 } }, input.handoff, input.ctx);
for (const row of input.cases) out.cases[row.name] = await run(row.envelope, row.handoff, row.ctx);
const digest = (value) => createHash('sha256').update(canonicalReviewedJson(value), 'utf8').digest('hex');
out.signedDigest = digest(input.signed);
out.trickyDigest = digest(input.tricky);
out.restricted = [...EXTENDED500_REVIEWED_RESTRICTED_FIELDS].sort();
process.stdout.write(JSON.stringify(out));
"""


def test_python_signed_reviewed_envelopes_verify_identically_in_javascript():
    base, handoff, rows = _materialize()
    signed = {k: v for k, v in base.items() if k != "proof"}
    tricky = {"z": "quote\" backslash\\ tab\t nl\n nul\x00 del\x7f ls  é 😀 中", "a": [0, -1, 2**53 - 1, None, False]}
    payload = {
        "envelope": base, "handoff": handoff, "ctx": _ctx(), "signed": signed, "tricky": tricky,
        "cases": [{"name": name, "envelope": env, "handoff": h, "ctx": _ctx(**ov)} for name, env, h, ov, _ in rows],
    }
    child = subprocess.run(
        ["node", "--input-type=module", "-e", _NODE],
        input=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        text=True, capture_output=True, cwd=ROOT, check=True, timeout=120,
    )
    status = json.loads(child.stdout)
    assert status["accepted"] == _verify(base, handoff)
    assert status["accepted"]["valid"] is True and status["accepted"]["customer_publishable"] is False
    assert status["tampered"] == {"valid": False, "reason": "hmac_invalid"}
    assert status["signedDigest"] == hashlib.sha256(canonical_reviewed_bytes(signed)).hexdigest()
    assert status["trickyDigest"] == hashlib.sha256(canonical_reviewed_bytes(tricky)).hexdigest()
    assert status["restricted"] == sorted(EXTENDED500_REVIEWED_RESTRICTED_FIELDS)
    for name, _env, _h, _ov, reason in rows:
        assert status["cases"][name] == {"valid": False, "reason": reason}, name


def test_contract_is_not_wired_into_any_runtime_surface():
    needles = ("extended500_reviewed_authority", "extended500ReviewedAuthority")
    own = {
        ROOT / "scanner-api/app/extended500_reviewed_authority.py",
        ROOT / "src/lib/extended500ReviewedAuthority.js",
    }
    offenders = []
    for folder, pattern in (("scanner-api/app", "*.py"), ("src", "**/*.js*"), ("base44", "**/*.*"),
                            ("extended500-admission", "*.py")):
        for file in (ROOT / folder).glob(pattern):
            if file in own or not file.is_file():
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            if any(needle in text for needle in needles):
                offenders.append(str(file.relative_to(ROOT)))
    assert offenders == []
    source = (ROOT / "scanner-api/app/extended500_reviewed_authority.py").read_text()
    for forbidden in ("os.getenv", "os.environ", "httpx", "requests", "invoke_function", "release_gate_eligible\": True"):
        assert forbidden not in source
