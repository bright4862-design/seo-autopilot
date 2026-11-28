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
ACCEPTANCE_LAUNCHER_BUILD_ID="${ACCEPTANCE_LAUNCHER_BUILD_ID:-}"
ACCEPTANCE_SOURCE_SHA="${ACCEPTANCE_SOURCE_SHA:-}"
ACCEPTANCE_OWNER_USER_IDS="${ACCEPTANCE_OWNER_USER_IDS:-}"
ACCEPTANCE_EXPIRES_AT="${ACCEPTANCE_EXPIRES_AT:-}"
ACCEPTANCE_TOTAL_CLAIM_BUDGET="${ACCEPTANCE_TOTAL_CLAIM_BUDGET:-}"
ACCEPTANCE_PER_OWNER_CLAIM_BUDGET="${ACCEPTANCE_PER_OWNER_CLAIM_BUDGET:-}"
LEGACY_ACCESS="${LEGACY_ACCESS:-}"
LEGACY_ACCESS_SHA256=""
LEGACY_ACCESS_PREFLIGHT=""
FIXLIST_RELEASE_OWNER="${FIXLIST_RELEASE_OWNER:-bright4862-design}"
FIXLIST_WORKER_ID_TOKEN="${FIXLIST_WORKER_ID_TOKEN:-}"
FIXLIST_WORKER_TOKEN_AUDIENCE="${FIXLIST_WORKER_TOKEN_AUDIENCE:-}"
FIXLIST_WORKER_PROBE_URL="${FIXLIST_WORKER_PROBE_URL:-}"
WORKER_CANDIDATE_TAG="${WORKER_CANDIDATE_TAG:-candidate}"

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
RUNTIME_PROBE_TMP=""

if [[ -n "$LEGACY_ACCESS" && "$OPERATION" != acceptance-only ]]; then
  echo "Legacy access configuration is only accepted when opening the named pilot." >&2
  exit 2
fi
if [[ -n "$LEGACY_ACCESS" && "${GITHUB_ACTIONS:-}" == true ]]; then
  echo "Approved legacy access requires the local authenticated Base44 owner preflight." >&2
  exit 2
fi

cleanup_operator_tmp() {
  if [[ -n "$OPERATOR_TMP" && -d "$OPERATOR_TMP" ]]; then
    rm -rf "$OPERATOR_TMP"
  fi
  if [[ -n "$RUNTIME_PROBE_TMP" && -d "$RUNTIME_PROBE_TMP" ]]; then
    rm -rf "$RUNTIME_PROBE_TMP"
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

# `describe` failing tells an operator nothing about why it failed, but a missing
# resource and an unreadable one need opposite responses: create it, or fix the
# reader's access. Collapsing both into "not_deployed" invites someone to
# recreate a queue that already exists, so classify the failure instead.
describe_or_explain() {
  local label="$1"; shift
  local out err_file
  err_file="$(mktemp)"
  if out="$("$@" 2>"$err_file")"; then
    printf '%s\n' "$out"
    rm -f "$err_file"
    return 0
  fi
  if grep -q 'PERMISSION_DENIED' "$err_file"; then
    echo "read_denied=$label"
  else
    echo "not_deployed=$label"
  fi
  rm -f "$err_file"
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
  describe_or_explain "$CLOUD_TASKS_DRAIN_QUEUE" \
    gcloud tasks queues describe "$CLOUD_TASKS_DRAIN_QUEUE" --location="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(name,state,rateLimits,retryConfig)'

  echo
  echo "=== Admission coordinator ==="
  describe_or_explain "$ADMISSION_COORDINATOR_SERVICE" \
    gcloud run services describe "$ADMISSION_COORDINATOR_SERVICE" --region="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(metadata.name,status.url,status.latestReadyRevisionName,status.traffic)'

  # A 401 returned in single-digit milliseconds with no application log entry is
  # Cloud Run refusing a request before the container runs, and the two settings
  # that cause it appear in no other status field: who holds run.invoker, and
  # whether ingress admits an external caller at all. Base44 authenticates its
  # claims with an HMAC envelope and holds no Google credentials by design, so
  # if neither allUsers nor a principal it can present is an invoker, every
  # customer scan dies at the door while operator calls carrying a minted ID
  # token still succeed -- which reads as a healthy coordinator everywhere else.
  # An empty ingress value is Cloud Run's default, "all".
  echo
  echo "=== Admission coordinator reachability ==="
  printf 'ingress: '
  describe_or_explain "${ADMISSION_COORDINATOR_SERVICE}-ingress" \
    gcloud run services describe "$ADMISSION_COORDINATOR_SERVICE" \
      --region="$GCP_REGION" --project="$GCP_PROJECT" \
      --format="value(metadata.annotations['run.googleapis.com/ingress'])"
  describe_or_explain "${ADMISSION_COORDINATOR_SERVICE}-invoker" \
    gcloud run services get-iam-policy "$ADMISSION_COORDINATOR_SERVICE" \
      --region="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(bindings)'

  echo
  echo "=== Reconciler ==="
  describe_or_explain "$STANDARD150_RECONCILER_JOB" \
    gcloud scheduler jobs describe "$STANDARD150_RECONCILER_JOB" --location="$GCP_REGION" --project="$GCP_PROJECT" --format='yaml(name,state,schedule,httpTarget.uri,httpTarget.oidcToken.serviceAccountEmail)'

  # --freshness is not applied when entries are ordered ascending: the read
  # returns the OLDEST matching entries instead of recent ones, so these reads
  # were quietly reporting 2026-08-15 while an operator waited for the last
  # half hour. An explicit timestamp predicate in the filter is unambiguous and
  # keeps chronological order readable.
  window_start() {
    local minutes="$1"
    date -u -d "-${minutes} minutes" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
      || date -u -v-"${minutes}"M +%Y-%m-%dT%H:%M:%SZ
  }

  local log_since coordinator_log_since coordinator_log_minutes
  log_since="$(window_start 30)"

  # The coordinator gets a much wider window than the worker, because the two
  # differ in volume by orders of magnitude. The worker logs continuously, so
  # with --order=asc and a bounded --limit a wide window would return the OLDEST
  # entries in it and report stale state -- the failure mode #242 fixed. The
  # coordinator writes almost nothing: a few lines per instance lifecycle, plus
  # one per rejected request. A hundred entries there span many hours, so the
  # limit binds long before the window does.
  #
  # Width matters here because a coordinator rejection is written once, at the
  # moment a customer's scan is refused. By the time someone has noticed the
  # refusal, opened CI and dispatched a status read, a half-hour window has
  # usually already closed over it, and the read then reports silence for a
  # failure sitting in Cloud Logging.
  coordinator_log_minutes="${FIXLIST_COORDINATOR_LOG_MINUTES:-720}"
  if ! printf '%s' "$coordinator_log_minutes" | grep -Eq '^[1-9][0-9]{0,4}$'; then
    echo "Refusing status read: coordinator log window must be a positive whole number of minutes." >&2
    exit 2
  fi
  coordinator_log_since="$(window_start "$coordinator_log_minutes")"
  printf 'coordinator_log_window_minutes=%s coordinator_log_since=%s\n' \
    "$coordinator_log_minutes" "$coordinator_log_since"

  # The admission coordinator decides whether a scan is claimed at all, so when
  # a customer is refused with "Scan admission is temporarily unavailable" the
  # reason exists only here. status read the worker and never the coordinator,
  # which left every such refusal undiagnosable from CI: the browser shows one
  # deliberately vague message for admission_unreachable, an unexpected upstream
  # code, and a rejected signature alike.
  echo
  echo "=== Recent admission coordinator logs ==="
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$ADMISSION_COORDINATOR_SERVICE\" AND timestamp>=\"$coordinator_log_since\"" \
    --project="$GCP_PROJECT" --limit=100 --order=asc \
    --format='table(timestamp,severity,jsonPayload.event,jsonPayload.reason,jsonPayload.auth_label,jsonPayload.matches_whitespace_stripped_root,jsonPayload.skew_seconds,jsonPayload.error_code,textPayload)' || true

  echo
  echo "=== Recent admission coordinator requests ==="
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$ADMISSION_COORDINATOR_SERVICE\" AND logName:\"run.googleapis.com%2Frequests\" AND timestamp>=\"$coordinator_log_since\"" \
    --project="$GCP_PROJECT" --limit=100 --order=asc \
    --format='table(timestamp,httpRequest.requestUrl,httpRequest.requestMethod,httpRequest.status,httpRequest.latency)' || true

  echo
  echo "=== Recent worker structured logs ==="
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE\" AND timestamp>=\"$log_since\"" \
    --project="$GCP_PROJECT" --limit=200 --order=asc \
    --format='table(timestamp,resource.labels.revision_name,severity,jsonPayload.event,jsonPayload.scan_id,jsonPayload.attempt_count,jsonPayload.pages_found,jsonPayload.pages_crawled,textPayload)' || true

  echo
  echo "=== Recent worker requests ==="
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE\" AND logName:\"run.googleapis.com%2Frequests\" AND timestamp>=\"$log_since\"" \
    --project="$GCP_PROJECT" --limit=100 --order=asc \
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

# Which Base44 functions the worker source at a given commit posts to. Read out
# of the source rather than kept as a list here, so this cannot drift from the
# cutover it exists to police. Prints one name per line, sorted.
base44_routes_called() {
  local ref="$1"
  git -C "$REPO_ROOT" show "${ref}:scanner-api/app/scan_job.py" 2>/dev/null \
    | python3 -c '
import re, sys
source = sys.stdin.read()
routes = set(re.findall(r"invoke_function\(\s*client,\s*(?:worker_function_name\()?\"([A-Za-z0-9_]+)\"", source))
if "def worker_function_name(" in source:
    routes.update(route[:-2] + "V9" for route in list(routes) if route.endswith("V8"))
print("\n".join(sorted(routes)))
'
}

# The durable pipeline sends every Cloud Task to POST /scan-job and the
# watchdog to POST /scan-job-drain. Those routes exist only in builds that
# contain scanner-api/app/scan_job.py. A worker built from older source without
# them accepts the deployment, serves /health, and 404s every task -- and the
# watchdog 404s too, so runs never reach a terminal state. Unauthenticated
# probes cannot answer this: Cloud Run IAM rejects them before routing. The
# only external proof is the image's build provenance.
verify_worker_routes() {
  local revision image timeout release_sha verdict=0
  local want_routes got_routes revision_json builds_json
  revision="${TARGET_REVISION:-$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(status.latestReadyRevisionName)')}"
  [ -n "$revision" ] || { echo "No ready revision found." >&2; exit 2; }

  # A deployment may be specified by a mutable tag, but the *exact revision*
  # records the resolved immutable digest even for tag-form image references.
  # Do not attribute a running digest to the first build sharing a tag/name.
  OPERATOR_TMP="$(mktemp -d)"
  chmod 700 "$OPERATOR_TMP"
  revision_json="$OPERATOR_TMP/worker-revision.json"
  builds_json="$OPERATOR_TMP/cloud-builds.json"
  gcloud run revisions describe "$revision" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json > "$revision_json"
  image="$(python3 - "$revision_json" <<'PY'
import json, sys
revision = json.load(open(sys.argv[1], encoding="utf-8"))
print(str(((revision.get("spec") or {}).get("containers") or [{}])[0].get("image") or ""))
PY
)"
  echo "revision: $revision"
  echo "image:    $image"

  echo
  echo "=== Build provenance (exact Ready revision + resolved digest) ==="
  # This bounded recent-build view may not include the original build.
  # Absence must be INDETERMINATE, never a fallback to image-name matching.
  if ! gcloud builds list --project="$GCP_PROJECT" --region="$GCP_REGION" --limit=50 \
    --format=json > "$builds_json"; then
    echo "INDETERMINATE: unable to retrieve Cloud Build records." >&2
    return 1
  fi
  if ! release_sha="$(python3 "$REPO_ROOT/scripts/verify_worker_build_provenance.py" \
      --revision-json "$revision_json" --builds-json "$builds_json" \
      --revision "$revision" --service "$CLOUD_RUN_SERVICE")"; then
    echo "INDETERMINATE: cannot uniquely bind the exact Ready revision's image digest to a SUCCESS build." >&2
    release_sha=""
    verdict=1
  fi

  # The runner has this repository checked out with full history, so whether a
  # SHA declares the durable routes is a fact we can decide here rather than
  # asking a human to eyeball it.
  echo
  echo "=== Route verification ==="
  if [ -z "$release_sha" ]; then
    echo "INDETERMINATE: no uniquely authenticated successful build/source for this exact revision digest."
    echo "The build may be absent from the recent-record window, malformed or ambiguous."
    echo "Do not infer a source from its mutable tag. Verify immutable provenance before promotion."
    verdict=1
  elif ! git cat-file -e "${release_sha}^{commit}" 2>/dev/null; then
    echo "INDETERMINATE: _RELEASE_SHA $release_sha is not a commit in this repository."
    verdict=1
  else
    echo "built from: $release_sha"
    # Consume each source file through EOF. grep -q can close the pipe on a
    # match and cause git show to fail with SIGPIPE under set -o pipefail.
    if git cat-file -e "${release_sha}:scanner-api/app/scan_job.py" 2>/dev/null \
      && git show "${release_sha}:scanner-api/app/main.py" 2>/dev/null | grep -Fx '@app.post("/scan-job")' >/dev/null \
      && git show "${release_sha}:scanner-api/app/main.py" 2>/dev/null | grep -Fx '@app.post("/scan-job-drain")' >/dev/null; then
      echo "PASS: that commit has scan_job.py and declares /scan-job and /scan-job-drain."
    else
      echo "FAIL: that commit does NOT declare both durable routes."
      echo "Every Cloud Task would 404, and the drain watchdog would 404 too,"
      echo "so runs would never reach a terminal state. Rebuild the worker from"
      echo "cloudbuild.durable-worker.yaml at current main before promoting."
      verdict=1
    fi

    # The 2026-09-03 cutover moved the browser and the worker onto the V2 Base44
    # function names. An image built before it still posts to the legacy names,
    # which Base44 serves from an older compiled handler -- so a scan would be
    # accepted, persist nothing, and never reach a terminal state. Publishing
    # Base44 does not move the worker, so provenance is the only place to catch
    # this before traffic moves.
    echo
    echo "=== Base44 route generation ==="
    want_routes="$(base44_routes_called HEAD)"
    got_routes="$(base44_routes_called "$release_sha")"
    printf 'release source calls: %s\n' "$(echo "$want_routes" | tr '\n' ' ')"
    printf 'running image calls:  %s\n' "$(echo "$got_routes" | tr '\n' ' ')"
    if [ -z "$want_routes" ]; then
      echo "FAIL: the release source declares no Base44 worker routes, so there is"
      echo "nothing to compare the running image against."
      verdict=1
    elif [ "$want_routes" = "$got_routes" ]; then
      echo "PASS"
    else
      echo "FAIL: the running worker calls a different Base44 route generation than"
      echo "this release source. Every scan would be accepted and then persist"
      echo "nothing. Rebuild the worker from cloudbuild.durable-worker.yaml at"
      echo "current main and promote that revision before opening intake."
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

# Build provenance proves which source the image was compiled from. It cannot
# prove what the running container computes. persistDurableScanAuthority admits
# a scan only when its beta_revision_fingerprint equals the fingerprint this
# release records, so a revision that serves a different fingerprint passes
# every check above and then fails every scan it is handed --
# authority_snapshot_not_eligible__beta_revision_fingerprint, with a green
# promotion behind it. GET /revision is the only reading of that runtime truth.
#
# The probe has to reach the revision under test rather than whatever holds
# traffic. A revision tag addresses one revision directly; without a tag the
# answer only stands when that revision already serves 100%. For Cloud Run
# traffic tags, request destination and ID-token audience are deliberately
# separate: the request targets the tag URL while the token uses the canonical
# service audience. Anything unattributable remains INDETERMINATE.
verify_worker_runtime_revision() {
  local revision="${1:-$TARGET_REVISION}" expected_sha="${2:-}"
  local recorded="${3:-$REPO_ROOT/data/beta-crawler-revision.json}"
  local service_json response probe_url token code compare_status=0

  echo
  echo "=== Runtime revision fingerprint ==="

  RUNTIME_PROBE_TMP="$(mktemp -d)" || return 1
  chmod 700 "$RUNTIME_PROBE_TMP" || return 1
  service_json="$RUNTIME_PROBE_TMP/service.json"
  response="$RUNTIME_PROBE_TMP/revision.json"

  gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json > "$service_json" || return 1

  service_url="$(python3 - "$service_json" <<'PY'
import json, sys
status = json.load(open(sys.argv[1], encoding="utf-8")).get("status") or {}
print(str(status.get("url") or ""))
PY
)"
  if [ -z "$service_url" ]; then
    echo "INDETERMINATE: Cloud Run reported no canonical service URL."
    return 1
  fi
  if [ -z "$FIXLIST_WORKER_TOKEN_AUDIENCE" ]; then
    echo "INDETERMINATE: no worker token audience was declared."
    return 1
  fi
  if [ "$FIXLIST_WORKER_TOKEN_AUDIENCE" != "$service_url" ]; then
    echo "INDETERMINATE: worker token audience does not match the canonical Cloud Run service URL."
    return 1
  fi

  if [ -z "$revision" ]; then
    revision="$(python3 - "$service_json" <<'PY'
import json, sys
status = json.load(open(sys.argv[1], encoding="utf-8")).get("status") or {}
traffic = status.get("traffic") or []
print(next((str(t.get("revisionName") or "") for t in traffic if int(t.get("percent") or 0) == 100), ""))
PY
)"
  fi
  if [ -z "$revision" ]; then
    echo "INDETERMINATE: no revision was named and none serves 100% of traffic."
    return 1
  fi
  echo "revision under test: $revision"

  probe_url="$(python3 - "$service_json" "$revision" "$FIXLIST_WORKER_PROBE_URL" <<'PY'
# runtime-revision-probe-url
import json, sys

service = json.load(open(sys.argv[1], encoding="utf-8"))
revision = sys.argv[2]
requested_url = sys.argv[3]
status = service.get("status") or {}
addressable = []
for entry in status.get("traffic") or []:
    if str(entry.get("revisionName") or "") != revision:
        continue
    # A revision tag resolves to one revision no matter how traffic is split,
    # so it is the only URL that can address a candidate before promotion.
    if entry.get("tag") and entry.get("url"):
        addressable.append(str(entry["url"]))
    if int(entry.get("percent") or 0) == 100 and status.get("url"):
        addressable.append(str(status["url"]))
# Cloud Run tag requests use the tag URL as their HTTP destination but the
# canonical service URL as their ID-token audience. The caller-provided
# target must exactly equal a URL in the trusted service traffic description.
# Never send an ID token to any other caller-controlled endpoint.
from urllib.parse import urlsplit
def safe_run_url(url):
    parts = urlsplit(url)
    canonical = urlsplit(str(status.get("url") or ""))
    return (parts.scheme == "https" and bool(parts.hostname)
            and parts.hostname.endswith(".run.app")
            and canonical.scheme == "https" and bool(canonical.hostname)
            and canonical.hostname.endswith(".run.app")
            and parts.username is None and parts.password is None
            and parts.port is None and not parts.path and not parts.query
            and not parts.fragment)
addressable = [url for url in addressable if safe_run_url(url)]
if requested_url:
    print(requested_url if requested_url in addressable else "")
else:
    # A 0% candidate requires the explicit, verified tagged destination.
    # Never infer one or fall through to the serving service URL.
    service_url = str(status.get("url") or "")
    print(service_url if service_url in addressable else "")
PY
)"
  if [ -z "$probe_url" ]; then
    echo "INDETERMINATE: no verified URL addresses revision $revision."
    echo "The Cloud Run ID-token audience must be the canonical service URL."
    echo "For a 0%-traffic candidate, FIXLIST_WORKER_PROBE_URL must equal the"
    echo "exact tagged URL in the authenticated service traffic metadata."
    return 1
  fi
  echo "probe URL:           $probe_url"

  # The worker is private: Cloud Run IAM rejects an unauthenticated probe before
  # routing, so /revision is unreadable without an invoker token. The token is
  # minted by the caller and handed over by name, never by gcloud here: the
  # federated credential this script runs under is an external_account, which
  # gcloud refuses to mint an audience-scoped identity token from. Same contract
  # as FIXLIST_OPERATOR_ID_TOKEN.
  token="$FIXLIST_WORKER_ID_TOKEN"
  if [ -z "$token" ]; then
    echo "INDETERMINATE: no identity token was supplied for the private worker."
    echo "Set FIXLIST_WORKER_ID_TOKEN to a token minted for the canonical Cloud Run service URL by a"
    echo "principal holding roles/run.invoker on $CLOUD_RUN_SERVICE."
    return 1
  fi

  code="$(curl --silent --show-error --max-time 20 \
    --output "$response" --write-out '%{http_code}' \
    --header "authorization: Bearer ${token}" \
    "${probe_url}/revision" || echo 000)"

  case "$code" in
    200) ;;
    401|403)
      echo "INDETERMINATE: /revision returned $code -- the identity token was rejected."
      echo "Grant roles/run.invoker on $CLOUD_RUN_SERVICE to the calling principal."
      return 1
      ;;
    404)
      echo "FAIL: /revision returned 404. This build predates the runtime revision"
      echo "endpoint, so what it computes cannot be read. Rebuild from current main."
      return 1
      ;;
    *)
      echo "INDETERMINATE: /revision returned ${code}; expected 200."
      return 1
      ;;
  esac

  python3 - "$response" "$recorded" "$expected_sha" "$revision" <<'PY' || compare_status=$?
# runtime-revision-comparator
import json, sys

response_path, recorded_path, expected_sha, expected_revision = sys.argv[1:5]
try:
    live = json.load(open(response_path, encoding="utf-8"))
except Exception:
    print("FAIL: /revision did not return JSON.")
    raise SystemExit(1)
if not isinstance(live, dict):
    print("FAIL: /revision did not return a JSON object.")
    raise SystemExit(1)
recorded = json.load(open(recorded_path, encoding="utf-8"))

live_fingerprint = str(live.get("fingerprint") or "")
recorded_fingerprint = str(recorded.get("fingerprint") or "")
live_sha = str(live.get("source_sha") or "")
live_worker_revision = str(live.get("worker_revision") or "")
print("runtime fingerprint:  %s" % (live_fingerprint or "(absent)"))
print("recorded fingerprint: %s" % (recorded_fingerprint or "(absent)"))
print("runtime source_sha:   %s" % (live_sha or "(unset)"))
print("runtime worker revision: %s" % (live_worker_revision or "(absent)"))
print("expected worker revision: %s" % (expected_revision or "(absent)"))

failed = False
live_components = live.get("component_versions")
recorded_components = recorded.get("component_versions") or {}

if not live_fingerprint or not recorded_fingerprint:
    print("FAIL: a fingerprint is missing, so the two cannot be compared.")
    failed = True
elif live_fingerprint != recorded_fingerprint:
    failed = True
    print("FAIL: the running worker computes a different release identity than the")
    print("one this commit records. Every scan it serves is rejected as")
    print("authority_snapshot_not_eligible__beta_revision_fingerprint.")

# The fingerprint is a hash of the marker set, so comparing the set itself is
# not redundant: it is what catches a response that carries the right hash with
# the wrong or a truncated marker set, and it is the only reading that can say
# *which* marker moved.
if not isinstance(live_components, dict) or not live_components:
    failed = True
    print("FAIL: /revision returned no release markers, so the running identity")
    print("cannot be verified against the frozen one.")
elif live_components != recorded_components:
    failed = True
    print("FAIL: the running worker's release markers differ from the frozen set.")

if isinstance(live_components, dict) and live_components != recorded_components:
    divergent = [
        name
        for name in sorted(set(live_components) | set(recorded_components))
        if live_components.get(name) != recorded_components.get(name)
    ]
    print("divergent markers (runtime -> recorded):")
    for name in divergent:
        print("  %s: %s -> %s" % (
            name,
            live_components.get(name, "(absent)"),
            recorded_components.get(name, "(absent)"),
        ))
elif failed and live_fingerprint != recorded_fingerprint:
    print("No marker differs, so the divergence is in how the fingerprint is")
    print("computed rather than in the marker set it is computed over.")

# A container that cannot say what it was built from must never be promoted:
# tying running bytes to a reviewed commit is the whole point of the check, so
# an unstamped container is a hard failure and not a warning.
if not live_sha:
    failed = True
    print("FAIL: the container declares no FIXLIST_WORKER_SOURCE_SHA, so its")
    print("running bytes cannot be tied to any reviewed commit.")
elif expected_sha and live_sha != expected_sha:
    failed = True
    print("FAIL: the container says it was built from %s, but the release being" % live_sha)
    print("promoted is %s." % expected_sha)

# The revision name comes from Cloud Run's own K_REVISION environment in
# the process answering /revision, not from the caller or the source-SHA stamp.
# Comparing it with the control-plane-selected revision also catches an
# A -> B -> A routing switch hidden between two identical service snapshots.
if not expected_revision or live_worker_revision != expected_revision:
    failed = True
    print("FAIL: the responding worker revision is absent or differs from the Cloud Run revision selected for this probe.")

raise SystemExit(1 if failed else 0)
PY

  if [ "$compare_status" -ne 0 ]; then
    return 1
  fi

  # A canonical service URL is a moving router. If traffic changes between
  # the first Cloud Run describe and /revision, a matching response might have
  # come from a *different* revision. Tags can be reassigned too. Re-read the
  # control plane after the probe and require the selected destination to
  # remain attributed to the same revision in both snapshots.
  # This is a fail-closed stability observation, not a claim of atomic routing.
  local after_service_json route_binding_status=0
  after_service_json="$RUNTIME_PROBE_TMP/service-after.json"
  gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json > "$after_service_json" || return 1
  python3 - "$service_json" "$after_service_json" "$revision" "$probe_url" "$FIXLIST_WORKER_TOKEN_AUDIENCE" <<'PY' || route_binding_status=$?
# runtime-revision-route-stability
import json, sys

before_path, after_path, revision, probe_url, audience = sys.argv[1:6]

def attributed(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    status = data.get("status") if isinstance(data, dict) else None
    if not isinstance(status, dict) or status.get("url") != audience:
        return False
    traffic = status.get("traffic")
    if not isinstance(traffic, list):
        return False
    for row in traffic:
        if not isinstance(row, dict) or row.get("revisionName") != revision:
            continue
        # 100% service routing is valid only while that exact revision serves.
        if probe_url == audience:
            if row.get("percent") == 100:
                return True
        # A tagged URL addresses only the revision the tag currently names.
        elif row.get("tag") and row.get("url") == probe_url:
            return True
    return False

if not (attributed(before_path) and attributed(after_path)):
    print("INDETERMINATE: Cloud Run routing for the probed revision changed or became unreadable during verification.")
    raise SystemExit(1)
print("PASS: route attribution remained stable across the authenticated probe.")
PY
  if [ "$route_binding_status" -ne 0 ]; then
    return 1
  fi
  echo "PASS: the running worker computes the release identity this commit records."
  if [[ "${FIXLIST_VERIFY_STAGED_BASE44_RUNTIME:-}" == 1 ]]; then
    local auth_file="$RUNTIME_PROBE_TMP/auth-header"
    (umask 077; printf 'Authorization: Bearer %s\n' "$token" > "$auth_file")
    token=""
    # Use the same verified Cloud Run URL and canonical audience as /revision.
    # The worker signs the three known Base44 requests with its mounted key.
    if ! curl -q --silent --show-error --fail --proto '=https' --noproxy '*' \
      --max-time 25 --max-filesize 16384 --header "@$auth_file" \
      --output "$RUNTIME_PROBE_TMP/staged-base44-runtime.json" \
      "${probe_url}/staged/base44-runtime"; then
      echo "FAIL: the staged worker could not verify the signed Base44 routes." >&2
      return 1
    fi
    python3 "$REPO_ROOT/scripts/verify_staged_worker_base44_runtime.py" \
      --source-sha "$expected_sha" --revision "$revision" \
      < "$RUNTIME_PROBE_TMP/staged-base44-runtime.json"
  fi
}

# A candidate at 0% traffic has no address of its own, so its runtime identity
# cannot be read before it is promoted -- which is the only moment the reading
# is still cheap to act on. A revision tag gives it one without moving any
# traffic, so the gate can run while a failure still costs nothing but a tag.
#
# --update-tags adds this one tag and leaves every other tag and the whole
# traffic split untouched; --set-tags would silently drop tags this release
# never knew about.
tag_worker_candidate() {
  local revision="$1" tag_url percent
  [ -n "$revision" ] || { echo "No revision to tag." >&2; exit 2; }
  if [[ "$WORKER_CANDIDATE_TAG" == canary-* ]]; then
    echo 'Refusing to reassign a reserved canary tag; use the verified canary preflight.' >&2
    exit 2
  fi

  # Tagging is a mutation of the live service, so it is confirmation-gated on
  # the exact revision name like every other traffic operation here.
  require_confirmation "$revision"

  percent="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json \
    | python3 -c '
import json, sys
traffic = (json.load(sys.stdin).get("status") or {}).get("traffic") or []
revision = sys.argv[1]
print(sum(int(t.get("percent") or 0) for t in traffic if t.get("revisionName") == revision))
' "$revision")"
  # Tagging a revision that already serves would make the gate prove nothing:
  # the point is to verify a candidate *before* it can answer customer traffic.
  if [ "$percent" != "0" ]; then
    echo "Refusing to tag $revision: it already receives ${percent}% of traffic." >&2
    exit 2
  fi

  gcloud run services update-traffic "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --update-tags="${WORKER_CANDIDATE_TAG}=${revision}" >/dev/null

  tag_url="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json \
    | python3 -c '
import json, sys
status = json.load(sys.stdin).get("status") or {}
revision, tag = sys.argv[1], sys.argv[2]
for entry in status.get("traffic") or []:
    if entry.get("revisionName") == revision and entry.get("tag") == tag and entry.get("url"):
        print(entry["url"])
        break
' "$revision" "$WORKER_CANDIDATE_TAG")"
  [ -n "$tag_url" ] || { echo "Tag $WORKER_CANDIDATE_TAG did not resolve to a URL for $revision." >&2; exit 2; }

  # Re-read rather than assume: --update-tags must not have moved traffic.
  percent="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json \
    | python3 -c '
import json, sys
traffic = (json.load(sys.stdin).get("status") or {}).get("traffic") or []
revision = sys.argv[1]
print(sum(int(t.get("percent") or 0) for t in traffic if t.get("revisionName") == revision))
' "$revision")"
  if [ "$percent" != "0" ]; then
    echo "Tagging moved traffic to $revision (${percent}%); refusing to continue." >&2
    exit 2
  fi

  echo "candidate_tag_url=$tag_url"
  echo "WORKER_CANDIDATE_TAGGED revision=$revision tag=$WORKER_CANDIDATE_TAG percent=0"
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

refuse_unaccepted_direct_vpc_promotion() {
  local revision="$1" tmp
  tmp="$(mktemp)"
  gcloud run revisions describe "$revision" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" --format=json > "$tmp"
  python3 - "$tmp" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
annotations = value.get("metadata", {}).get("annotations", {}) or {}
spec = value.get("spec", {}) or {}
containers = spec.get("containers") or [{}]
env = {item.get("name"): item.get("value", "") for item in containers[0].get("env", [])}
mode = str(env.get("FIXLIST_EGRESS_MODE") or "none")
direct = bool(annotations.get("run.googleapis.com/network-interfaces"))
if direct or mode != "none":
    raise SystemExit("Refusing promotion: Direct-VPC/static-egress candidates require a dedicated accepted-egress promotion gate")
PY
  rm -f "$tmp"
}

promote_revision() {
  refuse_unaccepted_direct_vpc_promotion "$TARGET_REVISION"
  # Staging remains 0%-traffic and rollback remains available. New promotions
  # cannot send customers to a source that is still explicitly a candidate.
  if [[ "$OPERATION" == "promote-worker" ]]; then
    python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA" --worker
  fi
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
    "$BARRIER_EXPECTED_GENERATION" "$CUTOVER_REASON" "$CHANGE_TICKET" "$ACCEPTANCE_COHORT_ID" "$SOURCE_SHA" <<'PY'
import json, sys

operation, destination, prior_mode, generation, reason, ticket, cohort, source_sha = sys.argv[1:]
payload = {
    "operation": operation,
    "reason": reason,
    "change_ticket": ticket,
}
if operation == "status":
    payload["expected_generation"] = int(generation)
else:
    payload["intended_prior"] = {"mode": prior_mode, "generation": int(generation)}
if operation in {"hold_150_pilot", "hold_500_pilot", "hold_public_150", "hold_eligible_500"}:
    payload["cohort_id"] = cohort
if operation in {"hold_150_pilot", "hold_eligible_500"}:
    payload["source_sha"] = source_sha
with open(destination, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
PY
}

write_acceptance_payload() {
  local destination="$1" operation="$2"
  python3 - "$destination" "$operation" "$BARRIER_EXPECTED_GENERATION" "$CUTOVER_REASON" "$CHANGE_TICKET" \
    "$ACCEPTANCE_COHORT_ID" "$ACCEPTANCE_RELEASE_ID" "$ACCEPTANCE_SOURCE_SHA" \
    "$ACCEPTANCE_OWNER_USER_IDS" "$ACCEPTANCE_EXPIRES_AT" \
    "$ACCEPTANCE_TOTAL_CLAIM_BUDGET" "$ACCEPTANCE_PER_OWNER_CLAIM_BUDGET" \
    "$ACCEPTANCE_LAUNCHER_BUILD_ID" "$LEGACY_ACCESS" "$LEGACY_ACCESS_PREFLIGHT" <<'PY'
import json, re, sys

(destination, operation, generation, reason, ticket, cohort_id, release_id, source_sha,
 owners_raw, expires_at, total_budget, owner_budget, launcher_build_id, legacy_access, legacy_preflight) = sys.argv[1:]
owners = [item.strip() for item in owners_raw.split(",") if item.strip()]
safe_id = re.compile(r"^[A-Za-z0-9_-]{6,160}$")
if not safe_id.fullmatch(cohort_id) or not safe_id.fullmatch(release_id):
    raise SystemExit("Acceptance cohort and release IDs must be bounded safe IDs")
if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
    raise SystemExit("Acceptance source SHA must be exact lowercase Git SHA")
if launcher_build_id and not re.fullmatch(r"[0-9a-f]{64}", launcher_build_id):
    raise SystemExit("Acceptance launcher build ID must be a 64-character SHA256")
eligible_500 = operation == "start_eligible_500"
if eligible_500 and owners:
    raise SystemExit("Eligible Standard 500 does not accept a named owner roster")
if not eligible_500 and (not owners or len(owners) != len(set(owners)) or not all(safe_id.fullmatch(item) for item in owners)):
    raise SystemExit("Acceptance owner allowlist is invalid")
# Older coordinators reject this operation before they can open the barrier.
if operation == "acceptance_only" and launcher_build_id:
    operation = "published_pilot_with_legacy" if legacy_access else "published_pilot_acceptance"
payload = {
    "operation": operation,
    "reason": reason,
    "change_ticket": ticket,
    "intended_prior": {"mode": "open" if operation in {"start_500_pilot", "start_eligible_500"} else "closed", "generation": int(generation)},
    {"open_public_150": "public_150", "start_eligible_500": "public_500"}.get(operation, "acceptance"): {
        "cohort_id": cohort_id,
        "release_id": release_id,
        "source_sha": source_sha,
        **({} if eligible_500 else {"owner_user_ids": owners}),
        "expires_at": int(expires_at),
        "total_claim_budget": int(total_budget),
        "per_owner_claim_budget": int(owner_budget),
        **({"required_launcher_build_id": launcher_build_id} if launcher_build_id else {}),
    },
}
if legacy_access:
    payload["legacy_access"] = json.loads(legacy_access)
    payload["legacy_preflight"] = json.loads(legacy_preflight)
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
  if [[ "$operation" == "acceptance_only" || "$operation" == "start_500_pilot" || "$operation" == "open_public_150" || "$operation" == "start_eligible_500" ]]; then
    write_acceptance_payload "$body" "$operation"
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
  local expected_operation="$1" expected_fields=9
  case "$expected_operation" in
    start_500_pilot|hold_500_pilot|hold_150_pilot|hold_public_150|start_eligible_500|hold_eligible_500) expected_fields=4 ;;
  esac
  mapfile -t _barrier_values < <(python3 - "$BARRIER_RESPONSE_FILE" "$expected_operation" \
    "$OPERATOR_TMP/operator-key" "$ADMISSION_DRAIN_SNAPSHOT_DERIVATION_LABEL" "$ACCEPTANCE_LAUNCHER_BUILD_ID" \
    "$ACCEPTANCE_COHORT_ID" "$SOURCE_SHA" "$ACCEPTANCE_OWNER_USER_IDS" "$ACCEPTANCE_EXPIRES_AT" \
    "$BARRIER_EXPECTED_GENERATION" "$LEGACY_ACCESS_SHA256" "$LEGACY_ACCESS_PREFLIGHT" \
    "$ACCEPTANCE_RELEASE_ID" "$ACCEPTANCE_TOTAL_CLAIM_BUDGET" "$ACCEPTANCE_PER_OWNER_CLAIM_BUDGET" <<'PY'
import hashlib, hmac, json, re, sys

(path, expected, key_path, snapshot_label, launcher_build_id, cohort_id, source_sha,
 owners_raw, expires_at, prior_generation, legacy_digest, legacy_preflight, release_id, total_budget, owner_budget) = sys.argv[1:]
value = json.load(open(path, encoding="utf-8"))
if value.get("success") is not True or value.get("operation") != expected:
    raise SystemExit("Unexpected operator response")
barrier = value.get("barrier") or {}
pilot_500_operation = expected in {"start_500_pilot", "hold_500_pilot"}
eligible_500_operation = expected in {"start_eligible_500", "hold_eligible_500"}
pilot_operation = pilot_500_operation or expected == "hold_150_pilot"
public_hold = expected == "hold_public_150"
scoped_operation = pilot_operation or public_hold or eligible_500_operation
snapshot_field = {
    "start_eligible_500": "eligible_500_snapshot",
    "hold_eligible_500": "eligible_500_snapshot",
}.get(expected, "pilot_snapshot" if pilot_operation else "public_150_snapshot" if public_hold else "drain_snapshot")
snapshot = value.get(snapshot_field) or {}
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
if type(generation) is not int or generation < 0:
    raise SystemExit("Invalid barrier generation")
expected_version = {
    "start_500_pilot": "admission_published_500_pilot_snapshot_v1",
    "hold_500_pilot": "admission_published_500_pilot_snapshot_v1",
    "hold_150_pilot": "admission_published_150_pilot_snapshot_v1",
    "hold_public_150": "admission_public_150_hold_snapshot_v1",
    "start_eligible_500": "admission_eligible_500_snapshot_v1",
    "hold_eligible_500": "admission_eligible_500_snapshot_v1",
}.get(expected, "admission_drain_snapshot_v1")
snapshot_kind = "pilot" if pilot_operation else "scope" if scoped_operation else "drain"
if version != expected_version or not snapshot_id:
    raise SystemExit(f"Invalid {snapshot_kind} snapshot identity")
if not re.fullmatch(r"[0-9a-f]{64}", proof):
    raise SystemExit(f"Invalid {snapshot_kind} snapshot proof")
if not hmac.compare_digest(proof, expected_proof):
    raise SystemExit(f"{snapshot_kind.capitalize()} snapshot signature mismatch")
# Bind unsigned transport mode/generation to the authenticated snapshot.
signed_barrier = snapshot.get("barrier")
if (not isinstance(signed_barrier, dict)
        or signed_barrier.get("mode") != mode
        or type(signed_barrier.get("generation")) is not int
        or signed_barrier["generation"] != generation):
    raise SystemExit("Barrier envelope disagrees with signed drain snapshot")
boundary = snapshot.get("boundary") or {}
if expected == "acceptance_only" and launcher_build_id:
    if boundary.get("required_launcher_build_id") != launcher_build_id:
        raise SystemExit("Published pilot launcher binding is missing from the signed snapshot")
if expected == "hold_150_pilot" or (expected == "acceptance_only" and legacy_digest):
    legacy = boundary.get("legacy_customer_access") or {}
    signed_barrier = snapshot.get("barrier") or {}
    if (mode != "acceptance_only" or signed_barrier.get("mode") != mode or signed_barrier.get("generation") != generation
            or generation != int(prior_generation) + 1
            or signed_barrier.get("current_snapshot_id") != snapshot_id or barrier.get("current_snapshot_id") != snapshot_id
            or legacy.get("coordinator_source_sha") != source_sha or legacy.get("page_cap") != 150
            or not re.fullmatch(r"[0-9a-f]{40}", str(legacy.get("source_sha") or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(legacy.get("configuration_sha256") or ""))
            or type(legacy.get("owner_count")) is not int or legacy["owner_count"] < 1
            or type(legacy.get("verified_at")) is not int or legacy["verified_at"] < 1
            or legacy.get("state") not in {"configured", "expired"}):
        raise SystemExit("The signed snapshot does not establish the approved legacy access lane")
    if expected == "hold_150_pilot":
        pilot = boundary.get("published_150_pilot") or {}
        if (pilot != {"state": "held", "cohort_id": cohort_id, "source_sha": source_sha}
                or snapshot.get("drain_ready") is not False or "counts" in snapshot):
            raise SystemExit("The signed snapshot does not establish the named Standard 150 pilot hold")
    elif (legacy.get("configuration_sha256") != legacy_digest or legacy.get("state") != "configured"
            or legacy["verified_at"] != json.loads(legacy_preflight)["verified_at"]
            or boundary.get("cohort_id") != cohort_id or boundary.get("source_sha") != source_sha):
        raise SystemExit("Named Standard 150 pilot or approved legacy configuration mismatch")
if pilot_500_operation or eligible_500_operation:
    scope = boundary.get("public_500" if eligible_500_operation else "published_500_pilot") or {}
    signed_barrier = snapshot.get("barrier") or {}
    state = "configured" if expected in {"start_500_pilot", "start_eligible_500"} else "held"
    if (mode != "open" or signed_barrier.get("mode") != mode or signed_barrier.get("generation") != generation
            or generation != int(prior_generation) + 1
            or signed_barrier.get("current_snapshot_id") != snapshot_id or barrier.get("current_snapshot_id") != snapshot_id
            or snapshot.get("drain_ready") is not False or "counts" in snapshot
            or scope.get("state") != state or scope.get("page_cap") != 500 or scope.get("cohort_id") != cohort_id):
        raise SystemExit("The signed snapshot does not establish this Standard 500 change")
    if eligible_500_operation and (scope.get("source_sha") != source_sha
            or signed_barrier.get("claim_sequence") != barrier.get("claim_sequence")):
        raise SystemExit("Eligible Standard 500 source or claim sequence mismatch")
    if eligible_500_operation:
        public_150 = boundary.get("public_150") or {}
        if (public_150.get("page_cap") != 150 or not public_150.get("cohort_id")
                or public_150.get("state") not in {"configured", "held", "expired"}):
            raise SystemExit("Eligible Standard 500 requires a signed Standard 150 boundary")
    if eligible_500_operation and state == "configured":
        if (scope.get("source_sha") != source_sha or scope.get("required_launcher_build_id") != launcher_build_id
                or scope.get("expires_at") != int(expires_at) or scope.get("release_id") != release_id
                or scope.get("total_claim_budget") != int(total_budget)
                or scope.get("per_owner_claim_budget") != int(owner_budget)):
            raise SystemExit("Eligible Standard 500 source, launcher, release, expiry or budget mismatch")
    elif state == "configured":
        owners = sorted(item.strip() for item in owners_raw.split(",") if item.strip())
        digest = hashlib.sha256(json.dumps(owners, separators=(",", ":")).encode("utf-8")).hexdigest()
        if (scope.get("source_sha") != source_sha or scope.get("required_launcher_build_id") != launcher_build_id
                or scope.get("owner_count") != len(owners) or scope.get("owner_cohort_sha256") != digest
                or scope.get("expires_at") != int(expires_at)):
            raise SystemExit("Standard 500 pilot source, launcher, account set or expiry mismatch")
if expected in {"open_public_150", "hold_public_150"}:
    public_150 = (snapshot.get("boundary") or {}).get("public_150") or {}
    signed_barrier = snapshot.get("barrier") or {}
    if (mode != "open" or signed_barrier.get("mode") != mode or signed_barrier.get("generation") != generation
            or generation != int(prior_generation) + 1 or signed_barrier.get("claim_sequence") != barrier.get("claim_sequence")
            or signed_barrier.get("current_snapshot_id") != snapshot_id or barrier.get("current_snapshot_id") != snapshot_id
            or public_150.get("page_cap") != 150 or public_150.get("cohort_id") != cohort_id):
        raise SystemExit("The signed snapshot does not establish this public Standard 150 cohort change")
    if public_hold:
        if public_150.get("state") != "held" or snapshot.get("drain_ready") is not False or "counts" in snapshot:
            raise SystemExit("The signed snapshot does not establish a scoped hold")
    else:
        owners = sorted(item.strip() for item in owners_raw.split(",") if item.strip())
        digest = hashlib.sha256(json.dumps(owners, separators=(",", ":")).encode("utf-8")).hexdigest()
        if (public_150.get("state") != "configured" or snapshot.get("drain_ready") is not True
                or public_150.get("source_sha") != source_sha or public_150.get("required_launcher_build_id") != launcher_build_id
                or public_150.get("owner_count") != len(owners) or public_150.get("owner_cohort_sha256") != digest
                or public_150.get("release_id") != release_id or public_150.get("expires_at") != int(expires_at)
                or public_150.get("total_claim_budget") != int(total_budget)
                or public_150.get("per_owner_claim_budget") != int(owner_budget)):
            raise SystemExit("Public Standard 150 source, launcher, account set or budget mismatch")
if not scoped_operation and any(not isinstance(item, int) or item < 0 for item in (total, live, active, expired, bound)):
    raise SystemExit("Invalid drain counts")
print(mode)
print(generation)
print(snapshot_id)
print("true" if ready else "false")
if not scoped_operation:
    print(total)
    print(live)
    print(active)
    print(expired)
    print(bound)
PY
  )
  if [[ ${#_barrier_values[@]} -ne $expected_fields ]]; then
    echo "Coordinator barrier response did not satisfy the signed snapshot contract." >&2
    return 1
  fi
  BARRIER_MODE="${_barrier_values[0]}"
  BARRIER_GENERATION="${_barrier_values[1]}"
  BARRIER_SNAPSHOT_ID="${_barrier_values[2]}"
  BARRIER_DRAIN_READY="${_barrier_values[3]}"
  if [[ "$expected_fields" -eq 4 ]]; then
    return 0
  fi
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
  if [[ "${FIXLIST_DRAIN_READBACK_SOURCE_GUARD:-current}" == pinned && "${GITHUB_ACTIONS:-}" != true ]]; then
    source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
    fixlist_require_merged_checkout "$REPO_ROOT" "$SOURCE_SHA"
  else
    require_exact_main_owner_source
  fi
  require_confirmation "VERIFY-ZERO-ADMISSION:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  verify_zero_admission_obligations
}

open_claim_barrier() {
  require_exact_main_owner_source
  require_barrier_inputs
  local operation=open
  if [[ -n "${ACCEPTANCE_COHORT_ID}${ACCEPTANCE_RELEASE_ID}${ACCEPTANCE_OWNER_USER_IDS}${ACCEPTANCE_EXPIRES_AT}${ACCEPTANCE_TOTAL_CLAIM_BUDGET}${ACCEPTANCE_PER_OWNER_CLAIM_BUDGET}${ACCEPTANCE_LAUNCHER_BUILD_ID}" ]]; then
    operation=open_public_150
    require_pilot_launcher_build
    [[ "$ACCEPTANCE_SOURCE_SHA" == "$SOURCE_SHA" ]] || return 1
    require_confirmation "OPEN-PUBLIC-150-COHORT:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}:${ACCEPTANCE_LAUNCHER_BUILD_ID}"
  else
    require_confirmation "OPEN-STANDARD150-CLAIMS:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
  fi
  require_closed_drained_barrier
  require_drain_plane_live
  BARRIER_EXPECTED_PRIOR_MODE="closed"
  call_barrier_operator "$operation" "$ADMISSION_BARRIER_OPEN_PATH"
  parse_barrier_response "$operation"
  [[ "$BARRIER_MODE" == "open" ]] || { echo "Coordinator did not open the claim barrier." >&2; return 1; }
  if [[ "$operation" == open_public_150 ]]; then
    echo "STANDARD150_PUBLIC_COHORT_OPEN generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID snapshot=$BARRIER_SNAPSHOT_ID"
  else
    echo "STANDARD150_CLAIM_BARRIER_OPEN generation=$BARRIER_GENERATION"
  fi
}

hold_public_150() {
  require_exact_main_owner_source
  require_barrier_inputs
  [[ "$BARRIER_EXPECTED_PRIOR_MODE" == open && "$ACCEPTANCE_COHORT_ID" =~ ^[A-Za-z0-9_-]{6,128}$ ]] \
    || { echo "Public Standard 150 hold requires an open barrier and exact cohort ID." >&2; return 1; }
  require_confirmation "HOLD-PUBLIC-150-COHORT:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}"
  call_barrier_operator hold_public_150 "/ops/barrier/public-150/hold"
  parse_barrier_response hold_public_150
  echo "STANDARD150_PUBLIC_COHORT_HELD generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID snapshot=$BARRIER_SNAPSHOT_ID"
}

require_pilot_launcher_build() {
  local exact_launcher
  exact_launcher="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["functions"]["startStandardScanJobV9"]["build_id"])' \
    "$REPO_ROOT/data/generated-staged-v9-routes.json")"
  if [[ ! "$ACCEPTANCE_LAUNCHER_BUILD_ID" =~ ^[0-9a-f]{64}$ || "$ACCEPTANCE_LAUNCHER_BUILD_ID" != "$exact_launcher" ]]; then
    echo "Published pilot launcher build ID does not match the exact source." >&2
    return 1
  fi
}

verify_legacy_fallback_worker() {
  local view="$1"
  local recorded="$view/baseline/data/beta-crawler-revision.json"
  [[ -s "$recorded" ]] || { echo "The retained V8 worker release record is missing." >&2; return 1; }
  # The separate control roster uses the canonical worker. The named V9
  # worker may be healthy while the canonical worker cannot save V8 reports.
  TMPDIR="$view" TARGET_REVISION="" FIXLIST_WORKER_PROBE_URL="" FIXLIST_VERIFY_STAGED_BASE44_RUNTIME=0 \
    verify_worker_runtime_revision "" "" "$recorded"
}

verify_approved_legacy_access() (
  set -euo pipefail
  local app_id="6a498732ec779dfaaeab0e53" baseline_sha view route_selection expected_owner expected_operator
  baseline_sha="$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["source_sha"])' "$LEGACY_ACCESS")"
  git -C "$REPO_ROOT" merge-base --is-ancestor "$baseline_sha" "$SOURCE_SHA" || {
    echo "Approved V8 source is outside the candidate's merged history." >&2
    return 1
  }
  expected_owner="${BASE44_EXPECTED_OWNER:-}"
  case "$expected_owner" in
    bright4862@gmail.com) expected_operator="6a498da58ef5cec1f5cd4486" ;;
    londonparisbrussels@gmail.com) expected_operator="6a498732ec779dfaaeab0e54" ;;
    *) echo "The configured Base44 app owner is required for the legacy access preflight." >&2; return 1 ;;
  esac
  [[ -z "${BASE44_API_KEY:-}" ]] || { echo "The legacy roster requires an authenticated owner session." >&2; return 1; }
  view="$(mktemp -d)"
  trap 'rm -rf "$view"' EXIT
  chmod 700 "$view"
  mkdir "$view/baseline"
  git -C "$REPO_ROOT" archive "$baseline_sha" | tar -x -C "$view/baseline" || return 1
  route_selection="$(node "$view/baseline/scripts/lib/base44-public-routes.mjs")"
  [[ "$route_selection" == v8\ * ]] || { echo "Approved baseline is not the V8 publisher source." >&2; return 1; }
  PUBLIC_URL=https://getfixlist.com/ BASE44_URL=https://getfixlist.base44.app/ EXPECTED_SOURCE_SHA="$SOURCE_SHA" \
    bash "$REPO_ROOT/scripts/verify-base44-site.sh" >&2 || return 1
  BASE44_APP_ID="$app_id" BASE44_FUNCTION_ORIGIN=https://base44.app \
    bash "$view/baseline/scripts/verify-base44-functions.sh" > "$view/runtime.out" || return 1
  [[ "$(grep -c '^FUNCTION_RUNTIME_VERIFIED ' "$view/runtime.out")" == 6 ]] || {
    echo "The six retained V8 function identities were not verified." >&2
    return 1
  }
  source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh" || return 1
  fixlist_install_base44_cli "$view/base44" >&2 || return 1
  fixlist_require_base44_owner "$expected_owner" "$view/whoami" "$app_id" >&2 || return 1

  python3 - "$LEGACY_ACCESS" "$expected_owner" "$expected_operator" > "$view/readback.js" <<'PY'
import json, sys
raw, email, operator_id = sys.argv[1:]
print("const ownerIds = " + json.dumps(json.loads(raw)["owner_user_ids"]) + ";")
print("const operatorEmail = " + json.dumps(email) + ";")
print("const operatorId = " + json.dumps(operator_id) + ";")
PY
  sed 's/^export //' "$view/baseline/base44/functions/startStandardScanJobV8/entitlement.js" >> "$view/readback.js"
  cat >> "$view/readback.js" <<'JS'

const actor = await base44.auth.me();
if (actor?.id !== operatorId || actor.role !== "admin" || normalizeEmail(actor.email) !== operatorEmail) {
  throw new Error("owner_identity_mismatch");
}
for (const id of ownerIds) {
  const user = await base44.entities.User.get(id);
  if (user?.id !== id || user.role !== "user" || !normalizeEmail(user.email)) throw new Error("ordinary_user_unverified");
  const byOwner = await base44.entities.Access.filter({owner_user_id:id}, "-created_date", 2);
  const byEmail = await base44.entities.Access.filter({user_email:normalizeEmail(user.email)}, "-created_date", 2);
  if (![byOwner, byEmail].every(rows => Array.isArray(rows) && rows.length === 1 && rows[0]?.id
        && evaluatePaidAccess({rows, user}).ok && (rows[0].page_cap ?? 150) === 150)
      || byOwner[0].id !== byEmail[0].id) throw new Error("active_standard_150_entitlement_unverified");
}
console.log("APPROVED_V8_OWNERS_VERIFIED=" + ownerIds.length);
JS
  if ! timeout --signal=TERM --kill-after=5s 180 "$FIXLIST_BASE44_CLI" --app-id "$app_id" exec --data-env prod \
    < "$view/readback.js" > "$view/access.out" 2> "$view/access.err"; then
    echo "The approved ordinary users' active Standard 150 grants could not be verified." >&2
    return 1
  fi
  PUBLIC_URL=https://getfixlist.com/ BASE44_URL=https://getfixlist.base44.app/ EXPECTED_SOURCE_SHA="$SOURCE_SHA" \
    bash "$REPO_ROOT/scripts/verify-base44-site.sh" >&2 || return 1
  verify_legacy_fallback_worker "$view" >&2 || return 1
  python3 - "$LEGACY_ACCESS" "$LEGACY_ACCESS_SHA256" "$SOURCE_SHA" "$view/access.out" <<'PY'
import json, sys, time
raw, digest, candidate, access_report = sys.argv[1:]
legacy = json.loads(raw)
count = len(legacy["owner_user_ids"])
with open(access_report, encoding="utf-8") as handle:
    markers = [line.strip() for line in handle if line.startswith("APPROVED_V8_OWNERS_VERIFIED=")]
if markers != [f"APPROVED_V8_OWNERS_VERIFIED={count}"]:
    raise SystemExit("The owner readback did not verify the complete approved roster.")
print(json.dumps({"version": "published_legacy_access_preflight_v1", "pilot_source_sha": candidate,
                  "legacy_source_sha": legacy["source_sha"], "configuration_sha256": digest,
                  "verified_owner_count": count, "verified_at": int(time.time())}))
PY
)

activate_acceptance_only() {
  require_exact_main_owner_source
  require_barrier_inputs
  local expected_confirmation="OPEN-STANDARD150-ACCEPTANCE:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}"
  if [[ -n "$ACCEPTANCE_LAUNCHER_BUILD_ID" ]]; then
    require_pilot_launcher_build
    expected_confirmation+=":$ACCEPTANCE_LAUNCHER_BUILD_ID"
  fi
  if [[ -n "$LEGACY_ACCESS" ]]; then
    [[ -n "$ACCEPTANCE_LAUNCHER_BUILD_ID" ]] || {
      echo "Approved legacy access requires a build-bound named pilot." >&2
      return 1
    }
    LEGACY_ACCESS_SHA256="$(PYTHONPATH="$REPO_ROOT/admission-coordinator" python3 - \
      "$LEGACY_ACCESS" "$ACCEPTANCE_COHORT_ID" "$ACCEPTANCE_OWNER_USER_IDS" "$SOURCE_SHA" "$ACCEPTANCE_EXPIRES_AT" <<'PY'
import json, sys, time

from control import legacy_access_definition

raw, cohort_id, owners, source_sha, expires_at = sys.argv[1:]
try:
    value = json.loads(raw)
    pilot = {"cohort_id": cohort_id, "owner_allowlist": [owner.strip() for owner in owners.split(",") if owner.strip()],
             "source_sha": source_sha, "expires_at": int(expires_at)}
    definition = legacy_access_definition(value, pilot, now=int(time.time()), operator_id="workflow")
except ValueError:
    raise SystemExit("Approved legacy access must be valid, disjoint and cover the entire named pilot window.")
print(definition["configuration_sha256"])
PY
)"
    expected_confirmation+=":LEGACY:$LEGACY_ACCESS_SHA256"
  fi
  require_confirmation "$expected_confirmation"
  [[ "$ACCEPTANCE_SOURCE_SHA" == "$SOURCE_SHA" ]] \
    || { echo "Acceptance cohort must bind the exact main source SHA." >&2; return 1; }
  require_closed_drained_barrier
  require_drain_plane_live
  BARRIER_EXPECTED_PRIOR_MODE="closed"
  if [[ -n "$LEGACY_ACCESS" ]]; then
    LEGACY_ACCESS_PREFLIGHT="$(verify_approved_legacy_access)"
  fi
  call_barrier_operator acceptance_only "$ADMISSION_BARRIER_ACCEPTANCE_PATH"
  parse_barrier_response acceptance_only
  [[ "$BARRIER_MODE" == "acceptance_only" ]] \
    || { echo "Coordinator did not enter acceptance-only mode." >&2; return 1; }
  echo "STANDARD150_ACCEPTANCE_ONLY generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID${LEGACY_ACCESS_SHA256:+ legacy_configuration_sha256=$LEGACY_ACCESS_SHA256}"
}

hold_published_150_pilot() {
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
    require_exact_main_owner_source
  else
    source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
    fixlist_require_merged_checkout "$REPO_ROOT" "$SOURCE_SHA"
  fi
  require_barrier_inputs
  [[ "$BARRIER_EXPECTED_PRIOR_MODE" == acceptance_only && "$ACCEPTANCE_COHORT_ID" =~ ^[A-Za-z0-9_-]{6,128}$ ]] \
    || { echo 'The Standard 150 pilot hold requires the exact acceptance generation and cohort.' >&2; return 1; }
  require_confirmation "HOLD-PUBLISHED-150-PILOT:$SOURCE_SHA:$BARRIER_EXPECTED_GENERATION:$ACCEPTANCE_COHORT_ID"
  call_barrier_operator hold_150_pilot /ops/barrier/pilot-150/hold
  parse_barrier_response hold_150_pilot
  echo "STANDARD150_PILOT_HELD generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID legacy_access=preserved"
}

operate_published_500_pilot() {
  local action="$1"
  require_exact_main_owner_source
  require_barrier_inputs
  [[ "$BARRIER_EXPECTED_PRIOR_MODE" == open && "$ACCEPTANCE_COHORT_ID" =~ ^[A-Za-z0-9_-]{6,128}$ ]] \
    || { echo 'The Standard 500 pilot requires an open public barrier and exact cohort ID.' >&2; return 1; }
  if [[ "$action" == start ]]; then
    require_pilot_launcher_build
    [[ "$ACCEPTANCE_SOURCE_SHA" == "$SOURCE_SHA" ]] || return 1
    require_confirmation "START-PUBLISHED-500-PILOT:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}:${ACCEPTANCE_LAUNCHER_BUILD_ID}"
    require_drain_plane_live
  else
    require_confirmation "HOLD-PUBLISHED-500-PILOT:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}:${ACCEPTANCE_COHORT_ID}"
  fi
  call_barrier_operator "${action}_500_pilot" "/ops/barrier/pilot-500/$action"
  parse_barrier_response "${action}_500_pilot"
  echo "STANDARD500_PILOT action=$action generation=$BARRIER_GENERATION cohort=$ACCEPTANCE_COHORT_ID public_mode=$BARRIER_MODE snapshot=$BARRIER_SNAPSHOT_ID"
}

operate_eligible_500() {
  local action="$1"
  if [[ "$action" == hold && "${GITHUB_ACTIONS:-}" != true ]]; then
    source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
    fixlist_require_merged_checkout "$REPO_ROOT" "$SOURCE_SHA"
  else
    require_exact_main_owner_source
  fi
  require_barrier_inputs
  [[ "$BARRIER_EXPECTED_PRIOR_MODE" == open && "$ACCEPTANCE_COHORT_ID" =~ ^[A-Za-z0-9_-]{6,128}$ && -z "$ACCEPTANCE_OWNER_USER_IDS" ]] \
    || { echo 'Eligible Standard 500 requires the exact open generation and rollout ID with no owner roster.' >&2; return 1; }
  if [[ "$action" == start ]]; then
    require_pilot_launcher_build
    [[ "$ACCEPTANCE_SOURCE_SHA" == "$SOURCE_SHA" ]] || return 1
    require_confirmation "START-ELIGIBLE-500:$SOURCE_SHA:$BARRIER_EXPECTED_GENERATION:$ACCEPTANCE_COHORT_ID:$ACCEPTANCE_LAUNCHER_BUILD_ID"
    python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA" --base44-v9 scanner-functions --worker
    EXPECTED_SOURCE_SHA="$SOURCE_SHA" bash "$REPO_ROOT/scripts/verify-base44-site.sh"
    require_drain_plane_live
  else
    require_confirmation "HOLD-ELIGIBLE-500:$SOURCE_SHA:$BARRIER_EXPECTED_GENERATION:$ACCEPTANCE_COHORT_ID"
  fi
  call_barrier_operator "${action}_eligible_500" "/ops/barrier/eligible-500/$action"
  parse_barrier_response "${action}_eligible_500"
  echo "STANDARD500_ELIGIBLE action=$action generation=$BARRIER_GENERATION rollout=$ACCEPTANCE_COHORT_ID public_mode=$BARRIER_MODE snapshot=$BARRIER_SNAPSHOT_ID"
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

  verify-worker-runtime-revision)
    verify_worker_runtime_revision "$TARGET_REVISION" "$SOURCE_SHA"
    ;;

  tag-worker-candidate)
    tag_worker_candidate "$TARGET_REVISION"
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

  hold-public-150)
    hold_public_150
    ;;

  acceptance-only)
    activate_acceptance_only
    ;;

  hold-published-150-pilot)
    hold_published_150_pilot
    ;;

  start-published-500-pilot)
    operate_published_500_pilot start
    ;;

  hold-published-500-pilot)
    operate_published_500_pilot hold
    ;;

  start-eligible-500)
    operate_eligible_500 start
    ;;

  hold-eligible-500)
    operate_eligible_500 hold
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
