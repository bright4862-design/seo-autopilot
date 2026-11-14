import assert from 'node:assert/strict';
import test from 'node:test';
import crypto from 'node:crypto';
import {classifyStagedApplyJournal} from '../../scripts/staged_schema_crash_triage.mjs';
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])) : v;
const sha = v => crypto.createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const before = Object.fromEntries(['ScanRun','FixList','FixItem','Access'].map(name=>[name,{name,properties:{}}]));
function witness(last = {}) {
  const meta = {version:'fixlist_staged_schema_mutation_journal_v1',action:'apply',source_sha:'a'.repeat(40),app_id:'6a498732ec779dfaaeab0e53'};
  return [
    {...meta,sequence:1,event:'started'},
    {...meta,sequence:2,event:'planned',before_schemas:before,operations:[],intended_after_sha256:sha(before),barrier_generation:77},
    {...meta,sequence:3,event:'put_started',entity:'Access',...last},
  ];
}
test('journal event cannot invent a PUT for an entity absent from the original plan',()=>{
  assert.throws(()=>classifyStagedApplyJournal(witness(),before,{operations:[],after:before}),/unexpected or overlapping PUT attempt/);
});
test('journal cannot silently skip sequence numbers or switch source identity',()=>{
  assert.throws(()=>classifyStagedApplyJournal(witness({sequence:99}),before,{operations:[],after:before}),/sequence or provenance inconsistent/);
  assert.throws(()=>classifyStagedApplyJournal(witness({source_sha:'b'.repeat(40)}),before,{operations:[],after:before}),/sequence or provenance inconsistent/);
});
