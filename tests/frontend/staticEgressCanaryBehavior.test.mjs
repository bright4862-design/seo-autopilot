import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const python = spawnSync('python3', ['-S', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).stdout.trim();
const root = fileURLToPath(new URL('../../', import.meta.url));
const verifier = join(root, 'scripts/verify-fixlist-static-egress-canary.sh');
const probe = readFileSync(join(root, 'scripts/verify-fixlist-static-egress-source-ip.sh'), 'utf8');
const project = 'seo-autopilot-501517';
const region = 'europe-west1';
const base = `https://www.googleapis.com/compute/v1/projects/${project}`;
const network = `${base}/global/networks/fixlist-scanner-egress`;
const subnet = `${base}/regions/${region}/subnetworks/fixlist-scanner-egress-euw1`;
const address = `${base}/regions/${region}/addresses/fixlist-scanner-egress-ip-a`;

function fixtures() {
  return {
    network: { autoCreateSubnetworks: false },
    subnet: { ipCidrRange: '10.210.0.0/24', network },
    address: { addressType: 'EXTERNAL', networkTier: 'PREMIUM', region: `${base}/regions/${region}`, selfLink: address, address: '34.100.10.20' },
    router: { network },
    nat: { natIpAllocateOption: 'MANUAL_ONLY', natIps: [address], sourceSubnetworkIpRangesToNat: 'LIST_OF_SUBNETWORKS', minPortsPerVm: 256, subnetworks: [{ name: subnet, sourceIpRangesToNat: ['ALL_IP_RANGES'] }] },
  };
}

// Only external commands are faked. The production verifier and log-reading shell
// execute unchanged; no cloud credentials, target sites, or network are needed.
function sandbox(t, data = fixtures(), options = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'fixlist-egress-test-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  mkdirSync(join(dir, 'bin'));
  // These scripts use only stdlib; isolate tests from machine-wide site hooks.
  writeFileSync(join(dir, 'bin/python3'), `#!/usr/bin/env bash\nexec '${python}' -S \"$@\"\n`);
  chmodSync(join(dir, 'bin/python3'), 0o755);
  writeFileSync(join(dir, 'fixtures.json'), JSON.stringify(data));
  writeFileSync(join(dir, 'options.json'), JSON.stringify(options));
  writeFileSync(join(dir, 'bin/gcloud'), `#!/usr/bin/env -S python3 -S
import json, os, pathlib, sys
p = pathlib.Path(os.environ['TEST_DIR'])
a = sys.argv[1:]
with (p/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\\n')
d = json.loads((p/'fixtures.json').read_text())
o = json.loads((p/'options.json').read_text())
if a[:3] == ['run','jobs','execute']:
    print('fixlist-egress-probe-123-1-abc'); sys.exit(0)
if a[:2] == ['logging','read']:
    count = int((p/'log-count').read_text()) + 1 if (p/'log-count').exists() else 1
    (p/'log-count').write_text(str(count))
    if o.get('log_error'): sys.exit(1)
    if count >= o.get('visible_after', 1):
        print(o.get('payload', 'FIXLIST_STATIC_EGRESS_PROBE={"source_ip":"34.100.10.20"}'))
    sys.exit(0)
if a[:2] == ['compute','networks']:
    key = 'subnet' if a[2] == 'subnets' else 'network'
elif a[:2] == ['compute','addresses']: key = 'address'
elif a[:2] == ['compute','routers']: key = 'nat' if a[2] == 'nats' else 'router'
else: raise SystemExit('Unexpected command in test: '+repr(a))
if o.get('read_error') == key: sys.exit(1)
print(json.dumps(d[key]))
`);
  writeFileSync(join(dir, 'bin/sleep'), '#!/usr/bin/env bash\nprintf "%s\\n" "$1" >> "$TEST_DIR/sleeps"\n');
  chmodSync(join(dir, 'bin/gcloud'), 0o755);
  chmodSync(join(dir, 'bin/sleep'), 0o755);
  const env = { ...process.env, PATH: `${join(dir, 'bin')}:${process.env.PATH}`, TEST_DIR: dir };
  // Do not let a developer's shell override the fixed fixtures.
  for (const key of Object.keys(env)) if (/^(FIXLIST_EGRESS_|GCP_|CLOUD_RUN_|SOURCE_SHA|TARGET_REVISION|CONFIRM)/.test(key)) delete env[key];
  return { dir, env };
}

function runVerifier(t, mutate = () => {}, options = {}, direct = false) {
  const data = fixtures(); mutate(data);
  const { dir, env } = sandbox(t, data, options);
  const result = spawnSync(direct ? verifier : 'bash', direct ? [] : [verifier], { env, encoding: 'utf8', timeout: 15000 });
  return { ...result, dir };
}

function assertRefused(result) {
  assert.equal(result.error, undefined, `Verifier did not complete: ${result.error}`);
  assert.notEqual(result.status, 0, result.stdout);
  assert.doesNotMatch(result.stdout || '', /STATIC_EGRESS_CANARY_READY=1/);
}

test('the nested-call verifier is executable from its actual checkout mode', t => {
  const result = runVerifier(t, () => {}, {}, true);
  assert.equal(result.error, undefined, `Direct invocation failed: ${result.error}`);
  assert.equal(result.status, 0, result.stderr);
});

test('one canonical manually assigned source IP passes real verifier', t => {
  const result = runVerifier(t);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /STATIC_EGRESS_IP=34\.100\.10\.20/);
});

for (const [label, mutate] of [
  ['second IP', d => d.nat.natIps.push(address.replace('ip-a', 'ip-b'))],
  ['duplicate IP', d => d.nat.natIps.push(address)],
  ['same name in another project', d => d.nat.natIps = [address.replace(project, 'other-project')]],
  ['same name in another region', d => d.nat.natIps = [address.replace(region, 'us-central1')]],
  ['draining IP', d => d.nat.drainNatIps = [address.replace('ip-a', 'ip-b')]],
  ['NAT rule source override', d => d.nat.rules = [{ ruleNumber: 100, action: { sourceNatActiveIps: [address.replace('ip-a', 'ip-b')] } }]],
  ['automatic IP allocation', d => d.nat.natIpAllocateOption = 'AUTO_ONLY'],
  ['wrong subnet', d => d.nat.subnetworks[0].name = subnet + '-other'],
  ['second subnet', d => d.nat.subnetworks.push({ name: subnet + '-other', sourceIpRangesToNat: ['ALL_IP_RANGES'] })],
  ['wrong CIDR', d => d.subnet.ipCidrRange = '10.210.0.0/26'],
]) {
  test(`refuses ${label}`, t => assertRefused(runVerifier(t, mutate)));
}

test('missing cloud read permission never becomes a ready result', t => {
  assertRefused(runVerifier(t, () => {}, { read_error: 'nat' }));
});

function runLogReader(t, options) {
  const { dir, env } = sandbox(t, fixtures(), options);
  const start = probe.indexOf('execution="$(gcloud run jobs execute');
  assert.ok(start > 0, 'production source-IP execution/log block must exist');
  const script = 'set -euo pipefail\n' + probe.slice(start);
  const result = spawnSync('bash', ['-c', script], { env: { ...env, tmp: dir, job: 'fixlist-egress-probe-123-1', PROJECT: project, REGION: region, EXPECTED_IP: '34.100.10.20', TARGET_REVISION: 'fixlist-standard150-worker-canary' }, encoding: 'utf8', timeout: 15000 });
  const count = Number(readFileSync(join(dir, 'log-count'), 'utf8'));
  return { ...result, count, dir };
}

test('delayed attributable IP log is found without executing another job', t => {
  const result = runLogReader(t, { visible_after: 3 });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.count, 3);
  assert.match(result.stdout, /STATIC_EGRESS_SOURCE_IP_VERIFIED=1/);
  const calls = readFileSync(join(result.dir, 'calls.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(calls.filter(a => a.slice(0, 3).join(' ') === 'run jobs execute').length, 1);
  for (const args of calls.filter(a => a[0] === 'logging')) {
    assert.ok(args[2].includes('fixlist-egress-probe-123-1-abc'), 'exact execution filter retained');
  }
});

test('missing logs stop at twelve reads and never report verified', t => {
  const result = runLogReader(t, { visible_after: 100 });
  assert.notEqual(result.status, 0);
  assert.equal(result.count, 12);
  assert.doesNotMatch(result.stdout, /SOURCE_IP_VERIFIED=1/);
});

test('wrong source IP fails immediately rather than retrying to hide mismatch', t => {
  const result = runLogReader(t, { payload: 'FIXLIST_STATIC_EGRESS_PROBE={"source_ip":"34.100.10.21"}' });
  assert.notEqual(result.status, 0);
  assert.equal(result.count, 1);
  assert.doesNotMatch(result.stdout, /SOURCE_IP_VERIFIED=1/);
});

test('log permission denial fails rather than being treated as ingestion delay', t => {
  const result = runLogReader(t, { log_error: true });
  assert.notEqual(result.status, 0);
  assert.equal(result.count, 1);
  assert.doesNotMatch(result.stdout, /SOURCE_IP_VERIFIED=1/);
});
