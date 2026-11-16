"""Offline tests of real Cloud Run serving-topology verifier (no GCP calls)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "assert_standard150_serving_topology.py"
OPERATOR = ROOT / "scripts" / "fixlist-cloud-operator.sh"
SERVICE = "fixlist-standard150-worker"
OLD = "fixlist-standard150-worker-00054-old"
NEXT = "fixlist-standard150-worker-00055-next"


def stable() -> dict:
    return {
        "metadata": {"name": SERVICE, "generation": 77},
        "spec": {
            "traffic": [
                {"revisionName": OLD, "percent": 100},
                {"revisionName": NEXT, "percent": 0, "tag": "candidate"},
            ]
        },
        "status": {
            "observedGeneration": 77,
            "conditions": [{"type": "Ready", "status": "True"}],
            "traffic": [
                {"revisionName": OLD, "percent": 100},
                {"revisionName": NEXT, "percent": 0, "tag": "candidate"},
            ],
        },
    }


def check(current, *, baseline=None, expected=None, expected_service=SERVICE):
    with tempfile.TemporaryDirectory() as temp:
        here = Path(temp)
        now = here / "current.json"
        now.write_text(json.dumps(current))
        cmd = [sys.executable, str(CHECK), str(now), "--service", expected_service]
        if baseline is not None:
            previous = here / "previous.json"
            previous.write_text(json.dumps(baseline))
            cmd += ["--baseline", str(previous)]
        if expected is not None:
            cmd += ["--expect-revision", expected]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_stable_explicit_topology_returns_only_serving_revision():
    state = stable()
    result = check(state)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == OLD
    state["metadata"]["generation"] = "77"
    state["status"]["observedGeneration"] = "77"
    assert check(state).returncode == 0, "Cloud Run may encode generation as a decimal string"


@pytest.mark.parametrize(
    "alter",
    [
        lambda s: s["spec"].update(traffic=[{"revisionName": NEXT, "percent": 100}]),
        lambda s: s["metadata"].update(generation=78),
        lambda s: s["status"].update(observedGeneration=76),
        lambda s: s["status"].update(conditions=[{"type": "Ready", "status": "False"}]),
        lambda s: s["status"].update(conditions=[]),
        lambda s: s["spec"].update(traffic=[{"revisionName": NEXT, "percent": 100, "latestRevision": True}]),
        lambda s: s["status"].update(traffic=[{"revisionName": OLD, "percent": 100, "latestRevision": True}]),
        lambda s: s["spec"].update(traffic=[{"revisionName": OLD, "percent": 90}, {"revisionName": NEXT, "percent": 10}]),
        lambda s: s["status"].update(traffic=[{"revisionName": OLD, "percent": 100}, {"revisionName": NEXT, "percent": 100}]),
        lambda s: s["spec"].update(traffic=[{"revisionName": OLD, "percent": True}]),
        lambda s: s["spec"].update(traffic=[]),
        lambda s: s["status"].pop("traffic"),
        lambda s: s["metadata"].update(name="not-the-worker"),
        lambda s: s["metadata"].pop("generation"),
        lambda s: s["status"].update(observedGeneration=False),
        lambda s: s["spec"].update(traffic=[{"latestRevision": True, "percent": 100}]),
    ],
)
def test_unsafe_or_unattributable_traffic_is_refused(alter):
    state = stable()
    alter(state)
    result = check(state)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "INDETERMINATE:" in result.stderr
    assert result.stdout == "", "never print a candidate revision from an unsafe inventory"


def test_after_probe_readback_must_match_exact_before_snapshot():
    original = stable()
    same = check(copy.deepcopy(original), baseline=original, expected=OLD)
    assert same.returncode == 0, same.stderr
    assert same.stdout.strip() == OLD

    # This is the main false-green scenario: the old worker still has status
    # 100%, but a new 100% revision is already desired.
    moving = copy.deepcopy(original)
    moving["metadata"]["generation"] = 78
    moving["spec"]["traffic"] = [{"revisionName": NEXT, "percent": 100}]
    moving["status"]["observedGeneration"] = 77
    assert check(moving, baseline=original, expected=OLD).returncode == 2

    # Even after reconciliation, a new 100% worker must not count as the
    # /revision result that was collected from the old worker.
    reconciled = stable()
    reconciled["metadata"]["generation"] = 78
    reconciled["status"]["observedGeneration"] = 78
    reconciled["spec"]["traffic"] = [{"revisionName": NEXT, "percent": 100}]
    reconciled["status"]["traffic"] = [{"revisionName": NEXT, "percent": 100}]
    assert check(reconciled, baseline=original, expected=OLD).returncode == 2
    assert check(reconciled, expected=OLD).returncode == 2


def test_readback_rejects_other_changes_even_with_same_selected_revision():
    baseline = stable()
    changed = copy.deepcopy(baseline)
    changed["metadata"]["generation"] = 78
    changed["status"]["observedGeneration"] = 78
    assert check(changed, baseline=baseline, expected=OLD).returncode == 2
    changed = copy.deepcopy(baseline)
    changed["spec"]["traffic"].append({"revisionName": NEXT, "percent": 0, "tag": "different"})
    assert check(changed, baseline=baseline, expected=OLD).returncode == 2


def test_runtime_script_uses_guard_before_and_after_the_authenticated_get():
    text = OPERATOR.read_text(encoding="utf-8")
    start = text.index("verify_worker_runtime_revision() {")
    end = text.index("\n# A candidate at 0% traffic", start)
    body = text[start:end]
    assert body.count("scripts/assert_standard150_serving_topology.py") == 2
    pre = body.index("serving_topology_baseline=\"$service_json\"")
    probe = body.index('"\u0024{probe_url}/revision"')
    after = body.index("--baseline \"$serving_topology_baseline\"")
    passing = body.index("PASS: the running worker computes")
    assert pre < probe < after < passing
    assert "if [ -z \"$revision\" ]; then" in body
    assert "if [ -n \"$serving_topology_baseline\" ]; then" in body
    assert "update-traffic" not in body
