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
}

verify_iam() {
  echo "=== Cloud Run IAM ==="
  gcloud run services get-iam-policy "$CLOUD_RUN_SERVICE" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT" \
    --format=yaml

  echo
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
  local revision image digest
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
    echo
    echo "WARNING: the revision runs a mutable tag, not an immutable digest."
    echo "An immutable release must pin image@sha256:..."
  fi

  echo
  echo "=== Build provenance for this image ==="
  gcloud builds list --project="$GCP_PROJECT" --limit=20 \
    --format='table(id,status,createTime,substitutions._RELEASE_SHA,results.images[0].name)' \
    --filter="results.images[0].name~$(printf '%s' "${image%%@*}" | sed 's/[].[^$\\*/]/\\&/g')" || true

  echo
  echo "ROUTE VERIFICATION IS NOT COMPLETE UNTIL A HUMAN CONFIRMS:"
  echo "  the _RELEASE_SHA above is a commit whose scanner-api/app/main.py"
  echo "  declares @app.post(\"/scan-job\") and @app.post(\"/scan-job-drain\")."
  echo "  Current main contains those routes, but an older deployed revision"
  echo "  may still have been built before they landed."
  echo
  echo "=== Revision request timeout (must be 480 to match dispatchDeadline) ==="
  gcloud run revisions describe "$revision" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --format='value(spec.timeoutSeconds)'
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
