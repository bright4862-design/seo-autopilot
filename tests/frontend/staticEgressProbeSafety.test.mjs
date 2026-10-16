import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const root = fileURLToPath(new URL('../../', import.meta.url));
const source = readFileSync(join(root, 'scripts/verify-fixlist-static-egress-source-ip.sh'), 'utf8');
const start = source.indexOf('tmp="$(mktemp -d)"');
assert.ok(start > 0, 'production probe body must exist');
const body = 'set -euo pipefail\n' + source.slice(start);
const sha = '2d9afe7dfe9eda1aebdcd6c1c2082eb680d70539';
const revision = 'fixlist-standard150-worker-test';
const worker = 'fixlist-standard150-worker';
const imageBase = 'europe-west1-docker.pkg.dev/seo-autopilot-501517/fixlist/scanner';
const digest = 'sha256:' + 'a'.repeat(64);
const image = imageBase + '@' + digest;
const sa = 'scanner@seo-autopilot-501517.iam.gserviceaccount.com';

function fixture() {
  return {
    metadata: { name: revision, labels: { 'serving.knative.dev/service': worker }, annotations: {
      'run.googleapis.com/network-interfaces': JSON.stringify([{ network: 'fixlist-scanner-egress', subnetwork: 'fixlist-scanner-egress-euw1' }]),
      'run.googleapis.com/vpc-access-egress': 'all-traffic',
    } },
    spec: { serviceAccountName: sa, containers: [{ image: imageBase + ':release', env: [
      { name: 'FIXLIST_WORKER_SOURCE_SHA', value: sha }, { name: 'FIXLIST_EGRESS_MODE', value: 'static-canary' },
    ] }] },
    status: { imageDigest: digest, conditions: [{ type: 'Ready', status: 'True' }] },
  };
}

// Execute the production probe body. Only gcloud is replaced; no cloud writes,
// credentials, or website requests occur. Exact-main/infrastructure gates have
// independent coverage and are intentionally outside this harness.
function runProbe(t, mutate = () => {}, options = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'fixlist-egress-safety-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const rev = fixture(); mutate(rev);
  mkdirSync(join(dir, 'bin'));
  writeFileSync(join(dir, 'input.json'), JSON.stringify({ revision: rev, options }));
  const python = spawnSync('python3', ['-S', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' });
  assert.equal(python.status, 0, python.stderr);
  writeFileSync(join(dir, 'bin/python3'), `#!/usr/bin/env bash\nexec '${python.stdout.trim()}' -S "$@"\n`);
  chmodSync(join(dir, 'bin/python3'), 0o755);
  writeFileSync(join(dir, 'bin/gcloud'), `#!/usr/bin/env python3
import json, os, pathlib, sys
p=pathlib.Path(os.environ['TEST_DIR']); a=sys.argv[1:]
x=json.loads((p/'input.json').read_text()); o=x['options']
with (p/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\\n')
if a[:3] == ['run','revisions','describe']: print(json.dumps(x['revision']))
elif a[:3] == ['run','services','describe']:
    print(json.dumps({'metadata': {'name': '${worker}'}, 'status': {'traffic': [{'revisionName': '${revision}', 'percent': o.get('traffic',0)}]}}))
elif a[:3] == ['compute','addresses','describe']: print('34.100.10.20')
elif a[:3] == ['run','jobs','create']:
    if o.get('create_error'): raise SystemExit(1)
    flags=next(z.split('=',1)[1] for z in a if z.startswith('--flags-file='))
    (p/'flags.json').write_text(pathlib.Path(flags).read_text())
elif a[:3] == ['run','jobs','execute']:
    if o.get('execute_error'): raise SystemExit(1)
    print(o.get('execution',a[3]+'-abc'))
elif a[:3] == ['run','jobs','delete']:
    if o.get('delete_error'): raise SystemExit(1)
elif a[:2] == ['logging','read']:
    print('FIXLIST_STATIC_EGRESS_PROBE='+json.dumps({'source_ip': o.get('observed_ip','34.100.10.20')}))
else: raise SystemExit('unexpected gcloud command: '+repr(a))
`);
  chmodSync(join(dir, 'bin/gcloud'), 0o755);
  const env = { ...process.env, PATH: `${join(dir, 'bin')}:${process.env.PATH}`, TEST_DIR: dir,
    PROJECT: 'seo-autopilot-501517', REGION: 'europe-west1', WORKER: worker, SOURCE_SHA: sha,
    TARGET_REVISION: revision, NETWORK: 'fixlist-scanner-egress', SUBNET: 'fixlist-scanner-egress-euw1',
    ADDRESS: 'fixlist-scanner-egress-ip-a', RUN_ID: '123456', ATTEMPT: '1' };
  const result = spawnSync('bash', ['-c', body], { env, encoding: 'utf8', timeout: 15000 });
  assert.equal(result.error, undefined, `probe harness did not complete: ${result.error}`);
  const calls = readFileSync(join(dir, 'calls.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  const count = action => calls.filter(a => a.slice(0,3).join(' ') === `run jobs ${action}`).length;
  const flags = existsSync(join(dir, 'flags.json')) ? JSON.parse(readFileSync(join(dir, 'flags.json'), 'utf8')) : null;
  return { ...result, count, calls, flags };
}

for (const form of ['bare', 'fully-qualified', 'pinned']) {
  test(`accepts ${form} immutable image identity`, t => {
    const r = runProbe(t, v => {
      if (form === 'fully-qualified') v.status.imageDigest = image;
      if (form === 'pinned') v.spec.containers[0].image = image;
    });
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.flags['--image'], image);
    assert.equal(r.flags['--service-account'], sa);
    assert.equal(r.flags['--vpc-egress'], 'all-traffic');
    assert.equal(r.count('create'), 1); assert.equal(r.count('delete'), 1);
    assert.match(r.stdout, /STATIC_EGRESS_SOURCE_IP_VERIFIED=1/);
  });
}

for (const [label, mutate] of [
  ['conflicting resolved digest', v => { v.spec.containers[0].image=image; v.status.imageDigest='sha256:'+'b'.repeat(64); }],
  ['malformed digest', v => { v.status.imageDigest='sha256:not-a-digest'; }],
  ['wrong revision identity', v => { v.metadata.name='fixlist-standard150-worker-other'; }],
  ['wrong service identity', v => { v.metadata.labels['serving.knative.dev/service']='other-service'; }],
  ['not-ready revision', v => { v.status.conditions=[]; }],
  ['sidecar', v => { v.spec.containers.push({ image }); }],
  ['proxy environment', v => { v.spec.containers[0].env.push({ name:'HTTPS_PROXY',value:'http://proxy.example' }); }],
]) {
  test(`rejects ${label} without creating or deleting a job`, t => {
    const r=runProbe(t,mutate);
    assert.notEqual(r.status,0);
    assert.equal(r.count('create'),0); assert.equal(r.count('delete'),0);
    assert.doesNotMatch(r.stdout,/SOURCE_IP_VERIFIED=1/);
  });
}

test('nonzero traffic is refused without cleanup of an unowned job', t => {
  const r=runProbe(t,()=>{}, {traffic:1});
  assert.notEqual(r.status,0); assert.equal(r.count('create'),0); assert.equal(r.count('delete'),0);
});
test('failed create never deletes a pre-existing same-named job', t => {
  const r=runProbe(t,()=>{}, {create_error:true});
  assert.notEqual(r.status,0); assert.equal(r.count('create'),1); assert.equal(r.count('delete'),0);
});
test('execution failure cleans up the job this invocation created', t => {
  const r=runProbe(t,()=>{}, {execute_error:true});
  assert.notEqual(r.status,0); assert.equal(r.count('delete'),1);
});
test('failed cleanup cannot report verified', t => {
  const r=runProbe(t,()=>{}, {delete_error:true});
  assert.notEqual(r.status,0); assert.doesNotMatch(r.stdout,/SOURCE_IP_VERIFIED=1/);
});
test('foreign execution identity cannot supply source-IP evidence', t => {
  const r=runProbe(t,()=>{}, {execution:'foreign-execution'});
  assert.notEqual(r.status,0); assert.equal(r.count('delete'),1);
  assert.equal(r.calls.filter(a=>a[0]==='logging').length,0);
});
test('IP mismatch still cleans up and fails closed', t => {
  const r=runProbe(t,()=>{}, {observed_ip:'34.100.10.21'});
  assert.notEqual(r.status,0); assert.equal(r.count('delete'),1); assert.doesNotMatch(r.stdout,/SOURCE_IP_VERIFIED=1/);
});
