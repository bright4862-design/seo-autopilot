"""Protect the isolated job boundary: never mutate a production service or copy secrets."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / "scripts/ironwood_diagnostic_job.py"
    assert path.exists(), "The bounded diagnostic operation has not been implemented"
    spec = importlib.util.spec_from_file_location("ironwood_job", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


REV = "fixlist-standard150-worker-00086-qpm"
SHA = "b5bce85967d23ddc97654e613eab9644a539f480"
DIGEST = "europe-west1-docker.pkg.dev/seo-autopilot-501517/workers/scanner@sha256:" + "a" * 64


def revision():
    return {"metadata": {"name": REV, "labels": {"serving.knative.dev/service": "fixlist-standard150-worker"}, "annotations": {}},
            "status": {"imageDigest": DIGEST, "conditions": [{"type": "Ready", "status": "True"}]},
            "spec": {"serviceAccountName": "fixlist-standard150-runtime@seo-autopilot-501517.iam.gserviceaccount.com",
                     "containers": [{"image": "mutable:tag", "env": [{"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SHA}, {"name": "SIGNING_KEY", "valueFrom": {"secretKeyRef": {"name": "production-secret", "key": "1"}}}]}]}}


def service():
    return {"status": {"traffic": [{"revisionName": REV, "percent": 100}]}}


def test_job_uses_digest_and_bounded_task_without_production_secrets():
    flags, evidence = module().job_plan(service(), revision(), REV, "print('diagnostic')")
    assert flags["--image"] == DIGEST
    assert flags["--tasks"] == flags["--parallelism"] == "1"
    assert flags["--max-retries"] == "0"
    assert flags["--task-timeout"] == "180s"
    assert flags["--command"] == ["python"]
    assert "SIGNING_KEY" not in json.dumps(flags)
    assert "production-secret" not in json.dumps(flags)
    assert "--set-secrets" not in flags and "--set-env-vars" not in flags
    assert evidence["source_ip_equivalence_verified"] is False
    assert evidence["worker_source_sha"] == SHA


@pytest.mark.parametrize("change", ["split", "wrong_revision", "unready", "mutable", "sidecar", "proxy", "direct_vpc", "gen1", "foreign_service", "missing_source"])
def test_ambiguous_or_unsupported_profile_is_refused_before_job_creation(change):
    s, r = service(), revision()
    if change == "split": s["status"]["traffic"][0]["percent"] = 50
    if change == "wrong_revision": r["metadata"]["name"] = "other"
    if change == "unready": r["status"]["conditions"] = []
    if change == "mutable": r["status"]["imageDigest"] = "mutable:tag"
    if change == "sidecar": r["spec"]["containers"].append({"image": "sidecar"})
    if change == "proxy": r["spec"]["containers"][0]["env"].append({"name": "HTTPS_PROXY", "value": "secret"})
    if change == "direct_vpc": r["metadata"]["annotations"]["run.googleapis.com/network-interfaces"] = "[]"
    if change == "gen1": r["metadata"]["annotations"]["run.googleapis.com/execution-environment"] = "gen1"
    if change == "foreign_service": r["metadata"]["labels"]["serving.knative.dev/service"] = "other"
    if change == "missing_source": r["spec"]["containers"][0]["env"] = []
    with pytest.raises(ValueError): module().job_plan(s, r, REV, "print('diagnostic')")


def test_supported_connector_configuration_is_preserved():
    r = revision()
    r["metadata"]["annotations"] = {"run.googleapis.com/vpc-access-connector": "projects/seo-autopilot-501517/locations/europe-west1/connectors/scanner", "run.googleapis.com/vpc-access-egress": "all-traffic"}
    flags, _ = module().job_plan(service(), r, REV, "print('diagnostic')")
    assert flags["--vpc-connector"].endswith("/connectors/scanner")
    assert flags["--vpc-egress"] == "all-traffic"


def test_wrong_confirmation_refuses_even_read_commands(tmp_path, monkeypatch):
    m = module()
    calls = []
    monkeypatch.setattr(m, "gcloud", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError): m.execute(REV, "b" * 40, "wrong", "123", "1", tmp_path)
    assert calls == []


def test_permission_failure_on_create_does_not_attempt_execute_or_iam_changes(tmp_path, monkeypatch):
    m = module()
    calls = []
    def cloud(*args):
        calls.append(args)
        if args[:3] == ("run", "services", "describe"): return service()
        if args[:3] == ("run", "revisions", "describe"): return revision()
        if args[:3] == ("run", "jobs", "create"): raise RuntimeError("PERMISSION_DENIED")
        raise AssertionError(args)
    monkeypatch.setattr(m, "gcloud", cloud)
    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        m.execute(REV, "b" * 40, f"ironwood-diagnostic:{REV}:{'b' * 40}", "123", "1", tmp_path)
    assert [c[:3] for c in calls] == [("run", "services", "describe"), ("run", "revisions", "describe"), ("run", "jobs", "create")]


def test_success_executes_once_and_deletes_only_its_unique_job(tmp_path, monkeypatch):
    m = module()
    calls = []
    job = "fixlist-ironwood-diag-123-1"
    def cloud(*args):
        calls.append(args)
        if args[:3] == ("run", "services", "describe"): return service()
        if args[:3] == ("run", "revisions", "describe"): return revision()
        if args[:3] == ("run", "jobs", "create"): return {}
        if args[:3] == ("run", "jobs", "execute"): return {"metadata": {"name": job + "-abc"}}
        if args[:2] == ("logging", "read"): return [{"jsonPayload": {"diagnostic": "ironwood_v1", "event": "complete", "requests": 7}}]
        if args[:3] == ("run", "jobs", "delete"): return {}
        raise AssertionError(args)
    monkeypatch.setattr(m, "gcloud", cloud)
    m.execute(REV, "b" * 40, f"ironwood-diagnostic:{REV}:{'b' * 40}", "123", "1", tmp_path)
    assert sum(c[:3] == ("run", "jobs", "execute") for c in calls) == 1
    assert calls[-1] == ("run", "jobs", "delete", job, "--quiet")
    assert json.loads((tmp_path / "result.json").read_text())["job_deleted"] is True


def test_failed_execution_still_cleans_only_the_job_it_created(tmp_path, monkeypatch):
    m, calls = module(), []
    def cloud(*args):
        calls.append(args)
        if args[:3] == ("run", "services", "describe"): return service()
        if args[:3] == ("run", "revisions", "describe"): return revision()
        if args[:3] == ("run", "jobs", "create"): return {}
        if args[:3] == ("run", "jobs", "execute"): raise RuntimeError("execution failed")
        if args == ("run", "jobs", "delete", "fixlist-ironwood-diag-123-1", "--quiet"): return {}
        raise AssertionError(args)
    monkeypatch.setattr(m, "gcloud", cloud)
    with pytest.raises(RuntimeError, match="execution failed"):
        m.execute(REV, "b" * 40, f"ironwood-diagnostic:{REV}:{'b' * 40}", "123", "1", tmp_path)
    assert calls[-1] == ("run", "jobs", "delete", "fixlist-ironwood-diag-123-1", "--quiet")


def test_gcloud_boundary_has_no_shell_and_scopes_every_call(monkeypatch):
    m, calls = module(), []
    class Result:
        stdout = "{}"
    def process(args, **kwargs):
        calls.append((args, kwargs))
        return Result()
    monkeypatch.setattr(m.subprocess, "run", process)
    m.gcloud("run", "services", "describe", "fixlist-standard150-worker")
    m.gcloud("logging", "read", 'resource.type="cloud_run_job"')
    assert calls[0][0][-1] == "--region=europe-west1"
    assert "--project=seo-autopilot-501517" in calls[0][0]
    assert not any(x.startswith("--region=") for x in calls[1][0])
    assert all(not kwargs.get("shell") and kwargs["check"] and kwargs["timeout"] == 300 for _, kwargs in calls)
