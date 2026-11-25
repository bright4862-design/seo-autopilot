#!/usr/bin/env bash
# Publish the named-account pilot bundle with the public V8 manifest intact.
# The signed coordinator barrier and Base44 intake must already be closed.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/release-source-guard.sh"
source "$ROOT/scripts/deploy-base44-staged-functions.sh"
source "$ROOT/scripts/lib/base44-pinned-cli.sh"

APP_ID=6a498732ec779dfaaeab0e53
SOURCE_SHA="${SOURCE_SHA:-}"
PUBLIC_BASELINE_SHA="${PUBLIC_BASELINE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"

refuse() { printf 'Published FixList pilot stopped. %s\n' "$*" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ && "$PUBLIC_BASELINE_SHA" =~ ^[a-f0-9]{40}$ ]] || refuse "Supply the exact candidate and currently published commits."
[[ "$CONFIRM" == "PUBLISH-BASE44-PILOT:$SOURCE_SHA:$PUBLIC_BASELINE_SHA" ]] || refuse "Supply exact pilot publication confirmation."
[[ "${BASE44_APP_ID:-$APP_ID}" == "$APP_ID" && -z "${BASE44_API_KEY:-}" ]] || refuse "Use the authenticated owner session for the GetFixList app."
case "$BASE44_EXPECTED_OWNER" in
  bright4862@gmail.com|londonparisbrussels@gmail.com) ;;
  *) refuse "Select the approved Base44 owner session." ;;
esac
[[ "$BARRIER_EXPECTED_GENERATION" =~ ^[0-9]+$ ]] || refuse "Select the current closed barrier generation."

fixlist_require_exact_main "$ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
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

backup="$(mktemp -d)"
outcome=0
mutation_started=false
cleanup() {
  if [[ "$mutation_started" == true && "$outcome" != 0 ]]; then
    printf 'Private recovery files are at %s\n' "$backup" >&2
  else
    rm -rf "$backup"
  fi
}
trap 'outcome=$?; cleanup' EXIT

verify_drain() {
  OPERATION=verify-zero-admission-obligations SOURCE_SHA="$SOURCE_SHA" BARRIER_EXPECTED_PRIOR_MODE=closed \
    BARRIER_EXPECTED_GENERATION="$BARRIER_EXPECTED_GENERATION" \
    CONFIRM="VERIFY-ZERO-ADMISSION:$SOURCE_SHA:$BARRIER_EXPECTED_GENERATION" bash "$ROOT/scripts/fixlist-cloud-operator.sh"
}
verify_v9() {
  SOURCE_SHA="$SOURCE_SHA" CONFIRM="VERIFY-BASE44-STAGED-V9:$SOURCE_SHA" BASE44_APP_ID="$APP_ID" \
    BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" READINESS_OUTPUT="$backup/v9-$1.json" \
    bash "$ROOT/scripts/deploy-base44-staged-functions.sh" verify
}
verify_site() {
  PUBLIC_URL=https://getfixlist.com/ BASE44_URL=https://getfixlist.base44.app/ EXPECTED_SOURCE_SHA="$1" \
    bash "$ROOT/scripts/verify-base44-site.sh"
}
verify_v8() {
  BASE44_APP_ID="$APP_ID" BASE44_FUNCTION_ORIGIN=https://base44.app bash "$backup/baseline/scripts/verify-base44-functions.sh"
}
make_capture_project() {
  mkdir -p "$1/base44/functions" "$1/base44/entities"
  printf '%s\n' '{"name":"fixlist-pilot-capture","functionsDir":"functions","entitiesDir":"entities"}' > "$1/base44/config.jsonc"
}
capture() {
  local snapshot="$backup/$1" restore_project="${2:-}"
  make_capture_project "$snapshot"
  ( cd "$snapshot"
    NO_COLOR=1 timeout --kill-after=5s 90 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list > listed.txt 2>&1
    NO_COLOR=1 timeout --kill-after=5s 110 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull > pulled.txt 2>&1
  )
  node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" capture "$snapshot" "$snapshot/listed.txt" "$snapshot/digests.json" ${restore_project:+"$restore_project"}
}
difference() {
  node "$ROOT/scripts/lib/base44-pilot-inventory.mjs" compare "$backup/before/digests.json" "$backup/$1/digests.json"
}

mkdir "$backup/baseline"
git archive "$PUBLIC_BASELINE_SHA" | tar -x -C "$backup/baseline"
[[ "$(node "$backup/baseline/scripts/lib/base44-public-routes.mjs")" == v8\ * ]] || refuse "The current public baseline does not specify V8."
verify_site "$PUBLIC_BASELINE_SHA"
verify_v8
verify_drain
fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
verify_v9 before
fixlist_install_base44_cli "$backup/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$backup/auth" "$APP_ID"
make_capture_project "$backup/restore"
capture before "$backup/restore"

VITE_SCAN_FUNCTION_GENERATION=PUBLISHED_PILOT VITE_BASE44_APP_ID="$APP_ID" VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build
fixlist_require_pinned_checkout "$ROOT" "$SOURCE_SHA"
verify_drain
fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
# Refresh inventory immediately before the upload so the recovery copy cannot
# silently erase route changes from an overlapping publication.
capture before-upload
before_upload_difference="$(difference before-upload)"
[[ -z "$before_upload_difference" ]] || refuse "The function inventory changed before upload."

mutation_started=true
site_status=0
timeout --kill-after=5s 180 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" site deploy --no-build --yes || site_status=$?

# Snapshot reconciliation can change live function packages even when the site
# call returns an error. Restore only routes with different or missing bytes.
capture after-upload
restore_routes="$(difference after-upload)"
if [[ -n "$restore_routes" ]]; then
  named_routes=()
  while IFS= read -r route; do named_routes+=("$route"); done <<< "$restore_routes"
  ( cd "$backup/restore"
    timeout --kill-after=5s 180 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${named_routes[@]}"
  )
  capture after-restore
  after_restore_difference="$(difference after-restore)"
  [[ -z "$after_restore_difference" ]] || refuse "Restored packages did not match the original deployed inventory."
fi
verify_v8
verify_v9 after
verify_drain
fixlist_assert_active_v9_intake_closed "$ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
(( site_status == 0 )) || refuse "The site upload did not report success; function packages were checked."
verify_site "$SOURCE_SHA"
printf 'BASE44_PUBLISHED_PILOT_VERIFIED source_sha=%s baseline_sha=%s admission=closed\n' "$SOURCE_SHA" "$PUBLIC_BASELINE_SHA"
