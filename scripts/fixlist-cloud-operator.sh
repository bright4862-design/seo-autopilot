#!/usr/bin/env bash
# Allowlisted Google Cloud operations for the durable Standard 150 release.
#
# Invoked only by .github/workflows/fixlist-cloud-operator.yml, which
# authenticates keylessly through Workload Identity Federation. No operation
# here creates, reads, or prints a credential.
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

gcloud config set project "$GCP_PROJECT" >/dev/null

echo "FixList Cloud Operator"
echo "project=$GCP_PROJECT"
echo "region=$GCP_REGION"
echo "service=$CLOUD_RUN_SERVICE"
echo "queue=$CLOUD_TASKS_QUEUE"
echo "operation=$OPERATION"
echo

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
    require_target_revision
    promote_revision
    show_status
    ;;

  rollback-worker)
    require_target_revision
    echo "Rolling traffic back to $TARGET_REVISION ..."
    promote_revision
    show_status
    ;;

  pause-queue)
    require_confirmation PAUSE
    gcloud tasks queues pause "$CLOUD_TASKS_QUEUE" \
      --location="$GCP_REGION" \
      --project="$GCP_PROJECT"
    show_status
    ;;

  resume-queue)
    require_confirmation RESUME
    gcloud tasks queues resume "$CLOUD_TASKS_QUEUE" \
      --location="$GCP_REGION" \
      --project="$GCP_PROJECT"
    show_status
    ;;

  activate-beta)
    require_target_revision

    echo "1/3 Promoting $TARGET_REVISION ..."
    promote_revision

    echo
    echo "2/3 Verifying the promoted revision serves before any task can flow..."
    assert_serving

    echo
    echo "3/3 Resuming the queue only after promotion verified..."
    gcloud tasks queues resume "$CLOUD_TASKS_QUEUE" \
      --location="$GCP_REGION" \
      --project="$GCP_PROJECT"
    show_status
    ;;

  *)
    echo "Unsupported operation: $OPERATION" >&2
    exit 64
    ;;
esac
