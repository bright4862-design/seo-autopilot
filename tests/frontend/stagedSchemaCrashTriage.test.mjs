import assert from 'node:assert/strict';
import test from 'node:test';
import {spawnSync} from 'node:child_process';
import {resolve,join} from 'node:path';
import {existsSync, mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import crypto from 'node:crypto';
import {classifyStagedApplyJournal} from '../../scripts/staged_schema_crash_triage.mjs';

const app_id = '6a498732ec779dfaaeab0e53';
const source_sha = 'a'.repeat(40);
const version = 'fixlist_staged_schema_mutation_journal_v1';
const entities = ['ScanRun','FixList','FixItem','Access'];
const canonical = obj => Array.isArray(obj) ? obj.map(canonical) : obj && typeof obj === 'object'
  ? Object.fromEntries(Object.keys(obj).sort().map(k=>[k,canonical(obj[k])])) : obj;
const digest = obj => crypto.createHash('sha256').update(JSON.stringify(canonical(obj))).digest('hex');
const baseline = () => Object.fromEntries(entities.map(name=>[name,{name,properties: name === 'Access' ? {} : {status:{type:'string'}}}]));
function prepare(before, operations, after, events=[]) {
  const planned = {operations, after};
  const meta = {version, action:'apply', source_sha, app_id};
  const list = [
    {...meta,sequence:1,event:'started',execution_environment:'localhost_fixture'},
    {...meta,sequence:2,event:'planned',before_schemas:before,operations,intended_after_sha256:digest(after),barrier_generation:77},
    ...events.map((e,i)=>({...meta,sequence:i+3,...e})),
  ];
  return {list,planned};
}

test('post-provider-commit lost acknowledgment remains uncertain, never safe to replay', () => {
  const before=baseline();
  const after=structuredClone(before);
  after.Access.properties.page_cap={type:'integer'};
  const op=[{entity:'Access',kind:'add_property',property:'page_cap'}];
  const {list,planned}=prepare(before,op,after,[{event:'put_started',entity:'Access'}]);
  const r=classifyStagedApplyJournal(list,{schemas:after},planned);
  assert.equal(r.classification.Access,'matches_intended');
  assert.deepEqual(r.uncertain_put_entities,['Access']);
  assert.equal(r.recovery_authorized,false);
  assert.equal(r.inventory_authenticated,false);
});

test('identical present inventory has two different plausible prehistories', () => {
  const before=baseline(); const present=structuredClone(before);
  present.Access.properties.page_cap={type:'integer'};
  const interrupted=prepare(before,[{entity:'Access',kind:'add_property',property:'page_cap'}],present,
    [{event:'put_started',entity:'Access'}]);
  const preexisting=prepare(present,[],present);
  const a=classifyStagedApplyJournal(interrupted.list,present,interrupted.planned);
  const b=classifyStagedApplyJournal(preexisting.list,present,preexisting.planned);
  assert.equal(a.classification.Access,'matches_intended');
  assert.equal(b.classification.Access,'unchanged');
  assert.notDeepEqual(a.uncertain_put_entities,b.uncertain_put_entities);
  assert.throws(()=>classifyStagedApplyJournal([],present,interrupted.planned),/baseline missing/);
});

test('unrelated schema drift is classified and never authorized', () => {
  const before=baseline();const after=structuredClone(before);
  after.Access.properties.page_cap={type:'integer'};
  const {list,planned}=prepare(before,[{entity:'Access',kind:'add_property',property:'page_cap'}],after);
  const changed=structuredClone(after);changed.FixItem.properties.alien={type:'boolean'};
  const r=classifyStagedApplyJournal(list,changed,planned);
  assert.equal(r.assessment,'unreconciled_drift');
  assert.equal(r.classification.FixItem,'unexpected_drift');
  assert.equal(r.mutation_authorized,false);
});

test('plan tampering and invented readback are refused', () => {
  const before=baseline();const after=structuredClone(before);
  const {list,planned}=prepare(before,[],after,[{event:'readback_verified',entity:'Access'}]);
  assert.throws(()=>classifyStagedApplyJournal(list,after,planned),/readback without returned PUT/);
  const second=prepare(before,[],after);
  second.list[1].intended_after_sha256='0'.repeat(64);
  assert.throws(()=>classifyStagedApplyJournal(second.list,after,second.planned),/plan disagrees/);
});

test('missing witness CLI refuses without writing or querying Base44', () => {
  const script=resolve('scripts/staged_schema_crash_triage.mjs');
  const child=spawnSync(process.execPath,[script,'--journal','/nonexistent/schema.journal.ndjson','--inventory','/nonexistent/readonly.json'],{encoding:'utf8'});
  assert.equal(child.status,2);
  assert.match(child.stderr,/original journal missing/);
  assert.equal(child.stdout,'');
});

// A source-bound end-to-end fixture for the actual reviewed Standard 150 plan.
test('real V9 plan and offline CLI classify a committed-but-unacknowledged Access PUT',
  {skip: !existsSync('base44/entities/ScanRun.jsonc')}, async t => {
    const {planStagedSchemas}=await import('../../scripts/base44_staged_schema.mjs');
    const before=Object.fromEntries(entities.map(name=>[name,JSON.parse(readFileSync('base44/entities/'+name+'.jsonc','utf8'))]));
    for (const [name,properties] of Object.entries({
      ScanRun:['page_cap','pipeline_mode','pages_planned','workspace_cleanup_state','workspace_cleanup_completed_at','last_committed_batch'],
      FixItem:['affected_page_count','affected_page_count_is_lower_bound','template_impact_estimates'],
      Access:['page_cap'],
    })) for (const property of properties) delete before[name].properties[property];
    before.ScanRun.properties.scan_mode.enum=before.ScanRun.properties.scan_mode.enum.filter(x=>x!=='standard_500');
    const plan=planStagedSchemas(before);
    assert.equal(plan.operations.length,11);
    const current=structuredClone(before);current.Access=plan.after.Access;
    const {list}=prepare(before,plan.operations,plan.after,[{event:'put_started',entity:'Access'}]);
    const dir=mkdtempSync(join(tmpdir(),'fixlist-crash-triage-'));
    t.after(()=>rmSync(dir,{recursive:true,force:true}));
    const journal=join(dir,'schema.journal.ndjson'), inventory=join(dir,'inventory.json');
    writeFileSync(journal,list.map(x=>JSON.stringify(x)).join('\n')+'\n');
    writeFileSync(inventory,JSON.stringify({schemas:current}));
    const child=spawnSync(process.execPath,[resolve('scripts/staged_schema_crash_triage.mjs'),
      '--journal',journal,'--inventory',inventory],{encoding:'utf8'});
    assert.equal(child.status,2,child.stderr);
    const result=JSON.parse(child.stdout);
    assert.equal(result.classification.Access,'matches_intended');
    assert.equal(result.classification.FixItem,'matches_original');
    assert.deepEqual(result.uncertain_put_entities,['Access']);
    assert.equal(result.recovery_authorized,false);
  });
