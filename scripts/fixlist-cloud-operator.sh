#!/usr/bin/env bash
# Allowlisted Google Cloud operations for the durable Standard 150 release.
#
# Invoked only by .github/workflows/fixlist-cloud-operator.yml, which
# authenticates keylessly through Workload Identity Federation. Operator calls
# read one dedicated signing secret into a mode-600 temporary file; no secret
# value is passed as an argument, environment value, digest log, or stdout.
#
# Mutations are confirmation-gated. For traffic operations the confirmation
# string is the exact revision name, so a confirmation that is right for one
# revision is wrong for every other one -- a stale approval cannot promote
# whatever happens to be newest.

set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"
: "${CLOUD_TASKS_QUEUE:?CLOUD_TASKS_QUEUE is required}"
STANDARD150_RECONCILER_JOB="${STANDARD150_RECONCILER_JOB:-fixlist-standard150-reconcile}"
CLOUD_TASKS_DRAIN_QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
ADMISSION_COORDINATOR_SERVICE="${ADMISSION_COORDINATOR_SERVICE:-fixlist-scan-admission-coordinator}"
: "${TASKS_INVOKER_SERVICE_ACCOUNT:?TASKS_INVOKER_SERVICE_ACCOUNT is required}"
: "${OPERATION:?OPERATION is required}"

CONFIRM="${CONFIRM:-}"
TARGET_REVISION="${TARGET_REVISION:-}"
SOURCE_SHA="${SOURCE_SHA:-}"
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"
BARRIER_EXPECTED_PRIOR_MODE="${BARRIER_EXPECTED_PRIOR_MODE:-}"
CHANGE_TICKET="${CHANGE_TICKET:-}"
CUTOVER_REASON="${CUTOVER_REASON:-Standard 150 controlled cutover}"
ACCEPTANCE_COHORT_ID="${ACCEPTANCE_COHORT_ID:-}"
ACCEPTANCE_RELEASE_ID="${ACCEPTANCE_RELEASE_ID:-}"
ACCEPTANCE_SOURCE_SHA="${ACCEPTANCE_SOURCE_SHA:-}"
ACCEPTANCE_OWNER_USER_IDS="${ACCEPTANCE_OWNER_USER_IDS:-}"
ACCEPTANCE_EXPIRES_AT="${ACCEPTANCE_EXPIRES_AT:-}"
ACCEPTANCE_TOTAL_CLAIM_BUDGET="${ACCEPTANCE_TOTAL_CLAIM_BUDGET:-}"
ACCEPTANCE_PER_OWNER_CLAIM_BUDGET="${ACCEPTANCE_PER_OWNER_CLAIM_BUDGET:-}"
FIXLIST_RELEASE_OWNER="${FIXLIST_RELEASE_OWNER:-bright4862-design}"

# Operator API paths are intentionally isolated here. The coordinator may share
# an internal handler, but the release shell never guesses or constructs a path
# from user input.
ADMISSION_BARRIER_CLOSE_PATH="${ADMISSION_BARRIER_CLOSE_PATH:-/ops/barrier/close}"
ADMISSION_BARRIER_STATUS_PATH="${ADMISSION_BARRIER_STATUS_PATH:-/ops/barrier/status}"
ADMISSION_BARRIER_OPEN_PATH="${ADMISSION_BARRIER_OPEN_PATH:-/ops/barrier/open}"
ADMISSION_BARRIER_ACCEPTANCE_PATH="${ADMISSION_BARRIER_ACCEPTANCE_PATH:-/ops/barrier/acceptance-only}"
ADMISSION_OPERATOR_DERIVATION_LABEL="fixlist-admission-operator-v1"
ADMISSION_DRAIN_SNAPSHOT_DERIVATION_LABEL="fixlist-admission-drain-snapshot-v1"
ADMISSION_DRAIN_TIMEOUT_SECONDS="${ADMISSION_DRAIN_TIMEOUT_SECONDS:-900}"
ADMISSION_DRAIN_POLL_SECONDS="${ADMISSION_DRAIN_POLL_SECONDS:-5}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPERATOR_TMP=""

cleanup_operator_tmp() {
  if [[ -n "$OPERATOR_TMP" && -d "$OPERATOR_TMP" ]]; then
    rm -rf "$OPERATOR_TMP"
  fi
}
trap cleanup_operator_tmp EXIT

gcloud config set project "$GCP_PROJECT" >/dev/null

echo "FixList Cloud Operator"
echo "project=$GCP_PROJECT"
echo "region=$GCP_REGION"
echo "service=$CLOUD_RUN_SERVICE"
echo "queue=$CLOUD_TASKS_QUEUE"
echo "operation=$OPERATION"
echo

require_exact_main_owner_source() {
  local head remote
  if ! printf '%s' "$SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
    echo "Refusing mutation: SOURCE_SHA must be an exact lowercase Git SHA." >&2
    exit 2
  fi
  head="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  if [[ "$head" != "$SOURCE_SHA" ]]; then
    echo "Refusing mutation: checked-out HEAD does not match SOURCE_SHA." >&2
    exit 2
  fi
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]]; then
    echo "Refusing mutation: checkout is dirty." >&2
    exit 2
  fi
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    if [[ "${GITHUB_ACTOR:-}" != "$FIXLIST_RELEASE_OWNER" ]]; then
      echo "Refusing mutation: workflow actor is not the release owner." >&2
      exit 2
    fi
    if [[ "${GITHUB_REF:-}" != "refs/heads/main" || "${GITHUB_SHA:-}" != "$SOURCE_SHA" ]]; then
      echo "Refusing mutation: workflow is not the exact main SHA." >&2
      exit 2
    fi
  else
    git -C "$REPO_ROOT" fetch origin main --quiet
    remote="$(git -C "$REPO_ROOT" rev-parse origin/main)"
    if [[ "$remote" != "$SOURCE_SHA" ]]; then
      echo "Refusing mutation: checkout is not current origin/main." >&2
      exit 2
    fi
  fi
}

require_barrier_inputs() {
  if ! printf '%s' "$BARRIER_EXPECTED_GENERATION" | grep -Eq '^[0-9]+$'; then
    echo "Refusing operator request: BARRIER_EXPECTED_GENERATION must be numeric." >&2
    exit 2
  fi
  case "$BARRIER_EXPECTED_PRIOR_MODE" in
    open|closed|acceptance_only) ;;
    *)
      echo "Refusing operator request: BARRIER_EXPECTED_PRIOR_MODE is invalid." >&2
      exit 2
      ;;
  esac
  if ! printf '%s' "$CHANGE_TICKET" | grep -Eq '^[A-Za-z0-9._:/-]{3,120}$'; then
    echo "Refusing operator request: CHANGE_TICKET must be an explicit safe identifier." >&2
    exit 2
  fi
  if [[ -z "$CUTOVER_REASON" || ${#CUTOVER_REASON} -gt 200 || "$CUTOVER_REASON" == *$'\n'* ]]; then
    echo "Refusing operator request: CUTOVER_REASON must be one non-empty bounded line." >&2
    exit 2
  fi
}

show_status() {
  echo "=== Cloud Run ==="
  gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --format='yaml(metadata.name,status.url,status.latestReadyRevisionName,status.latestCreatedRevisionName,status.traffic)'

  echo
  echo "=== Cloud Tasks ==="
  gcloud tasks queues describe "$CLOUD_TASKS_QUEUE" \
    --location="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --format='yaml(name,state,rateLimits,retryConfig)'

  echo
  echo "=== Drain queue ==="
  if gcloud tasks queues describe "$CLOUD_TASKS_DRAIN_QUEUE" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
    gcloud tasks queues describe "$CLOUD_TASKS_DRAIN_QUEUE" --location="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(name,state,rateLimits,retryConfig)'
  else
    echo "not_deployed=$CLOUD_TASKS_DRAIN_QUEUE"
  fi

  echo
  echo "=== Admission coordinator ==="
  if gcloud run services describe "$ADMISSION_COORDINATOR_SERVICE" --region="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
    gcloud run services describe "$ADMISSION_COORDINATOR_SERVICE" --region="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(metadata.name,status.url,status.latestReadyRevisionName,status.traffic)'
  else
    echo "not_deployed=$ADMISSION_COORDINATOR_SERVICE"
  fi

  echo
  echo "=== Reconciler ==="
  if gcloud scheduler jobs describe "$STANDARD150_RECONCILER_JOB" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
    gcloud scheduler jobs describe "$STANDARD150_RECONCILER_JOB" --location="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(name,state,schedule,httpTarget.uri,httpTarget.oidcToken.serviceAccountEmail)'
  else
    echo "not_deployed=$STANDARD150_RECONCILER_JOB"
  fi

  echo
  echo "=== Recent worker structured logs ==="
  gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="fixlist-standard150-worker"' \
    --project="$GCP_PROJECT" --freshness=30m --limit=200 --order=asc \
    --format='table(timestamp,resource.labels.revision_name,severity,jsonPayload.event,jsonPayload.scan_id,jsonPayload.attempt_count,jsonPayload.pages_found,jsonPayload.pages_crawled,textPayload)' || true

  echo
  echo "=== Recent worker requests ==="
  gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="fixlist-standard150-worker" AND logName:"run.googleapis.com%2Frequests"' \
    --project="$GCP_PROJECT" --freshness=30m --limit=100 --order=asc \
    --format='table(timestamp,resource.labels.revision_name,httpRequest.requestMethod,httpRequest.status,httpRequest.latency)' || true
}

verify_iam() {
  echo "=== Cloud Run IAM ==="
  gcloud run services get-iam-policy "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --format=yaml

  echo
  echo "=== Cloud Scheduler reconciler ==="
  gcloud scheduler jobs describe "$STANDARD150_RECONCILER_JOB" \
    --location="$GCP_REGION" --project="$GCP_PROJECT" --format=json || true

  echo "=== Cloud Tasks queue IAM ==="
  gcloud tasks queues get-iam-policy "$CLOUD_TASKS_QUEUE" \
    --location="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --format=yaml

  echo
  echo "=== Tasks invoker service-account IAM ==="
  gcloud iam service-accounts get-iam-policy "$TASKS_INVOKER_SERVICE_ACCOUNT" \
    --project="$GCP_PROJECT" \
    --format=yaml
}

# The durable pipeline sends every Cloud Task to POST /scan-job and the
# watchdog to POST /scan-job-drain. Those routes exist only in builds that
# contain scanner-api/app/scan_job.py. A worker built from older source without
# them accepts the deployment, serves /health, and 404s every task -- and the
# watchdog 404s too, so runs never reach a terminal state. Unauthenticated
# probes cannot answer this: Cloud Run IAM rejects them before routing. The
# only external proof is the image's build provenance.
verify_worker_routes() {
  local revision image digest timeout release_sha verdict=0
  revision="${TARGET_REVISION:-$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(status.latestReadyRevisionName)')}"
  [ -n "$revision" ] || { echo "No ready revision found." >&2; exit 2; }

  image=$(gcloud run revisions describe "$revision" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(spec.containers[0].image)')
  echo "revision: $revision"
  echo "image:    $image"

  digest="${image##*@}"
  if [ "$digest" = "$image" ]; then
    echo "WARNING: revision runs a mutable tag, not an immutable digest."
    digest=""
  fi

  # Match the image back to the Cloud Build that produced it. gcloud's --filter
  # cannot reliably index into results.images, so the builds are pulled as JSON
  # and matched here: by digest when the revision is digest-pinned, otherwise by
  # image name.
  echo
  echo "=== Build provenance ==="
  release_sha=$(gcloud builds list --project="$GCP_PROJECT" --region="$GCP_REGION" --limit=50 \
    --format=json 2>/dev/null | python3 -c '
import json,sys
builds=json.load(sys.stdin)
image=sys.argv[1]; digest=sys.argv[2]
name=image.split("@")[0].split(":")[0]
for b in builds:
    imgs=(b.get("results") or {}).get("images") or []
    names=[i.get("name","") for i in imgs]
    digs=[i.get("digest","") for i in imgs]
    hit=(digest and digest in digs) or (not digest and any(n.split("@")[0].split(":")[0]==name for n in names))
    if hit:
        sha=(b.get("substitutions") or {}).get("_RELEASE_SHA","")
        print(sha)
        sys.stderr.write("build %s  status=%s  created=%s  _RELEASE_SHA=%s\n" % (
            b.get("id",""), b.get("status",""), b.get("createTime",""), sha or "(unset)"))
        break
' "$image" "$digest" || true)

  # The runner has this repository checked out with full history, so whether a
  # SHA declares the durable routes is a fact we can decide here rather than
  # asking a human to eyeball it.
  echo
  echo "=== Route verification ==="
  if [ -z "$release_sha" ]; then
    echo "INDETERMINATE: no Cloud Build recorded for this image, or _RELEASE_SHA unset."
    echo "The image predates provenance-tagged builds. Rebuild from"
    echo "cloudbuild.durable-worker.yaml at a known SHA before promoting."
    verdict=1
  elif ! git cat-file -e "${release_sha}^{commit}" 2>/dev/null; then
    echo "INDETERMINATE: _RELEASE_SHA $release_sha is not a commit in this repository."
    verdict=1
  else
    echo "built from: $release_sha"
    if git cat-file -e "${release_sha}:scanner-api/app/scan_job.py" 2>/dev/null \
      && git show "${release_sha}:scanner-api/app/main.py" 2>/dev/null | grep -q '@app.post("/scan-job")' \
      && git show "${release_sha}:scanner-api/app/main.py" 2>/dev/null | grep -q '@app.post("/scan-job-drain")'; then
      echo "PASS: that commit has scan_job.py and declares /scan-job and /scan-job-drain."
    else
      echo "FAIL: that commit does NOT declare both durable routes."
      echo "Every Cloud Task would 404, and the drain watchdog would 404 too,"
      echo "so runs would never reach a terminal state. Rebuild the worker from"
      echo "cloudbuild.durable-worker.yaml at current main before promoting."
      verdict=1
    fi
  fi

  echo
  echo "=== Request timeout (must equal the 480s dispatchDeadline) ==="
  timeout=$(gcloud run revisions describe "$revision" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(spec.timeoutSeconds)')
  echo "timeoutSeconds: ${timeout:-unknown}"
  if [ "$timeout" != "480" ]; then
    echo "FAIL: expected 480. A shorter timeout kills the worker mid-crawl;"
    echo "a longer one outlives the Cloud Tasks dispatch deadline."
    verdict=1
  else
    echo "PASS"
  fi

  echo
  if [ "$verdict" -eq 0 ]; then
    echo "WORKER ROUTES VERIFIED"
  else
    echo "WORKER NOT VERIFIED -- do not promote or resume the queue."
    return 1
  fi
}

require_confirmation() {
  local expected="$1"
  if [[ "$CONFIRM" != "$expected" ]]; then
    echo "Refusing mutation: confirmation must be exactly '$expected'." >&2
    exit 2
  fi
}

# Traffic must move to a revision the operator named explicitly. --to-latest
# resolves at execution time, so anything deployed between validation and
# promotion would be promoted instead of the validated candidate.
require_target_revision() {
  if [ -z "$TARGET_REVISION" ]; then
    echo "Refusing mutation: an exact revision name is required." >&2
    exit 2
  fi
  if ! gcloud run revisions describe "$TARGET_REVISION" \
      --region="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
    echo "Refusing mutation: revision '$TARGET_REVISION' does not exist." >&2
    exit 2
  fi
  require_confirmation "$TARGET_REVISION"
}

promote_revision() {
  gcloud run services update-traffic "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --to-revisions="$TARGET_REVISION=100"
}

# A promoted revision must prove it serves before tasks are allowed to flow.
# The worker is private, so an unauthenticated probe cannot reach the app --
# 401/403 from Cloud Run IAM is the expected healthy answer and confirms both
# that the service is reachable and that it is not public. Anything else means
# the promotion should not be followed by a queue resume.
assert_serving() {
  local url code
  url=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(status.url)')
  [ -n "$url" ] || { echo "No service URL; refusing to continue." >&2; exit 2; }

  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$url/scan-job" || echo "000")
  case "$code" in
    401|403) echo "Worker is serving and private (probe returned $code)." ;;
    000)     echo "Worker probe could not reach $url; refusing to continue." >&2; exit 2 ;;
    *)       echo "Worker probe returned $code; expected 401/403. Refusing to continue." >&2; exit 2 ;;
  esac
}

prepare_operator_client() {
  local service_json metadata
  if [[ -n "$OPERATOR_TMP" ]]; then
    return 0
  fi

  OPERATOR_TMP="$(mktemp -d)"
  chmod 700 "$OPERATOR_TMP"
  service_json="$OPERATOR_TMP/coordinator.json"
  metadata="$OPERATOR_TMP/operator-metadata"

  gcloud run services describe "$ADMISSION_COORDINATOR_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json > "$service_json"

  python3 - "$service_json" "$metadata" <<'PY'
import json, sys

source, output = sys.argv[1:]
value = json.load(open(source, encoding="utf-8"))
url = str((value.get("status") or {}).get("url") or "").strip().rstrip("/")
containers = (((value.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
if not url.startswith("https://") or not containers:
    raise SystemExit("Coordinator operator metadata is unavailable")
env = {item.get("name"): item for item in containers[0].get("env", [])}
operator_sa = str((env.get("ADMISSION_OPERATOR_SERVICE_ACCOUNT") or {}).get("value") or "").strip()
audience = str((env.get("ADMISSION_OPERATOR_AUDIENCE") or {}).get("value") or "").strip()
secret_ref = (((env.get("ADMISSION_OPERATOR_SIGNING_KEY") or {}).get("valueFrom") or {}).get("secretKeyRef") or {})
secret_name = str(secret_ref.get("name") or "").strip()
secret_version = str(secret_ref.get("key") or "").strip()
if not operator_sa or not audience or not secret_name:
    raise SystemExit("Coordinator operator identity or signing-secret reference is missing")
if not secret_version.isdigit():
    raise SystemExit("Coordinator operator signing-secret version is not numeric")
with open(output, "w", encoding="utf-8") as handle:
    handle.write("\n".join([url, operator_sa, audience, secret_name, secret_version]) + "\n")
PY

  mapfile -t _operator_metadata < "$metadata"
  if [[ ${#_operator_metadata[@]} -ne 5 ]]; then
    echo "Coordinator operator metadata is incomplete." >&2
    exit 2
  fi
  COORDINATOR_OPERATOR_URL="${_operator_metadata[0]}"
  COORDINATOR_OPERATOR_SERVICE_ACCOUNT="${_operator_metadata[1]}"
  COORDINATOR_OPERATOR_AUDIENCE="${_operator_metadata[2]}"
  COORDINATOR_OPERATOR_SECRET="${_operator_metadata[3]}"
  COORDINATOR_OPERATOR_SECRET_VERSION="${_operator_metadata[4]}"

  if [[ "$COORDINATOR_OPERATOR_SERVICE_ACCOUNT" != "${GCP_OPERATOR_SERVICE_ACCOUNT:-}" ]]; then
    echo "Refusing operator request: authenticated workflow identity does not match coordinator policy." >&2
    exit 2
  fi
  # The identity token is minted before the coordinator is read, so the audience
  # it was bound to is checked against the one the coordinator actually
  # declares. Without this a token for the wrong audience reaches the
  # coordinator and is refused as a bare 401, naming nothing.
  if [[ "$COORDINATOR_OPERATOR_AUDIENCE" != "${FIXLIST_OPERATOR_TOKEN_AUDIENCE:-}" ]]; then
    echo "Refusing operator request: minted token audience does not match coordinator policy." >&2
    exit 2
  fi

  # Secret material is written only to a mode-600 temporary file and is never
  # passed as a command argument, environment value, digest log, or stdout.
  # Disable inherited tracing before Secret Manager can emit payload bytes.
  set +x
  umask 077
  gcloud secrets versions access "$COORDINATOR_OPERATOR_SECRET_VERSION" \
    --secret="$COORDINATOR_OPERATOR_SECRET" --project="$GCP_PROJECT" \
    > "$OPERATOR_TMP/operator-key"
  test -s "$OPERATOR_TMP/operator-key"
  chmod 600 "$OPERATOR_TMP/operator-key"
}

write_barrier_payload() {
  local operation="$1" destination="$2"
  python3 - "$operation" "$destination" "$BARRIER_EXPECTED_PRIOR_MODE" \
    "$BARRIER_EXPECTED_GENERATION" "$CUTOVER_REASON" "$CHANGE_TICKET" <<'PY'
import json, sys

operation, destination, prior_mode, generation, reason, ticket = sys.argv[1:]
payload = {
    "operation": operation,
    "reason": reason,
    "change_ticket": ticket,
}
if operation == "status":
    payload["expected_generation"] = int(generation)
else:
    payload["intended_prior"] = {"mode": prior_mode, "generation": int(generation)}
with open(destination, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
PY
}

write_acceptance_payload() {
  local destination="$1"
  python3 - "$destination" "$BARRIER_EXPECTED_GENERATION" "$CUTOVER_REASON" "$CHANGE_TICKET" \
    "$ACCEPTANCE_COHORT_ID" "$ACCEPTANCE_RELEASE_ID" "$ACCEPTANCE_SOURCE_SHA" \
    "$ACCEPTANCE_OWNER_USER_IDS" "$ACCEPTANCE_EXPIRES_AT" \
    "$ACCEPTANCE_TOTAL_CLAIM_BUDGET" "$ACCEPTANCE_PER_OWNER_CLAIM_BUDGET" <<'PY'
import json, re, sys

(destination, generation, reason, ticket, cohort_id, release_id, source_sha,
 owners_raw, expires_at, total_budget, owner_budget) = sys.argv[1:]
owners = [item.strip() for item in owners_raw.split(",") if item.strip()]
safe_id = re.compile(r"^[A-Za-z0-9_-]{6,160}$")
if not safe_id.fullmatch(cohort_id) or not safe_id.fullmatch(release_id):
    raise SystemExit("Acceptance cohort and release IDs must be bounded safe IDs")
if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
    raise SystemExit("Acceptance source SHA must be exact lowercase Git SHA")
if not owners or len(owners) != len(set(owners)) or not all(safe_id.fullmatch(item) for item in owners):
    raise SystemExit("Acceptance owner allowlist is invalid")
payload = {
    "operation": "acceptance_only",
    "reason": reason,
    "change_ticket": ticket,
    "intended_prior": {"mode": "closed", "generation": int(generation)},
    "acceptance": {
        "cohort_id": cohort_id,
        "release_id": release_id,
        "source_sha": source_sha,
        "owner_user_ids": owners,
        "expires_at": int(expires_at),
        "total_claim_budget": int(total_budget),
        "per_owner_claim_budget": int(owner_budget),
    },
}
with open(destination, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
PY
}

call_barrier_operator() {
  local operation="$1" path="$2" body response timestamp signature token code error_code
  prepare_operator_client
  # prepare_operator_client disables inherited xtrace before credential access;
  # keep it disabled through signature derivation, token minting, and cleanup.
  set +x
  body="$OPERATOR_TMP/${operation}-body.json"
  response="$OPERATOR_TMP/${operation}-response.json"
  if [[ "$operation" == "acceptance_only" ]]; then
    write_acceptance_payload "$body"
  else
    write_barrier_payload "$operation" "$body"
  fi
  timestamp="$(date +%s)"
  signature="$(python3 - "$OPERATOR_TMP/operator-key" "$body" "$timestamp" \
    "$ADMISSION_OPERATOR_DERIVATION_LABEL" <<'PY'
import hashlib, hmac, sys

key_path, body_path, timestamp, label = sys.argv[1:]
root = open(key_path, "rb").read()
body = open(body_path, "rb").read()
derived = hmac.new(root, label.encode("utf-8"), hashlib.sha256).digest()
print(hmac.new(derived, timestamp.encode("ascii") + b"\n" + body, hashlib.sha256).hexdigest())
PY
)"
  token="${FIXLIST_OPERATOR_ID_TOKEN:-}"
  if [[ -z "$token" ]]; then
    echo "Refusing operator request: coordinator operator identity token is unavailable." >&2
    exit 2
  fi

  code="$(curl --silent --show-error --max-time 20 \
    --output "$response" --write-out '%{http_code}' \
    --request POST "${COORDINATOR_OPERATOR_URL}${path}" \
    --header 'content-type: application/json' \
    --header "authorization: Bearer ${token}" \
    --header "x-fixlist-operator-timestamp: ${timestamp}" \
    --header "x-fixlist-operator-signature: ${signature}" \
    --data-binary "@${body}")"
  token=""
  signature=""

  if [[ "$code" != "200" ]]; then
    error_code="$(python3 - "$response" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8"))
    error = str(value.get("error") or "operator_request_failed")
except Exception:
    error = "operator_request_failed"
print(error if error.replace("_", "").isalnum() else "operator_request_failed")
PY
)"
    echo "Coordinator operator request failed: HTTP $code ($error_code)." >&2
    return 1
  fi
  BARRIER_RESPONSE_FILE="$response"
}

parse_barrier_response() {
  local expected_operation="$1"
  mapfile -t _barrier_values < <(python3 - "$BARRIER_RESPONSE_FILE" "$expected_operation" \
    "$OPERATOR_TMP/operator-key" "$ADMISSION_DRAIN_SNAPSHOT_DERIVATION_LABEL" <<'PY'
import hashlib, hmac, json, re, sys

path, expected, key_path, snapshot_label = sys.argv[1:]
value = json.load(open(path, encoding="utf-8"))
if value.get("success") is not True or value.get("operation") != expected:
    raise SystemExit("Unexpected operator response")
barrier = value.get("barrier") or {}
snapshot = value.get("drain_snapshot") or {}
counts = snapshot.get("counts") or {}
mode = str(barrier.get("mode") or "")
generation = barrier.get("generation")
snapshot_id = str(snapshot.get("snapshot_id") or "")
version = str(snapshot.get("version") or "")
proof = str(snapshot.get("proof") or "")
unsigned = {key: item for key, item in snapshot.items() if key != "proof"}
root = open(key_path, "rb").read()
derived = hmac.new(root, snapshot_label.encode("utf-8"), hashlib.sha256).digest()
canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
expected_proof = hmac.new(derived, canonical, hashlib.sha256).hexdigest()
total = counts.get("total_obligations")
live = counts.get("live_reconciliation")
active = counts.get("claimed_active")
expired = counts.get("claimed_expired")
bound = counts.get("bound")
ready = snapshot.get("drain_ready") is True
if mode not in {"open", "closed", "acceptance_only"}:
    raise SystemExit("Invalid barrier mode")
if not isinstance(generation, int) or generation < 0:
    raise SystemExit("Invalid barrier generation")
if version != "admission_drain_snapshot_v1" or not snapshot_id:
    raise SystemExit("Invalid drain snapshot identity")
if not re.fullmatch(r"[0-9a-f]{64}", proof):
    raise SystemExit("Invalid drain snapshot proof")
if not hmac.compare_digest(proof, expected_proof):
    raise SystemExit("Drain snapshot signature mismatch")
if any(not isinstance(item, int) or item < 0 for item in (total, live, active, expired, bound)):
    raise SystemExit("Invalid drain counts")
print(mode)
print(generation)
print(snapshot_id)
print("true" if ready else "false")
print(total)
print(live)
print(active)
print(expired)
print(bound)
PY
  )
  if [[ ${#_barrier_values[@]} -ne 9 ]]; then
    echo "Coordinator barrier response did not satisfy the signed snapshot contract." >&2
    return 1
  fi
  BARRIER_MODE="${_barrier_values[0]}"
  BARRIER_GENERATION="${_barrier_values[1]}"
  BARRIER_SNAPSHOT_ID="${_barrier_values[2]}"
  BARRIER_DRAIN_READY="${_barrier_values[3]}"
  BARRIER_TOTAL_OBLIGATIONS="${_barrier_values[4]}"
  BARRIER_LIVE_RECONCILIATIONS="${_barrier_values[5]}"
  BARRIER_CLAIMED_ACTIVE="${_barrier_values[6]}"
  BARRIER_CLAIMED_EXPIRED="${_barrier_values[7]}"
  BARRIER_BOUND="${_barrier_values[8]}"
}

read_barrier_status() {
  BARRIER_EXPECTED_PRIOR_MODE="closed"
  call_barrier_operator status "$ADMISSION_BARRIER_STATUS_PATH"
  parse_barrier_response status
}

wait_for_barrier_drain() {
  local deadline now
  deadline=$(( $(date +%s) + ADMISSION_DRAIN_TIMEOUT_SECONDS ))
  while true; do
    BARRIER_EXPECTED_GENERATION="$BARRIER_GENERATION"
    read_barrier_status
    if [[ "$BARRIER_MODE" != "closed" ]]; then
      echo "Barrier left closed mode during drain; refusing cutover." >&2
      return 1
    fi
    if [[ "$BARRIER_DRAIN_READY" == "true" && "$BARRIER_CLAIMED_ACTIVE" == "0" \
      && "$BARRIER_BOUND" == "0" && "$BARRIER_LIVE_RECONCILIATIONS" == "0" ]]; then
      echo "ADMISSION_DRAIN_VERIFIED generation=$BARRIER_GENERATION snapshot=$BARRIER_SNAPSHOT_ID"
      return 0
    fi
    now="$(date +%s)"
    if (( now >= deadline )); then
      echo "Admission obligations did not drain before the bounded deadline." >&2
      return 1
    fi
    sleep "$ADMISSION_DRAIN_POLL_SECONDS"
  done
}

queue_state() {
  gcloud tasks queues describe "$1" --location="$GCP_REGION" \
    --project="$GCP_PROJECT" --format='value(state)'
}

scheduler_state() {
  gcloud scheduler jobs describe "$STANDARD150_RECONCILER_JOB" \
    --location="$GCP_REGION" --project="$GCP_PROJECT" --format='value(state)'
}

require_drain_plane_live() {
  [[ "$(queue_state "$CLOUD_TASKS_QUEUE")" == "RUNNING" ]] \
    || { echo "Main queue must be RUNNING while barrier obligations drain." >&2; return 1; }
  [[ "$(queue_state "$CLOUD_TASKS_DRAIN_QUEUE")" == "RUNNING" ]] \
    || { echo "Drain queue must be RUNNING while barrier obligations drain." >&2; return 1; }
  [[ "$(scheduler_state)" == "ENABLED" ]] \
    || { echo "Reconciliation scheduler must be ENABLED while obligations drain." >&2; return 1; }
}

pause_queue_checked() {
  gcloud tasks queues pause "$1" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null
  [[ "$(queue_state "$1")" == "PAUSED" ]]
}

resume_queue_checked() {
  gcloud tasks queues resume "$1" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null
  [[ "$(queue_state "$1")" == "RUNNING" ]]
}

pause_scheduler_checked() {
  gcloud scheduler jobs pause "$STANDARD150_RECONCILER_JOB" \
    --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null
  [[ "$(scheduler_state)" == "PAUSED" ]]
}

resume_scheduler_checked() {
  gcloud scheduler jobs resume "$STANDARD150_RECONCILER_JOB" \
    --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null
  [[ "$(scheduler_state)" == "ENABLED" ]]
}

emergency_pause_all() {
  # Best-effort compensation always moves toward the fail-closed paused state.
  # It never opens the claim barrier or touches either Base44 intake secret.
  set +e
  gcloud tasks queues pause "$CLOUD_TASKS_QUEUE" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1
  gcloud tasks queues pause "$CLOUD_TASKS_DRAIN_QUEUE" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1
  gcloud scheduler jobs pause "$STANDARD150_RECONCILER_JOB" --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1
  set -e
}

cutover_pause() {
  require_exact_main_owner_source
  require_barrier_inputs
  require_confirmation "PAUSE-STANDARD150-CUTOVER:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  require_drain_plane_live
  call_barrier_operator close "$ADMISSION_BARRIER_CLOSE_PATH"
  parse_barrier_response close
  if [[ "$BARRIER_MODE" != "closed" ]]; then
    echo "Coordinator did not close the global claim barrier." >&2
    return 1
  fi
  wait_for_barrier_drain

  # Required order: main queue, drain queue, then Scheduler. If any step fails,
  # best-effort compensation pauses all three while the barrier remains closed.
  if ! pause_queue_checked "$CLOUD_TASKS_QUEUE" \
    || ! pause_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE" \
    || ! pause_scheduler_checked; then
    emergency_pause_all
    echo "Cutover pause failed partially; barrier remains closed and all controls were driven toward PAUSED." >&2
    return 1
  fi
  BARRIER_EXPECTED_GENERATION="$BARRIER_GENERATION"
  if ! require_closed_drained_barrier; then
    emergency_pause_all
    echo "Post-pause barrier verification failed; all drain controls remain PAUSED." >&2
    return 1
  fi
  echo "STANDARD150_CUTOVER_PAUSED generation=$BARRIER_GENERATION snapshot=$BARRIER_SNAPSHOT_ID"
}

require_closed_drained_barrier() {
  require_barrier_inputs
  read_barrier_status
  if [[ "$BARRIER_MODE" != "closed" || "$BARRIER_DRAIN_READY" != "true" \
    || "$BARRIER_CLAIMED_ACTIVE" != "0" || "$BARRIER_BOUND" != "0" \
    || "$BARRIER_LIVE_RECONCILIATIONS" != "0" ]]; then
    echo "Refusing: global claims are not closed and fully drained." >&2
    return 1
  fi
}

cutover_resume() {
  require_exact_main_owner_source
  require_confirmation "RESUME-STANDARD150-CUTOVER:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  require_closed_drained_barrier

  # Exact inverse of pause: Scheduler, drain queue, main queue. The barrier is
  # deliberately not opened; public claims/intake remain closed.
  if ! resume_scheduler_checked \
    || ! resume_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE" \
    || ! resume_queue_checked "$CLOUD_TASKS_QUEUE"; then
    emergency_pause_all
    echo "Cutover resume failed partially; compensated back toward PAUSED with claims still closed." >&2
    return 1
  fi
  echo "STANDARD150_DRAIN_PLANE_RESUMED_CLAIMS_CLOSED generation=$BARRIER_GENERATION"
}

verify_zero_admission_obligations() {
  require_closed_drained_barrier
  echo "ADMISSION_ZERO_OBLIGATIONS_VERIFIED generation=$BARRIER_GENERATION snapshot=$BARRIER_SNAPSHOT_ID expired_diagnostic=$BARRIER_CLAIMED_EXPIRED"
}

barrier_status_command() {
  require_exact_main_owner_source
  require_barrier_inputs
  read_barrier_status
  echo "ADMISSION_BARRIER_STATUS mode=$BARRIER_MODE generation=$BARRIER_GENERATION drain_ready=$BARRIER_DRAIN_READY active=$BARRIER_CLAIMED_ACTIVE bound=$BARRIER_BOUND expired_diagnostic=$BARRIER_CLAIMED_EXPIRED live_reconciliation=$BARRIER_LIVE_RECONCILIATIONS snapshot=$BARRIER_SNAPSHOT_ID"
}

verify_zero_admission_obligations_command() {
  require_exact_main_owner_source
  require_confirmation "VERIFY-ZERO-ADMISSION:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  verify_zero_admission_obligations
}

open_claim_barrier() {
  require_exact_main_owner_source
  require_barrier_inputs
  require_confirmation "OPEN-STANDARD150-CLAIMS:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  require_closed_drained_barrier
  require_drain_plane_live
  BARRIER_EXPECTED_PRIOR_MODE="closed"
  call_barrier_operator open "$ADMISSION_BARRIER_OPEN_PATH"
  parse_barrier_response open
  [[ "$BARRIER_MODE" == "open" ]] || { echo "Coordinator did not open the claim barrier." >&2; return 1; }
  echo "STANDARD150_CLAIM_BARRIER_OPEN generation=$BARRIER_GENERATION"
}

activate_acceptance_only() {
  require_exact_main_owner_source
  require_barrier_inputs
  require_confirmation "OPEN-STANDARD150-ACCEPTANCE:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}"
  [[ "$ACCEPTANCE_SOURCE_SHA" == "$SOURCE_SHA" ]] \
    || { echo "Acceptance cohort must bind the exact main source SHA." >&2; return 1; }
  require_closed_drained_barrier
  require_drain_plane_live
  BARRIER_EXPECTED_PRIOR_MODE="closed"
  call_barrier_operator acceptance_only "$ADMISSION_BARRIER_ACCEPTANCE_PATH"
  parse_barrier_response acceptance_only
  [[ "$BARRIER_MODE" == "acceptance_only" ]] \
    || { echo "Coordinator did not enter acceptance-only mode." >&2; return 1; }
  echo "STANDARD150_ACCEPTANCE_ONLY generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID"
}

case "$OPERATION" in
  status)
    show_status
    ;;

  verify-iam)
    verify_iam
    ;;

  verify-worker-routes)
    verify_worker_routes
    ;;

  promote-worker)
    require_exact_main_owner_source
    require_target_revision
    promote_revision
    show_status
    ;;

  rollback-worker)
    require_exact_main_owner_source
    require_target_revision
    echo "Rolling traffic back to $TARGET_REVISION ..."
    promote_revision
    show_status
    ;;

  barrier-status)
    barrier_status_command
    ;;

  verify-zero-admission-obligations)
    verify_zero_admission_obligations_command
    ;;

  cutover-pause)
    cutover_pause
    ;;

  cutover-resume)
    cutover_resume
    ;;

  open-claim-barrier)
    open_claim_barrier
    ;;

  acceptance-only)
    activate_acceptance_only
    ;;

  pause-queue|resume-queue|activate-beta)
    echo "Unsupported unsafe operation: $OPERATION. Use cutover-pause/cutover-resume and the separate claim-barrier operation." >&2
    exit 64
    ;;

  *)
    echo "Unsupported operation: $OPERATION" >&2
    exit 64
    ;;
esac
