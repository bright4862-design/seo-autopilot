import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);

const slimFixStart = source.indexOf("function slimFix(fix = {})");
const slimPageStart = source.indexOf("function slimPage(page = {})", slimFixStart);
const slimFixSource = source.slice(slimFixStart, slimPageStart);

test("slimFix preserves authoritative Python workflow fields", () => {
  assert.ok(slimFixStart >= 0 && slimPageStart > slimFixStart);
  assert.match(
    slimFixSource,
    /difficulty: fix\.difficulty \|\| \(requiresDeveloper \? "developer" : "easy"\)/,
  );
  assert.match(
    slimFixSource,
    /status: fix\.status \|\| \(requiresDeveloper \? "needs_developer"/,
  );
  assert.match(
    slimFixSource,
    /typeof fix\.requires_approval === "boolean" \? fix\.requires_approval : !requiresDeveloper/,
  );
  assert.match(
    slimFixSource,
    /hasAuthoritativeOwner \? normalizeOwner\(fix\.who_can_do_this\)/,
  );
  assert.doesNotMatch(
    slimFixSource,
    /developerOwned \? "needs_developer" : fix\.status/,
  );
  assert.doesNotMatch(
    slimFixSource,
    /developerOwned \? "your_web_person" : normalizeOwner/,
  );
});

test("slimFix only infers ownership for findings without the review contract", () => {
  assert.match(
    slimFixSource,
    /hasAuthoritativeDeveloperFlag[\s\S]*?\? fix\.requires_developer/,
  );
  assert.match(
    slimFixSource,
    /hasAuthoritativeOwner[\s\S]*?normalizeOwner\(fix\.who_can_do_this\) === "your_web_person"/,
  );
  assert.match(
    slimFixSource,
    /: inferredDeveloperOwned/,
  );
});
