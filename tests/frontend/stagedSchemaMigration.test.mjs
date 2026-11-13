import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import test from 'node:test';

const sourceSha = 'a'.repeat(40);
const appId = '6a498732ec779dfaaeab0e53';
const entities = ['ScanRun', 'FixList', 'FixItem', 'Access'];
const fields = {
  ScanRun: ['page_cap', 'pipeline_mode', 'pages_planned', 'workspace_cleanup_state', 'workspace_cleanup_completed_at', 'last_committed_batch'],
  FixItem: ['affected_page_count', 'affected_page_count_is_lower_bound', 'template_impact_estimates'],
  Access: ['page_cap'],
};
const local = () => Object.fromEntries(entities.map(name => [name, JSON.parse(readFileSync(`base44/entities/${name}.jsonc`, 'utf8'))]));
function baseline() {
  const schemas = local();
  for (const [name, properties] of Object.entries(fields)) for (const property of properties) delete schemas[name].properties[property];
  schemas.ScanRun.properties.scan_mode.enum = schemas.ScanRun.properties.scan_mode.enum.filter(value => value !== 'standard_500');
  return schemas;
}
const moduleUnderTest = () => import(pathToFileURL(resolve('scripts/base44_staged_schema.mjs')));
function run(script, args, options = {}) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(process.execPath, [script, ...args], options);
    let stdout = '', stderr = '';
    child.stdout.on('data', value => { stdout += value; });
    child.stderr.on('data', value => { stderr += value; });
    child.on('error', reject);
    child.on('close', status => resolveRun({status, stdout, stderr}));
  });
}
async function fixture(t, {schemas = baseline(), rows = {}, changeReadback = false, driftBeforeWrite = false, rowsMalformed = false} = {}) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'staged-schema-')));
  const artifactRoot = realpathSync(mkdtempSync(join(tmpdir(), 'staged-schema-reports-')));
  mkdirSync(join(root, 'scripts/lib'), {recursive: true});
  mkdirSync(join(root, 'base44/entities'), {recursive: true});
  for (const file of ['base44_named_schema_client.mjs', 'base44_authority_schema.mjs', 'base44_staged_schema.mjs']) {
    if (existsSync(`scripts/${file}`)) cpSync(`scripts/${file}`, join(root, 'scripts', file));
  }
  for (const name of entities) cpSync(`base44/entities/${name}.jsonc`, join(root, 'base44/entities', `${name}.jsonc`));
  const events = join(root, 'events');
  writeFileSync(join(root, 'scripts/lib/release-source-guard.sh'), 'fixlist_require_exact_main() { printf "source\\n" >> "$TEST_EVENTS"; [[ "${TEST_SOURCE_FAIL:-}" != yes ]]; }\n');
  writeFileSync(join(root, 'scripts/lib/base44-pinned-cli.sh'), 'fixlist_install_base44_cli() { :; }\nfixlist_require_base44_owner() { printf "owner\\n" >> "$TEST_EVENTS"; [[ "${TEST_OWNER_FAIL:-}" != yes ]]; }\n');
  writeFileSync(join(root, 'scripts/fixlist-cloud-operator.sh'), 'printf "barrier\\n" >> "$TEST_EVENTS"\n[[ "${TEST_BARRIER_FAIL:-}" != yes ]]\n');
  const auth = join(root, 'auth.json');
  writeFileSync(auth, JSON.stringify({accessToken: 'fixture-token-'.repeat(4)}));
  const requests = [];
  let reads = 0;
  const state = structuredClone(schemas);
  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    requests.push({method: request.method, path: url.pathname, query: Object.fromEntries(url.searchParams)});
    let body = '';
    request.on('data', value => { body += value; });
    request.on('end', () => {
      response.setHeader('content-type', 'application/json');
      if (request.method === 'GET' && url.pathname.endsWith('/entity-schemas')) {
        reads++;
        if (driftBeforeWrite && reads === 2) state.Access.platform_marker = 'concurrent-edit';
        response.end(JSON.stringify({schemas: entities.map(name => ({entity_name: name, entity_schema: state[name]}))}));
      } else if (request.method === 'PUT' && url.pathname.includes('/entity-schemas/')) {
        const name = url.pathname.split('/').at(-1);
        const payload = JSON.parse(body);
        assert.deepEqual(Object.keys(payload), ['entity_schema']);
        assert.equal(payload.entity_schema.name, name);
        state[name] = payload.entity_schema;
        if (changeReadback) state[name].rls.update = {user_condition: {role: 'user'}};
        response.end('{}');
      } else if (url.pathname.includes('/entities/')) {
        const name = url.pathname.split('/entities/')[1].split('/')[0];
        const page = url.searchParams.get('cursor') ? 1 : 0;
        const pages = rows[name] || [[]];
        response.end(JSON.stringify(rowsMalformed ? {items: []} : {items: pages[page] || [], has_more: page < pages.length - 1, ...(page < pages.length - 1 ? {next_cursor: 'next'} : {})}));
      } else { response.statusCode = 404; response.end('{}'); }
    });
  });
  await new Promise(resolveServer => server.listen(0, '127.0.0.1', resolveServer));
  const env = {...process.env, BASE44_APP_ID: appId, BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${server.address().port}`, BASE44_AUTH_FILE: auth, BASE44_API_KEY: '', GITHUB_ACTIONS: '', TEST_EVENTS: events, BASE44_EXPECTED_OWNER: 'owner@example.com'};
  t.after(async () => { await new Promise(done => server.close(done)); rmSync(root, {recursive: true, force: true}); rmSync(artifactRoot, {recursive: true, force: true}); });
  let reportNumber = 0;
  return {root, state, requests, events, env,
    async command(action, extra = [], environment = {}) {
      const report = join(artifactRoot, `report-${++reportNumber}.json`);
      const args = [action, '--source-sha', sourceSha, '--report', report, ...extra];
      if (action === 'apply') args.push('--generation', '77', '--confirm', `APPLY-STAGED-SCHEMA:${sourceSha}:77`);
      const result = await run(join(root, 'scripts/base44_staged_schema.mjs'), args, {cwd: root, env: {...env, ...environment}});
      return {...result, report, data: existsSync(report) ? JSON.parse(readFileSync(report, 'utf8')) : null};
    },
  };
}

test('named client fetch-staged includes Access and put-named permits only the staged write entities', async t => {
  const f = await fixture(t);
  const output = join(f.root, 'inventory.json');
  let result = await run('scripts/base44_named_schema_client.mjs', ['fetch-staged', output], {env: f.env});
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(Object.keys(JSON.parse(readFileSync(output, 'utf8')).schemas), entities);
  const access = join(f.root, 'access.json');
  writeFileSync(access, JSON.stringify(local().Access));
  result = await run('scripts/base44_named_schema_client.mjs', ['put-named', 'Access', access], {env: f.env});
  assert.equal(result.status, 0, result.stderr);
  for (const name of ['BusinessProject', '../Access', 'FixList']) {
    const count = f.requests.length;
    result = await run('scripts/base44_named_schema_client.mjs', ['put-named', name, access], {env: f.env});
    assert.notEqual(result.status, 0);
    assert.equal(f.requests.length, count);
  }
});

test('staged plan allows exactly the known additions while preserving the live documents', async () => {
  const {planStagedSchemas} = await moduleUnderTest();
  const before = baseline();
  before.ScanRun.platform_marker = 'preserve';
  before.ScanRun.properties.created_date = {type: 'string'};
  delete before.ScanRun.properties.website_url.description;
  const plan = planStagedSchemas(before);
  assert.equal(plan.decision, 'apply');
  assert.equal(plan.operations.length, 11);
  assert.equal(plan.after.ScanRun.platform_marker, 'preserve');
  assert.deepEqual(plan.after.ScanRun.properties.created_date, {type: 'string'});
  assert.equal(Object.hasOwn(plan.after.ScanRun.properties.website_url, 'description'), false);
  assert.deepEqual(plan.after.Access.properties.page_cap.enum, [150, 500]);
  assert.deepEqual(plan.after.ScanRun.properties.scan_mode.enum, ['standard_150', 'basic', 'quick', 'deep', 'advanced', 'standard_500']);
  assert.equal(planStagedSchemas(plan.after).decision, 'match');
  assert.equal(before.Access.properties.page_cap, undefined);
});

for (const [name, mutate] of [
  ['existing staged type replacement', schemas => { schemas.Access.properties.page_cap = {type: 'string'}; }],
  ['RLS replacement', schemas => { schemas.ScanRun.rls.update = {user_condition: {role: 'user'}}; }],
  ['unrelated missing property', schemas => { delete schemas.FixList.properties.website_url; }],
  ['unrelated enum removal', schemas => { schemas.ScanRun.properties.scan_mode.enum = ['standard_150']; }],
]) test(`staged plan refuses ${name}`, async () => {
  const {planStagedSchemas} = await moduleUnderTest();
  const schemas = baseline(); mutate(schemas);
  assert.throws(() => planStagedSchemas(schemas), /Refusing/);
});

test('offline plan writes a source-bound report without authentication or requests', async t => {
  const f = await fixture(t);
  const input = join(f.root, 'before.json'); writeFileSync(input, JSON.stringify({schemas: baseline()}));
  const result = await f.command('plan', ['--inventory', input]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.data.source_sha, sourceSha);
  assert.equal(result.data.live_verified, false);
  assert.match(result.data.contract_sha256, /^[a-f0-9]{64}$/);
  assert.equal(result.data.operations.length, 11);
  assert.equal(f.requests.length, 0);
  assert.equal(existsSync(f.events), false);
});

test('four-entity live verification includes Access without any PUT or barrier mutation', async t => {
  const f = await fixture(t, {schemas: local()});
  const result = await f.command('verify');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.data.status, 'live_match');
  assert.equal(result.data.readback_verified, true);
  assert.deepEqual(result.data.comparison.map(row => row.entity), entities);
  assert.equal(f.requests.filter(row => row.method !== 'GET').length, 0);
  assert.equal(readFileSync(f.events, 'utf8').includes('barrier'), false);
});

test('localhost fixture reports never claim verified production state', async t => {
  const f = await fixture(t);
  const result = await f.command('apply');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.data.execution_environment, 'localhost_fixture');
  assert.equal(result.data.live_verified, false);
  assert.equal(result.data.readback_verified, true);
});

test('source-bound offline comparison reports four entities and never accepts missing Access', async t => {
  const f = await fixture(t);
  const schemas = local(); delete schemas.Access;
  const input = join(f.root, 'incomplete.json'); writeFileSync(input, JSON.stringify({schemas}));
  const result = await f.command('compare', ['--inventory', input]);
  assert.notEqual(result.status, 0);
  assert.equal(result.data.status, 'offline_drift');
  assert.equal(result.data.comparison.find(row => row.entity === 'Access').status, 'missing');
  assert.equal(f.requests.length, 0);
});

test('apply refuses a dangling report symlink before authentication or schema requests', async t => {
  const f = await fixture(t);
  const output = join(f.root, '..', `dangling-report-${Date.now()}-${Math.random()}.json`);
  symlinkSync(join(f.root, 'missing-report-target'), output);
  t.after(() => rmSync(output, {force: true}));
  const result = await run(join(f.root, 'scripts/base44_staged_schema.mjs'), ['apply', '--source-sha', sourceSha, '--generation', '77', '--confirm', `APPLY-STAGED-SCHEMA:${sourceSha}:77`, '--report', output], {cwd: f.root, env: f.env});
  assert.notEqual(result.status, 0);
  assert.equal(f.requests.length, 0);
  assert.equal(existsSync(f.events), false);
});

test('apply adds three named schemas and freshly compares all four without touching unrelated fields', async t => {
  const schemas = baseline(); schemas.ScanRun.platform_marker = 'keep';
  const f = await fixture(t, {schemas});
  const result = await f.command('apply');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.data.status, 'applied_verified');
  assert.equal(result.data.source_sha, sourceSha);
  assert.equal(result.data.barrier_generation, 77);
  assert.equal(result.data.readback_verified, true);
  assert.deepEqual(result.data.comparison.map(row => row.entity), entities);
  assert.ok(result.data.comparison.every(row => row.status === 'match'));
  assert.equal(f.state.ScanRun.platform_marker, 'keep');
  assert.deepEqual(f.requests.filter(row => row.method === 'PUT').map(row => row.path.split('/').at(-1)), ['Access', 'FixItem', 'ScanRun']);
  assert.match(readFileSync(f.events, 'utf8'), /^source\nbarrier\nowner\n/);
  assert.ok(f.requests.filter(row => row.method === 'GET' && row.path.endsWith('/entity-schemas')).length >= 7);
});

for (const boundary of ['SOURCE', 'OWNER', 'BARRIER']) test(`apply refuses failed ${boundary.toLowerCase()} guard without schema requests`, async t => {
  const f = await fixture(t);
  const result = await f.command('apply', [], {[`TEST_${boundary}_FAIL`]: 'yes'});
  assert.notEqual(result.status, 0);
  assert.equal(f.requests.length, 0);
});

test('concurrent pre-write drift refuses every PUT', async t => {
  const f = await fixture(t, {driftBeforeWrite: true});
  const result = await f.command('apply');
  assert.notEqual(result.status, 0);
  assert.equal(f.requests.filter(row => row.method === 'PUT').length, 0);
});

test('changed live readback refuses success and preserves evidence without overwriting drift', async t => {
  const f = await fixture(t, {changeReadback: true});
  const result = await f.command('apply');
  assert.notEqual(result.status, 0);
  assert.equal(result.data.live_verified, false);
  assert.equal(result.data.status, 'failed');
  assert.equal(f.requests.filter(row => row.method === 'PUT').length, 1);
  assert.equal(f.state.Access.rls.update.user_condition.role, 'user');
});

test('rollback removes only this receipt additions after full paginated row proof', async t => {
  const f = await fixture(t, {rows: {ScanRun: [[{id: 'old', status: 'complete', pipeline_mode: 'monolith', scan_mode: 'standard_150'}], [{id: 'old2', status: 'failed'}]]}});
  const applied = await f.command('apply'); assert.equal(applied.status, 0, applied.stderr);
  const {receiptDigest} = await moduleUnderTest();
  const result = await f.command('rollback', ['--generation', '77', '--receipt', applied.report, '--confirm', `ROLLBACK-STAGED-SCHEMA:${sourceSha}:77:${receiptDigest(applied.data)}`]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.data.status, 'rolled_back_verified');
  assert.deepEqual(f.state, baseline());
  const rowReads = f.requests.filter(row => row.path.includes('/entities/'));
  assert.ok(rowReads.some(row => row.query.cursor === 'next'));
  assert.ok(rowReads.every(row => row.query.fields && row.query.limit === '500' && row.query.sort === 'created_date'));
});

test('rollback preserves staged properties that were already present before this apply receipt', async t => {
  const before = baseline(); before.Access.properties.page_cap = local().Access.properties.page_cap;
  const f = await fixture(t, {schemas: before});
  const applied = await f.command('apply'); assert.equal(applied.status, 0, applied.stderr);
  assert.equal(applied.data.operations.some(operation => operation.entity === 'Access'), false);
  const {receiptDigest} = await moduleUnderTest();
  const result = await f.command('rollback', ['--generation', '77', '--receipt', applied.report, '--confirm', `ROLLBACK-STAGED-SCHEMA:${sourceSha}:77:${receiptDigest(applied.data)}`]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(f.state, before);
});

test('rollback refuses receipt tampering before every destructive PUT', async t => {
  const f = await fixture(t);
  const applied = await f.command('apply'); assert.equal(applied.status, 0, applied.stderr);
  const putCount = f.requests.filter(row => row.method === 'PUT').length;
  const receipt = {...applied.data, operations: [{entity: 'FixList', kind: 'add_property', property: 'website_url'}]};
  writeFileSync(applied.report, JSON.stringify(receipt));
  const {receiptDigest} = await moduleUnderTest();
  const result = await f.command('rollback', ['--generation', '77', '--receipt', applied.report, '--confirm', `ROLLBACK-STAGED-SCHEMA:${sourceSha}:77:${receiptDigest(receipt)}`]);
  assert.notEqual(result.status, 0);
  assert.equal(f.requests.filter(row => row.method === 'PUT').length, putCount);
});

for (const [label, rows, rowsMalformed] of [
  ['active scan', {ScanRun: [[{id: 'active', status: 'crawling'}]]}, false],
  ['terminal staged scan', {ScanRun: [[{id: 'staged', status: 'complete', pipeline_mode: 'staged'}]]}, false],
  ['later-page staged scan', {ScanRun: [[{id: 'old', status: 'complete'}], [{id: 'staged', status: 'limited', pipeline_mode: 'staged'}]]}, false],
  ['500 entitlement', {Access: [[{id: 'grant', page_cap: 500}]]}, false],
  ['retained FixItem evidence', {FixItem: [[{id: 'fix', affected_page_count: 20}]]}, false],
  ['unverifiable rows', {}, true],
]) test(`rollback refuses ${label} without a destructive PUT`, async t => {
  const f = await fixture(t, {rows, rowsMalformed});
  const applied = await f.command('apply'); assert.equal(applied.status, 0, applied.stderr);
  const putCount = f.requests.filter(row => row.method === 'PUT').length;
  const {receiptDigest} = await moduleUnderTest();
  const result = await f.command('rollback', ['--generation', '77', '--receipt', applied.report, '--confirm', `ROLLBACK-STAGED-SCHEMA:${sourceSha}:77:${receiptDigest(applied.data)}`]);
  assert.notEqual(result.status, 0);
  assert.equal(f.requests.filter(row => row.method === 'PUT').length, putCount);
});

// Cursor pagination may overlap if the backing collection changes or a provider
// cursor is buggy. Repeated IDs cannot certify an exhaustive rollback inventory.
for (const [label, rows] of [
  ['same-page Access ID', {Access: [[{id: 'same-grant'}, {id: 'same-grant'}]]}],
  ['cross-page ScanRun ID', {ScanRun: [[{id: 'same-scan', status: 'complete'}], [{id: 'same-scan', status: 'failed'}]]}],
]) test(`rollback refuses duplicate ${label} before destructive PUT`, async t => {
  const f = await fixture(t, {rows});
  const applied = await f.command('apply'); assert.equal(applied.status, 0, applied.stderr);
  const putCount = f.requests.filter(row => row.method === 'PUT').length;
  // The outer schema orchestrator deliberately sanitizes child-process stderr.
  // Verify the exact duplicate reason at the underlying read-only client boundary.
  const inventory = join(f.root, 'duplicated-inventory.json');
  const direct = await run(join(f.root, 'scripts/base44_named_schema_client.mjs'), ['staged-rows', inventory], {cwd: f.root, env: f.env});
  assert.notEqual(direct.status, 0);
  assert.match(direct.stderr, /Staged rollback rows duplicated (Access|ScanRun) ID/);
  assert.equal(existsSync(inventory), false);
  const {receiptDigest} = await moduleUnderTest();
  const result = await f.command('rollback', ['--generation', '77', '--receipt', applied.report, '--confirm', `ROLLBACK-STAGED-SCHEMA:${sourceSha}:77:${receiptDigest(applied.data)}`]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Staged schema prerequisite failed: node \\(exit 2\\)/);
  assert.equal(result.data.failure, result.stderr.trim());
  assert.equal(f.requests.filter(row => row.method === 'PUT').length, putCount);
});
