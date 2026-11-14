import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  RELEASE_FUNCTIONS,
  STAGED_RELEASE_FUNCTIONS,
} from "../../scripts/base44_release_manifest.mjs";

const ROLES = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
];

// This protects the *source-side* diagnostic contract, not published code identity.
// The actual live probe still needs HTTP 405 from the pinned Base44 app origin,
// exact source-derived build/activation values, and a separate worker /revision.
function handlerSource(name) {
  const root = "base44/functions/" + name + "/";
  const entry = readFileSync(root + "entry.ts", "utf8");
  if (/import\s+["']\.\/index\.ts["']\s*;/.test(entry)) {
    return readFileSync(root + "index.ts", "utf8");
  }
  return entry;
}

function sourceProbeFailure(source, name) {
  if (!source.includes('from "./generatedBuildId.js"')) return "build-id import missing";
  if (!source.includes('const BASE44_RUNTIME_ACTIVATION_ID = "' + name + "-")) {
    return "activation constant missing or misnamed";
  }

  const start = /(?:export default async function\s*\(req:\s*Request\)\s*:\s*Promise<Response>\s*\{|Deno\.serve\(async\s*\(req\)\s*=>\s*\{)/.exec(source);
  if (!start) return "request handler missing";
  const body = source.slice(start.index + start[0].length);
  const guard = /if\s*\(\s*req\.method\s*!==\s*["']POST["']\s*\)\s*\{\s*return\s+([\s\S]*?)\s*;\s*\}/.exec(body);
  if (!guard) return "early non-POST guard missing";

  // No auth, entity, queue, persistence, or network action may execute ahead
  // of the read-only method guard. startStandardScanJob alone allows preflight.
  const before = body.slice(0, guard.index).replace(/\/\/[^\n]*/g, "").trim();
  const optionsOnly = /^if\s*\(\s*req\.method\s*===\s*["']OPTIONS["']\s*\)\s*return\s+new Response\(null,\s*\{\s*status:\s*204,\s*headers:\s*corsHeaders\(\)\s*\}\s*\);$/;
  if (before && !optionsOnly.test(before)) return "nontrivial action precedes method guard";

  const response = guard[1];
  if (!/\b405\b/.test(response)) return "non-POST response is not HTTP 405";
  if (!/\bbuild_id:\s*FUNCTION_BUILD_ID\b/.test(response)) return "405 response lacks package identity";
  if (!/\bruntime_activation_id:\s*BASE44_RUNTIME_ACTIVATION_ID\b/.test(response)) return "405 response lacks activation identity";
  return null;
}

test("V8 public and V9 staged sources expose a bounded read-only build/activation diagnostic", () => {
  const published = ROLES.map((role) => role + "V8");
  const staged = ROLES.map((role) => role + "V9");
  assert.deepEqual(RELEASE_FUNCTIONS.filter((name) => /V8$/.test(name)), published);
  assert.deepEqual(STAGED_RELEASE_FUNCTIONS, staged);
  for (const name of [...published, ...staged]) {
    assert.equal(sourceProbeFailure(handlerSource(name), name), null, name);
  }
});

test("the 405 contract rejects premature auth work, missing identity and wrong HTTP status", () => {
  const name = "getCustomerScanResultV9";
  const original = handlerSource(name);
  assert.equal(sourceProbeFailure(original, name), null);

  const movedAuth = original.replace(
    '  if (req.method !== "POST") {',
    '  const user = await base44.auth.me();\n  if (req.method !== "POST") {',
  );
  assert.equal(sourceProbeFailure(movedAuth, name), "nontrivial action precedes method guard");

  const missingBuild = original.replace(
    "build_id: FUNCTION_BUILD_ID, runtime_activation_id:",
    "runtime_activation_id:",
  );
  assert.equal(sourceProbeFailure(missingBuild, name), "405 response lacks package identity");

  const wrongStatus = original.replace(
    "runtime_activation_id: BASE44_RUNTIME_ACTIVATION_ID }, { status: 405 }",
    "runtime_activation_id: BASE44_RUNTIME_ACTIVATION_ID }, { status: 200 }",
  );
  assert.equal(sourceProbeFailure(wrongStatus, name), "non-POST response is not HTTP 405");
});
