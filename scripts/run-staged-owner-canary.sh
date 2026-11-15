#!/usr/bin/env bash
# Run exactly one explicitly confirmed, existing-owner Standard-150 canary.
# This never provisions projects, grants access, changes a cohort, or freezes production.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
EXPECTED_OWNER_USER_ID="${EXPECTED_OWNER_USER_ID:-}"
PROJECT_ID="${PROJECT_ID:-}"
TARGET_URL="${TARGET_URL:-}"
EXPECTED_PAGE_CAP="${EXPECTED_PAGE_CAP:-}"
REQUEST_ID="${REQUEST_ID:-}"
ACCEPTANCE_OUTPUT="${ACCEPTANCE_OUTPUT:-}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-900}"
POLL_SECONDS="${POLL_SECONDS:-5}"
CONFIRM="${CONFIRM:-}"

if [[ "$APP_ID" != 6a498732ec779dfaaeab0e53 ]]; then
  echo "Refusing: this canary is pinned to the FixList application." >&2
  exit 2
fi
if [[ ! "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ || ! "$EXPECTED_OWNER_USER_ID" =~ ^[A-Za-z0-9_-]{6,160}$ || ! "$PROJECT_ID" =~ ^[A-Za-z0-9_-]{6,160}$ || ! "$REQUEST_ID" =~ ^[A-Za-z0-9_-]{8,160}$ || "$EXPECTED_PAGE_CAP" != 150 || -z "$TARGET_URL" || -z "$ACCEPTANCE_OUTPUT" ]]; then
  echo "Refusing: exact SOURCE_SHA, EXPECTED_OWNER_USER_ID, PROJECT_ID, TARGET_URL, EXPECTED_PAGE_CAP=150, stable REQUEST_ID and ACCEPTANCE_OUTPUT are required." >&2
  exit 2
fi
if [[ ! "$MAX_WAIT_SECONDS" =~ ^[0-9]+$ || ! "$POLL_SECONDS" =~ ^[0-9]+$ ]] || (( MAX_WAIT_SECONDS < 1 || MAX_WAIT_SECONDS > 1800 || POLL_SECONDS < 1 || POLL_SECONDS > 60 )); then
  echo "Refusing: MAX_WAIT_SECONDS must be 1..1800 and POLL_SECONDS must be 1..60." >&2
  exit 2
fi
if [[ "$ACCEPTANCE_OUTPUT" != /* || -e "$ACCEPTANCE_OUTPUT" || -L "$ACCEPTANCE_OUTPUT" || ! -d "$(dirname "$ACCEPTANCE_OUTPUT")" ]]; then
  echo "Refusing: ACCEPTANCE_OUTPUT must name a new absolute file in an existing directory; prior evidence is never overwritten." >&2
  exit 2
fi
EXPECTED_CONFIRM="RUN-ONE-STAGED-OWNER-CANARY:${SOURCE_SHA}:${EXPECTED_OWNER_USER_ID}:${PROJECT_ID}:${REQUEST_ID}"
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing: CONFIRM must exactly authorize one scan: '$EXPECTED_CONFIRM'." >&2
  exit 2
fi
for executable in node deno timeout; do
  command -v "$executable" >/dev/null 2>&1 || { echo "Refusing: $executable is required." >&2; exit 2; }
done

node - "$REPO_ROOT" "$ACCEPTANCE_OUTPUT" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const [checkout, output] = process.argv.slice(2);
const root = fs.realpathSync(checkout);
const parent = path.dirname(path.resolve(output));
if (fs.realpathSync(parent) !== parent) throw new Error('Refusing: acceptance output parent must not use symlink aliases');
const relative = path.relative(root, parent);
if (!relative || (relative !== '..' && !relative.startsWith('..' + path.sep))) throw new Error('Refusing: acceptance output must be outside the source checkout');
if (fs.existsSync(output)) throw new Error('Refusing: prior acceptance evidence must not be overwritten');
NODE

# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
# shellcheck source=scripts/lib/base44-pinned-cli.sh
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

node --input-type=module - "$REPO_ROOT" "$APP_ID" "$SOURCE_SHA" "$EXPECTED_OWNER_USER_ID" "$PROJECT_ID" "$TARGET_URL" "$REQUEST_ID" "$MAX_WAIT_SECONDS" "$POLL_SECONDS" > "$TMP/config.js" <<'NODE'
import {pathToFileURL} from 'node:url';
import {join} from 'node:path';
const [root, appId, sourceSha, ownerId, projectId, rawTarget, requestId, maxWait, pollSeconds] = process.argv.slice(2);
let target;
try { target = new URL(rawTarget); } catch { throw new Error('Refusing invalid TARGET_URL'); }
if (target.protocol !== 'https:' || target.username || target.password || target.hash) throw new Error('Refusing: TARGET_URL must be an HTTPS URL without credentials or fragment');
const {RELEASE_FINGERPRINT} = await import(pathToFileURL(join(root, 'base44/functions/startStandardScanJobV9/generatedReleaseContract.js')));
if (!/^[a-f0-9]{16}$/.test(RELEASE_FINGERPRINT)) throw new Error('Refusing: release fingerprint unavailable');
console.log('const config = ' + JSON.stringify({appId, sourceSha, ownerId, projectId, targetUrl:target.href, requestId, maxWait:Number(maxWait), pollSeconds:Number(pollSeconds), expectedFingerprint:RELEASE_FINGERPRINT}) + ';');
NODE

fixlist_install_base44_cli "$TMP/pinned-cli"
cat > "$TMP/canary.js" <<'JS'
const report = {
  schema_version:'staged_owner_canary_v1', production_freeze:false,
  source_sha:config.sourceSha, local_source_verified:true,
  deployed_git_source_sha:{state:'unverified', reason:'The customer API does not attest a deployed Git SHA.'},
  app_id:config.appId, expected_owner_user_id:config.ownerId,
  verified_owner_user_id:null, project_id:config.projectId, target_url:config.targetUrl,
  request_id:config.requestId, expected_page_cap:150,
  expected_release_fingerprint:config.expectedFingerprint,
  scan_id:null, accepted:false, acceptance_verified:false, terminal_status:null,
  authority_verified:false, release_fingerprint:null, release_contract_current:false,
  customer_reopen_verified:false, customer_reopen_fix_list_id:null,
  durable_worker_owned:false, ownership_evidence:[], page_cap:null, pages_crawled:null,
  pipeline_mode:null, last_committed_batch:null, committed_batch_count:null,
  duration_ms:null, worker_peak_memory_bytes:null, progress:[], unverified:[], failure_code:null,
};
const deadline = Date.now() + config.maxWait * 1000;
class CanaryFailure extends Error { constructor(code) { super(code); this.code = code; } }
function requireCondition(value, code) { if (!value) throw new CanaryFailure(code); }
async function bounded(operation) {
  const remaining = Math.min(30000, deadline - Date.now());
  requireCondition(remaining > 0, 'canary_timeout');
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => { timer = setTimeout(() => reject(new CanaryFailure('operation_timeout')), remaining); })]);
  } finally { clearTimeout(timer); }
}
function body(response) { return response?.data && typeof response.data === 'object' ? response.data : response; }
function canonicalUrl(value) { try { return new URL(String(value)).href; } catch { return ''; } }
function finitePositive(value) { return typeof value === 'number' && Number.isFinite(value) && value > 0; }
function safeInteger(value) { return Number.isInteger(value) && value >= 0; }
// A second owner-authenticated result GET must reopen the SAME persisted FixList.
// This verifies customer read-back; it does not attest the deployment SHA or a new login session.
function verifiedCustomerReopen(reopened, original, scanId, projectId, fingerprint) {
  const initialFixListId = String(original?.fix_list_id || '');
  const reopenedFixListId = String(reopened?.fix_list_id || '');
  return /^[A-Za-z0-9_-]{6,160}$/.test(initialFixListId)
    && initialFixListId === reopenedFixListId
    && original?.scan_id === scanId && original?.run?.id === scanId && original?.run?.status === 'complete'
    && reopened?.success === true && reopened?.access === 'full'
    && reopened?.authority_verified === true && reopened?.release_contract_current === true
    && reopened?.scan_id === scanId && reopened?.run?.id === scanId
    && reopened?.run?.status === 'complete'
    && reopened?.run?.beta_revision_fingerprint === fingerprint
    && reopened?.fixList?.id === reopenedFixListId
    && reopened?.fixList?.scan_run_id === scanId
    && reopened?.fixList?.project_id === projectId;
}
function observe(run) {
  requireCondition(run?.id === report.scan_id && run?.owner_user_id === config.ownerId && run?.project_id === config.projectId, 'scan_identity_mismatch');
  requireCondition(run?.request_id === config.requestId && (run?.idempotency_key || run?.request_id) === config.requestId, 'scan_request_mismatch');
  requireCondition(canonicalUrl(run?.website_url) === config.targetUrl, 'scan_target_mismatch');
  requireCondition(run?.page_cap === 150 && run?.scan_mode === 'standard_150', 'scan_cap_mismatch');
  requireCondition(run?.pipeline_mode === 'staged', 'scan_pipeline_mismatch');
  const sample = {observed_at:new Date().toISOString(), status:String(run.status || ''), pages_crawled:safeInteger(run.pages_crawled) ? run.pages_crawled : null, pages_planned:safeInteger(run.pages_planned) ? run.pages_planned : null, last_committed_batch:safeInteger(run.last_committed_batch) ? run.last_committed_batch : null};
  requireCondition(sample.pages_crawled === null || sample.pages_crawled <= 150, 'scan_progress_invalid');
  requireCondition(sample.pages_planned === null || sample.pages_planned <= 150, 'scan_progress_invalid');
  const previous = report.progress.at(-1);
  requireCondition(!previous || previous.pages_crawled === null || sample.pages_crawled === null || sample.pages_crawled >= previous.pages_crawled, 'scan_progress_regressed');
  if (!previous || JSON.stringify({...sample, observed_at:''}) !== JSON.stringify({...previous, observed_at:''})) report.progress.push(sample);
  return sample;
}
try {
  // Authenticate as the expected application user before reading or starting anything.
  const me = await bounded(() => base44.auth.me());
  requireCondition(me?.id === config.ownerId, 'authenticated_owner_mismatch');
  report.verified_owner_user_id = me.id;
  requireCondition(me.role === 'admin', 'authenticated_owner_not_admin');
  const email = String(me.email || '').trim().toLowerCase();
  requireCondition(Boolean(email), 'owner_email_unavailable');
  const project = await bounded(() => base44.entities.BusinessProject.get(config.projectId));
  requireCondition(project?.id === config.projectId && project?.owner_user_id === config.ownerId, 'project_owner_mismatch');
  requireCondition(canonicalUrl(project.website_url) === config.targetUrl, 'project_target_mismatch');
  const byOwner = await bounded(() => base44.entities.Access.filter({owner_user_id:config.ownerId}));
  const byEmail = await bounded(() => base44.entities.Access.filter({user_email:email}));
  requireCondition(Array.isArray(byOwner) && Array.isArray(byEmail), 'access_records_unavailable');
  const rows = [...new Map([...byOwner, ...byEmail].filter(row => row?.id).map(row => [String(row.id), row])).values()];
  requireCondition(rows.length === 1, 'access_record_not_unique');
  const access = rows[0];
  requireCondition(access.owner_user_id === config.ownerId && String(access.user_email || '').trim().toLowerCase() === email, 'access_owner_mismatch');
  requireCondition(access.has_full_access === true && access.access_status === 'active' && access.plan_id === 'standard150_lifetime' && access.app_id === config.appId, 'access_not_active');
  requireCondition((access.page_cap ?? 150) === 150, 'access_cap_not_150');
  const datedGrant = Number.isFinite(Date.parse(String(access.granted_at || '')));
  const paidGrant = access.grant_source === 'stripe_checkout' && Boolean(String(access.stripe_checkout_session_id || '').trim()) && Number.isFinite(Date.parse(String(access.paid_at || '')));
  const manualGrant = access.grant_source === 'manual_grant' && datedGrant;
  const ownerGrant = access.grant_source === 'owner_test' && datedGrant && email === 'bright4862@gmail.com' && me.id === '6a498da58ef5cec1f5cd4486';
  requireCondition(paidGrant || manualGrant || ownerGrant, 'access_grant_unverified');

  // One start call only. The operator must reuse REQUEST_ID to recover a lost response.
  const accepted = body(await bounded(() => base44.functions.invoke('startStandardScanJobV9', {
    request_id:config.requestId, idempotency_key:config.requestId,
    project_id:config.projectId, website_url:config.targetUrl, submitted_url:config.targetUrl,
    scan_mode:'standard_150', source:'staged_owner_canary',
  })));
  requireCondition(accepted?.success === true && accepted?.accepted === true, 'scan_not_accepted');
  report.accepted = true;
  requireCondition(accepted.page_cap === 150 && accepted.pipeline_mode === 'staged' && accepted.scan_mode === 'standard_150', 'accepted_scan_contract_mismatch');
  report.scan_id = String(accepted.scan_id || accepted.scan_run_id || '');
  requireCondition(/^[A-Za-z0-9_-]{6,160}$/.test(report.scan_id), 'accepted_scan_identity_missing');
  let projection;
  let run;
  while (Date.now() < deadline) {
    projection = body(await bounded(() => base44.functions.invoke('getCustomerScanResultV9', {scan_id:report.scan_id})));
    requireCondition(projection?.success === true && projection.scan_id === report.scan_id, 'customer_result_unavailable');
    run = await bounded(() => base44.entities.ScanRun.get(report.scan_id));
    observe(run);
    if (['complete', 'limited', 'failed', 'cancelled'].includes(String(run.status)) && projection.run?.status === run.status) break;
    await new Promise(resolve => setTimeout(resolve, Math.min(config.pollSeconds * 1000, Math.max(1, deadline - Date.now()))));
  }
  report.terminal_status = String(run?.status || '');
  requireCondition(['complete', 'limited', 'failed', 'cancelled'].includes(report.terminal_status), 'canary_timeout');
  if (report.terminal_status === 'complete') {
    // A distinct, fresh user-scoped invocation after terminal persistence.
    // The polling projection alone cannot establish that the result reopens.
    const reopened = body(await bounded(() => base44.functions.invoke('getCustomerScanResultV9', {
      action:'get', scan_id:report.scan_id,
    })));
    report.customer_reopen_verified = verifiedCustomerReopen(
      reopened, projection, report.scan_id, config.projectId, config.expectedFingerprint,
    );
    if (report.customer_reopen_verified) report.customer_reopen_fix_list_id = reopened.fix_list_id;
  }
  report.authority_verified = projection.authority_verified === true;
  report.release_contract_current = projection.release_contract_current === true;
  report.release_fingerprint = /^[a-f0-9]{16}$/.test(String(projection.run?.beta_revision_fingerprint || '')) ? projection.run.beta_revision_fingerprint : null;
  report.page_cap = run.page_cap;
  report.pipeline_mode = run.pipeline_mode;
  report.pages_crawled = safeInteger(run.pages_crawled) ? run.pages_crawled : null;
  report.last_committed_batch = safeInteger(run.last_committed_batch) ? run.last_committed_batch : null;
  report.committed_batch_count = report.last_committed_batch === null ? null : report.last_committed_batch + 1;
  const duration = Date.parse(String(run.completed_at || '')) - Date.parse(String(run.started_at || ''));
  report.duration_ms = finitePositive(duration) ? duration : null;
  const memory = projection.run?.worker_peak_memory_bytes ?? projection.run?.peak_memory_bytes;
  report.worker_peak_memory_bytes = finitePositive(memory) ? memory : null;
  const ownership = run.owner_user_id === config.ownerId && run.project_id === config.projectId && run.request_id === config.requestId && run.pipeline_mode === 'staged'
    && report.committed_batch_count > 0 && projection.run?.advanced_scan_backend === 'python_scanner_api' && projection.run?.deno_fallback_used === false
    && projection.run?.ai_review_backend === 'python_review_api' && projection.run?.python_review_fallback_used === false;
  report.durable_worker_owned = ownership && report.authority_verified;
  if (report.durable_worker_owned) report.ownership_evidence = ['owner_user_id', 'project_id', 'request_id', 'pipeline_mode', 'last_committed_batch', 'python_scanner_api', 'python_review_api', 'authority_verified'];
  const checks = {
    terminal_complete:report.terminal_status === 'complete',
    signed_authority:report.authority_verified && /^[a-f0-9]{64}$/.test(String(run.authority_proof || '')) && Boolean(run.authority_seal_version),
    customer_reopen:report.customer_reopen_verified === true,
    release_fingerprint:report.release_contract_current && report.release_fingerprint === config.expectedFingerprint && run.beta_revision_fingerprint === config.expectedFingerprint,
    staged_150:report.page_cap === 150 && report.pipeline_mode === 'staged',
    durable_ownership:report.durable_worker_owned,
    batch_progress:report.committed_batch_count > 0 && safeInteger(run.pages_planned) && run.pages_planned > 0 && run.pages_planned <= 150 && report.pages_crawled > 0 && report.pages_crawled <= run.pages_planned,
    duration:report.duration_ms !== null,
    measured_memory:report.worker_peak_memory_bytes !== null,
  };
  report.unverified = Object.entries(checks).filter(([, verified]) => !verified).map(([name]) => name);
  report.acceptance_verified = report.unverified.length === 0;
  if (!report.acceptance_verified) report.failure_code = 'canary_evidence_incomplete';
} catch (error) {
  report.failure_code = error instanceof CanaryFailure ? error.code : 'remote_operation_failed';
  report.unverified = [...new Set([...report.unverified, report.failure_code])];
}
console.log('FIXLIST_STAGED_OWNER_CANARY=' + JSON.stringify(report));
JS

set +e
cat "$TMP/config.js" "$TMP/canary.js" | timeout --signal=TERM "$((MAX_WAIT_SECONDS + 120))" "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod > "$TMP/runtime-output" 2> "$TMP/runtime-error"
CLI_STATUS=$?
set -e
# Never print SDK responses, user email, authority proofs, credentials or raw evidence.
node - "$TMP/runtime-output" "$ACCEPTANCE_OUTPUT" "$CLI_STATUS" "$SOURCE_SHA" "$EXPECTED_OWNER_USER_ID" "$PROJECT_ID" "$REQUEST_ID" "$TMP/config.js" <<'NODE'
const fs = require('node:fs');
const [input, output, status, sourceSha, ownerId, projectId, requestId, configPath] = process.argv.slice(2);
const configSource = fs.readFileSync(configPath, 'utf8').trim();
const configPrefix = 'const config = ';
if (!configSource.startsWith(configPrefix) || !configSource.endsWith(';')) throw new Error('Malformed locally pinned canary config');
const pinned = JSON.parse(configSource.slice(configPrefix.length, -1));
if (pinned.sourceSha !== sourceSha || pinned.ownerId !== ownerId
    || pinned.projectId !== projectId || pinned.requestId !== requestId) {
  throw new Error('Canary receipt configuration identity mismatch');
}
// The CLI is a transport, not an independent witness of evidence acceptance.
// Refuse multiple stdout reports, foreign identities, or unsupported success claims.
function parseCanaryReceipt(stdout, expected) {
  const prefix = 'FIXLIST_STAGED_OWNER_CANARY=';
  const makeFailure = code => ({
    schema_version:'staged_owner_canary_v1', production_freeze:false,
    source_sha:expected.sourceSha, app_id:expected.appId,
    expected_owner_user_id:expected.ownerId, verified_owner_user_id:null,
    project_id:expected.projectId, target_url:expected.targetUrl,
    request_id:expected.requestId, expected_page_cap:150,
    expected_release_fingerprint:expected.fingerprint,
    accepted:false, acceptance_verified:false, failure_code:code,
    unverified:['authenticated_runtime_result'],
  });
  const plain = value => value !== null && typeof value === 'object'
    && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
  const lines = stdout.split(/\r?\n/).filter(line => line.startsWith(prefix));
  if (lines.length !== 1) return makeFailure(lines.length === 0 ? 'cli_result_unavailable' : 'cli_marker_ambiguous');
  let report;
  try { report = JSON.parse(lines[0].slice(prefix.length)); }
  catch { return makeFailure('cli_report_malformed'); }
  const permitted = new Set([
    'schema_version','production_freeze','source_sha','local_source_verified',
    'deployed_git_source_sha','app_id','expected_owner_user_id','verified_owner_user_id',
    'project_id','target_url','request_id','expected_page_cap','expected_release_fingerprint',
    'scan_id','accepted','acceptance_verified','terminal_status','authority_verified',
    'release_fingerprint','release_contract_current','customer_reopen_verified',
    'customer_reopen_fix_list_id','durable_worker_owned','ownership_evidence',
    'page_cap','pages_crawled','pipeline_mode','last_committed_batch',
    'committed_batch_count','duration_ms','worker_peak_memory_bytes','progress',
    'unverified','failure_code',
  ]);
  if (!plain(report) || Object.keys(report).some(key => !permitted.has(key))
      || !plain(report.deployed_git_source_sha)
      || report.deployed_git_source_sha.state !== 'unverified'
      || Object.keys(report.deployed_git_source_sha).some(key => !['state','reason'].includes(key))
      || typeof report.deployed_git_source_sha.reason !== 'string'
      || !Array.isArray(report.progress) || report.progress.length > 2000
      || !report.progress.every(row => plain(row)
        && Object.keys(row).every(key => ['observed_at','status','pages_crawled','pages_planned','last_committed_batch'].includes(key))
        && typeof row.observed_at === 'string' && !Number.isNaN(Date.parse(row.observed_at))
        && typeof row.status === 'string'
        && ['pages_crawled','pages_planned','last_committed_batch'].every(key =>
          row[key] === null || (Number.isSafeInteger(row[key]) && row[key] >= 0)))
      || !Array.isArray(report.unverified) || report.unverified.length > 100
      || !report.unverified.every(value => typeof value === 'string' && value.length <= 128)
      || !Array.isArray(report.ownership_evidence) || report.ownership_evidence.length > 32
      || !report.ownership_evidence.every(value => typeof value === 'string' && value.length <= 128)
      || typeof report.acceptance_verified !== 'boolean') {
    return makeFailure('cli_report_invalid');
  }
  if (report.schema_version !== 'staged_owner_canary_v1'
      || report.production_freeze !== false || report.local_source_verified !== true
      || report.source_sha !== expected.sourceSha || report.app_id !== expected.appId
      || report.expected_owner_user_id !== expected.ownerId
      || report.project_id !== expected.projectId || report.target_url !== expected.targetUrl
      || report.request_id !== expected.requestId
      || report.expected_page_cap !== 150
      || report.expected_release_fingerprint !== expected.fingerprint) {
    return makeFailure('cli_report_identity_mismatch');
  }
  if (report.acceptance_verified === true) {
    const idPattern = /^[A-Za-z0-9_-]{6,160}$/;
    const positive = value => Number.isSafeInteger(value) && value > 0;
    if (report.accepted !== true || report.verified_owner_user_id !== expected.ownerId
        || !idPattern.test(String(report.scan_id || ''))
        || !idPattern.test(String(report.customer_reopen_fix_list_id || ''))
        || report.terminal_status !== 'complete'
        || report.authority_verified !== true
        || report.release_contract_current !== true
        || report.customer_reopen_verified !== true
        || report.durable_worker_owned !== true
        || report.ownership_evidence.includes('authority_verified') !== true
        || report.release_fingerprint !== expected.fingerprint
        || report.page_cap !== 150 || report.pipeline_mode !== 'staged'
        || !positive(report.pages_crawled) || report.pages_crawled > 150
        || !Number.isSafeInteger(report.last_committed_batch) || report.last_committed_batch < 0
        || report.committed_batch_count !== report.last_committed_batch + 1
        || !positive(report.duration_ms) || !positive(report.worker_peak_memory_bytes)
        || report.progress.length === 0 || report.unverified.length !== 0
        || report.failure_code !== null) {
      return makeFailure('cli_success_unsubstantiated');
    }
  }
  return report;
}
// End of pure receipt-parser boundary.
let report = parseCanaryReceipt(fs.readFileSync(input, 'utf8'), {
  sourceSha, ownerId, projectId, requestId, appId:pinned.appId,
  targetUrl:pinned.targetUrl, fingerprint:pinned.expectedFingerprint,
});
if (Number(status) !== 0) {
  report.acceptance_verified = false;
  report.failure_code = 'cli_execution_failed';
  report.unverified = [...new Set([...(report.unverified || []), 'cli_execution'])];
}
const temporary = output + '.tmp-' + process.pid;
fs.writeFileSync(temporary, JSON.stringify(report, null, 2) + '\n', {mode:0o600, flag:'wx'});
fs.linkSync(temporary, output);
fs.unlinkSync(temporary);
if (report.acceptance_verified !== true) {
  console.error(`Staged owner canary unverified (${report.failure_code || 'missing_evidence'}); filtered report saved.`);
  process.exit(1);
}
console.log('STAGED_OWNER_CANARY_VERIFIED');
console.log(`scan_id=${report.scan_id}`);
console.log(`source_sha=${report.source_sha}`);
console.log('production_freeze=false');
NODE
