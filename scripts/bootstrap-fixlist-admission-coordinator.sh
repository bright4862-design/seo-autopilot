#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
CONFIRM="${CONFIRM:-}"
EXPECTED_CONFIRM="BOOTSTRAP-ADMISSION-INFRA"
[[ "$CONFIRM" == "$EXPECTED_CONFIRM" ]] || { echo "Refusing bootstrap: CONFIRM must equal $EXPECTED_CONFIRM" >&2; exit 2; }

COORDINATOR="${ADMISSION_COORDINATOR_SERVICE:-fixlist-scan-admission-coordinator}"
COORDINATOR_SA="${ADMISSION_COORDINATOR_RUNTIME_SA:-fixlist-admission-coordinator@${PROJECT}.iam.gserviceaccount.com}"
DATABASE="${FIRESTORE_DATABASE:-fixlist-admission}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
DRAIN_QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
GATEWAY_RUNTIME_SA="${GATEWAY_RUNTIME_SERVICE_ACCOUNT:-fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com}"
DEPLOYER_SA="${GCP_OPERATOR_SERVICE_ACCOUNT:-fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com}"
ADMISSION_OPERATOR_SA="${ADMISSION_OPERATOR_SERVICE_ACCOUNT:-fixlist-admission-operator@${PROJECT}.iam.gserviceaccount.com}"
ADMISSION_OPERATOR_SECRET="${ADMISSION_OPERATOR_SIGNING_SECRET:-fixlist-admission-operator-signing-key}"
ADMISSION_OPERATOR_AUDIENCE="${ADMISSION_OPERATOR_AUDIENCE:-https://fixlist-admission-operator}"
ADMISSION_OPERATOR_ID="${ADMISSION_OPERATOR_ID:-fixlist-cloud-operator}"
DB_JSON=""
WORKER_JSON=""
OPERATOR_SECRET_TMP=""

cleanup() {
  rm -f "${DB_JSON:-}" "${WORKER_JSON:-}" "${OPERATOR_SECRET_TMP:-}"
}
trap cleanup EXIT

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

gcloud config set project "$PROJECT" >/dev/null

gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com cloudtasks.googleapis.com \
  cloudscheduler.googleapis.com serviceusage.googleapis.com \
  --project="$PROJECT" --quiet

BUILD_SA_RAW="$(gcloud builds get-default-service-account --project="$PROJECT" --format='value(serviceAccountEmail)')"
BUILD_SA="${BUILD_SA_RAW##*/}"
[[ "$BUILD_SA" == *@* ]] || { echo "Invalid default Cloud Build SA." >&2; exit 2; }
BUILD_SA_RESOURCE="projects/${PROJECT}/serviceAccounts/${BUILD_SA}"
gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT" >/dev/null

if ! gcloud iam service-accounts describe "$COORDINATOR_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${COORDINATOR_SA%%@*}" --project="$PROJECT" \
    --display-name="FixList scan admission coordinator" --quiet
fi
if ! gcloud iam service-accounts describe "$ADMISSION_OPERATOR_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${ADMISSION_OPERATOR_SA%%@*}" --project="$PROJECT" \
    --display-name="FixList admission barrier operator" --quiet
fi

if ! gcloud firestore databases describe --database="$DATABASE" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud firestore databases create --database="$DATABASE" --location="$REGION" \
    --type=firestore-native --delete-protection --project="$PROJECT" --quiet
else
  DB_JSON="$(mktemp)"
  gcloud firestore databases describe --database="$DATABASE" --project="$PROJECT" --format=json > "$DB_JSON"
  python3 - "$DB_JSON" "$REGION" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); region=sys.argv[2]
if str(v.get('locationId') or '')!=region: raise SystemExit('existing admission DB location mismatch')
if str(v.get('type') or '').upper() not in {'FIRESTORE_NATIVE','FIRESTORE'}: raise SystemExit('existing admission DB is not Firestore Native')
PY
  gcloud firestore databases update --database="$DATABASE" --delete-protection --project="$PROJECT" --quiet
fi

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${COORDINATOR_SA}" --role="roles/datastore.user" --condition=None --quiet >/dev/null

WORKER_JSON="$(mktemp)"
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"
SIGNING_SECRET="$(python3 - "$WORKER_JSON" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); env=(v.get('spec',{}).get('template',{}).get('spec',{}).get('containers') or [{}])[0].get('env',[])
for i in env:
  if i.get('name')=='SCAN_EVIDENCE_SIGNING_KEY':
    r=i.get('valueFrom',{}).get('secretKeyRef',{}); n=str(r.get('name') or ''); k=str(r.get('key') or '')
    if not n or not k.isdigit(): raise SystemExit('live signing secret not numeric-pinned')
    print(n); break
else: raise SystemExit('live signing secret missing')
PY
)"
gcloud secrets add-iam-policy-binding "$SIGNING_SECRET" --project="$PROJECT" \
  --member="serviceAccount:${COORDINATOR_SA}" --role="roles/secretmanager.secretAccessor" --condition=None --quiet >/dev/null

# The operator signing root is a distinct random secret. Its value is never
# printed, exported, or reused as scan-evidence authority.
if [[ "$ADMISSION_OPERATOR_SECRET" == "$SIGNING_SECRET" ]]; then
  echo "Refusing bootstrap: admission operator and scan-evidence secret names must differ." >&2
  exit 2
fi
if ! gcloud secrets describe "$ADMISSION_OPERATOR_SECRET" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud secrets create "$ADMISSION_OPERATOR_SECRET" --project="$PROJECT" \
    --replication-policy=automatic --quiet
fi
if ! gcloud secrets versions list "$ADMISSION_OPERATOR_SECRET" --project="$PROJECT" \
  --filter='state=ENABLED' --format='value(name)' --limit=1 | grep -Eq '/versions/[0-9]+$'; then
  OPERATOR_SECRET_TMP="$(mktemp)"
  chmod 600 "$OPERATOR_SECRET_TMP"
  openssl rand -base64 48 > "$OPERATOR_SECRET_TMP"
  gcloud secrets versions add "$ADMISSION_OPERATOR_SECRET" --project="$PROJECT" \
    --data-file="$OPERATOR_SECRET_TMP" --quiet >/dev/null
  rm -f "$OPERATOR_SECRET_TMP"
fi
for SECRET_READER in "$COORDINATOR_SA" "$ADMISSION_OPERATOR_SA"; do
  gcloud secrets add-iam-policy-binding "$ADMISSION_OPERATOR_SECRET" --project="$PROJECT" \
    --member="serviceAccount:${SECRET_READER}" --role="roles/secretmanager.secretAccessor" \
    --condition=None --quiet >/dev/null
done

CONFIRM=SET-DRAIN-QUEUE-SAFE-BETA GCP_PROJECT="$PROJECT" GCP_REGION="$REGION" CLOUD_TASKS_DRAIN_QUEUE="$DRAIN_QUEUE" \
  "$REPO_ROOT/scripts/set-standard150-drain-policy.sh"

gcloud tasks queues add-iam-policy-binding "$DRAIN_QUEUE" --project="$PROJECT" --location="$REGION" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" --role="roles/cloudtasks.enqueuer" --quiet >/dev/null

for ROLE in roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${DEPLOYER_SA}" \
    --role="$ROLE" --condition=None --quiet >/dev/null
done
# The source deployer may attach only the coordinator runtime identity and the
# exact build identity resolved above; no project-wide Run Admin grant is used.
for TARGET_SA in "$COORDINATOR_SA" "$BUILD_SA"; do
  gcloud iam service-accounts add-iam-policy-binding "$TARGET_SA" --project="$PROJECT" \
    --member="serviceAccount:${DEPLOYER_SA}" --role="roles/iam.serviceAccountUser" --condition=None --quiet >/dev/null
done
# Build identity needs the documented source-build role.
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${BUILD_SA}" \
  --role="roles/run.builder" --condition=None --quiet >/dev/null

SOURCE_SHA="$SOURCE_SHA" CONFIRM="$SOURCE_SHA" CLOUD_BUILD_SERVICE_ACCOUNT="$BUILD_SA_RESOURCE" \
  GCP_PROJECT="$PROJECT" GCP_REGION="$REGION" ADMISSION_COORDINATOR_SERVICE="$COORDINATOR" \
  ADMISSION_COORDINATOR_RUNTIME_SA="$COORDINATOR_SA" FIRESTORE_DATABASE="$DATABASE" \
  ADMISSION_OPERATOR_SERVICE_ACCOUNT="$ADMISSION_OPERATOR_SA" \
  ADMISSION_OPERATOR_SIGNING_SECRET="$ADMISSION_OPERATOR_SECRET" \
  ADMISSION_OPERATOR_AUDIENCE="$ADMISSION_OPERATOR_AUDIENCE" \
  ADMISSION_OPERATOR_ID="$ADMISSION_OPERATOR_ID" \
  "$REPO_ROOT/scripts/deploy_admission_coordinator.sh"

gcloud run services add-iam-policy-binding "$COORDINATOR" --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/run.developer" --condition=None --quiet >/dev/null
gcloud run services add-iam-policy-binding "$COORDINATOR" --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:${ADMISSION_OPERATOR_SA}" --role="roles/run.invoker" --condition=None --quiet >/dev/null

if gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
  --filter="bindings.role=roles/run.admin AND bindings.members=serviceAccount:${DEPLOYER_SA}" \
  --format='value(bindings.role)' | grep -q .; then
  echo "Refusing completion: operator has project-wide roles/run.admin." >&2
  exit 2
fi

printf 'ADMISSION_BOOTSTRAP_COMPLETE\nsource_sha=%s\ncoordinator=%s\ndatabase=%s\ndrain_queue=%s\nbuild_service_account=%s\n' \
  "$SOURCE_SHA" "$COORDINATOR" "$DATABASE" "$DRAIN_QUEUE" "$BUILD_SA"
