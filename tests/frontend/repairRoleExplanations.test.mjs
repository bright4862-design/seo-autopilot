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
  "sitemap_redirect|owner": "45be43e85326a612c673a1545e400dd9c49abec03d44a0510ed0173ad7897754",
  "sitemap_redirect|marketing": "c0d09534f47e8ae5eba29aef34e709912aa37a6a17dda1d762aa482cbccfdc4e",
  "sitemap_redirect|seo": "268f094a8f8c682ccc5f5bcb35096bd23cf0d06d74c58111e0b2cb6a03c4a5ae",
  "sitemap_redirect|developer": "27c0d7e7a530d0ba3e2226ec1acde85d7717cb74bb278c5405ea8ba9bb5d8c00",
  "image_alt_text|owner": "357b34e67ba84a1446d4d76d1a267bca5d8caaee0c0720076ae351deb58f3352",
  "image_alt_text|marketing": "36764973f2c9ffc50fd0d447f9d9b15079797ee1bd2e6144ee9cf21af416ecca",
  "image_alt_text|seo": "d2ff5548451d1e1fefb27492d90ac059b3e59f8eada9c8d6bc9b927d765ef546",
  "image_alt_text|developer": "dd8a061358a801f4a77b72c27ca019c48165c25683b41500c46c6805e96a5b98",
  "missing_h1|owner": "7da193114bee46603ae2b91af46d2181d02349f692934560719b40304e7b52c9",
  "missing_h1|marketing": "663d26a720429d981996eb14f49074ff9870180f085d33f6e660743628d96f6d",
  "missing_h1|seo": "ed405c954552bab7fc1536b0f4244e1883805611518b06c3cd32b7420f9dc064",
  "missing_h1|developer": "278822aa4a220fdf2147cb49246f740fb9bc5e3b379afbbbd02b15fedfae3d7e",
  "canonical_missing|owner": "ea303577e9e70d94910c15604c64a69a96ea91446d1ea7937ad885408a69fa5f",
  "canonical_missing|marketing": "65e3adfcf17fe9421179a060e5651795e87403d7fc1501d9745cc809faf7e748",
  "canonical_missing|seo": "817d59de1e91a6496b2def2121bb0a6c899bd19f4ec85948e8b787f8cd13b134",
  "canonical_missing|developer": "11e7cb6fa534a573632ae8c07f40a8d232da18ec61442b8ee068a6ce0459eaa9",
  "potential_orphan_pages|owner": "8fda42f5481f097c98e67d2ae06549c6d7cba87da0d0eee186af99db4f8513aa",
  "potential_orphan_pages|marketing": "e88e34a243bb42056b97191547cb909e9794a7bbc5c3e92a06bb7fc4529fdcf7",
  "potential_orphan_pages|seo": "6f848cac66c4395120008f57da7ca898e2cd27e1d97684888c983360d46c0d4f",
  "potential_orphan_pages|developer": "d15f11ffdaa15991da16bfbd62b4411124ffdbd53d28f6477fbf481d07947969",
  "internal_link_redirect|owner": "c2b73561bdc3941a41731de2a9b347d3ace0a2263a2e6a9fb61159c5d0ff2add",
  "internal_link_redirect|marketing": "b6b2eb63bf1414f3d19e7b75af32d5b1e4d51f76dc64b34857077dbc21d89048",
  "internal_link_redirect|seo": "7746c6bf01931a5931d22fdb8a7e430cfe01cdad467e5dd468a747f1f3ece1aa",
  "internal_link_redirect|developer": "b90b8cabf75b890439d5d1f6f735b22cfba185a3d9f5ecab71f7ca03945608f7",
  "failed_page|owner": "5b833ff9e66b260218607c4c91ab6da2232263e5bcbd242bd15063d718590061",
  "failed_page|marketing": "39381ae1625b343e757db241986c09d3dddf42558889d0ecd609580f8892f280",
  "failed_page|seo": "c2bdd1e5ebbfc24e329424d1a267ff860e0b606f5461b3a4dc83c291cfad8af6",
  "failed_page|developer": "d08422e34f04123f2155b3d8eeb918cbcc3abaf5cc9a8bfc584d7182de3dc7aa",
  "duplicate_title_template|owner": "a0273072e8a8b992c0f4ea94490ebb0f3cf092d35bd5ef7dce68aea702de377d",
  "duplicate_title_template|marketing": "21617601bb89d51c70ba1e0eae2b54c42287948ee0024788d2957f63f577e9bc",
  "duplicate_title_template|seo": "c9790e7770d28810a4fcef3716f58bdcf4581fd95a5d7c4f9a179aff5be20b11",
  "duplicate_title_template|developer": "d5fba84b1c554f532c38e61893a21eacc2a19d07cfdc6f29cc9736ee43105d18",
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

test("missing_h1 gives each role one distinct next action without inventing a second headline", () => {
  assert.equal(
    REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION,
    "role_explanation_copy_v2_20260923_top8_missing_h1_actions",
  );

  const expected = {
    owner: "FixList did not find an H1. Ask the page owner to confirm whether the visible headline is already the main heading; do not add a second headline until they check.",
    marketing: "FixList did not find an H1. Confirm that the visible headline clearly states the page’s purpose. If the wording is right, keep it and ask for H1 markup; otherwise write one clear main headline.",
    seo: "No H1 was found in the collected evidence. Check the rendered page for a descriptive main heading that matches its topic, then confirm it is marked as an H1 before recommending new copy.",
    developer: "No H1 was found in the collected evidence. Inspect the rendered DOM and the page or template source. If the approved headline already exists, mark it up as an H1; otherwise add it once and verify the final HTML.",
  };

  for (const role of REPAIR_EXPLANATION_ROLES) {
    const actual = repairRoleExplanation({
      rule: "missing_h1",
      recommendation: "Preserve this scanner-authored recommendation.",
      evidence: { evidence_ref: "page:/example#heading" },
      action_priority: "important",
    }, role);
    assert.equal(actual.explanation, expected[role]);
    assert.equal(actual.rule, "missing_h1");
    assert.equal(actual.role, role);
  }

  assert.equal(new Set(Object.values(expected)).size, REPAIR_EXPLANATION_ROLES.length);
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
