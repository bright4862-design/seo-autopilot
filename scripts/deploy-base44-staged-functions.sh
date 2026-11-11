#!/usr/bin/env bash
# Publish only the isolated V9 candidate packages. This never promotes V8,
# publishes the site, updates entities/secrets, or changes the release-source stamp.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

if [[ "$APP_ID" != "6a498732ec779dfaaeab0e53" || ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Refusing V9 candidate publication: exact repository app identity and SOURCE_SHA are required." >&2
  exit 2
fi
if [[ "$CONFIRM" != "PUBLISH-BASE44-STAGED-V9:$SOURCE_SHA" ]]; then
  echo "Refusing V9 candidate publication: CONFIRM must equal PUBLISH-BASE44-STAGED-V9:<SOURCE_SHA>." >&2
  exit 2
fi
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
cd "$REPO_ROOT"

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
node --input-type=module - "$REPO_ROOT" "${FUNCTIONS[@]}" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root, ...expected] = process.argv.slice(2);
const routes = JSON.parse(fs.readFileSync(path.join(root,'data/base44-function-routes.json'),'utf8'));
const record = JSON.parse(fs.readFileSync(path.join(root,'data/beta-crawler-revision.json'),'utf8'));
const actual = Object.values(routes.candidate_routes?.v9 || {});
if (actual.length !== expected.length || new Set(actual).size !== expected.length || expected.some(name => !actual.includes(name))
    || Object.values(routes.routes || {}).some(name => expected.includes(name))
    || !['candidate','frozen_beta'].includes(record.status) || !/^[0-9a-f]{16}$/.test(record.fingerprint || '')) {
  throw new Error('V9 publication requires an isolated six-function candidate manifest.');
}
NODE
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
node "$REPO_ROOT/scripts/base44_release_manifest.mjs" verify --staged

READINESS_OUTPUT="${READINESS_OUTPUT:-/tmp/fixlist-staged-v9-${SOURCE_SHA}.json}"
if [[ "$READINESS_OUTPUT" != /* || -L "$READINESS_OUTPUT" || -e "$READINESS_OUTPUT" ]]; then
  echo "Refusing V9 readiness artifact: choose a new absolute READINESS_OUTPUT path." >&2
  exit 2
fi
if [[ ! -d "$(dirname "$READINESS_OUTPUT")" || "$READINESS_OUTPUT" == "$REPO_ROOT/"* ]]; then
  echo "Refusing V9 readiness artifact: its existing parent must be outside the source checkout." >&2
  exit 2
fi

TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
chmod 700 "$TASK_TMP"
fixlist_install_base44_cli "$TASK_TMP/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TASK_TMP/whoami" "$APP_ID"

# Naming every function is essential: an empty list means "all", and --force
# would prune other generations. Neither operation belongs in this lane.
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${FUNCTIONS[@]}" > "$TASK_TMP/deploy.log" 2>&1 || {
  echo "V9 candidate function publication failed. No readiness artifact was issued." >&2
  exit 1
}

# The pinned CLI supports one name per pull. Pull into a fresh temporary
# project so a missing route (which can return exit 0) cannot match stale files.
mkdir -p "$TASK_TMP/pulled/base44/functions" "$TASK_TMP/pulled/base44/entities"
cat > "$TASK_TMP/pulled/base44/config.jsonc" <<'JSON'
{"name":"fixlist-staged-readback","functionsDir":"functions","entitiesDir":"entities"}
JSON
for name in "${FUNCTIONS[@]}"; do
  (cd "$TASK_TMP/pulled" && "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull "$name") > "$TASK_TMP/pull-$name.log" 2>&1
  test -f "$TASK_TMP/pulled/base44/functions/$name/function.jsonc" || {
    echo "V9 deployed readback is missing $name." >&2
    exit 1
  }
done
node --input-type=module - "$REPO_ROOT" "$TASK_TMP/pulled/base44/functions" "$TASK_TMP/packages.json" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root, pulled, output] = process.argv.slice(2);
const {buildManifest, STAGED_RELEASE_FUNCTIONS} = await import(pathToFileURL(path.join(root,'scripts/base44_release_manifest.mjs')));
const local = buildManifest(STAGED_RELEASE_FUNCTIONS,path.join(root,'base44/functions'),[]);
const remote = buildManifest(STAGED_RELEASE_FUNCTIONS,pulled,[]);
for (const name of STAGED_RELEASE_FUNCTIONS) {
  if (local.functions[name].packageDigest !== remote.functions[name].packageDigest) throw new Error(`V9 deployed package differs: ${name}`);
}
fs.writeFileSync(output,JSON.stringify(Object.fromEntries(STAGED_RELEASE_FUNCTIONS.map(name => [name,local.functions[name].packageDigest]))));
NODE

SOURCE_SHA="$SOURCE_SHA" BASE44_APP_ID="$APP_ID" PROBE_REPORT="$TASK_TMP/runtime.json" \
  bash "$REPO_ROOT/scripts/verify-base44-staged-functions.sh"

node --input-type=module - "$REPO_ROOT" "$SOURCE_SHA" "$APP_ID" "$TASK_TMP/packages.json" "$TASK_TMP/runtime.json" "$READINESS_OUTPUT" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root,sourceSha,appId,packagesPath,runtimePath,output] = process.argv.slice(2);
const revision = JSON.parse(fs.readFileSync(path.join(root,'data/beta-crawler-revision.json'),'utf8'));
const probes = JSON.parse(fs.readFileSync(runtimePath,'utf8'));
const packages = JSON.parse(fs.readFileSync(packagesPath,'utf8'));
if (probes.source_sha !== sourceSha || probes.app_id !== appId || probes.functions.length !== 6) throw new Error('V9 runtime verification identity mismatch');
const result = {schema_version:'fixlist_staged_v9_readiness_v1',source_sha:sourceSha,app_id:appId,candidate_fingerprint:revision.fingerprint,
  package_comparison:'matched',runtime_probe:'matched',production_activation:false,observed_at:new Date().toISOString(),
  functions:probes.functions.map(row => ({...row,package_digest:packages[row.name]}))};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
NODE
printf 'BASE44_STAGED_V9_CANDIDATE_VERIFIED source_sha=%s readiness=%s production_activation=false\n' "$SOURCE_SHA" "$READINESS_OUTPUT"
