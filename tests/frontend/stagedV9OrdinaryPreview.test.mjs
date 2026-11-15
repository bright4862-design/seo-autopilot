import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { ORDINARY_RECEIPT_PATH, prepareOrdinaryReceiptEntry } from "../../scripts/lib/staged-v9-ordinary-preview.mjs";
import { allowsOrdinaryReceiptApi } from "../../scripts/preview-base44-v9.mjs";
import routes from "../../data/generated-staged-v9-routes.json" with { type: "json" };

test("receipt mode forwards reads and the exact generated result POST", () => {
  const app = "/api/apps/6a498732ec779dfaaeab0e53";
  const result = app + "/functions/" + routes.functions.getCustomerScanResultV9.route_name;
  const launch = app + "/functions/" + routes.functions.startStandardScanJobV9.route_name;
  assert.equal(allowsOrdinaryReceiptApi(app + "/entities/User/me", "GET"), true);
  assert.equal(allowsOrdinaryReceiptApi(result, "POST"), true);
  for (const blocked of [launch, app + "/functions/getCustomerScanResultV9", app + "/analytics/track/batch"]) {
    assert.equal(allowsOrdinaryReceiptApi(blocked, "POST"), false);
  }
  assert.equal(allowsOrdinaryReceiptApi(app + "/entities/ScanRun/scan", "PUT"), false);
});

test("the loopback receipt page uses the app's existing client and starts readback only on a click", async t => {
  const directory = await mkdtemp(join(tmpdir(), "fixlist-receipt-preview-"));
  t.after(() => rm(directory, { force: true, recursive: true }));
  const verifierModule = "export async function verifyOrdinaryStaged500Readback(client) { return client.read(); }";
  const page = await prepareOrdinaryReceiptEntry(directory, verifierModule);
  assert.equal(page, join(directory, ORDINARY_RECEIPT_PATH.slice(1)));
  const html = await readFile(page, "utf8");
  assert.match(html, /<a href="\/">Open FixList preview<\/a>/);
  assert.match(html, /id="verify" type="button" disabled/);
  assert.match(html, /name="referrer" content="no-referrer"/);
  assert.equal(await readFile(join(directory, "ordinary-receipt-verifier.js"), "utf8"), verifierModule);
  const entry = await readFile(join(directory, "ordinary-receipt-entry.js"), "utf8");
  assert.match(entry, /import \{ base44 \} from "\.\/src\/api\/base44Client\.js"/);
  assert.match(entry, /import \{ verifyOrdinaryStaged500Readback \} from "\.\/ordinary-receipt-verifier\.js"/);
  assert.doesNotMatch(entry, /localStorage|Authorization|fetch\(/);

  const button = () => ({
    addEventListener(event, handler) {
      assert.equal(event, "click");
      this.click = handler;
    },
  });
  const controls = { verify: button(), download: button(), status: {} };
  const link = { click() { assert.equal(this.href, "blob:fixture"); } };
  const document = { getElementById: id => controls[id], createElement: () => link };
  const appClient = {};
  const report = { terminal_outcome_verified: true, scan_id: "fixture_scan" };
  let calls = 0;
  let downloaded;
  const verifier = async client => { assert.equal(client, appClient); calls++; return report; };
  const url = {
    createObjectURL(blob) { downloaded = blob; return "blob:fixture"; },
    revokeObjectURL(value) { assert.equal(value, "blob:fixture"); },
  };
  const run = new Function("document", "URL", "Blob", "setTimeout", "base44", "verifyOrdinaryStaged500Readback",
    entry.replace(/^import .*;$/gm, ""));
  run(document, url, Blob, callback => callback(), appClient, verifier);
  assert.equal(calls, 0);
  assert.equal(controls.verify.disabled, false);
  await controls.verify.click();
  assert.equal(calls, 1);
  assert.equal(controls.status.textContent, "Saved scan verified.");
  assert.equal(controls.download.hidden, false);
  controls.download.click();
  assert.equal(link.download, "fixlist-standard500-receipt.json");
  assert.deepEqual(JSON.parse(await downloaded.text()), report);
});
