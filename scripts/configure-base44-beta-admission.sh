#!/usr/bin/env bash
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
COORDINATOR="${ADMISSION_COORDINATOR_SERVICE:-fixlist-scan-admission-coordinator}"
DRAIN_QUEUE="${CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

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
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami"

# Additive only: set these exact four admission/control keys and the exact-main
# release provenance used by durable reconciliation. Membership is
# determined by the owner-bound Access entitlement, not a second static cohort
# list. This intentionally does not touch the signing key, Stripe cohort/checkout
# configuration, entities, site, or any unrelated function.
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
  "BETA_SCAN_ADMISSION_ENABLED=false" \
  "BETA_CHECKOUT_ENABLED=false" \
  "SCAN_ADMISSION_COORDINATOR_URL=$COORD_URL" \
  "SCAN_DRAIN_QUEUE_PATH=$DRAIN_QUEUE_PATH" \
  "FIXLIST_RELEASE_SOURCE_SHA=$SOURCE_SHA"

printf 'BASE44_BETA_CONFIGURED_DISABLED_FIRST\nsource_sha=%s\ncoordinator=%s\ndrain_queue=%s\n' \
  "$SOURCE_SHA" "$COORD_URL" "$DRAIN_QUEUE_PATH"
