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


@pytest.mark.parametrize("kind,expected_ok", [
    ("baseline", True), ("update-failed", False),
    ("describe-failed", False), ("wrong-revision", False),
    ("reconciling", False),
])
def test_actual_workflow_rollback_function(tmp_path, kind, expected_ok):
    f = tmp_path / "fixture.json"
    fixture = state()
    if kind == "wrong-revision":
        fixture["status"]["traffic"] = [{"revisionName": OTHER, "percent": 100}]
    if kind == "reconciling":
        fixture["status"]["observedGeneration"] = 2
    f.write_text(json.dumps(fixture))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gcloud"
    stub.write_text("""#!/usr/bin/env python3
import os,sys
args=' '.join(sys.argv[1:])
if 'update-traffic' in args and os.getenv('FAIL_KIND')=='update-failed': sys.exit(19)
if 'services describe' in args and os.getenv('FAIL_KIND')=='describe-failed': sys.exit(23)
if 'services describe' in args:
    print(open(os.environ['SERVICE_FIXTURE']).read())
    sys.exit(0)
if 'update-traffic' in args: sys.exit(0)
sys.exit(99)
""")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}",
               FAIL_KIND=kind, SERVICE_FIXTURE=str(f),
               RUNNER_TEMP=str(tmp_path), ROLLBACK_REVISION=PRIOR,
               CLOUD_RUN_SERVICE="fixture", GCP_PROJECT="fixture", GCP_REGION="fixture")
    proc = subprocess.run(["bash", "-c", "set -euo pipefail\nrollback_attempted=0\n" +
                           rollback_function() + "\nrollback\n"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=8)
    assert (proc.returncode == 0) == expected_ok, proc.stderr
    assert ("ROLLBACK_TRAFFIC_READBACK_OK" in proc.stdout) == expected_ok
    assert ("ROLLBACK_UNVERIFIED" in proc.stderr) == (not expected_ok)
