#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
CONFIRM="${CONFIRM:-}"

EXPECTED_CONFIRM="SET-DRAIN-QUEUE-SAFE-BETA"
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing drain-queue change: CONFIRM must equal $EXPECTED_CONFIRM" >&2
  exit 2
fi

# The drain queue is control-plane work, not crawling. It must have enough
# retries to survive a scan waiting in the main queue and then wait until the
# worker-start anchored 600s terminal deadline becomes due.
MAX_CONCURRENT=5
MAX_RATE=5
MAX_ATTEMPTS=100
MAX_RETRY_DURATION="14400s"
MIN_BACKOFF="30s"
MAX_BACKOFF="180s"
MAX_DOUBLINGS=3

QUEUE_JSON="$(mktemp)"
trap 'rm -f "$QUEUE_JSON"' EXIT

if ! gcloud tasks queues describe "$QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud tasks queues create "$QUEUE" \
    --project="$PROJECT" \
    --location="$REGION" \
    --max-concurrent-dispatches="$MAX_CONCURRENT" \
    --max-dispatches-per-second="$MAX_RATE" \
    --max-attempts="$MAX_ATTEMPTS" \
    --max-retry-duration="$MAX_RETRY_DURATION" \
    --min-backoff="$MIN_BACKOFF" \
    --max-backoff="$MAX_BACKOFF" \
    --max-doublings="$MAX_DOUBLINGS" \
    --quiet
else
  gcloud tasks queues update "$QUEUE" \
    --project="$PROJECT" \
    --location="$REGION" \
    --max-concurrent-dispatches="$MAX_CONCURRENT" \
    --max-dispatches-per-second="$MAX_RATE" \
    --max-attempts="$MAX_ATTEMPTS" \
    --max-retry-duration="$MAX_RETRY_DURATION" \
    --min-backoff="$MIN_BACKOFF" \
    --max-backoff="$MAX_BACKOFF" \
    --max-doublings="$MAX_DOUBLINGS" \
    --quiet
fi

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format=json > "$QUEUE_JSON"
python3 - "$QUEUE_JSON" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
rate=q.get("rateLimits") or {}
retry=q.get("retryConfig") or {}
assert int(rate.get("maxConcurrentDispatches") or 0) == 5, rate
assert float(rate.get("maxDispatchesPerSecond") or 0) == 5.0, rate
assert int(retry.get("maxAttempts") or 0) == 100, retry
assert str(retry.get("maxRetryDuration") or "") == "14400s", retry
assert str(retry.get("minBackoff") or "") == "30s", retry
assert str(retry.get("maxBackoff") or "") == "180s", retry
assert int(retry.get("maxDoublings") or 0) == 3, retry
print("DRAIN_QUEUE_POLICY_OK concurrency=5 rate=5/s attempts=100 retry_duration=14400s min=30s max=180s")
PY
