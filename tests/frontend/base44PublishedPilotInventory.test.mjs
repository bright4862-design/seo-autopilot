import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { captureFunctionInventory, compareFunctionInventories } from "../../scripts/lib/base44-pilot-inventory.mjs";

function project(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "base44-pilot-inventory-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function writeFunction(root, name, { nested = false, source = "export default () => 200;" } = {}) {
  const fn = path.join(root, "base44/functions", name);
  const prefix = nested ? `base44/functions/${name}/` : "";
  const entry = prefix + "entry.ts";
  fs.mkdirSync(path.dirname(path.join(fn, entry)), { recursive: true });
  fs.writeFileSync(path.join(fn, entry), source);
  fs.writeFileSync(path.join(fn, "function.jsonc"), JSON.stringify({ name, entry }));
}

test("a pulled Base44 package can be restored without wrapping its repository-relative paths twice", t => {
  const before = project(t);
  const restore = project(t);
  const list = "Fetching functions...\n  launcherV8\n  readerV9B0000\n";
  writeFunction(before, "launcherV8", { nested: true });
  writeFunction(before, "readerV9B0000");
  const original = captureFunctionInventory(before, list, restore);
  const restored = captureFunctionInventory(restore, list);
  assert.deepEqual(compareFunctionInventories(original, restored), { missingOrChanged: [], unexpected: [] });
  const config = JSON.parse(fs.readFileSync(path.join(restore, "base44/functions/launcherV8/function.jsonc"), "utf8"));
  assert.equal(config.entry, "entry.ts");

  fs.writeFileSync(path.join(restore, "base44/functions/launcherV8/entry.ts"), "export default () => 503;");
  fs.rmSync(path.join(restore, "base44/functions/readerV9B0000"), { force: true, recursive: true });
  writeFunction(restore, "unknownRelease");
  const after = captureFunctionInventory(restore, "Fetching functions...\n  launcherV8\n  unknownRelease\n");
  assert.deepEqual(compareFunctionInventories(original, after), {
    missingOrChanged: ["launcherV8", "readerV9B0000"],
    unexpected: ["unknownRelease"],
  });
});

test("a missing listed package or link cannot be used for recovery", t => {
  const before = project(t);
  writeFunction(before, "launcherV8");
  assert.throws(() => captureFunctionInventory(before, "  launcherV8\n  readerV9B0000\n"), /disagree/);
  fs.symlinkSync("entry.ts", path.join(before, "base44/functions/launcherV8/copy.ts"));
  assert.throws(() => captureFunctionInventory(before, "  launcherV8\n"), /Unsupported/);
});

test("recovery selects original routes even if site publication adds another alias", t => {
  const root = project(t);
  const before = path.join(root, "before.json");
  const after = path.join(root, "after.json");
  fs.writeFileSync(before, JSON.stringify({ launcherV8: "original", readerV9B0000: "original" }));
  fs.writeFileSync(after, JSON.stringify({ launcherV8: "changed", unknownRelease: "additional" }));
  const inventory = fileURLToPath(new URL("../../scripts/lib/base44-pilot-inventory.mjs", import.meta.url));
  const plan = spawnSync(process.execPath, [inventory, "restore-plan", before, after], { encoding: "utf8" });
  assert.equal(plan.status, 0, plan.stderr);
  assert.equal(plan.stdout, "launcherV8\nreaderV9B0000\n");
  assert.match(plan.stderr, /Unexpected registered Base44 functions: unknownRelease/);

  fs.writeFileSync(after, JSON.stringify({ launcherV8: "original", readerV9B0000: "original", unknownRelease: "additional" }));
  const comparison = spawnSync(process.execPath, [inventory, "compare", before, after], { encoding: "utf8" });
  assert.notEqual(comparison.status, 0);
  assert.match(comparison.stderr, /Unexpected registered Base44 functions: unknownRelease/);
});

test("the site pilot authenticates a freshly pinned CLI before probing the V9 launcher", t => {
  const root = project(t);
  const scripts = path.join(root, "scripts");
  fs.mkdirSync(path.join(scripts, "lib"), { recursive: true });
  fs.mkdirSync(path.join(root, "data"));
  fs.copyFileSync(new URL("../../scripts/deploy-base44-published-pilot.sh", import.meta.url),
    path.join(scripts, "deploy-base44-published-pilot.sh"));
  fs.writeFileSync(path.join(root, "data/base44-function-routes.json"),
    JSON.stringify({ generation: "v8", candidate_routes: { v9: {} } }));
  fs.writeFileSync(path.join(root, "data/beta-crawler-revision.json"), JSON.stringify({ status: "candidate" }));
  fs.writeFileSync(path.join(scripts, "lib/release-source-guard.sh"), "fixlist_require_exact_main() { true; }\n");
  fs.writeFileSync(path.join(scripts, "lib/base44-public-routes.mjs"), 'console.log("v8 launcherV8");');
  fs.writeFileSync(path.join(scripts, "generate_release_contracts.mjs"), "");
  for (const name of ["verify-base44-site.sh", "verify-base44-functions.sh", "fixlist-cloud-operator.sh"]) {
    fs.writeFileSync(path.join(scripts, name), "exit 0\n");
  }
  fs.writeFileSync(path.join(scripts, "lib/base44-pinned-cli.sh"), [
    "fixlist_install_base44_cli() { export FIXLIST_BASE44_CLI=pinned-cli; echo install; }",
    'fixlist_require_base44_owner() { [[ "$FIXLIST_BASE44_CLI" == pinned-cli ]] || exit 30; export TEST_AUTHENTICATED=true; echo authenticate; }',
  ].join("\n"));
  fs.writeFileSync(path.join(scripts, "deploy-base44-staged-functions.sh"), [
    "fixlist_assert_active_v9_intake_closed() {",
    '  [[ "$FIXLIST_BASE44_CLI" == pinned-cli && "$TEST_AUTHENTICATED" == true ]] || exit 31',
    "  echo probe",
    "  exit 42",
    "}",
  ].join("\n"));
  const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  git("init", "-q");
  git("add", ".");
  git("-c", "user.name=Pilot Test", "-c", "user.email=test@example.test", "commit", "-qm", "Seed publisher fixture");
  const sha = git("rev-parse", "HEAD");
  for (const inherited of [undefined, "/not/a/pinned/base44"]) {
    const env = {
      ...process.env, BASE44_APP_ID: "6a498732ec779dfaaeab0e53", BASE44_API_KEY: "",
      BASE44_EXPECTED_OWNER: "londonparisbrussels@gmail.com", SOURCE_SHA: sha, PUBLIC_BASELINE_SHA: sha,
      BARRIER_EXPECTED_GENERATION: "10", CONFIRM: "PUBLISH-BASE44-PILOT:" + sha + ":" + sha,
    };
    if (inherited === undefined) delete env.FIXLIST_BASE44_CLI;
    else env.FIXLIST_BASE44_CLI = inherited;
    delete env.TEST_AUTHENTICATED;
    const result = spawnSync("bash", [path.join(scripts, "deploy-base44-published-pilot.sh")],
      { cwd: root, encoding: "utf8", env, timeout: 8_000 });
    assert.equal(result.status, 42, result.stderr);
    assert.equal(result.stdout, "install\nauthenticate\nprobe\n");
  }
});
