#!/usr/bin/env bash
# Publish or verify the content-addressed V9 packages from the selected source.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
OPERATION="${1:-publish}"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

if [[ "$APP_ID" != "6a498732ec779dfaaeab0e53" || ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Refusing V9 candidate publication: exact repository app identity and SOURCE_SHA are required." >&2
  exit 2
fi
if (( $# > 1 )); then
  echo 'Usage: deploy-base44-staged-functions.sh [verify|publish-active]' >&2
  exit 2
fi
case "$OPERATION" in
  publish) EXPECTED_CONFIRM="PUBLISH-BASE44-STAGED-V9:$SOURCE_SHA" ;;
  verify) EXPECTED_CONFIRM="VERIFY-BASE44-STAGED-V9:$SOURCE_SHA" ;;
  publish-active) EXPECTED_CONFIRM="PUBLISH-BASE44-ACTIVE-V9:$SOURCE_SHA" ;;
  *) echo 'Unsupported staged V9 operation.' >&2; exit 2 ;;
esac
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing V9 candidate operation: exact $EXPECTED_CONFIRM required." >&2
  exit 2
fi
command -v timeout >/dev/null || { echo "Refusing V9 candidate operation: timeout is required." >&2; exit 2; }
case "$BASE44_EXPECTED_OWNER" in
  bright4862@gmail.com|londonparisbrussels@gmail.com) ;;
  *) echo 'Refusing V9 candidate operation: select an approved Base44 owner session.' >&2; exit 2 ;;
esac
if [[ -n "${BASE44_API_KEY:-}" ]]; then
  echo 'Refusing V9 candidate operation: an authenticated Base44 owner session is required.' >&2
  exit 2
fi
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
cd "$REPO_ROOT"
if [[ "$OPERATION" == publish-active ]]; then
  python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"
  ROUTE_SELECTION="$(node "$REPO_ROOT/scripts/lib/base44-public-routes.mjs")"
  [[ "$ROUTE_SELECTION" == v9\ * ]] || { echo 'Active V9 publication requires the public V9 manifest.' >&2; exit 2; }
fi

FUNCTIONS=(
  startStandardScanJobV9
  durableScanWorkerControlV9
  persistDurableScanAuthorityV9
  persistLimitedScanResultV9
  getCustomerScanResultV9
  deleteCustomerScanDataV9
)
# Candidate permission is restricted to these unreferenced function names. The
# ordinary V8 publisher retains its separate production acceptance guard.
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify --staged

TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
chmod 700 "$TASK_TMP"
node --input-type=module - "$REPO_ROOT" "$TASK_TMP/routes.tsv" "$OPERATION" "${FUNCTIONS[@]}" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root, output, operation, ...expected] = process.argv.slice(2);
const routes = JSON.parse(fs.readFileSync(path.join(root,'data/base44-function-routes.json'),'utf8'));
const record = JSON.parse(fs.readFileSync(path.join(root,'data/beta-crawler-revision.json'),'utf8'));
const generated = JSON.parse(fs.readFileSync(path.join(root,'data/generated-staged-v9-routes.json'),'utf8'));
const active = operation === 'publish-active';
const actual = Object.values((active ? routes.routes : routes.candidate_routes?.v9) || {});
const occupied = new Set([
  ...Object.values(routes.routes || {}),
  ...Object.values(routes.historical_routes || {}).flatMap(Object.values),
  ...actual,
]);
if (actual.length !== expected.length || new Set(actual).size !== expected.length || expected.some(name => !actual.includes(name))
    || (!active && (routes.generation !== 'v8' || Object.values(routes.routes || {}).some(name => expected.includes(name))))
    || !['candidate','frozen_beta'].includes(record.status) || !/^[0-9a-f]{16}$/.test(record.fingerprint || '')
    || generated.schema_version !== 'fixlist_staged_v9_routes_v1'
    || Object.keys(generated.functions ?? {}).length !== expected.length) {
  throw new Error('V9 publication does not match its selected six-function manifest.');
}
const aliases = expected.map(name => {
  const row = generated.functions[name];
  if (!row || typeof row.route_name !== 'string' || row.route_name.length > 63
      || !new RegExp(`^${name}B[0-9a-f]{16}$`).test(row.route_name) || occupied.has(row.route_name)
      || !/^[a-f0-9]{64}$/.test(row.package_digest ?? '')) {
    throw new Error(`V9 candidate alias is invalid for ${name}.`);
  }
  occupied.add(row.route_name);
  return `${name}\t${row.route_name}\n`;
});
fs.writeFileSync(output, aliases.join(''));
NODE

READINESS_OUTPUT="${READINESS_OUTPUT:-/tmp/fixlist-staged-v9-${SOURCE_SHA}.json}"
if [[ "$READINESS_OUTPUT" != /* || -L "$READINESS_OUTPUT" || -e "$READINESS_OUTPUT" ]]; then
  echo "Refusing V9 readiness artifact: choose a new absolute READINESS_OUTPUT path." >&2
  exit 2
fi
if [[ ! -d "$(dirname "$READINESS_OUTPUT")" || "$READINESS_OUTPUT" == "$REPO_ROOT/"* ]]; then
  echo "Refusing V9 readiness artifact: its existing parent must be outside the source checkout." >&2
  exit 2
fi

node "$REPO_ROOT/scripts/materialize-base44-staged-functions.mjs" "$TASK_TMP/candidate"
fixlist_install_base44_cli "$TASK_TMP/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TASK_TMP/whoami" "$APP_ID"

make_readback_project() {
  mkdir -p "$1/base44/functions" "$1/base44/entities"
  cat > "$1/base44/config.jsonc" <<'JSON'
{"name":"fixlist-staged-readback","functionsDir":"functions","entitiesDir":"entities"}
JSON
}

pull_route() {
  local project="$1" route="$2" log="$1/$2.log"
  if ! (cd "$project" && NO_COLOR=1 timeout --signal=TERM --kill-after=5s 60 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull "$route") > "$log" 2>&1; then
    echo "V9 package readback failed for $route." >&2
    return 1
  fi
}

unregistered_alias() {
  local project="$1" route="$2"
  # A targeted pull may return success for a missing function. Require the
  # pinned CLI's explicit missing result, as well as a fresh empty destination.
  [[ ! -e "$project/base44/functions/$route" && ! -L "$project/base44/functions/$route" ]] &&
    grep -Fq "Function \"$route\" not found on remote" "$project/$route.log"
}

assert_pulled_package() {
  node --input-type=module - "$REPO_ROOT" "$TASK_TMP/candidate" "$@" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root, candidate, pulled, name, route] = process.argv.slice(2);
const { assertPulledFunctionPackage } = await import(pathToFileURL(path.join(root,'scripts/base44_release_manifest.mjs')));
const generated = JSON.parse(fs.readFileSync(path.join(root,'data/generated-staged-v9-routes.json'),'utf8'));
const localDir = path.join(candidate,'base44/functions',route);
const pulledDir = path.join(pulled,'base44/functions',route);
const pulledConfig = path.join(pulledDir,'function.jsonc');
// CLI 0.1.8 generates flat function.jsonc without a trailing newline. Restore
// the source newline in the scratch copy only when the rest is byte-identical.
if (!fs.lstatSync(path.join(pulledDir,'base44'), {throwIfNoEntry:false})
    && fs.lstatSync(pulledConfig, {throwIfNoEntry:false})?.isFile()) {
  const config = fs.readFileSync(path.join(localDir,'function.jsonc'));
  if (config.at(-1) === 10 && fs.readFileSync(pulledConfig).equals(config.subarray(0,-1))) {
    fs.writeFileSync(pulledConfig, config);
  }
}
const digest = assertPulledFunctionPackage(route, localDir, pulledDir);
if (digest !== generated.functions[name].package_digest) throw new Error(`Unexpected package digest for ${route}`);
console.log(digest);
NODE
}

assert_public_alias_absent() {
  local route="$1" status
  status="$(curl -q -sS --proto '=https' --max-time 8 --max-filesize 16384 --header 'Cache-Control: no-cache' \
    -o /dev/null -w '%{http_code}' "https://base44.app/api/apps/$APP_ID/functions/$route" 2>/dev/null)" || status=000
  if [[ "$status" != 404 ]]; then
    echo "V9 public alias absence could not be proven for $route (HTTP $status)." >&2
    return 1
  fi
}

make_readback_project "$TASK_TMP/preflight"
: > "$TASK_TMP/packages.tsv"
: > "$TASK_TMP/create.tsv"
while IFS=$'\t' read -r name route; do
  pull_route "$TASK_TMP/preflight" "$route"
  if unregistered_alias "$TASK_TMP/preflight" "$route"; then
    if [[ "$OPERATION" == verify ]]; then
      echo "V9 deployed readback is missing $route." >&2
      exit 1
    fi
    assert_public_alias_absent "$route"
    printf '%s\t%s\n' "$name" "$route" >> "$TASK_TMP/create.tsv"
  else
    digest="$(assert_pulled_package "$TASK_TMP/preflight" "$name" "$route")"
    printf '%s\t%s\n' "$name" "$digest" >> "$TASK_TMP/packages.tsv"
  fi
done < "$TASK_TMP/routes.tsv"

# Finish the entire collision preflight before the first creation; an existing
# matching alias is reused. Recheck each absent alias immediately before deploy.
make_readback_project "$TASK_TMP/recheck"
make_readback_project "$TASK_TMP/deployed"
while IFS=$'\t' read -r name route; do
  pull_route "$TASK_TMP/recheck" "$route"
  if unregistered_alias "$TASK_TMP/recheck" "$route"; then
    assert_public_alias_absent "$route"
    if ! (cd "$TASK_TMP/candidate" && timeout --signal=TERM --kill-after=5s 120 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "$route") > "$TASK_TMP/deploy-$route.log" 2>&1; then
      echo "V9 candidate function publication failed for $route." >&2
      exit 1
    fi
    pull_route "$TASK_TMP/deployed" "$route"
    digest="$(assert_pulled_package "$TASK_TMP/deployed" "$name" "$route")"
  else
    digest="$(assert_pulled_package "$TASK_TMP/recheck" "$name" "$route")"
  fi
  printf '%s\t%s\n' "$name" "$digest" >> "$TASK_TMP/packages.tsv"
done < "$TASK_TMP/create.tsv"

SOURCE_SHA="$SOURCE_SHA" BASE44_APP_ID="$APP_ID" BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" PROBE_REPORT="$TASK_TMP/runtime.json" \
  bash "$REPO_ROOT/scripts/verify-base44-staged-functions.sh"

node --input-type=module - "$REPO_ROOT" "$SOURCE_SHA" "$APP_ID" "$TASK_TMP/packages.tsv" "$TASK_TMP/runtime.json" "$READINESS_OUTPUT" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root,sourceSha,appId,packagesPath,runtimePath,output] = process.argv.slice(2);
const revision = JSON.parse(fs.readFileSync(path.join(root,'data/beta-crawler-revision.json'),'utf8'));
const probes = JSON.parse(fs.readFileSync(runtimePath,'utf8'));
const entries = fs.readFileSync(packagesPath,'utf8').trim().split('\n').map(row => row.split('\t'));
const packages = new Map(entries);
const { functions: expected } = JSON.parse(fs.readFileSync(path.join(root,'data/generated-staged-v9-routes.json'),'utf8'));
function matches(row) {
  const identity = expected[row.name];
  return identity && row.route_name === identity.route_name && row.build_id === identity.build_id
    && row.runtime_activation_id === identity.runtime_activation_id && row.http_status === 405;
}
if (probes.source_sha !== sourceSha || probes.app_id !== appId
    || probes.runtime_probe_transport !== 'base44_native_authenticated_sdk_get'
    || entries.length !== 6 || packages.size !== 6
    || probes.functions.length !== 6 || new Set(probes.functions.map(row => row.name)).size !== 6
    || probes.functions.some(row => !matches(row) || packages.get(row.name) !== expected[row.name].package_digest)
    || probes.anonymous_probe?.transport !== 'base44_legacy_anonymous_get'
    || probes.anonymous_probe.functions.length !== 6
    || new Set(probes.anonymous_probe.functions.map(row => row.name)).size !== 6
    || probes.anonymous_probe.functions.some(row => !matches(row) || row.state !== 'matched')) throw new Error('V9 runtime verification identity mismatch');
const result = {schema_version:'fixlist_staged_v9_readiness_v2',source_sha:sourceSha,app_id:appId,candidate_fingerprint:revision.fingerprint,
  package_comparison:'matched',runtime_probe:'matched',runtime_probe_transport:probes.runtime_probe_transport,
  anonymous_probe:probes.anonymous_probe,worker_signed_post_runtime_verified:false,production_activation:false,
  observed_at:new Date().toISOString(),
  functions:probes.functions.map(row => ({...row,package_digest:packages.get(row.name)}))};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
NODE
if [[ "$OPERATION" == publish-active ]]; then
  printf 'BASE44_ACTIVE_V9_PACKAGES_VERIFIED source_sha=%s\n' "$SOURCE_SHA"
else
  printf 'BASE44_STAGED_V9_CANDIDATE_VERIFIED source_sha=%s readiness=%s production_activation=false\n' "$SOURCE_SHA" "$READINESS_OUTPUT"
fi
