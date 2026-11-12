"""Offline contract for public Standard 150 claim reopening (incident #378).

A deliberately stubbed metadata verifier tests call order. This does not
exercise Cloud Run, Base44, signed receipts, or release acceptance.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts/fixlist-cloud-operator.sh"


def _function(source: str, name: str, next_name: str) -> str:
    return source.split(f"{name}() {{", 1)[1].split(f"\n{next_name}() {{", 1)[0]


def test_public_open_metadata_guard_precedes_cloud_operations():
    source = OPERATOR.read_text(encoding="utf-8")
    block = _function(source, "open_claim_barrier", "activate_acceptance_only")
    gate = 'python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"'
    assert block.count(gate) == 1
    assert block.index("require_exact_main_owner_source") < block.index(gate)
    assert block.index("require_confirmation") < block.index(gate)
    assert block.index(gate) < block.index("require_closed_drained_barrier")
    assert block.index(gate) < block.index("require_drain_plane_live")
    assert block.index(gate) < block.index('call_barrier_operator open "$ADMISSION_BARRIER_OPEN_PATH"')

    # Admission-only acceptance and emergency rollback must not gain an
    # accidental frozen-release prerequisite.
    acceptance = _function(source, "activate_acceptance_only", "case \"$OPERATION\" in")
    assert gate not in acceptance
    rollback = source.split('rollback-worker)', 1)[1].split(";;", 1)[0]
    assert gate not in rollback


def _run_public_open_with_stub(tmp_path: Path, *, accepted: bool):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "assert_standard150_promotion_record.py").write_text(
        f"import sys\nsys.exit({0 if accepted else 2})\n", encoding="utf-8"
    )
    source = OPERATOR.read_text(encoding="utf-8")
    body = _function(source, "open_claim_barrier", "activate_acceptance_only")
    # The production function is extracted unmodified, while all cloud and
    # signing operations are inert recording stubs.
    fixture = """set -euo pipefail
open_claim_barrier() {""" + body + """
require_exact_main_owner_source() { :; }
require_barrier_inputs() { :; }
require_confirmation() {
  [[ "$1" == "OPEN-STANDARD150-CLAIMS:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}" ]]
}
require_closed_drained_barrier() { echo drained >> "$TRACE"; }
require_drain_plane_live() { echo live >> "$TRACE"; }
call_barrier_operator() { echo cloud_write >> "$TRACE"; }
parse_barrier_response() { BARRIER_MODE=open; BARRIER_GENERATION=12; }
open_claim_barrier
"""
    trace = tmp_path / "trace"
    environment = {
        **os.environ,
        "REPO_ROOT": str(tmp_path),
        "SOURCE_SHA": "a" * 40,
        "BARRIER_EXPECTED_GENERATION": "11",
        "ADMISSION_BARRIER_OPEN_PATH": "/ops/barrier/open",
        "TRACE": str(trace),
    }
    result = subprocess.run(
        ["bash", "-c", fixture],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result, trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []


def test_unaccepted_metadata_blocks_before_first_cloud_operation(tmp_path):
    result, trace = _run_public_open_with_stub(tmp_path, accepted=False)
    assert result.returncode != 0
    assert trace == []


def test_mock_accepted_metadata_preserves_existing_drain_sequence(tmp_path):
    result, trace = _run_public_open_with_stub(tmp_path, accepted=True)
    assert result.returncode == 0, result.stderr
    assert trace == ["drained", "live", "cloud_write"]
    assert "STANDARD150_CLAIM_BARRIER_OPEN generation=12" in result.stdout
