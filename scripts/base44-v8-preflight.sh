#!/usr/bin/env bash
# Read-only Base44 V8 preflight for incident 378.
#
# Proves the six scanner function packages, authority-schema parity (including
# ScanRun.comparison_evidence), and signing-key reference continuity. It does
# not publish functions, change schemas, read secret values, or touch Cloud
# Run traffic, queues, or the admission barrier.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
# shellcheck source=scripts/lib/base44-pinned-cli.sh
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
EXPECTED_CONFIRM="READONLY-BASE44-V8-PREFLIGHT:${SOURCE_SHA}"
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing Base44 V8 preflight: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
  exit 2
fi

cd "$REPO_ROOT"
echo "BASE44_V8_PREFLIGHT source_sha=$SOURCE_SHA"
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify
node "$REPO_ROOT/scripts/base44_authority_schema.mjs" hmac-contract

failed=0
note_failure() {
  failed=1
}

if ! bash "$REPO_ROOT/scripts/verify-base44-functions.sh"; then
  note_failure
fi

TMP="$(mktemp -d)"
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list > "$TMP/functions.txt" 2>&1; then
  echo "Base44 function inventory could not be read." >&2
  note_failure
else
  node "$REPO_ROOT/scripts/base44_authority_schema.mjs" function-inventory "$TMP/functions.txt" || note_failure
fi

if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets list > "$TMP/secrets.txt" 2>&1; then
  echo "Base44 secret name list could not be read." >&2
  note_failure
else
  node "$REPO_ROOT/scripts/base44_authority_schema.mjs" secret-present "$TMP/secrets.txt" || note_failure
fi

if ! node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" fetch "$TMP/schemas.json"; then
  note_failure
else
  node "$REPO_ROOT/scripts/base44_authority_schema.mjs" classify "$TMP/schemas.json" || note_failure
fi

describe_service() {
  local label="$1" service="$2"
  if ! gcloud run services describe "$service" \
    --project="${GCP_PROJECT:?}" \
    --region="${GCP_REGION:?}" \
    --format=json > "$TMP/${label}.json"; then
    echo "SIGNING_REF service=$label state=unreadable" >&2
    note_failure
    return 1
  fi
}

if describe_service worker "${CLOUD_RUN_SERVICE:?}" \
  && describe_service gateway "${GATEWAY_SERVICE:?}" \
  && describe_service coordinator "${ADMISSION_COORDINATOR_SERVICE:?}"; then
  node "$REPO_ROOT/scripts/base44_authority_schema.mjs" signing-refs \
    "$TMP/worker.json" "$TMP/gateway.json" "$TMP/coordinator.json" || note_failure
fi

if [[ "$failed" -ne 0 ]]; then
  echo "BASE44_V8_PREFLIGHT_FAILED source_sha=$SOURCE_SHA"
  exit 1
fi
echo "BASE44_V8_PREFLIGHT_PASSED source_sha=$SOURCE_SHA"
