from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.fixbench.run_grounding import run_fixture


def test_fixbench_grounding_adversarial_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_adversarial_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 10


def test_fixbench_v8_evidence_preservation_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_v8_preservation_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 7
