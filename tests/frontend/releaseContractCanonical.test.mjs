import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/**
 * Patch A — one canonical release contract.
 *
 * The active Standard 150 worker and its completed ScanRuns agree on one
 * fingerprint while other Base44 paths still ship a different, older one, and
 * several runtime consumers carry copied literals. A release marker that can be
 * copied is a release marker that can silently disagree with itself.
 *
 * These tests pin the property: there is exactly one authoritative input, every
 * runtime consumer is generated from it, and no stale value survives anywhere.
 */

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const REVISION_RECORD = path.join(ROOT, "data/beta-crawler-revision.json");
const CROSS_RUNTIME_INPUT = path.join(ROOT, "data/cross-runtime-release-components.json");
const GENERATOR = path.join(ROOT, "scripts/generate_release_contracts.mjs");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function sourceFiles() {
  const roots = ["src", "base44", "scripts", "data"];
  const out = [];
  const skip = new Set(["node_modules", ".git", "dist", "__pycache__"]);
  for (const dir of roots) {
    const stack = [path.join(ROOT, dir)];
    while (stack.length) {
      const current = stack.pop();
      if (!fs.existsSync(current)) continue;
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        if (skip.has(entry.name)) continue;
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) stack.push(full);
        else if (/\.(js|jsx|ts|tsx|mjs|json|jsonc)$/.test(entry.name)) out.push(full);
      }
    }
  }
  return out;
}

// ------------------------------------------------ one authoritative input --

test("the canonical cross-runtime component input exists and is schema-valid", () => {
  assert.ok(fs.existsSync(CROSS_RUNTIME_INPUT), `missing ${CROSS_RUNTIME_INPUT}`);
  const input = readJson(CROSS_RUNTIME_INPUT);
  assert.equal(typeof input.schema_version, "string");
  assert.ok(input.schema_version.length > 0);
  assert.ok(input.components && typeof input.components === "object");
  for (const [key, value] of Object.entries(input.components)) {
    assert.match(key, /^[a-z0-9_]+$/, `component key ${key} is not snake_case`);
    assert.equal(typeof value, "string", `component ${key} must be a string`);
    assert.ok(value.trim().length > 0, `component ${key} is empty`);
  }
});

test("the recorded candidate stays a candidate until production acceptance", () => {
  const record = readJson(REVISION_RECORD);
  assert.equal(record.status, "candidate");
  assert.equal(record.git_commit, "");
  assert.equal(record.acceptance_report, "");
});

// -------------------------------------------------- no stale marker path --

test("no stale release fingerprint literal survives anywhere in shipped source", () => {
  const current = readJson(REVISION_RECORD).fingerprint;
  assert.match(current, /^[0-9a-f]{16}$/);

  const offenders = [];
  for (const file of sourceFiles()) {
    const text = fs.readFileSync(file, "utf8");
    for (const match of text.matchAll(/\b[0-9a-f]{16}\b/g)) {
      if (match[0] !== current) offenders.push(`${path.relative(ROOT, file)}: ${match[0]}`);
    }
  }
  assert.deepEqual(offenders, [], `stale release fingerprints still shipped:\n${offenders.join("\n")}`);
});

test("every runtime consumer carries the recorded candidate fingerprint", () => {
  const current = readJson(REVISION_RECORD).fingerprint;
  const carriers = sourceFiles().filter((file) => /\b[0-9a-f]{16}\b/.test(fs.readFileSync(file, "utf8")));
  assert.ok(carriers.length > 0, "no consumer carries a fingerprint at all");
  for (const file of carriers) {
    const found = [...fs.readFileSync(file, "utf8").matchAll(/\b[0-9a-f]{16}\b/g)].map((m) => m[0]);
    for (const value of found) {
      assert.equal(value, current, `${path.relative(ROOT, file)} carries ${value}, not ${current}`);
    }
  }
});

// ------------------------------------------------------ generated, not copied --

test("the generator exists and is deterministic", () => {
  assert.ok(fs.existsSync(GENERATOR), `missing ${GENERATOR}`);

  const before = new Map();
  const emitted = execFileSync("node", [GENERATOR, "--list"], { cwd: ROOT, encoding: "utf8" })
    .split("\n").map((line) => line.trim()).filter(Boolean);
  assert.ok(emitted.length > 0, "generator emits no consumers");

  for (const rel of emitted) before.set(rel, fs.readFileSync(path.join(ROOT, rel), "utf8"));
  execFileSync("node", [GENERATOR], { cwd: ROOT });
  for (const [rel, previous] of before) {
    assert.equal(fs.readFileSync(path.join(ROOT, rel), "utf8"), previous, `${rel} is not deterministic`);
  }
});

test("generated consumers are marked do-not-edit and agree with the input", () => {
  const record = readJson(REVISION_RECORD);
  const emitted = execFileSync("node", [GENERATOR, "--list"], { cwd: ROOT, encoding: "utf8" })
    .split("\n").map((line) => line.trim()).filter(Boolean);

  for (const rel of emitted) {
    const text = fs.readFileSync(path.join(ROOT, rel), "utf8");
    assert.match(text, /DO NOT EDIT/, `${rel} is not marked generated`);
    assert.ok(text.includes(record.fingerprint), `${rel} does not carry the recorded fingerprint`);
  }
});

test("editing a generated consumer is detected as drift", () => {
  const emitted = execFileSync("node", [GENERATOR, "--list"], { cwd: ROOT, encoding: "utf8" })
    .split("\n").map((line) => line.trim()).filter(Boolean);
  const target = path.join(ROOT, emitted[0]);
  const original = fs.readFileSync(target, "utf8");
  try {
    fs.writeFileSync(target, `${original}\n// hand edit\n`);
    assert.throws(
      () => execFileSync("node", [GENERATOR, "--check"], { cwd: ROOT, stdio: "pipe" }),
      "a hand-edited generated consumer must fail --check",
    );
  } finally {
    fs.writeFileSync(target, original);
  }
});

// ------------------------------------------- python fingerprint authority --

test("cross-runtime components participate in the python fingerprint", () => {
  const script = [
    "import json,sys",
    "sys.path.insert(0, 'scanner-api')",
    "from app.beta_revision import collect_component_versions",
    "print(json.dumps(collect_component_versions()))",
  ].join("; ");
  const versions = JSON.parse(execFileSync("python3", ["-c", script], { cwd: ROOT, encoding: "utf8" }));
  const input = readJson(CROSS_RUNTIME_INPUT);
  for (const [key, value] of Object.entries(input.components)) {
    assert.equal(versions[key], value, `cross-runtime component ${key} is not in the python fingerprint`);
  }
});

test("every declared cross-runtime component is a real marker in shipped code", () => {
  /**
   * A declared marker that no runtime actually uses is decorative: it would move
   * the fingerprint without describing any real behavior. Each one must appear
   * in the code it claims to version.
   */
  const owners = {
    authority_seal_version: "base44/functions/persistDurableScanAuthority/authoritySeal.js",
    customer_projection_version: "base44/functions/getCustomerScanResult/projection.js",
    review_attestation_version: "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    durable_completion_contract_version: "base44/functions/persistDurableScanAuthority/index.ts",
    durable_control_contract_version: "base44/functions/durableScanWorkerControl/index.ts",
    durable_worker_contract_version: "base44/functions/durableScanWorkerControl/index.ts",
    repair_presentation_contract_version: "src/lib/repairPresentation.js",
    repair_write_contract_version: "src/lib/repairContractPresentation.js",
    repair_suggestion_library_version: "src/lib/repairSuggestions.js",
  };
  const input = readJson(CROSS_RUNTIME_INPUT);

  for (const [key, value] of Object.entries(input.components)) {
    const owner = owners[key];
    assert.ok(owner, `cross-runtime component ${key} declares no owning module`);
    const text = fs.readFileSync(path.join(ROOT, owner), "utf8");
    assert.ok(text.includes(value), `${owner} does not carry ${key} value "${value}"`);
  }
});
