#!/usr/bin/env bash
# Deploy the keyless FixList dispatch gateway from the repo's canonical
# source (dispatch-gateway/), replacing the original Cloud Shell heredoc
# bootstrap with a version-controlled equivalent.
#
# OWNER-EXECUTED. This script is prepared in the repository but is only ever
# run by the repository owner in an authorized GCP shell. It deploys a new
# Cloud Run service revision for the gateway; it does not touch the worker,
# the queue, Base44, or customer traffic.
#
# Everything here matches the bootstrap block that first created the gateway:
# same service name, same IAM grants, same env contract. Idempotent — IAM
# add-iam-policy-binding calls and Cloud Run deploys are safe to re-run.
#
# It creates no service-account keys and prints no secret values.

set -euo pipefail

PROJECT="${PROJECT:-seo-autopilot-501517}"
REGION="${REGION:-europe-west1}"

WORKER="${WORKER:-fixlist-standard150-worker}"
GATEWAY="${GATEWAY:-fixlist-dispatch-gateway}"

DISPATCHER_SA="${DISPATCHER_SA:-fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com}"
INVOKER_SA="${INVOKER_SA:-fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com}"

QUEUE_PATH="${QUEUE_PATH:-projects/${PROJECT}/locations/${REGION}/queues/fixlist-standard150}"
WORKER_URL="${WORKER_URL:-https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app/scan-job}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/dispatch-gateway"

[ -f "$SOURCE_DIR/main.py" ] || { echo "ERROR: $SOURCE_DIR/main.py not found; run from a repo checkout."; exit 1; }

gcloud config set project "$PROJECT" >/dev/null

echo "Finding the signing secret already used by the worker..."

SECRET_INFO="$(
  gcloud run services describe "$WORKER" \
    --project="$PROJECT" \
    --region="$REGION" \
    --format=json |
  python3 -c '
import json,sys
d=json.load(sys.stdin)
envs=d.get("spec",{}).get("template",{}).get("spec",{}).get("containers",[{}])[0].get("env",[])
for e in envs:
    if e.get("name")=="SCAN_EVIDENCE_SIGNING_KEY":
        r=e.get("valueFrom",{}).get("secretKeyRef",{})
        print((r.get("name") or "") + "\t" + (r.get("key") or "latest"))
        break
'
)"

SECRET_NAME="$(printf '%s' "$SECRET_INFO" | cut -f1)"
SECRET_VERSION="$(printf '%s' "$SECRET_INFO" | cut -f2)"

if [ -z "$SECRET_NAME" ]; then
  echo "ERROR: Could not locate SCAN_EVIDENCE_SIGNING_KEY on the existing worker."
  exit 1
fi

[ -n "$SECRET_VERSION" ] || SECRET_VERSION="latest"

echo "Using existing signing-secret reference: $SECRET_NAME"
echo "Granting the gateway only the permissions it needs..."

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$DISPATCHER_SA" \
  --role="roles/cloudtasks.enqueuer" \
  --quiet >/dev/null

gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:$DISPATCHER_SA" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project="$PROJECT" \
  --member="serviceAccount:$DISPATCHER_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

echo
echo "Deploying keyless FixList dispatch gateway from $SOURCE_DIR ..."

gcloud run deploy "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$SOURCE_DIR" \
  --service-account="$DISPATCHER_SA" \
  --allow-unauthenticated \
  --ingress=all \
  --memory=256Mi \
  --cpu=1 \
  --concurrency=20 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="SCAN_TASKS_QUEUE_PATH=$QUEUE_PATH,SCAN_WORKER_URL=$WORKER_URL,TASKS_INVOKER_SERVICE_ACCOUNT=$INVOKER_SA" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=$SECRET_NAME:$SECRET_VERSION" \
  --quiet

GATEWAY_URL="$(
  gcloud run services describe "$GATEWAY" \
    --project="$PROJECT" \
    --region="$REGION" \
    --format='value(status.url)'
)"

echo
echo "========================================"
echo "GATEWAY READY"
echo "$GATEWAY_URL"
echo "========================================"
echo
curl -fsS "$GATEWAY_URL/health"
echo
