"""Owner-only paired access diagnostics; never invokes durable/customer routes.

All cloud operations are reads or creation/execution/deletion of nonce-owned jobs.
No service, traffic, queue, admission, IAM, secret or scanner mutation is permitted.
"""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import tempfile
import time

PROJECT = "seo-autopilot-501517"
REGION = "europe-west1"
SERVICE = "fixlist-standard150-worker"
RUNTIME_SA = f"{SERVICE}@{PROJECT}.iam.gserviceaccount.com"
NETWORK = "fixlist-scanner-egress"
SUBNET = "fixlist-scanner-egress-euw1"
IMAGE_REPO = f"{REGION}-docker.pkg.dev/{PROJECT}/cloud-run-source-deploy/{SERVICE}"
TARGETS = ("winamax", "ratp", "viator", "klook", "fever", "ironwood", "funbooker")
ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED_ENV = {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "ssl_cert_file", "ssl_cert_dir",
                   "requests_ca_bundle", "curl_ca_bundle"}


class CloudCommandError(RuntimeError):
    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__(json.dumps(evidence, sort_keys=True))


def gcloud(*args):
    operation = " ".join(args[:2] if args[0] == "logging" else args[:3])
    try:
        result = subprocess.run(["gcloud", *args, f"--project={PROJECT}", "--format=json",
                                 *([] if args[0] == "logging" else [f"--region={REGION}"])],
                                check=True, capture_output=True, text=True,
                                timeout=330 if args[:3] == ("run", "jobs", "execute") else 30 if args[0] == "logging" else 60)
    except subprocess.CalledProcessError as exc:
        category = next((code for code in (
            "ALREADY_EXISTS", "PERMISSION_DENIED", "UNAUTHENTICATED", "INVALID_ARGUMENT", "NOT_FOUND",
            "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED", "UNAVAILABLE", "FAILED_PRECONDITION"
        ) if re.search(r"\b" + code + r"\b", exc.stderr or "")), "unclassified_cloud_error")
        raise CloudCommandError({"operation": operation, "category": category}) from None
    except subprocess.TimeoutExpired:
        raise CloudCommandError({"operation": operation, "category": "command_timeout"}) from None
    try:
        return json.loads(result.stdout or "{}")
    except (TypeError, ValueError):
        raise CloudCommandError({"operation": operation, "category": "invalid_json"}) from None


def require_exact_main(source):
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "--no-tags", "origin",
                        "+refs/heads/main:refs/remotes/origin/main", "--quiet"],
                       check=True, capture_output=True, text=True, timeout=60)
        subprocess.run(["bash", "-c",
                        'source "$1/scripts/lib/release-source-guard.sh"; fixlist_require_exact_main "$1" "$2" "$2"',
                        "comparison-source", str(ROOT), source],
                       check=True, capture_output=True, text=True, timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError("exact_current_clean_main_required") from None


def public_ipv4(value):
    try:
        address = ipaddress.ip_address(value)
        if address.version != 4 or not address.is_global or address.is_multicast or address.is_reserved or str(address) != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("public_ipv4_required") from None
    return value


def verify_infra():
    # Do not inherit resource-name overrides from a human shell or workflow.
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIXLIST_EGRESS_")}
    env.update(GCP_PROJECT=PROJECT, GCP_REGION=REGION)
    try:
        result = subprocess.run(["bash", str(ROOT / "scripts/verify-fixlist-static-egress-canary.sh")],
                                env=env, check=True, capture_output=True, text=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError("infrastructure_verification_failed") from None
    rows = result.stdout.splitlines()
    ips = [line.removeprefix("STATIC_EGRESS_IP=") for line in rows if line.startswith("STATIC_EGRESS_IP=")]
    if rows.count("STATIC_EGRESS_CANARY_READY=1") != 1 or len(ips) != 1:
        raise ValueError("infrastructure_verification_incomplete")
    return public_ipv4(ips[0])


def _resource(value, kind, name):
    path = f"projects/{PROJECT}/" + ("global/" if kind == "networks" else f"regions/{REGION}/") + f"{kind}/{name}"
    return value in (name, path, "https://www.googleapis.com/compute/v1/" + path)


def _network(annotations, profile):
    if annotations.get("run.googleapis.com/vpc-access-connector") or annotations.get("run.googleapis.com/execution-environment") == "gen1":
        raise ValueError("unsupported_network_runtime")
    raw = annotations.get("run.googleapis.com/network-interfaces")
    if profile == "default":
        if raw or annotations.get("run.googleapis.com/vpc-access-egress"):
            raise ValueError("default_network_must_be_unattached")
        return
    try:
        interfaces = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("static_network_missing") from None
    if not isinstance(interfaces, list) or len(interfaces) != 1:
        raise ValueError("single_static_interface_required")
    item = interfaces[0]
    if not isinstance(item, dict) or set(item) != {"network", "subnetwork"}:
        raise ValueError("untagged_static_interface_required")
    if not _resource(item["network"], "networks", NETWORK) or not _resource(item["subnetwork"], "subnetworks", SUBNET):
        raise ValueError("static_network_identity_mismatch")
    if annotations.get("run.googleapis.com/vpc-access-egress") != "all-traffic":
        raise ValueError("all_traffic_required")


def _env(container):
    values = {}
    for item in container.get("env", []):
        name = item.get("name", "")
        if not name or name in values or name.lower() in UNSUPPORTED_ENV:
            raise ValueError("unsafe_or_duplicate_environment")
        values[name] = item.get("value")
    return values


def _traffic(service, revision):
    values = {}
    for section in ("spec", "status"):
        rows = service.get(section, {}).get("traffic", [])
        if not isinstance(rows, list) or not rows:
            raise ValueError("resolved_explicit_traffic_required")
        total = 0
        for row in rows:
            percent = row.get("percent", 0)
            if type(percent) is not int or not 0 <= percent <= 100 or row.get("latestRevision") or not row.get("revisionName"):
                raise ValueError("resolved_explicit_traffic_required")
            if row["revisionName"] == revision and (percent or row.get("tag")):
                raise ValueError("candidate_must_remain_zero_traffic")
            total += percent
        if total != 100:
            raise ValueError("complete_traffic_required")
        values[section] = rows
    return values


def validate_candidate(service, revision, iam, expected_revision, source):
    meta, spec, status = (revision.get(k, {}) for k in ("metadata", "spec", "status"))
    if service.get("metadata", {}).get("name") != SERVICE or meta.get("name") != expected_revision or meta.get("labels", {}).get("serving.knative.dev/service") != SERVICE:
        raise ValueError("candidate_identity_mismatch")
    if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])):
        raise ValueError("candidate_not_ready")
    _traffic(service, expected_revision)
    if service.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/invoker-iam-disabled", "false") != "false":
        raise ValueError("invoker_iam_required")
    if any(member in ("allUsers", "allAuthenticatedUsers") for binding in iam.get("bindings", []) for member in binding.get("members", [])):
        raise ValueError("public_service_binding_refused")
    containers = spec.get("containers", [])
    if len(containers) != 1 or spec.get("volumes") or containers[0].get("volumeMounts"):
        raise ValueError("single_container_without_volumes_required")
    if spec.get("serviceAccountName") != RUNTIME_SA or spec.get("containerConcurrency") != 1 or spec.get("timeoutSeconds") != 480:
        raise ValueError("candidate_runtime_mismatch")
    env = _env(containers[0])
    if env.get("FIXLIST_WORKER_SOURCE_SHA") != source or env.get("FIXLIST_EGRESS_MODE") != "static-canary" or env.get("GROK_PROXY_ENABLED") != "false":
        raise ValueError("candidate_source_or_mode_mismatch")
    _network(meta.get("annotations", {}), "static")
    raw = containers[0].get("image", "")
    base = raw.split("@", 1)[0].split(":", 1)[0]
    digest = status.get("imageDigest", "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        image = base + "@" + digest
    else:
        image = digest
    if not re.fullmatch(re.escape(IMAGE_REPO) + r"@sha256:[0-9a-f]{64}", image) or base != IMAGE_REPO or ("@" in raw and raw != image):
        raise ValueError("immutable_candidate_image_required")
    return image


def job_plan(profile, target, revision, source, image, ip, nonce, probe_source):
    if profile not in ("default", "static") or target not in TARGETS:
        raise ValueError("allowlisted_profile_and_target_required")
    encoded = base64.b64encode(probe_source.encode()).decode()
    flags = {
        "--image": image, "--service-account": RUNTIME_SA,
        "--tasks": "1", "--parallelism": "1", "--max-retries": "0", "--task-timeout": "210s",
        "--cpu": "1", "--memory": "1Gi", "--command": ["python"],
        "--args": ["-c", f"import base64; exec(compile(base64.b64decode('{encoded}'), 'static_egress_comparison_probe.py', 'exec'))"],
        "--labels": {"purpose": "fixlist-static-egress-comparison", "comparison-id": nonce},
        "--set-env-vars": {
            "FIXLIST_COMPARISON_TARGET": target, "FIXLIST_COMPARISON_PROFILE": profile,
            "FIXLIST_COMPARISON_EXPECTED_IP": ip, "FIXLIST_COMPARISON_SOURCE_SHA": source,
            "FIXLIST_COMPARISON_REVISION": revision, "FIXLIST_COMPARISON_IMAGE": image,
            "GROK_PROXY_ENABLED": "false",
        },
    }
    if profile == "static":
        flags.update({"--network": NETWORK, "--subnet": SUBNET, "--vpc-egress": "all-traffic"})
    return flags


def validate_job(actual, job, flags):
    meta = actual.get("metadata", {})
    if meta.get("name") != job or any(meta.get("labels", {}).get(k) != v for k, v in flags["--labels"].items()):
        raise ValueError("job_ownership_mismatch")
    template = actual.get("spec", {}).get("template", {})
    job_spec = template.get("spec", {})
    task = job_spec.get("template", {}).get("spec", {})
    if job_spec.get("taskCount") != 1 or job_spec.get("parallelism") != 1 or task.get("maxRetries") != 0 or task.get("timeoutSeconds") != "210":
        # Cloud Run v1 commonly serializes this IntOrString field as a string.
        if not (job_spec.get("taskCount") == 1 and job_spec.get("parallelism") == 1 and task.get("maxRetries") == 0 and task.get("timeoutSeconds") == 210):
            raise ValueError("job_limits_mismatch")
    containers = task.get("containers", [])
    if task.get("serviceAccountName") != RUNTIME_SA or task.get("volumes") or len(containers) != 1:
        raise ValueError("job_runtime_mismatch")
    container = containers[0]
    if any(container.get(k) != flags[f"--{k}"] for k in ("image", "command", "args")) or container.get("volumeMounts"):
        raise ValueError("job_container_mismatch")
    if _env(container) != flags["--set-env-vars"] or any("valueFrom" in item for item in container.get("env", [])):
        raise ValueError("job_environment_mismatch")
    limits = container.get("resources", {}).get("limits", {})
    if limits.get("cpu") not in ("1", "1000m") or limits.get("memory") not in ("1Gi", "1024Mi"):
        raise ValueError("job_resources_mismatch")
    _network(template.get("metadata", {}).get("annotations", {}), flags["--set-env-vars"]["FIXLIST_COMPARISON_PROFILE"])


# Explicit evidence allowlist. Never publish raw log rows, URLs, headers or errors.
COUNT_FIELDS = {"pages_crawled", "usable_html_pages", "access_limited_pages", "robots_blocked_pages", "transport_failure_pages", "http_403_pages", "http_429_pages"}
BOOL_FIELDS = {"static_ip_verified", "scan_deadline_reached", "authoritative_scan", "worker_process", "robots_unknown_seen", "robots_disallowed_seen", "scan_completed", "pressure_seen"}
STRING_FIELDS = {"diagnostic", "event", "target", "profile", "source_sha", "revision", "image", "observed_ip", "expected_ip", "classification", "robots_status", "failure_code"}


def validate_observation(payload, profile, target, revision, source, image, ip):
    allowed = COUNT_FIELDS | BOOL_FIELDS | STRING_FIELDS | {"robots_status_code", "elapsed_ms", "http_hops", "guard_refusals"}
    if not isinstance(payload, dict) or set(payload) != allowed:
        raise ValueError("observation_schema_mismatch")
    identities = {"diagnostic": "static_egress_comparison_v1", "event": "complete", "target": target,
                  "profile": profile, "source_sha": source, "revision": revision, "image": image, "expected_ip": ip,
                  "authoritative_scan": False, "worker_process": False}
    if any(payload.get(k) != v for k, v in identities.items()):
        raise ValueError("observation_identity_mismatch")
    for key in BOOL_FIELDS:
        if type(payload[key]) is not bool:
            raise ValueError("observation_boolean_required")
    for key in COUNT_FIELDS | {"elapsed_ms", "http_hops", "guard_refusals"}:
        limit = 210000 if key == "elapsed_ms" else 200 if key in {"http_hops", "guard_refusals"} else 150
        if type(payload[key]) is not int or not 0 <= payload[key] <= limit:
            raise ValueError("observation_count_out_of_bounds")
    if type(payload["robots_status_code"]) is not int or not 0 <= payload["robots_status_code"] <= 599:
        raise ValueError("observation_status_invalid")
    if payload["classification"] not in {"usable_html", "access_limited", "robots_blocked", "robots_unknown", "transport_failure", "inconclusive"} or payload["robots_status"] not in {"available", "missing", "unavailable", "access_limited", "not_checked"}:
        raise ValueError("observation_classification_invalid")
    if payload["failure_code"] not in {"", "ip_probe_failed", "source_ip_mismatch", "scanner_failed", "scanner_timeout", "probe_timeout", "request_budget_exhausted"}:
        raise ValueError("observation_failure_invalid")
    if payload["failure_code"]:
        raise ValueError("observation_probe_failed")
    public_ipv4(payload["observed_ip"])
    if profile == "static" and (payload["observed_ip"] != ip or payload["static_ip_verified"] is not True):
        raise ValueError("static_source_ip_not_verified")
    if profile == "default" and payload["static_ip_verified"] is not False:
        raise ValueError("default_must_not_claim_static_proof")
    if payload["usable_html_pages"] > payload["pages_crawled"] or payload["classification"] == "usable_html" and not payload["usable_html_pages"]:
        raise ValueError("observation_evidence_inconsistent")
    return payload


def _failure(exc):
    if isinstance(exc, CloudCommandError):
        return exc.evidence
    # ValueError messages originate only from fixed internal refusal codes.
    return {"category": str(exc) if type(exc) is ValueError and re.fullmatch(r"[a-z_]+", str(exc)) else "internal_diagnostic_error"}


def _read_candidate(revision, source):
    service = gcloud("run", "services", "describe", SERVICE)
    rev = gcloud("run", "revisions", "describe", revision)
    iam = gcloud("run", "services", "get-iam-policy", SERVICE)
    image = validate_candidate(service, rev, iam, revision, source)
    # Ready is validated on every read. Its transition timestamps may change
    # without changing the immutable candidate or its runtime configuration.
    meta = rev.get("metadata", {})
    identity = {"uid": meta.get("uid"), "generation": meta.get("generation"),
                "spec": rev.get("spec"), "image": image,
                "network": {key: meta.get("annotations", {}).get(key) for key in (
                    "run.googleapis.com/network-interfaces", "run.googleapis.com/vpc-access-egress",
                    "run.googleapis.com/vpc-access-connector", "run.googleapis.com/execution-environment")}}
    policy = {"etag": iam.get("etag"), "bindings": sorted(
        json.dumps(binding, sort_keys=True) for binding in iam.get("bindings", []))}
    return image, _traffic(service, revision), identity, policy


def _stable(expected, revision, source):
    require_exact_main(source)
    if _read_candidate(revision, source) != expected:
        raise ValueError("candidate_or_traffic_changed")


def _cleanup(job, flags):
    validate_job(gcloud("run", "jobs", "describe", job), job, flags)
    gcloud("run", "jobs", "delete", job, "--quiet")
    remaining = gcloud("run", "jobs", "list", f"--filter=metadata.name={job}")
    if remaining != []:
        raise ValueError("job_cleanup_not_verified")


def _observations(job, execution, flags, revision, source, image, ip, target, profile):
    query = (f'resource.type="cloud_run_job" AND resource.labels.project_id="{PROJECT}" AND '
             f'resource.labels.location="{REGION}" AND resource.labels.job_name="{job}" AND '
             f'labels."run.googleapis.com/execution_name"="{execution}" AND '
             'jsonPayload.diagnostic="static_egress_comparison_v1" AND jsonPayload.event="complete"')
    deadline = time.monotonic() + 120
    for attempt in range(12):
        logs = gcloud("logging", "read", query, "--limit=100", "--order=asc")
        if not isinstance(logs, list):
            raise ValueError("log_response_invalid")
        rows = []
        for row in logs:
            payload = row.get("jsonPayload", {})
            if payload.get("diagnostic") != "static_egress_comparison_v1" or payload.get("event") != "complete":
                continue
            resource = row.get("resource", {})
            labels = resource.get("labels", {})
            if resource.get("type") != "cloud_run_job" or labels.get("project_id") != PROJECT or labels.get("location") != REGION or labels.get("job_name") != job or row.get("labels", {}).get("run.googleapis.com/execution_name") != execution:
                raise ValueError("log_execution_identity_mismatch")
            rows.append(validate_observation(payload, profile, target, revision, source, image, ip))
        if len(rows) > 1:
            raise ValueError("duplicate_completion_evidence")
        if rows:
            return rows[0]
        if attempt < 11 and time.monotonic() + 10 < deadline:
            time.sleep(10)  # Log ingestion only; never rerun the job or website.
        else:
            break
    raise ValueError("completion_evidence_missing")


def execute(revision, source, target, confirm, run_id, attempt, output):
    if not re.fullmatch(r"fixlist-standard150-worker-[a-z0-9-]+", revision) or len(revision) > 63:
        raise ValueError("invalid_revision")
    if not re.fullmatch(r"[0-9a-f]{40}", source) or target not in TARGETS or confirm != f"STATIC-EGRESS-COMPARE:{target}:{revision}:{source}":
        raise ValueError("exact_target_revision_source_confirmation_required")
    if not re.fullmatch(r"[0-9]{1,20}", run_id) or not re.fullmatch(r"[0-9]{1,4}", attempt):
        raise ValueError("numeric_workflow_identity_required")
    jobs = {profile: f"fixlist-egress-compare-{run_id}-{attempt}-{target}-{profile}" for profile in ("default", "static")}
    if any(len(job) > 63 for job in jobs.values()):
        raise ValueError("job_name_too_long")
    require_exact_main(source)
    ip = verify_infra()
    snapshot = _read_candidate(revision, source)
    image = snapshot[0]
    evidence = {"diagnostic": "static_egress_comparison_pair_v1", "target": target, "source_sha": source,
                "candidate_revision": revision, "candidate_image": image, "expected_static_ip": ip,
                "service_policy_public_binding_absent": True, "pair_completed": False,
                "authoritative_scan": False, "profiles": {}}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for profile, job in jobs.items():
            _stable(snapshot, revision, source)
            flags = job_plan(profile, target, revision, source, image, ip, secrets.token_hex(16),
                             (ROOT / "scripts/static_egress_comparison_probe.py").read_text())
            row = {"job": job, "job_deleted": False}
            evidence["profiles"][profile] = row
            created = False
            first = None
            try:
                with tempfile.TemporaryDirectory(prefix="fixlist-compare-") as tmp:
                    flags_path = Path(tmp) / "flags.json"
                    flags_path.write_text(json.dumps(flags))
                    try:
                        gcloud("run", "jobs", "create", job, f"--flags-file={flags_path}", "--quiet")
                        created = True
                    except CloudCommandError as exc:
                        if exc.evidence.get("category") != "ALREADY_EXISTS":
                            # A timed-out create may have succeeded. Only nonce+spec
                            # ownership permits cleanup, never adopt or execute it.
                            try:
                                validate_job(gcloud("run", "jobs", "describe", job), job, flags)
                                created = True
                            except Exception:
                                pass
                        raise
                validate_job(gcloud("run", "jobs", "describe", job), job, flags)
                _stable(snapshot, revision, source)
                execution = gcloud("run", "jobs", "execute", job, "--wait")
                name = execution.get("metadata", {}).get("name", "")
                if not re.fullmatch(re.escape(job) + r"-[a-z0-9]+", name):
                    raise ValueError("execution_identity_mismatch")
                status = execution.get("status", {})
                if not any(c.get("type") == "Completed" and c.get("status") == "True" for c in status.get("conditions", [])) or int(status.get("succeededCount", 0)) != 1 or int(status.get("failedCount", 0)) != 0:
                    raise ValueError("execution_not_successful")
                row["execution"] = name
                row["observation"] = _observations(job, name, flags, revision, source, image, ip, target, profile)
            except Exception as exc:
                first = exc
                row["failure"] = _failure(exc)
            finally:
                if created:
                    try:
                        _cleanup(job, flags)
                        row["job_deleted"] = True
                    except Exception as exc:
                        row["cleanup_failure"] = _failure(exc)
                        if first is None:
                            first = exc
                try:
                    _stable(snapshot, revision, source)
                    row["candidate_and_traffic_unchanged"] = True
                except Exception as exc:
                    row["stability_failure"] = _failure(exc)
                    if first is None:
                        first = exc
                if first is not None:
                    raise first
        a, b = (evidence["profiles"][p]["observation"] for p in ("default", "static"))
        incomplete = any(not row["scan_completed"] or row["scan_deadline_reached"] or row["robots_unknown_seen"]
                         or row["pressure_seen"] or row["guard_refusals"] for row in (a, b))
        if a["observed_ip"] == b["observed_ip"] or incomplete:
            verdict = "inconclusive"
        elif not a["usable_html_pages"] and b["usable_html_pages"]:
            verdict = "static_observed_usable_html_gain"
        elif a["usable_html_pages"] and not b["usable_html_pages"]:
            verdict = "static_observed_usable_html_loss"
        elif a["usable_html_pages"] and b["usable_html_pages"]:
            verdict = "both_observed_usable_html"
        elif a["classification"] == b["classification"]:
            verdict = "same_access_classification"
        else:
            verdict = "inconclusive"
        evidence.update(pair_completed=True, comparison=verdict)
    except Exception as exc:
        evidence["failure"] = _failure(exc)
        raise
    finally:
        output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    def interrupted(_signum, _frame):
        raise ValueError("diagnostic_interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("revision", "source-sha", "target", "confirm", "run-id", "attempt", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.revision, args.source_sha, args.target, args.confirm, args.run_id, args.attempt, Path(args.output))
        print(json.dumps({"event": "comparison_pair_complete", "target": result["target"], "comparison": result["comparison"]}))
    except Exception as exc:
        print(json.dumps({"event": "comparison_pair_failed", **_failure(exc)}))
        raise SystemExit(1)
