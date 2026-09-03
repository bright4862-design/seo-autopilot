#!/usr/bin/env bash
# Publish the customer site without leaving the durable Base44 backend stripped.
#
# Observed Base44 CLI behavior (2026-08-17): `site deploy` can reconcile the
# remote function inventory back to the older site snapshot. Therefore the
# release functions must be (re-)deployed after the site, never only before.
#
# They are also deployed BEFORE it. On 2026-09-03 a full delete-and-redeploy of
# ownerScanDebugControl left the runtime still serving the older compiled
# handler through eight probes, so "the CLI reported it deployed" is not
# evidence that a route runs this source. The frontend published here calls the
# V2 routes, so publishing the site first would put getfixlist.com in front of
# handlers whose activation was never proven. The pre-site pass proves them
# while the live site is still untouched; the post-site pass repairs whatever
# `site deploy` reconciled away.
#
#   exact clean main -> release functions -> prove they serve this source
#     -> build -> site deploy -> all functions -> inventory -> site + functions
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

# The scanner and customer-data routes the published frontend and the Cloud Run
# worker actually call. Every one of these is build-ID verified below.
VERIFIED_FUNCTIONS=(
  startStandardScanJobV2
  durableScanWorkerControlV2
  persistDurableScanAuthorityV2
  persistLimitedScanResultV2
  getCustomerScanResultV2
  deleteCustomerScanDataV2
)
# Deployed, but not build-ID verified. createAccessCheckout and stripeWebhook
# keep their names because Stripe addresses stripeWebhook by URL from its own
# dashboard, and ownerScanDebugControl is owner-only. All three are known stale
# (2026-09-03 recovery preflight); nothing here claims otherwise.
UNVERIFIED_FUNCTIONS=(
  createAccessCheckout
  stripeWebhook
  ownerScanDebugControl
)

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"
fixlist_set_base44_release_source_sha "$APP_ID" "$SOURCE_SHA"

cd "$REPO_ROOT"

deploy_functions() {
  local status=0 report
  report="$("$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "$@" 2>&1)" || status=$?
  printf '%s\n' "$report"
  return "$status"
}

deploy_functions "${VERIFIED_FUNCTIONS[@]}"
bash "$REPO_ROOT/scripts/verify-base44-functions.sh"
printf 'BASE44_RELEASE_ROUTES_ACTIVE_PRE_SITE\n'

VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" site deploy --no-build --yes

# Re-establish every function afterwards using the SAME authenticated CLI
# session so a second interactive login can never strand production with the
# older site-snapshot inventory.
FUNCTIONS=("${VERIFIED_FUNCTIONS[@]}" "${UNVERIFIED_FUNCTIONS[@]}")
deploy_functions "${FUNCTIONS[@]}"

INVENTORY="$($FIXLIST_BASE44_CLI --app-id "$APP_ID" functions list 2>&1)"
printf '%s\n' "$INVENTORY"
for required in "${FUNCTIONS[@]}"; do
  grep -Eq "(^|[[:space:]])${required}([[:space:]]|$)" <<<"$INVENTORY" || {
    echo "Refusing: Base44 post-site inventory is missing ${required}." >&2
    exit 2
  }
done

EXPECTED_SOURCE_SHA="$SOURCE_SHA" bash "$REPO_ROOT/scripts/verify-base44-site.sh"
bash "$REPO_ROOT/scripts/verify-base44-functions.sh"

printf 'BASE44_SITE_AND_BACKEND_DEPLOYED\nsource_sha=%s\nbuild_verified=%s\nbuild_unverified=%s\n' \
  "$SOURCE_SHA" "${VERIFIED_FUNCTIONS[*]}" "${UNVERIFIED_FUNCTIONS[*]}"
