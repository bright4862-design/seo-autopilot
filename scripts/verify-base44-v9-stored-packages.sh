#!/usr/bin/env bash
# Read-only Base44 V9 package parity. This does not publish, deploy, scan,
# change intake, or authenticate the currently serving published runtime.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "$BASH_SOURCE")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"

refuse() { echo "BASE44_V9_READBACK_UNVERIFIED: $*" >&2; exit 2; }
[[ "$APP_ID" == "6a498732ec779dfaaeab0e53" ]] || refuse "unexpected application"
[[ "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ ]] || refuse "exact source SHA required"

source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
cd "$REPO_ROOT"
node scripts/generate_release_contracts.mjs --check >/dev/null || refuse "generated contract drift"
node scripts/base44_release_manifest.mjs verify --staged >/dev/null || refuse "local V9 package integrity failed"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"
fixlist_install_base44_cli "$TMP/pinned-cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID" || refuse "owner authentication unverified"

mkdir -p "$TMP/pulled/base44/functions" "$TMP/pulled/base44/entities"
cat > "$TMP/pulled/base44/config.jsonc" <<'JSON'
{"name":"fixlist-v9-package-readonly","functionsDir":"functions","entitiesDir":"entities"}
JSON

# Pull one explicit name at a time. An empty name list means "all" to the CLI;
# a missing function can also return success, so check every fresh directory.
for name in \
  startStandardScanJobV9 \
  durableScanWorkerControlV9 \
  persistDurableScanAuthorityV9 \
  persistLimitedScanResultV9 \
  getCustomerScanResultV9 \
  deleteCustomerScanDataV9
do
  if ! (cd "$TMP/pulled" && "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull "$name") > "$TMP/pull-$name.log" 2>&1; then
    refuse "read-only pull failed for $name"
  fi
  [[ -f "$TMP/pulled/base44/functions/$name/function.jsonc" ]] || refuse "missing pulled package $name"
done

node --input-type=module - "$REPO_ROOT" "$TMP/pulled/base44/functions" "$SOURCE_SHA" <<'NODE'
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root, pulled, sourceSha] = process.argv.slice(2);
const {buildManifest, STAGED_RELEASE_FUNCTIONS} =
  await import(pathToFileURL(path.join(root, 'scripts/base44_release_manifest.mjs')));
const local = buildManifest(STAGED_RELEASE_FUNCTIONS, path.join(root, 'base44/functions'), []);
const remote = buildManifest(STAGED_RELEASE_FUNCTIONS, pulled, []);
for (const name of STAGED_RELEASE_FUNCTIONS) {
  if (local.functions[name].packageDigest !== remote.functions[name].packageDigest) {
    throw new Error('V9 read-only package drift: ' + name);
  }
}
if (local.functionDigest !== remote.functionDigest) throw new Error('V9 aggregate package digest mismatch');
// This attests backend package pull parity only, never production function
// routing, deployed instance identity, source stamp, or HMAC persistence.
console.log('BASE44_V9_STORED_PACKAGES_MATCHED source_sha=' + sourceSha +
  ' function_count=' + STAGED_RELEASE_FUNCTIONS.length +
  ' runtime_identity=UNVERIFIED published_route=UNVERIFIED');
NODE
