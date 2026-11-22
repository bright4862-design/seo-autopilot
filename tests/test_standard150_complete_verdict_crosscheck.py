"""Hermetic falsifiers: available verdict evidence can contradict a complete release.

No network requests, Cloud Run mutations, customer scans, or signing operations.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for directory in (ROOT, SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from scripts.standard150_acceptance_matrix import (  # noqa: E402
    _matrix_contract_gaps,
    complete_verdict_failures,
)

SPEC = importlib.util.spec_from_file_location(
    "standard150_verdict_ramp", SCRIPTS / "standard150-ramp-harness.py",
)
assert SPEC is not None and SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)


def _item():
    item = HARNESS.Submission(
        email="owner@example.com",
        url="https://example.com",
        project_id="project_1",
        request_id="scanreq_fresh_1",
    )
    item.scan_id = "scan_verdict"
    item.http_status = 200
    item.accepted = True
    item.submitted_at = 100.0
    item.terminal_at = 101.0
    item.run = {
        "id": item.scan_id,
        "project_id": item.project_id,
        "status": "complete",
        "error_code": "",
        "fix_list_id": "fixlist_1",
        "coverage_authority_evidence": {"state": "sufficient"},
        "classification_integrity": {"state": "classified"},
        "evidence_quality_state": "representative",
        "evidence_quality_score": 92,
        "evidence_quality_blocking": False,
        "peak_memory_bytes": 1024 * 1024,
        "beta_revision_fingerprint": HARNESS.EXPECTED_RELEASE_FINGERPRINT,
    }
    item.customer_result = {
        "access": "full",
        "scan_id": item.scan_id,
        "authority_verified": True,
        "result_integrity_verified": True,
        "release_contract_current": True,
        "fixList": {
            "id": "fixlist_1",
            "project_id": item.project_id,
            "scan_run_id": item.scan_id,
        },
        "fixItems": [],
    }
    return item


def test_valid_complete_receipt_retains_zero_fix_baseline():
    item = _item()
    report = HARNESS.report([item], {})
    assert report["passed"] is True
    assert report["results"][0]["matrix_failures"] == []


def test_complete_with_measured_insufficient_coverage_is_not_green():
    item = _item()
    item.run["coverage_authority_evidence"]["state"] = "limited_coverage"
    report = HARNESS.report([item], {})
    assert report["passed"] is False
    assert "complete_coverage_not_sufficient" in report["results"][0]["matrix_failures"]


def test_complete_with_measured_inconclusive_classification_is_not_green():
    item = _item()
    item.run["classification_integrity"]["state"] = "inconclusive_insufficient_evidence"
    report = HARNESS.report([item], {})
    assert report["passed"] is False
    assert "complete_classification_inconclusive" in report["results"][0]["matrix_failures"]


def test_complete_with_evidence_quality_blocking_is_not_green():
    item = _item()
    item.run["evidence_quality_blocking"] = True
    report = HARNESS.report([item], {})
    assert report["passed"] is False
    assert "complete_evidence_quality_blocked" in report["results"][0]["matrix_failures"]


def test_complete_with_blocked_quality_state_and_forged_nonblocking_flag_fails():
    item = _item()
    item.run["evidence_quality_state"] = "no_usable_html"
    item.run["evidence_quality_blocking"] = False
    report = HARNESS.report([item], {})
    assert report["passed"] is False
    assert "complete_evidence_quality_blocked" in report["results"][0]["matrix_failures"]


def test_limited_scan_can_truthfully_report_poor_coverage_and_quality():
    item = _item()
    item.run.update({
        "status": "limited",
        "error_code": "scan_access_limited",
        "coverage_authority_evidence": {"state": "access_limited"},
        "classification_integrity": {"state": "inconclusive_insufficient_evidence"},
        "evidence_quality_state": "access_limited",
        "evidence_quality_blocking": True,
    })
    item.customer_result.update({
        "authority_verified": False,
        "result_integrity_verified": True,
        "fixList": None,
        "fixItems": [],
    })
    matrix = HARNESS.build_acceptance_matrix(HARNESS._matrix_observation(item))
    assert complete_verdict_failures(matrix) == []
    assert HARNESS.report([item], {})["passed"] is True


def test_unmeasured_coverage_remains_gap_not_invented_negative_verdict():
    item = _item()
    del item.run["coverage_authority_evidence"]
    matrix = HARNESS.build_acceptance_matrix(HARNESS._matrix_observation(item))
    assert "coverage_sufficiency" in _matrix_contract_gaps(matrix)
    assert complete_verdict_failures(matrix) == []
    assert HARNESS.report([item], {})["passed"] is False


def test_checkpoint_and_final_report_agree_on_verdict_blockers():
    item = _item()
    item.run["coverage_authority_evidence"]["state"] = "inventory_unproven"
    final = HARNESS.report([item], {})
    checkpoint = HARNESS.checkpoint_payload([item])
    assert "complete_coverage_not_sufficient" in final["results"][0]["matrix_failures"]
    assert "complete_coverage_not_sufficient" in checkpoint["sites"][0]["matrix_failures"]
