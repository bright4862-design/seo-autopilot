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
  "redirect_chain|owner": "2b2b76ee5b6ce11e56df1913a39bb9f3e7d1e229448d89fd0fc3bfe5f29f71cf",
  "redirect_chain|marketing": "1e971f6d9d579b16e05bcca5f0d84b5ca15ed497b73e62f6d11182d93db8bf32",
  "redirect_chain|seo": "b62d8c2b44d30d45271763b527e3a0bcbae6a199478b0b504e5c63e3cb09b64d",
  "redirect_chain|developer": "84d59ede128962bfd73aff2aa423e50e69a76720e5f105fff3fd96541c51bb7e",
  "meta_description_unusable|owner": "7f1e97e7161a8ca30c2ea64e44a9a60a740ccb301b87e5f33c1a02ea6b60541d",
  "meta_description_unusable|marketing": "c39f167c5119d06fa2e4b375d3ff1ad97b5867dae60a8dbd6bc8ad8e7cf30952",
  "meta_description_unusable|seo": "a8f690bdf4ccc33687733bdc6fbd94f70bea45a4b68c50868ed69fa1a115c9a8",
  "meta_description_unusable|developer": "8d597ffb6e8875872086773dac8188d31e7564a119231572149d334258d9e92c",
  "title_over_pixel_limit|owner": "e0fbb6ccedf3585e4e6e577cace8d14406d6f7f715cc17bbf10a681a7623d208",
  "title_over_pixel_limit|marketing": "b1e6b592c833d3a5f3f68dc08148edf9857ee5aa534284590d12598170efe18f",
  "title_over_pixel_limit|seo": "2e3eb2f74209fa4691280d6dd4986ad1ccd28eb7a42123ef135c0a9bc0e16748",
  "title_over_pixel_limit|developer": "5a1a3432e426e8d8388e0de2ba58a54e8ea727c61dd0d8f48b5d9993cebb45fa",
  "sitemap_redirect|owner": "1ba2c282ba36d296c62efea6366bc2371a1621e74bbc37a4d1b31b0b64b7a866",
  "sitemap_redirect|marketing": "935c310f6fccde43f9435dbb57b30ce85e18a45be8f9cb9afdb3f9a1c7764dae",
  "sitemap_redirect|seo": "4e1722e43818081a9275e4b59e0b18b386a1e4701dd248e5854ad29298df1311",
  "sitemap_redirect|developer": "32bffb4a21be3c640fbeeea7b838b4857566d4aacfbccad9756c24853342d3d5",
  "image_alt_text|owner": "30101408c24be931debfe02720882ba8d401509c4d69e1d0d3cc87d125217cf8",
  "image_alt_text|marketing": "66aaa393654f35bfbe4e5fbd72c4933170150315569841dc23d3d54152a4932d",
  "image_alt_text|seo": "cb6c5efe2493975068930fa852142e5a1aa8afbef6dadae2f9b08235152c989c",
  "image_alt_text|developer": "ad2b30d17ed55aa53475d98f0e6937fe544f34d75f7f1cd89cce118415a09948",
  "missing_h1|owner": "b9a98f02bd88e90a0409bd974e406a4cd15fb6e6cb226e1ce410bc07088ad6c7",
  "missing_h1|marketing": "d091005013ad2b1ecc1cd070ce26787874cd50b0c8cab5c1bb5b310270942e47",
  "missing_h1|seo": "67bc86e56aa9d3106ba048e29c55d39fd1df2f368d73829c63f51cc6e0ddce85",
  "missing_h1|developer": "243937193140b685fdecd1342e449d2634f291602d69f2fc5e28d9bd1b8b04af",
  "canonical_missing|owner": "cef5b55a807b4e607db4f508cdf159750d98f7a4f6cb7e1d79e5f1880cfa48cc",
  "canonical_missing|marketing": "73d8933eeab480970eccac367c5abb3b6a34e319c1b49f81413346d171377aad",
  "canonical_missing|seo": "4f1b7ee7be6f9bc2bd20d778e03da10d8cd41bd88c822bf765258e9943171421",
  "canonical_missing|developer": "9592639ee1a10357fc32f906165b7fa7476e396f0b621a3598e6adec0992bb17",
  "potential_orphan_pages|owner": "17955b0d367171f27a467afc87daaa1d70d6a3621279d1d2f0cff8c5a1b798c8",
  "potential_orphan_pages|marketing": "8c43f7f9d493ec5cddac3c05c763085f193e9ebda80820d39d13165015ab993c",
  "potential_orphan_pages|seo": "285260ce9f2d0b61883fbea4f13b80524620792cf75a99bf74437df846589bc6",
  "potential_orphan_pages|developer": "765be6eb54ac63ccf83a8260c0fc600fe47b3887df221820e886284c9f1796d5",
  "internal_link_redirect|owner": "13160b0dc364d9e992dda57135566ec8da81d64e419d67021819897d1b8a31ff",
  "internal_link_redirect|marketing": "2b81f92479acea823d10c90fb800b18659bdcc97d34fc0cc9fd387caebd246a0",
  "internal_link_redirect|seo": "0d296aa744b26e6237daeb3a32ebc232970b38abec22b9f156dda38728b1cde0",
  "internal_link_redirect|developer": "c6f166ee799cb5b842743fd4eb216b059edbf4acada567aef17f417becd55569",
  "failed_page|owner": "9ab24b7fa94bd0d55ff3af4f9a2ccba071130a940026b7a2e02627acf980aa2a",
  "failed_page|marketing": "99d19b875eddb20958fe85a6d5e7af34a739e238adcd37a148f44141258c88c1",
  "failed_page|seo": "a7ad3ecb48674f13baae3857df8e86f36c32ea3fa04e526a2b0492cf6a74b461",
  "failed_page|developer": "4e6832c4ad02ad5108632a4316971350ab623123dccb9bce119aa1ab00780b08",
  "duplicate_title_template|owner": "879737820aa69392e20df66623f1ad531533e1f4742aa765cecc8a2559f7a468",
  "duplicate_title_template|marketing": "84de8e4e4c2e218892434572adf93991a566f5fc8d9ce26ecb00a7ddb9460b4e",
  "duplicate_title_template|seo": "c4c809218b2dc4382fe395f4356255afbe7afa9d868e689ee03d14a30c52a5bf",
  "duplicate_title_template|developer": "b3759806cffdcc16160bb110d43a248b7ea3c13789dc68ca9ac55573353bba5c",
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
