from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.fixbench.run_grounding import run_fixture


def test_grounding_adversarial_fixbench_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_adversarial_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 13


def test_grounding_scalar_field_contract_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_scalar_field_contract_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 7
