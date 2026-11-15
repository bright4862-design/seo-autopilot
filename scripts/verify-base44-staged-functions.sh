#!/usr/bin/env bash
# Read-only native SDK probes and separate legacy diagnostics for the V9 candidate.
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
command -v timeout >/dev/null || { echo "Refusing V9 verification: timeout is required." >&2; exit 2; }
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
FUNCTIONS=(startStandardScanJobV9 durableScanWorkerControlV9 persistDurableScanAuthorityV9 persistLimitedScanResultV9 getCustomerScanResultV9 deleteCustomerScanDataV9)
TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
: > "$TASK_TMP/expected.tsv"
for name in "${FUNCTIONS[@]}"; do
  expected="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$name")"
  activation="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$name")"
  if [[ ! "$expected" =~ ^[0-9a-f]{64}$ || ! "$activation" =~ ^[A-Za-z0-9._-]{1,120}$ ]]; then
    echo "V9 local runtime identity is invalid for $name." >&2
    exit 2
  fi
  printf '%s\t%s\t%s\n' "$name" "$expected" "$activation" >> "$TASK_TMP/expected.tsv"
done

fixlist_install_base44_cli "$TASK_TMP/cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TASK_TMP/whoami" "$APP_ID"
{
  printf 'const ownerId = "%s";\nconst ownerEmail = "%s";\n' "$OWNER_ID" "$BASE44_EXPECTED_OWNER"
  printf 'const names = "%s".split(" ");\n' "${FUNCTIONS[*]}"
  cat <<'NODE'
const me = await base44.auth.me();
if (me?.id !== ownerId || me?.role !== "admin" || String(me?.email || "").trim().toLowerCase() !== ownerEmail) {
  throw new Error("unexpected_app_owner");
}
const rows = await Promise.all(names.map(async name => {
  try {
    const result = await base44.functions.fetch("/" + name, {
      method: "GET", cache: "no-store", redirect: "error",
    });
    if (result.url !== "https://getfixlist.base44.app/api/functions/" + name || result.status !== 405) {
      return {name, http_status: result.status};
    }
    const text = await result.text();
    const body = text.length <= 16384 ? JSON.parse(text) : null;
    const build = body?.build_id;
    const activation = body?.runtime_activation_id;
    return {
      name, http_status: result.status,
      build_id: typeof build === "string" && /^[a-f0-9]{64}$/.test(build) ? build : null,
      runtime_activation_id: typeof activation === "string" && /^[A-Za-z0-9._-]{1,120}$/.test(activation) ? activation : null,
    };
  } catch { return {name, http_status: null}; }
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
const verified = expected.map(([name, build_id, runtime_activation_id]) => {
  const matches = rows.filter(row => row?.name === name);
  if (matches.length !== 1 || matches[0].http_status !== 405 || matches[0].build_id !== build_id
      || matches[0].runtime_activation_id !== runtime_activation_id) process.exit(1);
  return {name, build_id, runtime_activation_id, http_status:405};
});
fs.writeFileSync(output, JSON.stringify(verified), {flag:'wx',mode:0o600});
for (const row of verified) console.log(`STAGED_FUNCTION_RUNTIME_VERIFIED name=${row.name} build_id=${row.build_id}`);
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

# The legacy anonymous route may serve older builds. It supplies a diagnostic,
# while the native owner session above supplies the candidate runtime evidence.
: > "$TASK_TMP/anonymous.jsonl"
while IFS=$'\t' read -r name expected activation; do
  status="$(curl -q -sS --proto '=https' --max-time 8 --max-filesize 16384 --header 'Cache-Control: no-cache' \
    -o "$TASK_TMP/anonymous-body.json" -w '%{http_code}' \
    "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null)" || status=000
  node - "$TASK_TMP/anonymous-body.json" "$name" "$expected" "$activation" "$status" "$TASK_TMP/anonymous.jsonl" <<'NODE'
const fs = require('node:fs');
const [input, name, expected, activation, status, output] = process.argv.slice(2);
const http_status = /^[1-5][0-9]{2}$/.test(status) ? Number(status) : null;
let state = 'unavailable';
if (http_status === 405) {
  try {
    const body = JSON.parse(fs.readFileSync(input, 'utf8'));
    if (typeof body?.build_id === 'string' && /^[a-f0-9]{64}$/.test(body.build_id)
        && typeof body?.runtime_activation_id === 'string' && /^[A-Za-z0-9._-]{1,120}$/.test(body.runtime_activation_id)) {
      state = body.build_id === expected && body.runtime_activation_id === activation ? 'matched' : 'stale';
    }
  } catch { /* Retain only the bounded diagnostic state. */ }
}
fs.appendFileSync(output, JSON.stringify({name, http_status, state}) + '\n');
NODE
done < "$TASK_TMP/expected.tsv"

if [[ -n "$PROBE_REPORT" ]]; then
  node - "$TASK_TMP/probes.json" "$TASK_TMP/anonymous.jsonl" "$PROBE_REPORT" "$SOURCE_SHA" "$APP_ID" <<'NODE'
const fs = require('node:fs');
const [input, anonymousPath, output, sourceSha, appId] = process.argv.slice(2);
const functions = JSON.parse(fs.readFileSync(input, 'utf8'));
const anonymous = fs.readFileSync(anonymousPath, 'utf8').trim().split('\n').map(line => JSON.parse(line));
const report = {source_sha:sourceSha, app_id:appId, runtime_probe_transport:'base44_native_authenticated_sdk_get',
  functions, anonymous_probe:{transport:'base44_legacy_anonymous_get', functions:anonymous}};
fs.writeFileSync(output, JSON.stringify(report) + '\n', {flag:'wx',mode:0o600});
NODE
fi
printf 'BASE44_STAGED_V9_RUNTIME_VERIFIED source_sha=%s production_activation=false\n' "$SOURCE_SHA"
