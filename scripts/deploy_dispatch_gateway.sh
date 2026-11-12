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

# The claimed SOURCE_SHA must be the exact clean checkout whose bytes are sent
# to source deploy. A label without this guard is not provenance.
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"

# Staging is a distinct, bounded opt-in. Validate before any cloud access;
# a normal deployment explicitly restores monolith mode and removes its cohort.
STAGED_PLAN="$(python3 "$REPO_ROOT/scripts/gateway_staged_config.py" \
  --config "${GATEWAY_STAGED_CONFIG:-off}" --owners "${GATEWAY_STAGED_OWNER_IDS:-}" \
  --canary-owners "${GATEWAY_CANARY_OWNER_USER_IDS:-}")"
read -r GATEWAY_PIPELINE_MODE STAGED_OWNER_COUNT STAGED_COHORT_SHA < <(python3 -c \
  'import json,sys; p=json.loads(sys.argv[1]); print(p["pipeline_mode"],p["staged_owner_count"],p["staged_owner_cohort_sha256"])' "$STAGED_PLAN")
STAGED_OWNER_IDS="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["owner_ids"])' "$STAGED_PLAN")"
if [[ "$GATEWAY_PIPELINE_MODE" == staged ]]; then
  [[ -n "${GATEWAY_CANARY_REVISION:-}" ]] || { echo 'Staging requires an exact canary revision.' >&2; exit 2; }
  [[ "${GATEWAY_STAGED_CONFIRM:-}" == "ENABLE-STAGED-GATEWAY:${SOURCE_SHA}:${STAGED_COHORT_SHA}" ]] || {
    echo 'Staging requires exact source and cohort confirmation.' >&2; exit 2;
  }
fi

# The gateway uses the canonical pure comparison library from scanner-api. Build
# a minimal context from this exact committed tree, never maintained copies or
# the full scanner/worker image. gcloud source deploy requires a root Dockerfile.
SOURCE_ARCHIVE_DIR="$(mktemp -d)"
trap 'rm -rf "$SOURCE_ARCHIVE_DIR"' EXIT
SOURCE_DIR="$SOURCE_ARCHIVE_DIR/context"
bash "$REPO_ROOT/scripts/package_dispatch_gateway.sh" "$SOURCE_SHA" "$SOURCE_DIR"

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
CREATED_JSON="$(mktemp)"
GATEWAY_ROLLBACK_BASELINE="$(mktemp)"
PRE_REVISION_JSON="$(mktemp)"
GATEWAY_PROMOTION_ATTEMPTED=0
GATEWAY_DEPLOY_VERIFIED=0
source "$REPO_ROOT/scripts/lib/gateway-rollback.sh"
finish_gateway_deploy() {
  local status=$?
  trap - EXIT
  set +e
  gateway_rollback_on_failure "$status"
  status=$?
  rm -f "$WORKER_JSON" "$GATEWAY_JSON" "$HEALTH_JSON" "$PRE_JSON" "$REVISION_JSON" "$CREATED_JSON" "$GATEWAY_ROLLBACK_BASELINE" "$PRE_REVISION_JSON"
  rm -rf "$SOURCE_ARCHIVE_DIR"
  exit "$status"
}
trap finish_gateway_deploy EXIT

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

# Creating a public Cloud Run service requires run.services.setIamPolicy. The
# authenticated owner bootstrap performs that one-time creation. After the
# service exists, the exact public-invoker annotation is preserved and future
# WIF deployments need only service-scoped Cloud Run Developer access.
PUBLIC_ARGS=()
# --no-traffic is valid only for an existing service; first creation must
# take traffic, and has no previous revision to roll back to anyway.
TRAFFIC_ARGS=()
PRE_DEPLOY_REVISION=""
if gcloud run services describe "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" --format=json > "$PRE_JSON" 2>/dev/null; then
  echo "Existing gateway detected; preserving its current invoker-IAM setting."
  TRAFFIC_ARGS+=(--no-traffic)
  PRE_DEPLOY_REVISION="$(serving_revision_from "$PRE_JSON")"
  echo "pre_deploy_serving_revision=${PRE_DEPLOY_REVISION:-<none>}"
else
  echo "Gateway does not exist; creating it with the Invoker IAM check disabled."
  PUBLIC_ARGS+=(--no-invoker-iam-check)
fi

# A rollback target is proven before deployment, rather than discovered only
# after a failure. Save no keys: this captures public /health and revision IDs.
if [[ -n "$PRE_DEPLOY_REVISION" ]]; then
  gcloud run revisions describe "$PRE_DEPLOY_REVISION" --project="$PROJECT" --region="$REGION" --format=json > "$PRE_REVISION_JSON"
  GATEWAY_ROLLBACK_SOURCE_SHA="$(python3 - "$PRE_REVISION_JSON" <<'PY'
import json, sys
revision=json.load(open(sys.argv[1]))
print(next((str(e.get('value') or '') for e in revision.get('spec',{}).get('containers',[{}])[0].get('env',[])
            if e.get('name')=='FIXLIST_GATEWAY_SOURCE_SHA'), ''))
PY
)"
  GATEWAY_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",{}).get("url", ""))' "$PRE_JSON")"
  [[ "$GATEWAY_URL" == https://* ]] || { echo 'Previous gateway URL is missing.' >&2; exit 2; }
  # Rollback keeps its own copy: the post-promotion check below reassigns
  # GATEWAY_URL from a heredoc, and a failure there leaves it empty.
  GATEWAY_ROLLBACK_URL="$GATEWAY_URL"
  curl --fail --silent --show-error --max-time 20 "$GATEWAY_ROLLBACK_URL/health" > "$GATEWAY_ROLLBACK_BASELINE"
  python3 "$REPO_ROOT/scripts/verify_gateway_rollback.py" \
    --service-json "$PRE_JSON" --revision-json "$PRE_REVISION_JSON" \
    --health-json "$GATEWAY_ROLLBACK_BASELINE" --baseline-json "$GATEWAY_ROLLBACK_BASELINE" \
    --expected-revision "$PRE_DEPLOY_REVISION" --expected-source-sha "$GATEWAY_ROLLBACK_SOURCE_SHA"
elif [[ -n "${GATEWAY_CANARY_REVISION:-}" || -n "${GATEWAY_CANARY_OWNER_USER_IDS:-}" ]]; then
  echo 'Owner canary requires a verified existing gateway rollback target.' >&2; exit 2
fi
if [[ "$GATEWAY_PIPELINE_MODE" == staged ]]; then
  # First deploy and verify the zero-owner revision. Enabling staging is then
  # a separate deployment with its own exact source/cohort confirmation.
  python3 - "$GATEWAY_ROLLBACK_BASELINE" "$SOURCE_SHA" <<'PY'
import hashlib,json,sys
previous=json.load(open(sys.argv[1]))
empty_hash=hashlib.sha256(b'[]').hexdigest()
if (previous.get('source_sha') != sys.argv[2]
        or previous.get('pipeline_mode') != 'monolith' or previous.get('staged_owner_count') != 0
        or previous.get('staged_owner_cohort_sha256') != empty_hash):
    raise SystemExit('Staging requires a freshly verified zero-owner gateway baseline')
PY
fi

# Optional owner-only release canary. Off unless BOTH an exact zero-traffic
# tagged worker revision and an owner allowlist are supplied. The canary origin
# is never taken from input: it is the revision-tag URL Cloud Run reports for
# that exact revision, verified at 0% traffic. Every normal deploy omits these
# inputs, and --set-env-vars replaces the whole environment, so a plain deploy
# removes any previous canary route.
GATEWAY_CANARY_REVISION="${GATEWAY_CANARY_REVISION:-}"
GATEWAY_CANARY_OWNER_USER_IDS="${GATEWAY_CANARY_OWNER_USER_IDS:-}"
CANARY_WORKER_ORIGIN=""
CANARY_OWNER_COUNT=0
if [[ -n "$GATEWAY_CANARY_REVISION" || -n "$GATEWAY_CANARY_OWNER_USER_IDS" ]]; then
  if [[ -z "$GATEWAY_CANARY_REVISION" || -z "$GATEWAY_CANARY_OWNER_USER_IDS" ]]; then
    echo "Refusing gateway deployment: canary revision and owner allowlist must be set together." >&2
    exit 2
  fi
  if ! printf '%s' "$GATEWAY_CANARY_OWNER_USER_IDS" | grep -Eq '^[A-Za-z0-9_-]{6,64}(,[A-Za-z0-9_-]{6,64}){0,4}$'; then
    echo "Refusing gateway deployment: canary owner allowlist must be 1-5 exact comma-separated user IDs." >&2
    exit 2
  fi
  canary_report="$(GCP_PROJECT="$PROJECT" GCP_REGION="$REGION" CLOUD_RUN_SERVICE="$WORKER" \
    CLOUD_TASKS_QUEUE="$QUEUE" TASKS_INVOKER_SERVICE_ACCOUNT="$INVOKER_SA" \
    bash "$REPO_ROOT/scripts/prepare_gateway_canary.sh")"
  printf '%s\n' "$canary_report"
  CANARY_WORKER_ORIGIN="$(printf '%s\n' "$canary_report" | sed -n 's/^GATEWAY_CANARY_WORKER_ORIGIN=//p')"
  [[ "$CANARY_WORKER_ORIGIN" == https://canary-* ]] || { echo 'Missing verified pinned canary origin.' >&2; exit 2; }
  CANARY_OWNER_COUNT="$(printf '%s' "$GATEWAY_CANARY_OWNER_USER_IDS" | tr ',' '\n' | sort -u | grep -c .)"
fi
verify_canary_mapping() {
  [[ -n "$CANARY_WORKER_ORIGIN" ]] || return 0
  gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"
  local check
  check="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" \
    --revision "$GATEWAY_CANARY_REVISION" --tag "canary-${GATEWAY_CANARY_REVISION#fixlist-standard150-worker-}" < "$WORKER_JSON")"
  [[ "${check##* tag_url=}" == "$CANARY_WORKER_ORIGIN" ]]
}
ENV_VARS="^|^SCAN_TASKS_QUEUE_PATH=$QUEUE_PATH|SCAN_DRAIN_QUEUE_PATH=$DRAIN_QUEUE_PATH|SCAN_WORKER_URL=$WORKER_URL|TASKS_INVOKER_SERVICE_ACCOUNT=$INVOKER_SA|DISPATCH_MAX_CLOCK_SKEW_SECONDS=300|DISPATCH_MAX_BODY_BYTES=262144|FIXLIST_GATEWAY_SOURCE_SHA=$SOURCE_SHA"
ENV_VARS="${ENV_VARS}|SCAN_PIPELINE_MODE=$GATEWAY_PIPELINE_MODE"
if [[ "$GATEWAY_PIPELINE_MODE" == staged ]]; then
  ENV_VARS="${ENV_VARS}|SCAN_STAGED_OWNER_IDS=$STAGED_OWNER_IDS"
fi
if [[ -n "$CANARY_WORKER_ORIGIN" ]]; then
  ENV_VARS="${ENV_VARS}|SCAN_CANARY_WORKER_ORIGIN=$CANARY_WORKER_ORIGIN|SCAN_CANARY_OWNER_USER_IDS=$GATEWAY_CANARY_OWNER_USER_IDS"
fi

echo "worker_origin=$WORKER_ORIGIN"
echo "queue_path=$QUEUE_PATH"
echo "drain_queue_path=$DRAIN_QUEUE_PATH"
echo "signing_secret_ref=${SIGNING_SECRET}:${SIGNING_VERSION} (value not read)"
echo "source_sha=$SOURCE_SHA"
echo "canary_worker_origin=${CANARY_WORKER_ORIGIN:-<off>} canary_owner_count=$CANARY_OWNER_COUNT"
echo "pipeline_mode=$GATEWAY_PIPELINE_MODE staged_owner_count=$STAGED_OWNER_COUNT staged_cohort_sha256=$STAGED_COHORT_SHA"

echo
echo "=== Reserve this deployment's revision name ==="
# Cloud Run names a revision <service>-<suffix>. Reading that name back after
# the deploy, from status.latestCreatedRevisionName, returns whichever revision
# is newest on the service -- and nothing stops a second deployment (a direct
# script call, another principal) from creating one in between. This run would
# then promote and attest a revision it never built. The name is instead
# reserved here, before anything is built, and Cloud Run refuses to reuse it,
# so the promoted revision can only be this invocation's.
REVISION_SUFFIX="g${SOURCE_SHA:0:8}-$(date -u +%Y%m%d%H%M%S)-$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
NEW_REVISION="$(python3 "$REPO_ROOT/scripts/verify_gateway_deployment.py" \
  --plan-revision \
  --service "$GATEWAY" \
  --revision-suffix "$REVISION_SUFFIX" | sed -n 's/^planned_revision=//p')"
if [[ -z "$NEW_REVISION" ]]; then
  echo "Refusing gateway deployment: could not reserve a revision name." >&2
  exit 2
fi
echo "reserved_revision=$NEW_REVISION"

if gcloud run revisions describe "$NEW_REVISION" \
  --project="$PROJECT" \
  --region="$REGION" >/dev/null 2>&1; then
  echo "Refusing gateway deployment: reserved revision $NEW_REVISION already exists." >&2
  exit 2
fi

echo
echo "=== Deploy canonical keyless gateway ==="
gcloud run deploy "$GATEWAY" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$SOURCE_DIR" \
  "${TRAFFIC_ARGS[@]}" \
  --revision-suffix="$REVISION_SUFFIX" \
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
  --set-env-vars="$ENV_VARS" \
  --set-secrets="SCAN_EVIDENCE_SIGNING_KEY=${SIGNING_SECRET}:${SIGNING_VERSION}" \
  --quiet

echo
echo "=== Promote the exact revision this deployment created ==="
gcloud run revisions describe "$NEW_REVISION" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$CREATED_JSON"

# The reserved name resolves to a Ready revision carrying this deployment's
# source SHA, so what is about to be promoted is the revision this run built --
# not whichever revision happens to be newest on the service.
python3 "$REPO_ROOT/scripts/verify_gateway_deployment.py" \
  --created-revision-json "$CREATED_JSON" \
  --expected-revision "$NEW_REVISION" \
  --expected-source-sha "$SOURCE_SHA"

# The traffic spec can be pinned by name to an older revision. While it is,
# gcloud run deploy builds correctly, creates a Ready revision, routes nothing
# to it, and Cloud Run retires it seconds later -- while the pinned revision
# keeps serving and the deploy still exits 0. Promotion is therefore explicit
# and is never inferred from a successful deploy.
verify_canary_mapping
GATEWAY_PROMOTION_ATTEMPTED=1
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

GATEWAY_URL="$(python3 - "$GATEWAY_JSON" "$DISPATCHER_SA" "$QUEUE_PATH" "$DRAIN_QUEUE_PATH" "$WORKER_URL" "$INVOKER_SA" "$SOURCE_SHA" "$SIGNING_SECRET" "$SIGNING_VERSION" "$CANARY_WORKER_ORIGIN" "$GATEWAY_CANARY_OWNER_USER_IDS" "$GATEWAY_PIPELINE_MODE" "$STAGED_OWNER_IDS" "$REVISION_JSON" <<'PY'
import json, sys
(path, expected_sa, queue_path, drain_queue_path, worker_url, invoker_sa, source_sha, secret_name, secret_version,
 canary_origin, canary_owners, pipeline_mode, staged_owners, revision_path) = sys.argv[1:]
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
    'SCAN_PIPELINE_MODE': pipeline_mode,
}
if pipeline_mode == 'staged':
    expected_values['SCAN_STAGED_OWNER_IDS'] = staged_owners
elif 'SCAN_STAGED_OWNER_IDS' in env:
    raise SystemExit('Inactive gateway unexpectedly carries staged owners')
if canary_origin:
    expected_values['SCAN_CANARY_WORKER_ORIGIN'] = canary_origin
    expected_values['SCAN_CANARY_OWNER_USER_IDS'] = canary_owners
else:
    for name in ('SCAN_CANARY_WORKER_ORIGIN', 'SCAN_CANARY_OWNER_USER_IDS'):
        if name in env:
            raise SystemExit(f'Gateway environment unexpectedly carries {name}')
for name, value in expected_values.items():
    if str(env.get(name, {}).get('value') or '') != value:
        raise SystemExit(f'Gateway environment mismatch: {name}')
revision = json.load(open(revision_path, encoding='utf-8'))
actual_env = {item.get('name'): str(item.get('value') or '')
              for item in revision.get('spec', {}).get('containers', [{}])[0].get('env', [])}
for name, value in expected_values.items():
    if actual_env.get(name, '') != value:
        raise SystemExit(f'Serving gateway revision configuration mismatch: {name}')
for name in ('SCAN_STAGED_OWNER_IDS', 'SCAN_CANARY_WORKER_ORIGIN', 'SCAN_CANARY_OWNER_USER_IDS'):
    if name not in expected_values and name in actual_env:
        raise SystemExit(f'Serving gateway revision unexpectedly carries {name}')
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

# Control plane: what Cloud Run has been told. Deterministic the moment the
# promotion returns, so a failure here is final rather than retried.
python3 "$REPO_ROOT/scripts/verify_gateway_deployment.py" \
  --service-json "$GATEWAY_JSON" \
  --revision-json "$REVISION_JSON" \
  --expected-revision "$NEW_REVISION" \
  --expected-source-sha "$SOURCE_SHA"

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

# Runtime: what a customer actually gets from the untagged service URL. That is
# the real customer route, and while traffic propagates it can still be
# answered by the revision being drained. Every other health field is identical
# across two revisions built from the same commit -- source_sha included -- so
# the executing revision is the only field that settles which one replied.
# Propagation is a race, so retry to a deadline and fail if it never settles.
GATEWAY_HEALTH_TIMEOUT_SECONDS="${GATEWAY_HEALTH_TIMEOUT_SECONDS:-180}"
HEALTH_DEADLINE=$(( SECONDS + GATEWAY_HEALTH_TIMEOUT_SECONDS ))
HEALTH_PROVEN=""
while :; do
  if curl --fail --silent --show-error --max-time 20 "$GATEWAY_URL/health" > "$HEALTH_JSON" 2>/dev/null; then
    if HEALTH_PROVEN="$(python3 "$REPO_ROOT/scripts/verify_gateway_deployment.py" \
      --health-json "$HEALTH_JSON" \
      --expected-revision "$NEW_REVISION" \
      --expected-source-sha "$SOURCE_SHA" \
      --expected-contract-version "$EXPECTED_CONTRACT_VERSION" \
      --queue-path "$QUEUE_PATH" \
      --drain-queue-path "$DRAIN_QUEUE_PATH" \
      --worker-origin "$WORKER_ORIGIN" \
      --canary-worker-origin "$CANARY_WORKER_ORIGIN" \
      --canary-owner-count "$CANARY_OWNER_COUNT" \
      --pipeline-mode "$GATEWAY_PIPELINE_MODE" \
      --staged-owner-ids "$STAGED_OWNER_IDS" 2>/dev/null)"; then
      break
    fi
  fi
  if (( SECONDS >= HEALTH_DEADLINE )); then
    echo "Refusing gateway deployment: /health never settled on $NEW_REVISION within ${GATEWAY_HEALTH_TIMEOUT_SECONDS}s." >&2
    echo "Last /health response:" >&2
    cat "$HEALTH_JSON" >&2 2>/dev/null || true
    echo >&2
    python3 "$REPO_ROOT/scripts/verify_gateway_deployment.py" \
      --health-json "$HEALTH_JSON" \
      --expected-revision "$NEW_REVISION" \
      --expected-source-sha "$SOURCE_SHA" \
      --expected-contract-version "$EXPECTED_CONTRACT_VERSION" \
      --queue-path "$QUEUE_PATH" \
      --drain-queue-path "$DRAIN_QUEUE_PATH" \
      --worker-origin "$WORKER_ORIGIN" \
      --canary-worker-origin "$CANARY_WORKER_ORIGIN" \
      --canary-owner-count "$CANARY_OWNER_COUNT" >&2 || true
    exit 2
  fi
  sleep 3
done
printf '%s\n' "$HEALTH_PROVEN"

RUNTIME_REVISION="$(printf '%s\n' "$HEALTH_PROVEN" | sed -n 's/^runtime_revision=//p')"
RUNTIME_SOURCE_SHA="$(printf '%s\n' "$HEALTH_PROVEN" | sed -n 's/^runtime_source_sha=//p')"
if [[ "$RUNTIME_REVISION" != "$NEW_REVISION" || "$RUNTIME_SOURCE_SHA" != "$SOURCE_SHA" ]]; then
  echo "Refusing gateway deployment: runtime identity $RUNTIME_REVISION/$RUNTIME_SOURCE_SHA != $NEW_REVISION/$SOURCE_SHA" >&2
  exit 2
fi
echo "Gateway health contract verified."
verify_canary_mapping
GATEWAY_DEPLOY_VERIFIED=1

echo
echo "GATEWAY_READY=$GATEWAY_URL"
echo "GATEWAY_PRE_DEPLOY_REVISION=${PRE_DEPLOY_REVISION:-<none>}"
echo "GATEWAY_SERVING_REVISION=$SERVING_REVISION"
echo "GATEWAY_CONTRACT_VERSION=$EXPECTED_CONTRACT_VERSION"
# Both read back from the live /health response, never echoed from the input.
echo "GATEWAY_RUNTIME_REVISION=$RUNTIME_REVISION"
echo "GATEWAY_SOURCE_SHA=$RUNTIME_SOURCE_SHA"
echo "GATEWAY_CANARY_WORKER_ORIGIN=${CANARY_WORKER_ORIGIN:-<off>}"
