from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.fixbench.run_grounding import run_fixture, run_suite


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


def test_fixbench_grounding_url_scope_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_url_scope_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 4


def test_fixbench_grounding_nested_scope_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_nested_scope_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 6


def test_fixbench_grounding_identity_scope_gate_passes():
    fixture = ROOT / "scripts" / "fixbench" / "fixtures" / "grounding_identity_scope_v1.json"
    report = run_fixture(fixture)
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 7


def test_all_registered_grounding_fixtures_pass_as_one_gate():
    report = run_suite()
    assert report["gate_state"] == "passed"
    assert report["passed"] == report["total"] == 83
    assert len(report["suites"]) == 11


def test_empty_suite_cannot_pass(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="empty"):
        run_suite(tmp_path)


def test_unregistered_fixture_cannot_be_silently_skipped(tmp_path):
    import pytest
    (tmp_path / "grounding_unknown.json").write_text('{"fixture_version":"unknown"}')
    with pytest.raises(ValueError, match="unsupported"):
        run_suite(tmp_path)
