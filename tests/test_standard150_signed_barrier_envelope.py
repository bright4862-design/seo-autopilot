"""Incident #378: signed admission barrier snapshot must bind the reported envelope.

Hermetic: the Python verifier is extracted from the actual Cloud Operator shell
source. No GCP, Base44, production key, network request or scanner is involved.
"""
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "fixlist-cloud-operator.sh"
LABEL = "fixlist-admission-drain-snapshot-v1"


def embedded_response_parser():
    source = OPERATOR.read_text(encoding="utf-8")
    match = re.search(
        r"mapfile -t _barrier_values < <\(python3 -[\s\S]*?<<'PY'\n([\s\S]*?)\nPY",
        source,
    )
    assert match, "Expected to run the real response-verifier Python here-doc"
    return match.group(1)


def signed_snapshot(*, mode="closed", generation=7, drained=True):
    snapshot = {
        "version": "admission_drain_snapshot_v1",
        "snapshot_id": "snap-verified",
        "barrier": {"mode": mode, "generation": generation},
        "counts": {
            "total_obligations": 0,
            "claimed_active": 0,
            "claimed_expired": 0,
            "bound": 0,
            "live_reconciliation": 0,
        },
        "drain_ready": drained,
    }
    return snapshot


def run_parser(tmp_path, *, signed_mode="closed", signed_generation=7,
               reported_mode="closed", reported_generation=7,
               drop_signed_barrier=False, corrupt_proof=False):
    key = b"synthetic-only-never-a-live-credential"
    key_path = tmp_path / "dummy-key"
    key_path.write_bytes(key)
    unsigned = signed_snapshot(mode=signed_mode, generation=signed_generation)
    if drop_signed_barrier:
        unsigned.pop("barrier")
    derived = hmac.new(key, LABEL.encode(), hashlib.sha256).digest()
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    proof = hmac.new(derived, canonical, hashlib.sha256).hexdigest()
    if corrupt_proof:
        proof = "0" * 64 if proof != "0" * 64 else "1" * 64
    envelope = {
        "success": True,
        "operation": "status",
        "barrier": {"mode": reported_mode, "generation": reported_generation},
        "drain_snapshot": {**unsigned, "proof": proof},
    }
    response_path = tmp_path / "response.json"
    response_path.write_text(json.dumps(envelope), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", embedded_response_parser(),
         str(response_path), "status", str(key_path), LABEL,
         # Current main's additional scoped-pilot arguments are inert for status.
         "", "", "", "", "0", "0", "", "{}", "", "0", "0"],
        capture_output=True, text=True, timeout=5,
    )


def test_matching_synthetically_signed_barrier_envelope_passes(tmp_path):
    proc = run_parser(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[:4] == [
        "closed", "7", "snap-verified", "true"
    ]


@pytest.mark.parametrize("case", [
    {"signed_mode": "open", "reported_mode": "closed"},
    {"signed_mode": "closed", "reported_mode": "open"},
    {"signed_mode": "acceptance_only", "reported_mode": "closed"},
    {"signed_generation": 6, "reported_generation": 7},
    {"signed_generation": 8, "reported_generation": 7},
    {"drop_signed_barrier": True},
    {"corrupt_proof": True},
    {"signed_generation": True, "reported_generation": 1},
    {"signed_generation": 1, "reported_generation": True},
])
def test_signed_snapshot_cannot_authorize_conflicting_envelope(tmp_path, case):
    proc = run_parser(tmp_path, **case)
    expected_error = ("Drain snapshot signature mismatch" if case.get("corrupt_proof")
                      else "Barrier envelope disagrees with signed drain snapshot")
    if type(case.get("reported_generation")) is bool:
        expected_error = "Invalid barrier generation"
    assert proc.returncode != 0, (
        "A valid HMAC for a different barrier state must not authorize the "
        f"outer mode/generation: {case!r}, stdout={proc.stdout!r}"
    )
    assert proc.stderr.strip() == expected_error, proc.stderr
