#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
INVOKER_SA="${TASKS_INVOKER_SERVICE_ACCOUNT:-}"
JOB="${STANDARD150_RECONCILER_JOB:-fixlist-standard150-reconcile}"
EXPECTED_SCHEDULE="${STANDARD150_RECONCILER_SCHEDULE:-*/5 * * * *}"

if [[ -z "$INVOKER_SA" ]]; then
  echo "TASKS_INVOKER_SERVICE_ACCOUNT is required." >&2
  exit 2
fi

WORKER_JSON="$(gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json 2>/dev/null || true)"
JOB_JSON="$(gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" --format=json 2>/dev/null || true)"
if [[ -z "$WORKER_JSON" || -z "$JOB_JSON" ]]; then
  echo "RECONCILER NOT VERIFIED — worker or Scheduler job could not be described." >&2
  exit 1
fi

WORKER_JSON="$WORKER_JSON" JOB_JSON="$JOB_JSON" INVOKER_SA="$INVOKER_SA" EXPECTED_SCHEDULE="$EXPECTED_SCHEDULE" python3 - <<'PY'
import json,os
worker=json.loads(os.environ["WORKER_JSON"])
job=json.loads(os.environ["JOB_JSON"])
worker_url=str((worker.get("status") or {}).get("url") or "").rstrip("/")
assert worker_url.startswith("https://"), worker_url
http=job.get("httpTarget") or {}
oidc=http.get("oidcToken") or {}
assert str(job.get("state") or "") == "ENABLED", job.get("state")
assert str(job.get("schedule") or "") == os.environ["EXPECTED_SCHEDULE"], job.get("schedule")
assert str(http.get("uri") or "") == worker_url + "/scan-reconcile", http.get("uri")
assert str(http.get("httpMethod") or "").upper() == "POST", http.get("httpMethod")
assert str(oidc.get("serviceAccountEmail") or "") == os.environ["INVOKER_SA"], oidc
assert str(oidc.get("audience") or "").rstrip("/") == worker_url, oidc
print("STANDARD150_RECONCILER_VERIFIED")
PY
