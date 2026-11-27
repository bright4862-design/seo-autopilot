#!/usr/bin/env bash
# Source-pinned, owner-only Base44 staged configuration and readback.
# The script intentionally changes NO GCP resources, entitlements, public routes,
# V8 functions, admission barrier, or BETA_SCAN_ADMISSION_ENABLED.
# For a customer pilot, set STAGED_OPERATOR_USER_ID to the signed-in admin and
# STAGED_OWNER_USER_ID to the exact tester ID verified in the native preview
# session. The tester must have role "user" and the intended scan entitlement.
# Use STAGED_COHORT_TARGET_ROLE=admin to select the other approved administrator
# for a controlled startup scan.
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
TARGET_ROLE="${STAGED_COHORT_TARGET_ROLE:-user}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
PAID_PAGE_CAP="${STAGED_PAID_PAGE_CAP:-150}"
GATEWAY_REVISION="${STAGED_GATEWAY_REVISION:-}"
PILOT_WORKER_ORIGIN="${STAGED_PILOT_WORKER_ORIGIN:-}"
PUBLIC_PILOT_EXPIRES_AT="${STAGED_PUBLIC_PILOT_EXPIRES_AT:-}"
GATEWAY_ORIGIN="https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app"
BRIGHT_ADMIN_ID="6a498da58ef5cec1f5cd4486"
LONDON_ADMIN_ID="6a498732ec779dfaaeab0e54"
ADMIN_500_MARKER="SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID"

refuse() { echo "BASE44_STAGED_CONTROL_BLOCKED: $*" >&2; exit 2; }
[[ "$APP_ID" == "6a498732ec779dfaaeab0e53" ]] || refuse "unexpected app"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || refuse "exact SOURCE_SHA required"
case "$OPERATOR_ID" in
  "$BRIGHT_ADMIN_ID") OPERATOR_EMAIL=bright4862@gmail.com ;;
  "$LONDON_ADMIN_ID") OPERATOR_EMAIL=londonparisbrussels@gmail.com ;;
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
if [[ "$OPERATION" == status-off || "$OPERATION" == hold-published-pilot ]]; then
  OWNER_ID="${OWNER_ID:-$OPERATOR_ID}"
  [[ "$OWNER_ID" == "$OPERATOR_ID" ]] || refuse "off status or pilot hold does not take a pilot account"
fi
[[ "$OWNER_ID" =~ ^[A-Za-z0-9_-]{6,64}$ ]] || refuse "exact STAGED_OWNER_USER_ID required"
[[ "$TARGET_ROLE" == user || "$TARGET_ROLE" == admin ]] || refuse "invalid staged cohort target role"
PILOT=false
if [[ "$OWNER_ID" != "$OPERATOR_ID" ]]; then
  case "$OWNER_ID" in
    "$BRIGHT_ADMIN_ID"|"$LONDON_ADMIN_ID")
      [[ "$TARGET_ROLE" == admin ]] || refuse "customer pilot target must be separate from the approved administrator accounts" ;;
    *)
      [[ "$TARGET_ROLE" == user ]] || refuse "administrator target must select an approved FixList administrator" ;;
  esac
  [[ -z "${BASE44_API_KEY:-}" && "$BASE44_EXPECTED_OWNER" == "$OPERATOR_EMAIL" ]] ||
    refuse "separate target requires the selected administrator's authenticated CLI session"
  PILOT=true
fi
if [[ "$OPERATION" == prepare-admin-500-rehearsal || "$OPERATION" == hold-admin-500-rehearsal ]]; then
  [[ "$OPERATOR_ID" == "$LONDON_ADMIN_ID" && "$OWNER_ID" == "$BRIGHT_ADMIN_ID" && "$TARGET_ROLE" == admin ]] \
    || refuse "the 500 rehearsal requires London to operate the exact Bright administrator"
fi
if [[ "$OPERATION" == prepare-admin-500-rehearsal ]]; then
  [[ "$PUBLIC_PILOT_EXPIRES_AT" =~ ^[1-9][0-9]{9,11}$ ]] || refuse "a future Bright rehearsal expiry is required"
  pilot_now="$(date +%s)"
  (( PUBLIC_PILOT_EXPIRES_AT > pilot_now && PUBLIC_PILOT_EXPIRES_AT <= pilot_now + 7200 )) \
    || refuse "select a future rehearsal expiry within two hours"
  [[ "$GATEWAY_REVISION" =~ ^fixlist-dispatch-gateway-[a-z0-9-]+$ && ${#GATEWAY_REVISION} -le 63 ]] \
    || refuse "exact serving STAGED_GATEWAY_REVISION required for the Bright rehearsal"
  [[ "$PILOT_WORKER_ORIGIN" =~ ^https://canary-([0-9]{5}-[a-z0-9]{3})---fixlist-standard150-worker-[a-z0-9-]+\.a\.run\.app$ ]] \
    || refuse "use the verified STAGED_PILOT_WORKER_ORIGIN for the Bright rehearsal"
  ADMIN_WORKER_REVISION="fixlist-standard150-worker-${BASH_REMATCH[1]}"
elif [[ -n "$PUBLIC_PILOT_EXPIRES_AT" ]]; then
  [[ ( "$OPERATION" == prepare-owner || "$OPERATION" == prepare-paid-500-pilot ) && "$PILOT" == true && "$TARGET_ROLE" == user
    && "$PUBLIC_PILOT_EXPIRES_AT" =~ ^[1-9][0-9]{9,11}$ ]] || refuse "Published pilot expiry requires a named ordinary account and a Unix timestamp."
  pilot_now="$(date +%s)"
  (( PUBLIC_PILOT_EXPIRES_AT > pilot_now && PUBLIC_PILOT_EXPIRES_AT <= pilot_now + 14 * 86400 )) \
    || refuse "Select a future pilot expiry within the coordinator's acceptance window."
  [[ "$GATEWAY_REVISION" =~ ^fixlist-dispatch-gateway-[a-z0-9-]+$ && ${#GATEWAY_REVISION} -le 63 ]] \
    || refuse "exact serving STAGED_GATEWAY_REVISION required for the published pilot"
  if [[ "$OPERATION" == prepare-owner ]]; then
    [[ "$PILOT_WORKER_ORIGIN" =~ ^https://canary-[a-z0-9-]+---fixlist-standard150-worker-[a-z0-9-]+\.a\.run\.app$ ]] \
      || refuse "use the verified STAGED_PILOT_WORKER_ORIGIN for the named gateway canary"
  fi
fi
case "$OPERATION" in
  status|status-paid|status-off) ;;
  hold-published-pilot)
    [[ "$CONFIRM" == "HOLD-BASE44-PUBLISHED-PILOT:$SOURCE_SHA" ]] || refuse "exact published pilot hold confirmation required" ;;
  deploy-probe)
    [[ "$CONFIRM" == "DEPLOY-BASE44-STAGED-PROBE:$SOURCE_SHA" ]] || refuse "exact deploy-probe confirmation required" ;;
  prepare-owner)
    [[ "$CONFIRM" == "PREPARE-BASE44-STAGED-150:$SOURCE_SHA:$OWNER_ID${PUBLIC_PILOT_EXPIRES_AT:+:$PUBLIC_PILOT_EXPIRES_AT}" ]] || refuse "exact prepare-owner confirmation required" ;;
  prepare-admin-500-rehearsal)
    [[ "$CONFIRM" == "PREPARE-BASE44-ADMIN-500-REHEARSAL:$SOURCE_SHA:$GATEWAY_REVISION:$OWNER_ID:$PUBLIC_PILOT_EXPIRES_AT" ]] \
      || refuse "exact Bright rehearsal source, gateway, account and expiry confirmation required" ;;
  hold-admin-500-rehearsal)
    [[ "$CONFIRM" == "HOLD-BASE44-ADMIN-500-REHEARSAL:$SOURCE_SHA:$OWNER_ID" ]] \
      || refuse "exact Bright rehearsal hold confirmation required" ;;
  prepare-paid)
    [[ "$CONFIRM" == "PREPARE-BASE44-STAGED-PAID:$SOURCE_SHA:$GATEWAY_REVISION:$PAID_PAGE_CAP" ]] \
      || refuse "exact source, gateway revision and paid tier confirmation required" ;;
  prepare-paid-500-pilot)
    [[ -n "$PUBLIC_PILOT_EXPIRES_AT" ]] || refuse "a future paid pilot expiry is required"
    [[ "$CONFIRM" == "PREPARE-PAID-500-PILOT:$SOURCE_SHA:$GATEWAY_REVISION:$OWNER_ID:$PUBLIC_PILOT_EXPIRES_AT" ]] \
      || refuse "exact paid pilot source, gateway, account and expiry confirmation required" ;;
  hold-paid-500-pilot)
    [[ "$PILOT" == true && "$TARGET_ROLE" == user && "$CONFIRM" == "HOLD-PAID-500-PILOT:$SOURCE_SHA:$OWNER_ID" ]] \
      || refuse "exact paid pilot source and account confirmation required" ;;
  disable)
    [[ "$CONFIRM" == "DISABLE-BASE44-STAGED:$SOURCE_SHA:$OWNER_ID" ]] || refuse "exact disable confirmation required" ;;
  *) refuse "unsupported operation" ;;
esac
if [[ "$OPERATION" == hold-published-pilot || "$OPERATION" == hold-paid-500-pilot || "$OPERATION" == hold-admin-500-rehearsal ]]; then
  fixlist_require_merged_checkout "$REPO_ROOT" "$SOURCE_SHA"
else
  fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
fi

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

if [[ "$OPERATION" != status && "$OPERATION" != status-paid && "$OPERATION" != status-off ]]; then
  # Prove the production app identity before deploying or changing settings.
  cp "$TMP/app-owner.js" "$TMP/preflight.js"
  if [[ "$OPERATION" == prepare-admin-500-rehearsal ]]; then
    # Reuse the exact launcher entitlement predicate. Do not create or change access here.
    sed 's/^export //' "$REPO_ROOT/base44/functions/startStandardScanJobV9/entitlement.js" >> "$TMP/preflight.js"
    cat >> "$TMP/preflight.js" <<'NODE'
const target = await base44.entities.User.get(OWNER_TEST_USER_ID);
if (target?.id !== OWNER_TEST_USER_ID || target.role !== "admin"
    || normalizeEmail(target.email) !== OWNER_TEST_EMAIL) throw new Error("bright_identity_mismatch");
const byOwner = await base44.entities.Access.filter({owner_user_id: OWNER_TEST_USER_ID}, "-created_date", 2);
const byEmail = await base44.entities.Access.filter({user_email: OWNER_TEST_EMAIL}, "-created_date", 2);
if (![byOwner, byEmail].every(rows => Array.isArray(rows) && rows.length === 1 && rows[0]?.id
      && evaluatePaidAccess({rows, user: target}).ok && rows[0].page_cap === 500)
    || byOwner[0].id !== byEmail[0].id) throw new Error("bright_500_entitlement_unverified");
NODE
  fi
  printf '%s\n' 'console.log("FIXLIST_STAGED_APP_OWNER_VERIFIED");' >> "$TMP/preflight.js"
  if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
      < "$TMP/preflight.js" > "$TMP/owner.out" 2> "$TMP/owner.err" \
    || [[ "$(grep -Fxc 'FIXLIST_STAGED_APP_OWNER_VERIFIED' "$TMP/owner.out")" != 1 ]]; then
    if [[ "$OPERATION" == prepare-admin-500-rehearsal ]]; then
      refuse "selected production app operator, Bright target or Bright 500 entitlement could not be verified"
    fi
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
  printf 'const intakeRoute = "%s";\n' "$V9_INTAKE_ROUTE" >> "$TMP/v9-pilot.js"
  cat >> "$TMP/v9-pilot.js" <<'NODE'
const result = await base44.functions.invoke(intakeRoute, {action:"staged_runtime_status"});
const value = result?.data && typeof result.data === "object" ? result.data : result;
const fields = ["schema_version", "success", "observed_at", "build_id", "runtime_activation_id",
  "release_fingerprint", "configured_pipeline_mode", "pipeline_mode", "staged_owner_cohort_state",
  "staged_owner_count", "staged_owner_cohort_sha256", "staged_owner_enabled", "intake_gate", "admission_gate",
  "staged_rollout_scope", "staged_500_entitled_enabled", "legacy_staged_500_entitled_enabled", "paid_dispatch_gateway_origin", "public_pilot_expires_at",
  "staged_pilot_owner_count", "staged_pilot_owner_cohort_sha256", "admin_500_rehearsal_enabled"];
const safe = Object.fromEntries(fields.map(key => [key, value?.[key]]));
console.log("FIXLIST_V9_PILOT_READBACK=" + JSON.stringify(safe));
NODE
  timeout --signal=TERM --kill-after=5s 55 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
    < "$TMP/v9-pilot.js" > "$TMP/v9-pilot.out" 2> "$TMP/v9-pilot.err" || return 1
  node --input-type=module - "$TMP/v9-pilot.out" "$TMP/v9-pilot.json" \
    "$REPO_ROOT" "$V9_BUILD_ID" "$V9_ACTIVATION_ID" "$OWNER_ID" "$OPERATOR_ID" "$phase" "$PAID_PAGE_CAP" "$GATEWAY_ORIGIN" "$PUBLIC_PILOT_EXPIRES_AT" <<'NODE'
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
const [input, output, root, buildId, activationId, targetId, operatorId, phase, cap, gatewayOrigin, pilotExpiresAt] = process.argv.slice(2);
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
    || !Number.isFinite(observationAgeMs) || Math.abs(observationAgeMs) > 60_000
    || typeof report.legacy_staged_500_entitled_enabled !== 'boolean') process.exit(1);
if (!['preflight', 'paid-preflight'].includes(phase) && report.legacy_staged_500_entitled_enabled !== false) process.exit(1);
if (['published-pilot-held', 'paid-prepared', 'paid-pilot-prepared', 'paid-pilot-held'].includes(phase)
    && report.admin_500_rehearsal_enabled === true) process.exit(1);
if (phase === 'published-pilot-preflight' || phase === 'published-pilot-held') {
  if (report.staged_rollout_scope !== 'off') process.exit(1);
  if (phase === 'published-pilot-held' && report.public_pilot_expires_at !== 0) process.exit(1);
  process.exit(0);
}
if (phase === 'prepared' && pilotExpiresAt && (report.public_pilot_expires_at !== Number(pilotExpiresAt)
    || report.admin_500_rehearsal_enabled === true)) process.exit(1);
const cohortDigest = createHash('sha256').update(JSON.stringify([targetId])).digest('hex');
const emptyCohort = createHash('sha256').update('[]').digest('hex');
if (phase === 'off-status') {
  if (report.configured_pipeline_mode !== 'monolith' || report.staged_rollout_scope !== 'off'
      || report.staged_500_entitled_enabled !== false || report.pipeline_mode !== 'monolith'
      || report.staged_owner_enabled !== false || report.staged_owner_cohort_state !== 'empty'
      || report.staged_owner_count !== 0 || report.staged_owner_cohort_sha256 !== emptyCohort
      || report.intake_gate !== 'disabled') process.exit(1);
  fs.writeFileSync(output, JSON.stringify({
    base44_v9_attested: true, staged_rollout_scope: 'off', staged_500_entitled_enabled: false, intake_gate: 'disabled',
  }) + '\n', {flag:'w',mode:0o600});
  process.exit(0);
}
const expectsGateway = phase === 'preflight' || phase === 'prepared' || phase.startsWith('paid-')
  || ['admin-500-preflight', 'admin-500-closed', 'admin-500-prepared'].includes(phase);
if (expectsGateway && report.paid_dispatch_gateway_origin !== gatewayOrigin) process.exit(1);
if (phase.startsWith('paid-')) {
  if (phase !== 'paid-preflight') {
    const paidPilot = phase.startsWith('paid-pilot-');
    if (report.configured_pipeline_mode !== 'staged' || report.staged_rollout_scope !== 'paid'
        || report.staged_500_entitled_enabled !== (!paidPilot && cap === '500')
        || report.pipeline_mode !== 'monolith' || report.staged_owner_enabled !== false
        || report.staged_owner_cohort_state !== 'empty' || report.staged_owner_count !== 0
        || report.staged_owner_cohort_sha256 !== emptyCohort
        || !['enabled', 'disabled'].includes(report.intake_gate)
        || !['enabled', 'disabled'].includes(report.admission_gate)
        || (phase === 'paid-prepared' && report.intake_gate !== 'disabled')) process.exit(1);
    if (paidPilot) {
      const empty = report.staged_pilot_owner_count === 0 && report.staged_pilot_owner_cohort_sha256 === emptyCohort;
      const named = report.staged_pilot_owner_count === 1 && report.staged_pilot_owner_cohort_sha256 === cohortDigest;
      if (phase === 'paid-pilot-prepare' && ((!empty && !named) || report.intake_gate !== 'enabled'
          || report.admission_gate !== 'enabled')) process.exit(1);
      if (phase === 'paid-pilot-prepared' && (!named || report.public_pilot_expires_at !== Number(pilotExpiresAt)
          || report.intake_gate !== 'enabled' || report.admission_gate !== 'enabled')) process.exit(1);
      if (phase === 'paid-pilot-hold' && !named) process.exit(1);
      if (phase === 'paid-pilot-held' && (!named || report.public_pilot_expires_at !== 0)) process.exit(1);
    }
    fs.writeFileSync(output, JSON.stringify({
      base44_v9_attested: true, page_cap: Number(cap), intake_gate: report.intake_gate,
      admission_gate: report.admission_gate,
    }) + '\n', {flag:'w',mode:0o600});
  }
  process.exit(0);
}
const operatorIsTarget = operatorId === targetId;
const cohortMatches = report.configured_pipeline_mode === 'staged' && report.staged_owner_cohort_state === 'explicit'
  && report.staged_owner_count === 1 && report.staged_owner_cohort_sha256 === cohortDigest
  && report.pipeline_mode === (operatorIsTarget ? 'staged' : 'monolith') && report.staged_owner_enabled === operatorIsTarget
  && report.staged_rollout_scope === 'off' && report.staged_500_entitled_enabled === false;
if (phase === 'prepared' && !(cohortMatches && report.intake_gate === 'disabled')) process.exit(1);
if (phase.startsWith('admin-500-')) {
  const enabled = report.admin_500_rehearsal_enabled;
  const expiry = report.public_pilot_expires_at;
  const active = Number.isSafeInteger(expiry) && expiry > Math.floor(Date.now() / 1000);
  if (typeof enabled !== 'boolean' || report.staged_rollout_scope !== 'off'
      || report.staged_500_entitled_enabled !== false
      || report.staged_pilot_owner_count !== 0 || report.staged_pilot_owner_cohort_sha256 !== emptyCohort) process.exit(1);
  if (['admin-500-preflight', 'admin-500-closed'].includes(phase) && active && !(enabled && cohortMatches)) process.exit(1);
  if (phase === 'admin-500-closed' && report.intake_gate !== 'disabled') process.exit(1);
  if (phase === 'admin-500-prepared' && (!enabled || !cohortMatches || !active
      || expiry !== Number(pilotExpiresAt) || report.intake_gate !== 'disabled')) process.exit(1);
  if (phase === 'admin-500-hold-preflight' && !cohortMatches && (enabled || active)) process.exit(1);
  if (phase === 'admin-500-held' && (enabled || expiry !== 0)) process.exit(1);
}
fs.writeFileSync(output, JSON.stringify(cohortMatches) + '\n', {flag:'w',mode:0o600});
NODE
}

verify_staged_gateway() {
  local scope="$1"
  curl --fail --silent --show-error --proto '=https' --max-time 20 \
    "$GATEWAY_ORIGIN/health" > "$TMP/gateway.json" || return 1
  node --input-type=module - "$TMP/gateway.json" "$SOURCE_SHA" "$GATEWAY_REVISION" "$scope" \
    "$PAID_PAGE_CAP" "$OWNER_ID" "$PILOT_WORKER_ORIGIN" <<'NODE'
import { createHash } from 'node:crypto';
import fs from 'node:fs';
const [file, sha, revision, scope, cap, ownerId, workerOrigin] = process.argv.slice(2);
const health = JSON.parse(fs.readFileSync(file, 'utf8'));
const adminRehearsal = scope === 'admin-rehearsal';
const pilot = scope === 'off' || adminRehearsal;
const paidPilot = scope === 'paid-pilot';
const digest = createHash('sha256').update(JSON.stringify(pilot ? [ownerId] : [])).digest('hex');
if (health.ok !== true || health.service !== 'fixlist-dispatch-gateway'
    || health.source_sha !== sha || health.revision !== revision
    || health.pipeline_mode !== 'staged' || health.staged_rollout_scope !== (pilot ? 'off' : 'paid')
    || health.staged_500_entitled_enabled !== (!pilot && !paidPilot && cap === '500')
    || health.canary_worker_origin !== (pilot ? workerOrigin : null)
    || health.canary_owner_count !== (pilot ? 1 : 0)
    || health.staged_owner_count !== (pilot ? 1 : 0) || health.staged_owner_cohort_sha256 !== digest
    || (pilot && health.canary_owner_cohort_sha256 !== digest)) process.exit(1);
if (adminRehearsal && (health.staged_pilot_owner_count !== 0
    || health.staged_pilot_owner_cohort_sha256 !== createHash('sha256').update('[]').digest('hex'))) process.exit(1);
if (paidPilot && (health.staged_pilot_owner_count !== 1
    || health.staged_pilot_owner_cohort_sha256 !== createHash('sha256').update(JSON.stringify([ownerId])).digest('hex'))) process.exit(1);
NODE
}

verify_admin_rehearsal_worker() {
  local service=fixlist-standard150-worker project=seo-autopilot-501517 region=europe-west1
  local worker_json="$TMP/admin-worker-service.json" revision_json="$TMP/admin-worker-revision.json"
  local tag="${PILOT_WORKER_ORIGIN#https://}" checked audience token
  gcloud run services describe "$service" --project="$project" --region="$region" --format=json > "$worker_json" || return 1
  checked="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" \
    --revision "$ADMIN_WORKER_REVISION" --tag "${tag%%---*}" < "$worker_json")" || return 1
  [[ "${checked##* tag_url=}" == "$PILOT_WORKER_ORIGIN" ]] || return 1
  python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" \
    --revision "$ADMIN_WORKER_REVISION" --tag "staged-${SOURCE_SHA:0:12}" --source-sha "$SOURCE_SHA" \
    < "$worker_json" > /dev/null || return 1
  gcloud run revisions describe "$ADMIN_WORKER_REVISION" --project="$project" --region="$region" --format=json \
    > "$revision_json" || return 1
  audience="$(node --input-type=module - "$worker_json" "$revision_json" "$ADMIN_WORKER_REVISION" "$SOURCE_SHA" "$OWNER_ID" <<'NODE'
import fs from 'node:fs';
const [serviceFile, revisionFile, revisionName, source, owner] = process.argv.slice(2);
const service = JSON.parse(fs.readFileSync(serviceFile, 'utf8'));
const revision = JSON.parse(fs.readFileSync(revisionFile, 'utf8'));
const containers = revision.spec?.containers;
if (revision.metadata?.name !== revisionName || containers?.length !== 1
    || !revision.status?.conditions?.some(row => row.type === 'Ready' && String(row.status).toLowerCase() === 'true')) process.exit(1);
const env = new Map(containers[0].env?.map(row => [row.name, row.value]));
if (env.get('FIXLIST_WORKER_SOURCE_SHA') !== source || env.get('SCAN_PIPELINE_MODE') !== 'staged'
    || env.get('SCAN_STAGED_OWNER_IDS') !== owner || env.get('SCAN_PIPELINE_OWNER_IDS')) process.exit(1);
console.log(service.status.url);
NODE
  )" || return 1
  token="${FIXLIST_WORKER_ID_TOKEN:-}"
  if [[ -z "$token" ]]; then
    token="$(gcloud auth print-identity-token)" || return 1
  fi
  [[ -n "$token" ]] || return 1
  GCP_PROJECT="$project" GCP_REGION="$region" CLOUD_RUN_SERVICE="$service" CLOUD_TASKS_QUEUE=fixlist-standard150 \
    TASKS_INVOKER_SERVICE_ACCOUNT="fixlist-standard150-invoker@$project.iam.gserviceaccount.com" \
    OPERATION=verify-worker-runtime-revision TARGET_REVISION="$ADMIN_WORKER_REVISION" SOURCE_SHA="$SOURCE_SHA" \
    FIXLIST_WORKER_PROBE_URL="$PILOT_WORKER_ORIGIN" FIXLIST_WORKER_TOKEN_AUDIENCE="$audience" \
    FIXLIST_WORKER_ID_TOKEN="$token" FIXLIST_VERIFY_STAGED_BASE44_RUNTIME=1 \
    bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh" > "$TMP/admin-worker-runtime.log" 2>&1
}

if [[ "$PAID" == true || "$OPERATION" == prepare-owner || "$OPERATION" == status-off \
  || "$OPERATION" == prepare-admin-500-rehearsal || "$OPERATION" == hold-admin-500-rehearsal \
  || "$OPERATION" == prepare-paid-500-pilot || "$OPERATION" == hold-paid-500-pilot \
  || "$OPERATION" == hold-published-pilot || ( "$PILOT" == true && "$OPERATION" == status ) ]]; then
  command -v timeout >/dev/null || refuse "timeout is required for customer pilot readback"
  v9_intake_identity="$(node -p 'const row = require(process.argv[1]).functions.startStandardScanJobV9; [row.route_name, row.build_id, row.runtime_activation_id].join(" ")' \
    "$REPO_ROOT/data/generated-staged-v9-routes.json")"
  read -r V9_INTAKE_ROUTE V9_BUILD_ID V9_ACTIVATION_ID <<< "$v9_intake_identity"
  [[ "$V9_INTAKE_ROUTE" =~ ^startStandardScanJobV9B[0-9a-f]{16}$ && "$V9_BUILD_ID" =~ ^[0-9a-f]{64}$ \
    && "$V9_ACTIVATION_ID" =~ ^[A-Za-z0-9._-]{1,120}$ ]] || refuse "exact staged intake identity required"
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
    verify_staged_gateway paid || refuse "serving gateway does not match the selected paid tier"
    cat "$TMP/v9-pilot.json"
    ;;
  status-off)
    v9_intake_readback off-status || refuse "V9 staged settings or closed intake are unverified"
    cat "$TMP/v9-pilot.json"
    ;;
  prepare-paid)
    verify_probe_package || refuse "deployed operator package mismatch"
    v9_intake_readback paid-preflight || refuse "deployed V9 intake or dispatcher origin does not match"
    verify_staged_gateway paid || refuse "serving gateway does not match the selected paid tier"
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1; then
      refuse "failed to close new Base44 intake"
    fi
    readback || refuse "closed intake could not be verified before configuration"
    node -e 'if (require(process.argv[1]).intake_disabled_verified !== true) process.exit(1)' "$TMP/verified.json" \
      || refuse "Base44 intake is unverified; paid settings have not been written"
    verify_staged_gateway paid || refuse "intake closed but the serving gateway changed before paid configuration"
    entitled500=false
    if [[ "$PAID_PAGE_CAP" == 500 ]]; then entitled500=true; fi
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
      "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=" "SCAN_PIPELINE_OWNER_IDS=" \
      "SCAN_STAGED_ROLLOUT_SCOPE=paid" "SCAN_STAGED_500_ENTITLED_ENABLED=false" \
      "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=$entitled500" \
      "SCAN_STAGED_PILOT_OWNER_IDS=" "SCAN_PUBLIC_PILOT_EXPIRES_AT=0" "$ADMIN_500_MARKER=" > "$TMP/config.log" 2>&1; then
      refuse "paid configuration write failed after intake was closed; state must be re-read"
    fi
    v9_intake_readback paid-prepared || refuse "intake closed but exact V9 paid configuration is unverified"
    verify_staged_gateway paid || refuse "intake closed but the serving gateway changed during paid preparation"
    echo "BASE44_STAGED_PAID_READBACK_VERIFIED source_sha=$SOURCE_SHA gateway_revision=$GATEWAY_REVISION page_cap=$PAID_PAGE_CAP public_intake=closed"
    ;;
  prepare-paid-500-pilot)
    verify_staged_gateway paid-pilot || refuse "serving gateway does not attest the exact named paid pilot"
    v9_intake_readback paid-pilot-prepare || refuse "active paid Standard 150 or pilot configuration is unverified"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
      "SCAN_STAGED_PILOT_OWNER_IDS=$OWNER_ID" "SCAN_PUBLIC_PILOT_EXPIRES_AT=$PUBLIC_PILOT_EXPIRES_AT" \
      "$ADMIN_500_MARKER=" > "$TMP/paid-pilot.log" 2>&1 \
      || refuse "paid pilot configuration write failed"
    v9_intake_readback paid-pilot-prepared || refuse "paid pilot configuration requires fresh readback"
    verify_staged_gateway paid-pilot || refuse "gateway changed while preparing the paid pilot"
    echo "BASE44_PAID_500_PILOT_PREPARED source_sha=$SOURCE_SHA gateway_revision=$GATEWAY_REVISION"
    ;;
  hold-paid-500-pilot)
    v9_intake_readback paid-pilot-hold || refuse "the exact paid pilot cohort is unverified"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "SCAN_PUBLIC_PILOT_EXPIRES_AT=0" "$ADMIN_500_MARKER=" > "$TMP/paid-pilot-hold.log" 2>&1 \
      || refuse "paid pilot hold write failed"
    v9_intake_readback paid-pilot-held || refuse "paid pilot hold requires fresh readback"
    echo "BASE44_PAID_500_PILOT_HELD source_sha=$SOURCE_SHA"
    ;;
  hold-published-pilot)
    v9_intake_readback published-pilot-preflight || refuse "the exact pilot launcher is unverified"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "SCAN_PUBLIC_PILOT_EXPIRES_AT=0" "$ADMIN_500_MARKER=" > "$TMP/pilot-hold.log" 2>&1 \
      || refuse "pilot hold write failed; check the current launcher before continuing"
    v9_intake_readback published-pilot-held || refuse "pilot hold requires a fresh launcher readback"
    echo "BASE44_PUBLISHED_PILOT_LAUNCHES_HELD source_sha=$SOURCE_SHA"
    ;;
  prepare-admin-500-rehearsal)
    v9_intake_readback admin-500-preflight || refuse "the exact V9 runtime is unverified or has another active pilot"
    verify_staged_gateway admin-rehearsal || refuse "the serving gateway does not attest the exact Bright canary"
    verify_admin_rehearsal_worker || refuse "the Bright canary worker is not the verified same-source tagged 0%-traffic revision"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1 \
      || refuse "failed to close new Base44 intake"
    v9_intake_readback admin-500-closed || refuse "Base44 intake is unverified; the rehearsal was not configured"
    verify_staged_gateway admin-rehearsal || refuse "intake closed but the serving gateway changed before rehearsal configuration"
    (( PUBLIC_PILOT_EXPIRES_AT > $(date +%s) )) || refuse "intake closed after the rehearsal expiry"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
      "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=$OWNER_ID" "SCAN_PIPELINE_OWNER_IDS=" \
      "SCAN_STAGED_ROLLOUT_SCOPE=off" "SCAN_STAGED_500_ENTITLED_ENABLED=false" "SCAN_STAGED_PILOT_OWNER_IDS=" \
      "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=false" \
      "$ADMIN_500_MARKER=$OWNER_ID" "SCAN_PUBLIC_PILOT_EXPIRES_AT=$PUBLIC_PILOT_EXPIRES_AT" \
      > "$TMP/admin-rehearsal.log" 2>&1 || refuse "intake closed but the rehearsal configuration write failed"
    v9_intake_readback admin-500-prepared || refuse "intake closed but the exact V9 rehearsal could not be verified"
    verify_staged_gateway admin-rehearsal || refuse "intake closed but the serving gateway changed during rehearsal preparation"
    echo "BASE44_ADMIN_500_REHEARSAL_PREPARED source_sha=$SOURCE_SHA gateway_revision=$GATEWAY_REVISION public_intake=closed"
    ;;
  hold-admin-500-rehearsal)
    v9_intake_readback admin-500-hold-preflight || refuse "the Bright rehearsal or current pilot could not be verified"
    "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "$ADMIN_500_MARKER=" "SCAN_PUBLIC_PILOT_EXPIRES_AT=0" \
      > "$TMP/admin-rehearsal-hold.log" 2>&1 || refuse "Bright rehearsal hold write failed"
    v9_intake_readback admin-500-held || refuse "Bright rehearsal hold requires fresh exact-launcher readback"
    echo "BASE44_ADMIN_500_REHEARSAL_HELD source_sha=$SOURCE_SHA"
    ;;
  prepare-owner|disable)
    verify_probe_package || refuse "deployed operator package mismatch"
    if [[ "$OPERATION" == prepare-owner ]]; then
      v9_intake_readback preflight || refuse "deployed V9 intake source or dispatcher origin does not match"
      if [[ -n "$PUBLIC_PILOT_EXPIRES_AT" ]]; then
        verify_staged_gateway off || refuse "the serving gateway does not route the named pilot to the verified worker"
      fi
    fi
    # Stop *new* Base44 intake first. Leave admission enabled so committed
    # scans can reconcile/release coordinator claims and finish persistence.
    if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set "BETA_SCAN_INTAKE_ENABLED=false" > "$TMP/intake.log" 2>&1; then
      refuse "failed to close new Base44 intake"
    fi
    if [[ "$OPERATION" == prepare-owner ]]; then
      # 500 stays entitlement-controlled, no owner grant or client cap selector.
      pilot_expiry_setting=()
      if [[ -n "$PUBLIC_PILOT_EXPIRES_AT" ]]; then
        verify_staged_gateway off || refuse "intake closed but the serving gateway changed before pilot configuration"
        pilot_expiry_setting+=("SCAN_PUBLIC_PILOT_EXPIRES_AT=$PUBLIC_PILOT_EXPIRES_AT" "$ADMIN_500_MARKER=")
      fi
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=staged" "SCAN_STAGED_OWNER_IDS=$OWNER_ID" \
        "SCAN_STAGED_ROLLOUT_SCOPE=off" "SCAN_STAGED_500_ENTITLED_ENABLED=false" "SCAN_STAGED_PILOT_OWNER_IDS=" \
        "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=false" \
        ${pilot_expiry_setting[@]+"${pilot_expiry_setting[@]}"} > "$TMP/config.log" 2>&1; then
        refuse "staged config write failed after intake was closed; state must be re-read"
      fi
    else
      # Does NOT remove a worker tag/queue or disable task execution.
      if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
        "SCAN_PIPELINE_MODE=monolith" "SCAN_STAGED_OWNER_IDS=" \
        "SCAN_STAGED_ROLLOUT_SCOPE=off" "SCAN_STAGED_500_ENTITLED_ENABLED=false" "SCAN_STAGED_PILOT_OWNER_IDS=" \
        "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=false" "$ADMIN_500_MARKER=" > "$TMP/config.log" 2>&1; then
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
    if [[ "$OPERATION" == prepare-owner ]]; then
      v9_intake_readback prepared || refuse "intake closed but the exact V9 pilot cohort or dispatcher origin could not be verified"
      if [[ -n "$PUBLIC_PILOT_EXPIRES_AT" ]]; then
        verify_staged_gateway off || refuse "intake closed but the serving gateway changed during pilot preparation"
      fi
      echo "BASE44_STAGED_CONFIG_READBACK_VERIFIED mode=$OPERATION source_sha=$SOURCE_SHA public_intake=closed v9_attested=true pilot_cohort_matches=true"
    else
      echo "BASE44_STAGED_CONFIG_READBACK_VERIFIED mode=$OPERATION source_sha=$SOURCE_SHA public_intake=closed v9_attested=false"
    fi
    ;;
esac
