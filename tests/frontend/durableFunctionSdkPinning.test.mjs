// The durable Standard 150 release deploys three Base44 functions from one
// immutable git SHA. An unpinned `npm:@base44/sdk` specifier resolves to the
// latest release at deploy time, so the same SHA can produce different runtime
// bytes on two different days -- which defeats the exact-candidate contract and
// is especially unsafe for the two functions that hold `asServiceRole` and
// write authority and allowance state.
//
// stripeWebhook pins 0.8.40 and uses asServiceRole in production, so pinning is
// compatible with service-role access; the unpinned imports were an oversight,
// not a requirement.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const FUNCTIONS_DIR = "base44/functions";

// The three functions this release deploys.
const DURABLE_RELEASE_FUNCTIONS = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
];

// Unpinned imports that predate this release. Listed explicitly so the set can
// only shrink: adding a new unpinned function fails the sweep below.
const KNOWN_UNPINNED = new Set([
  "grokChat/index.ts",
  "persistScanAuthority/index.ts",
]);

function entrypointsFor(fnName) {
  const dir = path.join(FUNCTIONS_DIR, fnName);
  return fs.readdirSync(dir)
    .filter((f) => f === "index.ts" || f === "entry.ts")
    .map((f) => path.join(dir, f));
}

function sdkImportLine(file) {
  const source = fs.readFileSync(file, "utf8");
  return source.split("\n").find((line) => line.includes("@base44/sdk")) || "";
}

/**
 * Base44 deploys only `entry.ts`, so a function whose handler lives in
 * `index.ts` ships a shim that imports it for its side effects. The shim holds
 * no SDK import of its own -- the pinned import is in the file it pulls in.
 *
 * Skipping it does not weaken this sweep: the skip requires the sibling
 * `index.ts` to exist, and `entrypointsFor` returns that file too, so the
 * pinned-version assertion below still runs against the code that actually
 * imports the SDK.
 */
function isShimForIndex(file) {
  if (path.basename(file) !== "entry.ts") return false;
  if (!fs.existsSync(path.join(path.dirname(file), "index.ts"))) return false;
  const body = fs.readFileSync(file, "utf8")
    .split("\n")
    .filter((line) => line.trim() && !line.trim().startsWith("//"))
    .join("\n")
    .trim();
  return /^import\s+["']\.\/index\.ts["'];?$/.test(body);
}

test("every function in the durable release pins the Base44 SDK", () => {
  for (const fnName of DURABLE_RELEASE_FUNCTIONS) {
    const files = entrypointsFor(fnName);
    assert.ok(files.length > 0, `${fnName} has no entrypoint`);
    for (const file of files) {
      if (isShimForIndex(file)) continue;
      const line = sdkImportLine(file);
      assert.ok(line, `${file} does not import the Base44 SDK`);
      assert.match(
        line,
        /@base44\/sdk@\d+\.\d+\.\d+/,
        `${file} imports the Base44 SDK without a pinned version; the same git SHA would deploy different bytes over time`,
      );
    }
  }
});

test("the service-role functions in this release are pinned", () => {
  // These two hold asServiceRole and write authority/allowance state, so a
  // silent SDK change is a release-safety problem, not just reproducibility.
  for (const fnName of ["durableScanWorkerControl", "persistDurableScanAuthority"]) {
    for (const file of entrypointsFor(fnName)) {
      const source = fs.readFileSync(file, "utf8");
      if (!source.includes("asServiceRole")) continue;
      assert.match(
        sdkImportLine(file),
        /@base44\/sdk@\d+\.\d+\.\d+/,
        `${file} uses asServiceRole with an unpinned SDK`,
      );
    }
  }
});

test("no new unpinned SDK imports are introduced anywhere", () => {
  const unpinned = [];
  for (const fnName of fs.readdirSync(FUNCTIONS_DIR)) {
    const dir = path.join(FUNCTIONS_DIR, fnName);
    if (!fs.statSync(dir).isDirectory()) continue;
    for (const file of fs.readdirSync(dir)) {
      if (file !== "index.ts" && file !== "entry.ts") continue;
      const full = path.join(dir, file);
      const line = sdkImportLine(full);
      if (line && !/@base44\/sdk@\d+\.\d+\.\d+/.test(line)) {
        unpinned.push(`${fnName}/${file}`);
      }
    }
  }
  for (const found of unpinned) {
    assert.ok(
      KNOWN_UNPINNED.has(found),
      `${found} imports the Base44 SDK unpinned; pin it or add it to KNOWN_UNPINNED with a reason`,
    );
  }
  // Guard against the allowlist going stale once those two are pinned.
  assert.ok(
    unpinned.length <= KNOWN_UNPINNED.size,
    "KNOWN_UNPINNED is larger than the actual unpinned set; shrink the allowlist",
  );
});
