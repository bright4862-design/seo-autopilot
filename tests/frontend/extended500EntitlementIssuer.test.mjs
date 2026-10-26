import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyAuthoritySeal } from '../../base44/functions/persistDurableScanAuthority/authoritySeal.js';
import {
  evaluateExtended500Entitlement, mintExtended500AdmissionEvidence,
  EXTENDED500_ENTITLEMENT_VERSION, EXTENDED500_ACCESS_PLAN_ID,
  EXTENDED500_ACCESS_APP_ID,
} from '../../src/lib/extended500EntitlementIssuer.js';

const user = { id: 'owner-one', email: 'owner@example.com' };
const scan = {
  id: 'scan-one', owner_user_id: user.id, project_id: 'project-one',
  request_id: 'request-one', idempotency_key: 'idem-one', attempt_count: 3,
  scan_mode: 'extended_500', status: 'queued',
  website_url: 'https://example.com/',
  path_prefix: null, respect_robots_txt: true,
  owner_attested_robots_override: false,
};
const access = {
  id: 'access-one', owner_user_id: user.id, user_email: user.email,
  app_id: EXTENDED500_ACCESS_APP_ID, plan_id: EXTENDED500_ACCESS_PLAN_ID,
  access_status: 'active', has_full_access: true, grant_source: 'stripe_checkout',
  paid_at: '2026-10-26T14:00:00Z', stripe_checkout_session_id: 'cs_test_signed',
};
const entitlementKey = 'fixture-entitlement-secret-aaaaaaaaaaaaaaaa';
const grantKey = 'fixture-grant-secret-bbbbbbbbbbbbbbbbbbbbb';

test('only a paid owner-bound Extended 500 grant can be minted, both signatures bind mode and attempt', async () => {
  const evidence = await mintExtended500AdmissionEvidence({
    user, accessRows: [access], scan, entitlementSigningKey: entitlementKey,
    grantSigningKey: grantKey, nowMs: Date.parse('2026-10-26T15:00:00Z'),
  });
  assert.equal(evidence.ok, true);
  const { proof: entitlementProof, ...document } = evidence.entitlement;
  const { proof: preflightProof, ...grant } = evidence.preflight_grant;
  assert.equal(document.version, EXTENDED500_ENTITLEMENT_VERSION);
  assert.equal(document.plan_id, EXTENDED500_ACCESS_PLAN_ID);
  assert.equal(document.attempt_count, 3);
  assert.equal(document.access_id, 'access-one');
  assert.equal(grant.attempt_count, 3);
  assert.equal(grant.canonical_mode, 'extended_500');
  assert.equal(grant.expires_at, '2026-10-26T15:02:00.000Z');
  assert.equal(await verifyAuthoritySeal(document, entitlementKey, entitlementProof), true);
  assert.equal(await verifyAuthoritySeal(grant, grantKey, preflightProof), true);
  assert.equal(await verifyAuthoritySeal(document, grantKey, entitlementProof), false);
  assert.equal(await verifyAuthoritySeal({ ...document, attempt_count: 4 }, entitlementKey, entitlementProof), false);
});

test('independent 500 plan rejects Standard 150, pending, fake owner, manual/preview and duplicates', () => {
  const cases = [
    [{ ...access, plan_id: 'standard150_lifetime' }],
    [{ ...access, access_status: 'pending', has_full_access: false }],
    [{ ...access, owner_user_id: 'other' }],
    [{ ...access, user_email: 'unrelated@example.com' }],
    [{ ...access, grant_source: 'owner_test' }],
    [{ ...access, grant_source: 'manual_grant' }],
    [{ ...access, stripe_checkout_session_id: '' }],
    [{ ...access, paid_at: '' }],
    [access, { ...access, id: 'access-two' }],
    [],
  ];
  for (const accessRows of cases) {
    assert.equal(evaluateExtended500Entitlement({ user, accessRows, scan }).ok, false);
  }
  for (const changed of [
    { ...scan, scan_mode: 'standard_150' }, { ...scan, attempt_count: 0 },
    { ...scan, owner_user_id: 'someone-else' }, { ...scan, status: 'complete' },
  ]) assert.equal(evaluateExtended500Entitlement({ user, accessRows: [access], scan: changed }).ok, false);
});

test('preflight issuer refuses missing or reused cryptographic keys and invalid frozen robots policy', async () => {
  const base = { user, accessRows: [access], scan, entitlementSigningKey: entitlementKey, grantSigningKey: grantKey };
  assert.equal((await mintExtended500AdmissionEvidence({ ...base, grantSigningKey: entitlementKey })).ok, false);
  assert.equal((await mintExtended500AdmissionEvidence({ ...base, grantSigningKey: 'short' })).ok, false);
  assert.equal((await mintExtended500AdmissionEvidence({
    ...base, scan: { ...scan, respect_robots_txt: true, owner_attested_robots_override: true },
  })).reason, 'frozen_robots_policy_invalid');
});
