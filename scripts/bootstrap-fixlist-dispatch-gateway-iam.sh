#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
PROJECT_NUMBER="919035207432"
REGION="europe-west1"
OPERATOR_SA="fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com"
GATEWAY_RUNTIME_SA="fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"
WORKER="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$PROJECT" >/dev/null

say "Enable APIs required by Cloud Run source deployment and gateway runtime"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudtasks.googleapis.com \
  --project="$PROJECT" \
  --quiet

say "Verify existing identities and resources"
gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT" >/dev/null
gcloud iam service-accounts describe "$GATEWAY_RUNTIME_SA" --project="$PROJECT" >/dev/null
gcloud iam service-accounts describe "$INVOKER_SA" --project="$PROJECT" >/dev/null
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" >/dev/null
gcloud tasks queues describe "$QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null

say "Grant gateway deployment permissions to the keyless GitHub operator"
for ROLE in \
  roles/run.admin \
  roles/run.sourceDeveloper \
  roles/serviceusage.serviceUsageConsumer \
  roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${OPERATOR_SA}" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null
done

say "Allow the operator to attach only the existing gateway runtime identity"
gcloud iam service-accounts add-iam-policy-binding "$GATEWAY_RUNTIME_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Allow Cloud Run source builds to build the gateway"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/run.builder" \
  --condition=None \
  --quiet >/dev/null

say "Grant the gateway runtime create-only access on the Standard 150 queue"
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer" \
  --condition=None \
  --quiet >/dev/null

say "Allow the gateway runtime to mint task OIDC only as the existing invoker identity"
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Resolve the exact signing-secret reference from the live worker without reading its value"
WORKER_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON"' EXIT
gcloud run services describe "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$WORKER_JSON"

read -r SIGNING_SECRET SIGNING_VERSION < <(python3 - "$WORKER_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    service = json.load(handle)
containers = service.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
if not containers:
    raise SystemExit('Worker has no container configuration')
for item in containers[0].get('env', []):
    if item.get('name') != 'SCAN_EVIDENCE_SIGNING_KEY':
        continue
    ref = item.get('valueFrom', {}).get('secretKeyRef', {})
    name = str(ref.get('name') or '').strip()
    version = str(ref.get('key') or '').strip()
    if not name or not version or version == 'latest':
        raise SystemExit('Worker signing secret is not pinned to an exact version')
    print(name, version)
    break
else:
    raise SystemExit('Worker does not reference SCAN_EVIDENCE_SIGNING_KEY')
PY
)

say "Grant the gateway runtime access only to that existing signing secret"
gcloud secrets add-iam-policy-binding "$SIGNING_SECRET" \
  --project="$PROJECT" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet >/dev/null

say "Final verification"
printf 'operator=%s\n' "$OPERATOR_SA"
printf 'gateway_runtime=%s\n' "$GATEWAY_RUNTIME_SA"
printf 'queue=projects/%s/locations/%s/queues/%s\n' "$PROJECT" "$REGION" "$QUEUE"
printf 'invoker=%s\n' "$INVOKER_SA"
printf 'signing_secret_ref=%s:%s (value was not read)\n' "$SIGNING_SECRET" "$SIGNING_VERSION"

echo
printf '%s\n' "GATEWAY_IAM_BOOTSTRAP_COMPLETE"
printf '%s\n' "No service-account key was created or read."
