#!/usr/bin/env bash
# Publish or verify the content-addressed V9 packages from the selected source.
fixlist_assert_active_v9_intake_closed() (
  set -euo pipefail
  local root="$1" app="$2" owner="$3" mode="${4:-launcher}" tmp expected marker
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  umask 077
  expected="$(node - "$root" "$owner" "$mode" <<'NODE'
const [root, email, mode] = process.argv.slice(2);
const path = require('node:path');
const {fingerprint} = require(path.join(root, 'data/beta-crawler-revision.json'));
const {functions} = require(path.join(root, 'data/generated-staged-v9-routes.json'));
const ids = {'bright4862@gmail.com':'6a498da58ef5cec1f5cd4486', 'londonparisbrussels@gmail.com':'6a498732ec779dfaaeab0e54'};
if (!Object.hasOwn(ids, email) || !['launcher', 'operator'].includes(mode)) process.exit(1);
console.log(JSON.stringify({email, id: ids[email], mode, fingerprint, ...functions.startStandardScanJobV9}));
NODE
)"
  marker=BASE44_ACTIVE_V9_INTAKE_DISABLED
  if [[ "$mode" == operator ]]; then marker=BASE44_INDEPENDENT_SCAN_INTAKE_DISABLED; fi
  {
    printf 'const expected = %s;\n' "$expected"
    printf 'const proofMarker = "%s";\n' "$marker"
    cat <<'NODE'
const me = await base44.auth.me();
if (me?.id !== expected.id || String(me.email || '').trim().toLowerCase() !== expected.email || me.role !== 'admin') {
  throw new Error('unexpected_app_owner');
}
const operator = expected.mode === 'operator';
const response = await base44.functions.invoke(operator ? 'fixlistStagedRuntimeControl' : expected.route_name,
  {action: operator ? 'status' : 'staged_runtime_status'});
const status = response?.data ?? response;
if (status?.success !== true || status.intake_gate !== 'disabled') throw new Error('intake_not_verified_closed');
if (operator) {
  if (status.schema_version !== 'fixlist_staged_runtime_readback_v1' || status.operator_build_id !== 'fixlist-staged-runtime-control-v1'
      || status.intake_disabled_verified !== true || status.new_owner_intake_disabled !== true
      || status.v9_runtime_attested !== false) throw new Error('invalid_independent_intake_readback');
} else {
  const age = Date.now() - Date.parse(status.observed_at);
  if (status.schema_version !== 'fixlist_staged_v9_intake_readback_v1' || status.build_id !== expected.build_id
      || status.runtime_activation_id !== expected.runtime_activation_id || status.release_fingerprint !== expected.fingerprint
      || !Number.isFinite(age) || Math.abs(age) > 60000) throw new Error('invalid_launcher_intake_readback');
}
console.log(proofMarker);
NODE
  } > "$tmp/intake.js"
  # Deno can materialize its SDK under the current node_modules during exec.
  # Keep the authenticated probe in its own package scope.
  printf '{"private":true}\n' > "$tmp/package.json"
  if ! (cd "$tmp" && timeout --signal=TERM --kill-after=5s 25 "$FIXLIST_BASE44_CLI" --app-id "$app" exec --data-env prod) \
      < "$tmp/intake.js" > "$tmp/intake.out" 2> "$tmp/intake.err" \
      || [[ "$(grep -Fxc "$marker" "$tmp/intake.out")" != 1 ]]; then
    if [[ "$mode" == operator ]]; then
      echo 'Refusing V9 recovery: the independent owner probe does not attest closed intake.' >&2
    else
      echo 'Refusing active V9 publication: the exact launcher does not attest closed intake.' >&2
    fi
    exit 2
  fi
  printf '%s\n' "$marker"
)

fixlist_publish_v9_packages() (
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
  echo 'Usage: deploy-base44-staged-functions.sh [verify|recover-active]' >&2
  exit 2
fi
ACTIVE=false
case "$OPERATION" in
  publish) EXPECTED_CONFIRM="PUBLISH-BASE44-STAGED-V9:$SOURCE_SHA" ;;
  verify) EXPECTED_CONFIRM="VERIFY-BASE44-STAGED-V9:$SOURCE_SHA" ;;
  verify-pinned) EXPECTED_CONFIRM="VERIFY-PINNED-BASE44-STAGED-V9:$SOURCE_SHA" ;;
  active-preflight|active-restore) ACTIVE=true; EXPECTED_CONFIRM="PUBLISH-BASE44-ACTIVE-V9:$SOURCE_SHA" ;;
  recover-active) ACTIVE=true; EXPECTED_CONFIRM="RECOVER-BASE44-ACTIVE-V9:$SOURCE_SHA" ;;
  *) echo 'Unsupported staged V9 operation.' >&2; exit 2 ;;
esac
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing V9 candidate operation: exact $EXPECTED_CONFIRM required." >&2
  exit 2
fi
timeout --signal=TERM --kill-after=5s 1 true >/dev/null 2>&1 || {
  echo 'Refusing V9 publication: a GNU-compatible timeout is required.' >&2; exit 2;
}
case "$BASE44_EXPECTED_OWNER" in
  bright4862@gmail.com|londonparisbrussels@gmail.com) ;;
  *) echo 'Refusing V9 candidate operation: select an approved Base44 owner session.' >&2; exit 2 ;;
esac
if [[ -n "${BASE44_API_KEY:-}" ]]; then
  echo 'Refusing V9 candidate operation: an authenticated Base44 owner session is required.' >&2
  exit 2
fi
cd "$REPO_ROOT"
if [[ "$OPERATION" == verify-pinned ]]; then
  fixlist_require_pinned_checkout "$REPO_ROOT" "$SOURCE_SHA"
elif [[ "$OPERATION" == recover-active || "$ACTIVE" == false ]]; then
  fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
fi
if [[ "$ACTIVE" == true ]]; then
  [[ "${BASE44_FUNCTION_ORIGIN:-https://base44.app}" == "https://base44.app" ]] || {
    echo 'Refusing active V9 operation: the Base44 origin must match.' >&2; exit 2;
  }
  fixlist_require_pinned_checkout "$REPO_ROOT" "$SOURCE_SHA"
  PROMOTION_SCOPE=scanner-functions
  if [[ "$OPERATION" == recover-active ]]; then PROMOTION_SCOPE=recover-functions; fi
  python3 "$REPO_ROOT/scripts/assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA" --base44-v9 "$PROMOTION_SCOPE"
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
const active = operation.startsWith('active-') || operation === 'recover-active';
const actual = Object.values((active ? routes.routes : routes.candidate_routes?.v9) || {});
const occupied = new Set([
  ...Object.values(routes.routes || {}),
  ...Object.values(routes.historical_routes || {}).flatMap(Object.values),
  ...actual,
]);
if (actual.length !== expected.length || new Set(actual).size !== expected.length || expected.some(name => !actual.includes(name))
    || (!active && (routes.generation !== 'v8' || Object.values(routes.routes || {}).some(name => expected.includes(name))))
    || !(active ? record.status === 'frozen_beta' : ['candidate','frozen_beta'].includes(record.status))
    || !/^[0-9a-f]{16}$/.test(record.fingerprint || '')
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
const operator = name === 'fixlistStagedRuntimeControl' && route === name;
const localDir = path.join(operator ? root : candidate,'base44/functions',route);
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
if (!operator && digest !== generated.functions[name].package_digest) throw new Error(`Unexpected package digest for ${route}`);
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
    if [[ "$OPERATION" == verify || "$OPERATION" == verify-pinned ]]; then
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

if [[ "$OPERATION" == recover-active ]] && grep -q $'^startStandardScanJobV9\t' "$TASK_TMP/create.tsv"; then
  probe=fixlistStagedRuntimeControl
  make_readback_project "$TASK_TMP/independent"
  pull_route "$TASK_TMP/independent" "$probe"
  if ! assert_pulled_package "$TASK_TMP/independent" "$probe" "$probe" > "$TASK_TMP/independent.digest"; then
    echo 'Refusing V9 recovery: the independent owner probe package is missing or does not match.' >&2
    exit 2
  fi
  fixlist_assert_active_v9_intake_closed "$REPO_ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER" operator
elif [[ "$OPERATION" == active-preflight || "$OPERATION" == recover-active ]]; then
  fixlist_assert_active_v9_intake_closed "$REPO_ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
fi

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

if [[ "$ACTIVE" == true || "$OPERATION" == verify-pinned ]]; then
  source "$REPO_ROOT/scripts/verify-base44-staged-functions.sh"
  SOURCE_SHA="$SOURCE_SHA" BASE44_APP_ID="$APP_ID" BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" PROBE_REPORT="$TASK_TMP/runtime.json" \
    fixlist_verify_staged_functions pinned
else
  SOURCE_SHA="$SOURCE_SHA" BASE44_APP_ID="$APP_ID" BASE44_EXPECTED_OWNER="$BASE44_EXPECTED_OWNER" PROBE_REPORT="$TASK_TMP/runtime.json" \
    bash "$REPO_ROOT/scripts/verify-base44-staged-functions.sh"
fi

if [[ "$OPERATION" == recover-active ]]; then
  fixlist_assert_active_v9_intake_closed "$REPO_ROOT" "$APP_ID" "$BASE44_EXPECTED_OWNER"
fi

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
if [[ "$OPERATION" == recover-active ]]; then
  printf 'BASE44_ACTIVE_V9_PACKAGES_RECOVERED source_sha=%s readiness=%s\n' "$SOURCE_SHA" "$READINESS_OUTPUT"
elif [[ "$ACTIVE" == true ]]; then
  printf 'BASE44_ACTIVE_V9_PACKAGES_VERIFIED source_sha=%s\n' "$SOURCE_SHA"
else
  printf 'BASE44_STAGED_V9_CANDIDATE_VERIFIED source_sha=%s readiness=%s production_activation=false\n' "$SOURCE_SHA" "$READINESS_OUTPUT"
fi
)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-publish}" in
    publish|verify|recover-active) fixlist_publish_v9_packages "$@" ;;
    *) echo 'Unsupported staged V9 operation.' >&2; exit 2 ;;
  esac
fi
