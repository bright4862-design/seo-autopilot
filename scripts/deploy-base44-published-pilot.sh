#!/usr/bin/env bash
# Publish the named-account pilot bundle with the public V8 manifest intact.
# The signed coordinator barrier and Base44 intake must already be closed.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$ROOT/scripts/lib/release-source-guard.sh"
source "$ROOT/scripts/deploy-base44-staged-functions.sh"
source "$ROOT/scripts/lib/base44-pinned-cli.sh"

APP_ID=6a498732ec779dfaaeab0e53
SOURCE_SHA="${SOURCE_SHA:-}"
PUBLIC_BASELINE_SHA="${PUBLIC_BASELINE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"
SNAPSHOT_DIR="${PILOT_SNAPSHOT_DIR:-}"
operation="${1:-publish}"
CAPTURE_CONFIG='{"name":"fixlist-pilot-capture","functionsDir":"functions","entitiesDir":"entities"}'

if [[ "$operation" == prepare-provider-snapshot ]]; then
  PUBLIC_BASELINE_SHA="$(<"$ROOT/data/published-pilot-legacy-source")"
fi

refuse() { printf 'Published FixList pilot stopped. %s\n' "$*" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ && "$PUBLIC_BASELINE_SHA" =~ ^[a-f0-9]{40}$ ]] || refuse "Supply the exact candidate and currently published commits."
(( $# <= 1 )) || refuse "Choose publish, restore-snapshot, or prepare-provider-snapshot."
case "$operation" in
  prepare-provider-snapshot) expected_confirmation="PREPARE-PROVIDER-SNAPSHOT:$SOURCE_SHA:$PUBLIC_BASELINE_SHA:$BARRIER_EXPECTED_GENERATION" ;;
  publish) expected_confirmation="PUBLISH-BASE44-PILOT:$SOURCE_SHA:$PUBLIC_BASELINE_SHA" ;;
  restore-snapshot) expected_confirmation="RESTORE-BASE44-PILOT:$SOURCE_SHA:$PUBLIC_BASELINE_SHA:$BARRIER_EXPECTED_GENERATION" ;;
  *) refuse "Choose publish, restore-snapshot, or prepare-provider-snapshot." ;;
esac
[[ "$CONFIRM" == "$expected_confirmation" ]] || refuse "Supply exact confirmation for the selected operation."
[[ "${BASE44_APP_ID:-$APP_ID}" == "$APP_ID" && -z "${BASE44_API_KEY:-}" ]] || refuse "Use the authenticated owner session for the GetFixList app."
case "$BASE44_EXPECTED_OWNER" in
  bright4862@gmail.com|londonparisbrussels@gmail.com) ;;
  *) refuse "Select the approved Base44 owner session." ;;
esac
[[ "$BARRIER_EXPECTED_GENERATION" =~ ^[0-9]+$ ]] || refuse "Select the current closed barrier generation."

if [[ "$operation" == restore-snapshot ]]; then
  fixlist_require_merged_checkout "$ROOT" "$SOURCE_SHA"
else
  fixlist_require_exact_main "$ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
fi
cd "$ROOT"
node --input-type=module <<'NODE'
import fs from "node:fs";
const manifest = JSON.parse(fs.readFileSync("data/base44-function-routes.json", "utf8"));
const candidate = JSON.parse(fs.readFileSync("data/beta-crawler-revision.json", "utf8"));
if (manifest.generation !== "v8" || !manifest.candidate_routes?.v9
    || candidate.status !== "candidate" || candidate.git_commit || candidate.acceptance_report) {
  throw new Error("Pilot publication requires the public V8 manifest and an unaccepted V9 candidate");
}
NODE
git merge-base --is-ancestor "$PUBLIC_BASELINE_SHA" "$SOURCE_SHA" || refuse "The current public source must be an ancestor of the pilot."
node "$ROOT/scripts/generate_release_contracts.mjs" --check

work="$(mktemp -d)"
backup=""
preserve_snapshot=false
cleanup() {
  if [[ "$operation" == publish && -n "$backup" && "$preserve_snapshot" == false ]]; then
    rm -rf "$backup"
  fi
  rm -rf "$work"
}
trap cleanup EXIT

verify_drain() {
  OPERATION=verify-zero-admission-obligations SOURCE_SHA="$SOURCE_SHA" FIXLIST_DRAIN_READBACK_SOURCE_GUARD="${1:-current}" \
    BARRIER_EXPECTED_PRIOR_MODE=closed \
    BARRIER_EXPECTED_GENERATION="$BARRIER_EXPECTED_GENERATION" \
    CONFIRM="VERIFY-ZERO-ADMISSION:$SOURCE_SHA:$BARRIER_EXPECTED_GENERATION" bash "$ROOT/scripts/fixlist-cloud-operator.sh"
}
verify_v9() {
  SOURCE_SHA="$SOURCE_SHA" CONFIRM="VERIFY-PINNED-BASE44-STAGED-V9:$SOURCE_SHA" BASE44_APP_ID="$APP_ID" \
    BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" READINESS_OUTPUT="$work/v9-$1.json" \
    fixlist_publish_v9_packages verify-pinned
}
verify_site() {
  PUBLIC_URL="${2:-https://getfixlist.com/}" BASE44_URL="${2:-https://getfixlist.base44.app/}" EXPECTED_SOURCE_SHA="$1" \
    EXPECTED_SCAN_FUNCTION_GENERATION="${3:-}" \
    bash "$ROOT/scripts/verify-base44-site.sh"
}
verify_v8() {
  BASE44_APP_ID="$APP_ID" BASE44_FUNCTION_ORIGIN=https://base44.app bash "$work/baseline/scripts/verify-base44-functions.sh"
}
make_capture_project() {
  mkdir -p "$1/base44/functions" "$1/base44/entities" || return 1
  printf '%s\n' "$CAPTURE_CONFIG" > "$1/base44/config.jsonc"
}
capture() {
  local snapshot="$1" restore_project="${2:-}"
  make_capture_project "$snapshot" || return 1
  ( cd "$snapshot" || exit 1
    NO_COLOR=1 timeout --kill-after=5s 90 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list > listed.txt 2>&1 || exit 1
    NO_COLOR=1 timeout --kill-after=5s 110 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull > pulled.txt 2>&1
  ) || return 1
  node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" capture "$snapshot" "$snapshot/listed.txt" "$snapshot/digests.json" ${restore_project:+"$restore_project"}
}
during_recovery_capture() {
  local output="$1" snapshot attempt
  for attempt in 1 2 3; do
    snapshot="$(mktemp -d "$work/inventory.XXXXXX")" || return 1
    if capture "$snapshot"; then
      mv "$snapshot" "$output"
      return $?
    fi
    printf 'Function inventory read failed on attempt %s.\n' "$attempt" >&2
  done
  return 1
}
difference() {
  node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" compare "$backup/before/digests.json" "$1"
}

restore_and_verify() {
  local observed="$1" after="$1" restore_routes after_restore_difference name recovery_status=0 names=()
  restore_routes="$(node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" restore-plan "$backup/before/digests.json" "$observed")"
  if [[ -n "$restore_routes" ]]; then
    while IFS= read -r name; do names+=("$name"); done <<< "$restore_routes"
    verify_drain pinned
    ( cd "$backup/restore" || exit 1
      timeout --kill-after=5s 180 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${names[@]}"
    ) || recovery_status=$?
    during_recovery_capture "$work/after-restore" || refuse "Could not re-read the restored function inventory. Use the saved snapshot after the provider recovers."
    after="$work/after-restore/digests.json"
  fi
  verify_v8
  verify_v9 after
  fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
  after_restore_difference="$(difference "$after")" || refuse "Unexpected functions remain after recovery. Review the inventory with intake closed."
  [[ -z "$after_restore_difference" ]] || refuse "Restored packages did not match the original deployed inventory."
  (( recovery_status == 0 )) || refuse "The recovery deploy reported an error. The inventory and scanner routes were verified separately."
}

mkdir "$work/baseline"
git archive "$PUBLIC_BASELINE_SHA" | tar -x -C "$work/baseline"
[[ "$(node "$work/baseline/scripts/lib/base44-public-routes.mjs")" == v8\ * ]] || refuse "The current public baseline does not specify V8."

if [[ "$operation" == prepare-provider-snapshot ]]; then
  output="${PILOT_PROVIDER_DIR:-}"
  [[ "$output" == /* && ! -e "$output" && ! -L "$output" ]] || refuse "Supply a new absolute PILOT_PROVIDER_DIR."
  parent="$(cd "$(dirname "$output")" && pwd -P)"
  [[ "$parent" != "$ROOT" && "$parent" != "$ROOT/"* ]] || refuse "Choose a directory outside the checkout."
  verify_drain
  fixlist_install_base44_cli "$work/cli"
  fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$work/auth" "$APP_ID"
  fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
  verify_v8
  verify_v9 before
  capture "$work/initial"
  capture "$work/current"
  diff -q "$work/initial/digests.json" "$work/current/digests.json" || refuse "The management inventory changed during capture."
  verify_drain
  fixlist_require_exact_main "$ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
  mkdir "$work/source"
  git archive "$SOURCE_SHA" | tar -x -C "$work/source"
  node "$ROOT/scripts/lib/base44-provider-snapshot.mjs" "$work/source" "$work/baseline" "$work/current" "$output" "$SOURCE_SHA" "$SOURCE_SHA" checkpoint-input
  exit 0
fi

snapshot_identity="$(printf '%s\n' "$APP_ID" "$SOURCE_SHA" "$PUBLIC_BASELINE_SHA")"
if [[ -n "$SNAPSHOT_DIR" ]]; then
  [[ "$SNAPSHOT_DIR" == /* ]] || refuse "The snapshot directory must be an absolute path."
  snapshot_parent="$(cd "$(dirname "$SNAPSHOT_DIR")" && pwd -P)"
  snapshot_path="$snapshot_parent/$(basename "$SNAPSHOT_DIR")"
  [[ "$snapshot_path" != "$ROOT" && "$snapshot_path" != "$ROOT/"* ]] || refuse "The snapshot directory must be outside the release checkout."
fi

if [[ "$operation" == restore-snapshot ]]; then
  [[ -n "$SNAPSHOT_DIR" ]] || refuse "Supply the saved PILOT_SNAPSHOT_DIR."
  backup="$snapshot_path"
  node - "$backup" <<'NODE'
const fs = require('node:fs');
const value = fs.lstatSync(process.argv[2]);
if (!value.isDirectory() || value.uid !== process.getuid() || (value.mode & 0o077)) process.exit(1);
NODE
  [[ "$(<"$backup/identity")" == "$snapshot_identity" ]] || refuse "The snapshot does not match the selected app and source commits."
  [[ "$(<"$backup/restore/base44/config.jsonc")" == "$CAPTURE_CONFIG" ]] || refuse "The recovery project configuration differs from the saved capture."
  node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" capture "$backup/restore" "$backup/before/listed.txt" "$work/snapshot-digests.json"
  snapshot_difference="$(difference "$work/snapshot-digests.json")" || refuse "The recovery copy has an unexpected function inventory."
  [[ -z "$snapshot_difference" ]] || refuse "The recovery copy does not match its saved inventory."
  for origin in https://getfixlist.com/ https://getfixlist.base44.app/; do
    if ! verify_site "$SOURCE_SHA" "$origin" && ! verify_site "$PUBLIC_BASELINE_SHA" "$origin"; then
      refuse "The site serves a source outside the pilot recovery snapshot."
    fi
  done
  verify_drain pinned
  fixlist_install_base44_cli "$work/cli"
  fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$work/auth" "$APP_ID"
  during_recovery_capture "$work/current" || refuse "The current function inventory could not be read."
  if ! fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"; then
    node - "$backup/before/digests.json" "$work/current/digests.json" <<'NODE'
const [before, current] = process.argv.slice(2).map(file => require(file));
const name = 'fixlistStagedRuntimeControl';
if (!before[name] || current[name] !== before[name]) process.exit(1);
NODE
    fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER" operator
  fi
  restore_and_verify "$work/current/digests.json"
  verify_drain pinned
  printf 'BASE44_PILOT_SNAPSHOT_RESTORED source_sha=%s baseline_sha=%s admission=closed\n' "$SOURCE_SHA" "$PUBLIC_BASELINE_SHA"
  exit 0
fi

if [[ -n "$SNAPSHOT_DIR" ]]; then
  mkdir -m 700 "$snapshot_path"
  backup="$snapshot_path"
else
  backup="$(mktemp -d)"
fi
printf '%s\n' "$snapshot_identity" > "$backup/identity"
verify_site "$PUBLIC_BASELINE_SHA"
verify_v8
verify_drain
fixlist_install_base44_cli "$work/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$work/auth" "$APP_ID"
fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
verify_v9 before
make_capture_project "$backup/restore"
capture "$backup/before" "$backup/restore"

VITE_SCAN_FUNCTION_GENERATION=PUBLISHED_PILOT VITE_BASE44_APP_ID="$APP_ID" VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build
fixlist_require_pinned_checkout "$ROOT" "$SOURCE_SHA"
verify_drain
fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
# Refresh inventory immediately before the upload so the recovery copy cannot
# silently erase route changes from an overlapping publication.
capture "$work/before-upload"
before_upload_difference="$(difference "$work/before-upload/digests.json")"
[[ -z "$before_upload_difference" ]] || refuse "The function inventory changed before upload."

preserve_snapshot=true
printf 'Recovery copy captured at %s\n' "$backup"
site_status=0
timeout --kill-after=5s 180 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" site deploy --no-build --yes || site_status=$?

# Snapshot reconciliation can change live function packages even when the site
# call returns an error. Restore only routes with different or missing bytes.
during_recovery_capture "$work/after-upload" || refuse "The function inventory is unavailable. Restore the saved snapshot after the provider recovers."
restore_and_verify "$work/after-upload/digests.json"
(( site_status == 0 )) || refuse "The site upload did not report success; function packages were checked."
verify_site "$SOURCE_SHA" "" PUBLISHED_PILOT
verify_drain pinned
fixlist_require_exact_main "$ROOT" "$SOURCE_SHA" "$SOURCE_SHA" || refuse "Main advanced after upload. The published source and routes were verified with admissions closed."
printf 'BASE44_PUBLISHED_PILOT_VERIFIED source_sha=%s baseline_sha=%s admission=closed\n' "$SOURCE_SHA" "$PUBLIC_BASELINE_SHA"
