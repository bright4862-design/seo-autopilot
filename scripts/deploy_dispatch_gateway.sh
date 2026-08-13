#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-${PROJECT:-seo-autopilot-501517}}"
REGION="${GCP_REGION:-${REGION:-europe-west1}}"
WORKER="${CLOUD_RUN_SERVICE:-${WORKER:-fixlist-standard150-worker}}"
QUEUE="${CLOUD_TASKS_QUEUE:-fixlist-standard150}"
GATEWAY="${GATEWAY_SERVICE:-${GATEWAY:-fixlist-dispatch-gateway}}"
DISPATCHER_SA="${GATEWAY_RUNTIME_SERVICE_ACCOUNT:-${DISPATCHER_SA:-fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com}}"
INVOKER_SA="${TASKS_INVOKER_SERVICE_ACCOUNT:-${INVOKER_SA:-fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com}}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"

if ! printf '%s' "$SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "Refusing gateway deployment: SOURCE_SHA must be an exact 40-character lowercase commit SHA." >&2
  exit 2
fi
if [[ "$CONFIRM" != "$SOURCE_SHA" ]]; then
  echo "Refusing gateway deployment: confirmation must equal exact source SHA $SOURCE_SHA" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/dispatch-gateway"
for file in main.py requirements.txt Dockerfile test_gateway.py; do
  test -f "$SOURCE_DIR/$file" || { echo "Missing canonical gateway source: $SOURCE_DIR/$file" >&2; exit 2; }
done

gcloud config set project "$PROJECT" >/dev/null

WORKER_JSON="$(mktemp)"
GATEWAY_JSON="$(mktemp)"
HEALTH_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$GATEWAY_JSON" "$HEALTH_JSON"' EXIT

echo "=== Resolve immutable live worker inputs ==="
gcloud run services describe "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
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

QUEUE_PATH="projects/${PROJECT}/locations/${REGION}/queues/${QUEUE}"
WORKER_URL="${WORKER_ORIGIN}/scan-job"

echo "worker_origin=$WORKER_ORIGIN"
echo "queue_path=$QUEUE_PATH"
echo "signing_secret_ref=${SIGNING_SECRET}:${SIGNING_VERSION} (value not read)"
echo "source_sha=$SOURCE_SHA"

# Creating a public Cloud Run service requires run.services.setIamPolicy. The
# authenticated owner bootstrap performs that one-time creation. After the
# service exists, the exact public-invoker annotation is preserved and future
# WIF deployments need only service-scoped Cloud Run Developer access.
PUBLIC_ARGS=()
if gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" >/dev/null 2>&1; then
  echo "Existing gateway detected; preserving its current invoker-IAM setting."
else
  echo "Gateway does not exist; creating it with the Invoker IAM check disabled."
  PUBLIC_ARGS+=(--no-invoker-iam-check)
fi

echo
echo "=== Deploy canonical keyless gateway ==="
gcloud run deploy "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$SOURCE_DIR" \
  --service-account="$DISPATCHER_SA" \
  "${PUBLIC_ARGS[@]}" \
  --ingress=all \
  --memory=256Mi \
  --cpu=1 \
  --concurrency=20 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="SCAN_TASKS_QUEUE_PATH=$QUEUE_PATH,SCAN_WORKER_URL=$WORKER_URL,TASKS_INVOKER_SERVICE_ACCOUNT=$INVOKER_SA,DISPATCH_MAX_CLOCK_SKEW_SECONDS=300,DISPATCH_MAX_BODY_BYTES=262144,FIXLIST_GATEWAY_SOURCE_SHA=$SOURCE_SHA" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=${SIGNING_SECRET}:${SIGNING_VERSION}" \
  --quiet

echo
echo "=== Verify deployed gateway ==="
gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$GATEWAY_JSON"

GATEWAY_URL="$(python3 - "$GATEWAY_JSON" "$DISPATCHER_SA" "$QUEUE_PATH" "$WORKER_URL" "$INVOKER_SA" "$SOURCE_SHA" "$SIGNING_SECRET" "$SIGNING_VERSION" <<'PY'
import json, sys
(path, expected_sa, queue_path, worker_url, invoker_sa, source_sha, secret_name, secret_version) = sys.argv[1:]
with open(path, encoding='utf-8') as handle:
    service = json.load(handle)
url = str(service.get('status', {}).get('url') or '').strip()
if not url.startswith('https://'):
    raise SystemExit('Gateway did not publish a canonical HTTPS URL')
template = service.get('spec', {}).get('template', {}).get('spec', {})
if template.get('serviceAccountName') != expected_sa:
    raise SystemExit('Gateway runtime service-account mismatch')
containers = template.get('containers', [])
if not containers:
    raise SystemExit('Gateway has no container configuration')
env = {item.get('name'): item for item in containers[0].get('env', [])}
expected_values = {
    'SCAN_TASKS_QUEUE_PATH': queue_path,
    'SCAN_WORKER_URL': worker_url,
    'TASKS_INVOKER_SERVICE_ACCOUNT': invoker_sa,
    'DISPATCH_MAX_CLOCK_SKEW_SECONDS': '300',
    'DISPATCH_MAX_BODY_BYTES': '262144',
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
    raise SystemExit('Gateway invoker IAM check is not disabled')
print(url)
PY
)"

test -n "$GATEWAY_URL"
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
