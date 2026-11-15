#!/usr/bin/env bash
# Read-only probes for the authenticated and external V9 candidate runtimes.
set -euo pipefail
umask 077
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-12}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
PROBE_REPORT="${PROBE_REPORT:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
if [[ "$APP_ID" != "6a498732ec779dfaaeab0e53" || ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ \
  || ! "$PROBE_ATTEMPTS" =~ ^[1-9][0-9]*$ || "$PROBE_ATTEMPTS" -gt 60 \
  || ! "$PROBE_DELAY_SECONDS" =~ ^[0-9]+$ || "$PROBE_DELAY_SECONDS" -gt 60 ]]; then
  echo "Refusing V9 verification: invalid app, source, or bounded probe settings." >&2
  exit 2
fi
if [[ "$PROBE_ORIGIN" != "https://base44.app" ]]; then
  echo "Refusing V9 verification: BASE44_FUNCTION_ORIGIN must be https://base44.app." >&2
  exit 2
fi
case "$BASE44_EXPECTED_OWNER" in
  bright4862@gmail.com) OWNER_ID=6a498da58ef5cec1f5cd4486 ;;
  londonparisbrussels@gmail.com) OWNER_ID=6a498732ec779dfaaeab0e54 ;;
  *) echo "Refusing V9 verification: select an approved Base44 owner session." >&2; exit 2 ;;
esac
if [[ -n "${BASE44_API_KEY:-}" ]]; then
  echo 'Refusing V9 verification: an authenticated Base44 owner session is required.' >&2
  exit 2
fi
command -v timeout >/dev/null || { echo "Refusing V9 verification: timeout is required." >&2; exit 2; }
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
FUNCTIONS=(startStandardScanJobV9 durableScanWorkerControlV9 persistDurableScanAuthorityV9 persistLimitedScanResultV9 getCustomerScanResultV9 deleteCustomerScanDataV9)
TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
node - "$REPO_ROOT/data/generated-staged-v9-routes.json" "$TASK_TMP/expected.tsv" "$TASK_TMP/native-routes.json" "${FUNCTIONS[@]}" <<'NODE'
const fs = require('node:fs');
const [manifest, tsv, native, ...expected] = process.argv.slice(2);
const {schema_version, functions} = JSON.parse(fs.readFileSync(manifest, 'utf8'));
if (schema_version !== 'fixlist_staged_v9_routes_v1' || Object.keys(functions ?? {}).length !== expected.length) {
  throw new Error('Invalid V9 candidate alias manifest');
}
const rows = expected.map(name => {
  const {route_name, build_id, runtime_activation_id} = functions[name] ?? {};
  if (typeof route_name !== 'string' || route_name.length > 63 || !new RegExp(`^${name}B[0-9a-f]{16}$`).test(route_name)
      || !/^[a-f0-9]{64}$/.test(build_id ?? '') || !/^[A-Za-z0-9._-]{1,120}$/.test(runtime_activation_id ?? '')) {
    throw new Error(`Invalid V9 candidate alias identity for ${name}`);
  }
  return {name, route_name, build_id, runtime_activation_id};
});
fs.writeFileSync(tsv, rows.map(row => Object.values(row).join('\t')).join('\n') + '\n');
fs.writeFileSync(native, JSON.stringify(rows.map(row => row.route_name)));
NODE

fixlist_install_base44_cli "$TASK_TMP/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TASK_TMP/whoami" "$APP_ID"
{
  printf 'const ownerId = "%s";\nconst ownerEmail = "%s";\n' "$OWNER_ID" "$BASE44_EXPECTED_OWNER"
  printf 'const routes = %s;\n' "$(< "$TASK_TMP/native-routes.json")"
  cat <<'NODE'
const me = await base44.auth.me();
if (me?.id !== ownerId || me?.role !== "admin" || String(me?.email || "").trim().toLowerCase() !== ownerEmail) {
  throw new Error("unexpected_app_owner");
}
const rows = await Promise.all(routes.map(async route_name => {
  try {
    const result = await base44.functions.fetch("/" + route_name, {
      method: "GET", cache: "no-store", redirect: "error",
    });
    if (result.url !== "https://getfixlist.base44.app/api/functions/" + route_name || result.status !== 405) {
      return {route_name, http_status: result.status};
    }
    const text = await result.text();
    const body = text.length <= 16384 ? JSON.parse(text) : null;
    const build = body?.build_id;
    const activation = body?.runtime_activation_id;
    return {
      route_name, http_status: result.status,
      build_id: typeof build === "string" && /^[a-f0-9]{64}$/.test(build) ? build : null,
      runtime_activation_id: typeof activation === "string" && /^[A-Za-z0-9._-]{1,120}$/.test(activation) ? activation : null,
    };
  } catch { return {route_name, http_status: null}; }
}));
console.log("FIXLIST_V9_NATIVE_GET=" + JSON.stringify(rows));
NODE
} > "$TASK_TMP/native.js"

verified=""
for (( attempt=1; attempt<=PROBE_ATTEMPTS; attempt++ )); do
  if timeout --signal=TERM --kill-after=5s 25 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
      < "$TASK_TMP/native.js" > "$TASK_TMP/native.out" 2> "$TASK_TMP/native.err" \
    && node - "$TASK_TMP/native.out" "$TASK_TMP/expected.tsv" "$TASK_TMP/probes.json" <<'NODE'
const fs = require('node:fs');
const [input, expectedPath, output] = process.argv.slice(2);
const prefix = 'FIXLIST_V9_NATIVE_GET=';
if (fs.statSync(input).size > 65536) process.exit(1);
const lines = fs.readFileSync(input, 'utf8').split('\n').filter(line => line.startsWith(prefix));
if (lines.length !== 1) process.exit(1);
let rows;
try { rows = JSON.parse(lines[0].slice(prefix.length)); } catch { process.exit(1); }
const expected = fs.readFileSync(expectedPath, 'utf8').trim().split('\n').map(line => line.split('\t'));
if (!Array.isArray(rows) || rows.length !== expected.length) process.exit(1);
const verified = expected.map(([name, route_name, build_id, runtime_activation_id]) => {
  const matches = rows.filter(row => row?.route_name === route_name);
  if (matches.length !== 1 || matches[0].http_status !== 405 || matches[0].build_id !== build_id
      || matches[0].runtime_activation_id !== runtime_activation_id) process.exit(1);
  return {name, route_name, build_id, runtime_activation_id, http_status:405};
});
fs.writeFileSync(output, JSON.stringify(verified), {flag:'wx',mode:0o600});
NODE
  then
    verified=yes
    break
  fi
  if (( attempt < PROBE_ATTEMPTS )); then sleep "$PROBE_DELAY_SECONDS"; fi
done
if [[ -z "$verified" ]]; then
  echo 'V9 native authenticated runtime identities could not be verified.' >&2
  exit 1
fi

# Confirm exact markers on the public route the worker actually calls. This
# GET attests the deployed handler identity. Signed POST is verified separately.
probe_external() {
  local route="$1" status
  rm -f "$TASK_TMP/$route.body"
  status="$(curl -q -sS --proto '=https' --max-time 8 --max-filesize 16384 --header 'Cache-Control: no-cache' \
    -o "$TASK_TMP/$route.body" -w '%{http_code}' \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$route" 2>/dev/null)" || status=000
  printf '%s\n' "$status" > "$TASK_TMP/$route.status"
}

verified=""
for (( attempt=1; attempt<=PROBE_ATTEMPTS; attempt++ )); do
  while IFS=$'\t' read -r name route expected activation; do
    probe_external "$route" &
  done < "$TASK_TMP/expected.tsv"
  wait
  if node - "$TASK_TMP" "$TASK_TMP/expected.tsv" "$TASK_TMP/anonymous.json" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const [directory, expectedPath, output] = process.argv.slice(2);
const expected = fs.readFileSync(expectedPath, 'utf8').trim().split('\n').map(line => line.split('\t'));
let verified;
try {
  verified = expected.map(([name, route_name, build_id, runtime_activation_id]) => {
    const status = fs.readFileSync(path.join(directory, route_name + '.status'), 'utf8').trim();
    const body = JSON.parse(fs.readFileSync(path.join(directory, route_name + '.body'), 'utf8'));
    if (status !== '405' || body?.build_id !== build_id || body?.runtime_activation_id !== runtime_activation_id) process.exit(1);
    return {name, route_name, build_id, runtime_activation_id, http_status:405, state:'matched'};
  });
} catch {
  process.exit(1);
}
fs.writeFileSync(output, JSON.stringify(verified), {flag:'wx',mode:0o600});
for (const row of verified) console.log(`STAGED_FUNCTION_RUNTIME_VERIFIED name=${row.name} route_name=${row.route_name} build_id=${row.build_id}`);
NODE
  then
    verified=yes
    break
  fi
  if (( attempt < PROBE_ATTEMPTS )); then sleep "$PROBE_DELAY_SECONDS"; fi
done
if [[ -z "$verified" ]]; then
  echo 'V9 external runtime identities could not be verified.' >&2
  exit 1
fi

if [[ -n "$PROBE_REPORT" ]]; then
  node - "$TASK_TMP/probes.json" "$TASK_TMP/anonymous.json" "$PROBE_REPORT" "$SOURCE_SHA" "$APP_ID" <<'NODE'
const fs = require('node:fs');
const [input, anonymousPath, output, sourceSha, appId] = process.argv.slice(2);
const functions = JSON.parse(fs.readFileSync(input, 'utf8'));
const anonymous = JSON.parse(fs.readFileSync(anonymousPath, 'utf8'));
const report = {source_sha:sourceSha, app_id:appId, runtime_probe_transport:'base44_native_authenticated_sdk_get',
  functions, anonymous_probe:{transport:'base44_legacy_anonymous_get', functions:anonymous}};
fs.writeFileSync(output, JSON.stringify(report) + '\n', {flag:'wx',mode:0o600});
NODE
fi
printf 'BASE44_STAGED_V9_RUNTIME_VERIFIED source_sha=%s production_activation=false\n' "$SOURCE_SHA"
