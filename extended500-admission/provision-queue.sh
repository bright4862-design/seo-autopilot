#!/usr/bin/env bash
# Preparation ONLY. This script cannot enable Extended 500 and never enqueues.
set -euo pipefail
: "${GCP_PROJECT:?}"
: "${GCP_LOCATION:?}"
: "${EXTENDED500_QUEUE_NAME:?}"
[[ "${EXTENDED500_QUEUE_NAME}" =~ ^extended500-[a-z0-9-]+$ ]] || { echo "Expected dedicated extended500- queue" >&2; exit 2; }
[[ "${EXTENDED500_QUEUE_NAME}" != "${SCAN_TASKS_QUEUE_NAME:-}" ]] || exit 2
[[ "${EXTENDED500_QUEUE_NAME}" != "${SCAN_DRAIN_QUEUE_NAME:-}" ]] || exit 2
QUEUE="projects/${GCP_PROJECT}/locations/${GCP_LOCATION}/queues/${EXTENDED500_QUEUE_NAME}"
echo "Dedicated queue: $QUEUE (creation followed by immediate pause)"
if [[ "${EXTENDED500_QUEUE_PROVISION_APPROVED:-}" != "YES" ]]; then
  echo "DRY RUN — set EXTENDED500_QUEUE_PROVISION_APPROVED=YES for isolated queue creation"
  exit 0
fi
if ! gcloud tasks queues describe "${EXTENDED500_QUEUE_NAME}" --project "${GCP_PROJECT}" --location "${GCP_LOCATION}" >/dev/null 2>&1; then
  gcloud tasks queues create "${EXTENDED500_QUEUE_NAME}" \
    --project "${GCP_PROJECT}" --location "${GCP_LOCATION}" \
    --max-concurrent-dispatches=1 --max-dispatches-per-second=1 \
    --max-attempts=5 --max-retry-duration=3600s
fi
gcloud tasks queues pause "${EXTENDED500_QUEUE_NAME}" --project "${GCP_PROJECT}" --location "${GCP_LOCATION}"
gcloud tasks queues describe "${EXTENDED500_QUEUE_NAME}" --project "${GCP_PROJECT}" --location "${GCP_LOCATION}" --format='yaml(name,state,rateLimits,retryConfig)'
echo "Queue is prepared and PAUSED. Neither coordinator nor worker is activated."
