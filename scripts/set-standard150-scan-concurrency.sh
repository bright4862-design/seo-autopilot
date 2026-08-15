#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
QUEUE="${CLOUD_TASKS_QUEUE:-fixlist-standard150}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
TARGET="${TARGET_SCAN_CONCURRENCY:-}"
CONFIRM="${CONFIRM:-}"

case "$TARGET" in
  1|3|5|10) ;;
  *)
    echo "Refusing scan concurrency change: TARGET_SCAN_CONCURRENCY must be exactly 1, 3, 5, or 10." >&2
    exit 2
    ;;
esac

EXPECTED_CONFIRM="SET-SCAN-CONCURRENCY-${TARGET}"
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing scan concurrency change: CONFIRM must equal $EXPECTED_CONFIRM" >&2
  exit 2
fi

# This operation changes only Cloud Tasks dispatch pressure. The worker itself
# must remain one request per instance so parallel scans scale horizontally.
WORKER_JSON="$(mktemp)"
QUEUE_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON" "$QUEUE_JSON"' EXIT

gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"

python3 - "$WORKER_JSON" <<'PY'
import json,sys
service=json.load(open(sys.argv[1]))
template=(service.get("spec") or {}).get("template") or {}
spec=template.get("spec") or {}
containers=spec.get("containers") or []
if not containers:
    raise SystemExit("Refusing: worker has no container configuration")
concurrency=spec.get("containerConcurrency")
if int(concurrency or 0) != 1:
    raise SystemExit(f"Refusing: worker concurrency must remain 1; observed {concurrency!r}")
max_instances=((template.get("metadata") or {}).get("annotations") or {}).get("autoscaling.knative.dev/maxScale")
if max_instances is not None and int(max_instances) < 10:
    raise SystemExit(f"Refusing: worker max instances {max_instances} is below the 10-scan ramp target")
print("Worker invariant verified: concurrency=1 and horizontal scale headroom is sufficient.")
PY

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format=json > "$QUEUE_JSON"
python3 - "$QUEUE_JSON" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
if str(q.get("state") or "") not in {"RUNNING","PAUSED"}:
    raise SystemExit(f"Refusing: unexpected queue state {q.get('state')!r}")
print("Queue exists and is in a known state.")
PY

# Keep dispatch rate equal to concurrency during beta ramp to avoid a large
# token-bucket burst after idle periods.
gcloud tasks queues update "$QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --max-concurrent-dispatches="$TARGET" \
  --max-dispatches-per-second="$TARGET" \
  --quiet

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format=json > "$QUEUE_JSON"
python3 - "$QUEUE_JSON" "$TARGET" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
expected=int(sys.argv[2])
rate=q.get("rateLimits") or {}
actual_concurrency=int(rate.get("maxConcurrentDispatches") or 0)
actual_rate=float(rate.get("maxDispatchesPerSecond") or 0)
assert actual_concurrency == expected, (actual_concurrency, expected)
assert actual_rate == float(expected), (actual_rate, expected)
print(f"SCAN_QUEUE_RAMP_OK concurrency={actual_concurrency} rate={actual_rate:g}/s state={q.get('state')}")
PY
