"""Protect candidate identity and the isolated comparison job boundary."""
import importlib.util
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHA = "ca94e93af02fc6eccd47ea79dffd374af8b9fdbb"
REV = "fixlist-standard150-worker-00098-kz5"
SERVING = "fixlist-standard150-worker-00097-lvl"
SERVICE = "fixlist-standard150-worker"
RUNTIME_SA = "fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"
REPOSITORY = "europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/fixlist-standard150-worker"
IMAGE = REPOSITORY + "@sha256:" + "a" * 64
IP = "34.52.147.10"
NETWORK = "fixlist-scanner-egress"
SUBNET = "fixlist-scanner-egress-euw1"
NONCE = "123-1"


def candidate():
    return {
        "metadata": {
            "name": REV,
            "labels": {"serving.knative.dev/service": SERVICE},
            "annotations": {
                "run.googleapis.com/execution-environment": "gen2",
                "run.googleapis.com/network-interfaces": json.dumps([
                    {"network": NETWORK, "subnetwork": SUBNET}
                ]),
                "run.googleapis.com/vpc-access-egress": "all-traffic",
            },
        },
        "status": {"imageDigest": IMAGE, "conditions": [{"type": "Ready", "status": "True"}]},
        "spec": {
            "serviceAccountName": RUNTIME_SA,
            "containerConcurrency": 1,
            "timeoutSeconds": 480,
            "containers": [{
                "image": REPOSITORY + ":" + SHA,
                "env": [
                    {"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SHA},
                    {"name": "FIXLIST_EGRESS_MODE", "value": "static-canary"},
                    {"name": "GROK_PROXY_ENABLED", "value": "false"},
                    {"name": "BASE44_API_URL", "value": "https://private.example/?token=NEVER_COPY"},
                    {"name": "SCAN_EVIDENCE_SIGNING_KEY", "valueFrom": {
                        "secretKeyRef": {"name": "NEVER_COPY_SECRET", "key": "1"}
                    }},
                ],
            }],
        },
    }


def service():
    return {
        "metadata": {"name": SERVICE, "annotations": {
            "run.googleapis.com/invoker-iam-disabled": "false"
        }},
        "spec": {"traffic": [{"revisionName": SERVING, "percent": 100}]},
        "status": {"traffic": [{"revisionName": SERVING, "percent": 100}]},
    }


def iam():
    return {"bindings": [{"role": "roles/run.invoker", "members": [
        "serviceAccount:fixlist-tasks-invoker@seo-autopilot-501517.iam.gserviceaccount.com"
    ]}]}


def env_value(revision, name, value):
    entries = revision["spec"]["containers"][0]["env"]
    entries[:] = [entry for entry in entries if entry["name"] != name]
    entries.append({"name": name, "value": value})


def planned_flags(profile="static"):
    return module().job_plan(profile, "ironwood", REV, SHA, IMAGE, IP, NONCE, "print('probe')")


def actual_job(flags, name="fixlist-egress-compare-123-1-static"):
    annotations = {"run.googleapis.com/execution-environment": "gen2"}
    if "--network" in flags:
        annotations.update({
            "run.googleapis.com/network-interfaces": json.dumps([{
                "network": flags["--network"], "subnetwork": flags["--subnet"]
            }]),
            "run.googleapis.com/vpc-access-egress": flags["--vpc-egress"],
        })
    env = flags.get("--set-env-vars", {})
    assert isinstance(env, dict), "Use structured flags-file env values, not delimiter-sensitive strings"
    return {
        "metadata": {"name": name, "labels": copy.deepcopy(flags["--labels"])},
        "spec": {"template": {
            "metadata": {"annotations": annotations},
            "spec": {
                "taskCount": int(flags["--tasks"]),
                "parallelism": int(flags["--parallelism"]),
                "template": {"spec": {
                    "serviceAccountName": flags["--service-account"],
                    "maxRetries": int(flags["--max-retries"]),
                    "timeoutSeconds": int(flags["--task-timeout"].removesuffix("s")),
                    "containers": [{
                        "image": flags["--image"], "command": flags["--command"], "args": flags["--args"],
                        "resources": {"limits": {"cpu": flags["--cpu"], "memory": flags["--memory"]}},
                        "env": [{"name": key, "value": value} for key, value in env.items()],
                    }],
                }},
            },
        }},
    }


def module():
    path = ROOT / "scripts/static_egress_comparison_job.py"
    assert path.exists(), "The static egress comparison orchestrator is missing"
    spec = importlib.util.spec_from_file_location("static_egress_comparison_job_test", path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_comparison_orchestrator_is_available():
    assert module()


def test_exact_zero_traffic_candidate_resolves_immutable_image_without_secrets():
    resolved = module().validate_candidate(service(), candidate(), iam(), REV, SHA)
    assert resolved == IMAGE


@pytest.mark.parametrize("digest_form", ["digest_only", "spec_immutable"])
def test_cloud_run_supported_digest_shapes_remain_immutable(digest_form):
    revision = candidate()
    if digest_form == "digest_only":
        revision["status"]["imageDigest"] = IMAGE.split("@", 1)[1]
    else:
        revision["spec"]["containers"][0]["image"] = IMAGE
    assert module().validate_candidate(service(), revision, iam(), REV, SHA) == IMAGE


@pytest.mark.parametrize("network,subnet", [
    ("projects/seo-autopilot-501517/global/networks/" + NETWORK,
     "projects/seo-autopilot-501517/regions/europe-west1/subnetworks/" + SUBNET),
    ("https://www.googleapis.com/compute/v1/projects/seo-autopilot-501517/global/networks/" + NETWORK,
     "https://www.googleapis.com/compute/v1/projects/seo-autopilot-501517/regions/europe-west1/subnetworks/" + SUBNET),
])
def test_fixed_canonical_network_references_are_supported(network, subnet):
    revision = candidate()
    revision["metadata"]["annotations"]["run.googleapis.com/network-interfaces"] = json.dumps([
        {"network": network, "subnetwork": subnet}
    ])
    assert module().validate_candidate(service(), revision, iam(), REV, SHA) == IMAGE


@pytest.mark.parametrize("change", [
    "wrong_service", "wrong_revision", "wrong_service_label", "unready", "sidecar", "volume",
    "foreign_runtime", "missing_runtime", "source_mismatch", "missing_source", "duplicate_source",
    "wrong_egress_mode", "grok_enabled", "connector", "gen1", "wrong_concurrency", "wrong_timeout",
    "missing_network", "extra_interface", "foreign_network", "foreign_subnet", "foreign_region",
    "network_tags", "private_only", "image_repository", "mutable_digest", "digest_conflict",
    "public_service", "iam_bypass",
])
def test_candidate_identity_and_runtime_mismatches_refuse(change):
    s, r, policy = service(), candidate(), iam()
    ann = r["metadata"]["annotations"]
    container = r["spec"]["containers"][0]
    if change == "wrong_service": s["metadata"]["name"] = "foreign-service"
    if change == "wrong_revision": r["metadata"]["name"] = SERVING
    if change == "wrong_service_label": r["metadata"]["labels"]["serving.knative.dev/service"] = "foreign-service"
    if change == "unready": r["status"]["conditions"] = [{"type": "Ready", "status": "False"}]
    if change == "sidecar": r["spec"]["containers"].append({"image": "foreign:latest"})
    if change == "volume": r["spec"]["volumes"] = [{"name": "private", "secret": {"secretName": "secret"}}]
    if change == "foreign_runtime": r["spec"]["serviceAccountName"] = "other@foreign.iam.gserviceaccount.com"
    if change == "missing_runtime": del r["spec"]["serviceAccountName"]
    if change == "source_mismatch": env_value(r, "FIXLIST_WORKER_SOURCE_SHA", "b" * 40)
    if change == "missing_source": container["env"] = [e for e in container["env"] if e["name"] != "FIXLIST_WORKER_SOURCE_SHA"]
    if change == "duplicate_source": container["env"].append({"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SHA})
    if change == "wrong_egress_mode": env_value(r, "FIXLIST_EGRESS_MODE", "none")
    if change == "grok_enabled": env_value(r, "GROK_PROXY_ENABLED", "true")
    if change == "connector": ann["run.googleapis.com/vpc-access-connector"] = "projects/seo-autopilot-501517/locations/europe-west1/connectors/other"
    if change == "gen1": ann["run.googleapis.com/execution-environment"] = "gen1"
    if change == "wrong_concurrency": r["spec"]["containerConcurrency"] = 2
    if change == "wrong_timeout": r["spec"]["timeoutSeconds"] = 600
    if change == "missing_network": del ann["run.googleapis.com/network-interfaces"]
    if change in {"extra_interface", "foreign_network", "foreign_subnet", "foreign_region", "network_tags"}:
        interfaces = [{"network": NETWORK, "subnetwork": SUBNET}]
        if change == "extra_interface": interfaces.append(copy.deepcopy(interfaces[0]))
        if change == "foreign_network": interfaces[0]["network"] = "projects/foreign-project/global/networks/" + NETWORK
        if change == "foreign_subnet": interfaces[0]["subnetwork"] = "projects/foreign-project/regions/europe-west1/subnetworks/" + SUBNET
        if change == "foreign_region": interfaces[0]["subnetwork"] = "projects/seo-autopilot-501517/regions/us-central1/subnetworks/" + SUBNET
        if change == "network_tags": interfaces[0]["tags"] = ["firewall-bypass"]
        ann["run.googleapis.com/network-interfaces"] = json.dumps(interfaces)
    if change == "private_only": ann["run.googleapis.com/vpc-access-egress"] = "private-ranges-only"
    if change == "image_repository":
        container["image"] = "foreign.example/scanner:latest"
        r["status"]["imageDigest"] = "foreign.example/scanner@sha256:" + "a" * 64
    if change == "mutable_digest": r["status"]["imageDigest"] = REPOSITORY + ":latest"
    if change == "digest_conflict": container["image"] = REPOSITORY + "@sha256:" + "b" * 64
    if change == "public_service": policy["bindings"].append({"role": "roles/run.invoker", "members": ["allUsers"]})
    if change == "iam_bypass": s["metadata"]["annotations"]["run.googleapis.com/invoker-iam-disabled"] = "true"
    with pytest.raises(ValueError):
        module().validate_candidate(s, r, policy, REV, SHA)


@pytest.mark.parametrize("name", ["HTTP_PROXY", "https_proxy", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_candidate_transport_environment_cannot_be_silently_omitted(name):
    revision = candidate()
    revision["spec"]["containers"][0]["env"].append({"name": name, "value": "private"})
    with pytest.raises(ValueError):
        module().validate_candidate(service(), revision, iam(), REV, SHA)


@pytest.mark.parametrize("section", ["spec", "status"])
@pytest.mark.parametrize("entry", [
    {"revisionName": REV, "percent": 1},
    {"revisionName": REV, "percent": -1},
    {"revisionName": REV, "percent": 0, "tag": "candidate"},
    {"latestRevision": True, "percent": 100},
    {"latestRevision": True, "percent": 0},
])
def test_candidate_live_pending_or_tagged_traffic_is_refused(section, entry):
    s = service()
    s[section]["traffic"].append(entry)
    with pytest.raises(ValueError):
        module().validate_candidate(s, candidate(), iam(), REV, SHA)


def test_paired_job_plans_use_same_bounded_probe_and_image_without_production_env():
    default, static = planned_flags("default"), planned_flags("static")
    for flags in (default, static):
        assert flags["--image"] == IMAGE
        assert flags["--service-account"] == RUNTIME_SA
        assert flags["--tasks"] == flags["--parallelism"] == "1"
        assert flags["--max-retries"] == "0"
        assert flags["--task-timeout"] == "210s"
        assert flags["--cpu"] == "1" and flags["--memory"] == "1Gi"
        assert flags["--command"] == ["python"]
        assert "--set-secrets" not in flags
        assert "NEVER_COPY" not in json.dumps(flags)
        assert flags["--set-env-vars"]["GROK_PROXY_ENABLED"] == "false"
        assert all(name.startswith("FIXLIST_COMPARISON_") or name == "GROK_PROXY_ENABLED" for name in flags["--set-env-vars"])
    assert default["--args"] == static["--args"]
    assert not any(name in default for name in ("--network", "--subnet", "--vpc-egress", "--vpc-connector"))
    assert static["--network"] == NETWORK and static["--subnet"] == SUBNET
    assert static["--vpc-egress"] == "all-traffic"
    default_env, static_env = copy.deepcopy(default["--set-env-vars"]), copy.deepcopy(static["--set-env-vars"])
    assert default_env.pop("FIXLIST_COMPARISON_PROFILE") == "default"
    assert static_env.pop("FIXLIST_COMPARISON_PROFILE") == "static"
    assert default_env == static_env


@pytest.mark.parametrize("profile", ["default", "static"])
def test_created_job_matches_exact_plan_before_execution(profile):
    flags = planned_flags(profile)
    actual = actual_job(flags)
    assert module().validate_job(actual, actual["metadata"]["name"], flags) is None


@pytest.mark.parametrize("change", ["name", "tasks", "parallelism", "timeout", "retries", "runtime", "image", "sidecar", "volume", "args", "cpu", "memory", "extra_env", "extra_secret", "egress", "connector", "network"])
def test_created_job_drift_is_refused_before_execution(change):
    flags = planned_flags()
    actual = actual_job(flags)
    execution = actual["spec"]["template"]
    task = execution["spec"]["template"]["spec"]
    container = task["containers"][0]
    ann = execution["metadata"]["annotations"]
    if change == "name": actual["metadata"]["name"] = "foreign-job"
    if change == "tasks": execution["spec"]["taskCount"] = 2
    if change == "parallelism": execution["spec"]["parallelism"] = 2
    if change == "timeout": task["timeoutSeconds"] = 480
    if change == "retries": task["maxRetries"] = 3
    if change == "runtime": task["serviceAccountName"] = "foreign@foreign.iam.gserviceaccount.com"
    if change == "image": container["image"] = REPOSITORY + ":latest"
    if change == "sidecar": task["containers"].append({"image": "foreign:latest"})
    if change == "volume": task["volumes"] = [{"name": "secret"}]
    if change == "args": container["args"] = ["-c", "print('different')"]
    if change == "cpu": container["resources"]["limits"]["cpu"] = "2"
    if change == "memory": container["resources"]["limits"]["memory"] = "2Gi"
    if change == "extra_env": container["env"].append({"name": "HTTPS_PROXY", "value": "private"})
    if change == "extra_secret": container["env"].append({"name": "SECRET", "valueFrom": {"secretKeyRef": {"name": "private", "key": "1"}}})
    if change == "egress": ann["run.googleapis.com/vpc-access-egress"] = "private-ranges-only"
    if change == "connector": ann["run.googleapis.com/vpc-access-connector"] = "foreign"
    if change == "network": ann["run.googleapis.com/network-interfaces"] = json.dumps([{"network": "foreign", "subnetwork": SUBNET}])
    with pytest.raises(ValueError):
        module().validate_job(actual, "fixlist-egress-compare-123-1-static", flags)


@pytest.mark.parametrize("change", ["revision", "source", "target", "confirm", "run_id", "attempt"])
def test_invalid_command_refuses_before_source_guard_infra_or_cloud(tmp_path, monkeypatch, change):
    m = module()
    calls = []
    for name in ("require_exact_main", "verify_infra", "gcloud"):
        monkeypatch.setattr(m, name, lambda *args, _name=name, **kwargs: calls.append((_name, args)))
    values = {"revision": REV, "source": SHA, "target": "ironwood",
              "confirm": f"STATIC-EGRESS-COMPARE:ironwood:{REV}:{SHA}", "run_id": "123", "attempt": "1"}
    values[change] = {"revision": "foreign-001", "source": "A" * 40, "target": "https://evil.example/?token=secret",
                      "confirm": "wrong", "run_id": "123;echo secret", "attempt": "1a"}[change]
    with pytest.raises(ValueError):
        m.execute(values["revision"], values["source"], values["target"], values["confirm"], values["run_id"], values["attempt"], tmp_path / "result.json")
    assert calls == []


def test_cloud_boundary_has_no_shell_and_scopes_project_region(monkeypatch):
    m, calls = module(), []
    class Result:
        stdout = "{}"
    def process(args, **kwargs):
        calls.append((args, kwargs))
        return Result()
    monkeypatch.setattr(m.subprocess, "run", process)
    m.gcloud("run", "jobs", "describe", "job")
    m.gcloud("logging", "read", 'resource.type="cloud_run_job"')
    assert all("--project=seo-autopilot-501517" in args for args, _ in calls)
    assert "--region=europe-west1" in calls[0][0]
    assert not any(arg.startswith("--region=") for arg in calls[1][0])
    assert all(not kwargs.get("shell") and kwargs["check"] and kwargs["timeout"] > 0 for _, kwargs in calls)


@pytest.mark.parametrize("timeout", [False, True])
def test_cloud_failures_never_publish_raw_output_tokens_or_urls(monkeypatch, timeout):
    m = module()
    def process(args, **kwargs):
        if timeout:
            raise m.subprocess.TimeoutExpired(args, kwargs["timeout"], output="Bearer SECRET", stderr="private")
        raise m.subprocess.CalledProcessError(1, args, stderr="PERMISSION_DENIED logging.logEntries.list Bearer SECRET https://private.example/?token=hidden")
    monkeypatch.setattr(m.subprocess, "run", process)
    with pytest.raises(m.CloudCommandError) as caught:
        m.gcloud("logging", "read", "private-filter")
    text = json.dumps(caught.value.evidence)
    assert all(secret not in text for secret in ("SECRET", "private", "hidden", "Bearer", "https://"))
    assert "logging" in text


def test_source_guard_force_refreshes_exact_main_ref_before_shared_guard(monkeypatch):
    m, calls = module(), []
    class Result:
        stdout = ""
    def process(args, **kwargs):
        calls.append((args, kwargs))
        return Result()
    monkeypatch.setattr(m.subprocess, "run", process)
    m.require_exact_main(SHA)
    assert len(calls) == 2
    fetch, guard = (call[0] for call in calls)
    assert fetch[:4] == ["git", "-C", str(ROOT), "fetch"]
    assert "+refs/heads/main:refs/remotes/origin/main" in fetch
    assert "origin" in fetch and "--no-tags" in fetch
    assert guard[:2] == ["bash", "-c"]
    assert "release-source-guard.sh" in guard[2] and "fixlist_require_exact_main" in guard[2]
    assert guard[-2:] == [str(ROOT), SHA]
    assert all(kwargs["check"] and kwargs["capture_output"] and not kwargs.get("shell") for _, kwargs in calls)


@pytest.mark.parametrize("failing_step", ["fetch", "guard"])
@pytest.mark.parametrize("timeout", [False, True])
def test_source_refresh_or_shared_guard_failure_is_sanitized_and_stops(monkeypatch, failing_step, timeout):
    m, calls = module(), []
    class Result:
        stdout = ""
    def process(args, **kwargs):
        calls.append(args)
        if args[0] == ("git" if failing_step == "fetch" else "bash"):
            if timeout:
                raise m.subprocess.TimeoutExpired(args, kwargs["timeout"], output="Bearer SECRET", stderr="https://private.example/?token=hidden")
            raise m.subprocess.CalledProcessError(1, args, stderr="Bearer SECRET https://private.example/?token=hidden")
        return Result()
    monkeypatch.setattr(m.subprocess, "run", process)
    with pytest.raises(ValueError, match="^exact_current_clean_main_required$") as caught:
        m.require_exact_main(SHA)
    assert "SECRET" not in str(caught.value) and "private" not in str(caught.value)
    assert len(calls) == (1 if failing_step == "fetch" else 2)


def observation(profile="static"):
    return {
        "diagnostic": "static_egress_comparison_v1", "event": "complete",
        "target": "ironwood", "profile": profile, "source_sha": SHA, "revision": REV,
        "image": IMAGE, "expected_ip": IP, "observed_ip": IP if profile == "static" else "8.8.8.8",
        "static_ip_verified": profile == "static", "classification": "usable_html",
        "robots_status": "available", "robots_status_code": 200,
        "pages_crawled": 1, "usable_html_pages": 1, "access_limited_pages": 0,
        "robots_blocked_pages": 0, "transport_failure_pages": 0, "http_403_pages": 0,
        "http_429_pages": 0, "elapsed_ms": 1000, "scan_deadline_reached": False,
        "authoritative_scan": False, "worker_process": False, "scan_completed": True,
        "robots_unknown_seen": False, "robots_disallowed_seen": False, "pressure_seen": False,
        "http_hops": 3, "guard_refusals": 0, "failure_code": "",
    }


@pytest.mark.parametrize("profile", ["default", "static"])
def test_strict_aggregate_observation_accepts_bound_identity(profile):
    row = observation(profile)
    assert module().validate_observation(row, profile, "ironwood", REV, SHA, IMAGE, IP) == row


OBSERVATION_NUMBER_LIMITS = {
    "pages_crawled": 150, "usable_html_pages": 150, "access_limited_pages": 150,
    "robots_blocked_pages": 150, "transport_failure_pages": 150, "http_403_pages": 150,
    "http_429_pages": 150, "robots_status_code": 599, "elapsed_ms": 210000,
    "http_hops": 200, "guard_refusals": 200,
}


def test_cloud_logging_integral_float_numbers_normalize_to_integer_evidence():
    row = observation()
    for field in OBSERVATION_NUMBER_LIMITS:
        row[field] = float(row[field])
    result = module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)
    assert all(type(result[field]) is int for field in OBSERVATION_NUMBER_LIMITS)
    assert result["pages_crawled"] == result["usable_html_pages"] == 1
    assert result["robots_status_code"] == 200 and result["elapsed_ms"] == 1000
    assert result["http_hops"] == 3 and result["guard_refusals"] == 0


@pytest.mark.parametrize("field", OBSERVATION_NUMBER_LIMITS)
@pytest.mark.parametrize("value", [1.25, float("nan"), float("inf"), -float("inf"), True, -1.0])
def test_cloud_logging_nonintegral_nonfinite_boolean_or_negative_numbers_refuse(field, value):
    row = observation()
    row[field] = value
    with pytest.raises(ValueError):
        module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)


@pytest.mark.parametrize("field,limit", OBSERVATION_NUMBER_LIMITS.items())
def test_cloud_logging_integral_floats_above_field_boundaries_refuse(field, limit):
    row = observation()
    row[field] = float(limit + 1)
    with pytest.raises(ValueError):
        module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)


@pytest.mark.parametrize("updates", [
    {"target": "winamax"}, {"profile": "default"}, {"source_sha": "b" * 40},
    {"revision": SERVING}, {"image": REPOSITORY + ":latest"}, {"expected_ip": "8.8.8.8"},
    {"observed_ip": "8.8.8.8"}, {"observed_ip": "127.0.0.1"}, {"static_ip_verified": False},
    {"static_ip_verified": 1}, {"authoritative_scan": True}, {"worker_process": True},
    {"pages_crawled": 151}, {"pages_crawled": -1}, {"pages_crawled": True},
    {"usable_html_pages": 2}, {"usable_html_pages": 0}, {"http_hops": 201},
    {"guard_refusals": 201}, {"elapsed_ms": 210001}, {"robots_status_code": 600},
    {"robots_status_code": True}, {"pressure_seen": "false"},
    {"classification": "http://private.example/?token=SECRET"},
    {"robots_status": "SECRET"}, {"failure_code": "Bearer SECRET"},
    {"raw_html": "SECRET"}, {"headers": {"Set-Cookie": "SECRET"}},
])
def test_observation_rejects_foreign_unbounded_or_sensitive_payloads(updates):
    row = observation()
    row.update(updates)
    with pytest.raises(ValueError):
        module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)


def test_observation_requires_every_schema_field():
    row = observation()
    del row["http_hops"]
    with pytest.raises(ValueError):
        module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)


def test_default_observation_cannot_claim_reserved_ip_proof():
    row = observation("default")
    row["static_ip_verified"] = True
    with pytest.raises(ValueError):
        module().validate_observation(row, "default", "ironwood", REV, SHA, IMAGE, IP)


@pytest.mark.parametrize("ip", ["224.0.0.1", "240.0.0.1"])
def test_multicast_and_reserved_addresses_are_not_public_source_ips(ip):
    with pytest.raises(ValueError, match="public_ipv4_required"):
        module().public_ipv4(ip)


@pytest.mark.parametrize("profile", ["default", "static"])
@pytest.mark.parametrize("ip", ["224.0.0.1", "240.0.0.1"])
def test_observation_refuses_multicast_and_reserved_source_ips(profile, ip):
    row = observation(profile)
    row["observed_ip"] = ip
    with pytest.raises(ValueError, match="public_ipv4_required"):
        module().validate_observation(row, profile, "ironwood", REV, SHA, IMAGE, IP)


def candidate_snapshot(monkeypatch):
    m = module()
    state = {"service": service(), "revision": candidate(), "iam": iam()}
    state["revision"]["metadata"].update(uid="stable-candidate-uid", generation=1)
    state["iam"]["etag"] = "stable-policy-etag"
    def cloud(*args):
        key = {
            ("run", "services", "describe"): "service",
            ("run", "revisions", "describe"): "revision",
            ("run", "services", "get-iam-policy"): "iam",
        }[args[:3]]
        return copy.deepcopy(state[key])
    monkeypatch.setattr(m, "gcloud", cloud)
    monkeypatch.setattr(m, "require_exact_main", lambda _source: None)
    return m, state, m._read_candidate(REV, SHA)


def test_candidate_snapshot_tolerates_ready_transition_timestamp_changes(monkeypatch):
    m, state, expected = candidate_snapshot(monkeypatch)
    condition = state["revision"]["status"]["conditions"][0]
    condition["lastTransitionTime"] = "2026-10-12T13:14:15Z"
    condition["lastUpdateTime"] = "2026-10-12T13:14:16Z"
    state["revision"]["status"]["observedGeneration"] = 1
    assert m._stable(expected, REV, SHA) is None


def test_ready_is_still_revalidated_when_condition_timestamps_are_ignored(monkeypatch):
    m, state, expected = candidate_snapshot(monkeypatch)
    state["revision"]["status"]["conditions"][0].update(status="False", lastTransitionTime="2026-10-12T13:14:15Z")
    with pytest.raises(ValueError, match="candidate_not_ready"):
        m._stable(expected, REV, SHA)


@pytest.mark.parametrize("change", ["uid", "generation", "spec", "image", "network_reference", "iam_etag", "iam_binding"])
def test_candidate_snapshot_refuses_identity_runtime_image_network_or_iam_drift(monkeypatch, change):
    m, state, expected = candidate_snapshot(monkeypatch)
    revision = state["revision"]
    if change == "uid": revision["metadata"]["uid"] = "another-candidate-uid"
    if change == "generation": revision["metadata"]["generation"] = 2
    if change == "spec": env_value(revision, "EXTRA_RUNTIME_SETTING", "changed")
    if change == "image":
        changed = REPOSITORY + "@sha256:" + "b" * 64
        revision["status"]["imageDigest"] = changed
        revision["spec"]["containers"][0]["image"] = changed
    if change == "network_reference":
        revision["metadata"]["annotations"]["run.googleapis.com/network-interfaces"] = json.dumps([{
            "network": "projects/seo-autopilot-501517/global/networks/" + NETWORK,
            "subnetwork": SUBNET,
        }])
    if change == "iam_etag": state["iam"]["etag"] = "another-policy-etag"
    if change == "iam_binding":
        state["iam"]["bindings"][0]["members"].append("serviceAccount:another-invoker@seo-autopilot-501517.iam.gserviceaccount.com")
    with pytest.raises(ValueError, match="candidate_or_traffic_changed"):
        m._stable(expected, REV, SHA)


@pytest.mark.parametrize("failure_code", [
    "ip_probe_failed", "source_ip_mismatch", "scanner_failed", "scanner_timeout",
    "probe_timeout", "request_budget_exhausted",
])
def test_completed_event_with_recognized_probe_failure_never_counts_as_success(failure_code):
    row = observation()
    row["failure_code"] = failure_code
    assert row["scan_completed"] is True and row["usable_html_pages"] == 1
    with pytest.raises(ValueError, match="observation_probe_failed"):
        module().validate_observation(row, "static", "ironwood", REV, SHA, IMAGE, IP)


class FakeCloud:
    """Exercise public execute with explicit read/create/execute/delete responses."""
    def __init__(self, module):
        self.module = module
        self.calls = []
        self.jobs = {}
        self.executions = []
        self.deleted = []
        self.fail_create = None
        self.fail_execute = False
        self.fail_logs = False
        self.fail_cleanup = False
        self.log_change = None
        self.execution_change = None
        self.job_change = None
        self.drift_after_execute = False
        self.drift_after_create = False
        self.same_default_ip = False
        self.empty_log_reads = 0
        self.observation_updates = {}
        self.delete_still_listed = False

    def __call__(self, *args):
        self.calls.append(args)
        operation = args[:3]
        if operation == ("run", "services", "describe"):
            value = service()
            if (self.drift_after_execute and self.executions or self.drift_after_create and
                    any(call[:3] == ("run", "jobs", "create") for call in self.calls)):
                for section in ("spec", "status"):
                    value[section]["traffic"] = [{"revisionName": "fixlist-standard150-worker-00096-zzz", "percent": 100}]
            return value
        if operation == ("run", "revisions", "describe"):
            return candidate()
        if operation == ("run", "services", "get-iam-policy"):
            return iam()
        if operation == ("run", "jobs", "create"):
            job = args[3]
            flags = json.loads(Path(next(arg.split("=", 1)[1] for arg in args if arg.startswith("--flags-file="))).read_text())
            if self.fail_create == "ALREADY_EXISTS":
                raise self.module.CloudCommandError({"operation": "run jobs create", "category": "ALREADY_EXISTS"})
            self.jobs[job] = flags
            if self.fail_create:
                raise self.module.CloudCommandError({"operation": "run jobs create", "category": self.fail_create})
            return {}
        if operation == ("run", "jobs", "describe"):
            job = args[3]
            value = actual_job(self.jobs[job], job)
            if self.job_change == "foreign_nonce": value["metadata"]["labels"]["comparison-id"] = "someone-else"
            if self.job_change == "wrong_image": value["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"] = REPOSITORY + ":latest"
            return value
        if operation == ("run", "jobs", "execute"):
            job = args[3]
            self.executions.append(job)
            if self.fail_execute:
                raise self.module.CloudCommandError({"operation": "run jobs execute", "category": "PERMISSION_DENIED"})
            result = {"metadata": {"name": job + "-abc"}, "status": {
                "conditions": [{"type": "Completed", "status": "True"}], "succeededCount": 1, "failedCount": 0
            }}
            if self.execution_change == "foreign_name": result["metadata"]["name"] = "foreign-job-abc"
            if self.execution_change == "failed_condition": result["status"]["conditions"][0]["status"] = "False"
            if self.execution_change == "wrong_success_count": result["status"]["succeededCount"] = 2
            if self.execution_change == "failed_task": result["status"]["failedCount"] = 1
            return result
        if args[:2] == ("logging", "read"):
            if self.fail_logs:
                raise self.module.CloudCommandError({"operation": "logging read", "category": "PERMISSION_DENIED"})
            if self.empty_log_reads:
                self.empty_log_reads -= 1
                return []
            job = self.executions[-1]
            profile = self.jobs[job]["--set-env-vars"]["FIXLIST_COMPARISON_PROFILE"]
            payload = observation(profile)
            payload.update(self.observation_updates.get(profile, {}))
            if self.same_default_ip and profile == "default": payload["observed_ip"] = IP
            row = {
                "resource": {"type": "cloud_run_job", "labels": {
                    "project_id": "seo-autopilot-501517", "location": "europe-west1", "job_name": job
                }},
                "labels": {"run.googleapis.com/execution_name": job + "-abc"},
                "jsonPayload": payload,
            }
            if self.log_change == "foreign_execution": row["labels"]["run.googleapis.com/execution_name"] = "foreign-abc"
            if self.log_change == "foreign_job": row["resource"]["labels"]["job_name"] = "foreign"
            if self.log_change == "foreign_region": row["resource"]["labels"]["location"] = "us-central1"
            if self.log_change == "foreign_project": row["resource"]["labels"]["project_id"] = "foreign"
            if self.log_change == "foreign_source": row["jsonPayload"]["source_sha"] = "b" * 40
            if self.log_change == "raw_html": row["jsonPayload"]["raw_html"] = "SECRET"
            if self.log_change == "missing_complete": row["jsonPayload"]["event"] = "progress"
            return [row, copy.deepcopy(row)] if self.log_change == "duplicate" else [row]
        if operation == ("run", "jobs", "delete"):
            if self.fail_cleanup:
                raise self.module.CloudCommandError({"operation": "run jobs delete", "category": "PERMISSION_DENIED"})
            self.deleted.append(args[3])
            del self.jobs[args[3]]
            return {}
        if operation == ("run", "jobs", "list"):
            name = args[3].split("=", 2)[-1]
            if self.delete_still_listed:
                return [{"metadata": {"name": name}}]
            return [] if name not in self.jobs else [{"metadata": {"name": name}}]
        raise AssertionError(args)


def fake_execution(monkeypatch, tmp_path, **settings):
    m = module()
    cloud = FakeCloud(m)
    for name, value in settings.items():
        setattr(cloud, name, value)
    monkeypatch.setattr(m, "gcloud", cloud)
    monkeypatch.setattr(m, "require_exact_main", lambda source: cloud.calls.append(("guard", source)))
    monkeypatch.setattr(m, "verify_infra", lambda: IP)
    monkeypatch.setattr(m.time, "sleep", lambda _seconds: None)
    output = tmp_path / "result.json"
    def run():
        return m.execute(REV, SHA, "ironwood", f"STATIC-EGRESS-COMPARE:ironwood:{REV}:{SHA}", "123", "1", output)
    return m, cloud, output, run


def test_success_creates_runs_and_deletes_two_jobs_sequentially(monkeypatch, tmp_path):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path)
    result = run()
    assert result["pair_completed"] is True
    assert result["comparison"] == "both_observed_usable_html"
    assert result["authoritative_scan"] is False
    assert len(cloud.executions) == len(cloud.deleted) == 2
    assert cloud.jobs == {}
    create_positions = [i for i, c in enumerate(cloud.calls) if c[:3] == ("run", "jobs", "create")]
    delete_positions = [i for i, c in enumerate(cloud.calls) if c[:3] == ("run", "jobs", "delete")]
    assert create_positions[0] < delete_positions[0] < create_positions[1] < delete_positions[1]
    assert all(row["job_deleted"] for row in result["profiles"].values())
    assert all(row["candidate_and_traffic_unchanged"] is True for row in result["profiles"].values())
    assert json.loads(output.read_text()) == result
    operations = {c[:3] for c in cloud.calls if c[0] == "run"}
    assert operations <= {
        ("run", "services", "describe"), ("run", "services", "get-iam-policy"),
        ("run", "revisions", "describe"), ("run", "jobs", "create"),
        ("run", "jobs", "describe"), ("run", "jobs", "execute"),
        ("run", "jobs", "delete"), ("run", "jobs", "list"),
    }
    for call in cloud.calls:
        if call[:2] == ("logging", "read"):
            assert 'resource.labels.project_id="seo-autopilot-501517"' in call[2]
            assert 'resource.labels.location="europe-west1"' in call[2]
            assert 'labels."run.googleapis.com/execution_name"=' in call[2]
            assert 'jsonPayload.diagnostic="static_egress_comparison_v1"' in call[2]
            assert 'jsonPayload.event="complete"' in call[2]


def test_same_ip_profiles_produce_inconclusive_result(monkeypatch, tmp_path):
    _m, cloud, _output, run = fake_execution(monkeypatch, tmp_path, same_default_ip=True)
    result = run()
    assert result["pair_completed"] is True and result["comparison"] == "inconclusive"
    assert len(cloud.deleted) == 2


@pytest.mark.parametrize("profile", ["default", "static"])
@pytest.mark.parametrize("field,value", [
    ("scan_completed", False), ("pressure_seen", True), ("scan_deadline_reached", True),
    ("robots_unknown_seen", True), ("guard_refusals", 1),
])
def test_limited_profile_is_inconclusive_despite_usable_html(monkeypatch, tmp_path, profile, field, value):
    _m, cloud, _output, run = fake_execution(monkeypatch, tmp_path,
        observation_updates={profile: {field: value}})
    result = run()
    assert result["pair_completed"] is True and result["comparison"] == "inconclusive"
    assert all(row["observation"]["usable_html_pages"] == 1 for row in result["profiles"].values())
    assert len(cloud.deleted) == 2


def test_ambiguous_create_cleans_only_owned_job_without_running_it(monkeypatch, tmp_path):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path, fail_create="command_timeout")
    with pytest.raises(m.CloudCommandError):
        run()
    result = json.loads(output.read_text())
    assert cloud.executions == [] and len(cloud.deleted) == 1 and cloud.jobs == {}
    assert result["pair_completed"] is False
    assert result["profiles"]["default"]["job_deleted"] is True
    assert result["profiles"]["default"]["candidate_and_traffic_unchanged"] is True
    assert result["failure"]["operation"] == "run jobs create"


def test_already_existing_name_is_never_adopted_executed_or_deleted(monkeypatch, tmp_path):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path, fail_create="ALREADY_EXISTS")
    with pytest.raises(m.CloudCommandError):
        run()
    assert cloud.executions == cloud.deleted == []
    assert not any(c[:3] == ("run", "jobs", "describe") for c in cloud.calls)
    assert json.loads(output.read_text())["pair_completed"] is False


@pytest.mark.parametrize("job_change", ["foreign_nonce", "wrong_image"])
def test_ambiguous_create_never_cleans_job_without_matching_ownership_and_spec(monkeypatch, tmp_path, job_change):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path, fail_create="command_timeout", job_change=job_change)
    with pytest.raises(m.CloudCommandError):
        run()
    assert cloud.executions == cloud.deleted == []
    assert json.loads(output.read_text())["profiles"]["default"]["job_deleted"] is False


@pytest.mark.parametrize("failure", ["execute", "logs"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failure_preserves_original_error_and_independent_cleanup_result(monkeypatch, tmp_path, failure, cleanup_fails):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path,
        fail_execute=failure == "execute", fail_logs=failure == "logs", fail_cleanup=cleanup_fails)
    with pytest.raises(m.CloudCommandError) as caught:
        run()
    result = json.loads(output.read_text())
    expected = "run jobs execute" if failure == "execute" else "logging read"
    assert caught.value.evidence["operation"] == expected
    assert result["failure"]["operation"] == expected
    row = result["profiles"]["default"]
    assert row["failure"]["operation"] == expected
    assert row["job_deleted"] is not cleanup_fails
    assert ("cleanup_failure" in row) is cleanup_fails
    assert result["pair_completed"] is False and "static" not in result["profiles"]
    assert len(cloud.executions) == 1
    assert row["candidate_and_traffic_unchanged"] is True


@pytest.mark.parametrize("failure", ["create", "execute", "logs"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failure_always_checks_stability_after_cleanup_and_preserves_first_error(monkeypatch, tmp_path, failure, cleanup_fails):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path,
        fail_create="command_timeout" if failure == "create" else None,
        fail_execute=failure == "execute", fail_logs=failure == "logs",
        fail_cleanup=cleanup_fails, drift_after_create=failure == "create",
        drift_after_execute=failure != "create")
    with pytest.raises(m.CloudCommandError) as caught:
        run()
    result = json.loads(output.read_text())
    expected = {"create": "run jobs create", "execute": "run jobs execute", "logs": "logging read"}[failure]
    row = result["profiles"]["default"]
    assert caught.value.evidence["operation"] == result["failure"]["operation"] == expected
    assert row["failure"]["operation"] == expected
    assert row["stability_failure"]["category"] == "candidate_or_traffic_changed"
    assert row.get("candidate_and_traffic_unchanged", False) is False
    assert row["job_deleted"] is not cleanup_fails
    assert ("cleanup_failure" in row) is cleanup_fails
    assert result["pair_completed"] is False and "static" not in result["profiles"]
    delete_index = next(i for i, call in enumerate(cloud.calls) if call[:3] == ("run", "jobs", "delete"))
    assert any(call[:3] == ("run", "services", "describe") for call in cloud.calls[delete_index + 1:])


def test_cleanup_failure_never_publishes_pair_success(monkeypatch, tmp_path):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path, fail_cleanup=True)
    with pytest.raises(m.CloudCommandError):
        run()
    result = json.loads(output.read_text())
    assert result["pair_completed"] is False
    assert result["profiles"]["default"]["job_deleted"] is False
    assert "comparison" not in result and len(cloud.executions) == 1


def test_deletion_command_without_verified_absence_never_publishes_pair_success(monkeypatch, tmp_path):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path, delete_still_listed=True)
    with pytest.raises(ValueError, match="job_cleanup_not_verified"):
        run()
    result = json.loads(output.read_text())
    assert result["pair_completed"] is False
    assert result["profiles"]["default"]["job_deleted"] is False
    assert len(cloud.deleted) == 1 and len(cloud.executions) == 1


def test_traffic_drift_stops_second_profile_after_cleanup(monkeypatch, tmp_path):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path, drift_after_execute=True)
    with pytest.raises(ValueError, match="candidate_or_traffic_changed"):
        run()
    assert len(cloud.executions) == len(cloud.deleted) == 1
    assert json.loads(output.read_text())["pair_completed"] is False


def test_new_main_between_profiles_stops_next_create_after_first_cleanup(monkeypatch, tmp_path):
    m, cloud, output, run = fake_execution(monkeypatch, tmp_path)
    guards = []
    def guard(source):
        guards.append((source, len(cloud.deleted)))
        if len(guards) == 5:
            assert len(cloud.deleted) == 1
            raise ValueError("exact_current_clean_main_required")
    monkeypatch.setattr(m, "require_exact_main", guard)
    with pytest.raises(ValueError, match="exact_current_clean_main_required"):
        run()
    result = json.loads(output.read_text())
    assert len(cloud.executions) == len(cloud.deleted) == 1
    assert sum(c[:3] == ("run", "jobs", "create") for c in cloud.calls) == 1
    assert result["pair_completed"] is False and "static" not in result["profiles"]
    assert result["profiles"]["default"]["job_deleted"] is True
    assert result["failure"]["category"] == "exact_current_clean_main_required"


@pytest.mark.parametrize("change", ["foreign_execution", "foreign_job", "foreign_region", "foreign_project", "foreign_source", "raw_html", "duplicate", "missing_complete"])
def test_unattributable_or_unsafe_logs_refuse_and_cleanup(monkeypatch, tmp_path, change):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path, log_change=change)
    with pytest.raises(ValueError):
        run()
    assert len(cloud.executions) == len(cloud.deleted) == 1
    result = json.loads(output.read_text())
    assert result["pair_completed"] is False
    assert "observation" not in result["profiles"]["default"]
    assert "SECRET" not in output.read_text()


def test_successful_task_with_failed_probe_record_refuses_pair_and_cleans_up(monkeypatch, tmp_path):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path,
        observation_updates={"default": {"failure_code": "scanner_failed"}})
    with pytest.raises(ValueError, match="observation_probe_failed"):
        run()
    result = json.loads(output.read_text())
    assert result["pair_completed"] is False
    assert "observation" not in result["profiles"]["default"]
    assert len(cloud.executions) == len(cloud.deleted) == 1


def test_delayed_log_ingestion_retries_only_log_reads(monkeypatch, tmp_path):
    _m, cloud, _output, run = fake_execution(monkeypatch, tmp_path, empty_log_reads=2)
    assert run()["pair_completed"] is True
    assert len(cloud.executions) == 2
    assert sum(c[:2] == ("logging", "read") for c in cloud.calls) == 4


@pytest.mark.parametrize("change", ["foreign_name", "failed_condition", "wrong_success_count", "failed_task"])
def test_unsuccessful_or_foreign_execution_never_queries_logs(monkeypatch, tmp_path, change):
    _m, cloud, output, run = fake_execution(monkeypatch, tmp_path, execution_change=change)
    with pytest.raises(ValueError):
        run()
    assert not any(c[:2] == ("logging", "read") for c in cloud.calls)
    assert len(cloud.deleted) == 1
    assert json.loads(output.read_text())["pair_completed"] is False
