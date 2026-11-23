"""Inert promotion readback regression. Never calls GCP or customer systems."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/assert_standard150_rollback_readback.py"
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
CANDIDATE = "worker-00125-candidate"
PRIOR = "worker-00100-prior"

def snapshot(*, desired=None, observed=None, ready="True", generation=9, seen=9):
    routed = [{"revisionName": CANDIDATE, "percent": 100}]
    return {"metadata": {"generation": generation},
            "spec": {"traffic": routed if desired is None else desired},
            "status": {"observedGeneration": seen,
                       "conditions": [{"type": "Ready", "status": ready}],
                       "traffic": routed if observed is None else observed}}

def evaluate(tmp_path, data, context="promotion"):
    path = tmp_path / "service.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--expected-revision", CANDIDATE,
                           "--service-json", str(path), "--context", context],
                          cwd=ROOT, capture_output=True, text=True, timeout=8)

def observed_only(data):
    """The removed workflow predicate, retained as a measurable weak baseline."""
    traffic = data.get("status", {}).get("traffic", []) or []
    return sum(int(item.get("percent") or 0)
               for item in traffic if item.get("revisionName") == CANDIDATE) == 100

def test_converged_promotion_and_backwards_compatible_rollback(tmp_path):
    data = snapshot()
    assert observed_only(data)
    for context, marker in (("promotion", "PROMOTION_TRAFFIC_READBACK_OK"),
                            ("rollback", "ROLLBACK_TRAFFIC_READBACK_OK")):
        outcome = evaluate(tmp_path, data, context)
        assert outcome.returncode == 0, outcome.stderr
        assert marker in outcome.stdout

@pytest.mark.parametrize("change", [
    {"desired": [{"revisionName": PRIOR, "percent": 100}]},
    {"ready": "False"},
    {"generation": 10, "seen": 9},
    {"desired": [{"latestRevision": True, "percent": 100}]},
    {"observed": [{"revisionName": CANDIDATE, "percent": 60},
                  {"revisionName": CANDIDATE, "percent": 40}]},
])
def test_false_green_baseline_is_rejected_by_strict_readback(tmp_path, change):
    data = snapshot(**change)
    assert observed_only(data), "the prior observed-only comparison must pass"
    result = evaluate(tmp_path, data)
    assert result.returncode == 2
    assert "PROMOTION_UNVERIFIED" in result.stderr
    assert "READBACK_OK" not in result.stdout

def test_exact_workflow_runs_readback_before_other_postchecks():
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Promote exact candidate with automatic rollback on failed post-check")
    end = text.index("      - name: Publish exact promotion status", start)
    section = text[start:end]
    assert "python3 scripts/assert_standard150_rollback_readback.py" in section
    assert '--expected-revision "$REVISION"' in section
    assert "--context promotion" in section
    assert section.index("--context promotion") < section.index('service_url="$(gcloud run services describe')
    assert "percent = sum(int(item.get('percent')" not in section
