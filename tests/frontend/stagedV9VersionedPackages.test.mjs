import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { assertPulledFunctionPackage, STAGED_RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";
import { materializeStagedV9Packages, STAGED_V9_ROUTES_FILE } from "../../scripts/lib/staged-v9-function-packages.mjs";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const GENERATOR = path.join(ROOT, "scripts/generate_release_contracts.mjs");
const MATERIALIZER = path.join(ROOT, "scripts/materialize-base44-staged-functions.mjs");
const FUNCTIONS = "base44/functions";

function tempRoot(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-versioned-v9-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function readRoutes(root) {
  return JSON.parse(fs.readFileSync(path.join(root, STAGED_V9_ROUTES_FILE), "utf8"));
}

function readPackageBuildId(dir) {
  const hash = createHash("sha256");
  for (const file of fs.readdirSync(dir).sort()) {
    if (file !== "generatedBuildId.js") {
      hash.update(file).update("\0").update(fs.readFileSync(path.join(dir, file))).update("\0");
    }
  }
  return hash.digest("hex");
}

test("materializes exactly six deterministic Base44 packages with distinct source and runtime identities", t => {
  const parent = tempRoot(t);
  const first = path.join(parent, "first");
  const second = path.join(parent, "second");
  for (const project of [first, second]) execFileSync(process.execPath, [MATERIALIZER, project]);

  const contract = readRoutes(ROOT);
  assert.equal(contract.schema_version, "fixlist_staged_v9_routes_v1");
  assert.deepEqual(Object.keys(contract.functions).sort(), [...STAGED_RELEASE_FUNCTIONS].sort());
  assert.deepEqual(fs.readdirSync(path.join(first, FUNCTIONS)).sort(),
    Object.values(contract.functions).map(row => row.route_name).sort());
  assert.deepEqual(fs.readdirSync(path.join(first, "base44/entities")), []);
  assert.equal(JSON.parse(fs.readFileSync(path.join(first, "base44/config.jsonc"), "utf8")).functionsDir, "functions");

  for (const [name, row] of Object.entries(contract.functions)) {
    const canonical = path.join(ROOT, FUNCTIONS, name);
    const materialized = path.join(first, FUNCTIONS, row.route_name);
    const duplicate = path.join(second, FUNCTIONS, row.route_name);
    assert.equal(row.route_name, `${name}B${readPackageBuildId(canonical).slice(0, 16)}`);
    assert.ok(row.route_name.length <= 63);
    assert.equal(readPackageBuildId(materialized), row.build_id);
    assert.notEqual(row.build_id, readPackageBuildId(canonical));
    assert.ok(fs.readFileSync(path.join(materialized, "generatedBuildId.js"), "utf8").includes(row.build_id));
    assert.equal(assertPulledFunctionPackage(row.route_name, materialized, duplicate), row.package_digest);
    assert.equal(fs.readFileSync(path.join(materialized, "function.jsonc"), "utf8"),
      fs.readFileSync(path.join(canonical, "function.jsonc"), "utf8").replace(`"${name}"`, `"${row.route_name}"`));
    for (const file of fs.readdirSync(canonical)) {
      if (file === "function.jsonc" || file === "generatedBuildId.js") continue;
      assert.ok(fs.readFileSync(path.join(canonical, file)).equals(fs.readFileSync(path.join(materialized, file))),
        `${name}/${file} changed during materialization`);
    }
    assert.ok(fs.readFileSync(path.join(materialized, "entry.ts"), "utf8").includes(row.runtime_activation_id));
  }

  const reused = spawnSync(process.execPath, [MATERIALIZER, first], { encoding: "utf8" });
  assert.notEqual(reused.status, 0);
  assert.equal(fs.readdirSync(path.join(first, FUNCTIONS)).length, 6);

  const route = contract.functions.persistDurableScanAuthorityV9.route_name;
  fs.appendFileSync(path.join(second, FUNCTIONS, route, "entry.ts"), "\n// Tampered pull.\n");
  assert.throws(() => assertPulledFunctionPackage(route, path.join(first, FUNCTIONS, route),
    path.join(second, FUNCTIONS, route)), /file bytes differ for entry\.ts/);
});

test("generator and materializer detect package drift then generate a fresh route for the changed package", t => {
  const root = tempRoot(t);
  for (const name of ["data/beta-crawler-revision.json", "data/cross-runtime-release-components.json", STAGED_V9_ROUTES_FILE,
    ...STAGED_RELEASE_FUNCTIONS.map(fn => path.join(FUNCTIONS, fn))]) {
    fs.cpSync(path.join(ROOT, name), path.join(root, name), { recursive: true });
  }
  const env = { ...process.env, RELEASE_CONTRACT_ROOT: root };
  execFileSync(process.execPath, [GENERATOR], { env });
  const original = readRoutes(root);
  assert.deepEqual(original, readRoutes(ROOT));
  const name = "durableScanWorkerControlV9";
  fs.appendFileSync(path.join(root, FUNCTIONS, name, "workerRuntime.js"), "\n// New source bytes.\n");
  const check = spawnSync(process.execPath, [GENERATOR, "--check"], { env, encoding: "utf8" });
  assert.equal(check.status, 1);
  assert.ok(check.stderr.includes(STAGED_V9_ROUTES_FILE));
  assert.ok(check.stderr.includes("scanner-api/app/generated_v9_worker_runtime.py"));

  const output = path.join(root, "fresh-project");
  assert.throws(() => materializeStagedV9Packages(root, output), /routes differ from package bytes/);
  assert.equal(fs.existsSync(output), false);

  execFileSync(process.execPath, [GENERATOR], { env });
  execFileSync(process.execPath, [GENERATOR, "--check"], { env });
  const updated = readRoutes(root);
  assert.notEqual(updated.functions[name].route_name, original.functions[name].route_name);
  assert.notEqual(updated.functions[name].build_id, original.functions[name].build_id);
  assert.notEqual(updated.functions[name].package_digest, original.functions[name].package_digest);
  assert.equal(updated.functions[name].runtime_activation_id, original.functions[name].runtime_activation_id);
  for (const unchanged of STAGED_RELEASE_FUNCTIONS.filter(fn => fn !== name)) {
    assert.deepEqual(updated.functions[unchanged], original.functions[unchanged]);
  }
  materializeStagedV9Packages(root, output);
  assert.ok(fs.existsSync(path.join(output, FUNCTIONS, updated.functions[name].route_name)));
});

test("recording acceptance and selecting public V9 preserves the exact staged package bytes", t => {
  const parent = tempRoot(t);
  const source = path.join(parent, "source");
  const stablePaths = ["base44/functions", "src", STAGED_V9_ROUTES_FILE,
    "data/cross-runtime-release-components.json", "scanner-api/app/generated_v9_worker_runtime.py"];
  for (const rel of [...stablePaths, "data/beta-crawler-revision.json", "data/base44-function-routes.json",
    "scripts/generate_release_contracts.mjs", "scripts/base44_release_manifest.mjs",
    "scripts/lib/staged-v9-function-packages.mjs"]) {
    fs.cpSync(path.join(ROOT, rel), path.join(source, rel), { recursive: true });
  }
  const env = { ...process.env, RELEASE_CONTRACT_ROOT: source };
  const generate = (...args) => execFileSync(process.execPath, [path.join(source, "scripts/generate_release_contracts.mjs"), ...args],
    { cwd: source, env, stdio: "pipe" });
  const exactFiles = root => fs.readdirSync(root, { recursive: true }).sort().flatMap(rel => {
    const file = path.join(root, rel);
    return fs.statSync(file).isFile() ? [[rel, createHash("sha256").update(fs.readFileSync(file)).digest("hex")]] : [];
  });
  const releaseFile = path.join(source, "data/beta-crawler-revision.json");
  const routesFile = path.join(source, "data/base44-function-routes.json");
  const record = JSON.parse(fs.readFileSync(releaseFile, "utf8"));
  const routes = JSON.parse(fs.readFileSync(routesFile, "utf8"));
  const v8 = routes.generation === "v8" ? routes.routes : routes.historical_routes.v8;
  const v9 = routes.generation === "v9" ? routes.routes : routes.candidate_routes.v9;
  const history = { ...routes.historical_routes };
  delete history.v8;
  fs.writeFileSync(releaseFile, JSON.stringify({ ...record, status: "candidate", git_commit: "", acceptance_report: "" }));
  fs.writeFileSync(routesFile, JSON.stringify({ ...routes, generation: "v8", routes: v8,
    historical_routes: history, candidate_routes: { ...routes.candidate_routes, v9 } }));
  generate("--check");
  const candidate = path.join(parent, "candidate");
  materializeStagedV9Packages(source, candidate);
  const candidateFiles = exactFiles(source);

  const frozenRecord = { ...record, status: "frozen_beta", git_commit: "a".repeat(40),
    acceptance_report: "docs/fixture-accepted-release.md" };
  fs.writeFileSync(releaseFile, JSON.stringify(frozenRecord));
  fs.writeFileSync(routesFile, JSON.stringify({ ...routes, generation: "v9", routes: v9,
    historical_routes: { ...history, v8 }, candidate_routes: {} }));
  generate("--check");
  generate();
  const frozen = path.join(parent, "frozen");
  materializeStagedV9Packages(source, frozen);

  const metadata = new Set(["data/beta-crawler-revision.json", "data/base44-function-routes.json"]);
  assert.deepEqual(exactFiles(source).filter(([rel]) => !metadata.has(rel)),
    candidateFiles.filter(([rel]) => !metadata.has(rel)), "freezing must preserve runtime and historical reader bytes");
  assert.deepEqual(exactFiles(frozen), exactFiles(candidate), "same accepted package archive must preserve every deployed byte");
  assert.deepEqual(JSON.parse(fs.readFileSync(releaseFile, "utf8")), frozenRecord);
});
