import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "standard150_ramp_harness_checkpoint_release",
    SCRIPTS / "standard150-ramp-harness.py",
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)

EXPECTED = "0123456789abcdef"
STALE = "fedcba9876543210"


def _terminal_item(
    *,
    scan_id: str,
    fingerprint: str | None,
    release_contract_current=True,
):
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.scan_id = scan_id
    item.accepted = True
    item.terminal_at = 1.0
    item.run = {
        "status": "complete",
        "error_code": "",
        "fix_list_id": "fixlist_1",
        "evidence_quality_score": 1,
    }
    if fingerprint is not None:
        item.run["beta_revision_fingerprint"] = fingerprint
    item.customer_result = {
        "authority_verified": True,
        "release_contract_current": release_contract_current,
        "fixList": {"id": "fixlist_1"},
        "fixItems": [],
    }
    return item


def _checkpoint_exact(item):
    return HARNESS._checkpoint_summary(item)["acceptance_matrix"]["exact_release_markers"]


def _final_exact(item):
    return HARNESS._result_summary(item)["acceptance_matrix"]["exact_release_markers"]


def test_checkpoint_stale_fingerprint_is_measured_mismatch(monkeypatch):
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", EXPECTED)
    item = _terminal_item(
        scan_id="scan_stale_checkpoint",
        fingerprint=STALE,
        release_contract_current=True,
    )

    checkpoint = HARNESS._checkpoint_summary(item)
    exact = checkpoint["acceptance_matrix"]["exact_release_markers"]

    assert exact["available"] is True
    assert exact["state"] == "mismatch"
    assert exact["matches"] is False
    assert exact["expected_fingerprint"] == EXPECTED
    assert exact["observed_fingerprint"] == STALE


def test_checkpoint_exact_fingerprint_is_match(monkeypatch):
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", EXPECTED)
    item = _terminal_item(
        scan_id="scan_exact_checkpoint",
        fingerprint=EXPECTED,
        release_contract_current=True,
    )

    exact = _checkpoint_exact(item)

    assert exact["available"] is True
    assert exact["state"] == "match"
    assert exact["matches"] is True


def test_checkpoint_missing_required_marker_remains_unavailable_gap(monkeypatch):
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", EXPECTED)
    item = _terminal_item(
        scan_id="scan_missing_checkpoint_marker",
        fingerprint=None,
        release_contract_current=True,
    )

    checkpoint = HARNESS._checkpoint_summary(item)
    exact = checkpoint["acceptance_matrix"]["exact_release_markers"]

    assert exact["available"] is False
    assert exact["state"] == "unavailable"
    assert exact["matches"] is None
    assert "exact_release_markers" in checkpoint["matrix_gaps"]


@pytest.mark.parametrize(
    ("fingerprint", "release_contract_current"),
    [
        (EXPECTED, True),
        (STALE, True),
        (EXPECTED, False),
        (None, True),
    ],
)
def test_checkpoint_and_final_use_identical_exact_release_projection(
    monkeypatch,
    fingerprint,
    release_contract_current,
):
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", EXPECTED)
    item = _terminal_item(
        scan_id="scan_checkpoint_final_parity",
        fingerprint=fingerprint,
        release_contract_current=release_contract_current,
    )

    assert _checkpoint_exact(item) == _final_exact(item)
