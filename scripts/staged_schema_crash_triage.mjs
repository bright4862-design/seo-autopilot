#!/usr/bin/env node
// OFFLINE-ONLY diagnosis of a possibly interrupted Standard 150 schema apply.
// This never contacts Base44, proves provider provenance, or authorizes replay.
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ENTITIES = Object.freeze(['ScanRun', 'FixList', 'FixItem', 'Access']);
const APP_ID = '6a498732ec779dfaaeab0e53';
const VERSION = 'fixlist_staged_schema_mutation_journal_v1';
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const canonical = value => Array.isArray(value) ? value.map(canonical) : isObject(value)
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const digest = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const requireEvidence = (ok, reason) => { if (!ok) throw new Error('Refusing schema crash triage: ' + reason); };

export function classifyStagedApplyJournal(entries, inventory, planned) {
  requireEvidence(Array.isArray(entries) && entries.length >= 2, 'original journal with pre-PUT baseline missing');
  const first = entries[0], witness = entries[1];
  requireEvidence(first?.event === 'started' && witness?.event === 'planned', 'journal lacks pre-PUT planned witness');
  requireEvidence(first.action === 'apply', 'only interrupted apply is supported');
  requireEvidence(/^[a-f0-9]{40}$/.test(first.source_sha) && first.app_id === APP_ID,
    'journal identity is not exact-source GetFixList');
  requireEvidence(Number.isSafeInteger(witness.barrier_generation) && witness.barrier_generation >= 0,
    'journal barrier generation missing');
  const baseline = witness.before_schemas;
  requireEvidence(isObject(baseline) && ENTITIES.every(name => isObject(baseline[name]) && baseline[name].name === name && isObject(baseline[name].properties))
    && Object.keys(baseline).length === ENTITIES.length, 'journal four-entity baseline unavailable');
  requireEvidence(isObject(planned) && Array.isArray(planned.operations) && isObject(planned.after)
    && same(planned.operations, witness.operations) && digest(planned.after) === witness.intended_after_sha256,
    'journal plan disagrees with current source contract');
  const live = inventory?.schemas || inventory;
  requireEvidence(isObject(live) && Object.keys(live).length === ENTITIES.length
    && ENTITIES.every(name => isObject(live[name]) && live[name].name === name && isObject(live[name].properties)),
    'four-entity read-only inventory unavailable');
  const touched = new Set(planned.operations.map(operation => operation.entity));
  let pending = null;
  const ackUncertain = new Set();
  let terminal = false;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    requireEvidence(isObject(e) && e.version === VERSION && e.sequence === i + 1
      && e.action === first.action && e.source_sha === first.source_sha && e.app_id === APP_ID,
      'journal sequence or provenance inconsistent');
    if (i <= 1) continue;
    requireEvidence(!terminal, 'journal contains events after final report');
    if (e.event === 'put_started') {
      requireEvidence(pending === null && touched.has(e.entity), 'unexpected or overlapping PUT attempt');
      pending = {entity:e.entity, phase:'started'};
      ackUncertain.add(e.entity);
    } else if (e.event === 'put_returned') {
      requireEvidence(pending?.entity === e.entity && pending.phase === 'started', 'PUT return without attempt');
      pending.phase = 'returned';
    } else if (e.event === 'readback_verified') {
      requireEvidence(pending?.entity === e.entity && pending.phase === 'returned', 'readback without returned PUT');
      ackUncertain.delete(e.entity);
      pending = null;
    } else if (e.event === 'failed') {
      // A failed attempt may leave the provider PUT uncertain even when local HTTP failed.
    } else if (e.event === 'report_fsynced') {
      terminal = true;
    } else requireEvidence(false, 'unexpected journal event ' + String(e.event));
  }
  const classifications = {};
  for (const name of ENTITIES) {
    const original = same(live[name], baseline[name]);
    const intended = same(live[name], planned.after[name]);
    classifications[name] = original && intended ? 'unchanged' : original ? 'matches_original'
      : intended ? 'matches_intended' : 'unexpected_drift';
  }
  return {
    schema_version: 'staged_schema_crash_triage_v1', action: 'apply', source_sha: first.source_sha,
    barrier_generation: witness.barrier_generation, classification: classifications,
    uncertain_put_entities: [...ackUncertain].sort(),
    assessment: Object.values(classifications).includes('unexpected_drift') ? 'unreconciled_drift' : 'offline_structural_only',
    inventory_authenticated: false, journal_authenticated: false, mutation_authorized: false,
    recovery_authorized: false,
    note: 'Matching a target schema is not proof of who wrote it. Fresh authenticated provider and signed barrier verification are still required.',
  };
}

async function cli(argv) {
  requireEvidence(argv.length === 4 && argv[0] === '--journal' && argv[2] === '--inventory',
    'expected --journal JOURNAL --inventory READONLY_JSON');
  // No fallback to re-planning from a partially changed provider snapshot.
  requireEvidence(fs.existsSync(argv[1]), 'original journal missing: no reliable pre-first-attempt baseline');
  const entries = fs.readFileSync(argv[1], 'utf8').trim().split('\n').map(line => JSON.parse(line));
  const inventory = JSON.parse(fs.readFileSync(argv[3], 'utf8'));
  const {planStagedSchemas} = await import('./base44_staged_schema.mjs');
  const planned = planStagedSchemas(entries[1]?.before_schemas);
  const result = classifyStagedApplyJournal(entries, inventory, planned);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  // Never permit a shell pipeline to mistake diagnostic success for permission.
  return 2;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await cli(process.argv.slice(2)); }
  catch (error) { process.stderr.write(error.message + '\n'); process.exitCode = 2; }
}
