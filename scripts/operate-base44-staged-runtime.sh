#!/usr/bin/env bash
# Source-pinned, owner-only Base44 staged configuration and readback.
# The script intentionally changes NO GCP resources, entitlements, public routes,
# V8 functions, admission barrier, or BETA_SCAN_ADMISSION_ENABLED.
# For a customer pilot, set STAGED_OPERATOR_USER_ID to the signed-in admin and
# STAGED_OWNER_USER_ID to the exact tester ID verified in the native preview
# session. The tester must have role "user" and the intended scan entitlement.
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
OPERATOR_ID="${STAGED_OPERATOR_USER_ID:-$OWNER_ID}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
PAID_PAGE_CAP="${STAGED_PAID_PAGE_CAP:-150}"
GATEWAY_REVISION="${STAGED_GATEWAY_REVISION:-}"
GATEWAY_ORIGIN="https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app"

refuse() { echo "BASE44_STAGED_CONTROL_BLOCKED: $*" >&2; exit 2; }
[[ "$APP_ID" == "6a498732ec779dfaaeab0e53" ]] || refuse "unexpected app"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || refuse "exact SOURCE_SHA required"
case "$OPERATOR_ID" in
  6a498da58ef5cec1f5cd4486) OPERATOR_EMAIL=bright4862@gmail.com ;;
  6a498732ec779dfaaeab0e54) OPERATOR_EMAIL=londonparisbrussels@gmail.com ;;
  *) refuse "STAGED_OPERATOR_USER_ID must select an approved FixList administrator" ;;
esac
PAID=false
if [[ "$OPERATION" == status-paid || "$OPERATION" == prepare-paid ]]; then
  PAID=true
  OWNER_ID="${OWNER_ID:-$OPERATOR_ID}"
  [[ "$OWNER_ID" == "$OPERATOR_ID" ]] || refuse "paid preparation does not take a pilot account"
  [[ "$PAID_PAGE_CAP" == 150 || "$PAID_PAGE_CAP" == 500 ]] || refuse "paid page cap must be 150 or 500"
  [[ "$GATEWAY_REVISION" =~ ^fixlist-dispatch-gateway-[a-z0-9-]+$ && ${#GATEWAY_REVISION} -le 63 ]] \
    || refuse "exact serving STAGED_GATEWAY_REVISION required"
fi
[[ "$OWNER_ID" =~ ^[A-Za-z0-9_-]{6,64}$ ]] || refuse "exact STAGED_OWNER_USER_ID required"
PILOT=false
if [[ "$OWNER_ID" != "$OPERATOR_ID" ]]; then
  case "$OWNER_ID" in
    6a498da58ef5cec1f5cd4486|6a498732ec779dfaaeab0e54)
      refuse "customer pilot target must be separate from the approved administrator accounts" ;;
  esac
  [[ -z "${BASE44_API_KEY:-}" && "$BASE44_EXPECTED_OWNER" == "$OPERATOR_EMAIL" ]] ||
    refuse "customer pilot requires the selected administrator's authenticated CLI session"
  PILOT=true
fi
case "$OPERATION" in
  status|status-paid) ;;
  deploy-probe)
    [[ "$CONFIRM" == "DEPLOY-BASE44-STAGED-PROBE:$SOURCE_SHA" ]] || refuse "exact deploy-probe confirmation required" ;;
  prepare-owner)
    [[ "$CONFIRM" == "PREPARE-BASE44-STAGED-150:$SOURCE_SHA:$OWNER_ID" ]] || refuse "exact prepare-owner confirmation required" ;;
  prepare-paid)
    [[ "$CONFIRM" == "PREPARE-BASE44-STAGED-PAID:$SOURCE_SHA:$GATEWAY_REVISION:$PAID_PAGE_CAP" ]] \
      || refuse "exact source, gateway revision and paid tier confirmation required" ;;
  disable)
    [[ "$CONFIRM" == "DISABLE-BASE44-STAGED:$SOURCE_SHA:$OWNER_ID" ]] || refuse "exact disable confirmation required" ;;
  *) refuse "unsupported operation" ;;
esac
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"
fixlist_install_base44_cli "$TMP/pinned-cli"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

{
  printf 'const expectedId = "%s";\nconst expectedEmail = "%s";\n' "$OPERATOR_ID" "$OPERATOR_EMAIL"
  cat <<'NODE'
const me = await base44.auth.me();
if (me?.id !== expectedId || String(me?.email || "").trim().toLowerCase() !== expectedEmail
    || me?.role !== "admin") throw new Error("owner_identity_mismatch");
NODE
} > "$TMP/app-owner.js"

if [[ "$OPERATION" != status && "$OPERATION" != status-paid ]]; then
  # Prove the production app identity before deploying or changing settings.
  cp "$TMP/app-owner.js" "$TMP/preflight.js"
  printf '%s\n' 'console.log("FIXLIST_STAGED_APP_OWNER_VERIFIED");' >> "$TMP/preflight.js"
  if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
      < "$TMP/preflight.js" > "$TMP/owner.out" 2> "$TMP/owner.err" \
    || [[ "$(grep -Fxc 'FIXLIST_STAGED_APP_OWNER_VERIFIED' "$TMP/owner.out")" != 1 ]]; then
    refuse "selected production app owner could not be verified"
  fi
fi

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
const {assertPulledFunctionPackage} = await import(pathToFileURL(path.join(root,'scripts/base44_release_manifest.mjs')));
const name = 'fixlistStagedRuntimeControl';
assertPulledFunctionPackage(name, path.join(root, 'base44/functions', name), path.join(remote, name));
console.log('BASE44_STAGED_OPERATOR_PACKAGE_MATCHED');
NODE
}

readback() {
  cp "$TMP/app-owner.js" "$TMP/readback.js"
  cat >> "$TMP/readback.js" <<'NODE'
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

v9_intake_readback() {
  local phase="$1"
  cp "$TMP/app-owner.js" "$TMP/v9-pilot.js"
  cat >> "$TMP/v9-pilot.js" <<'NODE'
const result = await base44.functions.invoke("startStandardScanJobV9", {action:"staged_runtime_status"});
const value = result?.data && typeof result.data === "object" ? result.data : result;
const fields = ["schema_version", "success", "observed_at", "build_id", "runtime_activation_id",
  "release_fingerprint", "configured_pipeline_mode", "pipeline_mode", "staged_owner_cohort_state",
  "staged_owner_count", "staged_owner_cohort_sha256", "staged_owner_enabled", "intake_gate", "admission_gate",
  "staged_rollout_scope", "staged_500_entitled_enabled", "paid_dispatch_gateway_origin"];
const safe = Object.fromEntries(fields.map(key => [key, value?.[key]]));
console.log("FIXLIST_V9_PILOT_READBACK=" + JSON.stringify(safe));
NODE
  timeout --signal=TERM --kill-after=5s 55 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
    < "$TMP/v9-pilot.js" > "$TMP/v9-pilot.out" 2> "$TMP/v9-pilot.err" || return 1
  node --input-type=module - "$TMP/v9-pilot.out" "$TMP/v9-pilot.json" \
    "$REPO_ROOT" "$V9_BUILD_ID" "$V9_ACTIVATION_ID" "$OWNER_ID" "$phase" "$PAID_PAGE_CAP" "$GATEWAY_ORIGIN" <<'NODE'
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
const [input, output, root, buildId, activationId, targetId, phase, cap, gatewayOrigin] = process.argv.slice(2);
const prefix = 'FIXLIST_V9_PILOT_READBACK=';
const lines = fs.readFileSync(input, 'utf8').split('\n').filter(line => line.startsWith(prefix));
if (lines.length !== 1) process.exit(1);
const report = JSON.parse(lines[0].slice(prefix.length));
const {fingerprint} = JSON.parse(fs.readFileSync(path.join(root, 'data/beta-crawler-revision.json'), 'utf8'));
const observationAgeMs = Date.now() - Date.parse(report.observed_at);
if (report.success !== true || report.schema_version !== 'fixlist_staged_v9_intake_readback_v1'
    || !/^[0-9a-f]{64}$/.test(buildId) || report.build_id !== buildId
    || !activationId || report.runtime_activation_id !== activationId
    || !/^[0-9a-f]{16}$/.test(fingerprint) || report.release_fingerprint !== fingerprint
    || !Number.isFinite(observationAgeMs) || Math.abs(observationAgeMs) > 60_000) process.exit(1);
const cohortDigest = createHash('sha256').update(JSON.stringify([targetId])).digest('hex');
if (phase.startsWith('paid-')) {
  if (report.paid_dispatch_gateway_origin !== gatewayOrigin) process.exit(1);
  if (phase !== 'paid-preflight') {
    const emptyCohort = createHash('sha256').update('[]').digest('hex');
    if (report.configured_pipeline_mode !== 'staged' || report.staged_rollout_scope !== 'paid'
        || report.staged_500_entitled_enabled !== (cap === '500')
        || report.pipeline_mode !== 'monolith' || report.staged_owner_enabled !== false
        || report.staged_owner_cohort_state !== 'empty' || report.staged_owner_count !== 0
        || report.staged_owner_cohort_sha256 !== emptyCohort
        || !['enabled', 'disabled'].includes(report.intake_gate)
        || !['enabled', 'disabled'].includes(report.admission_gate)
        || (phase === 'paid-prepared' && report.intake_gate !== 'disabled')) process.exit(1);
    fs.writeFileSync(output, JSON.stringify({
      base44_v9_attested: true, page_cap: Number(cap), intake_gate: report.intake_gate,
      admission_gate: report.admission_gate,
    }) + '\n', {flag:'w',mode:0o600});
  }
  process.exit(0);
}
const cohortMatches = report.configured_pipeline_mode === 'staged' && report.staged_owner_cohort_state === 'explicit'
  && report.staged_owner_count === 1 && report.staged_owner_cohort_sha256 === cohortDigest
  && report.pipeline_mode === 'monolith' && report.staged_owner_enabled === false
  && report.staged_rollout_scope === 'off' && report.staged_500_entitled_enabled === false;
if (phase === 'prepared' && !(cohortMatches && report.intake_gate === 'disabled')) process.exit(1);
fs.writeFileSync(output, JSON.stringify(cohortMatches) + '\n', {flag:'w',mode:0o600});
NODE
}

verify_paid_gateway() {
  curl --fail --silent --show-error --proto '=https' --max-time 20 \
    "$GATEWAY_ORIGIN/health" > "$TMP/gateway.json" || return 1
  node --input-type=module - "$TMP/gateway.json" "$SOURCE_SHA" "$GATEWAY_REVISION" "$PAID_PAGE_CAP" <<'NODE'
import { createHash } from 'node:crypto';
import fs from 'node:fs';
const [file, sha, revision, cap] = process.argv.slice(2);
const health = JSON.parse(fs.readFileSync(file, 'utf8'));
const digest = createHash('sha256').update('[]').digest('hex');
if (health.ok !== true || health.service !== 'fixlist-dispatch-gateway'
    || health.source_sha !== sha || health.revision !== revision
    || health.pipeline_mode !== 'staged' || health.staged_rollout_scope !== 'paid'
    || health.staged_500_entitled_enabled !== (cap === '500')
    || health.canary_worker_origin !== null || health.canary_owner_count !== 0
    || health.staged_owner_count !== 0 || health.staged_owner_cohort_sha256 !== digest) process.exit(1);
NODE
}

if [[ "$PAID" == true || ( "$PILOT" == true && ( "$OPERATION" == status || "$OPERATION" == prepare-owner ) ) ]]; then
  command -v timeout >/dev/null || refuse "timeout is required for customer pilot readback"
  V9_BUILD_ID="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id startStandardScanJobV9)"
  V9_ACTIVATION_ID="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id startStandardScanJobV9)"
fi

case "$OPERATION" in
  status)
    verify_probe_package || refuse "deployed operator package mismatch"
    readback || refuse "runtime readback unavailable"
    if [[ "$PILOT" == true ]]; then
      v9_intake_readback status || refuse "exact V9 pilot readback unavailable"
    fi
    node - "$TMP/verified.json" "$TMP/v9-pilot.json" <<'NODE'
const fs = require('node:fs');
const report = require(process.argv[2]);
if (fs.existsSync(process.argv[3])) {
  report.v9_intake_attested = true;
  report.pilot_cohort_matches = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
}
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
  status-paid)
    v9_intake_readback paid-status || refuse "exact V9 paid configuration could not be verified"
    verify_paid_gateway || refuse "serving gateway does not match the selected paid tier"
    cat "$TMP/v9-pilot.json"
    ;;
  prepare-paid)
    verify_probe_package || refuse "deployed operator package mismatch"
    v9_intake_readback paid-preflight || refuse "deployed V9 intake or dispatcher origin does not match"
    verify_paid_gateway || refuse "serving gateway does not match the selected paid tier"
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1; then
      refuse "failed to close new Base44 intake"
    fi
    readback || refuse "closed intake could not be verified before configuration"
    node -e 'if (require(process.argv[1]).intake_disabled_verified !== true) process.exit(1)' "$TMP/verified.json" \
      || refuse "Base44 intake is unverified; paid settings have not been written"
    verify_paid_gateway || refuse "intake closed but the serving gateway changed before paid configuration"
    entitled500=false
    if [[ "$PAID_PAGE_CAP" == 500 ]]; then entitled500=true; fi
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
      "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=" "SCAN_PIPELINE_OWNER_IDS=" \
      "SCAN_STAGED_ROLLOUT_SCOPE=paid" "SCAN_STAGED_500_ENTITLED_ENABLED=$entitled500" > "$TMP/config.log" 2>&1; then
      refuse "paid configuration write failed after intake was closed; state must be re-read"
    fi
    v9_intake_readback paid-prepared || refuse "intake closed but exact V9 paid configuration is unverified"
    verify_paid_gateway || refuse "intake closed but the serving gateway changed during paid preparation"
    echo "BASE44_STAGED_PAID_READBACK_VERIFIED source_sha=$SOURCE_SHA gateway_revision=$GATEWAY_REVISION page_cap=$PAID_PAGE_CAP public_intake=closed"
    ;;
  prepare-owner|disable)
    verify_probe_package || refuse "deployed operator package mismatch"
    if [[ "$PILOT" == true && "$OPERATION" == prepare-owner ]]; then
      v9_intake_readback preflight || refuse "deployed V9 intake does not match the selected source"
    fi
    # Stop *new* Base44 intake first. Leave admission enabled so committed
    # scans can reconcile/release coordinator claims and finish persistence.
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1; then
      refuse "failed to close new Base44 intake"
    fi
    if [[ "$OPERATION" == prepare-owner ]]; then
      # 500 stays entitlement-controlled, no owner grant or client cap selector.
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=$OWNER_ID" \
        "SCAN_STAGED_ROLLOUT_SCOPE=off" "SCAN_STAGED_500_ENTITLED_ENABLED=false" > "$TMP/config.log" 2>&1; then
        refuse "staged config write failed after intake was closed; state must be re-read"
      fi
    else
      # Does NOT remove a worker tag/queue or disable task execution.
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=monolith" "SCAN_STAGED_OWNER_IDS=" \
        "SCAN_STAGED_ROLLOUT_SCOPE=off" "SCAN_STAGED_500_ENTITLED_ENABLED=false" > "$TMP/config.log" 2>&1; then
        refuse "disable write failed after intake was closed; state must be re-read"
      fi
    fi
    readback || refuse "configuration may have changed; deployed runtime readback unavailable"
    if ! node - "$TMP/verified.json" "$OPERATION" "$PILOT" <<'NODE'
const fs = require('node:fs');
const report = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const operation = process.argv[3];
const operatorIsTarget = process.argv[4] === 'false';
if (report.intake_disabled_verified !== true || report.config_converged !== true) process.exit(1);
if (operation === 'prepare-owner' && (report.env_mode !== 'staged' || report.owner_match !== operatorIsTarget || report.cohort_count !== 1)) process.exit(1);
if (operation === 'disable' && (report.env_mode !== 'monolith' || report.owner_match !== false || report.cohort_count !== 0)) process.exit(1);
NODE
    then refuse "runtime configuration did not converge; never infer activation from a secrets write"; fi
    if [[ "$PILOT" == true && "$OPERATION" == prepare-owner ]]; then
      v9_intake_readback prepared || refuse "intake closed but the exact V9 pilot cohort could not be verified"
      echo "BASE44_STAGED_CONFIG_READBACK_VERIFIED mode=$OPERATION source_sha=$SOURCE_SHA public_intake=closed v9_attested=true pilot_cohort_matches=true"
    else
      echo "BASE44_STAGED_CONFIG_READBACK_VERIFIED mode=$OPERATION source_sha=$SOURCE_SHA public_intake=closed v9_attested=false"
    fi
    ;;
esac
