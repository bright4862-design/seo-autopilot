import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const helper = resolve("scripts/lib/v8-site-generation.sh");
const publisher = readFileSync("scripts/deploy-base44-beta-site.sh", "utf8");

function checkGeneration(value) {
  const env = { ...process.env };
  delete env.VITE_SCAN_FUNCTION_GENERATION;
  if (value !== undefined) env.VITE_SCAN_FUNCTION_GENERATION = value;
  // Run only the isolated, source-only preflight; no publish/CLI call.
  // A child process proves that export reaches the eventual npm/Vite build.
  return spawnSync("bash", [
    "-c",
    "set -euo pipefail; source \"$1\"; fixlist_require_v8_site_generation; bash -c 'printf %s \"$VITE_SCAN_FUNCTION_GENERATION\"'",
    "v8-generation-test",
    helper,
  ], { encoding: "utf8", env });
}

test("V8 publisher pins unset, empty, and explicit V8 generation in child builds", () => {
  for (const value of [undefined, "", "V8"]) {
    const result = checkGeneration(value);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "V8");
  }
});

test("V8 site preflight refuses ambient V9 and malformed browser routing modes", () => {
  for (const value of ["V9", "v9", "V8,V9", "standard_500", " V8 "]) {
    const result = checkGeneration(value);
    assert.equal(result.status, 2, `input=${JSON.stringify(value)} stdout=${result.stdout}`);
    assert.match(result.stderr, /Refusing V8 site publication/);
    assert.equal(result.stdout, "");
  }
});

test("live site publisher invokes V8 gate before any release or deployment action", () => {
  const gate = publisher.indexOf("fixlist_require_v8_site_generation");
  const sourceGate = publisher.indexOf("fixlist_require_exact_main");
  const promotion = publisher.indexOf("assert_standard150_promotion_record.py");
  const build = publisher.indexOf("npm run build");
  const publish = publisher.indexOf("site deploy --no-build");
  assert.ok(gate > 0 && gate < sourceGate && sourceGate < promotion && promotion < build && build < publish);
  assert.match(publisher, /source "\$REPO_ROOT\/scripts\/lib\/v8-site-generation\.sh"/);
});
