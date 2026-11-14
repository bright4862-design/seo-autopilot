"""Offline fixtures for the GCP prerequisite observation boundary."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import collect_staged_gcp_observations as observed


SOURCE = "1" * 40
FINGERPRINT = "2" * 16
OWNER = "owner_01"
WORKER_REV = "fixlist-standard150-worker-00106-8cf"
GATEWAY_REV = "fixlist-dispatch-gateway-g11111111-20261114200400-120abc"
WORKER_URL = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
GATEWAY_URL = "https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app"
CANARY = "https://canary-00106-8cf---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
STAGE = "https://staged-111111111111---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"
STAMP = datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc)
PRIVATE = "test-data-must-never-appear"
COMPONENTS = {"synthetic_component": "test-v1"}
GATEWAY_VERSION = "test_gateway_v1"


def args(tmp_path, task=None):
    return SimpleNamespace(source_sha=SOURCE, fingerprint=FINGERPRINT, owner_id=OWNER,
                           worker_revision=WORKER_REV, gateway_revision=GATEWAY_REV,
                           task_name=task, output=tmp_path / "report.json")


class FixtureCloud:
    def __init__(self):
        self.calls = []
        self.worker = {
            "metadata": {"name": observed.WORKER}, "status": {"url": WORKER_URL, "traffic": [
                {"revisionName": "fixlist-standard150-worker-00097-lvl", "percent": 100},
                {"revisionName": WORKER_REV, "tag": "canary-00106-8cf", "url": CANARY},
                {"revisionName": WORKER_REV, "tag": "staged-111111111111", "url": STAGE},
            ]},
        }
        self.gateway = {
            "metadata": {"name": observed.GATEWAY}, "status": {"url": GATEWAY_URL, "traffic": [
                {"revisionName": GATEWAY_REV, "percent": 100},
            ]},
        }
        worker_env = {
            "SCAN_WORKSPACE_BUCKET": observed.WORKSPACE_BUCKET, "SCAN_TASKS_PROJECT": observed.PROJECT,
            "SCAN_TASKS_LOCATION": observed.REGION, "SCAN_STAGE_QUEUE": observed.STAGE_QUEUE,
            "SCAN_STAGE_TASKS_QUEUE_PATH": observed.STAGE_QUEUE_PATH, "SCAN_STAGE_TARGET_URL": STAGE,
            "SCAN_STAGE_TOKEN_AUDIENCE": WORKER_URL, "SCAN_PIPELINE_MODE": "monolith", "SCAN_STAGED_OWNER_IDS": "",
        }
        config = json.dumps({"source_sha": SOURCE, "environment": worker_env}, sort_keys=True, separators=(",", ":"))
        worker_env.update(SCAN_PIPELINE_MODE="staged", SCAN_STAGED_OWNER_IDS=OWNER,
                          FIXLIST_WORKER_SOURCE_SHA=SOURCE,
                          FIXLIST_STAGED_CONFIG_SHA256=hashlib.sha256(config.encode()).hexdigest(),
                          TASKS_INVOKER_SERVICE_ACCOUNT=observed.INVOKER_SA)
        gateway_env = {
            "FIXLIST_GATEWAY_SOURCE_SHA": SOURCE, "SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": OWNER,
            "SCAN_CANARY_WORKER_ORIGIN": CANARY, "SCAN_CANARY_OWNER_USER_IDS": OWNER,
            "SCAN_TASKS_QUEUE_PATH": observed.ENTRY_PATH, "SCAN_DRAIN_QUEUE_PATH": observed.DRAIN_PATH,
            "SCAN_WORKER_URL": WORKER_URL + "/scan-job", "TASKS_INVOKER_SERVICE_ACCOUNT": observed.INVOKER_SA,
        }

        def revision(name, service, env):
            return {
                "metadata": {"name": name, "unrelated": PRIVATE},
                "spec": {"serviceAccountName": service, "containers": [{"env": [
                    *[{"name": name, "value": value} for name, value in env.items()],
                    {"name": "IGNORED_SECRET", "value": PRIVATE},
                ]}]},
                "status": {"conditions": [{"type": "Ready", "status": "True", "message": PRIVATE}],
                           "imageDigest": "europe-west1-docker.pkg.dev/project/worker@sha256:" + "a" * 64},
            }

        self.worker_revision = revision(WORKER_REV, observed.WORKER_SA, worker_env)
        self.gateway_revision = revision(GATEWAY_REV, observed.GATEWAY_SA, gateway_env)
        self.queue = {"name": observed.STAGE_QUEUE_PATH, "state": "RUNNING",
                      "rateLimits": {"maxConcurrentDispatches": 40}, "retryConfig": {
                          "maxAttempts": 10, "minBackoff": "10s", "maxBackoff": "120s",
                          "maxDoublings": 4, "maxRetryDuration": "1800s"}}
        self.bucket = {
            "name": observed.WORKSPACE_BUCKET,
            "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}, "publicAccessPrevention": "enforced"},
            "lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30}}]},
        }
        self.task = {
            "name": observed.STAGE_QUEUE_PATH + "/tasks/stage-job-1", "dispatchDeadline": "480s",
            "httpRequest": {"url": STAGE + "/scan-batch", "httpMethod": "POST", "body": PRIVATE,
                            "headers": {"X-Secret": PRIVATE}, "oidcToken": {
                                "serviceAccountEmail": observed.INVOKER_SA, "audience": WORKER_URL}},
        }
        self.worker_health = {"source_sha": SOURCE, "fingerprint": FINGERPRINT,
                              "component_versions": COMPONENTS, "ignored": PRIVATE}
        self.gateway_health = {
            "ok": True, "service": observed.GATEWAY, "revision": GATEWAY_REV, "source_sha": SOURCE,
            "contract_version": GATEWAY_VERSION, "queue": observed.ENTRY_PATH, "drain_queue": observed.DRAIN_PATH,
            "worker_origin": WORKER_URL, "canary_worker_origin": CANARY, "canary_owner_count": 1,
            "pipeline_mode": "staged", "staged_owner_count": 1,
            "staged_owner_cohort_sha256": hashlib.sha256(b'["owner_01"]').hexdigest(), "ignored": PRIVATE,
        }

    def read(self, *command):
        self.calls.append(command)
        action, resource = command[:3], command[3]
        if action == ("run", "services", "describe"):
            return {observed.WORKER: self.worker, observed.GATEWAY: self.gateway}[resource]
        if action == ("run", "revisions", "describe"):
            return {WORKER_REV: self.worker_revision, GATEWAY_REV: self.gateway_revision}[resource]
        if action == ("tasks", "queues", "describe"):
            return self.queue
        if action == ("storage", "buckets", "describe"):
            return self.bucket
        if command[:2] == ("tasks", "describe"):
            assert "--response-view=basic" in command
            return self.task
        role = {
            ("storage", "buckets", "get-iam-policy"): "roles/storage.objectUser",
            ("tasks", "queues", "get-iam-policy"): "roles/cloudtasks.enqueuer",
            ("iam", "service-accounts", "get-iam-policy"): "roles/iam.serviceAccountUser",
        }[action]
        return {"bindings": [{"role": role, "members": [f"serviceAccount:{observed.WORKER_SA}", "user:" + PRIVATE]}]}

    def health(self, url, *, audience=None):
        self.calls.append(("health", url, audience))
        if url == CANARY + "/revision":
            assert audience == WORKER_URL
            return self.worker_health
        assert url == GATEWAY_URL + "/health" and audience is None
        return self.gateway_health


@pytest.fixture(autouse=True)
def freeze_contract(monkeypatch):
    monkeypatch.setattr(observed, "release_contract", lambda *_: (COMPONENTS, GATEWAY_VERSION))


def test_projection_is_packet_compatible_and_excludes_unrelated_data(tmp_path):
    cloud = FixtureCloud()
    receipt = observed.collect(args(tmp_path, cloud.task["name"]), cloud, now=lambda: STAMP)
    assert receipt["schema_version"] == "staged_scan_gcp_observations_v1"
    assert receipt["source_sha"] == SOURCE and receipt["release_fingerprint"] == FINGERPRINT
    assert receipt["worker"]["probe_url"] == CANARY
    assert receipt["worker"]["runtime"] == {"source_sha": SOURCE, "fingerprint": FINGERPRINT}
    assert receipt["gateway"]["runtime"]["revision"] == GATEWAY_REV
    assert receipt["infrastructure"]["task"]["httpRequest"] == {
        "url": STAGE + "/scan-batch", "httpMethod": "POST",
        "oidcToken": {"serviceAccountEmail": observed.INVOKER_SA, "audience": WORKER_URL},
    }
    assert receipt["infrastructure"]["bucket"]["lifecycle_config"]["rule"][0]["condition"] == {"age": 30}
    for part in (receipt, receipt["worker"], receipt["gateway"], receipt["infrastructure"]):
        assert part["observed_at"] == STAMP.isoformat()
        assert part["expires_at"] == (STAMP + timedelta(minutes=5)).isoformat()
    assert PRIVATE not in json.dumps(receipt)


def test_absent_task_is_null_and_queue_is_not_searched(tmp_path):
    cloud = FixtureCloud()
    receipt = observed.collect(args(tmp_path), cloud, now=lambda: STAMP)
    assert receipt["infrastructure"]["task"] is None
    assert not any(call[:2] == ("tasks", "describe") for call in cloud.calls)


@pytest.mark.parametrize("failure", ["route", "mode", "revision", "source", "owner", "queue", "task", "task_audience"])
def test_blocks_drift_before_emitting_an_observation(tmp_path, failure):
    cloud = FixtureCloud()
    if failure == "route":
        cloud.worker["status"]["traffic"][-1]["url"] = "https://unrelated.run.app"
    elif failure == "mode":
        cloud.gateway_health["pipeline_mode"] = "monolith"
    elif failure == "revision":
        cloud.gateway["status"]["traffic"][0]["revisionName"] += "-other"
    elif failure == "source":
        cloud.worker_health["source_sha"] = "0" * 40
    elif failure == "owner":
        for row in cloud.gateway_revision["spec"]["containers"][0]["env"]:
            if row["name"] == "SCAN_STAGED_OWNER_IDS":
                row["value"] = "another_owner"
    elif failure == "queue":
        cloud.queue["state"] = "PAUSED"
    elif failure == "task":
        cloud.task["name"] += "-other"
    else:
        cloud.task["httpRequest"]["oidcToken"]["audience"] = STAGE
    with pytest.raises(ValueError):
        observed.collect(args(tmp_path, "stage-job-1"), cloud, now=lambda: STAMP)
    if failure == "route":
        assert not any(call[0] == "health" for call in cloud.calls)


def test_service_traffic_is_reread_after_probes(tmp_path):
    cloud = FixtureCloud()
    original = cloud.health

    def moving_health(url, **kwargs):
        response = original(url, **kwargs)
        if url == GATEWAY_URL + "/health":
            cloud.gateway["status"]["traffic"][0]["revisionName"] += "-new"
        return response

    cloud.health = moving_health
    with pytest.raises(observed.ObservationError, match="cloud_run_changed_during_collection"):
        observed.collect(args(tmp_path), cloud, now=lambda: STAMP)


def test_cli_writes_new_private_file_and_never_overwrites(monkeypatch, tmp_path, capsys):
    cloud = FixtureCloud()
    monkeypatch.setattr(observed, "Gcloud", lambda: cloud)
    output = tmp_path.resolve() / "evidence.json"
    flags = ["--source-sha", SOURCE, "--fingerprint", FINGERPRINT, "--owner-id", OWNER,
             "--worker-revision", WORKER_REV, "--gateway-revision", GATEWAY_REV, "--output", str(output)]
    assert observed.main(flags) == 0
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "task_observed=false" in capsys.readouterr().out
    before = output.read_bytes()
    cloud.calls.clear()
    assert observed.main(flags) == 1
    assert not cloud.calls and output.read_bytes() == before


def test_command_failure_never_prints_child_output(monkeypatch, capsys):
    def fail(*_, **kwargs):
        assert kwargs["env"]["CLOUDSDK_CORE_LOG_HTTP"] == "false"
        raise subprocess.CalledProcessError(1, ["gcloud"], output=PRIVATE, stderr=PRIVATE)

    monkeypatch.setattr(observed.subprocess, "run", fail)
    with pytest.raises(observed.ObservationError, match="gcp_read_failed") as error:
        observed.Gcloud().read("tasks", "queues", "describe", observed.STAGE_QUEUE)
    assert PRIVATE not in str(error.value)
    assert PRIVATE not in repr(capsys.readouterr())
