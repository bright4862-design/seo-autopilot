import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const root = fileURLToPath(new URL('../../', import.meta.url));
const workflow = readFileSync(join(root, '.github/workflows/fixlist-cloud-operator.yml'), 'utf8');
const job = workflow.match(/^  compare-static-egress-access-on-owner-comment:\n([\s\S]*?)(?=^  [\w-]+:|$(?![\s\S]))/m)?.[1];
const sha = 'a'.repeat(40);
const aliases = ['winamax', 'ratp', 'viator', 'klook', 'fever', 'ironwood', 'funbooker'];

function shellStep(name) {
  assert.ok(job, 'Owner-only comparison job must exist');
  const step = job.split('      - name: ').find(value => value.startsWith(name + '\n'));
  assert.ok(step, `Missing step ${name}`);
  const script = step.split('        run: |\n')[1];
  assert.ok(script, `Missing executable shell for ${name}`);
  return script.split('\n').map(line => line.startsWith('          ') ? line.slice(10) : line).join('\n');
}

function validate(t, { body = `/compare-static-egress-access ${sha} ironwood`, user = 'bright4862-design',
  ref = 'refs/heads/main', eventSha = sha, head = sha, remote = sha, dirty = false, fetchFail = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'fixlist-comparison-command-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  mkdirSync(join(dir, 'bin'));
  writeFileSync(join(dir, 'bin/git'), `#!/usr/bin/env bash
set -eu
case "$1" in
  rev-parse)
    case "$*" in
      'rev-parse HEAD') printf '%s\\n' "$TEST_HEAD";;
      'rev-parse --verify refs/remotes/origin/main'|'rev-parse refs/remotes/origin/main') printf '%s\\n' "$TEST_REMOTE";;
      *) exit 91;;
    esac;;
  fetch) printf '%s\\n' "$*" >> "$TEST_FETCHES"; test "$TEST_FETCH_FAIL" = false;;
  status) if [ "$TEST_DIRTY" = true ]; then printf ' M changed.py\\n'; fi;;
  -C) shift 2; exec "$0" "$@";;
  *) exit 92;;
esac
`);
  chmodSync(join(dir, 'bin/git'), 0o755);
  writeFileSync(join(dir, 'output'), '');
  const result = spawnSync('bash', ['-c', shellStep('Validate exact owner comparison command')], {
    cwd: root, encoding: 'utf8', timeout: 10000,
    env: { ...process.env, PATH: `${join(dir, 'bin')}:${process.env.PATH}`,
      COMMENT_BODY: body, COMMENT_USER: user, GITHUB_REF: ref, GITHUB_SHA: eventSha, GITHUB_ACTIONS: 'true',
      GITHUB_OUTPUT: join(dir, 'output'), TEST_HEAD: head, TEST_REMOTE: remote,
      TEST_FETCHES: join(dir, 'fetches'), TEST_FETCH_FAIL: String(fetchFail), TEST_DIRTY: String(dirty) },
  });
  assert.equal(result.error, undefined, String(result.error));
  return { ...result, output: readFileSync(join(dir, 'output'), 'utf8') };
}

test('comparison gate is restricted to owner PR comments and authenticates only after exact-main validation', () => {
  assert.ok(job, 'Owner-only comparison job must exist');
  assert.match(job, /github\.event_name == 'issue_comment'/);
  assert.match(job, /github\.event\.issue\.pull_request/);
  assert.match(job, /github\.event\.comment\.user\.login == 'bright4862-design'/);
  assert.match(job, /startsWith\(github\.event\.comment\.body, '\/compare-static-egress-access '\)/);
  assert.ok(job.indexOf('Validate exact owner comparison command') < job.indexOf('google-github-actions/auth@v3'));
  assert.match(job, /persist-credentials: false/);
  assert.match(job, /service_account: \$\{\{ env\.GCP_OPERATOR_SERVICE_ACCOUNT \}\}/);
  assert.match(shellStep('Validate exact owner comparison command'), /\+refs\/heads\/main:refs\/remotes\/origin\/main/);
});

for (const target of aliases) {
  test(`exact current-main command accepts fixed alias ${target}`, t => {
    const result = validate(t, { body: `/compare-static-egress-access ${sha} ${target}` });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.output, new RegExp(`^source_sha=${sha}$`, 'm'));
    assert.match(result.output, new RegExp(`^target=${target}$`, 'm'));
  });
}

for (const [label, settings] of [
  ['non-owner', { user: 'other-owner' }],
  ['branch execution', { ref: 'refs/heads/codex/other' }],
  ['event mismatch', { eventSha: 'b'.repeat(40) }],
  ['stale main', { remote: 'b'.repeat(40) }],
  ['dirty checkout', { dirty: true }],
  ['failed main refresh', { fetchFail: true }],
  ['short SHA', { body: `/compare-static-egress-access ${sha.slice(1)} ironwood` }],
  ['uppercase SHA', { body: `/compare-static-egress-access ${sha.toUpperCase()} ironwood` }],
  ['arbitrary URL', { body: `/compare-static-egress-access ${sha} https://example.com` }],
  ['unknown alias', { body: `/compare-static-egress-access ${sha} rbi` }],
  ['extra argument', { body: `/compare-static-egress-access ${sha} ironwood promote` }],
  ['trailing space', { body: `/compare-static-egress-access ${sha} ironwood ` }],
  ['multiline injection', { body: `/compare-static-egress-access ${sha} ironwood\nprintf danger` }],
  ['shell substitution', { body: `/compare-static-egress-access ${sha} $(printf ironwood)` }],
]) {
  test(`comparison command rejects ${label} before producing mutation inputs`, t => {
    const result = validate(t, settings);
    assert.notEqual(result.status, 0, result.stdout);
    assert.equal(result.output, '');
  });
}

test('pair runs only the scoped runner and uploads only its sanitized output', () => {
  const script = shellStep('Run isolated default versus static access comparison');
  assert.match(script, /python3 scripts\/static_egress_comparison_job\.py/);
  assert.match(script, /--confirm "STATIC-EGRESS-COMPARE:\$TARGET:\$REVISION:\$SOURCE_SHA"/);
  for (const flag of ['--revision', '--source-sha', '--target', '--run-id', '--attempt', '--output']) {
    assert.ok(script.includes(flag), flag);
  }
  assert.match(job, /path: \/tmp\/fixlist-static-egress-comparison\.json/);
  assert.match(job, /if-no-files-found: ignore/);
  assert.match(job, /fixlist\/static-egress-comparison-\$TARGET/);
  assert.match(job, /Pair diagnostic complete; access improvement unassessed/);
  assert.doesNotMatch(job, /update-traffic|promote-worker|run deploy|tasks queues|continue-on-error|upload-artifact[\s\S]*path:.*\*/);
});

function resolve(t, mutate = () => {}) {
  const dir = mkdtempSync(join(tmpdir(), 'fixlist-comparison-candidate-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  mkdirSync(join(dir, 'bin'));
  const revision = 'fixlist-standard150-worker-00100-abc';
  const rows = [{ metadata: { name: revision, creationTimestamp: '2026-10-12T00:00:00Z',
    labels: { 'serving.knative.dev/service': 'fixlist-standard150-worker' } },
  spec: { containers: [{ env: [{ name: 'FIXLIST_WORKER_SOURCE_SHA', value: sha },
    { name: 'FIXLIST_EGRESS_MODE', value: 'static-canary' }] }] },
  status: { conditions: [{ type: 'Ready', status: 'True' }] } }];
  const service = { metadata: { name: 'fixlist-standard150-worker' },
    spec: { traffic: [{ revisionName: 'fixlist-standard150-worker-00099-abc', percent: 100 }] },
    status: { traffic: [{ revisionName: 'fixlist-standard150-worker-00099-abc', percent: 100 }] } };
  mutate(rows, service);
  writeFileSync(join(dir, 'revisions.json'), JSON.stringify(rows));
  writeFileSync(join(dir, 'service.json'), JSON.stringify(service));
  writeFileSync(join(dir, 'bin/gcloud'), `#!/usr/bin/env bash
set -eu
case "$1 $2 $3" in
  'run revisions list') cat "$TEST_DIR/revisions.json";;
  'run services describe') cat "$TEST_DIR/service.json";;
  *) exit 93;;
esac
`);
  chmodSync(join(dir, 'bin/gcloud'), 0o755);
  writeFileSync(join(dir, 'output'), '');
  const script = shellStep('Resolve Ready zero-traffic candidate from this exact main')
    .replaceAll('/tmp/comparison-revisions.json', `${dir}/read-revisions.json`)
    .replaceAll('/tmp/comparison-service.json', `${dir}/read-service.json`);
  const result = spawnSync('bash', ['-c', script], { cwd: root, encoding: 'utf8', timeout: 10000,
    env: { ...process.env, PATH: `${join(dir, 'bin')}:${process.env.PATH}`, TEST_DIR: dir,
      SOURCE_SHA: sha, CLOUD_RUN_SERVICE: 'fixlist-standard150-worker', GCP_PROJECT: 'seo-autopilot-501517',
      GCP_REGION: 'europe-west1', GITHUB_OUTPUT: join(dir, 'output') } });
  assert.equal(result.error, undefined, String(result.error));
  return { ...result, output: readFileSync(join(dir, 'output'), 'utf8'), revision };
}

test('workflow resolves the Ready zero-traffic candidate built from the requested source', t => {
  const result = resolve(t);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.output, `revision=${result.revision}\n`);
});

for (const [label, mutate] of [
  ['obsolete source', rows => { rows[0].spec.containers[0].env[0].value = 'b'.repeat(40); }],
  ['unready candidate', rows => { rows[0].status.conditions[0].status = 'False'; }],
  ['foreign service', (_rows, service) => { service.metadata.name = 'foreign'; }],
  ['nonzero resolved traffic', (rows, service) => { service.status.traffic.push({ revisionName: rows[0].metadata.name, percent: 1 }); }],
  ['nonzero desired traffic', (rows, service) => { service.spec.traffic.push({ revisionName: rows[0].metadata.name, percent: 1 }); }],
  ['pending latest revision traffic', (_rows, service) => { service.spec.traffic = [{ latestRevision: true, percent: 100 }]; }],
]) {
  test(`workflow refuses ${label} before producing runner inputs`, t => {
    const result = resolve(t, mutate);
    assert.notEqual(result.status, 0, result.stdout);
    assert.equal(result.output, '');
  });
}
