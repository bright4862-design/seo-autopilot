from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.standard150_acceptance_matrix import (  # noqa: E402
    REQUIRED_MATRIX_DIMENSIONS,
    _matrix_contract_gaps,
    build_acceptance_matrix,
)


SPEC = importlib.util.spec_from_file_location(
    "standard150_ramp_harness",
    SCRIPTS / "standard150-ramp-harness.py",
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)


def _complete_item(scan_id: str = "scan_complete"):
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.scan_id = scan_id
    item.http_status = 200
    item.accepted = True
    item.submitted_at = 100.0
    item.terminal_at = 102.5
    item.run = {
        "id": scan_id,
        "status": "complete",
        "error_code": "",
        "fix_list_id": "fixlist_1",
        "evidence_quality_state": "sufficient",
        "evidence_quality_score": 100,
        "beta_revision_fingerprint": "fingerprint_1",
        "scanner_version": "scanner_1",
        "scanner_build_revision": "build_1",
        "review_version": "review_1",
    }
    item.customer_result = {
        "scan_id": scan_id,
        "authority_verified": True,
        "result_integrity_verified": False,
        "release_contract_current": True,
        "fixList": {"id": "fixlist_1"},
        "fixItems": [],
    }
    return item


def test_matrix_has_ten_independent_dimensions_and_only_real_gaps():
    item = _complete_item()
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert set(matrix) == set(REQUIRED_MATRIX_DIMENSIONS)
    assert matrix["infrastructure_outcome"]["terminal_status"] == "complete"
    assert matrix["authority_outcome"]["state"] == "authoritative"
    assert matrix["evidence_quality_verdict"]["state"] == "sufficient"
    assert matrix["ui_result_route_verdict"]["state"] == "exact"
    assert matrix["duration"]["milliseconds"] == 2500
    assert matrix["exact_release_markers"]["beta_revision_fingerprint"] == "fingerprint_1"

    assert set(_matrix_contract_gaps(matrix)) == {
        "coverage_sufficiency",
        "classification_verdict",
        "memory_resource_result",
    }


def test_healthy_complete_scan_measures_absence_of_limited_access():
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(_complete_item()))
    dimension = matrix["limited_access_failure_class"]

    assert dimension == {
        "available": True,
        "state": "none",
        "limited": False,
        "failure_class": "",
    }
    assert "limited_access_failure_class" not in _matrix_contract_gaps(matrix)


def test_unprojected_limited_access_dimension_is_still_a_gap():
    matrix = build_acceptance_matrix({})

    assert matrix["limited_access_failure_class"]["available"] is False
    assert "limited_access_failure_class" in _matrix_contract_gaps(matrix)


def test_failed_access_limited_scan_records_its_real_class():
    matrix = build_acceptance_matrix({
        "scan_id": "scan_failed",
        "http_status": 200,
        "accepted": True,
        "run": {
            "id": "scan_failed",
            "status": "failed",
            "error_code": "scan_access_limited",
        },
        "customer_result": {
            "scan_id": "scan_failed",
            "authority_verified": False,
            "result_integrity_verified": False,
        },
    })
    dimension = matrix["limited_access_failure_class"]

    assert dimension["available"] is True
    assert dimension["state"] == "limited"
    assert dimension["limited"] is True
    assert dimension["failure_class"] == "scan_access_limited"


def test_integrity_only_limited_scan_records_its_class():
    item = _complete_item("scan_limited")
    item.run.update({
        "status": "limited",
        "error_code": "access_limited_429",
    })
    item.customer_result.update({
        "authority_verified": False,
        "result_integrity_verified": True,
    })
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["authority_outcome"]["state"] == "integrity_only"
    assert matrix["limited_access_failure_class"]["failure_class"] == "access_limited_429"


def test_archetype_label_is_not_invented_as_classification_verdict():
    item = _complete_item()
    item.run["business_archetype"] = "ecommerce"
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["classification_verdict"]["available"] is False
    assert matrix["classification_verdict"]["state"] == "unavailable"


def test_exact_result_route_mismatch_is_a_matrix_failure():
    item = _complete_item()
    item.customer_result["scan_id"] = "different_scan"
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["ui_result_route_verdict"]["state"] == "mismatch"
    assert "ui_result_route_mismatch" in _matrix_contract_gaps(matrix)


def test_admission_failure_code_is_consistent_in_matrix_and_summary():
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.http_status = 429
    item.accepted = False
    item.failure_code = "admission_capacity_limited"

    summary = HARNESS._result_summary(item)

    assert summary["error_code"] == "admission_capacity_limited"
    assert (
        summary["acceptance_matrix"]["infrastructure_outcome"]["failure_code"]
        == "admission_capacity_limited"
    )


def test_exact_release_wrapper_preserves_base_release_markers(monkeypatch):
    item = _complete_item("scan_exact_markers")
    item.run.update({
        "beta_revision_fingerprint": "0123456789abcdef",
        "review_evidence_calibration_version": "calibration_1",
        "archetype_classifier_version": "classifier_1",
    })
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(
        HARNESS,
        "EXPECTED_RELEASE_FINGERPRINT",
        "0123456789abcdef",
    )

    exact = HARNESS.build_acceptance_matrix(
        HARNESS._matrix_observation(item)
    )["exact_release_markers"]

    assert exact["state"] == "match"
    assert exact["scanner_version"] == "scanner_1"
    assert exact["scanner_build_revision"] == "build_1"
    assert exact["review_version"] == "review_1"
    assert exact["review_evidence_calibration_version"] == "calibration_1"
    assert exact["archetype_classifier_version"] == "classifier_1"


def test_terminal_poll_durably_checkpoints_the_completed_site(
    tmp_path,
    monkeypatch,
):
    item = _complete_item("scan_1")
    item.terminal_at = 0.0
    item.run = {}
    item.customer_result = {}
    checkpoint = tmp_path / "acceptance.json"

    async def fake_invoke(_client, _token, function, payload):
        assert function == "getCustomerScanResult"
        assert payload == {"action": "get", "scan_id": "scan_1"}
        return 200, {
            "scan_id": "scan_1",
            "run": {
                "id": "scan_1",
                "status": "complete",
                "fix_list_id": "fixlist_1",
                "evidence_quality_state": "sufficient",
                "beta_revision_fingerprint": "fingerprint_1",
            },
            "authority_verified": True,
            "release_contract_current": True,
            "fixList": {"id": "fixlist_1"},
            "fixItems": [],
        }

    monkeypatch.setattr(HARNESS, "invoke", fake_invoke)
    asyncio.run(HARNESS.wait_terminal(
        object(),
        {item.email: "token"},
        [item],
        1,
        checkpoint_path=str(checkpoint),
    ))

    persisted = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert persisted["completed_sites"] == 1
    assert persisted["sites"][0]["scan_id"] == "scan_1"
    assert set(persisted["sites"][0]["acceptance_matrix"]) == set(
        REQUIRED_MATRIX_DIMENSIONS
    )


def test_checkpoint_is_atomic_fsynced_compact_and_preserves_prior_sites(
    tmp_path,
    monkeypatch,
):
    first = _complete_item("scan_1")
    second = _complete_item("scan_2")
    second.terminal_at = 0.0
    second.run = {"id": "scan_2", "status": "crawling"}
    second.customer_result = {"scan_id": "scan_2", "run": dict(second.run)}
    checkpoint = tmp_path / "acceptance.json"
    fsync_calls = []
    real_fsync = HARNESS.os.fsync

    def observed_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(HARNESS.os, "fsync", observed_fsync)
    HARNESS.write_checkpoint(str(checkpoint), [first, second])

    first_write = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert [site["scan_id"] for site in first_write["sites"]] == ["scan_1"]
    assert "acceptance@example.com" not in checkpoint.read_text(encoding="utf-8")
    assert "Bearer " not in checkpoint.read_text(encoding="utf-8")
    assert "fixItems" not in checkpoint.read_text(encoding="utf-8")
    assert len(fsync_calls) == 2
    assert list(tmp_path.glob("*.tmp")) == []

    second.terminal_at = 105.0
    second.run.update({
        "status": "complete",
        "evidence_quality_state": "sufficient",
        "beta_revision_fingerprint": "fingerprint_1",
    })
    second.customer_result.update({
        "authority_verified": True,
        "release_contract_current": True,
        "fixList": {"id": "fixlist_2"},
        "fixItems": [],
    })
    HARNESS.write_checkpoint(str(checkpoint), [first, second])

    second_write = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert [site["scan_id"] for site in second_write["sites"]] == [
        "scan_1",
        "scan_2",
    ]


def test_final_aggregate_cannot_pass_with_unmeasured_dimensions():
    result = HARNESS.report(
        [_complete_item()],
        {"available": False, "reason": "test"},
    )

    assert result["passed"] is False
    assert any(
        "coverage_sufficiency" in failure
        and "classification_verdict" in failure
        and "memory_resource_result" in failure
        for failure in result["failures"]
    )


def test_real_harness_requires_the_exact_release_under_acceptance(monkeypatch):
    item = _complete_item("scan_exact_release")
    item.run["beta_revision_fingerprint"] = "0123456789abcdef"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is True
    assert exact["matches"] is True
    assert exact["state"] == "match"
    assert "exact_release_markers" not in summary["matrix_gaps"]
    assert "exact_release_markers" not in summary["matrix_failures"]


def test_real_harness_rejects_historical_valid_but_not_current_release(monkeypatch):
    item = _complete_item("scan_historical")
    item.run["beta_revision_fingerprint"] = "fedcba9876543210"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is True
    assert exact["matches"] is False
    assert exact["state"] == "mismatch"
    assert "exact_release_markers" in summary["matrix_failures"]


def test_real_harness_missing_release_fingerprint_remains_a_gap(monkeypatch):
    item = _complete_item("scan_missing_marker")
    item.run.pop("beta_revision_fingerprint", None)
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is False
    assert exact["state"] == "unavailable"
    assert "exact_release_markers" in summary["matrix_gaps"]


def test_final_aggregate_fails_on_stale_exact_release_even_when_marker_is_present(
    monkeypatch,
):
    item = _complete_item("scan_wrong_release")
    item.run["beta_revision_fingerprint"] = "fedcba9876543210"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    result = HARNESS.report(
        [item],
        {"available": False, "reason": "test"},
    )
    assert result["passed"] is False
    assert any(
        "exact_release_markers" in failure
        and "failed required evidence" in failure
        for failure in result["failures"]
    )
