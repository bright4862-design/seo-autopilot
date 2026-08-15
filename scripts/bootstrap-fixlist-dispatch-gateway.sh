#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
REGION="europe-west1"
OPERATOR_SA="fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com"
GATEWAY="fixlist-dispatch-gateway"
GATEWAY_RUNTIME_SA="fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"
WORKER="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
DRAIN_QUEUE="fixlist-standard150-drain"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n==> %s\n' "$*"; }

say "Verify an exact clean origin/main checkout before any cloud mutation"
git -C "$REPO_ROOT" fetch origin main --quiet
SOURCE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
REMOTE_MAIN_SHA="$(git -C "$REPO_ROOT" rev-parse origin/main)"
if [[ "$SOURCE_SHA" != "$REMOTE_MAIN_SHA" ]]; then
  echo "Refusing bootstrap: checkout $SOURCE_SHA is not current origin/main $REMOTE_MAIN_SHA" >&2
  exit 2
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]]; then
  echo "Refusing bootstrap: repository contains tracked or untracked changes." >&2
  exit 2
fi
if ! printf '%s' "$SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "Refusing bootstrap: source identity is not an exact Git SHA." >&2
  exit 2
fi
printf 'source_sha=%s\n' "$SOURCE_SHA"

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

say "Verify the existing keyless operator, runtime identities, worker, and queue"
gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT" >/dev/null
gcloud iam service-accounts describe "$GATEWAY_RUNTIME_SA" --project="$PROJECT" >/dev/null
gcloud iam service-accounts describe "$INVOKER_SA" --project="$PROJECT" >/dev/null
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" >/dev/null
gcloud tasks queues describe "$QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
gcloud tasks queues describe "$DRAIN_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null

say "Resolve the project's actual default Cloud Build service account"
BUILD_SA_RESOURCE="$(gcloud builds get-default-service-account --project="$PROJECT" --format='value(serviceAccountEmail)')"
BUILD_SA="${BUILD_SA_RESOURCE##*/}"
if [[ -z "$BUILD_SA" || "$BUILD_SA" != *@* ]]; then
  echo "Refusing bootstrap: Cloud Build returned an invalid default service-account identity." >&2
  exit 2
fi
gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT" >/dev/null
printf 'build_service_account=%s\n' "$BUILD_SA"

say "Grant only source-build permissions the WIF operator needs for future revisions"
for ROLE in \
  roles/run.sourceDeveloper \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${OPERATOR_SA}" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null
done

say "Allow the WIF operator to attach only the gateway runtime identity"
gcloud iam service-accounts add-iam-policy-binding "$GATEWAY_RUNTIME_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Allow the WIF operator to use only the resolved Cloud Build identity"
gcloud iam service-accounts add-iam-policy-binding "$BUILD_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Allow the actual Cloud Build identity to build the gateway"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/run.builder" \
  --condition=None \
  --quiet >/dev/null

say "Grant the gateway runtime create-only access on the Standard 150 queue"
# The GA Cloud Tasks queue IAM command does not expose --condition in all
# installed gcloud releases. Queue bindings here are intentionally unconditional.
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer" \
  --quiet >/dev/null
gcloud tasks queues add-iam-policy-binding "$DRAIN_QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer" \
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

# If a previous gateway deployment exists from the earlier owner-only script,
# normalize it to the recommended public boundary before the exact-SHA deploy.
# This mutation is intentionally performed under the authenticated owner/admin
# shell, never by the WIF operator.
if gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" >/dev/null 2>&1; then
  say "Normalize the existing gateway public boundary under owner credentials"
  gcloud run services update "$GATEWAY" \
    --project="$PROJECT" \
    --region="$REGION" \
    --no-invoker-iam-check \
    --quiet >/dev/null
fi

say "Deploy and verify the exact current main gateway under owner credentials"
GCP_PROJECT="$PROJECT" \
GCP_REGION="$REGION" \
CLOUD_RUN_SERVICE="$WORKER" \
CLOUD_TASKS_QUEUE="$QUEUE" \
TASKS_INVOKER_SERVICE_ACCOUNT="$INVOKER_SA" \
GATEWAY_SERVICE="$GATEWAY" \
GATEWAY_RUNTIME_SERVICE_ACCOUNT="$GATEWAY_RUNTIME_SA" \
SOURCE_SHA="$SOURCE_SHA" \
CONFIRM="$SOURCE_SHA" \
  "$REPO_ROOT/scripts/deploy_dispatch_gateway.sh"

say "Grant future WIF deployments Developer access only on the gateway service"
gcloud run services add-iam-policy-binding "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/run.developer" \
  --condition=None \
  --quiet >/dev/null

say "Verify the operator has no project-wide Cloud Run Admin binding"
if gcloud projects get-iam-policy "$PROJECT" \
  --flatten='bindings[].members' \
  --filter="bindings.role=roles/run.admin AND bindings.members=serviceAccount:${OPERATOR_SA}" \
  --format='value(bindings.role)' | grep -q .; then
  echo "Refusing completion: operator still has project-wide roles/run.admin." >&2
  exit 2
fi

printf '\nGATEWAY_BOOTSTRAP_COMPLETE\n'
printf 'source_sha=%s\n' "$SOURCE_SHA"
printf 'operator=%s\n' "$OPERATOR_SA"
printf 'build_service_account=%s\n' "$BUILD_SA"
printf 'gateway_runtime=%s\n' "$GATEWAY_RUNTIME_SA"
printf 'queue=projects/%s/locations/%s/queues/%s\n' "$PROJECT" "$REGION" "$QUEUE"
printf 'invoker=%s\n' "$INVOKER_SA"
printf 'signing_secret_ref=%s:%s (value was not read)\n' "$SIGNING_SECRET" "$SIGNING_VERSION"
printf 'No service-account key was created or read.\n'
