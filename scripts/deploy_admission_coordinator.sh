#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${ADMISSION_COORDINATOR_SERVICE:-fixlist-scan-admission-coordinator}"
RUNTIME_SA="${ADMISSION_COORDINATOR_RUNTIME_SA:-fixlist-admission-coordinator@${PROJECT}.iam.gserviceaccount.com}"
DATABASE="${FIRESTORE_DATABASE:-fixlist-admission}"
COLLECTION="${ADMISSION_COLLECTION:-scan_admission}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BUILD_SA_INPUT="${CLOUD_BUILD_SERVICE_ACCOUNT:-}"
OPERATOR_SA="${ADMISSION_OPERATOR_SERVICE_ACCOUNT:-fixlist-admission-operator@${PROJECT}.iam.gserviceaccount.com}"
OPERATOR_SECRET="${ADMISSION_OPERATOR_SIGNING_SECRET:-fixlist-admission-operator-signing-key}"
OPERATOR_SECRET_VERSION="${ADMISSION_OPERATOR_SIGNING_VERSION:-}"
OPERATOR_AUDIENCE="${ADMISSION_OPERATOR_AUDIENCE:-https://fixlist-admission-operator}"
OPERATOR_ID="${ADMISSION_OPERATOR_ID:-fixlist-cloud-operator}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

gcloud config set project "$PROJECT" >/dev/null

normalize_build_sa() {
  local raw="$1"
  raw="${raw##*/}"
  [[ "$raw" == *@* ]] || { echo "Invalid Cloud Build service account: $1" >&2; exit 2; }
  BUILD_SA_EMAIL="$raw"
  BUILD_SA_RESOURCE="projects/${PROJECT}/serviceAccounts/${raw}"
}
if [[ -n "$BUILD_SA_INPUT" ]]; then
  normalize_build_sa "$BUILD_SA_INPUT"
else
  normalize_build_sa "$(gcloud builds get-default-service-account --project="$PROJECT" --format='value(serviceAccountEmail)')"
fi
gcloud iam service-accounts describe "$BUILD_SA_EMAIL" --project="$PROJECT" >/dev/null

echo "build_service_account=$BUILD_SA_EMAIL"

WORKER_JSON="$(mktemp)"
COORD_JSON="$(mktemp)"
HEALTH_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$COORD_JSON" "$HEALTH_JSON"' EXIT

gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"
read -r SIGNING_SECRET SIGNING_VERSION < <(python3 - "$WORKER_JSON" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]))
containers=v.get('spec',{}).get('template',{}).get('spec',{}).get('containers',[])
if not containers: raise SystemExit('worker container missing')
for item in containers[0].get('env',[]):
    if item.get('name')=='SCAN_EVIDENCE_SIGNING_KEY':
        ref=item.get('valueFrom',{}).get('secretKeyRef',{})
        name=str(ref.get('name') or ''); version=str(ref.get('key') or '')
        if not name or not version.isdigit(): raise SystemExit('worker signing secret is not numeric-pinned')
        print(name,version); break
else: raise SystemExit('worker signing secret missing')
PY
)

if [[ "$OPERATOR_SECRET" == "$SIGNING_SECRET" ]]; then
  echo "Refusing deployment: operator and scan-evidence secret references must differ." >&2
  exit 2
fi
# The release operator is intentionally not allowed to enumerate Secret
# Manager versions. Reuse the exact numeric reference already pinned on the
# deployed coordinator before falling back to owner/bootstrap discovery.
if [[ -z "$OPERATOR_SECRET_VERSION" ]] && gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format=json > "$COORD_JSON" 2>/dev/null; then
  OPERATOR_SECRET_VERSION="$(python3 - "$COORD_JSON" "$OPERATOR_SECRET" <<'PY'
import json, sys

value = json.load(open(sys.argv[1]))
expected_name = sys.argv[2]
containers = value.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
if containers:
    for item in containers[0].get('env', []):
        if item.get('name') != 'ADMISSION_OPERATOR_SIGNING_KEY':
            continue
        ref = item.get('valueFrom', {}).get('secretKeyRef', {})
        name = str(ref.get('name') or '')
        version = str(ref.get('key') or '')
        if name == expected_name and version.isdigit():
            print(version)
        break
PY
)"
fi
if [[ -z "$OPERATOR_SECRET_VERSION" ]]; then
  OPERATOR_SECRET_VERSION="$(gcloud secrets versions list "$OPERATOR_SECRET" \
    --project="$PROJECT" --filter='state=ENABLED' --sort-by='~createTime' \
    --limit=1 --format='value(name)' | sed -n 's#^.*/versions/\([0-9][0-9]*\)$#\1#p')"
fi
if ! printf '%s' "$OPERATOR_SECRET_VERSION" | grep -Eq '^[0-9]+$'; then
  echo "Refusing deployment: operator signing secret has no enabled numeric version." >&2
  exit 2
fi
gcloud secrets versions describe "$OPERATOR_SECRET_VERSION" --secret="$OPERATOR_SECRET" \
  --project="$PROJECT" --format='value(state)' | grep -qx ENABLED
gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT" >/dev/null
printf 'coordinator_signing_refs=verified_numeric_pinned_and_distinct\n'

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$REPO_ROOT/admission-coordinator" \
  --build-service-account="$BUILD_SA_RESOURCE" \
  --service-account="$RUNTIME_SA" \
  --no-invoker-iam-check \
  --ingress=all \
  --memory=256Mi \
  --cpu=1 \
  --concurrency=20 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="FIRESTORE_PROJECT=$PROJECT,FIRESTORE_DATABASE=$DATABASE,ADMISSION_COLLECTION=$COLLECTION,ADMISSION_LEASE_SECONDS=2400,ADMISSION_MAX_CLOCK_SKEW_SECONDS=300,ADMISSION_MAX_BODY_BYTES=65536,FIXLIST_COORDINATOR_SOURCE_SHA=$SOURCE_SHA,ADMISSION_OPERATOR_SERVICE_ACCOUNT=$OPERATOR_SA,ADMISSION_OPERATOR_AUDIENCE=$OPERATOR_AUDIENCE,ADMISSION_OPERATOR_ID=$OPERATOR_ID" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=${SIGNING_SECRET}:${SIGNING_VERSION},ADMISSION_OPERATOR_SIGNING_KEY=${OPERATOR_SECRET}:${OPERATOR_SECRET_VERSION}" \
  --quiet

gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format=json > "$COORD_JSON"
COORD_URL="$(python3 - "$COORD_JSON" "$RUNTIME_SA" "$DATABASE" "$COLLECTION" "$SOURCE_SHA" "$SIGNING_SECRET" "$SIGNING_VERSION" "$OPERATOR_SA" "$OPERATOR_AUDIENCE" "$OPERATOR_ID" "$OPERATOR_SECRET" "$OPERATOR_SECRET_VERSION" <<'PY'
import json,sys
path,runtime,database,collection,source_sha,secret,version,operator_sa,audience,operator_id,operator_secret,operator_version=sys.argv[1:]
v=json.load(open(path)); url=str(v.get('status',{}).get('url') or '')
if not url.startswith('https://'): raise SystemExit('coordinator url missing')
t=v.get('spec',{}).get('template',{}).get('spec',{})
if t.get('serviceAccountName')!=runtime: raise SystemExit('coordinator runtime SA mismatch')
c=(t.get('containers') or [{}])[0]; env={i.get('name'):i for i in c.get('env',[])}
expected={'FIRESTORE_DATABASE':database,'ADMISSION_COLLECTION':collection,'ADMISSION_LEASE_SECONDS':'2400','FIXLIST_COORDINATOR_SOURCE_SHA':source_sha,'ADMISSION_OPERATOR_SERVICE_ACCOUNT':operator_sa,'ADMISSION_OPERATOR_AUDIENCE':audience,'ADMISSION_OPERATOR_ID':operator_id}
for k,val in expected.items():
    if str(env.get(k,{}).get('value') or '')!=val: raise SystemExit('coordinator env mismatch: '+k)
ref=env.get('SCAN_EVIDENCE_SIGNING_KEY',{}).get('valueFrom',{}).get('secretKeyRef',{})
if str(ref.get('name') or '')!=secret or str(ref.get('key') or '')!=version: raise SystemExit('coordinator secret ref mismatch')
operator_ref=env.get('ADMISSION_OPERATOR_SIGNING_KEY',{}).get('valueFrom',{}).get('secretKeyRef',{})
if str(operator_ref.get('name') or '')!=operator_secret or str(operator_ref.get('key') or '')!=operator_version: raise SystemExit('coordinator operator secret ref mismatch')
if operator_secret==secret: raise SystemExit('coordinator signing domains reuse one secret')
print(url)
PY
)"

curl --fail --silent --show-error --max-time 20 "$COORD_URL/health" > "$HEALTH_JSON"
python3 - "$HEALTH_JSON" "$SOURCE_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); expected=sys.argv[2]
assert v.get('ok') is True, v
assert v.get('service')=='fixlist-admission-coordinator', v
assert v.get('source_sha')==expected, v
assert int(v.get('lease_seconds') or 0)==2400, v
print('Coordinator health provenance verified.')
PY

HTTP_CODE="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 20 \
  -X POST -H 'content-type: application/json' --data '{}' "$COORD_URL/claim" || true)"
if [[ "$HTTP_CODE" != "401" ]]; then
  echo "Refusing completion: unsigned coordinator mutation returned $HTTP_CODE, expected 401." >&2
  exit 2
fi
OPERATOR_HTTP_CODE="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 20 \
  -X POST -H 'content-type: application/json' --data '{}' "$COORD_URL/ops/barrier/status" || true)"
if [[ "$OPERATOR_HTTP_CODE" != "401" ]]; then
  echo "Refusing completion: unauthenticated operator request returned $OPERATOR_HTTP_CODE, expected 401." >&2
  exit 2
fi
printf 'ADMISSION_COORDINATOR_READY=%s\n' "$COORD_URL"
printf 'ADMISSION_COORDINATOR_SOURCE_SHA=%s\n' "$SOURCE_SHA"
