#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
INVOKER_SA="${TASKS_INVOKER_SERVICE_ACCOUNT:-}"
JOB="${STANDARD150_RECONCILER_JOB:-fixlist-standard150-reconcile}"
EXPECTED_SCHEDULE="${STANDARD150_RECONCILER_SCHEDULE:-*/5 * * * *}"
# Supplying either staged identity makes the complete staged check mandatory.
EXPECTED_SOURCE="${RECONCILER_EXPECTED_SOURCE_SHA:-}"
EXPECTED_STAGE_DIGEST="${RECONCILER_EXPECTED_STAGED_CONFIG_SHA256:-}"
EXPECTED_REVISION="${RECONCILER_EXPECTED_REVISION:-}"

if [[ -z "$INVOKER_SA" ]]; then
  echo "TASKS_INVOKER_SERVICE_ACCOUNT is required." >&2
  exit 2
fi
if [[ -n "$EXPECTED_SOURCE$EXPECTED_STAGE_DIGEST$EXPECTED_REVISION" ]] &&
  [[ ! "$EXPECTED_SOURCE" =~ ^[0-9a-f]{40}$ || ! "$EXPECTED_STAGE_DIGEST" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Staged verification requires RECONCILER_EXPECTED_SOURCE_SHA and RECONCILER_EXPECTED_STAGED_CONFIG_SHA256." >&2
  exit 2
fi

WORKER_JSON="$(gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json 2>/dev/null || true)"
JOB_JSON="$(gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" --format=json 2>/dev/null || true)"
if [[ -z "$WORKER_JSON" || -z "$JOB_JSON" ]]; then
  echo "RECONCILER NOT VERIFIED — worker or Scheduler job could not be described." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKER_JSON="$WORKER_JSON" JOB_JSON="$JOB_JSON" PYTHONDONTWRITEBYTECODE=1 python3 - \
  "$SCRIPT_DIR" "$PROJECT" "$REGION" "$WORKER" "$INVOKER_SA" "$EXPECTED_SCHEDULE" \
  "$EXPECTED_SOURCE" "$EXPECTED_STAGE_DIGEST" "$EXPECTED_REVISION" <<'PY'
import json
import os
import re
import subprocess
import sys

scripts, project, region, worker_name, invoker, schedule, source, digest, expected_revision = sys.argv[1:]
sys.path.insert(0, scripts)
from staged_candidate_cloudbuild import digest_for, environment, owner_cohort, source_tag
from staged_queue_guard import COHORT_KEYS, STAGE_QUEUE, canonical_origin, require, traffic_entries, traffic_percent


def verify_scheduler(job, origin):
    http = job.get("httpTarget") or {}
    oidc = http.get("oidcToken") or {}
    require(job.get("state") == "ENABLED", "Scheduler is not enabled")
    require(job.get("schedule") == schedule, "Scheduler schedule mismatch")
    require(http.get("uri") == origin + "/scan-reconcile", "Scheduler does not target the canonical reconciliation route")
    require(str(http.get("httpMethod") or "").upper() == "POST", "Scheduler method mismatch")
    require(oidc.get("serviceAccountEmail") == invoker, "Scheduler invoker mismatch")
    audience = str(oidc.get("audience") or "")
    require((audience if source else audience.rstrip("/")) == origin, "Scheduler OIDC audience mismatch")


def verify_staged(worker, origin):
    require(worker["metadata"]["name"] == worker_name, "Worker service readback mismatch")
    traffic = traffic_entries(worker)
    serving = [row for row in traffic if traffic_percent(row) > 0]
    require(len(serving) == 1 and serving[0]["percent"] == 100 and serving[0].get("latestRevision", False) is False,
            "Canonical worker is not pinned to a single 100%-serving revision")
    revision_name = serving[0].get("revisionName")
    require(isinstance(revision_name, str) and re.fullmatch(re.escape(worker_name) + r"-[a-z0-9-]+", revision_name)
            and len(revision_name) <= 63 and (not expected_revision or revision_name == expected_revision),
            "Serving revision identity mismatch")

    reviewed = environment(source, project, region, f"fixlist-scan-workspaces-{project}",
                           f"projects/{project}/locations/{region}/queues/{STAGE_QUEUE}", origin)
    require(digest_for(source, reviewed) == digest, "Expected digest does not describe the reviewed staged configuration")
    tag_rows = [row for row in traffic if row.get("tag") == source_tag(source)]
    require(len(tag_rows) == 1 and tag_rows[0].get("revisionName") == revision_name
            and tag_rows[0].get("url") == reviewed["SCAN_STAGE_TARGET_URL"],
            "Source-bound stage tag does not address the serving revision")

    cloud = subprocess.run(["gcloud", "run", "revisions", "describe", revision_name,
                            f"--project={project}", f"--region={region}", "--format=json"],
                           capture_output=True, text=True, check=True, timeout=30)
    revision = json.loads(cloud.stdout)
    require(revision["metadata"]["name"] == revision_name, "Worker revision readback mismatch")
    ready = [row for row in revision["status"]["conditions"] if row.get("type") == "Ready"]
    require(len(ready) == 1 and ready[0].get("status") == "True", "Serving worker revision is not Ready")
    containers = revision["spec"]["containers"]
    require(len(containers) == 1, "Serving worker must have one container")

    expected = {key: value for key, value in reviewed.items() if key not in COHORT_KEYS}
    expected.update(FIXLIST_WORKER_SOURCE_SHA=source, FIXLIST_STAGED_CONFIG_SHA256=digest,
                    TASKS_INVOKER_SERVICE_ACCOUNT=invoker)
    keys = expected.keys() | COHORT_KEYS | {"SCAN_PIPELINE_OWNER_IDS"}
    entries = [row for row in containers[0]["env"] if row.get("name") in keys]
    env = {row["name"]: row.get("value", "") for row in entries}
    require(len(env) == len(entries) and all("valueFrom" not in row for row in entries)
            and all(isinstance(value, str) for value in env.values()),
            "Serving staged configuration contains ambiguous environment entries")
    mismatches = sorted(key for key, value in expected.items() if env.get(key) != value)
    require(not mismatches, "Serving staged configuration mismatch: " + ", ".join(mismatches))
    require(env.get("SCAN_PIPELINE_OWNER_IDS", "") == "", "Unexpected legacy staged owner cohort")
    mode, cohort = env.get("SCAN_PIPELINE_MODE"), env.get("SCAN_STAGED_OWNER_IDS", "")
    if mode == "staged":
        owner_cohort(cohort)
    else:
        require(mode == "monolith" and cohort == "", "Serving staged capability mode or owner cohort is invalid")
    return revision_name


try:
    worker = json.loads(os.environ["WORKER_JSON"])
    job = json.loads(os.environ["JOB_JSON"])
    origin = canonical_origin(worker) if source else str((worker.get("status") or {}).get("url") or "").rstrip("/")
    require(origin.startswith("https://"), "Worker canonical HTTPS origin is missing")
    verify_scheduler(job, origin)
    if source:
        revision = verify_staged(worker, origin)
        print(f"STANDARD150_STAGED_RECONCILER_VERIFIED revision={revision} source_sha={source} staged_config_sha256={digest}")
    print("STANDARD150_RECONCILER_VERIFIED")
except (subprocess.SubprocessError, OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
    raise SystemExit("RECONCILER NOT VERIFIED — Cloud Run or Scheduler metadata could not be read") from None
except ValueError as exc:
    raise SystemExit(f"RECONCILER NOT VERIFIED — {exc}") from None
PY
