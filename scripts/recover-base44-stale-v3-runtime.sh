#!/usr/bin/env bash
# Recover the six active V3 Base44 routes when the platform accepts their
# current definitions but continues executing a known stale compiled runtime.
#
# Safety properties:
# - exact clean current main only
# - owner device session only
# - explicit destructive-action confirmation
# - valid generated contracts and release manifest
# - all six routes are classified before the first deletion
# - already-current routes are never deleted
# - only exact incident-bound September 7 or September 9 stale builds are eligible
# - transport, HTML, router errors, malformed JSON, unknown status/marker refuse
# - delete -> prove absent -> deploy -> prove present -> verify build+activation
# - any failure stops before the next route
# - no Cloud Run, queue, admission, IAM, entity, scanner or frontend mutation
set -euo pipefail

SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
ACTION_CONFIRM="${ACTION_CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-12}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
FIXLIST_STALE_RECOVERY_LIB_ONLY=1 source "$REPO_ROOT/scripts/recover-base44-stale-release-functions.sh"

V3_EXPECTED_ACTION_CONFIRM="RECREATE-STALE-BASE44-V3-RUNTIME"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"

V3_FUNCTIONS=(
  startStandardScanJobV3
  durableScanWorkerControlV3
  persistDurableScanAuthorityV3
  persistLimitedScanResultV3
  getCustomerScanResultV3
  deleteCustomerScanDataV3
)

# Exact stale build identities observed on all six routes after Release Publish
# #133 reported them deployed but runtime attestation still returned the
# September 7 activation generation. Recovery is intentionally incident-bound:
# any other build with that marker is an uncharacterized state and refuses.
declare -A V3_STALE_BUILD_IDS=(
  [startStandardScanJobV3]="0b5465cb2230724e1d2320413e24830ddff6131aaed22f8ddb57275bcbda2b71"
  [durableScanWorkerControlV3]="ad58d77373edbca90aad92b103d444aa676dc8dba5ee1437fb5464dd3424f413"
  [persistDurableScanAuthorityV3]="c3d06e823cea841b3b461a753c4c3926d90c050e94e4a7375d3c62133b799317"
  [persistLimitedScanResultV3]="c8a7282b26e267aa76eb2f067fd4593071e021209138d155be167407c5fb609a"
  [getCustomerScanResultV3]="d7f681b2c965be72b077b20d6a713b9a82c679c42fc1c842255dab0769760de8"
  [deleteCustomerScanDataV3]="6f6c73c198d7a20df923721d826c994f4d8d40decec0ecd313e8f9992f12f481"
)

# Exact intermediate build identities observed in the September 9 production
# incident. These routes already expose the current activation marker, but their
# compiled build id is still the older incident-bound runtime. Only these exact
# build+activation pairs are eligible; unknown builds with the same marker refuse.
declare -A V3_SEPT9_INTERMEDIATE_BUILD_IDS=(
  [startStandardScanJobV3]="471f4c627608653dcce1a7f1eca0c6eff05569e85ba9728e0d3d7a1a8d6b3011"
  [persistDurableScanAuthorityV3]="96a6dfdd9a60eea0fbc687f81fcff2236c84d367ed4b247d1649c8e8545863ce"
  [persistLimitedScanResultV3]="803178674d7ef0d1c80637b0840ec2fb74c77833043ad92c4d7ae2647e089700"
  [getCustomerScanResultV3]="c29241f2779ee37dd7fe3ba1b3d5f991c05f7fe3ad1b5b29b152d273e650bb19"
)

canonical_of_v3() {
  node -e '
    const fs = require("node:fs");
    const routes = JSON.parse(fs.readFileSync(process.argv[1], "utf8")).routes;
    const alias = process.argv[2];
    const found = Object.entries(routes).find(([, active]) => active === alias);
    if (!found) process.exit(3);
    process.stdout.write(found[0]);
  ' "$REPO_ROOT/data/base44-function-routes.json" "$1"
}

expected_v3_activation_id() {
  node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$1"
}

valid_activation_id() {
  [[ "$1" =~ ^[A-Za-z0-9._-]{1,120}$ ]]
}

stale_v3_activation_id() {
  printf '%s-fresh-20260907-v1' "$1"
}

probe_v3_route() {
  local name="$1" body_file status identity
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 25 \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
  PROBE_STATUS="$status"
  PROBE_BODY="$(head -c 2048 "$body_file" | tr -d '\n')"
  identity="$(python3 - "$body_file" <<'PY' 2>/dev/null || true
import json, re, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8", errors="replace"))
except Exception:
    raise SystemExit
if not isinstance(value, dict):
    raise SystemExit
build_id = str(value.get("build_id") or "")
activation = str(value.get("runtime_activation_id") or "")
if not re.fullmatch(r"[0-9a-f]{64}", build_id):
    build_id = ""
if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", activation):
    activation = ""
print(f"{build_id} {activation}", end="")
PY
)"
  PROBE_BUILD_ID="${identity%% *}"
  PROBE_ACTIVATION_ID=""
  [[ "$identity" == *" "* ]] && PROBE_ACTIVATION_ID="${identity#* }"
  rm -f "$body_file"
}

route_serves_expected_v3_runtime() {
  local expected_build="$1" expected_activation="$2"
  [[ -n "$expected_build" && "$PROBE_BUILD_ID" == "$expected_build" ]] \
    && [[ -n "$expected_activation" && "$PROBE_ACTIVATION_ID" == "$expected_activation" ]]
}

route_is_known_stale_v3() {
  local name="$1" canonical="$2" stale_activation="$3" stale_build sept9_build
  stale_build="${V3_STALE_BUILD_IDS[$name]:-}"
  sept9_build="${V3_SEPT9_INTERMEDIATE_BUILD_IDS[$name]:-}"
  route_reaches_json_handler || return 1
  route_is_known_stale_handler "$canonical" || return 1

  if valid_build_id "$stale_build" \
    && [[ "$PROBE_BUILD_ID" == "$stale_build" ]] \
    && [[ -n "$stale_activation" && "$PROBE_ACTIVATION_ID" == "$stale_activation" ]]; then
    return 0
  fi

  if valid_build_id "$sept9_build" \
    && [[ "$PROBE_BUILD_ID" == "$sept9_build" ]] \
    && [[ -n "${V3_EXPECTED_ACTIVATION:-}" && "$PROBE_ACTIVATION_ID" == "$V3_EXPECTED_ACTIVATION" ]]; then
    return 0
  fi

  return 1
}

resolve_v3_expectations() {
  local name="$1"
  V3_CANONICAL="$(canonical_of_v3 "$name")" || {
    echo "Refusing V3 runtime recovery for $name: no canonical package in the active route contract." >&2
    return 1
  }
  V3_EXPECTED_BUILD="$(expected_build_id "$name")"
  V3_EXPECTED_ACTIVATION="$(expected_v3_activation_id "$name")"
  V3_STALE_ACTIVATION="$(stale_v3_activation_id "$name")"
  if ! valid_build_id "$V3_EXPECTED_BUILD"; then
    echo "Refusing V3 runtime recovery for $name: expected build id is not a 64-hex digest." >&2
    return 1
  fi
  if ! valid_activation_id "$V3_EXPECTED_ACTIVATION"; then
    echo "Refusing V3 runtime recovery for $name: expected activation marker is malformed." >&2
    return 1
  fi
  if ! valid_activation_id "$V3_STALE_ACTIVATION"; then
    echo "Refusing V3 runtime recovery for $name: stale activation marker is malformed." >&2
    return 1
  fi
  if [[ "$V3_EXPECTED_ACTIVATION" == "$V3_STALE_ACTIVATION" ]]; then
    echo "Refusing V3 runtime recovery for $name: expected and stale activation markers are identical." >&2
    return 1
  fi
}

require_recoverable_v3_prestate() {
  local name="$1"
  resolve_v3_expectations "$name" || return 1
  probe_v3_route "$name"
  if route_reaches_json_handler && route_serves_expected_v3_runtime "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"; then
    printf 'PREFLIGHT_RUNTIME_CURRENT name=%s build_id=%s runtime_activation_id=%s\n' \
      "$name" "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"
    return 0
  fi
  if route_is_known_stale_v3 "$name" "$V3_CANONICAL" "$V3_STALE_ACTIVATION"; then
    printf 'PREFLIGHT_STALE_CONFIRMED name=%s http_status=%s build_id=%s stale_activation=%s expected_activation=%s\n' \
      "$name" "$PROBE_STATUS" "$PROBE_BUILD_ID" "$PROBE_ACTIVATION_ID" "$V3_EXPECTED_ACTIVATION"
    return 0
  fi
  echo "Refusing V3 runtime recovery preflight for $name: runtime is neither exact-current nor a proven incident-bound stale handler (HTTP $PROBE_STATUS, build ${PROBE_BUILD_ID:-missing}, activation ${PROBE_ACTIVATION_ID:-missing})." >&2
  return 1
}

preflight_all_v3_routes() {
  local fn
  PREFLIGHT_UNCLASSIFIED=()
  for fn in "${V3_FUNCTIONS[@]}"; do
    if ! require_recoverable_v3_prestate "$fn"; then
      PREFLIGHT_UNCLASSIFIED+=("$fn")
    fi
  done
  (( ${#PREFLIGHT_UNCLASSIFIED[@]} == 0 ))
}

require_expected_v3_runtime() {
  local name="$1" expected_build="$2" expected_activation="$3" attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    probe_v3_route "$name"
    if route_reaches_json_handler && route_serves_expected_v3_runtime "$expected_build" "$expected_activation"; then
      printf 'FUNCTION_RUNTIME_VERIFIED name=%s build_id=%s runtime_activation_id=%s attempt=%s\n' \
        "$name" "$expected_build" "$expected_activation" "$attempt"
      return 0
    fi
    printf '  probe %s: HTTP %s build_id=%s activation=%s expected_build=%s expected_activation=%s attempt=%s/%s\n' \
      "$name" "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "${PROBE_ACTIVATION_ID:-missing}" \
      "$expected_build" "$expected_activation" "$attempt" "$PROBE_ATTEMPTS"
    attempt=$(( attempt + 1 ))
    (( attempt <= PROBE_ATTEMPTS )) && sleep "$PROBE_DELAY_SECONDS"
  done
  echo "Refusing to continue: $name did not serve expected build $expected_build with activation $expected_activation." >&2
  return 1
}

recover_one_v3() {
  local name="$1" inventory
  resolve_v3_expectations "$name" || return 1

  printf '\n--- %s ---\n' "$name"
  probe_v3_route "$name"
  if route_reaches_json_handler && route_serves_expected_v3_runtime "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"; then
    printf '  skip: already serves build %s with activation %s\n' "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"
    return 0
  fi
  if ! route_is_known_stale_v3 "$name" "$V3_CANONICAL" "$V3_STALE_ACTIVATION"; then
    echo "Refusing V3 runtime recovery for $name: pre-state no longer matches a proven incident-bound stale handler." >&2
    return 1
  fi

  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing V3 runtime recovery for $name: function is absent from remote inventory." >&2
    return 1
  fi

  # Re-probe immediately before deletion. If the platform converged in the
  # meantime, leave the now-current route untouched; any other state refuses.
  probe_v3_route "$name"
  if route_reaches_json_handler && route_serves_expected_v3_runtime "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"; then
    printf '  skip: became current between classification and deletion\n'
    return 0
  fi
  if ! route_is_known_stale_v3 "$name" "$V3_CANONICAL" "$V3_STALE_ACTIVATION"; then
    echo "Refusing V3 runtime recovery for $name: state changed between classification and deletion." >&2
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

  require_expected_v3_runtime "$name" "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"
  RECOVERED=$(( RECOVERED + 1 ))
}

if [[ -n "${FIXLIST_V3_RUNTIME_RECOVERY_LIB_ONLY:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

require_v3_action_confirmation() {
  if [[ "$ACTION_CONFIRM" != "$V3_EXPECTED_ACTION_CONFIRM" ]]; then
    echo "Refusing V3 runtime recovery: ACTION_CONFIRM must equal $V3_EXPECTED_ACTION_CONFIRM." >&2
    exit 2
  fi
}

require_owner_session_mode
require_v3_action_confirmation
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

cd "$REPO_ROOT"

FINAL_PRESTATE="$(remote_inventory)"
for fn in "${V3_FUNCTIONS[@]}"; do
  inventory_contains "$FINAL_PRESTATE" "$fn" || {
    echo "Refusing V3 runtime recovery: $fn is missing from the initial remote inventory." >&2
    exit 1
  }
done

if ! preflight_all_v3_routes; then
  printf 'BASE44_V3_RUNTIME_PREFLIGHT_REFUSED unclassified=%s of=%s routes=%s\n' \
    "${#PREFLIGHT_UNCLASSIFIED[@]}" "${#V3_FUNCTIONS[@]}" "${PREFLIGHT_UNCLASSIFIED[*]}" >&2
  echo "No function was deleted." >&2
  exit 1
fi
printf 'BASE44_V3_RUNTIME_PREFLIGHT_VERIFIED\n'

RECOVERED=0
for fn in "${V3_FUNCTIONS[@]}"; do
  recover_one_v3 "$fn"
done

for fn in "${V3_FUNCTIONS[@]}"; do
  resolve_v3_expectations "$fn" || exit 1
  require_expected_v3_runtime "$fn" "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"
done

printf '\nBASE44_V3_RUNTIME_RECOVERED\nsource_sha=%s\nrecovered=%s\n' "$SOURCE_SHA" "$RECOVERED"
