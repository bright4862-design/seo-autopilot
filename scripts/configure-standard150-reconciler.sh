#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
INVOKER_SA="${TASKS_INVOKER_SERVICE_ACCOUNT:-}"
JOB="${STANDARD150_RECONCILER_JOB:-fixlist-standard150-reconcile}"
SCHEDULE="${STANDARD150_RECONCILER_SCHEDULE:-*/5 * * * *}"
CONFIRM="${CONFIRM:-}"

if [[ "$CONFIRM" != "CONFIGURE-STANDARD150-RECONCILER" ]]; then
  echo "Refusing Scheduler mutation: CONFIRM must equal CONFIGURE-STANDARD150-RECONCILER" >&2
  exit 2
fi
if [[ -z "$INVOKER_SA" ]]; then
  echo "TASKS_INVOKER_SERVICE_ACCOUNT is required; the reconciler reuses the exact private worker invoker identity." >&2
  exit 2
fi

WORKER_JSON="$(mktemp)"
JOB_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$JOB_JSON"' EXIT

gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"
WORKER_URL="$(python3 - "$WORKER_JSON" <<'PY'
import json,sys
service=json.load(open(sys.argv[1]))
url=str((service.get("status") or {}).get("url") or "").rstrip("/")
if not url.startswith("https://"):
    raise SystemExit("Worker has no canonical HTTPS service URL")
print(url)
PY
)"
TARGET_URL="$WORKER_URL/scan-reconcile"

# Cloud Scheduler uses OIDC for non-googleapis HTTP targets. The audience is the
# Cloud Run service origin, matching the existing Cloud Tasks worker audience.
COMMON=(
  --project="$PROJECT"
  --location="$REGION"
  --schedule="$SCHEDULE"
  --time-zone="Etc/UTC"
  --uri="$TARGET_URL"
  --http-method=POST
  --oidc-service-account-email="$INVOKER_SA"
  --oidc-token-audience="$WORKER_URL"
  --attempt-deadline=120s
  --max-retry-attempts=2
  --min-backoff=30s
  --max-backoff=120s
  --max-doublings=2
  --description="FixList Standard 150 stale ScanRun reconciliation backstop"
  --quiet
)

if gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" "${COMMON[@]}"
else
  gcloud scheduler jobs create http "$JOB" "${COMMON[@]}"
fi

gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" --format=json > "$JOB_JSON"
python3 - "$JOB_JSON" "$TARGET_URL" "$WORKER_URL" "$INVOKER_SA" "$SCHEDULE" <<'PY'
import json,sys
path,target,audience,sa,schedule=sys.argv[1:]
job=json.load(open(path))
http=job.get("httpTarget") or {}
oidc=http.get("oidcToken") or {}
assert str(job.get("schedule") or "") == schedule, job
assert str(http.get("uri") or "") == target, http
assert str(http.get("httpMethod") or "").upper() == "POST", http
assert str(oidc.get("serviceAccountEmail") or "") == sa, oidc
assert str(oidc.get("audience") or "").rstrip("/") == audience.rstrip("/"), oidc
print("STANDARD150_RECONCILER_CONFIG_OK")
PY
