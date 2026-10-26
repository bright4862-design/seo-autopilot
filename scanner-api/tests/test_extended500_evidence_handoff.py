"""Cross-runtime private evidence handoff contract; no network or Base44 writes."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from app.extended500_evidence_handoff import (
    EXTENDED500_HANDOFF_VERSION,
    build_extended500_evidence_handoff,
)
from app.scan_job import build_completion_envelope
from app.authority_seal import create_authority_seal

ROOT = Path(__file__).resolve().parents[2]
KEY = "fixture-secret-not-for-production"


def _scan():
    return {
        "scan_mode": "extended_500",
        "owner_user_id": "owner-500",
        "id": "scan-500",
        "project_id": "project-500",
        "request_id": "req-500",
        "idempotency_key": "idem-500",
        "normalized_domain": "example.com",
        "attempt_count": 2,
    }


def _result(size=500):
    pages = [
        {"url": f"https://example.com/page-{i:04d}", "final_url": f"https://example.com/page-{i:04d}",
         "status_code": 200, "title": f"Page {i}", "main_text": "secret internal text",
         "_reachability_links": [{"href": "https://example.com/page-0000"}],
         "future_internal_field": "not for customer"}
        for i in range(size)
    ]
    return {
        "scan_mode": "extended_500",
        "canonical_mode": "extended_500",
        "scan_id": "scan-500",
        "request_id": "req-500",
        "idempotency_key": "idem-500",
        "normalized_domain": "example.com",
        "pages_found": 850,
        "pages_crawled": size,
        "pages": pages,
        "crawled_pages": copy.deepcopy(pages),
        "scan_coverage": {
            "urls_attempted": size + 13,
            "usable_html_pages": size,
            "unique_retained_destinations": size,
        },
        "scanner_source_sha": "a" * 40,
        "beta_revision_fingerprint": "b" * 16,
        "release_gate_eligible": False,
    }


def test_private_500_handoff_preserves_counts_identity_and_projection():
    scan, result = _scan(), _result()
    envelope = build_extended500_evidence_handoff(scan, result, KEY)
    assert envelope["version"] == EXTENDED500_HANDOFF_VERSION
    assert envelope["identity"]["canonical_mode"] == "extended_500"
    assert envelope["identity"]["attempt_count"] == "2"
    assert envelope["scan"]["pages_crawled"] == 500
    assert len(envelope["scan"]["pages"]) == 500
    assert envelope["scan"]["scan_coverage"] == {
        "urls_attempted": 513, "usable_html_pages": 500, "unique_retained_destinations": 500,
    }
    assert envelope["review"] == {
        "review_status": "not_reviewed", "pages_reviewed": 0, "release_gate_eligible": False,
    }
    assert len(envelope["proof"]) == 64
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert create_authority_seal(signed, KEY) == envelope["proof"]
    assert "main_text" not in envelope["scan"]["pages"][0]
    assert "_reachability_links" not in envelope["scan"]["pages"][0]
    assert "future_internal_field" not in envelope["scan"]["pages"][0]
    assert result["pages"][0]["main_text"] == "secret internal text"

    # The deployed legacy builder MUST continue to refuse the same 500 pages.
    with pytest.raises(ValueError, match="more than 150"):
        build_completion_envelope(scan, result, {}, KEY)


@pytest.mark.parametrize("tamper", [
    lambda s, r: r.update(scan_mode="advanced"),
    lambda s, r: s.update(scan_mode="standard_150"),
    lambda s, r: r.update(canonical_mode="standard_150"),
    lambda s, r: r.update(request_id="other"),
    lambda s, r: s.update(attempt_count=0),
    lambda s, r: r.update(pages_crawled=499),
    lambda s, r: r["pages"][10].update(final_url=r["pages"][0]["final_url"]),
    lambda s, r: r.update(scanner_source_sha="not-a-source-sha"),
    lambda s, r: r.update(release_gate_eligible=True),
    lambda s, r: r["scan_coverage"].update(unique_retained_destinations=499),
    lambda s, r: r["scan_coverage"].update(urls_attempted=499),
])
def test_reject_misidentified_or_false_500_evidence(tamper):
    scan, result = _scan(), _result()
    tamper(scan, result)
    with pytest.raises(ValueError):
        build_extended500_evidence_handoff(scan, result, KEY)


def test_reject_501_and_mismatched_page_aliases_and_missing_scan_identity():
    scan, result = _scan(), _result(501)
    with pytest.raises(ValueError, match="assessed page count"):
        build_extended500_evidence_handoff(scan, result, KEY)
    scan, result = _scan(), _result()
    result["crawled_pages"].pop()
    with pytest.raises(ValueError, match="page aliases"):
        build_extended500_evidence_handoff(scan, result, KEY)
    scan, result = _scan(), _result()
    scan.pop("owner_user_id")
    with pytest.raises(ValueError, match="owner_user_id"):
        build_extended500_evidence_handoff(scan, result, KEY)


def test_python_hmac_verifies_in_javascript_without_widening_legacy_authority():
    payload = {"envelope": build_extended500_evidence_handoff(_scan(), _result(), KEY),
               "frozenScan": _scan(), "secret": KEY}
    script = """
import { readFileSync } from 'node:fs';
import { verifyExtended500EvidenceHandoff } from './base44/functions/persistDurableScanAuthority/extended500EvidenceHandoff.js';
const { envelope, frozenScan, secret } = JSON.parse(readFileSync(0, 'utf8'));
const accepted = await verifyExtended500EvidenceHandoff(envelope, frozenScan, secret);
const wrongAttempt = await verifyExtended500EvidenceHandoff(envelope, {...frozenScan, attempt_count: 3}, secret);
const forged = {...envelope, scan: {...envelope.scan, pages_crawled: 499}};
const tampered = await verifyExtended500EvidenceHandoff(forged, frozenScan, secret);
process.stdout.write(JSON.stringify({accepted, wrongAttempt, tampered}));
"""
    child = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        text=True, capture_output=True, cwd=ROOT, check=True, timeout=20,
    )
    status = json.loads(child.stdout)
    assert status["accepted"] == {
        "valid": True, "state": "unreviewed_evidence_only", "pages_retained": 500,
    }
    assert status["wrongAttempt"]["valid"] is False
    assert status["wrongAttempt"]["reason"] == "attempt_mismatch"
    assert status["tampered"]["valid"] is False
