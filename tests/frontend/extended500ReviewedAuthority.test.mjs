import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { createAuthoritySeal } from '../../base44/functions/persistDurableScanAuthority/authoritySeal.js';
import { EXTENDED500_HANDOFF_VERSION } from '../../src/lib/extended500EvidenceHandoff.js';
import { RELEASE_FINGERPRINT, RELEASE_COMPONENT_VERSIONS } from '../../src/lib/generatedReleaseContract.js';
import {
  EXTENDED500_REVIEWED_PURPOSE,
  EXTENDED500_REVIEWED_VERSION,
  EXTENDED500_REVIEWED_OPERATIONAL,
  canonicalReviewedJson,
  verifyExtended500ReviewedAuthority,
} from '../../src/lib/extended500ReviewedAuthority.js';

// Fixture roots only; NOT production secrets.
const handoffSecret = 'fixture-secret-not-for-production';
const secret = 'fixture-reviewed-root-not-for-production-500';
const expectedRelease = {
  scanner_source_sha: 'a'.repeat(40),
  beta_revision_fingerprint: RELEASE_FINGERPRINT,
  review_version: RELEASE_COMPONENT_VERSIONS.review_version,
};
const frozenScan = {
  scan_mode: 'extended_500', status: 'reviewing',
  owner_user_id: 'owner-500', id: 'scan-500', project_id: 'project-500',
  request_id: 'req-500', idempotency_key: 'idem-500',
  normalized_domain: 'example.com', attempt_count: 1, release_gate_eligible: false,
};
const url = (i) => `https://example.com/page-${i}`;
const identity = {
  canonical_mode: 'extended_500', owner_user_id: 'owner-500', scan_id: 'scan-500',
  project_id: 'project-500', request_id: 'req-500', idempotency_key: 'idem-500',
  normalized_domain: 'example.com', attempt_count: '1',
};

async function handoffFixture(size) {
  const payload = {
    version: EXTENDED500_HANDOFF_VERSION,
    identity,
    scan: {
      canonical_mode: 'extended_500', scan_id: 'scan-500', request_id: 'req-500',
      idempotency_key: 'idem-500', normalized_domain: 'example.com',
      pages_found: size + 10, pages_crawled: size,
      scan_coverage: { urls_attempted: size + 2, usable_html_pages: size, unique_retained_destinations: size },
      scanner_source_sha: expectedRelease.scanner_source_sha,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      pages: Array.from({ length: size }, (_, i) => ({ url: url(i), final_url: url(i), status_code: 200 })),
    },
    review: { review_status: 'not_reviewed', pages_reviewed: 0, release_gate_eligible: false },
  };
  return { ...payload, proof: await createAuthoritySeal(payload, handoffSecret) };
}

// Independent signer: purpose-derived key over the canonical bytes.
function sign(signed, root = secret) {
  const derived = createHmac('sha256', root).update(EXTENDED500_REVIEWED_PURPOSE).digest();
  return { ...signed, proof: createHmac('sha256', derived).update(canonicalReviewedJson(signed), 'utf8').digest('hex') };
}
function resign(envelope) {
  const { proof: _proof, ...signed } = envelope;
  return sign(signed);
}

function finding(fixId, ids, extra = {}) {
  return {
    fix_id: fixId, rule: `rule_${fixId}`, category: 'Metadata', issue_title: `Fix ${fixId}`,
    plain_english_explanation: '', simple_next_step: 'Do it.', priority: 'high',
    evidence_class: 'confirmed_problem', action_priority: 'fix_first', action_priority_score: 4380,
    canonical_action_rank: 1, page_scope: ids.length === 1 ? 'page' : 'family',
    page_template_family: 'article', affected_page_ids: ids, page_count: ids.length,
    page_url: url(Number(ids[0].slice(1)) - 1), evidence_status: 'confirmed',
    verification_state: 'verified', confidence_score: 88, repair_fingerprint: `fp_${fixId}`,
    user_status: 'open', repair_verification_state: 'not_compared', ...extra,
  };
}

async function fixture({ size = 4, reviewed = size } = {}) {
  const evidenceHandoff = await handoffFixture(size);
  const findings = [
    finding('f1', ['p001', 'p002']),
    finding('f2', ['p001'], { action_priority: 'important', action_priority_score: 3200, priority: 'medium', canonical_action_rank: 2 }),
  ];
  const signed = {
    version: EXTENDED500_REVIEWED_VERSION,
    purpose: EXTENDED500_REVIEWED_PURPOSE,
    operational_status: 'non_operational_no_verified_terminal_issuer',
    identity: { ...identity },
    release: { ...expectedRelease },
    evidence_binding: { handoff_version: EXTENDED500_HANDOFF_VERSION, handoff_proof: evidenceHandoff.proof },
    coverage: {
      pages_found: size + 10, urls_attempted: size + 2, usable_html_pages: size,
      pages_assessed: size, pages_reviewed: reviewed, pages_not_reviewed: size - reviewed,
      review_coverage_basis_points: Math.floor((reviewed * 10000) / size), pages_with_findings: 2,
    },
    review: {
      review_status: 'reviewed',
      review_coverage_state: reviewed === size ? 'all_assessed_pages_reviewed' : 'bounded_sample_reviewed',
      sampling_policy_version: 'extended500_review_all_assessed_v1',
      review_confidence_state: 'complete', score_is_provisional: reviewed < size,
      no_high_confidence_findings: false, health_score: 70,
      release_gate_eligible: false, terminal_receipt_state: 'not_issued',
    },
    pages: Array.from({ length: size }, (_, i) => ({
      page_id: `p${String(i + 1).padStart(3, '0')}`, final_url: url(i),
      review_state: i < reviewed ? 'reviewed' : 'not_reviewed',
    })),
    findings,
    fix_list_summary: {
      total_fixes: 2, critical_count: 0, high_count: 1, medium_count: 1, low_count: 0,
      fix_first_count: 1, important_count: 1, improve_count: 0, review_count: 0,
      completed_count: 0, top_action_fix_ids: ['f1', 'f2'], canonical_action_fix_ids: ['f1', 'f2'],
    },
  };
  return { envelope: sign(signed), evidenceHandoff };
}

const options = (evidenceHandoff, extra = {}) => ({
  frozenScan, expectedRelease, secret, evidenceHandoff, handoffSecret, ...extra,
});

test('a minimal reviewed envelope verifies but is never operational or publishable', async () => {
  const { envelope, evidenceHandoff } = await fixture();
  assert.equal(EXTENDED500_REVIEWED_OPERATIONAL, false);
  assert.deepEqual(await verifyExtended500ReviewedAuthority(envelope, options(evidenceHandoff)), {
    valid: true, state: 'reviewed_authority_candidate_non_operational', operational: false,
    customer_publishable: false, release_gate_eligible: false,
    pages_assessed: 4, pages_reviewed: 4, total_fixes: 2,
  });
  const sample = await fixture({ size: 10, reviewed: 3 });
  assert.equal((await verifyExtended500ReviewedAuthority(sample.envelope, options(sample.evidenceHandoff))).valid, true);
});

const mutate = (fn) => (e) => { fn(e); return e; };
const CASES = [
  ['unreviewed handoff presented as reviewed', (e, h) => structuredClone(h), false, 'unreviewed_handoff_not_promotable'],
  ['standard 150 completion version', mutate((e) => { e.version = 'durable_standard150_completion_v1'; }), true, 'version_invalid'],
  ['purpose swapped', mutate((e) => { e.purpose = 'fixlist-extended500-atomic-admission-v1'; }), true, 'purpose_invalid'],
  ['operational claim', mutate((e) => { e.operational_status = 'operational'; }), true, 'non_operational_marker_invalid'],
  ['top-level extra', mutate((e) => { e.complete = true; }), true, 'shape_invalid'],
  ['raw html smuggled', mutate((e) => { e.pages[0].raw_html = '<html>'; }), true, 'restricted_field_present'],
  ['main text smuggled', mutate((e) => { e.findings[0].main_text = 'body'; }), true, 'restricted_field_present'],
  ['standard150 identity mode', mutate((e) => { e.identity.canonical_mode = 'standard_150'; }), true, 'mode_invalid'],
  ['foreign tenant identity', mutate((e) => { e.identity.owner_user_id = 'owner-b'; }), true, 'identity_mismatch'],
  ['premature release gate', mutate((e) => { e.review.release_gate_eligible = true; }), true, 'premature_release_gate'],
  ['premature terminal receipt', mutate((e) => { e.review.terminal_receipt_state = 'issued'; }), true, 'premature_release_gate'],
  ['not reviewed status', mutate((e) => { e.review.review_status = 'not_reviewed'; }), true, 'review_not_reviewed'],
  ['stale source sha', mutate((e) => { e.release.scanner_source_sha = 'b'.repeat(40); }), true, 'release_mismatch'],
  ['foreign handoff proof', mutate((e) => { e.evidence_binding.handoff_proof = 'c'.repeat(64); }), true, 'evidence_binding_mismatch'],
  ['501 pages', mutate((e) => {
    for (let i = 4; i < 501; i += 1) e.pages.push({ page_id: `p${String(i + 1).padStart(3, '0')}`, final_url: url(i), review_state: 'reviewed' });
  }), true, 'page_count_invalid'],
  ['page order swapped', mutate((e) => { e.pages.reverse(); }), true, 'page_index_invalid'],
  ['contradictory reviewed total', mutate((e) => { e.coverage.pages_reviewed = 3; }), true, 'denominator_mismatch'],
  ['inflated discovery', mutate((e) => { e.coverage.pages_found = 999; }), true, 'denominator_mismatch'],
  ['coverage overclaim', mutate((e) => { e.review.review_coverage_state = 'bounded_sample_reviewed'; }), true, 'review_coverage_invalid'],
  ['provisional hidden', mutate((e) => { e.review.review_confidence_state = 'incomplete_evidence'; }), true, 'review_confidence_invalid'],
  ['false fix: done', mutate((e) => { e.findings[0].user_status = 'done'; }), true, 'false_fix_claim'],
  ['false fix: verified_fixed', mutate((e) => { e.findings[1].repair_verification_state = 'verified_fixed'; }), true, 'false_fix_claim'],
  ['false fix: completed count', mutate((e) => { e.fix_list_summary.completed_count = 2; }), true, 'false_fix_claim'],
  ['finding without evidence', mutate((e) => { e.findings[0].affected_page_ids = []; e.findings[0].page_count = 0; }), true, 'finding_evidence_missing'],
  ['finding on unknown page', mutate((e) => { e.findings[1].affected_page_ids = ['p404']; }), true, 'finding_evidence_missing'],
  ['finding on unreviewed page', mutate((e) => {
    e.pages[1].review_state = 'not_reviewed';
    Object.assign(e.coverage, { pages_reviewed: 3, pages_not_reviewed: 1, review_coverage_basis_points: 7500 });
    Object.assign(e.review, { review_coverage_state: 'bounded_sample_reviewed', score_is_provisional: true });
  }), true, 'finding_evidence_not_reviewed'],
  ['float confidence', mutate((e) => { e.findings[0].confidence_score = 88.5; }), false, 'finding_field_invalid'],
  ['duplicate finding', mutate((e) => { e.findings[1].repair_fingerprint = 'fp_f1'; }), true, 'duplicate_finding'],
  ['priority inversion', mutate((e) => { e.findings.reverse(); }), true, 'priority_order_invalid'],
  ['aggregation mismatch', mutate((e) => { e.fix_list_summary.critical_count = 1; }), true, 'aggregation_mismatch'],
  ['tampered after signing', mutate((e) => { e.findings[0].issue_title = 'Changed'; }), false, 'hmac_invalid'],
  ['raw-secret seal', async (e) => {
    const { proof: _p, ...signed } = e;
    return { ...signed, proof: await createAuthoritySeal(signed, secret) };
  }, false, 'hmac_invalid'],
];

for (const [name, change, shouldResign, reason] of CASES) {
  test(`refuses: ${name}`, async () => {
    const { envelope, evidenceHandoff } = await fixture();
    let candidate = await change(structuredClone(envelope), evidenceHandoff);
    if (shouldResign) candidate = resign(candidate);
    assert.deepEqual(await verifyExtended500ReviewedAuthority(candidate, options(evidenceHandoff)), { valid: false, reason });
  });
}

test('context refusals: stale scan, foreign tenant, roots and release expectations', async () => {
  const { envelope, evidenceHandoff } = await fixture();
  const check = async (extra) => (await verifyExtended500ReviewedAuthority(envelope, options(evidenceHandoff, extra))).reason;
  assert.equal(await check({ frozenScan: { ...frozenScan, scan_mode: 'standard_150' } }), 'mode_invalid');
  assert.equal(await check({ frozenScan: { ...frozenScan, status: 'complete' } }), 'scan_state_invalid');
  assert.equal(await check({ frozenScan: { ...frozenScan, attempt_count: 2 } }), 'attempt_mismatch');
  assert.equal(await check({ frozenScan: { ...frozenScan, project_id: 'project-b' } }), 'identity_mismatch');
  assert.equal(await check({ expectedRelease: undefined }), 'release_expectation_missing');
  assert.equal(await check({ expectedRelease: { ...expectedRelease, beta_revision_fingerprint: '0'.repeat(16) } }), 'release_mismatch');
  assert.equal(await check({ secret: 'short' }), 'signing_root_invalid');
  assert.equal(await check({ handoffSecret: secret }), 'signing_root_not_distinct');
  assert.equal(await check({ handoffSecret: 'wrong-handoff-secret' }), 'evidence_handoff_invalid');
  assert.equal(await check({ secret: `${secret}-other` }), 'hmac_invalid');
  assert.equal((await verifyExtended500ReviewedAuthority(null)).reason, 'shape_invalid');
});

test('canonical serialization is strict and deterministic', () => {
  assert.equal(canonicalReviewedJson({ b: 1, a: [true, null, 'é\n 😀'] }), '{"a":[true,null,"é\\n 😀"],"b":1}');
  for (const bad of [1.5, 2 ** 53, { é: 1 }, '\ud800', new Date(0), undefined]) {
    assert.throws(() => canonicalReviewedJson(bad));
  }
});

test('the verifier is not imported by any customer, Base44 or worker source', () => {
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(full);
      else if (!full.endsWith('extended500ReviewedAuthority.js') && /\.(js|jsx|ts|mjs)$/.test(entry.name)
        && fs.readFileSync(full, 'utf8').includes('extended500ReviewedAuthority')) offenders.push(full);
    }
  };
  walk('src');
  walk('base44');
  assert.deepEqual(offenders, []);
});

test('a Python-produced reviewed envelope is accepted in JS and a tampered copy refused', async () => {
  const code = `
import json, copy
from app.extended500_evidence_handoff import build_extended500_evidence_handoff
from app.extended500_reviewed_authority import build_extended500_reviewed_authority
scan = {"scan_mode": "extended_500", "status": "reviewing", "owner_user_id": "owner-500", "id": "scan-500",
        "project_id": "project-500", "request_id": "req-500", "idempotency_key": "idem-500",
        "normalized_domain": "example.com", "attempt_count": 1}
pages = [{"url": f"https://example.com/p{i}", "final_url": f"https://example.com/p{i}", "status_code": 200,
          "main_text": "private"} for i in range(500)]
result = {"scan_mode": "extended_500", "canonical_mode": "extended_500", "scan_id": "scan-500",
          "request_id": "req-500", "idempotency_key": "idem-500", "normalized_domain": "example.com",
          "pages_found": 700, "pages_crawled": 500, "pages": pages, "crawled_pages": copy.deepcopy(pages),
          "scan_coverage": {"urls_attempted": 510, "usable_html_pages": 500, "unique_retained_destinations": 500},
          "scanner_source_sha": "a" * 40, "beta_revision_fingerprint": ${JSON.stringify(RELEASE_FINGERPRINT)}}
handoff = build_extended500_evidence_handoff(scan, result, ${JSON.stringify(handoffSecret)})
review = {"review_status": "reviewed", "review_version": ${JSON.stringify(expectedRelease.review_version)},
          "sampling_policy_version": "extended500_bounded_sample_v1",
          "reviewed_page_urls": [f"https://example.com/p{i}" for i in range(60)],
          "review_confidence_state": "complete", "health_score": 64,
          "findings": [{"fix_id": "f1", "rule": "missing_meta_description", "issue_title": "Add descriptions",
                        "priority": "high", "evidence_class": "confirmed_problem", "action_priority": "fix_first",
                        "action_priority_score": 4300, "page_scope": "family", "page_template_family": "article",
                        "affected_pages": ["https://example.com/p0", "https://example.com/p7"],
                        "evidence_status": "confirmed", "verification_state": "verified",
                        "confidence_score": 90, "repair_fingerprint": "fp1"}]}
envelope = build_extended500_reviewed_authority(scan_run=scan, evidence_handoff=handoff,
    handoff_signing_key=${JSON.stringify(handoffSecret)}, review=review,
    expected_release=${JSON.stringify(expectedRelease).replace(/true/g, 'True')},
    signing_root=${JSON.stringify(secret)})
print(json.dumps({"envelope": envelope, "handoff": handoff, "scan": scan}, ensure_ascii=False))
`;
  const child = spawnSync('python', ['-c', code], {
    encoding: 'utf8', env: { ...process.env, PYTHONPATH: 'scanner-api' }, maxBuffer: 64 * 1024 * 1024,
  });
  assert.equal(child.status, 0, child.stderr);
  const { envelope, handoff, scan } = JSON.parse(child.stdout);
  const opts = { frozenScan: scan, expectedRelease, secret, evidenceHandoff: handoff, handoffSecret };
  const verdict = await verifyExtended500ReviewedAuthority(envelope, opts);
  assert.equal(verdict.valid, true);
  assert.equal(verdict.pages_assessed, 500);
  assert.equal(verdict.pages_reviewed, 60);
  assert.equal(verdict.customer_publishable, false);
  assert.equal(envelope.review.score_is_provisional, true);
  assert.ok(!JSON.stringify(envelope).includes('main_text'));
  const tampered = structuredClone(envelope);
  tampered.review.health_score = 99;
  assert.deepEqual(await verifyExtended500ReviewedAuthority(tampered, opts), { valid: false, reason: 'hmac_invalid' });
});
