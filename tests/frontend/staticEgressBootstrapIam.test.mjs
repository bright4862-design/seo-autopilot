import assert from 'node:assert/strict';
import { chmodSync, copyFileSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const root = fileURLToPath(new URL('../../', import.meta.url));
const bootstrapPath = 'scripts/bootstrap-fixlist-static-egress-canary.sh';
const bootstrap = readFileSync(join(root, bootstrapPath), 'utf8');
const provision = readFileSync(join(root, 'scripts/provision-fixlist-static-egress-canary.sh'), 'utf8');
const workflow = readFileSync(join(root, '.github/workflows/fixlist-cloud-operator.yml'), 'utf8');
const python = spawnSync('python3', ['-S', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).stdout.trim();
const operator = 'serviceAccount:fixlist-github-operator@seo-autopilot-501517.iam.gserviceaccount.com';
const readOnly = ['compute.addresses.get', 'compute.networks.get', 'compute.routers.get', 'compute.subnetworks.get'];
const project = 'seo-autopilot-501517';
const region = 'europe-west1';
const base = `https://www.googleapis.com/compute/v1/projects/${project}`;
const network = `${base}/global/networks/fixlist-scanner-egress`;
const subnet = `${base}/regions/${region}/subnetworks/fixlist-scanner-egress-euw1`;
const address = `${base}/regions/${region}/addresses/fixlist-scanner-egress-ip-a`;

test('operator verifier role is exactly four read-only compute permissions', () => {
  const declared = bootstrap.match(/^VERIFIER_PERMISSIONS="([^"]+)"$/m);
  assert.ok(declared, 'verifier permission list must be declared once');
  assert.deepEqual(declared[1].split(',').sort(), readOnly);
  assert.doesNotMatch(bootstrap, /compute\.[a-zA-Z]+\.(create|createInternal|update|updatePolicy|delete|use|setIamPolicy)\b/);
});

test('bootstrap never grants broad roles and binds only the verifier role to the operator', () => {
  const bindings = [...bootstrap.matchAll(/add-iam-policy-binding[\s\S]*?--quiet/g)].map(m => m[0]);
  assert.equal(bindings.length, 1, 'exactly one IAM binding');
  assert.match(bindings[0], /--member="serviceAccount:\$\{OPERATOR_SA\}"/);
  assert.match(bindings[0], /--role="\$VERIFIER_ROLE"/);
  assert.doesNotMatch(bootstrap, /--role="?roles\//);
  assert.doesNotMatch(bootstrap, /set-iam-policy|keys create|workload-identity/);
  for (const role of ['roles/owner', 'roles/editor', 'roles/compute.admin', 'roles/compute.networkAdmin']) {
    assert.ok(bootstrap.includes(role), `${role} must be refused, never granted`);
  }
});

test('network mutation stays in the exact-main provisioner run under admin credentials', () => {
  assert.match(bootstrap, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$SOURCE_SHA"/);
  assert.match(bootstrap, /BOOTSTRAP-STATIC-EGRESS-CANARY:\$SOURCE_SHA/);
  assert.match(bootstrap, /CONFIRM="STATIC-EGRESS-CANARY:\$SOURCE_SHA"/);
  assert.match(bootstrap, /scripts\/provision-fixlist-static-egress-canary\.sh/);
  assert.doesNotMatch(bootstrap, /compute (networks|addresses|routers) [a-z ]*create/);
  assert.doesNotMatch(bootstrap, /run (deploy|services update|jobs)|update-traffic|tasks queues (resume|pause)/);
  // The WIF operator path is unchanged and still cannot promote static egress.
  assert.doesNotMatch(workflow, /bootstrap-fixlist-static-egress-canary/);
  assert.doesNotMatch(workflow, /\/promote-static-egress-worker /);
  assert.doesNotMatch(provision, /add-iam-policy-binding|set-iam-policy/);
});

function fixtures() {
  return {
    network: { autoCreateSubnetworks: false },
    subnet: { ipCidrRange: '10.210.0.0/24', network },
    address: { addressType: 'EXTERNAL', networkTier: 'PREMIUM', region: `${base}/regions/${region}`, selfLink: address, address: '34.100.10.20' },
    router: { network },
    nat: { natIpAllocateOption: 'MANUAL_ONLY', natIps: [address], sourceSubnetworkIpRangesToNat: 'LIST_OF_SUBNETWORKS', minPortsPerVm: 256, subnetworks: [{ name: subnet, sourceIpRangesToNat: ['ALL_IP_RANGES'] }] },
  };
}

function git(cwd, ...args) {
  const result = spawnSync('git', ['-c', 'user.email=test@example.invalid', '-c', 'user.name=test', '-c', 'commit.gpgsign=false', ...args], { cwd, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

// Run the production bootstrap (and the production provisioner/verifier it
// calls) from an exact clean "main" checkout. Only gcloud is faked; existing
// canary resources make the provisioner describe-only, so nothing is created.
function runBootstrap(t, { confirm, sourceSha, options = {}, script = 'bootstrap' } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'fixlist-egress-bootstrap-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const origin = join(dir, 'origin.git');
  const repo = join(dir, 'repo');
  git(dir, 'init', '--quiet', '--bare', origin);
  git(dir, 'init', '--quiet', '-b', 'main', repo);
  for (const file of [bootstrapPath, 'scripts/lib/release-source-guard.sh', 'scripts/provision-fixlist-static-egress-canary.sh', 'scripts/verify-fixlist-static-egress-canary.sh']) {
    mkdirSync(dirname(join(repo, file)), { recursive: true });
    copyFileSync(join(root, file), join(repo, file));
    chmodSync(join(repo, file), statSync(join(root, file)).mode);
  }
  git(repo, 'add', '-A');
  git(repo, 'commit', '--quiet', '-m', 'fixture');
  git(repo, 'remote', 'add', 'origin', origin);
  git(repo, 'push', '--quiet', 'origin', 'main');
  git(repo, 'fetch', '--quiet', 'origin', 'main');
  const sha = git(repo, 'rev-parse', 'HEAD');
  if (options.stale_main) {
    git(repo, 'commit', '--quiet', '--allow-empty', '-m', 'new main');
    git(repo, 'push', '--quiet', 'origin', 'main');
    git(repo, 'reset', '--hard', sha);
    if (options.stale_tracking) {
      git(repo, 'update-ref', 'refs/remotes/origin/main', sha);
      git(repo, 'config', 'remote.origin.fetch', '+refs/heads/other:refs/remotes/origin/other');
    } else git(repo, 'update-ref', '-d', 'refs/remotes/origin/main');
  }
  if (options.dirty) writeFileSync(join(repo, 'dirty.txt'), 'unreviewed');

  const bin = join(dir, 'bin');
  mkdirSync(bin);
  writeFileSync(join(bin, 'python3'), `#!/usr/bin/env bash\nexec '${python}' -S "$@"\n`);
  writeFileSync(join(dir, 'fixtures.json'), JSON.stringify(fixtures()));
  writeFileSync(join(dir, 'options.json'), JSON.stringify(options));
  writeFileSync(join(bin, 'gcloud'), `#!/usr/bin/env -S python3 -S
import json, os, pathlib, sys
p = pathlib.Path(os.environ['TEST_DIR'])
a = sys.argv[1:]
with (p/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\\n')
o = json.loads((p/'options.json').read_text())
d = json.loads((p/'fixtures.json').read_text())
state = p/'role.json'
if o.get('fail_command') == ' '.join(a[:3]): sys.exit(1)
if a[:3] == ['config','set','project'] or a[:2] == ['services','enable']: sys.exit(0)
if a[:2] == ['projects','get-ancestors']:
    print(json.dumps([{'type':'project','id':'919035207432'}, *o.get('ancestors', [])])); sys.exit(0)
if a[:3] == ['resource-manager','folders','get-iam-policy'] or a[:2] == ['organizations','get-iam-policy']:
    held = o.get('inherited_role')
    print(json.dumps({'bindings': [{'role':held,'members':['${operator}']}] if held else []})); sys.exit(0)
if a[:2] == ['projects','get-iam-policy']:
    held = o.get('operator_role')
    if '--format=json' in a:
        print(json.dumps({'bindings':[{'role':held,'members':['${operator}']}] if held else []}))
    elif held and any(x == '--filter=bindings.role='+held+' AND bindings.members=${operator}' for x in a): print(held)
    sys.exit(0)
if a[:3] == ['iam','roles','describe']:
    if not state.exists():
        if o.get('existing_role'): state.write_text(json.dumps(${JSON.stringify(readOnly)}))
        else: sys.exit(1)
    perms = json.loads(state.read_text()) + o.get('extra_permissions', [])
    print(json.dumps({'name': 'projects/${project}/roles/fixlistStaticEgressVerifier', 'stage':o.get('role_stage','GA'), 'deleted':o.get('role_deleted',False), 'includedPermissions': perms})); sys.exit(0)
if a[:3] in (['iam','roles','create'], ['iam','roles','update']):
    perms = next(x.split('=',1)[1] for x in a if x.startswith('--permissions='))
    state.write_text(json.dumps(perms.split(','))); sys.exit(0)
if a[:2] == ['projects','add-iam-policy-binding']: sys.exit(0)
if a[:2] == ['compute','networks']: key = 'subnet' if a[2] == 'subnets' else 'network'
elif a[:2] == ['compute','addresses']: key = 'address'
elif a[:2] == ['compute','routers']: key = 'nat' if a[2] == 'nats' else 'router'
else: raise SystemExit('Unexpected command in test: '+repr(a))
if 'describe' not in a: raise SystemExit('Unexpected compute mutation in test: '+repr(a))
if o.get('read_error') == key: sys.exit(1)
fmt = next((x for x in a if x.startswith('--format=')), '')
if fmt == '--format=value(autoCreateSubnetworks)': print('False')
elif fmt == '--format=value(network)': print(d[key]['network'])
else: print(json.dumps(d[key]))
`);
  chmodSync(join(bin, 'python3'), 0o755);
  chmodSync(join(bin, 'gcloud'), 0o755);

  const env = { ...process.env, PATH: `${bin}:${process.env.PATH}`, TEST_DIR: dir, SOURCE_SHA: sourceSha ?? sha, CONFIRM: confirm ?? `BOOTSTRAP-STATIC-EGRESS-CANARY:${sha}` };
  // Exercise the local (Cloud Shell) guard path and the fixed canary names.
  for (const key of Object.keys(env)) if (/^(GITHUB_|FIXLIST_EGRESS_|GCP_)/.test(key)) delete env[key];
  if (options.stray_network) env.FIXLIST_EGRESS_NETWORK = 'some-other-network';
  Object.assign(env, options.overrides);
  if (options.spoof_actions) Object.assign(env, { GITHUB_ACTIONS: 'true', GITHUB_REF: 'refs/heads/main', GITHUB_SHA: sha });
  if (script === 'provision' || script === 'wif') env.CONFIRM = confirm ?? `STATIC-EGRESS-CANARY:${sourceSha ?? sha}`;
  const wifBlock = workflow.split('  provision-static-egress-canary-on-owner-comment:')[1].split('  stage-static-egress-worker-on-owner-comment:')[0];
  const wifCommand = wifBlock.match(/run: bash (scripts\/[\w-]+\.sh)/)[1];
  const target = script === 'wif' ? wifCommand : script === 'provision' ? 'scripts/provision-fixlist-static-egress-canary.sh' : bootstrapPath;
  const result = spawnSync('bash', [join(repo, target)], { cwd: repo, env, encoding: 'utf8', timeout: 30000 });
  const calls = existsSync(join(dir, 'calls.jsonl'))
    ? readFileSync(join(dir, 'calls.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse)
    : [];
  return { ...result, calls, sha };
}

const mutating = a => ['create', 'update', 'add-iam-policy-binding', 'enable'].some(v => a.includes(v));

test('exact-main bootstrap grants only the read-only role, then verifies existing canary infrastructure', t => {
  const r = runBootstrap(t);
  assert.equal(r.error, undefined, String(r.error));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /STATIC_EGRESS_CANARY_READY=1/);
  assert.match(r.stdout, /STATIC_EGRESS_IP=34\.100\.10\.20/);
  assert.match(r.stdout, /STATIC_EGRESS_BOOTSTRAP_COMPLETE/);
  const create = r.calls.find(a => a.slice(0, 3).join(' ') === 'iam roles create');
  assert.deepEqual(create.find(x => x.startsWith('--permissions=')).split('=')[1].split(',').sort(), readOnly);
  const bindings = r.calls.filter(a => a[1] === 'add-iam-policy-binding');
  assert.equal(bindings.length, 1);
  assert.ok(bindings[0].includes(`--member=${operator}`));
  assert.ok(bindings[0].includes(`--role=projects/${project}/roles/fixlistStaticEgressVerifier`));
  const firstMutation = r.calls.findIndex(mutating);
  const lastBroadRoleCheck = r.calls.map(a => a[1]).lastIndexOf('get-iam-policy');
  assert.ok(lastBroadRoleCheck < firstMutation, 'broad-role refusal must precede every mutation');
  assert.ok(r.calls.findIndex(a => a[0] === 'compute') > r.calls.indexOf(bindings[0]), 'provisioning follows the verified grant');
  assert.ok(r.calls.filter(a => a[0] === 'compute').every(a => a.includes('describe')), 'existing canary resources are never recreated');
});

test('human bootstrap cannot accept stale main through spoofed Actions variables', t => {
  const r = runBootstrap(t, { options: { stale_main: true, spoof_actions: true } });
  assert.equal(r.status, 2, r.stderr);
  assert.deepEqual(r.calls, []);
});

test('direct provisioner refuses an empty source SHA and degenerate confirmation', t => {
  const r = runBootstrap(t, {script:'provision', sourceSha:'', confirm:'STATIC-EGRESS-CANARY:'});
  assert.equal(r.status, 2, r.stderr);
  assert.deepEqual(r.calls, []);
});

for (const script of ['bootstrap', 'provision']) {
  test(`${script} refreshes main even with a nonstandard fetch mapping`, t => {
    const r = runBootstrap(t, {script,options:{stale_main:true,stale_tracking:true}});
    assert.equal(r.status, 2, r.stderr);
    assert.deepEqual(r.calls, []);
  });
}

for (const scope of ['folder', 'organization']) {
  test(`inherited network admin on a ${scope} refuses before cloud mutation`, t => {
    const r = runBootstrap(t, { options: { ancestors: [{type:scope,id:'12345'}], inherited_role:'roles/compute.networkAdmin' } });
    assert.equal(r.status, 4, r.stderr);
    assert.equal(r.calls.filter(mutating).length, 0);
  });
}

for (const key of ['network', 'subnet', 'address', 'router', 'nat']) {
  test(`WIF re-verification with a failed ${key} read never attempts creation`, t => {
    const r = runBootstrap(t, { script:'wif', options:{read_error:key} });
    assert.notEqual(r.status, 0);
    assert.equal(r.calls.filter(mutating).length, 0, JSON.stringify(r.calls));
    assert.doesNotMatch(r.stdout, /CANARY_READY=1/);
  });
}

for (const [name, value] of Object.entries({
  GCP_PROJECT:'other-project', GCP_REGION:'us-central1', FIXLIST_EGRESS_NETWORK:'other-network',
  FIXLIST_EGRESS_SUBNET:'other-subnet', FIXLIST_EGRESS_SUBNET_CIDR:'10.211.0.0/24',
  FIXLIST_EGRESS_ROUTER:'other-router', FIXLIST_EGRESS_NAT:'other-nat', FIXLIST_EGRESS_ADDRESS:'other-address',
})) {
  test(`direct provisioner refuses a ${name} override before cloud calls`, t => {
    const r = runBootstrap(t, {script:'provision', options:{overrides:{[name]:value}}});
    assert.equal(r.status, 2, r.stderr);
    assert.deepEqual(r.calls, []);
  });
}

test('disabled verifier role cannot be bound or provision infrastructure', t => {
  const r = runBootstrap(t, { options:{role_stage:'DISABLED'} });
  assert.notEqual(r.status, 0);
  assert.equal(r.calls.filter(a=>a[1]==='add-iam-policy-binding'||a[0]==='compute').length, 0);
});

for (const options of [
  {fail_command:'iam roles create'}, {existing_role:true,fail_command:'iam roles update'},
  {fail_command:'projects get-iam-policy seo-autopilot-501517'},
  {ancestors:[{type:'folder',id:'12345'}],fail_command:'resource-manager folders get-iam-policy'},
]) {
  test(`failed ${options.fail_command} stops before binding or provision`, t => {
    const r = runBootstrap(t, {options});
    assert.notEqual(r.status, 0);
    assert.equal(r.calls.filter(a=>a[1]==='add-iam-policy-binding'||a[0]==='compute').length, 0);
  });
}

for (const options of [{stale_main:true}, {dirty:true}]) {
  test(`bootstrap refuses ${options.dirty ? 'dirty checkout' : 'stale main'} before cloud calls`, t => {
    const r = runBootstrap(t, {options});
    assert.equal(r.status, 2, r.stderr);
    assert.deepEqual(r.calls, []);
  });
}

test('wrong confirmation refuses before any cloud call', t => {
  const r = runBootstrap(t, { confirm: 'BOOTSTRAP-STATIC-EGRESS-CANARY:' + '0'.repeat(40) });
  assert.notEqual(r.status, 0);
  assert.deepEqual(r.calls, []);
  assert.doesNotMatch(r.stdout, /BOOTSTRAP_COMPLETE/);
});

test('an empty source SHA cannot satisfy a degenerate confirmation', t => {
  const r = runBootstrap(t, { sourceSha: '', confirm: 'BOOTSTRAP-STATIC-EGRESS-CANARY:' });
  assert.equal(r.status, 2, r.stderr);
  assert.deepEqual(r.calls, []);
});

for (const role of ['roles/owner', 'roles/editor', 'roles/compute.admin', 'roles/compute.networkAdmin']) {
  test(`operator already holding ${role} refuses before any mutation`, t => {
    const r = runBootstrap(t, { options: { operator_role: role } });
    assert.equal(r.status, 4, r.stderr);
    assert.equal(r.calls.filter(mutating).length, 0);
    assert.equal(r.calls.filter(a => a[0] === 'compute').length, 0);
  });
}

test('verifier role permission drift refuses before the operator binding or provisioning', t => {
  const r = runBootstrap(t, { options: { extra_permissions: ['compute.networks.create'] } });
  assert.notEqual(r.status, 0);
  assert.equal(r.calls.filter(a => a[1] === 'add-iam-policy-binding').length, 0);
  assert.equal(r.calls.filter(a => a[0] === 'compute').length, 0);
});

test('a stray network override cannot redirect the canary contract names', t => {
  const r = runBootstrap(t, { options: { stray_network: true } });
  assert.equal(r.status, 0, r.stderr);
  for (const a of r.calls.filter(x => x[0] === 'compute' && x[1] === 'networks' && x[2] === 'describe')) {
    assert.equal(a[3], 'fixlist-scanner-egress');
  }
});
