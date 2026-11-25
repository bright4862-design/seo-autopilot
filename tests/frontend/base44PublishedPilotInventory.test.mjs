import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
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
