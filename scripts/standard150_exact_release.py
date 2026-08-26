"""Release-contract identity checks for Standard 150 production acceptance.

The expected fingerprint comes from the repository's canonical beta revision
record. Runtime/ScanRun fields are observations only and are never promoted
into the expected identity. This proves the declared release-contract identity;
source/deployment SHA provenance remains a separate release gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_RECORD = REPO_ROOT / "data" / "beta-crawler-revision.json"
# beta-crawler-revision fingerprints are canonical 16-hex values. Do not accept
# arbitrary SHA-like lengths as equivalent release identities.
FINGERPRINT_RE = re.compile(r"^[a-f0-9]{16}$")


def load_expected_release_fingerprint(path: Path | str = DEFAULT_RELEASE_RECORD) -> str:
    """Load the exact candidate fingerprint from the canonical source record."""
    record_path = Path(path)
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"canonical release fingerprint could not be loaded from {record_path}"
        ) from exc
    fingerprint = str(payload.get("fingerprint") or "").strip().lower()
    if not FINGERPRINT_RE.fullmatch(fingerprint):
        raise RuntimeError(
            f"canonical release fingerprint is missing or invalid in {record_path}"
        )
    return fingerprint


def exact_release_dimension(
    *,
    observed_fingerprint: Any,
    release_contract_current: Any,
    expected_fingerprint: str,
) -> dict[str, Any]:
    """Project current release-contract identity without conflating absence/mismatch.

    Missing required markers are unavailable. A present but stale/wrong marker
    is available evidence with a failing mismatch state.
    """
    expected = str(expected_fingerprint or "").strip().lower()
    if not FINGERPRINT_RE.fullmatch(expected):
        raise ValueError("expected_release_fingerprint_invalid")

    observed = str(observed_fingerprint or "").strip().lower()
    marker_measured = isinstance(release_contract_current, bool)
    if not observed or not marker_measured:
        return {
            "available": False,
            "state": "unavailable",
            "matches": None,
            "expected_fingerprint": expected,
            "observed_fingerprint": observed,
            "release_contract_current": (
                release_contract_current if marker_measured else None
            ),
        }

    matches = bool(
        observed == expected
        and release_contract_current is True
    )
    return {
        "available": True,
        "state": "match" if matches else "mismatch",
        "matches": matches,
        "expected_fingerprint": expected,
        "observed_fingerprint": observed,
        "release_contract_current": release_contract_current,
    }


def exact_release_matrix_failures(matrix: dict[str, Any]) -> list[str]:
    """Return measured release-identity failures; unavailable stays a gap."""
    dimension = (
        matrix.get("exact_release_markers")
        if isinstance(matrix, dict)
        else None
    )
    if not isinstance(dimension, dict):
        return []
    if dimension.get("available") is True and dimension.get("matches") is not True:
        return ["exact_release_markers"]
    return []
