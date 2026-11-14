#!/usr/bin/env bash
# Source-pinned, owner-only Base44 staged-150 configuration and readback.
# The script intentionally changes NO GCP resources, entitlements, public routes,
# V8 functions, admission barrier, or BETA_SCAN_ADMISSION_ENABLED.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
OPERATION="${OPERATION:-status}"
OWNER_ID="${STAGED_OWNER_USER_ID:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"

refuse() { echo "BASE44_STAGED_CONTROL_BLOCKED: $*" >&2; exit 2; }
[[ "$APP_ID" == "6a498732ec779dfaaeab0e53" ]] || refuse "unexpected app"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || refuse "exact SOURCE_SHA required"
case "$OPERATION" in
  status) ;;
  deploy-probe)
    [[ "$CONFIRM" == "DEPLOY-BASE44-STAGED-PROBE:$SOURCE_SHA" ]] || refuse "exact deploy-probe confirmation required" ;;
  prepare-owner)
    [[ "$OWNER_ID" == "6a498da58ef5cec1f5cd4486" ]] || refuse "only the fixed owner-test account is allowed"
    [[ "$CONFIRM" == "PREPARE-BASE44-STAGED-150:$SOURCE_SHA:$OWNER_ID" ]] || refuse "exact prepare-owner confirmation required" ;;
  disable)
    [[ "$OWNER_ID" == "6a498da58ef5cec1f5cd4486" ]] || refuse "only the fixed owner-test account is allowed"
    [[ "$CONFIRM" == "DISABLE-BASE44-STAGED:$SOURCE_SHA:$OWNER_ID" ]] || refuse "exact disable confirmation required" ;;
  *) refuse "unsupported operation" ;;
esac
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"
fixlist_install_base44_cli "$TMP/pinned-cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

verify_probe_package() {
  # A runtime response without exact deployed package readback is not source evidence.
  mkdir -p "$TMP/pulled/base44/functions" "$TMP/pulled/base44/entities"
  cat > "$TMP/pulled/base44/config.jsonc" <<'JSON'
{"name":"staged-runtime-operator-readback","functionsDir":"functions","entitiesDir":"entities"}
JSON
  if ! (cd "$TMP/pulled" && "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions pull fixlistStagedRuntimeControl) > "$TMP/pull.log" 2>&1; then
    echo "BASE44_STAGED_OPERATOR_PACKAGE_UNVERIFIED: deployed function pull failed." >&2
    return 1
  fi
  [[ -f "$TMP/pulled/base44/functions/fixlistStagedRuntimeControl/function.jsonc" ]] || return 1
  node --input-type=module - "$REPO_ROOT" "$TMP/pulled/base44/functions" <<'NODE'
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root,remote] = process.argv.slice(2);
const {buildManifest} = await import(pathToFileURL(path.join(root,'scripts/base44_release_manifest.mjs')));
const names=['fixlistStagedRuntimeControl'];
const local=buildManifest(names,path.join(root,'base44/functions'),[]);
const deployed=buildManifest(names,remote,[]);
if (local.functions[names[0]].packageDigest !== deployed.functions[names[0]].packageDigest)
  throw Error('Base44 staged runtime operator bytes differ from source');
console.log('BASE44_STAGED_OPERATOR_PACKAGE_MATCHED');
NODE
}

readback() {
  cat > "$TMP/readback.js" <<'NODE'
const me = await base44.auth.me();
if (me?.id !== "6a498da58ef5cec1f5cd4486" || me?.role !== "admin") throw new Error("owner_identity_mismatch");
const result = await base44.functions.invoke("fixlistStagedRuntimeControl", {action:"status"});
const value = result?.data && typeof result.data === "object" ? result.data : result;
if (value?.success !== true || value.operator_build_id !== "fixlist-staged-runtime-control-v1") throw new Error("runtime_probe_not_ready");
console.log("FIXLIST_STAGED_BASE44_READBACK=" + JSON.stringify(value));
NODE
  if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod < "$TMP/readback.js" > "$TMP/probe.out" 2> "$TMP/probe.err"; then
    echo "BASE44_STAGED_READBACK_UNVERIFIED: owner CLI could not invoke the deployed runtime probe." >&2
    return 1
  fi
  node --input-type=module - "$TMP/probe.out" "$TMP/verified.json" <<'NODE'
import fs from 'node:fs';
const [input, output] = process.argv.slice(2);
const lines = fs.readFileSync(input, 'utf8').split('\n').filter(line => line.startsWith('FIXLIST_STAGED_BASE44_READBACK='));
if (lines.length !== 1) throw new Error('Expected exactly one runtime readback');
const report = JSON.parse(lines[0].slice('FIXLIST_STAGED_BASE44_READBACK='.length));
if (report?.success !== true || report.operator_build_id !== 'fixlist-staged-runtime-control-v1'
    || report.schema_version !== 'fixlist_staged_runtime_readback_v1'
    || report.v9_runtime_attested !== false) throw new Error('Invalid staged runtime readback identity');
const approved = ['success','operator_build_id','schema_version','config_converged','env_mode','secret_mode',
  'env_cohort_state','secret_cohort_state','cohort_count','owner_match','staged_owner_enabled',
  'legacy_alias_state','intake_gate','admission_gate','intake_disabled_verified',
  'new_owner_intake_disabled','v9_runtime_attested'];
if (Object.keys(report).some(key => !approved.includes(key))) throw new Error('Unexpected runtime readback field');
fs.writeFileSync(output, JSON.stringify(report) + '\n', {flag:'w',mode:0o600});
console.log('BASE44_STAGED_RUNTIME_READBACK_OBSERVED');
NODE
}

case "$OPERATION" in
  status)
    verify_probe_package || refuse "deployed operator package mismatch"
    readback || refuse "runtime readback unavailable"
    node - "$TMP/verified.json" <<'NODE'
const report = require(process.argv[2]);
console.log(JSON.stringify(report));
NODE
    ;;
  deploy-probe)
    # Deploy ONLY the new unreferenced owner probe, never V8/V9 or the public site.
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy fixlistStagedRuntimeControl > "$TMP/deploy.log" 2>&1; then
      refuse "probe deployment failed; no success claimed"
    fi
    verify_probe_package || refuse "probe deployed but package readback failed"
    readback || refuse "probe deployed but runtime readback is unverified"
    echo "BASE44_STAGED_PROBE_DEPLOYED_READBACK_OBSERVED source_sha=$SOURCE_SHA v9_attested=false"
    ;;
  prepare-owner|disable)
    verify_probe_package || refuse "deployed operator package mismatch"
    # Stop *new* Base44 intake first. Leave admission enabled so committed
    # scans can reconcile/release coordinator claims and finish persistence.
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1; then
      refuse "failed to close new Base44 intake"
    fi
    if [[ "$OPERATION" == prepare-owner ]]; then
      # 500 stays entitlement-controlled, no owner grant or client cap selector.
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=$OWNER_ID" > "$TMP/config.log" 2>&1; then
        refuse "staged config write failed after intake was closed; state must be re-read"
      fi
    else
      # Does NOT remove a worker tag/queue or disable task execution.
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=monolith" "SCAN_STAGED_OWNER_IDS=" > "$TMP/config.log" 2>&1; then
        refuse "disable write failed after intake was closed; state must be re-read"
      fi
    fi
    readback || refuse "configuration may have changed; deployed runtime readback unavailable"
    if ! node - "$TMP/verified.json" "$OPERATION" <<'NODE'
const fs = require('node:fs');
const report = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const operation = process.argv[3];
if (report.intake_disabled_verified !== true || report.config_converged !== true) process.exit(1);
if (operation === 'prepare-owner' && (report.env_mode !== 'staged' || report.owner_match !== true || report.cohort_count !== 1)) process.exit(1);
if (operation === 'disable' && (report.env_mode !== 'monolith' || report.owner_match !== false || report.cohort_count !== 0)) process.exit(1);
NODE
    then refuse "runtime configuration did not converge; never infer activation from a secrets write"; fi
    echo "BASE44_STAGED_CONFIG_READBACK_VERIFIED mode=$OPERATION source_sha=$SOURCE_SHA public_intake=closed v9_attested=false"
    ;;
esac
