#!/usr/bin/env python3
"""Read the fixed FixList owner-canary GCP resources into a private observation.

Requires an existing authorized gcloud session and permission to mint an
identity token for the fixed worker invoker. Only an explicitly named,
existing stage task is read. This command does not run a task or a scan.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from assert_tagged_zero_traffic_worker import verify_tagged_zero_traffic
from staged_candidate_cloudbuild import cohort_sha256, digest_for, environment, source_tag
from staged_queue_guard import (
    INVOKER_SA, OWNER_RE, PROJECT, REGION, REVISION_RE, SHA_RE, STAGE_QUEUE,
    STAGE_QUEUE_PATH, WORKER_SA, WORKSPACE_BUCKET, traffic_entries,
)
from verify_gateway_deployment import VerificationError as GatewayVerificationError, verify_runtime_health
from verify_staged_scan_infra import validate_binding, validate_bucket, validate_queue, validate_task
from verify_staged_worker_base44_runtime import matches_observation

ROOT = Path(__file__).resolve().parent.parent
WORKER = "fixlist-standard150-worker"
GATEWAY = "fixlist-dispatch-gateway"
GATEWAY_SA = f"fixlist-base44-dispatcher@{PROJECT}.iam.gserviceaccount.com"
QUEUE_ROOT = f"projects/{PROJECT}/locations/{REGION}/queues/"
ENTRY_PATH = QUEUE_ROOT + "fixlist-standard150"
DRAIN_PATH = QUEUE_ROOT + "fixlist-standard150-drain"
SCHEMA = "staged_scan_gcp_observations_v1"
LIMIT_BYTES = 1_048_576
TIMEOUT_SECONDS = 20
OBSERVATION_TTL = timedelta(minutes=5)
RUN_SCOPE = (f"--project={PROJECT}", f"--region={REGION}")
TASK_SCOPE = (f"--project={PROJECT}", f"--location={REGION}")


class ObservationError(ValueError):
    """A stable diagnostic that can be printed without raw command output."""


def require(condition, code):
    if not condition:
        raise ObservationError(code)


def checked_command(args, error):
    env = {**os.environ, "CLOUDSDK_CORE_LOG_HTTP": "false", "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true"}
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=TIMEOUT_SECONDS, check=True)
    except (OSError, subprocess.SubprocessError):
        raise ObservationError(error) from None
    require(len(result.stdout) <= LIMIT_BYTES, error)
    return result.stdout


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def parse_object(raw, code):
    try:
        document = json.loads(raw)
    except (UnicodeError, ValueError):
        raise ObservationError(code) from None
    require(isinstance(document, dict), code)
    return document


class Gcloud:
    def __init__(self):
        self.executable = shutil.which("gcloud") or str(Path.home() / "google-cloud-sdk/bin/gcloud")

    def read(self, *args):
        document = checked_command([self.executable, *args, "--quiet", "--format=json"], "gcp_read_failed")
        return parse_object(document, "gcp_read_invalid")

    def health(self, url, *, audience=None):
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        if audience is not None:
            token = checked_command([
                self.executable, "auth", "print-identity-token", f"--project={PROJECT}", "--quiet",
                f"--impersonate-service-account={INVOKER_SA}", f"--audiences={audience}", "--include-email",
            ], "worker_probe_auth_unavailable").strip()
            require(re.fullmatch(rb"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token), "worker_probe_auth_invalid")
            headers["Authorization"] = "Bearer " + token.decode("ascii")
        # Service and route are validated by collect before the token is minted.
        # Avoid redirects and proxy configuration moving a bearer to another host.
        opener = build_opener(ProxyHandler({}), NoRedirects())
        try:
            with opener.open(Request(url, headers=headers), timeout=TIMEOUT_SECONDS) as response:
                require(response.status == 200, "runtime_probe_bad_status")
                raw = response.read(LIMIT_BYTES + 1)
        except (OSError, HTTPException):
            raise ObservationError("runtime_probe_unavailable") from None
        require(len(raw) <= LIMIT_BYTES, "runtime_probe_too_large")
        return parse_object(raw, "runtime_probe_invalid")


def release_contract(source, fingerprint):
    """Read the reviewed fingerprint and gateway version from the named local commit."""
    recorded = parse_object(checked_command(
        ["git", "show", f"{source}:data/beta-crawler-revision.json"], "release_source_unavailable",
    ), "release_contract_invalid")
    require(recorded.get("fingerprint") == fingerprint and isinstance(recorded.get("component_versions"), dict),
            "release_fingerprint_mismatch")
    gateway = checked_command(["git", "show", f"{source}:dispatch-gateway/main.py"], "release_source_unavailable")
    match = re.search(rb'^GATEWAY_CONTRACT_VERSION\s*=\s*"([a-z0-9_]+)"', gateway, re.M)
    require(match, "gateway_contract_unavailable")
    return recorded["component_versions"], match[1].decode("ascii")


def canonical_service(document, service):
    require(document["metadata"]["name"] == service, "service_readback_mismatch")
    origin = document["status"]["url"]
    require(isinstance(origin, str) and re.fullmatch(
        rf"https://{service}-[a-z0-9-]+(?:\.a)?\.run\.app", origin,
    ) and "---" not in origin, "service_origin_invalid")
    traffic = traffic_entries(document)
    tags = [row["tag"] for row in traffic if row.get("tag")]
    require(all(isinstance(tag, str) for tag in tags) and len(tags) == len(set(tags))
            and sum(row.get("percent", 0) for row in traffic) == 100, "service_traffic_invalid")
    rows = []
    for row in traffic:
        name = row["revisionName"]
        require(isinstance(name, str) and re.fullmatch(rf"{service}-[a-z0-9-]+", name)
                and len(name) <= 63, "service_traffic_revision_invalid")
        exported = {"revisionName": name, "percent": row.get("percent", 0)}
        if "tag" in row:
            tag = row["tag"]
            require(isinstance(tag, str) and re.fullmatch(r"[a-z0-9-]{1,63}", tag)
                    and row.get("url") == origin.replace("https://", f"https://{tag}---", 1),
                    "service_tag_origin_invalid")
            exported.update(tag=tag, url=row["url"])
        rows.append(exported)
    rows.sort(key=lambda row: (row["revisionName"], row.get("tag", ""), row["percent"]))
    return {"status": {"url": origin, "traffic": rows}}


def exact_revision(raw, revision, service_account, expected, must_be_empty=()):
    spec, status = raw["spec"], raw["status"]
    require(raw["metadata"]["name"] == revision and spec["serviceAccountName"] == service_account
            and len(spec["containers"]) == 1, "revision_readback_mismatch")
    conditions = [row for row in status["conditions"] if row["type"] == "Ready"]
    require(len(conditions) == 1 and conditions[0]["status"] == "True", "revision_not_ready")
    digest = status["imageDigest"]
    require(isinstance(digest, str) and re.fullmatch(r"[a-z0-9._/-]+@sha256:[a-f0-9]{64}", digest),
            "revision_image_digest_invalid")
    relevant = [row for row in spec["containers"][0]["env"] if row["name"] in expected or row["name"] in must_be_empty]
    fields = {row["name"]: row["value"] for row in relevant}
    require(len(fields) == len(relevant) and all(fields.get(name) == value for name, value in expected.items())
            and all(fields.get(name, "") == "" for name in must_be_empty), "revision_configuration_mismatch")
    return {
        "metadata": {"name": revision},
        "spec": {"serviceAccountName": service_account,
                 "containers": [{"env": [{"name": name, "value": value} for name, value in sorted(fields.items())]}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}], "imageDigest": digest},
    }


def selected_policy(raw, role):
    require(not any(member in {"allUsers", "allAuthenticatedUsers"}
                    for binding in raw.get("bindings", []) for member in binding["members"]), "iam_public_binding")
    validate_binding(raw, role, WORKER_SA)
    # Retain just the observed, unconditional binding of this one principal.
    return {"bindings": [{"role": role, "members": [f"serviceAccount:{WORKER_SA}"]}]}


def collect_infra(client, target, audience, task_id):
    bucket = f"gs://{WORKSPACE_BUCKET}"
    bucket_row = client.read("storage", "buckets", "describe", bucket, f"--project={PROJECT}")
    require(bucket_row.get("name") == WORKSPACE_BUCKET, "workspace_bucket_identity_mismatch")
    bucket_policy = client.read("storage", "buckets", "get-iam-policy", bucket, f"--project={PROJECT}")
    validate_bucket(bucket_row, bucket_policy, WORKER_SA)
    queue = client.read("tasks", "queues", "describe", STAGE_QUEUE, *TASK_SCOPE)
    validate_queue(queue, STAGE_QUEUE_PATH, 40, expected_state="RUNNING")
    queue_policy = client.read("tasks", "queues", "get-iam-policy", STAGE_QUEUE, *TASK_SCOPE)
    invoker_policy = client.read("iam", "service-accounts", "get-iam-policy", INVOKER_SA, f"--project={PROJECT}")
    task = None
    if task_id is not None:
        raw = client.read("tasks", "describe", task_id, f"--queue={STAGE_QUEUE}", "--response-view=basic", *TASK_SCOPE)
        require(raw.get("name") == STAGE_QUEUE_PATH + "/tasks/" + task_id, "stage_task_identity_mismatch")
        validate_task(raw, target, INVOKER_SA, audience)
        request = raw["httpRequest"]
        task = {"name": raw["name"], "dispatchDeadline": raw["dispatchDeadline"],
                "httpRequest": {"url": request["url"], "httpMethod": request["httpMethod"],
                                "oidcToken": {key: request["oidcToken"][key] for key in ("serviceAccountEmail", "audience")}}}
    return {
        "bucket": {"name": bucket_row["name"], "uniform_bucket_level_access": True,
                   "public_access_prevention": "enforced",
                   "lifecycle_config": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30}}]}},
        "bucket_policy": selected_policy(bucket_policy, "roles/storage.objectUser"),
        "queue": {"name": queue["name"], "state": queue["state"],
                  "rateLimits": {"maxConcurrentDispatches": queue["rateLimits"]["maxConcurrentDispatches"]},
                  "retryConfig": {key: queue["retryConfig"][key] for key in (
                      "maxAttempts", "minBackoff", "maxBackoff", "maxDoublings", "maxRetryDuration")}},
        "queue_policy": selected_policy(queue_policy, "roles/cloudtasks.enqueuer"),
        "invoker_policy": selected_policy(invoker_policy, "roles/iam.serviceAccountUser"),
        "invoker_service_account": INVOKER_SA, "task": task,
    }


def collect(args, client, now=lambda: datetime.now(timezone.utc)):
    source, fingerprint, owner = args.source_sha, args.fingerprint, args.owner_id
    require(SHA_RE.fullmatch(source) and re.fullmatch(r"[a-f0-9]{16}", fingerprint) and OWNER_RE.fullmatch(owner),
            "expected_identity_invalid")
    require(REVISION_RE.fullmatch(args.worker_revision) and re.fullmatch(
        rf"{GATEWAY}-g{source[:8]}-[0-9]{{14}}-[0-9a-f]{{6}}", args.gateway_revision,
    ), "expected_revision_invalid")
    task_id = args.task_name.removeprefix(STAGE_QUEUE_PATH + "/tasks/") if args.task_name is not None else None
    require(task_id is None or re.fullmatch(r"[A-Za-z0-9_-]{1,500}", task_id), "stage_task_name_invalid")
    components, gateway_version = release_contract(source, fingerprint)
    started_at = now()

    def service_status(name):
        return canonical_service(client.read("run", "services", "describe", name, *RUN_SCOPE), name)

    worker_service, gateway_service = service_status(WORKER), service_status(GATEWAY)
    worker_origin, gateway_origin = (row["status"]["url"] for row in (worker_service, gateway_service))
    canary = verify_tagged_zero_traffic(worker_service, args.worker_revision,
                                        "canary-" + args.worker_revision.removeprefix(WORKER + "-"))
    reviewed = environment(source, PROJECT, REGION, WORKSPACE_BUCKET, STAGE_QUEUE_PATH, worker_origin)
    target = reviewed["SCAN_STAGE_TARGET_URL"]
    tags = [row for row in worker_service["status"]["traffic"] if row.get("tag") == source_tag(source)]
    require(tags == [{"revisionName": args.worker_revision, "percent": 0, "tag": source_tag(source), "url": target}],
            "worker_stage_tag_mismatch")
    traffic = gateway_service["status"]["traffic"]
    require(sum(row["percent"] for row in traffic if row["revisionName"] == args.gateway_revision) == 100,
            "gateway_traffic_mismatch")
    worker_env = {
        **reviewed, "SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": owner,
        "FIXLIST_WORKER_SOURCE_SHA": source, "FIXLIST_STAGED_CONFIG_SHA256": digest_for(source, reviewed),
        "TASKS_INVOKER_SERVICE_ACCOUNT": INVOKER_SA,
    }
    gateway_env = {
        "FIXLIST_GATEWAY_SOURCE_SHA": source, "SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": owner,
        "SCAN_CANARY_WORKER_ORIGIN": canary, "SCAN_CANARY_OWNER_USER_IDS": owner,
        "SCAN_TASKS_QUEUE_PATH": ENTRY_PATH, "SCAN_DRAIN_QUEUE_PATH": DRAIN_PATH,
        "SCAN_WORKER_URL": worker_origin + "/scan-job", "TASKS_INVOKER_SERVICE_ACCOUNT": INVOKER_SA,
    }
    worker = exact_revision(client.read("run", "revisions", "describe", args.worker_revision, *RUN_SCOPE),
                            args.worker_revision, WORKER_SA, worker_env, ("SCAN_PIPELINE_OWNER_IDS",))
    gateway = exact_revision(client.read("run", "revisions", "describe", args.gateway_revision, *RUN_SCOPE),
                             args.gateway_revision, GATEWAY_SA, gateway_env)
    worker_runtime = client.health(canary + "/revision", audience=worker_origin)
    require(worker_runtime.get("source_sha") == source and worker_runtime.get("fingerprint") == fingerprint
            and worker_runtime.get("component_versions") == components, "worker_runtime_mismatch")
    base44_runtime = client.health(canary + "/staged/base44-runtime", audience=worker_origin)
    require(matches_observation(base44_runtime, source_sha=source, revision=args.worker_revision)
            and base44_runtime["release_fingerprint"] == fingerprint, "worker_base44_runtime_mismatch")
    health = client.health(gateway_origin + "/health")
    require(health.get("ok") is True and type(health.get("canary_owner_count")) is int
            and type(health.get("staged_owner_count")) is int, "gateway_runtime_invalid")
    try:
        verify_runtime_health(health, args.gateway_revision, source, gateway_version, ENTRY_PATH, DRAIN_PATH,
                              worker_origin, canary, 1, "staged", owner, cohort_sha256(owner), 1)
    except GatewayVerificationError:
        raise ObservationError("gateway_runtime_mismatch") from None
    infra = collect_infra(client, target, worker_origin, task_id)
    require(service_status(WORKER) == worker_service and service_status(GATEWAY) == gateway_service,
            "cloud_run_changed_during_collection")
    expires_at = started_at + OBSERVATION_TTL
    require(now() < expires_at, "observation_expired_during_collection")
    times = {"observed_at": started_at.isoformat(), "expires_at": expires_at.isoformat()}
    return {
        "schema_version": SCHEMA, "source_sha": source, "release_fingerprint": fingerprint, **times,
        "worker": {**times, "revision": worker, "service": worker_service, "probe_url": canary,
                   "runtime": {"source_sha": worker_runtime["source_sha"], "fingerprint": worker_runtime["fingerprint"]},
                   "base44_runtime": base44_runtime},
        "gateway": {**times, "revision": gateway, "service": gateway_service, "runtime": {
            key: health[key] for key in ("ok", "service", "contract_version", "source_sha", "revision", "queue",
                                        "drain_queue", "worker_origin", "canary_worker_origin", "canary_owner_count",
                                        "pipeline_mode", "staged_owner_count", "staged_owner_cohort_sha256")}},
        "infrastructure": {**times, **infra},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-sha", "fingerprint", "owner-id", "worker-revision", "gateway-revision"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--task-name", help="Existing task ID or full name on the fixed stage queue")
    parser.add_argument("--output", required=True, type=Path, help="New absolute path outside this checkout")
    args = parser.parse_args(argv)
    try:
        path = args.output
        require(path.is_absolute() and path.parent.resolve(strict=True) == path.parent
                and path.parent.is_dir() and not path.is_relative_to(ROOT)
                and not os.path.lexists(path), "observation_output_path_invalid")
        report = collect(args, Gcloud())
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
    except ObservationError as exc:
        print(f"STAGED_GCP_OBSERVATION_BLOCKED: {exc}", file=sys.stderr)
        return 1
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        print("STAGED_GCP_OBSERVATION_BLOCKED: cloud_contract_or_output_unavailable", file=sys.stderr)
        return 1
    print(f"STAGED_GCP_OBSERVATION_SAVED task_observed={str(bool(report['infrastructure']['task'])).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
