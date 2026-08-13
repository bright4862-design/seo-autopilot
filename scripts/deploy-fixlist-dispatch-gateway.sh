#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"
: "${CLOUD_TASKS_QUEUE:?CLOUD_TASKS_QUEUE is required}"
: "${TASKS_INVOKER_SERVICE_ACCOUNT:?TASKS_INVOKER_SERVICE_ACCOUNT is required}"
: "${GATEWAY_SERVICE:?GATEWAY_SERVICE is required}"
: "${GATEWAY_RUNTIME_SERVICE_ACCOUNT:?GATEWAY_RUNTIME_SERVICE_ACCOUNT is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"

CONFIRM="${CONFIRM:-}"
if [[ "$CONFIRM" != "$SOURCE_SHA" ]]; then
  echo "Refusing gateway deployment: confirmation must equal exact source SHA $SOURCE_SHA" >&2
  exit 2
fi

if ! printf '%s' "$SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "Refusing gateway deployment: SOURCE_SHA is not an exact 40-character commit SHA." >&2
  exit 2
fi

SOURCE_DIR="ops/fixlist-dispatch-gateway"
for file in main.py requirements.txt Dockerfile test_gateway.py; do
  test -f "$SOURCE_DIR/$file" || { echo "Missing gateway source: $SOURCE_DIR/$file" >&2; exit 2; }
done

gcloud config set project "$GCP_PROJECT" >/dev/null

WORKER_JSON="$(mktemp)"
GATEWAY_JSON="$(mktemp)"
HEALTH_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$GATEWAY_JSON" "$HEALTH_JSON"' EXIT

echo "=== Resolve immutable live worker inputs ==="
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format=json > "$WORKER_JSON"

read -r WORKER_ORIGIN SIGNING_SECRET SIGNING_VERSION < <(python3 - "$WORKER_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    service = json.load(handle)
origin = str(service.get('status', {}).get('url') or '').strip().rstrip('/')
if not origin.startswith('https://'):
    raise SystemExit('Worker canonical URL is missing or invalid')
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
        raise SystemExit('Worker signing secret must be pinned to an exact Secret Manager version')
    print(origin, name, version)
    break
else:
    raise SystemExit('Worker does not reference SCAN_EVIDENCE_SIGNING_KEY')
PY
)

QUEUE_PATH="projects/${GCP_PROJECT}/locations/${GCP_REGION}/queues/${CLOUD_TASKS_QUEUE}"
WORKER_URL="${WORKER_ORIGIN}/scan-job"

echo "worker_origin=$WORKER_ORIGIN"
echo "queue_path=$QUEUE_PATH"
echo "signing_secret_ref=${SIGNING_SECRET}:${SIGNING_VERSION} (value not read)"

echo
echo "=== Deploy constrained keyless gateway from exact source $SOURCE_SHA ==="
gcloud run deploy "$GATEWAY_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --source="$SOURCE_DIR" \
  --service-account="$GATEWAY_RUNTIME_SERVICE_ACCOUNT" \
  --no-invoker-iam-check \
  --ingress=all \
  --memory=256Mi \
  --cpu=1 \
  --concurrency=20 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="SCAN_TASKS_QUEUE_PATH=$QUEUE_PATH,SCAN_WORKER_URL=$WORKER_URL,TASKS_INVOKER_SERVICE_ACCOUNT=$TASKS_INVOKER_SERVICE_ACCOUNT,DISPATCH_MAX_CLOCK_SKEW_SECONDS=300,FIXLIST_GATEWAY_SOURCE_SHA=$SOURCE_SHA" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=${SIGNING_SECRET}:${SIGNING_VERSION}" \
  --quiet

echo
echo "=== Verify deployed gateway configuration ==="
gcloud run services describe "$GATEWAY_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format=json > "$GATEWAY_JSON"

GATEWAY_URL="$(python3 - "$GATEWAY_JSON" "$GATEWAY_RUNTIME_SERVICE_ACCOUNT" "$QUEUE_PATH" "$WORKER_URL" "$TASKS_INVOKER_SERVICE_ACCOUNT" "$SOURCE_SHA" "$SIGNING_SECRET" "$SIGNING_VERSION" <<'PY'
import json, sys
(path, expected_sa, queue_path, worker_url, invoker_sa, source_sha, secret_name, secret_version) = sys.argv[1:]
with open(path, encoding='utf-8') as handle:
    service = json.load(handle)
url = str(service.get('status', {}).get('url') or '').strip()
if not url.startswith('https://'):
    raise SystemExit('Gateway did not publish a canonical HTTPS URL')
template = service.get('spec', {}).get('template', {}).get('spec', {})
if template.get('serviceAccountName') != expected_sa:
    raise SystemExit('Gateway runtime service account mismatch')
containers = template.get('containers', [])
if not containers:
    raise SystemExit('Gateway has no container configuration')
env = {item.get('name'): item for item in containers[0].get('env', [])}
expected_values = {
    'SCAN_TASKS_QUEUE_PATH': queue_path,
    'SCAN_WORKER_URL': worker_url,
    'TASKS_INVOKER_SERVICE_ACCOUNT': invoker_sa,
    'DISPATCH_MAX_CLOCK_SKEW_SECONDS': '300',
    'FIXLIST_GATEWAY_SOURCE_SHA': source_sha,
}
for name, value in expected_values.items():
    if str(env.get(name, {}).get('value') or '') != value:
        raise SystemExit(f'Gateway environment mismatch: {name}')
ref = env.get('SCAN_EVIDENCE_SIGNING_KEY', {}).get('valueFrom', {}).get('secretKeyRef', {})
if str(ref.get('name') or '') != secret_name or str(ref.get('key') or '') != secret_version:
    raise SystemExit('Gateway signing-secret reference mismatch')
annotations = service.get('metadata', {}).get('annotations', {}) or {}
if str(annotations.get('run.googleapis.com/invoker-iam-disabled', '')).lower() != 'true':
    raise SystemExit('Gateway invoker IAM check is still enabled; Base44 could not reach it anonymously')
print(url)
PY
)"

test -n "$GATEWAY_URL"

echo "gateway_url=$GATEWAY_URL"
curl --fail --silent --show-error --retry 12 --retry-delay 3 --max-time 20 \
  "$GATEWAY_URL/health" > "$HEALTH_JSON"
python3 - "$HEALTH_JSON" "$QUEUE_PATH" "$WORKER_ORIGIN" <<'PY'
import json, sys
path, queue_path, worker_origin = sys.argv[1:]
with open(path, encoding='utf-8') as handle:
    value = json.load(handle)
assert value.get('ok') is True
assert value.get('service') == 'fixlist-dispatch-gateway'
assert value.get('queue') == queue_path
assert value.get('worker_origin') == worker_origin
print('Gateway health contract verified.')
PY

echo
echo "GATEWAY_READY=$GATEWAY_URL"
echo "GATEWAY_SOURCE_SHA=$SOURCE_SHA"
