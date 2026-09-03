#!/usr/bin/env bash
# Publish the customer site without leaving the durable Base44 backend stripped.
#
# Observed Base44 CLI behavior (2026-08-17): `site deploy` can reconcile the
# remote function inventory back to the older site snapshot. Therefore the
# only supported beta site-publish order is:
#   exact clean main -> build -> site deploy -> canonical release functions ->
#   owner-safe history function -> final inventory verification.
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
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"
fixlist_set_base44_release_source_sha "$APP_ID" "$SOURCE_SHA"

cd "$REPO_ROOT"
VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" site deploy --no-build --yes

# Site publication comes first. Re-establish the canonical release functions
# afterwards using the SAME authenticated CLI session so a second interactive
# login can never strand production with the older site-snapshot inventory.
FUNCTIONS=(
  startStandardScanJobV2
  durableScanWorkerControlV2
  persistDurableScanAuthorityV2
  persistLimitedScanResultV2
  getCustomerScanResultV2
  deleteCustomerScanDataV2
  createAccessCheckout
  stripeWebhook
  ownerScanDebugControl
)
DEPLOY_STATUS=0
DEPLOY_REPORT="$("$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${FUNCTIONS[@]}" 2>&1)" || DEPLOY_STATUS=$?
printf '%s\n' "$DEPLOY_REPORT"
if (( DEPLOY_STATUS != 0 )); then
  exit "$DEPLOY_STATUS"
fi

INVENTORY="$($FIXLIST_BASE44_CLI --app-id "$APP_ID" functions list 2>&1)"
printf '%s\n' "$INVENTORY"
for required in \
  startStandardScanJobV2 \
  durableScanWorkerControlV2 \
  persistDurableScanAuthorityV2 \
  persistLimitedScanResultV2 \
  getCustomerScanResultV2 \
  deleteCustomerScanDataV2 \
  createAccessCheckout \
  stripeWebhook \
  ownerScanDebugControl
do
  grep -Eq "(^|[[:space:]])${required}([[:space:]]|$)" <<<"$INVENTORY" || {
    echo "Refusing: Base44 post-site inventory is missing ${required}." >&2
    exit 2
  }
done

EXPECTED_SOURCE_SHA="$SOURCE_SHA" bash "$REPO_ROOT/scripts/verify-base44-site.sh"
bash "$REPO_ROOT/scripts/verify-base44-functions.sh"

printf 'BASE44_SITE_AND_BACKEND_DEPLOYED\nsource_sha=%s\n' "$SOURCE_SHA"
