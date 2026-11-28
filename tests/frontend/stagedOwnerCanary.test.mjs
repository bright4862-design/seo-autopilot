import assert from 'node:assert/strict';
import {chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import test from 'node:test';

const sourceSha = 'a'.repeat(40);
const fingerprint = '1470ccb6398a7f4f';
const ownerId = 'owner_123';
const projectId = 'project_123';
const requestId = 'staged_canary_123';
const routeManifest = 'data/generated-staged-v9-routes.json';
const {functions} = JSON.parse(readFileSync(new URL('../../' + routeManifest, import.meta.url), 'utf8'));
const launchRoute = functions.startStandardScanJobV9.route_name;
const resultRoute = functions.getCustomerScanResultV9.route_name;
const confirm = `RUN-ONE-STAGED-OWNER-CANARY:${sourceSha}:${ownerId}:${projectId}:${requestId}`;

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'staged-owner-canary-'));
  const artifactRoot = mkdtempSync(join(tmpdir(), 'staged-owner-canary-artifacts-'));
  t.after(() => { rmSync(root, {recursive:true, force:true}); rmSync(artifactRoot, {recursive:true, force:true}); });
  mkdirSync(join(root, 'scripts/lib'), {recursive:true});
  mkdirSync(join(root, 'bin'));
  mkdirSync(join(root, 'data'));
  copyFileSync(routeManifest, join(root, routeManifest));
  mkdirSync(join(root, 'base44/functions/startStandardScanJobV9'), {recursive:true});
  writeFileSync(join(root, 'package.json'), '{"type":"module"}');
  copyFileSync('scripts/run-staged-owner-canary.sh', join(root, 'scripts/run-staged-owner-canary.sh'));
  writeFileSync(join(root, 'base44/functions/startStandardScanJobV9/generatedReleaseContract.js'), `export const RELEASE_FINGERPRINT = '${fingerprint}';`);
  // Existing release guard and CLI installer have their own tests. Replace
  // only those external boundaries; execute the complete canary payload here.
  writeFileSync(join(root, 'scripts/lib/release-source-guard.sh'), 'fixlist_require_exact_main() { [[ "$2" == "$SOURCE_SHA" && "$3" == "$SOURCE_SHA" ]] || return 2; }\n');
  writeFileSync(join(root, 'scripts/lib/base44-pinned-cli.sh'), 'fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$FIXTURE_FAKE_CLI"; export FIXLIST_BASE44_CLI; }\n');
  writeFileSync(join(root, 'bin/deno'), '#!/usr/bin/env bash\nexit 0\n');
  chmodSync(join(root, 'bin/deno'), 0o700);
  const cli = join(root, 'bin/base44');
  writeFileSync(cli, `#!/usr/bin/env node
import {appendFileSync,readFileSync} from 'node:fs';
const scenario=process.env.CANARY_TEST_SCENARIO;
const track=(name,payload)=>appendFileSync(process.env.CANARY_TEST_TRACE,JSON.stringify({name,payload})+'\\n');
track('cli_args',process.argv.slice(2));
const owner='${ownerId}', project='${projectId}', request='${requestId}', url='https://norris.example/';
const run={id:'scan_123456',owner_user_id:owner,project_id:project,request_id:request,idempotency_key:request,website_url:url,scan_mode:'standard_150',page_cap:150,pipeline_mode:'staged',status:scenario==='timeout'?'crawling':'complete',pages_crawled:150,pages_planned:150,last_committed_batch:2,started_at:'2026-11-11T12:00:00.000Z',completed_at:'2026-11-11T12:01:00.000Z',beta_revision_fingerprint:'${fingerprint}',authority_proof:'a'.repeat(64),authority_seal_version:'standard_review_snapshot_hmac_identity_v1'};
if(scenario==='missingProgress') delete run.last_committed_batch;
const projected={...run,advanced_scan_backend:'python_scanner_api',deno_fallback_used:false,ai_review_backend:'python_review_api',python_review_fallback_used:false,worker_peak_memory_bytes:123456789,email:'never-print@example.com',main_text:'private page body'};
if(scenario==='missingMemory') delete projected.worker_peak_memory_bytes;
if(scenario==='fingerprintMismatch') projected.beta_revision_fingerprint='b'.repeat(16);
if(scenario==='unconfirmedCooldown') projected.crawl_timing={target_cooldown_publication:{state:'unconfirmed',observation:{target_origin:'https://never-print.example:443'}}};
const grant={id:'access_123',owner_user_id:owner,user_email:'never-print@example.com',has_full_access:true,access_status:'active',plan_id:'standard150_lifetime',app_id:'6a498732ec779dfaaeab0e53',grant_source:'manual_grant',granted_at:'2026-11-01T00:00:00Z',page_cap:150};
if(scenario==='legacyGrant') delete grant.page_cap;
if(scenario==='grant500') grant.page_cap=500;
if(scenario==='revokedGrant') grant.access_status='revoked';
const denied=async()=>{track('forbidden_mutation');throw new Error('Mutation forbidden');};
const base44={auth:{me:async()=>{track('auth.me');return{id:scenario==='wrongOwner'?'other_123':owner,email:'never-print@example.com',role:scenario==='nonAdmin'?'user':'admin'};}},entities:{
BusinessProject:{get:async(id)=>{track('BusinessProject.get',id);return{id,owner_user_id:scenario==='wrongProject'?'other_123':owner,website_url:url};},create:denied,update:denied},
Access:{filter:async(query)=>{track('Access.filter',query);return scenario==='duplicateGrant'?[grant,{...grant,id:'access_456'}]:[grant];},create:denied,update:denied},
ScanRun:{filter:async(query)=>{track('ScanRun.filter',query);return scenario==='priorRequest'?[run]:scenario==='historyUnavailable'?null:[];},get:async(id)=>{track('ScanRun.get',id);return run;},create:denied,update:denied}
},functions:{invoke:async(name,payload)=>{track(name,payload);if(name==='${launchRoute}')return{data:{success:true,accepted:true,replayed:scenario==='replayed'||scenario==='replayedRecovered',replay_reason:scenario==='replayed'?'request_replay':scenario==='replayedRecovered'?'request_replay_recovered':scenario==='unmarked'?'':'server_admitted',scan_id:run.id,scan_mode:'standard_150',page_cap:150,pipeline_mode:scenario==='monolith'?'monolith':'staged'}};if(name==='${resultRoute}'){ const fixListId='fixlist_123456'; const isReopen=payload?.action==='get'; return {data:{success:true,access:'full',scan_id:run.id,fix_list_id:isReopen&&scenario==='reopenMismatch'?'fixlist_foreign':fixListId,authority_verified:true,release_contract_current:true,run:projected,fixList:{id:fixListId,scan_run_id:run.id,project_id:project}}}; }throw new Error('Unexpected function');}}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
await new AsyncFunction('base44',readFileSync(0,'utf8'))(base44);
`);
  chmodSync(cli, 0o700);
  const output = join(artifactRoot, 'acceptance.json');
  const trace = join(root, 'trace.jsonl');
  return {
    root, output,
    run(scenario='good', overrides={}) {
      const result = spawnSync('bash', [join(root, 'scripts/run-staged-owner-canary.sh')], {
        encoding:'utf8', timeout:6000,
        env:{...process.env, PATH:join(root,'bin')+':'+process.env.PATH,
          SOURCE_SHA:sourceSha, EXPECTED_OWNER_USER_ID:ownerId, PROJECT_ID:projectId,
          TARGET_URL:'https://norris.example/', EXPECTED_PAGE_CAP:'150', REQUEST_ID:requestId,
          ACCEPTANCE_OUTPUT:output, MAX_WAIT_SECONDS:'1', POLL_SECONDS:'1', CONFIRM:confirm,
          FIXTURE_FAKE_CLI:cli, CANARY_TEST_SCENARIO:scenario, CANARY_TEST_TRACE:trace,
          ...overrides},
      });
      assert.ifError(result.error);
      return {...result, report:existsSync(output)?JSON.parse(readFileSync(output,'utf8')):null,
        calls:existsSync(trace)?readFileSync(trace,'utf8').trim().split('\n').filter(Boolean).map(line=>JSON.parse(line)):[]};
    },
  };
}

for (const [scenario, description] of [
  ['replayed', 'terminal idempotency replay'],
  ['replayedRecovered', 'recovered idempotency replay'],
  ['unmarked', 'unmarked browser-row admission response'],
]) {
  test('owner canary refuses '+description+' before polling a saved result', t => {
    const result=fixture(t).run(scenario);
    assert.equal(result.status,1);
    assert.equal(result.report.acceptance_verified,false);
    assert.equal(result.report.failure_code,'canary_fresh_admission_unverified');
    assert.equal(result.calls.filter(row=>row.name===launchRoute).length,1);
    assert.equal(result.calls.filter(row=>row.name===resultRoute).length,0);
  });
}

test('canary refuses absent exact one-scan confirmation before any CLI call', t => {
  const result=fixture(t).run('good',{CONFIRM:''});
  assert.equal(result.status,2);
  assert.equal(result.calls.length,0);
  assert.equal(result.report,null);
});

test('initial canary refuses a 500-page requested cap', t => {
  const result=fixture(t).run('good',{EXPECTED_PAGE_CAP:'500'});
  assert.equal(result.status,2);
  assert.equal(result.calls.length,0);
});

test('canary refuses the old launcher route before CLI authentication', t => {
  const canary=fixture(t);
  const invalid=structuredClone(functions);
  invalid.startStandardScanJobV9.route_name='startStandardScanJobV9';
  writeFileSync(join(canary.root,routeManifest),JSON.stringify({functions:invalid}));
  const result=canary.run();
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/staged scan routes unavailable/);
  assert.deepEqual(result.calls,[]);
  assert.equal(result.report,null);
});

test('canary rejects missing or unsuffixed V9B reader before any CLI authentication', t => {
  const canary=fixture(t);
  const invalid=structuredClone(functions);
  invalid.getCustomerScanResultV9.route_name='getCustomerScanResultV9';
  writeFileSync(join(canary.root,routeManifest),JSON.stringify({functions:invalid}));
  const result=canary.run();
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/staged scan routes unavailable/);
  assert.deepEqual(result.calls,[]);
});

test('authenticated identity mismatch stops before project lookup or scan start', t => {
  const result=fixture(t).run('wrongOwner');
  assert.equal(result.status,1);
  assert.equal(result.report.failure_code,'authenticated_owner_mismatch');
  assert.deepEqual(result.calls.map(row=>row.name),['cli_args','auth.me']);
});

test('canary verifies the existing project owner without modifying it', t => {
  const result=fixture(t).run('wrongProject');
  assert.equal(result.status,1);
  assert.equal(result.report.failure_code,'project_owner_mismatch');
  assert.equal(result.calls.filter(row=>row.name===launchRoute).length,0);
  assert.equal(result.calls.some(row=>row.name==='forbidden_mutation'),false);
});

for (const scenario of ['grant500','duplicateGrant','revokedGrant']) {
  test(`canary refuses ${scenario} before scan creation`, t => {
    const result=fixture(t).run(scenario);
    assert.equal(result.status,1);
    assert.equal(result.calls.filter(row=>row.name===launchRoute).length,0);
    assert.equal(result.calls.some(row=>row.name==='forbidden_mutation'),false);
  });
}

for (const [scenario, code] of [
  ['priorRequest', 'canary_request_preexisting'],
  ['historyUnavailable', 'canary_request_history_unavailable'],
]) {
  test('owner canary refuses '+scenario+' before calling the launcher', t => {
    const result=fixture(t).run(scenario);
    assert.equal(result.status,1);
    assert.equal(result.report.acceptance_verified,false);
    assert.equal(result.report.failure_code,code);
    assert.equal(result.calls.filter(row=>row.name==='ScanRun.filter').length,1);
    assert.equal(result.calls.filter(row=>row.name===launchRoute).length,0);
    assert.equal(result.calls.filter(row=>row.name===resultRoute).length,0);
    assert.equal(result.calls.some(row=>row.name==='forbidden_mutation'),false);
  });
}

test('one stable request produces a filtered verified staged-150 acceptance report', t => {
  const result=fixture(t).run();
  assert.equal(result.status,0,result.stderr);
  const starts=result.calls.filter(row=>row.name===launchRoute);
  assert.equal(starts.length,1);
  assert.equal(result.calls.filter(row=>row.name===resultRoute).length,2);
  assert.equal(result.calls.filter(row=>row.name===resultRoute)[1].payload.action,'get');
  assert.equal(starts[0].payload.request_id,requestId);
  assert.equal(starts[0].payload.idempotency_key,requestId);
  assert.equal(starts[0].payload.scan_mode,'standard_150');
  assert.equal('page_cap' in starts[0].payload,false);
  assert.deepEqual(result.calls[0].payload,['--app-id','6a498732ec779dfaaeab0e53','exec','--data-env','prod']);
  assert.equal(result.report.acceptance_verified,true);
  assert.equal(result.report.verified_owner_user_id,ownerId);
  assert.equal(result.report.authority_verified,true);
  assert.equal(result.report.durable_worker_owned,true);
  assert.equal(result.report.committed_batch_count,3);
  assert.equal(result.report.duration_ms,60000);
  assert.equal(result.report.worker_peak_memory_bytes,123456789);
  assert.equal(result.report.production_freeze,false);
  assert.equal(result.report.deployed_git_source_sha.state,'unverified');
  assert.equal(result.report.release_fingerprint,fingerprint);
  assert.doesNotMatch(JSON.stringify(result.report),/never-print|private page body|authority_proof/);
  assert.doesNotMatch(result.stdout,/never-print|private page body/);
});

test('fresh customer reopen rejects mismatched FixList on exact V9B route', t => {
  const result=fixture(t).run('reopenMismatch');
  assert.equal(result.status,1);
  assert.equal(result.report.acceptance_verified,false);
  assert.equal(result.report.customer_reopen_verified,false);
  assert.ok(result.report.unverified.includes('customer_reopen'));
  assert.equal(result.calls.filter(row=>row.name===launchRoute).length,1);
  assert.equal(result.calls.filter(row=>row.name===resultRoute).length,2);
});

test('a legacy active grant without page_cap resolves to the server default 150', t => {
  const result=fixture(t).run('legacyGrant');
  assert.equal(result.status,0,result.stderr);
  assert.equal(result.report.acceptance_verified,true);
});

for (const [scenario, missing] of [['missingProgress','batch_progress'],['missingMemory','measured_memory'],['fingerprintMismatch','release_fingerprint'],['unconfirmedCooldown','target_cooldown_publication']]) {
  test(`missing or mismatched ${missing} remains explicitly unverified`, t => {
    const result=fixture(t).run(scenario);
    assert.equal(result.status,1);
    assert.equal(result.report.acceptance_verified,false);
    assert.ok(result.report.unverified.includes(missing));
    if (scenario==='unconfirmedCooldown') {
      assert.equal(result.report.authority_verified,true);
      assert.equal(result.report.target_cooldown_publication,'unconfirmed');
      assert.doesNotMatch(JSON.stringify(result.report),/never-print\.example/);
    }
    assert.equal(result.calls.filter(row=>row.name===launchRoute).length,1);
  });
}

test('a still-running scan stops polling at the configured deadline without resubmitting', t => {
  const result=fixture(t).run('timeout');
  assert.equal(result.status,1);
  assert.equal(result.report.failure_code,'canary_timeout');
  assert.equal(result.calls.filter(row=>row.name===launchRoute).length,1);
  assert.equal(result.report.acceptance_verified,false);
});


test('nonadmin authenticated owner fails before any scan because evidence RLS requires admin', t => {
  const result=fixture(t).run('nonAdmin');
  assert.equal(result.status,1);
  assert.equal(result.report.failure_code,'authenticated_owner_not_admin');
  assert.equal(result.calls.some(row=>row.name===launchRoute),false);
  assert.deepEqual(result.calls.map(row=>row.name),['cli_args','auth.me']);
});

test('existing acceptance evidence is never overwritten or followed by another scan', t => {
  const canary=fixture(t);
  const first=canary.run();
  assert.equal(first.status,0,first.stderr);
  const second=canary.run();
  assert.equal(second.status,2);
  assert.deepEqual(second.report,first.report);
  assert.equal(second.calls.filter(row=>row.name===launchRoute).length,1);
});


test('canary refuses another application before any authenticated CLI work', t => {
  const result=fixture(t).run('good',{BASE44_APP_ID:'another_app_123'});
  assert.equal(result.status,2);
  assert.equal(result.calls.length,0);
  assert.equal(result.report,null);
});

test('canary acceptance artifacts cannot be written inside the exact source checkout', t => {
  const canary=fixture(t);
  const result=canary.run('good',{ACCEPTANCE_OUTPUT:join(canary.root,'inside.json')});
  assert.equal(result.status,1);
  assert.equal(result.calls.length,0);
});


test('a symlink parent cannot alias an acceptance output path', t => {
  const canary=fixture(t);
  const alias=join(canary.root,'artifact-alias');
  symlinkSync(join(canary.output,'..'),alias,'dir');
  const result=canary.run('good',{ACCEPTANCE_OUTPUT:join(alias,'aliased.json')});
  assert.equal(result.status,1);
  assert.equal(result.calls.length,0);
});

test('a relative acceptance output is refused before any CLI work', t => {
  const result=fixture(t).run('good',{ACCEPTANCE_OUTPUT:'relative-canary.json'});
  assert.equal(result.status,2);
  assert.equal(result.calls.length,0);
});
