#!/usr/bin/env bash
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
DEPLOY_SCOPE="${DEPLOY_SCOPE:-release-functions}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$DEPLOY_SCOPE" in
  scanner-functions|release-functions) ;;
  *)
    printf 'Refusing Base44 deployment: unknown deployment scope %s.\n' "$DEPLOY_SCOPE" >&2
    exit 2
    ;;
esac

source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
cd "$REPO_ROOT"
# Never publish new production scanner authority for an unaccepted candidate.
# This source gate complements, but does not replace, runtime and signed-canary checks.
python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"

ROUTE_SELECTION="$(node "$REPO_ROOT/scripts/lib/base44-public-routes.mjs")"
read -r -a ROUTE_FIELDS <<<"$ROUTE_SELECTION"
FUNCTIONS=("${ROUTE_FIELDS[@]:1}")
RELEASE_CONTRACT_ROOT="$REPO_ROOT" node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify
CHECKOUT_FUNCTIONS=("${FUNCTIONS[@]}")
if [[ "${ROUTE_FIELDS[0]}" == "v9" ]]; then
  [[ "$APP_ID" == "6a498732ec779dfaaeab0e53" && "${BASE44_FUNCTION_ORIGIN:-https://base44.app}" == "https://base44.app" ]] || {
    echo 'Refusing active V9 publication: the FixList app and Base44 origin must match.' >&2
    exit 2
  }
  node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify --staged
  CHECKOUT_FUNCTIONS=("${FUNCTIONS[@]:6}")
fi
if [[ "$DEPLOY_SCOPE" == "release-functions" ]]; then
  ADDITIONAL_FUNCTIONS=(createAccessCheckout stripeWebhook ownerScanDebugControl)
  FUNCTIONS+=("${ADDITIONAL_FUNCTIONS[@]}")
  CHECKOUT_FUNCTIONS+=("${ADDITIONAL_FUNCTIONS[@]}")
fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"
fixlist_set_base44_release_source_sha "$APP_ID" "$SOURCE_SHA"

"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${CHECKOUT_FUNCTIONS[@]}"
if [[ "${ROUTE_FIELDS[0]}" == "v9" ]]; then
  SOURCE_SHA="$SOURCE_SHA" CONFIRM="PUBLISH-BASE44-ACTIVE-V9:$SOURCE_SHA" BASE44_APP_ID="$APP_ID" \
    BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" READINESS_OUTPUT="$TMP/active-v9.json" \
    bash "$REPO_ROOT/scripts/deploy-base44-staged-functions.sh" publish-active
fi
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list
BASE44_APP_ID="$APP_ID" bash "$REPO_ROOT/scripts/verify-base44-functions.sh"

printf 'BASE44_RELEASE_FUNCTIONS_DEPLOYED\nsource_sha=%s\nfunction_count=%s\n' "$SOURCE_SHA" "${#FUNCTIONS[@]}"
