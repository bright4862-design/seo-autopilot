import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const ENTRY = "base44/functions/persistDurableScanAuthority/entry.ts";
const INDEX = "base44/functions/persistDurableScanAuthority/index.ts";
const CONTRACT = "base44/functions/persistDurableScanAuthority/generatedReleaseContract.js";

function fingerprintFrom(source) {
  const match = source.match(/RELEASE_FINGERPRINT\s*=\s*"([0-9a-f]{16})"/);
  assert.ok(match, "release fingerprint literal must exist");
  return match[1];
}

test("persistence handler executes directly from Base44 entry.ts", () => {
  const entry = fs.readFileSync(ENTRY, "utf8");
  assert.match(entry, /Deno\.serve\(/, "entry.ts must contain the actual handler");
  assert.doesNotMatch(entry, /import\s+["']\.\/index\.ts["']/, "entry.ts must not delegate to the stale imported handler path");
  assert.equal(fs.existsSync(INDEX), false, "imported index.ts handler must not remain in the package");
});

test("entry module identity moves whenever the release fingerprint moves", () => {
  const entry = fs.readFileSync(ENTRY, "utf8");
  const contract = fs.readFileSync(CONTRACT, "utf8");
  const expected = fingerprintFrom(contract);
  const marker = entry.match(/BASE44_HANDLER_RELEASE_FINGERPRINT\s*=\s*"([0-9a-f]{16})"/);
  assert.ok(marker, "entry.ts must carry a release-sensitive fingerprint marker");
  assert.equal(marker[1], expected, "entry.ts release marker must match generated release contract");
  assert.match(entry, /authority_release_activation_mismatch/);
});
