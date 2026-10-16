import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { auditOwnSiteSource } from "../../scripts/stage4OwnSiteSourceAudit.mjs";

test("FixList source carries a useful home title, description and exact canonical", () => {
  const result = auditOwnSiteSource();
  assert.equal(result.metadata.status, "pass", result.metadata.failures.join("; "));
  assert.match(result.metadata.title, /FixList/);
  assert.ok(result.metadata.description.length >= 70);
  assert.equal(result.metadata.canonical, "https://getfixlist.com/");
});

test("robots declares the canonical sitemap and sitemap contains only conservative public routes", () => {
  const result = auditOwnSiteSource();
  assert.equal(result.sitemap.status, "pass", result.sitemap.failures.join("; "));
  assert.equal(result.sitemap.declared_in_robots, true);
  assert.deepEqual(result.sitemap.locations, [
    "https://getfixlist.com/",
    "https://getfixlist.com/blog",
  ]);
  const sitemap = fs.readFileSync("public/sitemap.xml", "utf8");
  for (const route of ["login", "register", "forgot-password", "reset-password", "dashboard", "onboarding", "billing", "account"]) {
    assert.doesNotMatch(sitemap, new RegExp(`getfixlist\\.com/${route}(?:<|/)`));
  }
});

test("source audit refuses to manufacture a soft-404 pass without deployed HTTP evidence", () => {
  const result = auditOwnSiteSource();
  assert.equal(result.soft_404.status, "not_assessed");
  assert.match(result.soft_404.reason, /deployed exact-source runtime observation/);
  assert.equal(result.deployment_verified, false);
});
