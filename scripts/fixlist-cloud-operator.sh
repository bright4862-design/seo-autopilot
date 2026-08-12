#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"
: "${CLOUD_TASKS_QUEUE:?CLOUD_TASKS_QUEUE is required}"
: "${TASKS_INVOKER_SERVICE_ACCOUNT:?TASKS_INVOKER_SERVICE_ACCOUNT is required}"
: "${OPERATION:?OPERATION is required}"

CONFIRM="${CONFIRM:-}"

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

require_confirmation() {
  local expected="$1"
  if [[ "$CONFIRM" != "$expected" ]]; then
    echo "Refusing mutation: confirmation must be exactly '$expected'." >&2
    exit 2
  fi
}

case "$OPERATION" in
  status)
    show_status
    ;;

  verify-iam)
    verify_iam
    ;;

  promote-worker)
    require_confirmation PROMOTE
    gcloud run services update-traffic "$CLOUD_RUN_SERVICE" \
      --region="$GCP_REGION" \
      --project="$GCP_PROJECT" \
      --to-latest
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
    require_confirmation ACTIVATE
    echo "Promoting latest Ready Cloud Run revision first..."
    gcloud run services update-traffic "$CLOUD_RUN_SERVICE" \
      --region="$GCP_REGION" \
      --project="$GCP_PROJECT" \
      --to-latest

    echo
    echo "Resuming queue only after traffic promotion succeeds..."
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
