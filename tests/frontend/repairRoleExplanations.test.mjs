import assert from "node:assert/strict";
import crypto from "node:crypto";
import test from "node:test";

import {
  REPAIR_EXPLANATION_FALLBACK,
  REPAIR_EXPLANATION_ROLES,
  REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION,
  REPAIR_ROLE_EXPLANATION_VERSION,
  repairRoleExplanation,
  roleExplanationEntry,
} from "../../src/lib/repairRoleExplanations.js";

const SNAPSHOTS = Object.freeze({
  "sitemap_redirect|owner": "86ea6ad54dc40db7e4568adaa78061bb25e92f516d284764b9d71ae9e1ac6c25",
  "sitemap_redirect|marketing": "bae0c54db02b2e11429bac1b28a097e14ea883254a3198b5913c5ceafa862f81",
  "sitemap_redirect|seo": "d37466157211abed31cd064c77119b3204cc6f82224784f6ac8473610d298200",
  "sitemap_redirect|developer": "e9ddde52232cc31ff5ad7c3a53881bb9ee0f7a5b9140b630461b76e933fb45df",
  "image_alt_text|owner": "7e4d180a7fd3252a7d08d89298deb54c7b7135fb2bda8d3713badad8fa3bac54",
  "image_alt_text|marketing": "5f35983464ddd85d4fa766db707a6e4734616171a800ce129b69d646c672a0a0",
  "image_alt_text|seo": "bd050cbdc11b173c0dfe937827dcc9cd143a3d4d4f4ffd317e8117cd09669a4f",
  "image_alt_text|developer": "4cb46599595393aaf76d2f6a60bc58b9766abcab637dc25b7a7544f231cedd7b",
  "missing_h1|owner": "03320c1016dbc2fa146d7a59d7cda0d336253f573ff641ce4ecd3110613432dc",
  "missing_h1|marketing": "166a8dab92e38e645fa3d9395e26dc067fc2cdc6858b186234b7ad8b7228db95",
  "missing_h1|seo": "2870166a3c9a9bafb82b6e103fcdde8f01e88ce2b1e4727469ed4d07540d5809",
  "missing_h1|developer": "3d5acde2f105c07f693fb2fd060c7fbe76a64561a95a4c6e35dff0d67ea05286",
  "canonical_missing|owner": "28c1b80dcfcd937040555ea5446379a6cf197932149210005f35274b4d9d4d0c",
  "canonical_missing|marketing": "be09c96a7a994e137d3f4ca1b7357d1216cb8bbb58ff1b0ff9eea5837c80bf77",
  "canonical_missing|seo": "e46127181468de7714dd2161f9c5998be605fb8dee8edd5abc95301aef5ae8c6",
  "canonical_missing|developer": "8dd8acf4f2758e0e0b32f2c5dcf269746a9c36998d201e939b71de44debd0905",
  "potential_orphan_pages|owner": "cb529eb1826d61a92e706e1dadf9d6792a5631a56f60816fda98ba764cbc99d1",
  "potential_orphan_pages|marketing": "2b7e18ea8c17b8bdb04bb64df5a710b6a6ae07432397fe636f83865bbacffed1",
  "potential_orphan_pages|seo": "9b9600bb17dfa775b9d190af503568a2c2bbc74971848613cfdca68ae11b3159",
  "potential_orphan_pages|developer": "d94bab82277cf6c406a70654d73a16058336a16d1a24df9062d340e195edd1f0",
  "internal_link_redirect|owner": "8bc718cd99749975382f949327c42e4fb6eed4274bf59d26c3bf4ad9b3bc4a55",
  "internal_link_redirect|marketing": "31adaa3303b231485e32f98147569e8b2a4dde395f7e0ebbc101113cd63743dc",
  "internal_link_redirect|seo": "bd14a7ed9b8edb8640268f83bf76ae12f0e1b9e23f216729aa7b0968357a4662",
  "internal_link_redirect|developer": "0f3f3351b9159bc2ac94c983daf3cb8be0405e4e829788cc61ce1ae8e3a5e585",
  "failed_page|owner": "0c990a7818ecd06604d75eefa3663603e9ba7ba47235703cb20b07b6d153b930",
  "failed_page|marketing": "95321a0b290f9bfc338e059f044b40237d1a04b12ca88fecac4fcbdea8c38a4c",
  "failed_page|seo": "b53787580ee0f1f636d501a907512f92784bfe8fe98e819c09cf6c998fe2a334",
  "failed_page|developer": "0b6b1e248719d57d02aa52da56bf700b5a7d2689569d96506cc57213f6b3b5d0",
  "duplicate_title_template|owner": "4743fc6fbdbc89d9188b196effb0b488fa0a19127c616c821e2f8d33f8ea497a",
  "duplicate_title_template|marketing": "d2cc942fef094493f647066144fca36ea8aa39409224230d0eb446b788a0bb95",
  "duplicate_title_template|seo": "02262a3bd5e25dc712d6c904ae7b17a59160a65d1e5f73d4a08986a7ea9382d6",
  "duplicate_title_template|developer": "9cfda0f419abd683fede0d8bbc7a3252ba0d27bc3c9e6811c50c1b8e4a2318c7",
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

test("array-shaped rule or role identifiers fail closed instead of coercing into supported values", () => {
  const arrayRole = repairRoleExplanation({ rule: "missing_h1" }, ["owner"]);
  assert.equal(arrayRole.role, "");
  assert.equal(arrayRole.explanationAvailable, false);
  assert.equal(arrayRole.explanation, REPAIR_EXPLANATION_FALLBACK);

  const arrayRule = repairRoleExplanation({ rule: ["missing_h1"] }, "owner");
  assert.equal(arrayRule.rule, "");
  assert.equal(arrayRule.explanationAvailable, false);
  assert.equal(arrayRule.explanation, REPAIR_EXPLANATION_FALLBACK);
});

test("conflicting published rule aliases fail closed instead of selecting one explanation", () => {
  const actual = repairRoleExplanation({
    rule: "missing_h1",
    rule_id: "canonical_missing",
  }, "owner");

  assert.equal(actual.rule, "");
  assert.equal(actual.explanationAvailable, false);
  assert.equal(actual.explanation, REPAIR_EXPLANATION_FALLBACK);
  assert.equal(actual.explanationSource, "manual_review_fallback");
});

test("blank published rule aliases fail closed beside a valid alias", () => {
  const actual = repairRoleExplanation({
    rule: "missing_h1",
    rule_id: "   ",
  }, "seo");

  assert.equal(actual.rule, "");
  assert.equal(actual.explanationAvailable, false);
  assert.equal(actual.explanation, REPAIR_EXPLANATION_FALLBACK);
});

test("matching published rule aliases preserve the deterministic mapped explanation", () => {
  const actual = repairRoleExplanation({
    rule: "missing_h1",
    rule_id: "MISSING_H1",
    original: { rule: "missing_h1", rule_id: "missing_h1" },
  }, "developer");

  assert.equal(actual.rule, "missing_h1");
  assert.equal(actual.explanationAvailable, true);
  assert.equal(actual.explanationSource, "fixlist_role_library");
});

test("issue_type remains a deterministic fallback when no published rule alias exists", () => {
  const actual = repairRoleExplanation({ issue_type: "missing_h1" }, "marketing");
  assert.equal(actual.rule, "missing_h1");
  assert.equal(actual.explanationAvailable, true);
  assert.equal(actual.explanationSource, "fixlist_role_library");
});

test("direct role entry lookup rejects inherited object-property names", () => {
  assert.ok(roleExplanationEntry("missing_h1"));
  for (const inheritedName of ["constructor", "toString", "__proto__"]) {
    assert.equal(roleExplanationEntry(inheritedName), null);
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
