import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("FixList only rewrites rate-limit presentation for legacy records", () => {
  assert.match(source, /const legacyBlocked429 = shouldUseLegacyRateLimitPresentation\(scanRecord, item\)/);
  assert.match(source, /title = legacyBlocked429 \? build429Title/);
  assert.match(source, /generalSteps: legacyBlocked429 \? build429Steps/);
  assert.doesNotMatch(source, /const blocked429 = isBlocked429\(item\)/);
});
