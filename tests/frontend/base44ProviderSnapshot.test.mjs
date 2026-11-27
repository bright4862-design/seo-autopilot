import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { captureFunctionInventory } from "../../scripts/lib/base44-pilot-inventory.mjs";
import { buildInputs } from "../../scripts/lib/base44-provider-inputs.mjs";
import { prepareProviderSnapshot } from "../../scripts/lib/base44-provider-snapshot.mjs";
import { renderStagedV9Packages, stagedV9RoutesSource, materializeStagedV9Packages } from "../../scripts/lib/staged-v9-function-packages.mjs";
import { STAGED_RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";

const sha = "1".repeat(40);
const root = fileURLToPath(new URL("../../", import.meta.url));
function write(location, content) {
  fs.mkdirSync(path.dirname(location), { recursive: true });
  fs.writeFileSync(location, content);
}
function writeFunction(project, name, bytes) {
  const dir = path.join(project, "base44/functions", name);
  write(path.join(dir, "function.jsonc"), JSON.stringify({ name, entry: "entry.ts" }));
  write(path.join(dir, "entry.ts"), 'const BASE44_RUNTIME_ACTIVATION_ID = "fixture-v1";\n' + bytes);
}
function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "provider-snapshot-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const source = path.join(temp, "source"), legacy = path.join(temp, "legacy");
  const capture = path.join(temp, "capture"), output = path.join(temp, "output");
  for (const item of buildInputs) {
    if (["src", "public", "base44/agents", "base44/entities"].includes(item)) fs.mkdirSync(path.join(source, item), { recursive: true });
    else write(path.join(source, item), item.endsWith(".json") ? "{}" : "");
  }
  write(path.join(source, "vite.config.js"), "export default {};\n");
  write(path.join(source, "package.json"), '{"type":"module","scripts":{"build":"vite build"}}');
  write(path.join(source, "package-lock.json"), "{}");
  write(path.join(source, "index.html"), '<script type="module" src="/src/main.js"></script>');
  write(path.join(source, "src/main.js"), "window.fixture = [import.meta.env.VITE_BASE44_APP_ID, import.meta.env.VITE_FIXLIST_SOURCE_SHA, import.meta.env.VITE_SCAN_FUNCTION_GENERATION];");
  write(path.join(source, "base44/config.jsonc"), '{"site":{"buildCommand":"npm run build"}}');
  write(path.join(source, "data/beta-crawler-revision.json"), '{"status":"candidate","git_commit":"","acceptance_report":""}');
  write(path.join(legacy, "data/beta-crawler-revision.json"), '{"fingerprint":"b36ca24b8e0f728e"}');
  const routes = {};
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const key = name.slice(0, -2), v8 = key + "V8";
    routes[key] = v8;
    writeFunction(source, name, "export default 9;");
    writeFunction(legacy, v8, "export default 8;");
    writeFunction(source, v8, "export default 81;");
  }
  write(path.join(source, "data/base44-function-routes.json"), JSON.stringify({ generation: "v8", routes }));
  write(path.join(source, "data/generated-staged-v9-routes.json"), stagedV9RoutesSource(renderStagedV9Packages(source).contract));
  materializeStagedV9Packages(source, capture);
  const capturedFunction = name => path.join(capture, "base44/functions", name);
  for (const v8 of Object.values(routes)) fs.cpSync(path.join(source, "base44/functions", v8), capturedFunction(v8), { recursive: true });
  writeFunction(capture, "providerOnlyFunction", "export default 40;");
  writeFunction(capture, "deleteCustomerScanDataV2", "export default 20;");
  const shared = "base44/functions/persistDurableScanAuthorityV7/evidenceUrlIdentity.js";
  writeFunction(capture, "persistDurableScanAuthorityV7", "export default 7;");
  for (const project of [capture, source]) write(path.join(project, shared), "export const version = 1;");
  const listing = fs.readdirSync(path.join(capture, "base44/functions")).map(n => "  " + n).join("\n");
  write(path.join(capture, "listed.txt"), listing);
  const record = () => write(path.join(capture, "digests.json"), JSON.stringify(captureFunctionInventory(capture, listing)));
  record();
  const prepare = () => prepareProviderSnapshot(source, legacy, capture, output, sha, sha, "preview");
  return { output, capture, listing, record, prepare, capturedFunction };
}

test("a no-Git, no-release-env provider build retains the entire capture, substitutes only pinned V8 and runs the configured build", t => {
  const { output, capture, listing, prepare } = fixture(t);
  const manifest = prepare();
  assert.equal(Object.keys(manifest.functions).length, 15);
  assert.equal(manifest.restored_v8.length, 6);
  for (const name of ["providerOnlyFunction", "deleteCustomerScanDataV2"]) {
    assert.equal(manifest.functions[name], captureFunctionInventory(capture, listing)[name]);
  }
  assert.equal(fs.existsSync(path.join(output, ".git")), false);
  fs.symlinkSync(path.join(root, "node_modules"), path.join(output, "node_modules"));
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(VITE_|BASE44_|GIT_|GITHUB_)/.test(k)));
  const build = options => spawnSync("npm", ["run", "build"], { cwd: output, env: { ...env, ...options }, encoding: "utf8" });
  const result = build({});
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const assets = path.join(output, "dist/assets");
  const js = fs.readFileSync(path.join(assets, fs.readdirSync(assets).find(p => p.endsWith(".js"))), "utf8");
  for (const expected of [sha, "PUBLISHED_PILOT", "6a498732ec779dfaaeab0e53"]) assert.ok(js.includes(expected));
  assert.notEqual(build({ VITE_SCAN_FUNCTION_GENERATION: "PUBLIC" }).status, 0);
  fs.appendFileSync(path.join(output, "base44/functions/providerOnlyFunction/entry.ts"), "\n// changed");
  assert.match(build({}).stderr, /Provider package inventory changed/);
});

test("unrecognized V8 bytes or stale recorded inventory abort the build and remove the partial output", t => {
  const f = fixture(t);
  fs.appendFileSync(path.join(f.capturedFunction("getCustomerScanResultV8"), "entry.ts"), "\n// unknown");
  assert.throws(f.prepare, /recorded digests/);
  f.record();
  assert.throws(f.prepare, /Unrecognized captured package/);
  assert.equal(fs.existsSync(f.output), false);
});

test("changed V9 aliases and missing listed functions cannot be silently recreated", t => {
  const f = fixture(t);
  const alias = fs.readdirSync(path.join(f.capture, "base44/functions")).find(name => name.includes("V9B"));
  fs.appendFileSync(path.join(f.capturedFunction(alias), "entry.ts"), "\n// unknown");
  f.record();
  assert.throws(f.prepare, /Unrecognized captured package/);
  fs.rmSync(f.capturedFunction("providerOnlyFunction"), { recursive: true });
  assert.throws(f.prepare, /disagree/);
  assert.equal(fs.existsSync(f.output), false);
});

test("a preexisting output directory and its contents survive even if the capture is invalid", t => {
  const f = fixture(t);
  fs.mkdirSync(f.output);
  const sentinel = path.join(f.output, "caller-owned");
  write(sentinel, "keep me");
  fs.appendFileSync(path.join(f.capturedFunction("getCustomerScanResultV8"), "entry.ts"), "\n// drift");
  assert.throws(f.prepare, { code: "EEXIST" });
  assert.equal(fs.readFileSync(sentinel, "utf8"), "keep me");
  assert.deepEqual(fs.readdirSync(f.output), ["caller-owned"]);
});
