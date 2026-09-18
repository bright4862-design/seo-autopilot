"""Allowlisted, isolated GCP diagnostic. Never alters services, queues, IAM or secrets."""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path

PROJECT = "seo-autopilot-501517"
REGION = "europe-west1"
SERVICE = "fixlist-standard150-worker"
ROOT = Path(__file__).resolve().parents[1]


def job_plan(service, revision, expected_revision, probe_source):
    traffic = [t for t in service.get("status", {}).get("traffic", []) if t.get("percent", 0) > 0]
    if len(traffic) != 1 or traffic[0].get("percent") != 100 or traffic[0].get("revisionName") != expected_revision:
        raise ValueError("Refusing: expected revision must serve exactly 100 percent")
    meta, status, spec = (revision.get(k, {}) for k in ("metadata", "status", "spec"))
    if meta.get("name") != expected_revision or meta.get("labels", {}).get("serving.knative.dev/service") != SERVICE:
        raise ValueError("Refusing: revision identity/service mismatch")
    if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])):
        raise ValueError("Refusing: revision is not ready")
    image = status.get("imageDigest", "")
    if not re.fullmatch(r"[a-z0-9./_:-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("Refusing: resolved immutable image digest required")
    containers = spec.get("containers", [])
    if len(containers) != 1 or spec.get("volumes"):
        raise ValueError("Refusing: sidecars or volumes require separate network assessment")
    env = containers[0].get("env", [])
    unsupported = {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "ssl_cert_file", "ssl_cert_dir"}
    if any(e.get("name", "").lower() in unsupported for e in env):
        raise ValueError("Refusing: proxy/custom certificate environment cannot be silently omitted")
    source = next((e.get("value", "") for e in env if e.get("name") == "FIXLIST_WORKER_SOURCE_SHA"), "")
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Refusing: worker source SHA missing")
    account = spec.get("serviceAccountName", "")
    if not re.fullmatch(r"[a-z][a-z0-9-]+@seo-autopilot-501517\.iam\.gserviceaccount\.com", account):
        raise ValueError("Refusing: explicit runtime service account required")
    annotations = meta.get("annotations", {})
    if "run.googleapis.com/network-interfaces" in annotations or annotations.get("run.googleapis.com/execution-environment") == "gen1":
        raise ValueError("Refusing: direct VPC or gen1 requires separately reviewed job equivalence")
    encoded = base64.b64encode(probe_source.encode()).decode()
    flags = {"--image": image, "--service-account": account,
             "--tasks": "1", "--parallelism": "1", "--max-retries": "0", "--task-timeout": "180s",
             "--cpu": "1", "--memory": "512Mi", "--command": ["python"],
             "--args": ["-c", f"import base64; exec(compile(base64.b64decode('{encoded}'), 'ironwood_probe.py', 'exec'))"],
             "--labels": {"purpose": "fixlist-ironwood-diagnostic"}}
    connector = annotations.get("run.googleapis.com/vpc-access-connector")
    egress = annotations.get("run.googleapis.com/vpc-access-egress")
    if connector:
        if not re.fullmatch(r"projects/seo-autopilot-501517/locations/europe-west1/connectors/[a-z][a-z0-9-]+", connector):
            raise ValueError("Refusing: unsupported connector reference")
        if egress not in (None, "all-traffic", "private-ranges-only"):
            raise ValueError("Refusing: unsupported VPC egress")
        flags.update({"--vpc-connector": connector, "--vpc-egress": egress or "private-ranges-only"})
    elif egress:
        raise ValueError("Refusing: egress without supported connector")
    evidence = {"worker_revision": expected_revision, "worker_image": image, "worker_source_sha": source,
                "runtime_service_account": account, "vpc_connector": connector, "vpc_egress": egress,
                "source_ip_equivalence_verified": False,
                "limitation": "Separate Cloud Run job; same image and supported network configuration do not prove same outbound IP"}
    return flags, evidence


def gcloud(*args):
    result = subprocess.run(["gcloud", *args, f"--project={PROJECT}", "--format=json",
                             *([] if args[0] == "logging" else [f"--region={REGION}"])],
                            check=True, capture_output=True, text=True, timeout=300)
    return json.loads(result.stdout or "{}")


def execute(revision, source, confirm, run_id, attempt, output):
    if not re.fullmatch(r"fixlist-standard150-worker-[a-z0-9-]+", revision):
        raise ValueError("Invalid revision")
    if not re.fullmatch(r"[0-9a-f]{40}", source) or confirm != f"ironwood-diagnostic:{revision}:{source}":
        raise ValueError("Exact diagnostic/revision/source confirmation required")
    if not re.fullmatch(r"[0-9]{1,20}", run_id) or not re.fullmatch(r"[0-9]{1,4}", attempt):
        raise ValueError("Numeric workflow run/attempt required")
    output.mkdir(parents=True, exist_ok=True)
    job = f"fixlist-ironwood-diag-{run_id}-{attempt}"
    s = gcloud("run", "services", "describe", SERVICE)
    r = gcloud("run", "revisions", "describe", revision)
    flags, evidence = job_plan(s, r, revision, (ROOT / "scripts/ironwood_probe.py").read_text())
    evidence.update({"diagnostic_source_sha": source, "job": job, "job_deleted": False})
    flags_file = output / "job-flags.json"
    flags_file.write_text(json.dumps(flags))  # Contains code/config only, never production env/secrets.
    (output / "profile.json").write_text(json.dumps(evidence, indent=2))
    # Create, never replace: an existing name is a hard refusal, not a reuse opportunity.
    gcloud("run", "jobs", "create", job, f"--flags-file={flags_file}", "--quiet")
    try:
        execution = gcloud("run", "jobs", "execute", job, "--wait")
        name = execution.get("metadata", {}).get("name", "")
        if not re.fullmatch(re.escape(job) + r"-[a-z0-9]+", name):
            raise ValueError("Unrecognized execution identity; refusing broad log query")
        evidence["execution"] = name
        logs = gcloud("logging", "read", f'resource.type="cloud_run_job" AND resource.labels.job_name="{job}" AND labels."run.googleapis.com/execution_name"="{name}"', "--limit=100", "--order=asc")
        rows = [row["jsonPayload"] for row in logs if row.get("jsonPayload", {}).get("diagnostic") == "ironwood_v1"]
        (output / "observations.json").write_text(json.dumps(rows, indent=2))
        if not any(row.get("event") == "complete" for row in rows):
            raise ValueError("Diagnostic completion evidence missing; do not infer a result")
        # Detect concurrent production movement, without trying to roll it back.
        job_plan(gcloud("run", "services", "describe", SERVICE), r, revision, "")
    finally:
        try:
            gcloud("run", "jobs", "delete", job, "--quiet")
            evidence["job_deleted"] = True
        finally:
            (output / "result.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("revision", "source", "confirm", "run-id", "attempt", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        execute(args.revision, args.source, args.confirm, args.run_id, args.attempt, Path(args.output))
    except subprocess.CalledProcessError as exc:
        # gcloud errors may contain account/resource details, but never print flags/code or credentials.
        print(f"Diagnostic cloud command failed (exit {exc.returncode}); no IAM/access workaround attempted.")
        raise SystemExit(1)
