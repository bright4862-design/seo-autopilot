"""Offline controls for selecting which worker a read-only route check certifies."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve_serving_worker_revision.py"
spec = importlib.util.spec_from_file_location("serving_worker", SCRIPT)
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)
SERVICE = "fixlist-standard150-worker"
OLD = SERVICE + "-00011-v7m"
SERVING = SERVICE + "-00012-ab1"
LATEST = SERVICE + "-00013-bc2"


def service(traffic=None, ready="True", observed=7):
    return {
        "metadata": {"generation": 7},
        "status": {
            "observedGeneration": observed,
            "conditions": [{"type": "Ready", "status": ready}],
            "latestReadyRevisionName": LATEST,
            "traffic": traffic if traffic is not None else [
                {"revisionName": SERVING, "percent": 100},
                {"revisionName": LATEST, "percent": 0, "tag": "candidate"},
            ],
        },
    }


def test_default_and_latest_ready_can_both_differ_from_serving():
    # Baseline main workflow default points to OLD and legacy empty-input fallback
    # points to latestReady (LATEST). Neither proves the real SERVING revision.
    assert OLD != LATEST != SERVING
    assert resolver.resolve(service(), service_name=SERVICE) == SERVING


def test_single_100_serving_positive_control():
    assert resolver.resolve(service([{"revisionName": SERVING, "percent": 100}]), service_name=SERVICE) == SERVING


@pytest.mark.parametrize("traffic,error", [
    ([{"revisionName": SERVING, "percent": 99}, {"revisionName": LATEST, "percent": 1}], "single_100"),
    ([{"revisionName": LATEST, "percent": 0, "tag": "staged"}], "single_100"),
    ([], "traffic_missing"),
    ([{"percent": 100}], "revision_invalid"),
    ([{"revisionName": SERVING, "percent": "100"}], "percent_invalid"),
    ([{"revisionName": SERVING, "percent": 100}, {"revisionName": SERVING, "percent": 100}], "single_100"),
])
def test_split_zero_only_missing_identity_or_bad_percent_refused(traffic, error):
    with pytest.raises(resolver.ServingRevisionUnavailable, match=error):
        resolver.resolve(service(traffic), service_name=SERVICE)


@pytest.mark.parametrize("mutation,error", [
    ({"observedGeneration": 6}, "reconciliation_not_observed"),
    ({"conditions": [{"type": "Ready", "status": "False"}]}, "service_not_ready"),
    ({"conditions": [{"type": "Ready", "status": "True"}, {"type": "Ready", "status": "False"}]}, "service_not_ready"),
])
def test_stale_or_conflicting_service_status_refused(mutation, error):
    obj = service()
    obj["status"].update(mutation)
    with pytest.raises(resolver.ServingRevisionUnavailable, match=error):
        resolver.resolve(obj, service_name=SERVICE)


def test_cli_stdout_is_exact_revision_or_nothing():
    cmd = [sys.executable, str(SCRIPT), SERVICE]
    ok = subprocess.run(cmd, input=json.dumps(service()), text=True, capture_output=True)
    assert ok.returncode == 0 and ok.stdout == SERVING + "\n" and not ok.stderr
    failed = subprocess.run(cmd, input=json.dumps(service(observed=3)), text=True, capture_output=True)
    assert failed.returncode == 2 and not failed.stdout and "INDETERMINATE" in failed.stderr


def test_workflow_routes_readonly_check_to_resolved_100_percent_target_when_present():
    workflow = ROOT / ".github" / "workflows" / "fixlist-cloud-operator.yml"
    if not workflow.exists():
        pytest.skip("workflow file only exists in the full repository")
    content = workflow.read_text()
    block = content.split("- name: Run allowlisted worker operation", 1)[1].split(
        "- name: Build isolated Standard 150 worker candidate", 1
    )[0]
    assert 'if [[ "$OPERATION" == "verify-worker-routes" ]]' in block
    assert 'export TARGET_REVISION="$route_revision"' in block
    assert 'after_revision="$(get_serving_revision)"' in block
    assert '[[ "$after_revision" == "$route_revision" ]]' in block
