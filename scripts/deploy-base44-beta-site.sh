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
# evidence that a route runs this source. The frontend published here calls
# the source-selected routes. The pre-site pass proves them
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
cd "$REPO_ROOT"
# A site publish reconciles live Base44 scanner functions: it must not move
# customer authority onto a release that is still explicitly a candidate.
python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"

# The scanner and customer-data routes the published frontend and the Cloud Run
# worker actually call. A V9 publish also keeps historical V8 routes serving
# clients with the previous bundle and scans already admitted on V8.
ROUTE_SELECTION="$(node "$REPO_ROOT/scripts/lib/base44-public-routes.mjs")"
read -r -a ROUTE_FIELDS <<<"$ROUTE_SELECTION"
VERIFIED_FUNCTIONS=("${ROUTE_FIELDS[@]:1}")
CHECKOUT_FUNCTIONS=("${VERIFIED_FUNCTIONS[@]}")
RELEASE_CONTRACT_ROOT="$REPO_ROOT" node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify
if [[ "${ROUTE_FIELDS[0]}" == "v9" ]]; then
  [[ "$APP_ID" == "6a498732ec779dfaaeab0e53" && "${BASE44_FUNCTION_ORIGIN:-https://base44.app}" == "https://base44.app" ]] || {
    echo 'Refusing active V9 publication: the FixList app and Base44 origin must match.' >&2
    exit 2
  }
  node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify --staged
  # The first six routes are materialized from V9 source in a scratch project.
  CHECKOUT_FUNCTIONS=("${VERIFIED_FUNCTIONS[@]:6}")
fi
# Deployed, but not build-ID verified. createAccessCheckout and stripeWebhook
# keep their names because Stripe addresses stripeWebhook by URL from its own
# dashboard, and ownerScanDebugControl is owner-only. Keep workflow-backed
# publishers such as generateDailyBlog out of this legacy functions deployment:
# Base44 rejects legacy automation deployment when Workflows are enabled.
UNVERIFIED_FUNCTIONS=(
  createAccessCheckout
  stripeWebhook
  ownerScanDebugControl
)

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"
fixlist_set_base44_release_source_sha "$APP_ID" "$SOURCE_SHA"

deploy_functions() {
  local status=0 report
  report="$("$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "$@" 2>&1)" || status=$?
  printf '%s\n' "$report"
  return "$status"
}

deploy_active_v9() {
  if [[ "${ROUTE_FIELDS[0]}" == "v9" ]]; then
    SOURCE_SHA="$SOURCE_SHA" CONFIRM="PUBLISH-BASE44-ACTIVE-V9:$SOURCE_SHA" BASE44_APP_ID="$APP_ID" \
      BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" READINESS_OUTPUT="$TMP/v9-$1.json" \
      bash "$REPO_ROOT/scripts/deploy-base44-staged-functions.sh" publish-active
  fi
}

deploy_functions "${CHECKOUT_FUNCTIONS[@]}"
deploy_active_v9 pre-site
BASE44_APP_ID="$APP_ID" bash "$REPO_ROOT/scripts/verify-base44-functions.sh"
printf 'BASE44_RELEASE_ROUTES_ACTIVE_PRE_SITE\n'

# A fresh browser has no cached Base44 app ID; bind it to this deployment.
VITE_SCAN_FUNCTION_GENERATION= VITE_BASE44_APP_ID="$APP_ID" VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" site deploy --no-build --yes

# Re-establish every function afterwards using the SAME authenticated CLI
# session so a second interactive login can never strand production with the
# older site-snapshot inventory.
FUNCTIONS=("${VERIFIED_FUNCTIONS[@]}" "${UNVERIFIED_FUNCTIONS[@]}")
deploy_functions "${CHECKOUT_FUNCTIONS[@]}" "${UNVERIFIED_FUNCTIONS[@]}"
deploy_active_v9 post-site

INVENTORY="$($FIXLIST_BASE44_CLI --app-id "$APP_ID" functions list 2>&1)"
printf '%s\n' "$INVENTORY"
for required in "${FUNCTIONS[@]}"; do
  grep -Eq "(^|[[:space:]])${required}([[:space:]]|$)" <<<"$INVENTORY" || {
    echo "Refusing: Base44 post-site inventory is missing ${required}." >&2
    exit 2
  }
done

EXPECTED_SOURCE_SHA="$SOURCE_SHA" bash "$REPO_ROOT/scripts/verify-base44-site.sh"
BASE44_APP_ID="$APP_ID" bash "$REPO_ROOT/scripts/verify-base44-functions.sh"

printf 'BASE44_SITE_AND_BACKEND_DEPLOYED\nsource_sha=%s\nbuild_verified=%s\nbuild_unverified=%s\n' \
  "$SOURCE_SHA" "${VERIFIED_FUNCTIONS[*]}" "${UNVERIFIED_FUNCTIONS[*]}"
