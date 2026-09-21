import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  CURRENT_IDENTITY_AUTHORITY_VERSION,
  HISTORICAL_AUTHORITY_VERSIONS,
} from "../../scripts/stage4EvidenceCompatibility.mjs";

function acceptedVersions(source) {
  const block = source.match(/const ACCEPTED_AUTHORITY_VERSIONS = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(block, "reader no longer exposes an explicit accepted authority version set");
  return new Set([...block[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]));
}

for (const target of [
  "base44/functions/getCustomerScanResultV7/entry.ts",
  "base44/functions/grokChat/index.ts",
]) {
  test(`${target} retains every historical seal plus the current identity seal`, () => {
    const accepted = acceptedVersions(fs.readFileSync(target, "utf8"));
    for (const version of HISTORICAL_AUTHORITY_VERSIONS) {
      assert.ok(accepted.has(version), `${target} lost historical authority ${version}`);
    }
    assert.ok(accepted.has(CURRENT_IDENTITY_AUTHORITY_VERSION), `${target} lost current identity authority`);
    assert.equal(accepted.has("standard_review_snapshot_hmac_future_unknown"), false);
  });
}

test("customer V7 reader fail-closes before reconstructing an unaccepted seal", () => {
  const source = fs.readFileSync("base44/functions/getCustomerScanResultV7/entry.ts", "utf8");
  assert.match(source, /!ACCEPTED_AUTHORITY_VERSIONS\.has\(cleanText\(run\.authority_seal_version, 160\)\)/);
});

test("Grok reader fail-closes before reconstructing an unaccepted seal", () => {
  const source = fs.readFileSync("base44/functions/grokChat/index.ts", "utf8");
  assert.match(source, /!ACCEPTED_AUTHORITY_VERSIONS\.has\(cleanText\(scan\.authority_seal_version, MAX_ID_LENGTH\)\)/);
});
