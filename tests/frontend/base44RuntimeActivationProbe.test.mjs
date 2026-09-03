import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync("base44/functions/fixlistRuntimeActivationProbe/entry.ts", "utf8");

test("fresh Base44 route activation probe is bound to exact main source", () => {
  assert.match(source, /fixlist-new-route-activation-probe-20260903-v1/);
  assert.match(source, /5a91dfee0a86a6c67a5ef56d56e46a1b240647e7/);
  assert.match(source, /probe_id:\s*PROBE_ID/);
  assert.match(source, /source_sha:\s*SOURCE_SHA/);
});
