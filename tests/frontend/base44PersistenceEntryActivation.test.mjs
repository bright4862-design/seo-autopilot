import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const CONTRACT = "base44/functions/persistDurableScanAuthority/generatedReleaseContract.js";
const ENTRY_MODULES = [
  ["persistDurableScanAuthority", /Deno\.serve\(/],
  ["persistLimitedScanResult", /Deno\.serve\(/],
  ["startStandardScanJob", /export default async function/],
  ["durableScanWorkerControl", /Deno\.serve\(/],
  ["getCustomerScanResult", /Deno\.serve\(/],
  ["persistDurableScanAuthorityV2", /Deno\.serve\(/],
  ["persistLimitedScanResultV2", /Deno\.serve\(/],
  ["startStandardScanJobV2", /export default async function/],
  ["durableScanWorkerControlV2", /Deno\.serve\(/],
  ["getCustomerScanResultV2", /Deno\.serve\(/],
  ["ownerScanDebugControl", /Deno\.serve\(/],
  ["aiReviewScan", /Deno\.serve\(/],
];

// Base44 routes entry.ts only, so a function without one is not deployed at
// all. These two are legacy paths kept in the tree; naming them here is what
// keeps "no entry identity" a deliberate state rather than an oversight, and
// what makes adding an entry.ts to either one fail this test until it is also
// given a maintained release identity.
const UNROUTED_LEGACY = new Set(["persistScanAuthority", "grokChat"]);

function source(relative, root = ROOT) {
  return fs.readFileSync(path.join(root, relative), "utf8");
}

function fingerprintFromContract(value) {
  const match = value.match(/RELEASE_FINGERPRINT\s*=\s*"([0-9a-f]{16})"/);
  assert.ok(match, "release fingerprint literal must exist");
  return match[1];
}

function fingerprintFromEntry(value) {
  const match = value.match(/BASE44_HANDLER_RELEASE_FINGERPRINT\s*=\s*"([0-9a-f]{16})"/);
  assert.ok(match, "entry release fingerprint marker must exist");
  return match[1];
}

test("all release-sensitive Base44 functions execute from entry.ts", () => {
  for (const [name, handlerPattern] of ENTRY_MODULES) {
    const entryPath = `base44/functions/${name}/entry.ts`;
    const indexPath = `base44/functions/${name}/index.ts`;
    const entry = source(entryPath);

    assert.match(entry, handlerPattern, `${name} entry.ts must contain the actual handler`);
    assert.doesNotMatch(
      entry,
      /import\s+["']\.\/index\.ts["']/,
      `${name} entry.ts must not delegate to an imported handler`,
    );
    assert.equal(fs.existsSync(path.join(ROOT, indexPath)), false, `${name} imported index.ts must not remain`);
  }
});

test("all release-sensitive entry identities match the generated release contract", () => {
  const expected = fingerprintFromContract(source(CONTRACT));
  for (const [name] of ENTRY_MODULES) {
    const entry = source(`base44/functions/${name}/entry.ts`);
    assert.equal(fingerprintFromEntry(entry), expected, `${name} entry identity must match release fingerprint`);
  }
});

test("the canonical generator changes deployed entry identities when the fingerprint changes", (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-release-entry-"));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

  for (const relative of [
    "data/beta-crawler-revision.json",
    "data/cross-runtime-release-components.json",
  ]) {
    const target = path.join(tempRoot, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(ROOT, relative), target);
  }

  for (const [name] of ENTRY_MODULES) {
    const relative = `base44/functions/${name}/entry.ts`;
    const target = path.join(tempRoot, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(ROOT, relative), target);
  }

  const revisionPath = path.join(tempRoot, "data/beta-crawler-revision.json");
  const revision = JSON.parse(fs.readFileSync(revisionPath, "utf8"));
  const changedFingerprint = revision.fingerprint === "aaaaaaaaaaaaaaaa"
    ? "bbbbbbbbbbbbbbbb"
    : "aaaaaaaaaaaaaaaa";
  revision.fingerprint = changedFingerprint;
  fs.writeFileSync(revisionPath, JSON.stringify(revision, null, 2) + "\n");

  execFileSync(process.execPath, [path.join(ROOT, "scripts/generate_release_contracts.mjs")], {
    cwd: ROOT,
    env: { ...process.env, RELEASE_CONTRACT_ROOT: tempRoot },
    stdio: "pipe",
  });

  for (const [name] of ENTRY_MODULES) {
    const entry = source(`base44/functions/${name}/entry.ts`, tempRoot);
    assert.equal(fingerprintFromEntry(entry), changedFingerprint, `${name} entry identity did not move`);
  }
  assert.equal(
    fingerprintFromContract(source(CONTRACT, tempRoot)),
    changedFingerprint,
    "generated release contract did not move with the entry identities",
  );

  execFileSync(
    process.execPath,
    [path.join(ROOT, "scripts/generate_release_contracts.mjs"), "--check"],
    { cwd: ROOT, env: { ...process.env, RELEASE_CONTRACT_ROOT: tempRoot }, stdio: "pipe" },
  );

  const staleRelative = `base44/functions/${ENTRY_MODULES[0][0]}/entry.ts`;
  const stalePath = path.join(tempRoot, staleRelative);
  const staleSource = fs.readFileSync(stalePath, "utf8");
  const staleFingerprint = changedFingerprint === "cccccccccccccccc"
    ? "dddddddddddddddd"
    : "cccccccccccccccc";
  const deliberatelyStale = staleSource.replace(
    /const BASE44_HANDLER_RELEASE_FINGERPRINT = "[0-9a-f]{16}";/,
    `const BASE44_HANDLER_RELEASE_FINGERPRINT = "${staleFingerprint}";`,
  );
  assert.notEqual(deliberatelyStale, staleSource, "test must actually stale one entry identity");
  fs.writeFileSync(stalePath, deliberatelyStale);

  assert.throws(
    () => execFileSync(
      process.execPath,
      [path.join(ROOT, "scripts/generate_release_contracts.mjs"), "--check"],
      {
        cwd: ROOT,
        env: { ...process.env, RELEASE_CONTRACT_ROOT: tempRoot },
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    ),
    (error) => {
      assert.notEqual(error.status, 0, "stale entry identity must make --check fail");
      assert.ok(
        String(error.stderr || "").includes(staleRelative),
        `--check must report the stale entry path: ${staleRelative}`,
      );
      return true;
    },
  );
});

test("every function carrying a release contract has a maintained entry identity", () => {
  // The generator writes generatedReleaseContract.js to nine functions but
  // maintains entry identities separately. When those two lists drift, a
  // fingerprint move changes only an *imported* module -- which is exactly the
  // shape Base44 was observed to serve from a stale compiled worker. Deriving
  // both from the filesystem means the drift cannot reappear silently.
  const generator = source("scripts/generate_release_contracts.mjs");
  const contractCarrying = fs
    .readdirSync(path.join(ROOT, "base44/functions"))
    .filter((name) => fs.existsSync(path.join(ROOT, `base44/functions/${name}/generatedReleaseContract.js`)))
    .sort();
  assert.ok(contractCarrying.length >= 9, "expected the full release-contract set");

  const guarded = new Set(ENTRY_MODULES.map(([name]) => name));
  for (const name of contractCarrying) {
    const entryPath = path.join(ROOT, `base44/functions/${name}/entry.ts`);
    if (UNROUTED_LEGACY.has(name)) {
      assert.equal(
        fs.existsSync(entryPath),
        false,
        `${name} is declared unrouted legacy but now has an entry.ts; give it a maintained release identity or drop it from UNROUTED_LEGACY`,
      );
      continue;
    }
    assert.ok(
      guarded.has(name),
      `${name} receives a generated release contract but has no entry identity, so a fingerprint move would change only an imported module`,
    );
    assert.match(
      generator,
      new RegExp(`base44/functions/${name}/entry\\.ts`),
      `${name} entry identity is asserted here but the generator does not maintain it`,
    );
  }
});

test("the generator maintains an identity for exactly the guarded entries", () => {
  // A name asserted here but absent from the generator would go stale on the
  // next fingerprint move; a name in the generator but not asserted here would
  // never be checked. Both directions have to hold.
  const generator = source("scripts/generate_release_contracts.mjs");
  const maintained = [...generator.matchAll(/"base44\/functions\/([A-Za-z0-9_]+)\/entry\.ts"/g)]
    .map((match) => match[1])
    .sort();
  assert.deepEqual(maintained, ENTRY_MODULES.map(([name]) => name).sort());
});
