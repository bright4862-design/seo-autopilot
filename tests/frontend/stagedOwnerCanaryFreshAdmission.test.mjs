import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

// Source-contract probe only; never invokes the Base44 client or dispatches scans.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const canary = fs.readFileSync(path.join(root, 'scripts/run-staged-owner-canary.sh'), 'utf8');
const launcher = fs.readFileSync(path.join(root, 'base44/functions/startStandardScanJobV9/entry.ts'), 'utf8');
const begin = canary.indexOf('function freshAdmissionClaim(');
const end = canary.indexOf('\nfunction verifiedCustomerReopen(', begin);
assert.ok(begin !== -1 && end > begin, 'fresh admission predicate must be present in the canary');
const fresh = vm.runInNewContext(canary.slice(begin, end) + '\nfreshAdmissionClaim', {});

const reply = (extra = {}) => ({
  success: true, accepted: true, replayed: false, replay_reason: 'server_admitted', ...extra,
});

test('fresh accepted claim is allowed by the launch guard', () => {
  assert.equal(fresh(reply()), true);
  assert.match(canary, /requireCondition\(freshAdmissionClaim\(accepted\), 'canary_fresh_admission_unverified'\)/);
});

for (const [name, input] of [
  ['terminal request replay', reply({replayed: true, replay_reason: 'request_replay'})],
  ['recovered request replay', reply({replayed: true, replay_reason: 'request_replay_recovered'})],
  ['replay flag omitted', {success: true, accepted: true, replay_reason: ''}],
  ['replay reason omitted', {success: true, accepted: true, replayed: false}],
  ['browser-row reason instead of new server claim', reply({replay_reason: ''})],
  ['conflicting reason on false replay flag', reply({replay_reason: 'request_replay'})],
  ['unknown null replay flag', reply({replayed: null})],
]) {
  test('idempotent launch cannot count as a fresh owner canary: ' + name, () => {
    // Previous code accepted every response in this set.
    assert.equal(input.success === true && input.accepted === true, true);
    assert.equal(fresh(input), false);
  });
}

test('V9 launcher explicitly emits replay metadata for accepted paths', () => {
  assert.match(launcher, /let admissionMeta = \{ replayed: false, replay_reason: "" \}/);
  assert.match(launcher, /replayed: admitted\.replayed === true/);
  assert.match(launcher, /replay_reason: admitted\.replayReason \|\| ""/);
  assert.match(launcher, /replayReason: claim\.outcome === "replayed" \? "request_replay_recovered" : "server_admitted"/);
  assert.ok((launcher.match(/\.\.\.admissionMeta,/g) || []).length >= 2);
});
