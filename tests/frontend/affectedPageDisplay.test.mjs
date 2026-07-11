import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../src/pages/FixList.jsx", import.meta.url),
  "utf8",
);

const start = source.indexOf("function AffectedPage({ page })");
const end = source.indexOf("function ScanDebugPanel", start);
const affectedPageSource = source.slice(start, end);

test("relative affected URLs are not printed twice", () => {
  assert.ok(start >= 0 && end > start);
  assert.match(affectedPageSource, /const label = formatPageLabel\(page\)/);
  assert.match(affectedPageSource, /const path = formatPagePath\(page\)/);
  assert.match(
    affectedPageSource,
    /const showPath = cleanString\(path\) !== cleanString\(label\)/,
  );
  assert.match(
    affectedPageSource,
    /\{showPath \? <p[^>]*>\{path\}<\/p> : null\}/,
  );
  assert.doesNotMatch(
    affectedPageSource,
    /<p[^>]*>\{formatPagePath\(page\)\}<\/p>/,
  );
});
