#!/usr/bin/env node
// Add only the staged schema contract through named entity PUTs. No bulk sync.
//
// Offline: plan|compare --inventory FILE --source-sha SHA --report NEW_FILE
// Live: verify|apply|rollback --source-sha SHA --report NEW_FILE
// Mutations also require --generation N and the exact confirmation printed below.
// Rollback requires --receipt APPLY_REPORT and refuses active or staged records.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {diffEntity, normalizeProperty, readLocalSchema} from './base44_authority_schema.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const APP_ID = '6a498732ec779dfaaeab0e53';
export const STAGED_SCHEMA_ENTITIES = Object.freeze(['ScanRun', 'FixList', 'FixItem', 'Access']);
const ADDITIONS = Object.freeze({
  ScanRun: ['page_cap', 'pipeline_mode', 'pages_planned', 'workspace_cleanup_state', 'workspace_cleanup_completed_at', 'last_committed_batch'],
  FixItem: ['affected_page_count', 'affected_page_count_is_lower_bound', 'template_impact_estimates'],
  Access: ['page_cap'],
});
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const requireCondition = (condition, reason) => { if (!condition) throw new Error(`Refusing staged schema operation: ${reason}`); };
const canonical = value => Array.isArray(value) ? value.map(canonical) : object(value)
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const equal = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
const digest = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const localSchemas = () => Object.fromEntries(STAGED_SCHEMA_ENTITIES.map(name => [name, readLocalSchema(name)]));
export const receiptDigest = receipt => digest(receipt);

export function compareStagedSchemas(schemas, local = localSchemas()) {
  return STAGED_SCHEMA_ENTITIES.map(name => diffEntity(name, local[name], schemas?.[name]));
}

export function planStagedSchemas(schemas, local = localSchemas()) {
  requireCondition(object(schemas), 'four-entity inventory required');
  const after = structuredClone(schemas), operations = [];
  for (const name of STAGED_SCHEMA_ENTITIES) {
    const schema = after[name];
    requireCondition(object(schema) && schema.name === name && object(schema.properties), `${name} schema missing or misnamed`);
    for (const property of ADDITIONS[name] || []) {
      requireCondition(object(local[name]?.properties?.[property]), `local allowlisted property ${name}.${property} missing`);
      if (!Object.hasOwn(schema.properties, property)) {
        requireCondition(!local[name].required?.includes(property), `new required property ${name}.${property}`);
        schema.properties[property] = structuredClone(local[name].properties[property]);
        operations.push({entity: name, kind: 'add_property', property});
      }
    }
    if (name === 'ScanRun') {
      const remoteMode = schema.properties.scan_mode, localMode = local.ScanRun.properties.scan_mode;
      requireCondition(object(remoteMode) && Array.isArray(remoteMode.enum), 'ScanRun.scan_mode contract missing');
      if (!remoteMode.enum.includes('standard_500')) {
        const widened = {...remoteMode, enum: [...remoteMode.enum, 'standard_500']};
        requireCondition(equal(normalizeProperty(localMode, widened), localMode), 'ScanRun.scan_mode has unrelated drift');
        schema.properties.scan_mode = widened;
        operations.push({entity: name, kind: 'append_enum', property: 'scan_mode', value: 'standard_500'});
      }
    }
  }
  const comparison = compareStagedSchemas(after, local);
  requireCondition(comparison.every(row => row.status === 'match'), `schema drift beyond staged additions (${comparison.filter(row => row.status !== 'match').map(row => row.entity).join(',')})`);
  return {decision: operations.length ? 'apply' : 'match', operations, after, comparison, contract_sha256: digest(local)};
}

// Only newly added properties may have Base44's documented metadata omissions.
// Every pre-existing property, RLS rule, and remote annotation stays identical.
function matchesExpected(expected, observed, operations) {
  if (!object(observed)) return false;
  const normalized = structuredClone(observed);
  for (const operation of operations) {
    if (operation.kind !== 'add_property') continue;
    const property = normalized[operation.entity]?.properties?.[operation.property];
    const wanted = expected[operation.entity]?.properties?.[operation.property];
    if (property && wanted && equal(normalizeProperty(wanted, property), wanted)) {
      normalized[operation.entity].properties[operation.property] = structuredClone(wanted);
    }
  }
  return equal(expected, normalized);
}

export function assertRollbackRows(evidence, operations) {
  requireCondition(evidence?.complete === true && object(evidence.rows), 'rollback row inventory is unverified');
  const counts = {};
  for (const name of ['ScanRun', 'FixItem', 'Access']) {
    const rows = evidence.rows[name];
    requireCondition(Array.isArray(rows), `${name} rollback rows missing`);
    counts[name] = rows.length;
    for (const row of rows) {
      requireCondition(object(row) && typeof row.id === 'string' && row.id, `${name} rollback row is malformed`);
      if (name === 'ScanRun') {
        requireCondition(['complete', 'limited', 'failed', 'cancelled'].includes(row.status), 'active or unknown ScanRun status blocks rollback');
        requireCondition(!row.pipeline_mode || row.pipeline_mode === 'monolith', 'staged ScanRun blocks rollback');
        requireCondition(row.scan_mode !== 'standard_500' && (row.page_cap == null || row.page_cap === 150), 'large-cap ScanRun blocks rollback');
        requireCondition(['pages_planned', 'last_committed_batch', 'workspace_cleanup_state', 'workspace_cleanup_completed_at'].every(key => row[key] == null || row[key] === ''), 'retained staged ScanRun evidence blocks rollback');
      } else if (name === 'Access') {
        requireCondition(row.page_cap == null || row.page_cap === 150, '500 or unknown Access entitlement blocks rollback');
      } else {
        const removed = operations.filter(operation => operation.entity === name && operation.kind === 'add_property');
        requireCondition(removed.every(({property}) => row[property] == null || (Array.isArray(row[property]) && row[property].length === 0)), 'retained FixItem evidence blocks rollback');
      }
    }
  }
  return {state: 'clear', complete: true, examined: counts};
}

function rollbackPlan(receipt, schemas, local, environment) {
  requireCondition(receipt?.schema_version === 'fixlist_staged_schema_v1' && receipt.status === 'applied_verified'
    && receipt.readback_verified === true && receipt.execution_environment === environment
    && receipt.live_verified === (environment === 'production')
    && receipt.app_id === APP_ID && /^[a-f0-9]{40}$/.test(receipt.source_sha || ''), 'verified apply receipt from this environment required');
  const original = planStagedSchemas(receipt.before_schemas, local);
  requireCondition(receipt.contract_sha256 === digest(local) && equal(receipt.operations, original.operations)
    && matchesExpected(original.after, receipt.after_schemas, original.operations), 'receipt contract or additions differ from this source');
  requireCondition(matchesExpected(receipt.after_schemas, schemas, receipt.operations), 'live inventory differs from the verified apply receipt');
  const after = structuredClone(schemas);
  for (const operation of receipt.operations) {
    const properties = after[operation.entity].properties;
    if (operation.kind === 'add_property') delete properties[operation.property];
    else properties.scan_mode.enum = properties.scan_mode.enum.filter(value => value !== 'standard_500');
  }
  requireCondition(equal(after, receipt.before_schemas), 'rollback would change more than the receipt additions');
  return {operations: receipt.operations, after};
}

function options(argv) {
  const action = argv[0], values = {};
  requireCondition(['plan', 'compare', 'verify', 'apply', 'rollback'].includes(action), 'expected plan, compare, verify, apply or rollback');
  const allowed = new Set(['source-sha', 'report', 'inventory', 'generation', 'confirm', 'receipt']);
  for (let i = 1; i < argv.length; i += 2) {
    const name = argv[i].replace(/^--/, '');
    requireCondition(argv[i].startsWith('--') && allowed.has(name) && !Object.hasOwn(values, name) && argv[i + 1], 'invalid, duplicate or missing argument');
    values[name] = argv[i + 1];
  }
  requireCondition(/^[a-f0-9]{40}$/.test(values['source-sha'] || ''), 'exact source SHA required');
  requireCondition(values.report && path.isAbsolute(values.report) && !fs.existsSync(values.report), 'new absolute report file required');
  const parent = path.dirname(values.report), relative = path.relative(ROOT, parent);
  requireCondition(fs.realpathSync(parent) === parent && relative && (relative === '..' || relative.startsWith('..' + path.sep)), 'report parent must be outside the checkout without symlink aliases');
  requireCondition(!fs.lstatSync(parent).isSymbolicLink(), 'report parent is a symlink');
  requireCondition((process.env.BASE44_APP_ID || APP_ID) === APP_ID, 'unexpected Base44 app');
  if (['plan', 'compare'].includes(action)) requireCondition(values.inventory && !values.generation && !values.confirm && !values.receipt, 'offline inventory required without mutation inputs');
  else requireCondition(!values.inventory, 'live operation cannot use a saved inventory');
  if (['apply', 'rollback'].includes(action)) {
    requireCondition(/^(0|[1-9][0-9]*)$/.test(values.generation || '') && Number.isSafeInteger(Number(values.generation)), 'exact barrier generation required');
    const prefix = `${action === 'apply' ? 'APPLY' : 'ROLLBACK'}-STAGED-SCHEMA:${values['source-sha']}:${values.generation}`;
    const receipt = action === 'rollback' ? JSON.parse(fs.readFileSync(values.receipt || '', 'utf8')) : null;
    requireCondition(values.confirm === prefix + (receipt ? ':' + receiptDigest(receipt) : ''), `confirmation must equal ${prefix}${receipt ? ':<apply-receipt-sha256>' : ''}`);
    values.receiptDocument = receipt;
  } else requireCondition(!values.generation && !values.confirm && !values.receipt, 'read-only operation cannot use mutation inputs');
  return {action, ...values};
}

function invoke(command, args, env = process.env) {
  try { return execFileSync(command, args, {cwd: ROOT, env, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe']}); }
  catch (error) { throw new Error(`Staged schema prerequisite failed: ${path.basename(command)}${error.status == null ? '' : ` (exit ${error.status})`}`); }
}
function sourceGuard(sha) {
  invoke('/bin/bash', ['-c', 'source "$1"; fixlist_require_exact_main "$2" "$3" "$3"', 'staged-schema', path.join(ROOT, 'scripts/lib/release-source-guard.sh'), ROOT, sha]);
}
function ownerGuard() {
  const shell = 'set -euo pipefail; source "$1"; staged_tmp="$(mktemp -d)"; trap \'rm -rf "$staged_tmp"\' EXIT; fixlist_install_base44_cli "$staged_tmp"; fixlist_require_base44_owner "$2" "$staged_tmp/whoami" "$3"';
  invoke('/bin/bash', ['-c', shell, 'staged-schema', path.join(ROOT, 'scripts/lib/base44-pinned-cli.sh'), process.env.BASE44_EXPECTED_OWNER || '', APP_ID]);
}
function barrierGuard(config) {
  invoke('/bin/bash', [path.join(ROOT, 'scripts/fixlist-cloud-operator.sh')], {...process.env,
    OPERATION: 'verify-zero-admission-obligations', SOURCE_SHA: config['source-sha'],
    CONFIRM: `VERIFY-ZERO-ADMISSION:${config['source-sha']}:${config.generation}`,
    BARRIER_EXPECTED_GENERATION: config.generation, BARRIER_EXPECTED_PRIOR_MODE: 'closed',
    GCP_OPERATOR_SERVICE_ACCOUNT: process.env.GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT || process.env.GCP_OPERATOR_SERVICE_ACCOUNT || '',
  });
}

async function main(argv) {
  const config = options(argv), local = localSchemas();
  // Reserve the evidence destination before any remote operation. In
  // particular, a dangling symlink must fail before the first schema PUT.
  const reportDescriptor = fs.openSync(config.report, 'wx', 0o600);
  // Append-only, fsynced evidence survives a killed orchestrator. A pre-PUT
  // entry is an intent, NOT proof of a successful provider mutation.
  const journalPath = config.report + '.journal.ndjson';
  const journalDescriptor = ['apply', 'rollback'].includes(config.action)
    ? fs.openSync(journalPath, 'wx', 0o600) : null;
  let journalSequence = 0;
  const journal = (event, details = {}) => {
    if (journalDescriptor === null) return;
    const entry = {version: 'fixlist_staged_schema_mutation_journal_v1',
      sequence: ++journalSequence, action: config.action, source_sha: config['source-sha'],
      app_id: APP_ID, event, ...details};
    fs.writeSync(journalDescriptor, JSON.stringify(entry) + '\n');
    fs.fsyncSync(journalDescriptor);
  };
  const environment = ['plan', 'compare'].includes(config.action) ? 'offline_inventory'
    : process.env.BASE44_SCHEMA_API_FIXTURE ? 'localhost_fixture' : 'production';
  const report = {schema_version: 'fixlist_staged_schema_v1', action: config.action, source_sha: config['source-sha'],
    app_id: APP_ID, contract_sha256: digest(local), observed_at: new Date().toISOString(),
    execution_environment: environment, readback_verified: false, live_verified: false,
    local_source_verified: false, status: 'failed', operations: [], completed_entities: [],
    mutation_journal: journalDescriptor === null ? null : journalPath};
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'fixlist-staged-schema-'));
  let sequence = 0;
  const fetchSchemas = () => {
    const file = path.join(temporary, `inventory-${sequence++}.json`);
    invoke(process.execPath, [path.join(ROOT, 'scripts/base44_named_schema_client.mjs'), 'fetch-staged', file]);
    return JSON.parse(fs.readFileSync(file, 'utf8')).schemas;
  };
  let status = 0;
  try {
    journal('started', {execution_environment: environment});
    if (['plan', 'compare'].includes(config.action)) {
      const input = JSON.parse(fs.readFileSync(config.inventory, 'utf8'));
      const schemas = input.schemas || input;
      if (config.action === 'plan') {
        const plan = planStagedSchemas(schemas, local);
        Object.assign(report, {status: 'planned', decision: plan.decision, operations: plan.operations, comparison: plan.comparison});
      } else {
        report.comparison = compareStagedSchemas(schemas, local);
        report.status = report.comparison.every(row => row.status === 'match') ? 'offline_match' : 'offline_drift';
        status = report.status === 'offline_match' ? 0 : 1;
      }
    } else {
      sourceGuard(config['source-sha']); report.local_source_verified = true;
      if (config.action !== 'verify') { barrierGuard(config); report.barrier_generation = Number(config.generation); }
      ownerGuard();
      const before = fetchSchemas(); report.before_schemas = before;
      if (config.action === 'verify') {
        report.comparison = compareStagedSchemas(before, local);
        requireCondition(report.comparison.every(row => row.status === 'match'), 'four-entity live comparison differs');
        report.status = 'live_match'; report.readback_verified = true; report.live_verified = environment === 'production';
      } else {
        const plan = config.action === 'apply' ? planStagedSchemas(before, local) : rollbackPlan(config.receiptDocument, before, local, environment);
        report.operations = plan.operations;
        if (config.action === 'rollback') {
          const file = path.join(temporary, 'rows.json');
          invoke(process.execPath, [path.join(ROOT, 'scripts/base44_named_schema_client.mjs'), 'staged-rows', file]);
          report.rollback_rows = assertRollbackRows(JSON.parse(fs.readFileSync(file, 'utf8')), plan.operations);
          report.apply_receipt_sha256 = receiptDigest(config.receiptDocument);
          report.apply_source_sha = config.receiptDocument.source_sha;
        }
        // Preserve the original complete four-entity baseline before ANY
        // schema PUT. A later retry must not infer that baseline from a partial state.
        journal('planned', {before_schemas: before, operations: plan.operations,
          intended_after_sha256: digest(plan.after), barrier_generation: Number(config.generation)});
        let expected = structuredClone(before);
        const touched = [...new Set(plan.operations.map(operation => operation.entity))].sort();
        for (const name of touched) {
          barrierGuard(config);
          const fresh = fetchSchemas();
          requireCondition(matchesExpected(expected, fresh, plan.operations), 'inventory changed before named PUT');
          const schema = path.join(temporary, `${name}.json`);
          fs.writeFileSync(schema, JSON.stringify(plan.after[name]), {mode: 0o600});
          journal('put_started', {entity: name, before_sha256: digest(expected[name]),
            intended_sha256: digest(plan.after[name])});
          invoke(process.execPath, [path.join(ROOT, 'scripts/base44_named_schema_client.mjs'), 'put-named', name, schema]);
          journal('put_returned', {entity: name});
          expected[name] = structuredClone(plan.after[name]);
          const readback = fetchSchemas(); report.after_schemas = readback;
          requireCondition(matchesExpected(expected, readback, config.action === 'apply' ? plan.operations : []), 'fresh readback changed more than the intended additions');
          journal('readback_verified', {entity: name, schema_sha256: digest(readback[name])});
          expected = readback;
          report.completed_entities.push(name);
        }
        report.after_schemas = fetchSchemas();
        requireCondition(matchesExpected(plan.after, report.after_schemas, config.action === 'apply' ? plan.operations : []), 'final readback differs');
        report.comparison = compareStagedSchemas(report.after_schemas, local);
        report.status = config.action === 'apply' ? 'applied_verified' : 'rolled_back_verified';
        report.readback_verified = true;
        report.live_verified = environment === 'production';
      }
    }
  } catch (error) {
    status = 2;
    report.failure = error instanceof Error ? error.message : 'staged schema operation failed';
    journal('failed', {failure: report.failure});
    process.stderr.write(`${report.failure}\n`);
  } finally {
    fs.rmSync(temporary, {recursive: true, force: true});
    try {
      fs.writeFileSync(reportDescriptor, JSON.stringify(report, null, 2) + '\n');
      fs.fsyncSync(reportDescriptor);
      // Only the persisted JSON report is an apply/rollback receipt. Do not
      // call a crash-interrupted postflight an accepted terminal result.
      journal('report_fsynced', {status: report.status, report_sha256: digest(report)});
    } finally {
      fs.closeSync(reportDescriptor);
      if (journalDescriptor !== null) fs.closeSync(journalDescriptor);
    }
  }
  process.stdout.write(`STAGED_SCHEMA_REPORT status=${report.status} source_sha=${report.source_sha} live_verified=${report.live_verified}\n`);
  return status;
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`${error instanceof Error ? error.message : 'staged schema operation failed'}\n`); process.exitCode = 2; }
}
