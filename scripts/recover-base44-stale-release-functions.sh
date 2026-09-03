#!/usr/bin/env bash
# Recover Base44 release functions when the platform reports their deployment as
# "unchanged" but the live handler does not expose the expected per-package
# build identity.
#
# This is intentionally separate from recover-base44-unrouted-functions.sh:
# that script repairs router-level 404 registration loss. This script repairs a
# different proven failure mode: a routed but stale compiled handler.
#
# Safety:
# - exact clean current main only
# - owner device session only
# - all nine release functions are fixed one at a time
# - a function already serving the exact expected build is never deleted
# - an edge/non-JSON/transport response is never eligible for deletion
# - delete -> prove absent -> deploy -> prove present -> exact build-id probe
# - any failure stops before the next function
# - no site deploy, no queue/barrier/IAM/secret/worker mutation
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
ACTION_CONFIRM="${ACTION_CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-8}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
EXPECTED_ACTION_CONFIRM="RECREATE-STALE-BASE44-RELEASE-FUNCTIONS"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

RECOVERY_FUNCTIONS=(
  ownerScanDebugControl
  durableScanWorkerControl
  persistDurableScanAuthority
  persistLimitedScanResult
  deleteCustomerScanData
  getCustomerScanResult
  startStandardScanJob
  createAccessCheckout
  stripeWebhook
)

strip_ansi() { sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g'; }

require_owner_session_mode() {
  if [[ -n "${BASE44_API_KEY:-}" ]]; then
    echo "Refusing stale-function recovery: unset BASE44_API_KEY and use the owner device session." >&2
    exit 2
  fi
  if [[ -z "$BASE44_EXPECTED_OWNER" ]]; then
    echo "Refusing stale-function recovery: BASE44_EXPECTED_OWNER is required." >&2
    exit 2
  fi
}

require_action_confirmation() {
  if [[ "$ACTION_CONFIRM" != "$EXPECTED_ACTION_CONFIRM" ]]; then
    echo "Refusing stale-function recovery: ACTION_CONFIRM must equal $EXPECTED_ACTION_CONFIRM." >&2
    exit 2
  fi
}

remote_inventory() {
  "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list 2>&1 | strip_ansi
}

inventory_contains() {
  local inventory="$1" name="$2"
  grep -Eq "(^|[[:space:]])${name}([[:space:]]|$)" <<<"$inventory"
}

expected_build_id() {
  node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$1"
}

valid_build_id() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]]
}

probe_route() {
  local name="$1" body_file status
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 25 \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
  PROBE_STATUS="$status"
  PROBE_BODY="$(head -c 2048 "$body_file" | tr -d '\n')"
  PROBE_BUILD_ID="$(python3 - "$body_file" <<'PY' 2>/dev/null || true
import json, re, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8", errors="replace"))
except Exception:
    raise SystemExit
build_id = str(value.get("build_id") or "")
if re.fullmatch(r"[0-9a-f]{64}", build_id):
    print(build_id, end="")
PY
)"
  rm -f "$body_file"
}

probe_body_is_json_object() {
  printf '%s' "$PROBE_BODY" | python3 -c 'import json, sys; value = json.load(sys.stdin); raise SystemExit(0 if isinstance(value, dict) else 1)' >/dev/null 2>&1
}

route_reaches_json_handler() {
  [[ "$PROBE_STATUS" =~ ^[1-5][0-9]{2}$ ]] \
    && probe_body_is_json_object \
    && [[ "$PROBE_BODY" != *"user worker not found"* ]]
}

route_is_known_stale_handler() {
  local name="$1"
  probe_body_is_json_object || return 1
  case "$name" in
    startStandardScanJob)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"version"[[:space:]]*:[[:space:]]*"startStandardScanJob_v3_server_admission"' <<<"$PROBE_BODY" \
        && grep -Eq '"error"[[:space:]]*:[[:space:]]*"Method not allowed\."' <<<"$PROBE_BODY"
      ;;
    durableScanWorkerControl)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error":"Use POST for durable worker control."' <<<"$PROBE_BODY"
      ;;
    persistDurableScanAuthority)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error":"Use POST to persist durable scan authority."' <<<"$PROBE_BODY"
      ;;
    persistLimitedScanResult)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error_message":"Use POST to persist a limited scan result."' <<<"$PROBE_BODY"
      ;;
    getCustomerScanResult)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error":"Use POST to load a saved scan."' <<<"$PROBE_BODY"
      ;;
    deleteCustomerScanData)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error":"Use POST to manage saved scan history."' <<<"$PROBE_BODY"
      ;;
    ownerScanDebugControl)
      [[ "$PROBE_STATUS" == "405" ]] \
        && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
        && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY" \
        && grep -Fq '"error":"Use POST for owner scan controls."' <<<"$PROBE_BODY"
      ;;
    createAccessCheckout)
      [[ "$PROBE_STATUS" == "500" ]] \
        && grep -Eq '"code"[[:space:]]*:[[:space:]]*"checkout_failed"' <<<"$PROBE_BODY"
      ;;
    stripeWebhook)
      [[ "$PROBE_STATUS" == "400" ]] \
        && grep -Fq '"error":"Neither apiKey nor config.authenticator provided"' <<<"$PROBE_BODY"
      ;;
    *)
      return 1
      ;;
  esac
}

route_serves_expected_build() {
  local expected="$1"
  [[ -n "$expected" && "$PROBE_BUILD_ID" == "$expected" ]]
}

require_expected_build() {
  local name="$1" expected="$2" attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    probe_route "$name"
    if route_reaches_json_handler && route_serves_expected_build "$expected"; then
      printf 'FUNCTION_BUILD_VERIFIED name=%s build_id=%s attempt=%s\n' "$name" "$expected" "$attempt"
      return 0
    fi
    printf '  probe %s: HTTP %s build_id=%s expected=%s attempt=%s/%s\n' \
      "$name" "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "$expected" "$attempt" "$PROBE_ATTEMPTS"
    attempt=$(( attempt + 1 ))
    (( attempt <= PROBE_ATTEMPTS )) && sleep "$PROBE_DELAY_SECONDS"
  done
  echo "Refusing to continue: $name did not serve expected build $expected." >&2
  return 1
}

require_recoverable_prestate() {
  local name="$1" expected
  expected="$(expected_build_id "$name")"
  if ! valid_build_id "$expected"; then
    echo "Refusing recovery preflight for $name: expected build id is not a 64-hex digest." >&2
    return 1
  fi
  probe_route "$name"
  if route_reaches_json_handler && route_serves_expected_build "$expected"; then
    printf 'PREFLIGHT_BUILD_CURRENT name=%s build_id=%s\n' "$name" "$expected"
    return 0
  fi
  if route_is_known_stale_handler "$name"; then
    printf 'PREFLIGHT_STALE_CONFIRMED name=%s http_status=%s expected=%s\n' \
      "$name" "$PROBE_STATUS" "$expected"
    return 0
  fi
  echo "Refusing recovery preflight for $name: runtime is neither exact-current nor the proven stale handler (HTTP $PROBE_STATUS)." >&2
  return 1
}

recover_one() {
  local name="$1" expected inventory
  expected="$(expected_build_id "$name")"
  if ! valid_build_id "$expected"; then
    echo "Refusing recovery for $name: expected build id is not a 64-hex digest." >&2
    return 1
  fi

  printf '\n--- %s ---\n' "$name"
  probe_route "$name"

  if route_reaches_json_handler && route_serves_expected_build "$expected"; then
    printf '  skip: already serves expected build %s\n' "$expected"
    return 0
  fi
  if ! route_is_known_stale_handler "$name"; then
    echo "Refusing recovery for $name: pre-state does not match the proven stale handler signature (HTTP $PROBE_STATUS)." >&2
    return 1
  fi

  printf '  stale: HTTP %s build_id=%s expected=%s\n' \
    "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "$expected"

  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing recovery for $name: function is absent from remote inventory." >&2
    return 1
  fi

  printf '  deleting ...\n'
  "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions delete "$name"
  inventory="$(remote_inventory)"
  if inventory_contains "$inventory" "$name"; then
    echo "Refusing to continue: $name is still present after delete." >&2
    return 1
  fi
  printf '  deleted: absent from remote inventory\n'

  printf '  deploying exact current-main package ...\n'
  "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "$name"
  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing to continue: $name did not reappear after deploy." >&2
    return 1
  fi
  printf '  deployed: present in remote inventory\n'

  require_expected_build "$name" "$expected"
  RECOVERED=$(( RECOVERED + 1 ))
}

if [[ -n "${FIXLIST_STALE_RECOVERY_LIB_ONLY:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

require_owner_session_mode
require_action_confirmation
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

cd "$REPO_ROOT"

FINAL_PRESTATE="$(remote_inventory)"
for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  inventory_contains "$FINAL_PRESTATE" "$fn" || {
    echo "Refusing recovery: $fn is missing from the initial remote inventory." >&2
    exit 1
  }
done

# Complete a non-mutating all-nine preflight before the first deletion. This
# prevents a later ambiguous handler from leaving the release half-recovered.
for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  require_recoverable_prestate "$fn"
done
printf 'BASE44_STALE_RECOVERY_PREFLIGHT_VERIFIED\n'

RECOVERED=0
for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  recover_one "$fn"
done

for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  expected="$(expected_build_id "$fn")"
  if ! valid_build_id "$expected"; then
    echo "Refusing final verification: expected build id for $fn is not a 64-hex digest." >&2
    exit 1
  fi
  require_expected_build "$fn" "$expected"
done

printf '\nBASE44_STALE_RELEASE_FUNCTIONS_RECOVERED\nsource_sha=%s\nrecovered=%s\n' \
  "$SOURCE_SHA" "$RECOVERED"
