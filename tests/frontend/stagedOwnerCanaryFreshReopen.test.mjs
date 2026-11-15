import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

// Execute the exact pure predicate embedded in the CLI's Base44 runtime script.
// No auth, network, cloud scan or remote fixture is needed.
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const script = fs.readFileSync(path.join(repoRoot, 'scripts/run-staged-owner-canary.sh'), 'utf8');
const start = script.indexOf('function verifiedCustomerReopen(');
const end = script.indexOf('\nfunction observe(', start);
assert.ok(start !== -1 && end > start, 'fresh customer reopen predicate must remain in the canary');
const verify = vm.runInNewContext(script.slice(start, end) + '\nverifiedCustomerReopen', {});

const scanId = 'scan_12345678';
const projectId = 'project_12345678';
const fingerprint = '118544dcf77d86cf';
function fixture() {
  const original = {
    success:true, scan_id:scanId, fix_list_id:'fixlist_12345678',
    run:{id:scanId, status:'complete'},
  };
  const reopened = {
    success:true, access:'full', authority_verified:true, release_contract_current:true,
    scan_id:scanId, fix_list_id:'fixlist_12345678',
    run:{id:scanId, status:'complete', beta_revision_fingerprint:fingerprint},
    fixList:{id:'fixlist_12345678', scan_run_id:scanId, project_id:projectId},
  };
  return {original,reopened};
}
function check(mutator) {
  const {original,reopened}=fixture();
  mutator(original,reopened);
  return verify(reopened, original, scanId, projectId, fingerprint);
}
test('separate owner read-back accepts same signed current-release FixList', () => {
  assert.equal(check(()=>{}), true);
});
for (const [name, mutate] of [
  ['missing persisted FixList', (_, r)=>{r.fixList=null;}],
  ['changed FixList on reopen', (_, r)=>{r.fix_list_id='fixlist_foreign';}],
  ['wrong FixList parent scan', (_, r)=>{r.fixList.scan_run_id='scan_foreign';}],
  ['wrong project', (_, r)=>{r.fixList.project_id='project_foreign';}],
  ['reopened scan belongs to another ID', (_, r)=>{r.run.id='scan_foreign';}],
  ['original poll belongs to another ID', (o)=>{o.run.id='scan_foreign';}],
  ['unverified authority', (_, r)=>{r.authority_verified=false;}],
  ['preview access rather than full owner access', (_, r)=>{r.access='preview';}],
  ['old release fingerprint', (_, r)=>{r.run.beta_revision_fingerprint='01ebe8e90df1e6bd';}],
  ['release-current flag false', (_, r)=>{r.release_contract_current=false;}],
  ['noncomplete terminal status', (_, r)=>{r.run.status='limited';}],
  ['missing FixList ID', (_, r)=>{r.fix_list_id='';}],
]) {
  test('fresh owner read-back refuses '+name, () => {
    assert.equal(check(mutate), false);
  });
}
test('canary gates acceptance on fresh reopen and does not launch a second scan', () => {
  assert.match(script, /customer_reopen:report\.customer_reopen_verified === true/);
  const invoked = script.match(/base44\.functions\.invoke\('startStandardScanJobV9'/g) || [];
  assert.equal(invoked.length, 1);
  assert.match(script, /action:'get', scan_id:report\.scan_id/);
});
