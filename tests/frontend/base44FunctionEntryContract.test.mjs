import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import test from "node:test";

// Base44 deploys base44/functions/{name}/entry.ts and nothing else. A function
// whose function.jsonc points anywhere else is accepted by `base44 functions
// deploy` and by inventory verification, but the live router then answers
// `404 user worker not found` for it.
//
// That is not hypothetical. On 2026-08-29, five of the nine canonical
// functions declared "entry": "index.ts" and every one of them 404'd in
// production while all four entry.ts functions served their own responses.
// durableScanWorkerControl and persistDurableScanAuthority are the durable
// worker's control and persistence handoff, so a Standard 150 scan admitted
// correctly, dispatched correctly, and then sat at status=queued forever with
// no way to terminalize.
//
// Inventory verification could not see it: the functions existed, they were
// simply unroutable. This asserts the deployable shape instead.
const FUNCTIONS_DIR = "base44/functions";

// Two functions carry the same defect and are deliberately not repaired here.
// Both are knowingly 404 today; each exemption must be removed by the change
// that puts the function on a live path, or that change ships a dead endpoint.
//
//   grokChat             Grok is not part of the Standard 150 beta. Billing
//                        lists it "Coming soon" and publicBetaSurface asserts
//                        the navigation never advertises it.
//   persistScanAuthority Superseded by persistDurableScanAuthority, which is
//                        what the worker actually calls (scan_job.py). It has
//                        no callers anywhere in the tree.
const KNOWN_UNROUTED = new Set(["grokChat", "persistScanAuthority"]);

function functionDirectories() {
  return readdirSync(FUNCTIONS_DIR, { withFileTypes: true })
    .filter((item) => item.isDirectory())
    .map((item) => item.name)
    .filter((name) => existsSync(`${FUNCTIONS_DIR}/${name}/function.jsonc`))
    .filter((name) => !KNOWN_UNROUTED.has(name));
}

test("every Base44 function declares entry.ts and ships that file", () => {
  const directories = functionDirectories();
  assert.ok(directories.length > 0, "no Base44 function packages were found");

  for (const name of directories) {
    const root = `${FUNCTIONS_DIR}/${name}`;
    const config = readFileSync(`${root}/function.jsonc`, "utf8");
    const declared = config.match(/"entry"\s*:\s*"([^"]+)"/)?.[1];

    assert.equal(
      declared,
      "entry.ts",
      `${name}/function.jsonc declares "${declared}"; Base44 only deploys entry.ts, so the live route would 404`,
    );
    assert.ok(
      existsSync(`${root}/entry.ts`),
      `${name} declares entry.ts but does not ship one`,
    );
  }
});

test("a function keeping its handler in index.ts imports it from entry.ts", () => {
  for (const name of functionDirectories()) {
    const root = `${FUNCTIONS_DIR}/${name}`;
    if (!existsSync(`${root}/index.ts`)) continue;

    // entry.ts is the only file deployed, so an index.ts handler reaches the
    // runtime solely by being imported for its side effects.
    assert.match(
      readFileSync(`${root}/entry.ts`, "utf8"),
      /import\s+["']\.\/index\.ts["']/,
      `${name}/entry.ts must import ./index.ts or the handler is never deployed`,
    );
  }
});
