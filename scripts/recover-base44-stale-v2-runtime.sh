#!/usr/bin/env bash
# Recover the six V2 Base44 routes when Base44 has synchronized their function
# definitions but has not recompiled the live handlers.
#
# The proven failure mode this repairs: `functions deploy` reports all six V2
# functions as "unchanged" while every V2 URL still executes the compiled
# package it was first created with. Publication then fails at the runtime gate
# with FUNCTION_BUILD_MISMATCH, and no amount of redeploying moves it, because
# Base44 believes the definition it holds is already current.
#
# This is deliberately a sibling of recover-base44-stale-release-functions.sh
# rather than a change to it. That script repairs the same class of fault on the
# nine canonical-era routes and is known to work; the V2 routes need one extra
# check it does not make, and adding a second identity to a destructive script
# that is currently correct is a worse trade than a separate entry point that
# reuses its proven classification.
#
# Why the extra check. A V2 package is stamped with the build identity of the
# canonical package it mirrors, so its expected build ID moves only when the
# canonical moves. The activation refresh changed the V2 entry files alone, so
# deleteCustomerScanDataV2's expected build ID is still exactly the one its
# stale handler serves. Verifying the build ID by itself calls that route
# current while it is running canonical-era code. Each package also carries its
# own runtime_activation_id, and that is what actually separates a V2 handler
# from the canonical-era one it was compiled from -- so both are required, here
# and in scripts/verify-base44-functions.sh.
#
# Safety:
# - exact clean current main only
# - owner device session only
# - explicit destructive-action confirmation
# - valid release manifest
# - a non-mutating preflight over all six precedes the first deletion
# - a route already serving the exact build AND activation marker is never deleted
# - any transport failure, HTML body, router 404, malformed JSON, unexpected
#   status, missing marker or unrecognized signature stops without deleting
# - delete -> prove absent -> deploy -> prove present -> poll both identities
# - a failure on one route stops before the next is touched
# - no site deploy, no Cloud Run, worker traffic, queue, admission barrier, IAM,
#   secret, entity, scanner or frontend mutation
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
# Reuse the proven stale-handler signature table and inventory helpers rather
# than restating them. LIB_ONLY stops that script before its own main body.
FIXLIST_STALE_RECOVERY_LIB_ONLY=1 source "$REPO_ROOT/scripts/recover-base44-stale-release-functions.sh"

# Everything below is declared after that source, because the canonical recovery
# assigns several of these unconditionally and a value set above the source is
# silently replaced by its own.
#
# EXPECTED_ACTION_CONFIRM is the case where that already bit: the phrase set
# above was being replaced by the canonical one, which would have meant this
# destructive run accepted the canonical recovery's authorisation instead of its
# own. It failed closed rather than open, but only by luck, and an operator
# holding one phrase must never be able to trigger the other. It is renamed here
# so the sourced script cannot reach it at all.
#
# APP_ID and PROBE_ORIGIN currently survive that reassignment by coincidence --
# both scripts derive them from the same environment variables with identical
# defaults, so the value is the same either way. They are set here anyway: the
# coincidence is not a property either file states, and if the defaults ever
# diverge the canonical's would win silently, which is exactly how the
# confirmation phrase went wrong.
V2_EXPECTED_ACTION_CONFIRM="RECREATE-STALE-BASE44-V2-RUNTIME"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"

V2_FUNCTIONS=(
  startStandardScanJobV2
  durableScanWorkerControlV2
  persistDurableScanAuthorityV2
  persistLimitedScanResultV2
  getCustomerScanResultV2
  deleteCustomerScanDataV2
)

# The canonical package each V2 route mirrors, read from the route contract
# rather than derived by trimming "V2" off the name.
canonical_of() {
  node -e '
    const fs = require("node:fs");
    const routes = JSON.parse(fs.readFileSync(process.argv[1], "utf8")).routes;
    const alias = process.argv[2];
    const found = Object.entries(routes).find(([, active]) => active === alias);
    if (!found) process.exit(3);
    process.stdout.write(found[0]);
  ' "$REPO_ROOT/data/base44-function-routes.json" "$1"
}

# The activation marker the named package declares, from the one resolver both
# this script and verify-base44-functions.sh use.
expected_activation_id() {
  node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$1"
}

# An activation marker shaped like one this repository produces. Anything else
# is a value no package here wrote, and is never compared against.
valid_activation_id() {
  [[ "$1" =~ ^[A-Za-z0-9._-]{1,120}$ ]]
}

# Captures both identities from one response. PROBE_STATUS, PROBE_BODY and
# PROBE_BUILD_ID keep the meanings the sourced script gives them, so its
# classification helpers continue to work unchanged.
probe_v2_route() {
  local name="$1" body_file status
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 25 \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
  PROBE_STATUS="$status"
  PROBE_BODY="$(head -c 2048 "$body_file" | tr -d '\n')"
  # Both identities from one parse. Neither pattern admits a space, so a single
  # separator is unambiguous and an absent or malformed marker stays empty --
  # which is what every caller checks for.
  local identity
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

# True only when the probed route serves this exact build AND this exact
# activation marker. Either alone is satisfiable by a handler that is not the
# one this source builds.
route_serves_expected_runtime() {
  local expected_build="$1" expected_activation="$2"
  [[ -n "$expected_build" && "$PROBE_BUILD_ID" == "$expected_build" ]] \
    && [[ -n "$expected_activation" && "$PROBE_ACTIVATION_ID" == "$expected_activation" ]]
}

# A stale V2 route is not merely "not current". It must be the exact handler we
# expect to find there: the recognized 405 JSON body for its canonical package,
# a well-formed build ID, and the canonical-era activation marker it was
# compiled with. Anything else -- an edge error, a router 404, a half-deployed
# handler, an unfamiliar marker -- is a state this script has not proven safe to
# delete, and it stops instead of guessing.
route_is_known_stale_v2() {
  local name="$1" canonical="$2" canonical_activation="$3"
  route_reaches_json_handler || return 1
  route_is_known_stale_handler "$canonical" || return 1
  valid_build_id "${PROBE_BUILD_ID:-}" || return 1
  [[ -n "$canonical_activation" && "$PROBE_ACTIVATION_ID" == "$canonical_activation" ]]
}

require_expected_v2_runtime() {
  local name="$1" expected_build="$2" expected_activation="$3" attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    probe_v2_route "$name"
    if route_reaches_json_handler && route_serves_expected_runtime "$expected_build" "$expected_activation"; then
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

# The four values every decision about one route is made from, or a refusal.
# Resolving them up front is what lets the preflight classify all six before
# anything is deleted.
resolve_expectations() {
  local name="$1"
  V2_CANONICAL="$(canonical_of "$name")" || {
    echo "Refusing V2 runtime recovery for $name: no canonical package in the route contract." >&2
    return 1
  }
  V2_EXPECTED_BUILD="$(expected_build_id "$name")"
  V2_EXPECTED_ACTIVATION="$(expected_activation_id "$name")"
  V2_CANONICAL_ACTIVATION="$(expected_activation_id "$V2_CANONICAL")"
  if ! valid_build_id "$V2_EXPECTED_BUILD"; then
    echo "Refusing V2 runtime recovery for $name: expected build id is not a 64-hex digest." >&2
    return 1
  fi
  if ! valid_activation_id "$V2_EXPECTED_ACTIVATION"; then
    echo "Refusing V2 runtime recovery for $name: expected activation marker is malformed." >&2
    return 1
  fi
  if ! valid_activation_id "$V2_CANONICAL_ACTIVATION"; then
    echo "Refusing V2 runtime recovery for $name: canonical activation marker is malformed." >&2
    return 1
  fi
  # If these were equal, a stale handler and a current one would be
  # indistinguishable and the recovery could not prove it had done anything.
  if [[ "$V2_EXPECTED_ACTIVATION" == "$V2_CANONICAL_ACTIVATION" ]]; then
    echo "Refusing V2 runtime recovery for $name: V2 and canonical activation markers are identical, so staleness cannot be proven." >&2
    return 1
  fi
  return 0
}

# Non-mutating. Classifies one route as already-current or provably stale, and
# refuses anything else. Runs for all six before the first deletion.
require_recoverable_v2_prestate() {
  local name="$1"
  resolve_expectations "$name" || return 1
  probe_v2_route "$name"
  if route_reaches_json_handler && route_serves_expected_runtime "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"; then
    printf 'PREFLIGHT_RUNTIME_CURRENT name=%s build_id=%s runtime_activation_id=%s\n' \
      "$name" "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"
    return 0
  fi
  if route_is_known_stale_v2 "$name" "$V2_CANONICAL" "$V2_CANONICAL_ACTIVATION"; then
    printf 'PREFLIGHT_STALE_CONFIRMED name=%s http_status=%s build_id=%s stale_activation=%s expected_activation=%s\n' \
      "$name" "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "${PROBE_ACTIVATION_ID:-missing}" "$V2_EXPECTED_ACTIVATION"
    return 0
  fi
  echo "Refusing V2 runtime recovery preflight for $name: runtime is neither exact-current nor the proven stale handler (HTTP $PROBE_STATUS, build ${PROBE_BUILD_ID:-missing}, activation ${PROBE_ACTIVATION_ID:-missing})." >&2
  return 1
}

# Recompile one route, or leave it alone. Every step proves its own outcome
# before the next begins, and any failure returns non-zero so `set -e` stops the
# run before the next route is touched.
recover_one_v2() {
  local name="$1" inventory
  resolve_expectations "$name" || return 1

  printf '\n--- %s ---\n' "$name"
  probe_v2_route "$name"

  if route_reaches_json_handler && route_serves_expected_runtime "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"; then
    printf '  skip: already serves build %s with activation %s\n' "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"
    return 0
  fi
  if ! route_is_known_stale_v2 "$name" "$V2_CANONICAL" "$V2_CANONICAL_ACTIVATION"; then
    echo "Refusing V2 runtime recovery for $name: pre-state does not match the proven stale handler signature (HTTP $PROBE_STATUS, build ${PROBE_BUILD_ID:-missing}, activation ${PROBE_ACTIVATION_ID:-missing})." >&2
    return 1
  fi

  printf '  stale: HTTP %s build_id=%s activation=%s expected_activation=%s\n' \
    "$PROBE_STATUS" "${PROBE_BUILD_ID:-missing}" "${PROBE_ACTIVATION_ID:-missing}" "$V2_EXPECTED_ACTIVATION"

  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing V2 runtime recovery for $name: function is absent from remote inventory." >&2
    return 1
  fi

  # Re-probe immediately before deleting, because the classification above is
  # now one network round trip old. Base44 activating the current handler inside
  # that window would mean deleting a route that is healthy at the moment of
  # deletion -- briefly taking a live route down for no reason, on a fleet whose
  # whole problem is that activation is unpredictable. A route that has become
  # current is left alone; anything else stops the run rather than deleting on a
  # classification that no longer describes the route.
  probe_v2_route "$name"
  if route_reaches_json_handler && route_serves_expected_runtime "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"; then
    printf '  skip: became current between classification and deletion\n'
    return 0
  fi
  if ! route_is_known_stale_v2 "$name" "$V2_CANONICAL" "$V2_CANONICAL_ACTIVATION"; then
    echo "Refusing V2 runtime recovery for $name: state changed between classification and deletion (HTTP $PROBE_STATUS, build ${PROBE_BUILD_ID:-missing}, activation ${PROBE_ACTIVATION_ID:-missing})." >&2
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

  require_expected_v2_runtime "$name" "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"
  RECOVERED=$(( RECOVERED + 1 ))
}

if [[ -n "${FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

require_v2_action_confirmation() {
  if [[ "$ACTION_CONFIRM" != "$V2_EXPECTED_ACTION_CONFIRM" ]]; then
    echo "Refusing V2 runtime recovery: ACTION_CONFIRM must equal $V2_EXPECTED_ACTION_CONFIRM." >&2
    exit 2
  fi
}

require_owner_session_mode
require_v2_action_confirmation
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

cd "$REPO_ROOT"

FINAL_PRESTATE="$(remote_inventory)"
for fn in "${V2_FUNCTIONS[@]}"; do
  inventory_contains "$FINAL_PRESTATE" "$fn" || {
    echo "Refusing V2 runtime recovery: $fn is missing from the initial remote inventory." >&2
    exit 1
  }
done

# Every route is classified before any route is deleted. A sixth function that
# turns out to be in an unrecognized state after the first five were deleted and
# redeployed would leave the release half-recovered, which is a worse position
# than the one this script exists to repair.
for fn in "${V2_FUNCTIONS[@]}"; do
  require_recoverable_v2_prestate "$fn"
done
printf 'BASE44_V2_RUNTIME_PREFLIGHT_VERIFIED\n'

RECOVERED=0
for fn in "${V2_FUNCTIONS[@]}"; do
  recover_one_v2 "$fn"
done

for fn in "${V2_FUNCTIONS[@]}"; do
  resolve_expectations "$fn" || exit 1
  require_expected_v2_runtime "$fn" "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"
done

printf '\nBASE44_V2_RUNTIME_RECOVERED\nsource_sha=%s\nrecovered=%s\n' \
  "$SOURCE_SHA" "$RECOVERED"
