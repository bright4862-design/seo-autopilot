import assert from "node:assert/strict";
import crypto from "node:crypto";
import test from "node:test";

import {
  REPAIR_EXPLANATION_FALLBACK,
  REPAIR_EXPLANATION_ROLES,
  REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION,
  REPAIR_ROLE_EXPLANATION_VERSION,
  repairRoleExplanation,
} from "../../src/lib/repairRoleExplanations.js";

const SNAPSHOTS = Object.freeze({
  "sitemap_redirect|owner": "0e6fcf6ce6a897dda921969350dfd5b9b34bcd67d6bb27bc49343cd36b3e5ea4",
  "sitemap_redirect|marketing": "321475ef4ca6c3a8dd16da9c890ae820829c8454e6a92bc109031ca197ee7f2f",
  "sitemap_redirect|seo": "b868a717562b35dd8a64d623dfa86af491edb0d58481875b9b7576152a7d95a7",
  "sitemap_redirect|developer": "ae6b1b8aef6f8e485b2af9f58d4b1e00f5b4b573ddc99ab4aca4503c4d02dc1b",
  "image_alt_text|owner": "52e1aef09190adee23129c5357fe7fd06c2328b76b19297ee55a8aa989f59aa4",
  "image_alt_text|marketing": "d4138236e59566afcf80830385f1a3947cbf87a579a6b3f2b5fce18ade622368",
  "image_alt_text|seo": "171c9a266b59ec155c6bb3e6721ed58bc2f23a74edf7003948681f8b817ed8d6",
  "image_alt_text|developer": "65ed12c121e18aaccd51efddeda6652687dd3acdd29cf6836687ec98c10697b2",
  "missing_h1|owner": "605de815f2f7cc7df50c49862611fd4c5e816936d3f3b2f209569e791c75cbc9",
  "missing_h1|marketing": "a242151c64957fac36e6896aa994ddb71f9095145efcf49092f5c757b32797b4",
  "missing_h1|seo": "fc0dabf891cff26502e7c5eb232fa9fa4cb9042a502fc5f3cfd6d76aa97aa43a",
  "missing_h1|developer": "9154ea05a88bb4219570b4f1ef2087f631537c23c7f5f00c36f9640098466d1e",
  "canonical_missing|owner": "052a3635f657bc20ff99590c6ea47cf2d1d72939a7b89c74f561145b030b849b",
  "canonical_missing|marketing": "4f954dc9f81cfb7dbd92d9d4a893d5c6f96f9f9a98c97c8bd3f0558cc89bfb81",
  "canonical_missing|seo": "99600430e15d4b66f22ebdd076b9f1e399011fce33418446c714ab2a17682dc5",
  "canonical_missing|developer": "07b76d0bc54063b9f953c1098608a5df4fbe0690df587e8c1e4f149e3ca981a9",
  "potential_orphan_pages|owner": "81ef092a71db4c1e34c293e91be9f1750ace101cb2c7e4b58f430f569dd7a536",
  "potential_orphan_pages|marketing": "6f22659c3181d3c202036f99aeb97598db39198e737e67f5781553c3482a3c80",
  "potential_orphan_pages|seo": "46926781d7b767b607d441ab207e1f269837cb6734e24ab45dccf268ca33c06b",
  "potential_orphan_pages|developer": "73b77463ff1e28f74829bd0a4ce0b2eff4e77a08fb3542ee4b88595a7358b89f",
  "internal_link_redirect|owner": "c62f8844f0bec540048ce7aa77ba78fc3230a800dedb77ee9598ad20612be121",
  "internal_link_redirect|marketing": "66ffa2c820586d4b897e0c498f585236651e56945cce8befa7bf4002ce47a7f8",
  "internal_link_redirect|seo": "1a3e31d0005cafef031643462e425ff884ba2edb00ca99ef57037eb469f6e5c7",
  "internal_link_redirect|developer": "d0276e6a4dd7fc385257837cd1d2353ecf36c213de60b00390d0c4df55609406",
  "failed_page|owner": "1831673d72fe7bad9633cd3560530921431bd150e33282df0452ea933d350773",
  "failed_page|marketing": "fded13651dea48dd3561e8a4449400ee06fcb9791cf6bdf15c239b3724673265",
  "failed_page|seo": "6c25f4335add12f25e8161353036d5085c88886635e11cb905ea2b824b500130",
  "failed_page|developer": "08c6c8950b3f84baa011d27b0e788e75fdcb2be89b62706dbcf0489aaadf7bf3",
  "duplicate_title_template|owner": "850de8d97bd04c33130af5d4704a7733237e0b4038c339ae8ef74413d3dd0475",
  "duplicate_title_template|marketing": "f9653ae61f1d30a99cf28a8a650e122cc95a7ab2f335643d3104868c30223e38",
  "duplicate_title_template|seo": "82fd549b3af0caf078fcfb309578758c2f087e61415bb84890ac96528fd8bc0d",
  "duplicate_title_template|developer": "5dfeee2f84a9758dbfc22254303f39504f70815c194a0ed327de3a04002d3dda",
});

for (const [key, expectedDigest] of Object.entries(SNAPSHOTS)) {
  const [rule, role] = key.split("|");
  test(`role explanation snapshot ${rule} x ${role}`, () => {
    const actual = repairRoleExplanation({ rule }, role);
    const digest = crypto.createHash("sha256").update(JSON.stringify(actual)).digest("hex");
    assert.equal(digest, expectedDigest);
    assert.equal(actual.version, REPAIR_ROLE_EXPLANATION_VERSION);
    assert.equal(actual.libraryVersion, REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION);
    assert.equal(actual.explanationAvailable, true);
    assert.equal(actual.explanationSource, "fixlist_role_library");
  });
}

test("role inventory is the four viewer roles only", () => {
  assert.deepEqual(REPAIR_EXPLANATION_ROLES, ["owner", "marketing", "seo", "developer"]);
});

test("unmapped rule preserves the existing generic fallback wording", () => {
  const actual = repairRoleExplanation({ rule: "future_unmapped_rule" }, "seo");
  assert.equal(actual.explanationAvailable, false);
  assert.equal(actual.explanation, REPAIR_EXPLANATION_FALLBACK);
  assert.equal(actual.fallback, REPAIR_EXPLANATION_FALLBACK);
  assert.equal(actual.explanationSource, "manual_review_fallback");
});

test("missing or unsupported role fails closed instead of guessing an audience", () => {
  for (const role of ["", "product", null]) {
    const actual = repairRoleExplanation({ rule: "missing_h1" }, role);
    assert.equal(actual.explanationAvailable, false);
    assert.equal(actual.role, "");
    assert.equal(actual.explanation, REPAIR_EXPLANATION_FALLBACK);
  }
});

test("role explanation lookup does not mutate scanner remediation or authority fields", () => {
  const repair = {
    id: "fix-1",
    fix_id: "fix-1",
    rule: "canonical_missing",
    action_priority: "fix_first",
    evidence_class: "confirmed_problem",
    page_count: 4,
    authority_sealed: true,
    recommendation: "Scanner-authored remediation stays authoritative.",
  };
  const before = structuredClone(repair);
  const actual = repairRoleExplanation(repair, "developer");
  assert.equal(actual.explanationAvailable, true);
  assert.deepEqual(repair, before);
  assert.equal(repair.recommendation, "Scanner-authored remediation stays authoritative.");
  assert.equal(repair.id, "fix-1");
  assert.equal(repair.action_priority, "fix_first");
  assert.equal(repair.evidence_class, "confirmed_problem");
  assert.equal(repair.page_count, 4);
  assert.equal(repair.authority_sealed, true);
});

test("identical explanation inputs are byte-stable", () => {
  const input = { rule_id: "sitemap_redirect", recommendation: "Do not replace me" };
  assert.equal(
    JSON.stringify(repairRoleExplanation(input, "owner")),
    JSON.stringify(repairRoleExplanation(input, "owner")),
  );
});
