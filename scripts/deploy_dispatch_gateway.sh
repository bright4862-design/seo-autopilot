#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-${PROJECT:-seo-autopilot-501517}}"
REGION="${GCP_REGION:-${REGION:-europe-west1}}"
WORKER="${CLOUD_RUN_SERVICE:-${WORKER:-fixlist-standard150-worker}}"
QUEUE="${CLOUD_TASKS_QUEUE:-fixlist-standard150}"
DRAIN_QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
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

# The claimed SOURCE_SHA must be the exact clean checkout whose bytes are sent
# to source deploy. A label without this guard is not provenance.
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"

BUILD_SA_RAW="${CLOUD_BUILD_SERVICE_ACCOUNT:-$(gcloud builds get-default-service-account --project="$PROJECT" --format='value(serviceAccountEmail)')}"
BUILD_SA_EMAIL="${BUILD_SA_RAW##*/}"
[[ "$BUILD_SA_EMAIL" == *@* ]] || { echo "Refusing gateway deployment: invalid Cloud Build SA." >&2; exit 2; }
BUILD_SA_RESOURCE="projects/${PROJECT}/serviceAccounts/${BUILD_SA_EMAIL}"
gcloud iam service-accounts describe "$BUILD_SA_EMAIL" --project="$PROJECT" >/dev/null
echo "build_service_account=$BUILD_SA_EMAIL"
for file in main.py requirements.txt Dockerfile test_gateway.py; do
  test -f "$SOURCE_DIR/$file" || { echo "Missing canonical gateway source: $SOURCE_DIR/$file" >&2; exit 2; }
done

gcloud config set project "$PROJECT" >/dev/null

WORKER_JSON="$(mktemp)"
GATEWAY_JSON="$(mktemp)"
HEALTH_JSON="$(mktemp)"
PRE_JSON="$(mktemp)"
REVISION_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$GATEWAY_JSON" "$HEALTH_JSON" "$PRE_JSON" "$REVISION_JSON"' EXIT

# Reads the revision that actually holds traffic, not the desired template.
# spec.template is whatever the last deploy asked for; status.traffic is what
# customers reach. Conflating the two let a August revision serve for weeks
# while every deploy reported success.
serving_revision_from() {
  python3 -c 'import json,sys
service = json.load(open(sys.argv[1], encoding="utf-8"))
best_name, best_percent = "", -1
for item in (service.get("status", {}).get("traffic") or []):
    percent = int(item.get("percent") or 0)
    if percent > best_percent:
        best_name, best_percent = str(item.get("revisionName") or ""), percent
print(best_name)' "$1"
}

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
DRAIN_QUEUE_PATH="projects/${PROJECT}/locations/${REGION}/queues/${DRAIN_QUEUE}"
if [[ "$QUEUE_PATH" == "$DRAIN_QUEUE_PATH" ]]; then
  echo "Refusing gateway deployment: scan and drain queues must be distinct." >&2
  exit 2
fi
WORKER_URL="${WORKER_ORIGIN}/scan-job"

echo "worker_origin=$WORKER_ORIGIN"
echo "queue_path=$QUEUE_PATH"
echo "drain_queue_path=$DRAIN_QUEUE_PATH"
echo "signing_secret_ref=${SIGNING_SECRET}:${SIGNING_VERSION} (value not read)"
echo "source_sha=$SOURCE_SHA"

# Creating a public Cloud Run service requires run.services.setIamPolicy. The
# authenticated owner bootstrap performs that one-time creation. After the
# service exists, the exact public-invoker annotation is preserved and future
# WIF deployments need only service-scoped Cloud Run Developer access.
PUBLIC_ARGS=()
PRE_DEPLOY_REVISION=""
if gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" --format=json > "$PRE_JSON" 2>/dev/null; then
  echo "Existing gateway detected; preserving its current invoker-IAM setting."
  PRE_DEPLOY_REVISION="$(serving_revision_from "$PRE_JSON")"
  echo "pre_deploy_serving_revision=${PRE_DEPLOY_REVISION:-<none>}"
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
  --build-service-account="$BUILD_SA_RESOURCE" \
  --service-account="$DISPATCHER_SA" \
  "${PUBLIC_ARGS[@]}" \
  --ingress=all \
  --memory=256Mi \
  --cpu=1 \
  --concurrency=20 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="SCAN_TASKS_QUEUE_PATH=$QUEUE_PATH,SCAN_DRAIN_QUEUE_PATH=$DRAIN_QUEUE_PATH,SCAN_WORKER_URL=$WORKER_URL,TASKS_INVOKER_SERVICE_ACCOUNT=$INVOKER_SA,DISPATCH_MAX_CLOCK_SKEW_SECONDS=300,DISPATCH_MAX_BODY_BYTES=262144,FIXLIST_GATEWAY_SOURCE_SHA=$SOURCE_SHA" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=${SIGNING_SECRET}:${SIGNING_VERSION}" \
  --quiet

echo
echo "=== Promote the exact revision this deployment created ==="
gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$GATEWAY_JSON"

NEW_REVISION="$(python3 -c 'import json,sys
service = json.load(open(sys.argv[1], encoding="utf-8"))
print(str(service.get("status", {}).get("latestCreatedRevisionName") or ""))' "$GATEWAY_JSON")"

if [[ -z "$NEW_REVISION" ]]; then
  echo "Refusing gateway deployment: no latestCreatedRevisionName after deploy." >&2
  exit 2
fi
echo "created_revision=$NEW_REVISION"

if [[ -n "$PRE_DEPLOY_REVISION" && "$NEW_REVISION" == "$PRE_DEPLOY_REVISION" ]]; then
  echo "Refusing gateway deployment: deploy created no new revision (still $NEW_REVISION)." >&2
  exit 2
fi

# The traffic spec can be pinned by name to an older revision. While it is,
# gcloud run deploy builds correctly, creates a Ready revision, routes nothing
# to it, and Cloud Run retires it seconds later -- while the pinned revision
# keeps serving and the deploy still exits 0. Promotion is therefore explicit
# and is never inferred from a successful deploy.
gcloud run services update-traffic "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --to-revisions="${NEW_REVISION}=100" \
  --quiet

echo
echo "=== Verify deployed gateway ==="
gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$GATEWAY_JSON"

gcloud run revisions describe "$NEW_REVISION" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$REVISION_JSON"

GATEWAY_URL="$(python3 - "$GATEWAY_JSON" "$DISPATCHER_SA" "$QUEUE_PATH" "$DRAIN_QUEUE_PATH" "$WORKER_URL" "$INVOKER_SA" "$SOURCE_SHA" "$SIGNING_SECRET" "$SIGNING_VERSION" <<'PY'
import json, sys
(path, expected_sa, queue_path, drain_queue_path, worker_url, invoker_sa, source_sha, secret_name, secret_version) = sys.argv[1:]
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
    'SCAN_DRAIN_QUEUE_PATH': drain_queue_path,
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

SERVING_REVISION="$(serving_revision_from "$GATEWAY_JSON")"
if [[ "$SERVING_REVISION" != "$NEW_REVISION" ]]; then
  echo "Refusing gateway deployment: traffic serves '$SERVING_REVISION', not the revision just created '$NEW_REVISION'." >&2
  exit 2
fi

python3 - "$GATEWAY_JSON" "$REVISION_JSON" "$NEW_REVISION" "$SOURCE_SHA" <<'PYCHECK'
import json, sys
service_path, revision_path, expected_revision, source_sha = sys.argv[1:]
with open(service_path, encoding="utf-8") as handle:
    service = json.load(handle)
with open(revision_path, encoding="utf-8") as handle:
    revision = json.load(handle)

percent = sum(
    int(item.get("percent") or 0)
    for item in (service.get("status", {}).get("traffic") or [])
    if item.get("revisionName") == expected_revision
)
if percent != 100:
    raise SystemExit(f"Serving traffic on {expected_revision} is {percent}%, expected 100%")

# The image the revision actually pulled, not the image the template asked for.
digest = str(revision.get("status", {}).get("imageDigest") or "")
if "@sha256:" not in digest:
    raise SystemExit(f"Revision {expected_revision} has no immutable image digest")
template_image = str(
    service.get("spec", {}).get("template", {}).get("spec", {})
    .get("containers", [{}])[0].get("image") or ""
)
if template_image != digest:
    raise SystemExit(
        f"Serving digest {digest} does not equal the image this deployment built {template_image}"
    )

# The serving revision's own environment, not the desired template's.
env = {
    item.get("name"): str(item.get("value") or "")
    for item in (revision.get("spec", {}).get("containers", [{}])[0].get("env", []) or [])
}
if env.get("FIXLIST_GATEWAY_SOURCE_SHA") != source_sha:
    raise SystemExit(
        "Serving revision FIXLIST_GATEWAY_SOURCE_SHA is "
        f"{env.get('FIXLIST_GATEWAY_SOURCE_SHA')!r}, expected {source_sha!r}"
    )
print(f"serving_revision={expected_revision}")
print(f"serving_image_digest={digest}")
PYCHECK
curl --fail --silent --show-error --retry 12 --retry-delay 3 --max-time 20 \
  "$GATEWAY_URL/health" > "$HEALTH_JSON"
# Pinned to the constant the deployed source declares, so the assertion cannot
# drift from the code it is meant to prove.
EXPECTED_CONTRACT_VERSION="$(python3 -c 'import re,sys
src = open(sys.argv[1], encoding="utf-8").read()
found = re.search(r"^GATEWAY_CONTRACT_VERSION\s*=\s*\"([^\"]+)\"", src, re.M)
print(found.group(1) if found else "")' "$SOURCE_DIR/main.py")"
if [[ -z "$EXPECTED_CONTRACT_VERSION" ]]; then
  echo "Refusing gateway deployment: cannot read GATEWAY_CONTRACT_VERSION from source." >&2
  exit 2
fi

RUNTIME_SOURCE_SHA="$(python3 - "$HEALTH_JSON" "$QUEUE_PATH" "$DRAIN_QUEUE_PATH" "$WORKER_ORIGIN" "$EXPECTED_CONTRACT_VERSION" "$SOURCE_SHA" <<'PYHEALTH'
import json, sys
path, queue_path, drain_queue_path, worker_origin, contract_version, source_sha = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    value = json.load(handle)
def require(name, actual, expected):
    if actual != expected:
        raise SystemExit(f"Gateway /health {name} is {actual!r}, expected {expected!r}")
require("ok", value.get("ok"), True)
require("service", value.get("service"), "fixlist-dispatch-gateway")
require("queue", value.get("queue"), queue_path)
require("drain_queue", value.get("drain_queue"), drain_queue_path)
require("worker_origin", value.get("worker_origin"), worker_origin)
# Runtime identity. These two are the only evidence that the bytes answering
# this request are the bytes this deployment built.
require("contract_version", value.get("contract_version"), contract_version)
require("source_sha", value.get("source_sha"), source_sha)
print(value["source_sha"])
PYHEALTH
)"

if [[ "$RUNTIME_SOURCE_SHA" != "$SOURCE_SHA" ]]; then
  echo "Refusing gateway deployment: runtime source SHA $RUNTIME_SOURCE_SHA != $SOURCE_SHA" >&2
  exit 2
fi
echo "Gateway health contract verified."

echo
echo "GATEWAY_READY=$GATEWAY_URL"
echo "GATEWAY_PRE_DEPLOY_REVISION=${PRE_DEPLOY_REVISION:-<none>}"
echo "GATEWAY_SERVING_REVISION=$SERVING_REVISION"
echo "GATEWAY_CONTRACT_VERSION=$EXPECTED_CONTRACT_VERSION"
# Read back from the live /health response, never echoed from the input.
echo "GATEWAY_SOURCE_SHA=$RUNTIME_SOURCE_SHA"
