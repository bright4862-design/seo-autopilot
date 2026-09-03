import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
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
const REVISION_RECORD_REL = "data/beta-crawler-revision.json";
const CROSS_RUNTIME_REL = "data/cross-runtime-release-components.json";
const REVISION_RECORD = path.join(ROOT, REVISION_RECORD_REL);
const CROSS_RUNTIME_INPUT = path.join(ROOT, CROSS_RUNTIME_REL);
const HISTORICAL_COMPAT_REL = "base44/functions/getCustomerScanResult/releaseCompatibility.js";
const HISTORICAL_COMPAT_ALIAS_REL = "base44/functions/getCustomerScanResultV2/releaseCompatibility.js";
const HISTORICAL_COMPAT_RELS = new Set([HISTORICAL_COMPAT_REL, HISTORICAL_COMPAT_ALIAS_REL]);
const HISTORICAL_COMPAT = path.join(ROOT, HISTORICAL_COMPAT_REL);
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

test("old release fingerprints are isolated to the explicit historical reader registry", () => {
  const current = readJson(REVISION_RECORD).fingerprint;
  assert.match(current, /^[0-9a-f]{16}$/);

  const offenders = [];
  for (const file of sourceFiles()) {
    const rel = path.relative(ROOT, file).replaceAll("\\", "/");
    const text = fs.readFileSync(file, "utf8");
    for (const match of text.matchAll(/\b[0-9a-f]{16}\b/g)) {
      if (match[0] !== current && !HISTORICAL_COMPAT_RELS.has(rel)) {
        offenders.push(`${rel}: ${match[0]}`);
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `old release fingerprints escaped the explicit historical compatibility registry:\n${offenders.join("\n")}`,
  );

  const compatibility = fs.readFileSync(HISTORICAL_COMPAT, "utf8");
  const historical = [...compatibility.matchAll(/\b[0-9a-f]{16}\b/g)].map((match) => match[0]);
  assert.ok(historical.length > 0, "historical compatibility registry is unexpectedly empty");
  assert.ok(historical.every((value) => value !== current), "current fingerprint belongs in the generated release contract, not historical registry");
  assert.match(compatibility, /HISTORICAL_READABLE_RELEASE_FINGERPRINTS/);
  assert.match(compatibility, /CUSTOMER_RESULT_READER_VERSION/);
  assert.equal(fs.readFileSync(path.join(ROOT, HISTORICAL_COMPAT_ALIAS_REL), "utf8"), compatibility, "V2 reader must mirror the canonical historical compatibility registry");
});

test("every ordinary runtime fingerprint carrier uses the recorded candidate fingerprint", () => {
  const current = readJson(REVISION_RECORD).fingerprint;
  const carriers = sourceFiles().filter((file) => {
    const rel = path.relative(ROOT, file).replaceAll("\\", "/");
    return !HISTORICAL_COMPAT_RELS.has(rel) && /\b[0-9a-f]{16}\b/.test(fs.readFileSync(file, "utf8"));
  });
  assert.ok(carriers.length > 0, "no consumer carries a fingerprint at all");
  for (const file of carriers) {
    const found = [...fs.readFileSync(file, "utf8").matchAll(/\b[0-9a-f]{16}\b/g)].map((m) => m[0]);
    for (const value of found) {
      assert.equal(value, current, `${path.relative(ROOT, file)} carries ${value}, not ${current}`);
    }
  }
});

// ------------------------------------------------------ generated, not copied --

/**
 * Drive the generator against an isolated copy of the inputs and consumers.
 * `node --test` runs files in parallel, so a check that wrote to the real tree
 * would race with any other test importing a generated contract.
 */
function isolatedRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "release-contract-"));
  const emitted = execFileSync("node", [GENERATOR, "--list"], { cwd: ROOT, encoding: "utf8" })
    .split("\n").map((line) => line.trim()).filter(Boolean);
  for (const rel of [REVISION_RECORD_REL, CROSS_RUNTIME_REL, ...emitted]) {
    const from = path.join(ROOT, rel);
    if (!fs.existsSync(from)) continue;
    const to = path.join(root, rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(from, to);
  }
  return { root, emitted };
}

test("the generator exists and is deterministic", () => {
  assert.ok(fs.existsSync(GENERATOR), `missing ${GENERATOR}`);
  const { root, emitted } = isolatedRoot();
  const env = { ...process.env, RELEASE_CONTRACT_ROOT: root };

  execFileSync("node", [GENERATOR], { cwd: ROOT, env });
  const first = emitted.map((rel) => fs.readFileSync(path.join(root, rel), "utf8"));
  execFileSync("node", [GENERATOR], { cwd: ROOT, env });
  const second = emitted.map((rel) => fs.readFileSync(path.join(root, rel), "utf8"));

  assert.ok(emitted.length > 0, "generator emits no consumers");
  assert.deepEqual(second, first, "generator output is not deterministic");
});

test("the committed contracts are already up to date with their inputs", () => {
  execFileSync("node", [GENERATOR, "--check"], { cwd: ROOT, stdio: "pipe" });
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
  const { root, emitted } = isolatedRoot();
  const env = { ...process.env, RELEASE_CONTRACT_ROOT: root };
  execFileSync("node", [GENERATOR], { cwd: ROOT, env });

  const target = path.join(root, emitted[0]);
  fs.writeFileSync(target, `${fs.readFileSync(target, "utf8")}\n// hand edit\n`);
  assert.throws(
    () => execFileSync("node", [GENERATOR, "--check"], { cwd: ROOT, env, stdio: "pipe" }),
    "a hand-edited generated consumer must fail --check",
  );
});

// ----------------------------------------------- fingerprint participation --

/**
 * Python's fingerprint, re-derived without Python.
 *
 * beta_revision.fingerprint is sha256 over json.dumps(components,
 * sort_keys=True, separators=(",", ":")), truncated to 16 hex. Every marker is
 * ASCII, so JSON.stringify over sorted keys is byte-identical to that payload
 * -- asserted below rather than assumed, because Python escapes non-ASCII by
 * default and Node does not.
 *
 * This runs in the frontend job, which installs Node only. Shelling out to
 * python3 here fails on `import bs4`: collect_component_versions reaches the
 * scanner modules transitively. The Python-side half -- that the collector
 * really does merge this input, and fails closed without it -- is asserted in
 * scanner-api/tests/test_beta_revision.py, where the dependencies exist.
 */
function pythonFingerprint(components) {
  const keys = Object.keys(components).sort();
  for (const key of keys) {
    assert.ok(
      /^[\x20-\x7e]*$/.test(key) && /^[\x20-\x7e]*$/.test(components[key]),
      `component ${key} is not ASCII; the node re-derivation would not match python`,
    );
  }
  const payload = `{${keys.map((key) => `${JSON.stringify(key)}:${JSON.stringify(components[key])}`).join(",")}}`;
  return createHash("sha256").update(payload, "utf8").digest("hex").slice(0, 16);
}

test("the recorded fingerprint is the hash of the recorded component set", () => {
  const record = readJson(REVISION_RECORD);
  assert.equal(pythonFingerprint(record.component_versions), record.fingerprint);
});

test("cross-runtime components participate in the release fingerprint", () => {
  const record = readJson(REVISION_RECORD);
  const input = readJson(CROSS_RUNTIME_INPUT);

  for (const [key, value] of Object.entries(input.components)) {
    assert.equal(
      record.component_versions[key],
      value,
      `cross-runtime component ${key} is not in the recorded component set`,
    );
  }

  // Presence in the record is not participation. Drop each declared marker and
  // the fingerprint must move, or the record could carry a decorative copy.
  for (const key of Object.keys(input.components)) {
    const without = { ...record.component_versions };
    delete without[key];
    assert.notEqual(
      pythonFingerprint(without),
      record.fingerprint,
      `dropping ${key} does not move the fingerprint`,
    );
  }
});

test("every declared cross-runtime component is a real marker in shipped code", () => {
  /**
   * A declared marker that no runtime actually uses is decorative: it would move
   * the fingerprint without describing any real behavior. Each one must appear
   * in the code it claims to version.
   */
  const owners = {
    admission_reconciliation_version: "base44/functions/durableScanWorkerControl/generatedReleaseContract.js",
    authority_seal_version: "base44/functions/persistDurableScanAuthority/authoritySeal.js",
    customer_projection_version: "base44/functions/getCustomerScanResult/projection.js",
    customer_result_reader_version: "base44/functions/getCustomerScanResult/releaseCompatibility.js",
    limited_result_integrity_version: "base44/functions/persistLimitedScanResult/limitedResultIntegrity.js",
    review_attestation_version: "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    durable_completion_contract_version: "base44/functions/persistDurableScanAuthority/entry.ts",
    durable_control_contract_version: "base44/functions/durableScanWorkerControl/entry.ts",
    durable_worker_contract_version: "base44/functions/durableScanWorkerControl/entry.ts",
    failure_state_presentation_version: "src/pages/FixList.jsx",
    focused_scan_scope_version: "src/lib/focusedScanScope.js",
    priority_summary_version: "src/pages/FixList.jsx",
    scan_history_version: "src/lib/scanRuns.js",
    scan_history_delete_version: "base44/functions/deleteCustomerScanData/index.ts",
    count_copy_version: "src/pages/FixList.jsx",
    repair_presentation_contract_version: "src/lib/repairPresentation.js",
    repair_write_contract_version: "src/lib/repairContractPresentation.js",
    repair_suggestion_library_version: "src/lib/repairSuggestions.js",
    sampling_disclosure_version: "src/lib/samplingDisclosure.js",
  };
  const input = readJson(CROSS_RUNTIME_INPUT);

  for (const [key, value] of Object.entries(input.components)) {
    const owner = owners[key];
    assert.ok(owner, `cross-runtime component ${key} declares no owning module`);
    const text = fs.readFileSync(path.join(ROOT, owner), "utf8");
    assert.ok(text.includes(value), `${owner} does not carry ${key} value "${value}"`);
  }
});
