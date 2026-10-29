"""Dual-attested reviewed *candidate* tests: no real reviewer or customer writes."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from app.authority_seal import create_authority_seal
from app.extended500_evidence_handoff import build_extended500_evidence_handoff
from app.extended500_reviewed_authority import (
    REVIEW_VERSION, AUTHORITY_VERSION,
    Extended500ReviewedRefused,
    build_extended500_reviewed_authority,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_KEY = "e" * 40
REVIEWER_KEY = "r" * 40
AUTHORITY_KEY = "a" * 40
SHA = "b" * 40
MARKER = "c" * 16


def scan():
    return {
        "scan_mode": "extended_500", "id": "scan_one",
        "owner_user_id": "owner_one", "project_id": "project_one",
        "request_id": "req_one", "idempotency_key": "idem_one",
        "attempt_count": 1, "website_url": "https://example.com/",
        "normalized_domain": "example.com",
    }


def raw(n):
    pages = [
        {"url": f"https://example.com/item-{i}", "final_url": f"https://example.com/item-{i}",
         "title": f"Fixture {i}", "status_code": 200,
         "main_text": "secret text", "_reachability_links": [{"href": "https://example.com"}]}
        for i in range(n)
    ]
    return {
        "scan_mode": "extended_500", "canonical_mode": "extended_500",
        "scan_id": "scan_one", "request_id": "req_one", "idempotency_key": "idem_one",
        "normalized_domain": "example.com", "pages_found": n + 20,
        "pages_crawled": n, "pages": pages, "crawled_pages": copy.deepcopy(pages),
        "scan_coverage": {"urls_attempted": n, "usable_html_pages": n,
                          "unique_retained_destinations": n},
        "scanner_source_sha": SHA, "beta_revision_fingerprint": MARKER,
        "release_gate_eligible": False,
    }


def fixture(n=3):
    frozen = scan()
    handoff = build_extended500_evidence_handoff(frozen, raw(n), EVIDENCE_KEY)
    identity = handoff["identity"]
    destinations = [page["final_url"] for page in handoff["scan"]["pages"]]
    review = {
        "version": REVIEW_VERSION, "review_status": "reviewed",
        "identity": copy.deepcopy(identity),
        "scanner_source_sha": SHA, "beta_revision_fingerprint": MARKER,
        "pages_reviewed": n, "reviewed_destinations": destinations,
        "findings": [{
            "rule_id": "missing_h1", "page_url": destinations[0],
            "severity": "medium", "evidence_state": "observed",
        }],
    }
    return frozen, handoff, {**review, "proof": create_authority_seal(review, REVIEWER_KEY)}


def build(frozen, handoff, review, **overrides):
    args = {
        "evidence_signing_key": EVIDENCE_KEY,
        "reviewer_signing_key": REVIEWER_KEY,
        "authority_signing_key": AUTHORITY_KEY,
        "expected_source_sha": SHA, "expected_fingerprint": MARKER,
    }
    return build_extended500_reviewed_authority(frozen, handoff, review, **{**args, **overrides})


@pytest.mark.parametrize("n", [1, 150, 500])
def test_independently_signed_reviewed_evidence_is_still_unreleased(n):
    frozen, handoff, review = fixture(n)
    actual = build(frozen, handoff, review)
    assert actual["version"] == AUTHORITY_VERSION
    assert actual["review"]["review_status"] == "reviewed"
    assert actual["review"]["pages_reviewed"] == n
    assert actual["release_gate_eligible"] is False
    assert actual["reviewer_proof"] == review["proof"]
    assert len(actual["proof"]) == 64
    assert create_authority_seal({k: v for k, v in actual.items() if k != "proof"}, AUTHORITY_KEY) == actual["proof"]
    assert "main_text" not in actual["scan"]["pages"][0]
    assert "_reachability_links" not in actual["scan"]["pages"][0]


@pytest.mark.parametrize("field,value,expected", [
    ("scan_mode", "standard_150", "frozen_extended500"),
    ("owner_user_id", "other", "owner_request_identity"),
    ("project_id", "other", "owner_request_identity"),
    ("attempt_count", 2, "attempt_identity"),
    ("attempt_count", True, "attempt_identity"),
    ("website_url", "https://other.example.net/", "domain_mode"),
])
def test_wrong_frozen_identity_fails(field, value, expected):
    f, h, r = fixture()
    f[field] = value
    with pytest.raises(Extended500ReviewedRefused, match=expected):
        build(f, h, r)


def test_unsigned_or_forged_reviewer_cannot_promote_collection():
    f, h, r = fixture()
    with pytest.raises(Extended500ReviewedRefused, match="reviewer_shape_invalid"):
        build(f, h, {k: v for k, v in r.items() if k != "proof"})
    r["review_status"] = "reviewed"
    r["findings"].append({"rule_id": "fake", "page_url": "https://example.com/",
                          "severity": "critical", "evidence_state": "verified"})
    with pytest.raises(Extended500ReviewedRefused, match="review_finding_unverified"):
        build(f, h, r)
    f, h, r = fixture()
    r["pages_reviewed"] = 2
    with pytest.raises(Extended500ReviewedRefused, match="review_coverage_identity_mismatch"):
        build(f, h, r)
    f, h, r = fixture()
    r["proof"] = "0" * 64
    with pytest.raises(Extended500ReviewedRefused, match="independent_reviewer_signature_invalid"):
        build(f, h, r)


def test_handoff_hmac_tamper_fails_even_if_valid_reviewer_proof():
    f, h, r = fixture()
    h["scan"]["pages"][0]["title"] = "tampered after evidence signer"
    with pytest.raises(Extended500ReviewedRefused, match="unreviewed_handoff_signature_invalid"):
        build(f, h, r)


@pytest.mark.parametrize("change,expected", [
    ({"expected_source_sha": "f" * 40}, "release_source_marker_mismatch"),
    ({"expected_fingerprint": "f" * 16}, "release_source_marker_mismatch"),
    ({"reviewer_signing_key": AUTHORITY_KEY}, "distinct_server_signing_roots_required"),
    ({"evidence_signing_key": "short"}, "distinct_server_signing_roots_required"),
])
def test_release_identity_and_separate_signing_roots(change, expected):
    f, h, r = fixture()
    with pytest.raises(Extended500ReviewedRefused, match=expected):
        build(f, h, r, **change)


def test_page_coverage_cannot_claim_unobserved_or_foreign_domains():
    f, h, r = fixture()
    r["reviewed_destinations"][0] = "https://example.com/unknown"
    with pytest.raises(Extended500ReviewedRefused, match="review_coverage_identity_mismatch"):
        build(f, h, r)
    f, h, r = fixture()
    h["scan"]["pages"][0]["final_url"] = "https://attacker.test/x"
    h["proof"] = create_authority_seal({k: v for k, v in h.items() if k != "proof"}, EVIDENCE_KEY)
    with pytest.raises(Extended500ReviewedRefused, match="foreign_retained_page"):
        build(f, h, r)
    f, h, r = fixture()
    h["scan"]["scan_coverage"]["unique_retained_destinations"] = 2
    h["proof"] = create_authority_seal({k: v for k, v in h.items() if k != "proof"}, EVIDENCE_KEY)
    with pytest.raises(Extended500ReviewedRefused, match="coverage_denominator_invalid"):
        build(f, h, r)


def test_501_pages_never_produce_reviewed_authority():
    f = scan()
    with pytest.raises(ValueError, match="assessed page count mismatch"):
        build_extended500_evidence_handoff(f, raw(501), EVIDENCE_KEY)


def test_python_reviewed_envelope_verifies_in_node_without_publishing_customer_result():
    f, h, r = fixture(12)
    envelope = build(f, h, r)
    script = """
import { readFileSync } from 'node:fs';
import { verifyExtended500ReviewedAuthority } from './src/lib/extended500ReviewedAuthority.js';
const d = JSON.parse(readFileSync(0, 'utf8'));
const opts = { reviewerSigningKey:d.reviewerKey, authoritySigningKey:d.authorityKey,
  expectedSourceSha:d.source, expectedFingerprint:d.marker };
const good = await verifyExtended500ReviewedAuthority(d.envelope,d.frozen,opts);
const badOwner = await verifyExtended500ReviewedAuthority(d.envelope,{...d.frozen,owner_user_id:'attacker'},opts);
const badSignature = await verifyExtended500ReviewedAuthority({...d.envelope, proof:'0'.repeat(64)},d.frozen,opts);
process.stdout.write(JSON.stringify({good,badOwner,badSignature}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps({"frozen": f, "envelope": envelope, "reviewerKey": REVIEWER_KEY,
                          "authorityKey": AUTHORITY_KEY, "source": SHA, "marker": MARKER}),
        text=True, capture_output=True, cwd=ROOT, check=True, timeout=20,
    )
    data = json.loads(result.stdout)
    assert data["good"] == {"valid": True, "state": "reviewed_but_unreleased", "pages_reviewed": 12}
    assert data["badOwner"]["valid"] is False
    assert data["badSignature"]["valid"] is False
