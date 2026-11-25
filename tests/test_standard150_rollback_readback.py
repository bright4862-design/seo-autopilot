"""Inert Cloud Run fixtures and direct tests of the exact promotion rollback shell."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/assert_standard150_rollback_readback.py"
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
PRIOR = "fixlist-standard150-worker-00100-abc"
OTHER = "fixlist-standard150-worker-00101-xyz"


def state(*, desired=None, observed=None, generation=3, seen=3, ready="True"):
    a = [{"revisionName": PRIOR, "percent": 100}]
    return {"metadata": {"generation": generation},
            "spec": {"traffic": a if desired is None else desired},
            "status": {"observedGeneration": seen,
                       "conditions": [{"type": "Ready", "status": ready}],
                       "traffic": a if observed is None else observed}}


def check(tmp_path, fixture):
    f = tmp_path / "service.json"
    f.write_text(json.dumps(fixture))
    return subprocess.run([sys.executable, str(SCRIPT), "--expected-revision", PRIOR,
                           "--service-json", str(f)], capture_output=True, text=True, timeout=8)


def test_exact_rollback_and_zero_traffic_candidate(tmp_path):
    tag = {"revisionName": OTHER, "percent": 0, "tag": "candidate"}
    fixture = state(desired=[{"revisionName": PRIOR, "percent": 100}, tag],
                    observed=[{"revisionName": PRIOR, "percent": 100}, tag],
                    generation="12", seen=12)
    result = check(tmp_path, fixture)
    assert result.returncode == 0, result.stderr
    assert "ROLLBACK_TRAFFIC_READBACK_OK" in result.stdout


@pytest.mark.parametrize("change", [
    {"desired": [{"revisionName": OTHER, "percent": 100}]},
    {"observed": [{"revisionName": OTHER, "percent": 100}]},
    {"observed": [{"revisionName": PRIOR, "percent": 60},
                  {"revisionName": OTHER, "percent": 40}]},
    {"observed": [{"revisionName": PRIOR, "percent": 50},
                  {"revisionName": PRIOR, "percent": 50}]},
    {"desired": [{"revisionName": PRIOR, "percent": 99}]},
    {"observed": [{"revisionName": PRIOR, "percent": 100},
                  {"revisionName": OTHER, "percent": 1}]},
    {"observed": [{"latestRevision": True, "percent": 100}]},
    {"desired": [{"revisionName": PRIOR, "percent": True}]},
    {"observed": [{"revisionName": PRIOR, "percent": 100.0}]},
    {"generation": 4, "seen": 3},
    {"generation": 3, "seen": 4},
    {"generation": True},
    {"ready": "False"},
    {"desired": []},
    {"observed": []},
])
def test_not_proven_rollback_refused(tmp_path, change):
    result = check(tmp_path, state(**change))
    assert result.returncode == 2
    assert "ROLLBACK_UNVERIFIED" in result.stderr
    assert "READBACK_OK" not in result.stdout


def rollback_function():
    text = WORKFLOW.read_text()
    start = "          rollback() {\n"
    end = "          rollback_on_unhandled_exit() {\n"
    assert text.count(start) == 1
    return textwrap.dedent(text[text.index(start):text.index(end)])


@pytest.mark.parametrize("kind,expected_ok,marker,updates", [
    ("baseline", True, "ROLLBACK_TRAFFIC_READBACK_OK", 1),
    ("already-restored", True, "ROLLBACK_ALREADY_RESTORED", 0),
    ("update-failed", False, "ROLLBACK_UNVERIFIED", 1),
    ("describe-failed", False, "ROLLBACK_UNVERIFIED", 0),
    ("wrong-revision", False, "ROLLBACK_UNVERIFIED", 0),
    ("reconciling", False, "ROLLBACK_UNVERIFIED", 1),
])
def test_actual_workflow_rollback_function(tmp_path, kind, expected_ok, marker, updates):
    # Two separate inert snapshots: a candidate initially owns 100%, then a
    # successful fake update restores the prior revision. The new ownership
    # guard must not be bypassed just to satisfy the old rollback test.
    candidate = [{"revisionName": OTHER, "percent": 100}]
    before = state(desired=candidate, observed=candidate)
    if kind == "already-restored":
        before = state()
    elif kind == "wrong-revision":
        foreign = [{"revisionName": "fixlist-standard150-worker-00102-foreign", "percent": 100}]
        before = state(desired=foreign, observed=foreign)
    after = state(seen=2 if kind == "reconciling" else 3)
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps(before))
    after_path.write_text(json.dumps(after))

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gcloud"
    stub.write_text("""#!/usr/bin/env python3
import os,sys
from pathlib import Path
args = ' '.join(sys.argv[1:])
marker = Path(os.environ['UPDATE_MARKER'])
if 'update-traffic' in args:
    with Path(os.environ['CALL_LOG']).open('a') as log:
        log.write('update\\n')
    if os.getenv('FAIL_KIND') == 'update-failed': sys.exit(19)
    marker.write_text('updated')
    sys.exit(0)
if 'services describe' in args:
    if os.getenv('FAIL_KIND') == 'describe-failed': sys.exit(23)
    snapshot = 'SERVICE_FIXTURE_AFTER' if marker.exists() else 'SERVICE_FIXTURE_BEFORE'
    print(Path(os.environ[snapshot]).read_text())
    sys.exit(0)
sys.exit(99)
""")
    stub.chmod(0o755)
    calls = tmp_path / "calls.txt"
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}",
               FAIL_KIND=kind,
               SERVICE_FIXTURE_BEFORE=str(before_path),
               SERVICE_FIXTURE_AFTER=str(after_path),
               UPDATE_MARKER=str(tmp_path / "updated"),
               CALL_LOG=str(calls),
               RUNNER_TEMP=str(tmp_path), REVISION=OTHER, ROLLBACK_REVISION=PRIOR,
               CLOUD_RUN_SERVICE="fixture", GCP_PROJECT="fixture", GCP_REGION="fixture")
    proc = subprocess.run(["bash", "-c", "set -euo pipefail\nrollback_attempted=0\n" +
                           rollback_function() + "\nrollback\n"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=8)
    assert (proc.returncode == 0) == expected_ok, proc.stderr
    assert marker in (proc.stdout + proc.stderr), (proc.stdout, proc.stderr)
    assert (calls.read_text().splitlines().count("update") if calls.exists() else 0) == updates
    assert ("ROLLBACK_UNVERIFIED" in proc.stderr) == (not expected_ok)
    if kind == "already-restored":
        assert "ROLLBACK_TRAFFIC_READBACK_OK" not in proc.stdout
