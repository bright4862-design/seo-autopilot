#!/usr/bin/env bash
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
COORDINATOR="${ADMISSION_COORDINATOR_SERVICE:-fixlist-scan-admission-coordinator}"
DRAIN_QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
COHORT="${BETA_COHORT_ALLOWED_USER_IDS:-}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

python3 - "$COHORT" <<'PY'
import re,sys
raw=sys.argv[1]
ids=[x.strip() for x in raw.split(',') if x.strip()]
if not 1 <= len(ids) <= 25: raise SystemExit('BETA_COHORT_ALLOWED_USER_IDS must contain 1-25 ids')
if len(set(ids)) != len(ids): raise SystemExit('BETA_COHORT_ALLOWED_USER_IDS contains duplicates')
for value in ids:
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,160}', value): raise SystemExit('invalid cohort user id')
print(f'cohort_size={len(ids)}')
PY

COORD_URL="$(gcloud run services describe "$COORDINATOR" --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
[[ "$COORD_URL" == https://* ]] || { echo "Coordinator URL unavailable." >&2; exit 2; }
HEALTH="$(mktemp)"; TMP="$(mktemp -d)"; trap 'rm -f "$HEALTH"; rm -rf "$TMP"' EXIT
curl --fail --silent --show-error --max-time 20 "$COORD_URL/health" > "$HEALTH"
python3 - "$HEALTH" "$SOURCE_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); expected=sys.argv[2]
assert v.get('ok') is True, v
assert v.get('service')=='fixlist-admission-coordinator', v
assert v.get('source_sha')==expected, (v.get('source_sha'), expected)
PY

DRAIN_QUEUE_PATH="projects/${PROJECT}/locations/${REGION}/queues/${DRAIN_QUEUE}"
gcloud tasks queues describe "$DRAIN_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null

fixlist_install_base44_cli "$TMP"
"$FIXLIST_BASE44_CLI" login

# Additive only: set these exact five keys. This intentionally does not touch
# the signing key, Stripe secrets, entities, site, or any unrelated function.
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
  "BETA_SCAN_ADMISSION_ENABLED=false" \
  "BETA_CHECKOUT_ENABLED=false" \
  "SCAN_ADMISSION_COORDINATOR_URL=$COORD_URL" \
  "SCAN_DRAIN_QUEUE_PATH=$DRAIN_QUEUE_PATH" \
  "BETA_COHORT_ALLOWED_USER_IDS=$COHORT"

printf 'BASE44_BETA_CONFIGURED_DISABLED_FIRST\nsource_sha=%s\ncohort=%s\ncoordinator=%s\ndrain_queue=%s\n' \
  "$SOURCE_SHA" "$COHORT" "$COORD_URL" "$DRAIN_QUEUE_PATH"
