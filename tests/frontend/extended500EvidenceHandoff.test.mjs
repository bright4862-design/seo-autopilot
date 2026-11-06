import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthoritySeal } from '../../base44/functions/persistDurableScanAuthority/authoritySeal.js';
import {
  EXTENDED500_HANDOFF_VERSION,
  verifyExtended500EvidenceHandoff,
} from '../../src/lib/extended500EvidenceHandoff.js';

const secret = 'fixture-secret-not-for-production';
const frozenScan = {
  scan_mode: 'extended_500',
  owner_user_id: 'owner-500', id: 'scan-500', project_id: 'project-500',
  request_id: 'req-500', idempotency_key: 'idem-500',
  normalized_domain: 'example.com', attempt_count: 1,
};

async function fixture(size = 500) {
  const payload = {
    version: EXTENDED500_HANDOFF_VERSION,
    identity: {
      canonical_mode: 'extended_500', owner_user_id: frozenScan.owner_user_id,
      scan_id: frozenScan.id, project_id: frozenScan.project_id,
      request_id: frozenScan.request_id, idempotency_key: frozenScan.idempotency_key,
      normalized_domain: frozenScan.normalized_domain, attempt_count: '1',
    },
    scan: {
      canonical_mode: 'extended_500', scan_id: frozenScan.id,
      request_id: frozenScan.request_id, idempotency_key: frozenScan.idempotency_key,
      normalized_domain: frozenScan.normalized_domain,
      pages_found: size + 5, pages_crawled: size,
      scan_coverage: {
        urls_attempted: size + 2,
        usable_html_pages: size,
        unique_retained_destinations: size,
      },
      scanner_source_sha: 'a'.repeat(40),
      beta_revision_fingerprint: 'b'.repeat(16),
      pages: Array.from({ length: size }, (_, index) => ({
        url: `https://example.com/page-${index}`,
        final_url: `https://example.com/page-${index}`, status_code: 200,
      })),
    },
    review: { review_status: 'not_reviewed', pages_reviewed: 0, release_gate_eligible: false },
  };
  return { ...payload, proof: await createAuthoritySeal(payload, secret) };
}
async function resigned(envelope) {
  const { proof: _, ...signed } = envelope;
  return { ...signed, proof: await createAuthoritySeal(signed, secret) };
}

test('only the exact signed Extended 500 evidence handoff is staged (never authority)', async () => {
  const envelope = await fixture();
  assert.deepEqual(await verifyExtended500EvidenceHandoff(envelope, frozenScan, secret), {
    valid: true, state: 'unreviewed_evidence_only', pages_retained: 500,
  });

  assert.deepEqual(
    await verifyExtended500EvidenceHandoff(
      envelope, { ...frozenScan, attempt_count: 2 }, secret,
    ),
    { valid: false, reason: 'attempt_mismatch' },
  );
  assert.deepEqual(
    await verifyExtended500EvidenceHandoff(
      envelope, { ...frozenScan, scan_mode: 'standard_150' }, secret,
    ),
    { valid: false, reason: 'mode_invalid' },
  );
});

test('tampering and newly resigned premature release claims are both refused', async () => {
  const evidence = await fixture();
  const tampered = { ...evidence, scan: { ...evidence.scan, pages_crawled: 499 } };
  assert.equal((await verifyExtended500EvidenceHandoff(tampered, frozenScan, secret)).valid, false);
  const claim = await resigned({
    ...evidence,
    review: { ...evidence.review, review_status: 'complete', release_gate_eligible: true },
  });
  assert.equal(
    (await verifyExtended500EvidenceHandoff(claim, frozenScan, secret)).reason,
    'premature_authority_claim',
  );
  const fakeLegacy = await resigned({ ...evidence, version: 'durable_standard150_completion_v1' });
  assert.equal(
    (await verifyExtended500EvidenceHandoff(fakeLegacy, frozenScan, secret)).reason,
    'version_invalid',
  );
});

test('500 max, count/identity mismatches, duplicate destinations and source pins fail closed', async () => {
  const atCap = await fixture();
  const tooMany = await resigned({
    ...atCap,
    scan: {
      ...atCap.scan, pages_found: 510, pages_crawled: 501,
      pages: [...atCap.scan.pages, { url: 'https://example.com/overflow' }],
      scan_coverage: {
        ...atCap.scan.scan_coverage, urls_attempted: 503,
        unique_retained_destinations: 501,
      },
    },
  });
  assert.equal((await verifyExtended500EvidenceHandoff(tooMany, frozenScan, secret)).reason, 'page_count_invalid');
  const duplicate = await resigned({
    ...atCap,
    scan: {
      ...atCap.scan,
      pages: [...atCap.scan.pages.slice(0, -1), atCap.scan.pages[0]],
    },
  });
  assert.equal((await verifyExtended500EvidenceHandoff(duplicate, frozenScan, secret)).reason, 'duplicate_retained_destination');
  const wrongSource = await resigned({
    ...atCap, scan: { ...atCap.scan, scanner_source_sha: 'not-immutable' },
  });
  assert.equal((await verifyExtended500EvidenceHandoff(wrongSource, frozenScan, secret)).reason, 'source_identity_invalid');
  const wrongProject = await resigned({
    ...atCap, identity: { ...atCap.identity, project_id: 'someone-elses-project' },
  });
  assert.equal((await verifyExtended500EvidenceHandoff(wrongProject, frozenScan, secret)).reason, 'identity_mismatch');
});
