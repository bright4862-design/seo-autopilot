#!/usr/bin/env bash
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

FUNCTIONS=(
  startStandardScanJob
  durableScanWorkerControl
  persistDurableScanAuthority
  persistLimitedScanResult
  getCustomerScanResult
  createAccessCheckout
  stripeWebhook
  deleteCustomerScanData
  ownerScanDebugControl
)

node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"
fixlist_set_base44_release_source_sha "$APP_ID" "$SOURCE_SHA"

cd "$REPO_ROOT"
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${FUNCTIONS[@]}"
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list

printf 'BASE44_RELEASE_FUNCTIONS_DEPLOYED\nsource_sha=%s\nfunction_count=%s\n' "$SOURCE_SHA" "${#FUNCTIONS[@]}"
