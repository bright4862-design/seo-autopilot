import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.standard150_exact_release import (
    exact_release_dimension,
    exact_release_matrix_failures,
    load_expected_release_fingerprint,
)


EXPECTED = "0123456789abcdef"


def test_exact_release_match_passes():
    dimension = exact_release_dimension(
        observed_fingerprint=EXPECTED,
        release_contract_current=True,
        expected_fingerprint=EXPECTED,
    )
    assert dimension == {
        "available": True,
        "state": "match",
        "matches": True,
        "expected_fingerprint": EXPECTED,
        "observed_fingerprint": EXPECTED,
        "release_contract_current": True,
    }
    assert exact_release_matrix_failures(
        {"exact_release_markers": dimension}
    ) == []


def test_nonempty_stale_fingerprint_is_measured_but_fails():
    stale = "fedcba9876543210"
    dimension = exact_release_dimension(
        observed_fingerprint=stale,
        release_contract_current=True,
        expected_fingerprint=EXPECTED,
    )
    assert dimension["available"] is True
    assert dimension["state"] == "mismatch"
    assert dimension["matches"] is False
    assert dimension["observed_fingerprint"] == stale
    assert exact_release_matrix_failures(
        {"exact_release_markers": dimension}
    ) == ["exact_release_markers"]


def test_missing_required_fingerprint_is_unavailable_gap_material():
    dimension = exact_release_dimension(
        observed_fingerprint="",
        release_contract_current=True,
        expected_fingerprint=EXPECTED,
    )
    assert dimension["available"] is False
    assert dimension["state"] == "unavailable"
    assert dimension["matches"] is None


def test_missing_current_release_marker_is_unavailable():
    dimension = exact_release_dimension(
        observed_fingerprint=EXPECTED,
        release_contract_current=None,
        expected_fingerprint=EXPECTED,
    )
    assert dimension["available"] is False
    assert dimension["state"] == "unavailable"
    assert dimension["matches"] is None


def test_present_fingerprint_with_false_current_marker_fails():
    dimension = exact_release_dimension(
        observed_fingerprint=EXPECTED,
        release_contract_current=False,
        expected_fingerprint=EXPECTED,
    )
    assert dimension["available"] is True
    assert dimension["state"] == "mismatch"
    assert dimension["matches"] is False
    assert exact_release_matrix_failures(
        {"exact_release_markers": dimension}
    ) == ["exact_release_markers"]


@pytest.mark.parametrize(
    "invalid",
    [
        "0" * 15,
        "0" * 17,
        "0" * 64,
        "G" * 16,
    ],
)
def test_expected_release_identity_rejects_noncanonical_fingerprint_shape(invalid):
    with pytest.raises(ValueError, match="expected_release_fingerprint_invalid"):
        exact_release_dimension(
            observed_fingerprint=EXPECTED,
            release_contract_current=True,
            expected_fingerprint=invalid,
        )


def test_expected_release_identity_is_loaded_from_canonical_record(tmp_path):
    record = tmp_path / "beta-crawler-revision.json"
    record.write_text(
        json.dumps({
            "fingerprint": EXPECTED,
            "git_commit": "",
        }),
        encoding="utf-8",
    )
    assert load_expected_release_fingerprint(record) == EXPECTED


@pytest.mark.parametrize("invalid", ["0" * 15, "0" * 17, "0" * 64])
def test_canonical_record_rejects_noncanonical_fingerprint_lengths(tmp_path, invalid):
    record = tmp_path / "beta-crawler-revision.json"
    record.write_text(json.dumps({"fingerprint": invalid}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or invalid"):
        load_expected_release_fingerprint(record)


def test_exact_release_dimension_does_not_invent_source_sha():
    dimension = exact_release_dimension(
        observed_fingerprint=EXPECTED,
        release_contract_current=True,
        expected_fingerprint=EXPECTED,
    )
    assert "source_sha" not in dimension
    assert "git_commit" not in dimension
