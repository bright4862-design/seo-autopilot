#!/usr/bin/env bash
# Read-only probes for the six isolated V9 candidate routes.
set -euo pipefail
umask 077
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-12}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
PROBE_REPORT="${PROBE_REPORT:-}"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
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
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --check
FUNCTIONS=(startStandardScanJobV9 durableScanWorkerControlV9 persistDurableScanAuthorityV9 persistLimitedScanResultV9 getCustomerScanResultV9 deleteCustomerScanDataV9)
TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
: > "$TASK_TMP/probes.jsonl"
for name in "${FUNCTIONS[@]}"; do
  expected="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$name")"
  activation="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$name")"
  if [[ ! "$expected" =~ ^[0-9a-f]{64}$ || ! "$activation" =~ ^[A-Za-z0-9._-]{1,120}$ ]]; then
    echo "V9 local runtime identity is invalid for $name." >&2
    exit 2
  fi
  verified=""
  for (( attempt=1; attempt<=PROBE_ATTEMPTS; attempt++ )); do
    status="$(curl -sS --proto '=https' --max-time 25 --max-filesize 16384 \
      -o "$TASK_TMP/body.json" -w '%{http_code}' \
      "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
    if [[ "$status" == "405" ]] && node - "$TASK_TMP/body.json" "$name" "$expected" "$activation" "$TASK_TMP/probes.jsonl" <<'NODE'
const fs = require('node:fs');
const [file,name,expected,activation,output] = process.argv.slice(2);
let body;
try { body = JSON.parse(fs.readFileSync(file,'utf8')); } catch { process.exit(1); }
if (!body || typeof body !== 'object' || Array.isArray(body) || body.build_id !== expected || body.runtime_activation_id !== activation) process.exit(1);
fs.appendFileSync(output,JSON.stringify({name,build_id:expected,runtime_activation_id:activation,http_status:405})+'\n');
NODE
    then
      printf 'STAGED_FUNCTION_RUNTIME_VERIFIED name=%s build_id=%s\n' "$name" "$expected"
      verified=yes
      break
    fi
    if (( attempt < PROBE_ATTEMPTS )); then sleep "$PROBE_DELAY_SECONDS"; fi
  done
  if [[ -z "$verified" ]]; then
    echo "V9 runtime identity could not be verified for $name (HTTP $status)." >&2
    exit 1
  fi
done
if [[ -n "$PROBE_REPORT" ]]; then
  node - "$TASK_TMP/probes.jsonl" "$PROBE_REPORT" "$SOURCE_SHA" "$APP_ID" <<'NODE'
const fs = require('node:fs');
const [input,output,sourceSha,appId] = process.argv.slice(2);
const functions = fs.readFileSync(input,'utf8').trim().split('\n').map(line => JSON.parse(line));
fs.writeFileSync(output,JSON.stringify({source_sha:sourceSha,app_id:appId,functions})+'\n',{flag:'wx',mode:0o600});
NODE
fi
printf 'BASE44_STAGED_V9_RUNTIME_VERIFIED source_sha=%s production_activation=false\n' "$SOURCE_SHA"
