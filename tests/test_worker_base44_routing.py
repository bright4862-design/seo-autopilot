"""Offline falsifiers for release-critical worker/Base44 routing metadata."""
import json
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "scripts/check_worker_base44_routing.py"
REV = "fixlist-standard150-worker-00055-abc"
APP_ID = "6a498732ec779dfaaeab0e53"


def case(env, revision=REV):
    return {"metadata": {"name": revision}, "spec": {"containers": [{"env": env}]}}


def env(app=APP_ID, origin="https://base44.app"):
    return [{"name": "BASE44_APP_ID", "value": app}, {"name": "BASE44_API_URL", "value": origin}]


def run(doc, revision=REV):
    raw = doc if isinstance(doc, str) else json.dumps(doc)
    return subprocess.run(
        [sys.executable, str(CHECK), "--revision", revision],
        input=raw, text=True, capture_output=True, timeout=10,
    )


def test_exact_revision_and_pinned_route_pass():
    done = run(case(env()))
    assert done.returncode == 0, done.stderr
    assert "WORKER_BASE44_ROUTE_MATCH" in done.stdout


def test_wrong_app_id_refused():
    done = run(case(env(app="other-app")))
    assert done.returncode == 1
    assert "BASE44_APP_ID" in done.stderr and "MATCH" not in done.stdout


def test_wrong_origin_refused():
    assert run(case(env(origin="https://other.example"))).returncode == 1


def test_missing_and_duplicate_names_refused():
    for values in (
        env()[:1],
        env() + [env()[0]],
        env() + [{"name": "BASE44_API_URL", "value": "https://other.example"}],
    ):
        assert run(case(values)).returncode == 1


def test_secret_reference_cannot_stand_in_for_literal_route():
    values = [
        {"name": "BASE44_APP_ID", "valueFrom": {"secretKeyRef": {"name": "x"}}},
        env()[1],
    ]
    assert run(case(values)).returncode == 1


def test_revision_confusion_and_missing_container_refused():
    assert run(case(env()), revision="fixlist-standard150-worker-00099-foreign").returncode == 1
    assert run({"metadata": {"name": REV}, "spec": {"containers": []}}).returncode == 1


def test_duplicate_json_members_refused():
    raw = json.dumps(case(env())).replace('"metadata": {', '"metadata": {}, "metadata": {', 1)
    assert run(raw).returncode == 1


def test_parser_errors_refused_without_echoing_env():
    done = run('{"metadata":')
    assert done.returncode == 1
    assert "secret" not in done.stderr


def test_post_deploy_probe_targets_ready_revision_not_only_service_template():
    script = (Path(__file__).resolve().parents[1] / "scripts/post_deploy_verify.sh").read_text()
    assert 'gcloud run revisions describe "$REV"' in script
    assert 'check_worker_base44_routing.py" --revision "$REV"' in script
    assert script.index('REV=$(jqq') < script.index('gcloud run revisions describe "$REV"')
    assert script.index('gcloud run revisions describe "$REV"') < script.index('=== 3. Runtime configuration ===')
