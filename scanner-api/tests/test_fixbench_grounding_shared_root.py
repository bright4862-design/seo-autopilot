from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.fixbench.run_grounding import run_fixture


def test_fixbench_grounding_shared_root_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_shared_root_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 6
