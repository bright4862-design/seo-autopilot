#!/usr/bin/env bash
# Recover the nine release-critical Base44 routes when Base44 still stores the
# function definitions but the public router answers `404 user worker not found`.
#
# Safety model:
# - exact clean current main only
# - owner device session only
# - classify all nine routes before the first mutation
# - only the exact router-level 404 is eligible for deletion
# - recover one function at a time, with inventory read-back and live attestation
# - V3 scanner/customer routes must serve the exact build + activation identity
# - owner debug / checkout / webhook must reach their known handler signatures
# - any ambiguous route state fails closed before the next function is touched
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
ACTION_CONFIRM="${ACTION_CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-12}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
EXPECTED_ACTION_CONFIRM="RECREATE-UNROUTED-BASE44-V3-RELEASE-FUNCTIONS"
ROUTER_MISSING_MARKER="user worker not found"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

# ownerScanDebugControl is deliberately first: it is an owner-only control
# surface and proves the delete/recreate mechanism before customer scan routes.
RECOVERY_FUNCTIONS=(
  ownerScanDebugControl
  startStandardScanJobV3
  durableScanWorkerControlV3
  persistDurableScanAuthorityV3
  persistLimitedScanResultV3
  getCustomerScanResultV3
  deleteCustomerScanDataV3
  createAccessCheckout
  stripeWebhook
)

strip_ansi() { sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g'; }

require_owner_session_mode() {
  if [[ -n "${BASE44_API_KEY:-}" ]]; then
    echo "Refusing V3 unrouted recovery: unset BASE44_API_KEY and use the owner device session." >&2
    exit 2
  fi
  if [[ -z "$BASE44_EXPECTED_OWNER" ]]; then
    echo "Refusing V3 unrouted recovery: BASE44_EXPECTED_OWNER is required." >&2
    exit 2
  fi
}

require_action_confirmation() {
  if [[ "$ACTION_CONFIRM" != "$EXPECTED_ACTION_CONFIRM" ]]; then
    echo "Refusing V3 unrouted recovery: ACTION_CONFIRM must equal $EXPECTED_ACTION_CONFIRM." >&2
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

probe_route() {
  local name="$1" body_file status
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 25 \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
  PROBE_STATUS="$status"
  PROBE_BODY="$(head -c 4096 "$body_file" | tr -d '\n')"
  PROBE_BUILD_ID=""
  PROBE_ACTIVATION_ID=""
  read -r PROBE_BUILD_ID PROBE_ACTIVATION_ID < <(
    node - "$body_file" <<'NODE' 2>/dev/null || true
const fs = require("node:fs");
let value;
try {
  value = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
} catch {
  process.exit(0);
}
if (value === null || typeof value !== "object" || Array.isArray(value)) process.exit(0);
const build = String(value.build_id || "");
const activation = String(value.runtime_activation_id || "");
process.stdout.write(`${build} ${activation}`);
NODE
  )
  rm -f "$body_file"
}

probe_body_is_json_object() {
  printf '%s' "$PROBE_BODY" | node -e '
let input="";
process.stdin.setEncoding("utf8");
process.stdin.on("data", c => input += c);
process.stdin.on("end", () => {
  try {
    const v = JSON.parse(input);
    process.exit(v && typeof v === "object" && !Array.isArray(v) ? 0 : 1);
  } catch { process.exit(1); }
});' >/dev/null 2>&1
}

route_is_unregistered() {
  [[ "$PROBE_STATUS" == "404" && "$PROBE_BODY" == *"$ROUTER_MISSING_MARKER"* ]]
}

is_v3_identity_route() {
  case "$1" in
    startStandardScanJobV3|durableScanWorkerControlV3|persistDurableScanAuthorityV3|persistLimitedScanResultV3|getCustomerScanResultV3|deleteCustomerScanDataV3)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

expected_build_id() {
  node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$1"
}

expected_activation_id() {
  node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$1"
}

valid_build_id() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]]
}

valid_activation_id() {
  [[ "$1" =~ ^[A-Za-z0-9._-]{1,120}$ ]]
}

route_is_expected_now() {
  local name="$1" expected_build expected_activation
  probe_body_is_json_object || return 1

  if is_v3_identity_route "$name"; then
    expected_build="$(expected_build_id "$name")"
    expected_activation="$(expected_activation_id "$name")"
    valid_build_id "$expected_build" || return 1
    valid_activation_id "$expected_activation" || return 1
    [[ "$PROBE_STATUS" == "405" \
      && "$PROBE_BUILD_ID" == "$expected_build" \
      && "$PROBE_ACTIVATION_ID" == "$expected_activation" ]]
    return
  fi

  case "$name" in
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

require_expected_route() {
  local name="$1" attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    probe_route "$name"
    if route_is_expected_now "$name"; then
      printf 'FUNCTION_ROUTE_VERIFIED name=%s http_status=%s build_id=%s activation_id=%s attempt=%s\n' \
        "$name" "$PROBE_STATUS" "${PROBE_BUILD_ID:-n/a}" "${PROBE_ACTIVATION_ID:-n/a}" "$attempt"
      return 0
    fi
    printf '  probe %s: HTTP %s build_id=%s activation_id=%s attempt=%s/%s\n' \
      "$name" "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "${PROBE_ACTIVATION_ID:-missing}" \
      "$attempt" "$PROBE_ATTEMPTS"
    attempt=$(( attempt + 1 ))
    (( attempt <= PROBE_ATTEMPTS )) && sleep "$PROBE_DELAY_SECONDS"
  done
  echo "Refusing to continue: $name did not reach its expected handler after recreation." >&2
  return 1
}

preflight_one_route() {
  local name="$1"
  probe_route "$name"
  if route_is_expected_now "$name"; then
    printf 'PREFLIGHT_CURRENT name=%s http_status=%s\n' "$name" "$PROBE_STATUS"
    return 0
  fi
  if route_is_unregistered; then
    printf 'PREFLIGHT_UNROUTED name=%s http_status=%s marker=%s\n' \
      "$name" "$PROBE_STATUS" "$ROUTER_MISSING_MARKER"
    return 0
  fi
  echo "Refusing recovery preflight for $name: route is neither exact-current nor the proven router-level 404 (HTTP $PROBE_STATUS)." >&2
  return 1
}

preflight_all_routes() {
  local name inventory
  inventory="$(remote_inventory)"
  for name in "${RECOVERY_FUNCTIONS[@]}"; do
    if ! inventory_contains "$inventory" "$name"; then
      echo "Refusing recovery preflight: $name is absent from Base44 function inventory." >&2
      return 1
    fi
    preflight_one_route "$name" || return 1
  done
  printf 'BASE44_V3_UNROUTED_RECOVERY_PREFLIGHT_VERIFIED\n'
}

recover_one() {
  local name="$1" inventory
  printf '\n--- %s ---\n' "$name"

  probe_route "$name"
  if route_is_expected_now "$name"; then
    printf '  skip: route already reaches the expected handler\n'
    return 0
  fi
  if ! route_is_unregistered; then
    echo "Refusing recovery for $name: pre-state is not the exact router-level 404 (HTTP $PROBE_STATUS)." >&2
    return 1
  fi

  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing recovery for $name: function disappeared from remote inventory before delete." >&2
    return 1
  fi

  printf '  deleting router-stale definition ...\n'
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

  require_expected_route "$name"
  RECOVERED=$(( RECOVERED + 1 ))
}

if [[ -n "${FIXLIST_V3_UNROUTED_RECOVERY_LIB_ONLY:-}" ]]; then
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
preflight_all_routes

RECOVERED=0
for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  recover_one "$fn"
done

for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  require_expected_route "$fn"
done

# The canonical verifier is the final authority for all six V3 scanner/customer
# routes and checks both exact build identity and runtime activation identity.
/bin/bash "$REPO_ROOT/scripts/verify-base44-functions.sh"

printf '\nBASE44_V3_UNROUTED_RELEASE_FUNCTIONS_RECOVERED\nsource_sha=%s\nrecovered=%s\n' \
  "$SOURCE_SHA" "$RECOVERED"
