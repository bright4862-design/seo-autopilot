#!/usr/bin/env bash
# Re-register the five Base44 functions whose public routes answer
# `404 user worker not found` even though the server already stores the correct
# entry.ts package.
#
# Why this exists. base44@0.1.8 exposes exactly three backend-function
# operations: GET backend-functions (list), PUT backend-functions/{name}
# (deploy one), DELETE backend-functions/{name} (delete one). The server -- not
# the client -- decides `deployed` vs `unchanged`, and a guarded functions-only
# deploy from 6151d0ef reported `2 deployed / 7 unchanged` while those five kept
# 404ing. A server-read-only `functions pull` confirmed the stored package
# already carries the entry.ts shim, so the content is right and the route
# registration is stale. `unchanged` therefore never re-registers the route, and
# no CLI flag forces it: `deploy --force` is prune-only (it DELETEs every remote
# function missing locally) and refuses to run with explicit names. Deleting one
# function and redeploying it is the only narrow supported path.
#
# Safety model:
#   - Only the five names below may ever be touched. The four functions that
#     currently serve traffic -- startStandardScanJob, getCustomerScanResult,
#     createAccessCheckout, stripeWebhook -- are never named, never deleted and
#     never redeployed by this script.
#   - A function is deleted ONLY after its live route is proven to be the
#     router-level 404. A route that already answers is left alone, so this can
#     never take down something that works.
#   - One function at a time: delete -> confirm gone -> deploy -> confirm listed
#     -> probe. Any failure stops the run before the next function is touched.
#   - Inventory membership is read back from `functions list` rather than parsed
#     out of CLI prose, because `functions delete` reports failures in text and
#     still exits zero.
#   - No site deploy, no cohort, no scan, no --force, no secret mutation.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
DRY_RUN="${DRY_RUN:-}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-6}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

# ownerScanDebugControl leads deliberately: it is an owner-only debug surface
# with no customer traffic and no worker dependency, so it proves the
# delete/recreate mechanism before anything on the durable scan path moves.
RECOVERY_FUNCTIONS=(
  ownerScanDebugControl
  durableScanWorkerControl
  persistDurableScanAuthority
  persistLimitedScanResult
  deleteCustomerScanData
)

# Named so a future edit that adds one of these to RECOVERY_FUNCTIONS fails the
# guard below instead of deleting a live route.
PROTECTED_FUNCTIONS=(
  startStandardScanJob
  getCustomerScanResult
  createAccessCheckout
  stripeWebhook
)

ROUTER_MISSING_MARKER="user worker not found"

strip_ansi() { sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g'; }

require_recovery_allowlist() {
  local candidate protected
  for candidate in "${RECOVERY_FUNCTIONS[@]}"; do
    for protected in "${PROTECTED_FUNCTIONS[@]}"; do
      if [[ "$candidate" == "$protected" ]]; then
        echo "Refusing recovery: $candidate serves live traffic and must never be deleted." >&2
        exit 2
      fi
    done
  done
}

require_owner_session_mode() {
  # The workspace key demonstrably cannot reach this app (publish run
  # 33260872931 failed closed on exactly that check), and the key path skips the
  # owner identity assertion entirely. Recovery is owner-session only.
  if [[ -n "${BASE44_API_KEY:-}" ]]; then
    echo "Refusing recovery: unset BASE44_API_KEY and use the owner device-code session." >&2
    exit 2
  fi
  if [[ -z "$BASE44_EXPECTED_OWNER" ]]; then
    echo "Refusing recovery: BASE44_EXPECTED_OWNER is required." >&2
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

# Read-only GET. Every recovery function answers 405 method_not_allowed on GET,
# so a GET can never mutate anything and still distinguishes a live handler from
# the router's 404.
probe_route() {
  local name="$1" body_file status
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 25 \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
  PROBE_STATUS="$status"
  PROBE_BODY="$(head -c 512 "$body_file" | tr -d '\n')"
  rm -f "$body_file"
}

route_is_unregistered() {
  [[ "$PROBE_STATUS" == "404" && "$PROBE_BODY" == *"$ROUTER_MISSING_MARKER"* ]]
}

# Weak liveness: the response came from some Base44 function rather than the
# router or an edge. Used only for the protected four, whose GET answers
# legitimately differ (405 without an error_code, 400, 500), so their shape
# cannot be pinned to one signature. Requiring a JSON object still rejects
# Cloudflare/edge HTML, empty redirect bodies and transport failures.
route_reaches_handler() {
  [[ "$PROBE_STATUS" =~ ^[1-5][0-9]{2}$ ]] \
    && [[ "$PROBE_BODY" == "{"* ]] \
    && [[ "$PROBE_BODY" != *"$ROUTER_MISSING_MARKER"* ]]
}

# Strong proof of recovery, required of the five before the next one is touched.
# Each of their handlers rejects GET as its first statement, before any
# try/catch or env access, via Response.json({success:false, error_code:
# "method_not_allowed", ...}, {status: 405}) -- so the signature is
# deterministic and anything else means the route did not reach the handler.
#
# Deliberately NOT "any response without the router marker": a Cloudflare 403,
# an arbitrary 500, an unrelated 404, a redirect and an HTML login page all pass
# that weaker test, and each would let the run delete the next function while
# this one is still broken.
route_is_recovered() {
  [[ "$PROBE_STATUS" == "405" ]] \
    && [[ "$PROBE_BODY" == "{"* ]] \
    && grep -Eq '"success"[[:space:]]*:[[:space:]]*false' <<<"$PROBE_BODY" \
    && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*"method_not_allowed"' <<<"$PROBE_BODY"
}

require_handled_route() {
  local name="$1" attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    probe_route "$name"
    if route_is_recovered; then
      printf '  probe %s: HTTP %s method_not_allowed from the handler (attempt %s)\n' \
        "$name" "$PROBE_STATUS" "$attempt"
      return 0
    fi
    printf '  probe %s: HTTP %s is not the handler 405 signature (attempt %s/%s)\n' \
      "$name" "$PROBE_STATUS" "$attempt" "$PROBE_ATTEMPTS"
    attempt=$(( attempt + 1 ))
    (( attempt <= PROBE_ATTEMPTS )) && sleep "$PROBE_DELAY_SECONDS"
  done
  echo "Refusing to continue: $name did not answer 405 method_not_allowed after recreation (last HTTP $PROBE_STATUS)." >&2
  return 1
}

recover_one() {
  local name="$1" inventory

  printf '\n--- %s ---\n' "$name"

  probe_route "$name"
  if route_is_recovered; then
    printf '  skip: already answering the handler 405; not deleting a live route\n'
    return 0
  fi
  # Anything that is neither the handler signature nor the exact router 404 --
  # an edge 403, a 5xx, an unrelated 404 -- is an unknown state, and deleting a
  # function whose real state is unknown is exactly what must not happen.
  if ! route_is_unregistered; then
    echo "Refusing recovery for $name: unexpected pre-state HTTP $PROBE_STATUS." >&2
    return 1
  fi
  printf '  pre-state: HTTP %s router-level 404, eligible for re-registration\n' "$PROBE_STATUS"
  RECOVERY_ELIGIBLE=$(( RECOVERY_ELIGIBLE + 1 ))

  if [[ -n "$DRY_RUN" ]]; then
    printf '  DRY_RUN: would delete then deploy %s, then require a handler-level probe\n' "$name"
    return 0
  fi

  printf '  deleting ...\n'
  "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions delete "$name"
  inventory="$(remote_inventory)"
  if inventory_contains "$inventory" "$name"; then
    echo "Refusing to continue: $name is still present in the remote inventory after delete." >&2
    return 1
  fi
  printf '  deleted: absent from remote inventory\n'

  printf '  deploying ...\n'
  "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "$name"
  inventory="$(remote_inventory)"
  if ! inventory_contains "$inventory" "$name"; then
    echo "Refusing to continue: $name did not reappear in the remote inventory after deploy." >&2
    return 1
  fi
  printf '  deployed: present in remote inventory\n'

  require_handled_route "$name"
  RECOVERY_APPLIED=$(( RECOVERY_APPLIED + 1 ))
}

# Sourcing the script for its route classifiers must never run the recovery.
# The regression tests exercise route_is_recovered/route_reaches_handler against
# real response shapes, which is only possible if loading the file is inert.
if [[ -n "${FIXLIST_RECOVERY_LIB_ONLY:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

RECOVERY_ELIGIBLE=0
RECOVERY_APPLIED=0

require_recovery_allowlist
require_owner_session_mode
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami"

cd "$REPO_ROOT"

echo
echo "Protected routes before recovery (must already answer):"
for fn in "${PROTECTED_FUNCTIONS[@]}"; do
  probe_route "$fn"
  if ! route_reaches_handler; then
    echo "Refusing recovery: protected function $fn is not answering (HTTP $PROBE_STATUS)." >&2
    exit 1
  fi
  printf '  %-24s HTTP %s\n' "$fn" "$PROBE_STATUS"
done

for fn in "${RECOVERY_FUNCTIONS[@]}"; do
  recover_one "$fn"
done

echo
echo "Protected routes after recovery (must be unchanged):"
for fn in "${PROTECTED_FUNCTIONS[@]}"; do
  probe_route "$fn"
  if ! route_reaches_handler; then
    echo "Recovery damaged protected function $fn (HTTP $PROBE_STATUS)." >&2
    exit 1
  fi
  printf '  %-24s HTTP %s\n' "$fn" "$PROBE_STATUS"
done

FINAL_INVENTORY="$(remote_inventory)"
for fn in "${RECOVERY_FUNCTIONS[@]}" "${PROTECTED_FUNCTIONS[@]}"; do
  inventory_contains "$FINAL_INVENTORY" "$fn" || {
    echo "Refusing to report success: $fn missing from the final remote inventory." >&2
    exit 1
  }
done

# A dry run mutates nothing, so it must never emit the recovered banner or a
# non-zero recovered count -- the operator reads that line as proof of work.
if [[ -n "$DRY_RUN" ]]; then
  printf '\nBASE44_UNROUTED_FUNCTIONS_DRY_RUN_COMPLETE\nsource_sha=%s\neligible=%s\nrecovered=0\n' \
    "$SOURCE_SHA" "$RECOVERY_ELIGIBLE"
  exit 0
fi

printf '\nBASE44_UNROUTED_FUNCTIONS_RECOVERED\nsource_sha=%s\neligible=%s\nrecovered=%s\n' \
  "$SOURCE_SHA" "$RECOVERY_ELIGIBLE" "$RECOVERY_APPLIED"
