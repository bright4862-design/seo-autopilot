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

function commitFixture(root) {
  const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  git("init", "-q");
  git("add", ".");
  git("-c", "user.name=Pilot Test", "-c", "user.email=test@example.test", "commit", "-qm", "Seed publisher fixture");
  return git("rev-parse", "HEAD");
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
  const sha = commitFixture(root);
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

test("the publisher restores stripped routes before rejecting extra aliases and can recover again from the saved snapshot", t => {
  const root = project(t);
  const provider = project(t);
  const remote = path.join(provider, "base44/functions");
  const calls = path.join(provider, "calls");
  const snapshot = path.join(project(t), "pilot-snapshot");
  writeFunction(provider, "launcherV8");
  writeFunction(provider, "readerV9B0000");
  fs.mkdirSync(path.join(root, "scripts/lib"), { recursive: true });
  fs.mkdirSync(path.join(root, "data"));
  for (const file of ["scripts/deploy-base44-published-pilot.sh", "scripts/lib/base44-pilot-inventory.mjs"]) {
    fs.copyFileSync(new URL("../../" + file, import.meta.url), path.join(root, file));
  }
  fs.writeFileSync(path.join(root, "data/base44-function-routes.json"),
    JSON.stringify({ generation: "v8", candidate_routes: { v9: {} } }));
  fs.writeFileSync(path.join(root, "data/beta-crawler-revision.json"), JSON.stringify({ status: "candidate" }));
  fs.writeFileSync(path.join(root, "scripts/lib/base44-public-routes.mjs"), 'console.log("v8 launcherV8");');
  fs.writeFileSync(path.join(root, "scripts/generate_release_contracts.mjs"), "");
  fs.writeFileSync(path.join(root, "scripts/verify-base44-site.sh"), "exit 0\n");
  fs.writeFileSync(path.join(root, "scripts/verify-base44-functions.sh"), [
    'test -f "$TEST_PROVIDER/base44/functions/launcherV8/entry.ts"',
    'printf "verified-v8\\n" >> "$TEST_CALLS"',
  ].join("\n"));
  fs.writeFileSync(path.join(root, "scripts/fixlist-cloud-operator.sh"), [
    'test "$BARRIER_EXPECTED_PRIOR_MODE" = closed',
    'printf "drain:%s\\n" "$FIXLIST_DRAIN_READBACK_SOURCE_GUARD" >> "$TEST_CALLS"',
  ].join("\n"));
  fs.writeFileSync(path.join(root, "scripts/lib/release-source-guard.sh"), [
    'fixlist_require_exact_main() { [[ "$TEST_MAIN_MOVED" != yes ]]; }',
    'fixlist_require_pinned_checkout() { true; }',
    'fixlist_require_merged_checkout() { printf "merged-source\\n" >> "$TEST_CALLS"; }',
  ].join("\n"));
  fs.writeFileSync(path.join(root, "scripts/lib/base44-pinned-cli.sh"), [
    'fixlist_install_base44_cli() { export FIXLIST_BASE44_CLI="$TEST_PROVIDER/base44-cli"; }',
    "fixlist_require_base44_owner() { true; }",
  ].join("\n"));
  fs.writeFileSync(path.join(root, "scripts/deploy-base44-staged-functions.sh"), [
    'fixlist_assert_active_v9_intake_closed() { printf "intake-closed\\n" >> "$TEST_CALLS"; }',
    'fixlist_publish_v9_packages() { [[ "$1" == verify-pinned ]] && printf "verified-v9\\n" >> "$TEST_CALLS"; }',
  ].join("\n"));
  fs.writeFileSync(path.join(provider, "npm"), "#!/usr/bin/env bash\nexit 0\n", { mode: 0o700 });
  fs.writeFileSync(path.join(provider, "base44-cli"), `#!${process.execPath}
const fs = require("node:fs");
const path = require("node:path");
const [group, command, ...names] = process.argv.slice(4);
const remote = ${JSON.stringify(remote)};
const failOnce = path.join(process.env.TEST_PROVIDER, "failed-pull");
const log = (...parts) => fs.appendFileSync(process.env.TEST_CALLS, parts.join(" ") + "\\n");
if (group === "site" && command === "deploy") {
  fs.rmSync(path.join(remote, "launcherV8"), { recursive: true });
  fs.cpSync(path.join(remote, "readerV9B0000"), path.join(remote, "addedAlias"), { recursive: true });
  fs.writeFileSync(path.join(remote, "addedAlias/function.jsonc"), '{"name":"addedAlias","entry":"entry.ts"}');
  fs.writeFileSync(failOnce, "");
} else if (group === "functions" && command === "list") {
  console.log(fs.readdirSync(remote).sort().map(name => "  " + name).join("\\n"));
} else if (group === "functions" && command === "pull") {
  if (fs.existsSync(failOnce)) { fs.unlinkSync(failOnce); process.exit(5); }
  fs.cpSync(remote, "base44/functions", { recursive: true });
} else if (group === "functions" && command === "deploy") {
  log(group, command, ...names);
  for (const name of names) fs.cpSync(path.join("base44/functions", name), path.join(remote, name), { recursive: true });
} else process.exit(6);
`, { mode: 0o700 });

  const sha = commitFixture(root);
  const env = {
    ...process.env, PATH: provider + ":" + process.env.PATH,
    BASE44_APP_ID: "6a498732ec779dfaaeab0e53", BASE44_API_KEY: "",
    BASE44_EXPECTED_OWNER: "londonparisbrussels@gmail.com", SOURCE_SHA: sha, PUBLIC_BASELINE_SHA: sha,
    BARRIER_EXPECTED_GENERATION: "10", PILOT_SNAPSHOT_DIR: snapshot, TEST_PROVIDER: provider,
    TEST_CALLS: calls, TEST_MAIN_MOVED: "no",
  };
  const run = (operation, confirm, extra = {}) => spawnSync("bash",
    [path.join(root, "scripts/deploy-base44-published-pilot.sh"), operation],
    { cwd: root, encoding: "utf8", timeout: 15_000, env: { ...env, CONFIRM: confirm, ...extra } });
  const initial = run("publish", `PUBLISH-BASE44-PILOT:${sha}:${sha}`);
  assert.equal(initial.status, 2, initial.stderr);
  assert.match(initial.stderr, /Function inventory read failed on attempt 1/);
  assert.match(initial.stderr, /Unexpected registered Base44 functions: addedAlias/);
  assert.match(fs.readFileSync(calls, "utf8"), /functions deploy launcherV8\nverified-v8\nverified-v9\nintake-closed/);
  assert.equal(fs.existsSync(path.join(remote, "addedAlias")), true);
  assert.equal(fs.statSync(snapshot).mode & 0o077, 0);

  fs.rmSync(path.join(remote, "addedAlias"), { recursive: true });
  fs.rmSync(path.join(remote, "launcherV8"), { recursive: true });
  const restored = run("restore-snapshot", `RESTORE-BASE44-PILOT:${sha}:${sha}:10`, { TEST_MAIN_MOVED: "yes" });
  assert.equal(restored.status, 0, restored.stderr);
  assert.match(restored.stdout, /BASE44_PILOT_SNAPSHOT_RESTORED/);
  assert.match(fs.readFileSync(calls, "utf8"), /merged-source[\s\S]*functions deploy launcherV8/);
  const actualDigests = captureFunctionInventory(provider, "  launcherV8\n  readerV9B0000\n");
  assert.deepEqual({ ...actualDigests }, JSON.parse(fs.readFileSync(path.join(snapshot, "before/digests.json"), "utf8")));

  fs.appendFileSync(path.join(snapshot, "restore/base44/functions/launcherV8/entry.ts"), "\n// modified archive");
  const beforeRejectedRecovery = fs.readFileSync(calls, "utf8");
  const rejected = run("restore-snapshot", `RESTORE-BASE44-PILOT:${sha}:${sha}:10`);
  assert.equal(rejected.status, 2, rejected.stderr);
  assert.match(rejected.stderr, /recovery copy does not match its saved inventory/);
  assert.equal(fs.readFileSync(calls, "utf8"), beforeRejectedRecovery + "merged-source\n");
});
