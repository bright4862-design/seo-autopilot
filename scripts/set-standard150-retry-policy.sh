#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
QUEUE="${CLOUD_TASKS_QUEUE:-fixlist-standard150}"
CONFIRM="${CONFIRM:-}"

EXPECTED_CONFIRM="SET-SCAN-RETRY-SAFE-BETA"
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing retry-policy change: CONFIRM must equal $EXPECTED_CONFIRM" >&2
  exit 2
fi

# Fixed beta policy. This script intentionally accepts no arbitrary retry
# values, so it cannot be used as a general queue mutator.
MAX_ATTEMPTS=3
MIN_BACKOFF="10s"
MAX_BACKOFF="300s"
MAX_DOUBLINGS=3

QUEUE_JSON="$(mktemp)"
trap 'rm -f "$QUEUE_JSON"' EXIT

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format=json > "$QUEUE_JSON"
python3 - "$QUEUE_JSON" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
state=str(q.get("state") or "")
if state not in {"RUNNING","PAUSED"}:
    raise SystemExit(f"Refusing: unexpected queue state {state!r}")
print(f"Queue state verified: {state}")
PY

gcloud tasks queues update "$QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --max-attempts="$MAX_ATTEMPTS" \
  --min-backoff="$MIN_BACKOFF" \
  --max-backoff="$MAX_BACKOFF" \
  --max-doublings="$MAX_DOUBLINGS" \
  --quiet

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format=json > "$QUEUE_JSON"
python3 - "$QUEUE_JSON" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
retry=q.get("retryConfig") or {}
assert int(retry.get("maxAttempts") or 0) == 3, retry
assert str(retry.get("minBackoff") or "") == "10s", retry
assert str(retry.get("maxBackoff") or "") == "300s", retry
assert int(retry.get("maxDoublings") or 0) == 3, retry
print("SCAN_RETRY_POLICY_OK attempts=3 min=10s max=300s doublings=3")
PY
