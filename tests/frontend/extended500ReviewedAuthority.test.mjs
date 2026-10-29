import test from "node:test";
import assert from "node:assert/strict";
import { createAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { verifyExtended500ReviewedAuthority } from "../../src/lib/extended500ReviewedAuthority.js";

const reviewerSigningKey = "r".repeat(40);
const authoritySigningKey = "a".repeat(40);
const expectedSourceSha = "b".repeat(40);
const expectedFingerprint = "c".repeat(16);
const opts = { reviewerSigningKey, authoritySigningKey, expectedSourceSha, expectedFingerprint };

async function fixture(n = 2) {
  const frozen = {
    id: "scan_one", owner_user_id: "owner_one", project_id: "project_one",
    request_id: "request_one", idempotency_key: "idem_one",
    normalized_domain: "example.com", website_url: "https://example.com/",
    scan_mode: "extended_500", attempt_count: 1,
  };
  const identity = {
    canonical_mode: "extended_500", owner_user_id: frozen.owner_user_id,
    scan_id: frozen.id, project_id: frozen.project_id, request_id: frozen.request_id,
    idempotency_key: frozen.idempotency_key, normalized_domain: frozen.normalized_domain,
    attempt_count: "1",
  };
  const pages = Array.from({length:n}, (_, i) => ({
    url: `https://example.com/item-${i}`, final_url: `https://example.com/item-${i}`,
    title: "Synthetic", status_code: 200,
  }));
  const scan = {
    canonical_mode: "extended_500", scan_id: frozen.id,
    request_id: frozen.request_id, idempotency_key: frozen.idempotency_key,
    normalized_domain: frozen.normalized_domain, pages_found: n+10,
    pages_crawled: n, scan_coverage: {
      urls_attempted:n, usable_html_pages:n, unique_retained_destinations:n,
    }, scanner_source_sha:expectedSourceSha,
    beta_revision_fingerprint:expectedFingerprint, pages,
  };
  const review = {
    version:"extended500_reviewer_attestation_v1", review_status:"reviewed",
    identity: { ...identity }, scanner_source_sha:expectedSourceSha,
    beta_revision_fingerprint:expectedFingerprint, pages_reviewed:n,
    reviewed_destinations: pages.map(p=>p.final_url),
    findings: [{rule_id:"missing_h1",page_url:pages[0].final_url,
      severity:"medium",evidence_state:"observed"}],
  };
  const reviewer_proof = await createAuthoritySeal(review, reviewerSigningKey);
  const body = {
    version:"extended500_reviewed_authority_v1_unreleased",
    identity, scan, review, reviewer_proof, release_gate_eligible:false,
  };
  return {
    frozen,
    envelope: {...body, proof: await createAuthoritySeal(body, authoritySigningKey)},
  };
}

test("dual signed reviewer + authority is valid yet cannot authorize customer publication", async () => {
  for(const n of [1,150,500]){
    const {frozen,envelope} = await fixture(n);
    assert.deepEqual(await verifyExtended500ReviewedAuthority(envelope,frozen,opts),
      {valid:true,state:"reviewed_but_unreleased",pages_reviewed:n});
    assert.equal(envelope.release_gate_eligible,false);
  }
});

test("changed owner, domain, attempt and plan mode fail even when the signature is unchanged", async () => {
  const {frozen,envelope}=await fixture(2);
  for(const changed of [
    {...frozen,owner_user_id:"attacker"},
    {...frozen,project_id:"other"},
    {...frozen,request_id:"other"},
    {...frozen,attempt_count:2},
    {...frozen,scan_mode:"standard_150"},
    {...frozen,website_url:"https://attacker.com/"},
  ]){
    assert.equal((await verifyExtended500ReviewedAuthority(envelope,changed,opts)).valid,false);
  }
});

test("untrusted review body, non-reviewed state, destination claims and 501-page forgery fail", async () => {
  const {frozen,envelope}=await fixture(2);
  const cases = [
    {...envelope,release_gate_eligible:true},
    {...envelope,version:"extended500_evidence_handoff_v1_unreviewed"},
    {...envelope,review:{...envelope.review,review_status:"not_reviewed"}},
    {...envelope,review:{...envelope.review,pages_reviewed:1}},
    {...envelope,review:{...envelope.review,reviewed_destinations:["https://example.com/not-crawled"]}},
    {...envelope,scan:{...envelope.scan,pages_crawled:501}},
    {...envelope,scan:{...envelope.scan,pages_crawled:true}},
    {...envelope,scan:{...envelope.scan,pages_found:0}},
    {...envelope,scan:{...envelope.scan,scanner_source_sha:"f".repeat(40)}},
    {...envelope,scan:{...envelope.scan,scan_coverage:{...envelope.scan.scan_coverage,unique_retained_destinations:1}}},
    {...envelope,scan:{...envelope.scan,pages:[{...envelope.scan.pages[0],main_text:"secret"},envelope.scan.pages[1]]}},
    {...envelope,scan:{...envelope.scan,pages:[{...envelope.scan.pages[0],final_url:"https://attacker.com/a"},envelope.scan.pages[1]]}},
    {...envelope,reviewer_proof:"0".repeat(64)},
    {...envelope,proof:"0".repeat(64)},
  ];
  for(const tamper of cases) {
    assert.equal((await verifyExtended500ReviewedAuthority(tamper,frozen,opts)).valid,false);
  }
});

test("external claims to reviewed state cannot substitute for a separately signed reviewer", async () => {
  const {frozen,envelope}=await fixture();
  const other = {...opts, reviewerSigningKey:"wrong".repeat(10)};
  const result = await verifyExtended500ReviewedAuthority(envelope,frozen,other);
  assert.equal(result.valid,false);
  assert.equal(result.reason,"reviewer_hmac_invalid");
  const sameRoots={...opts, reviewerSigningKey:authoritySigningKey};
  assert.equal((await verifyExtended500ReviewedAuthority(envelope,frozen,sameRoots)).valid,false);
  assert.equal((await verifyExtended500ReviewedAuthority(envelope,frozen,{
    ...opts,expectedFingerprint:"d".repeat(16),
  })).reason,"release_identity_mismatch");
});
