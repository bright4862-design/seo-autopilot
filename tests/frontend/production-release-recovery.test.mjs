import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const advanced = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");
const scannerForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
const scanRunModel = readFileSync("src/lib/scanRunModel.js", "utf8");
const persistence = readFileSync("base44/functions/persistDurableScanAuthority/index.ts", "utf8");

test("normal scans require Python and do not silently save Deno fallback", () => {
  assert.match(scannerForm, /require_python_scanner: true/);
  assert.match(scannerForm, /allow_deno_fallback: false/);
  assert.match(advanced, /did not save a fallback result/);
  assert.match(advanced, /python_scanner_failure_code/);
  assert.match(advanced, /release_gate_eligible: false/);
});

test("scan results route by exact durable scan ID without browser-result fallback", () => {
  assert.match(scannerForm, /scan_id: scanId/);
  assert.match(scannerForm, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
  assert.match(scannerForm, /submitLockRef\.current/);
  assert.match(scannerForm, /assertCurrentScanSession\(/);
  assert.doesNotMatch(scannerForm, /localStorage\.(?:getItem|setItem)/);
  assert.match(fixList, /searchParams\.get\("scan_id"\)/);
  assert.match(fixList, /getScanRunWithFixList\(requestedScanId\)/);
  assert.match(fixList, /normalizeDurableScanBundle\(durableBundle\)/);
  assert.match(fixList, /No other scan has been substituted/);
  assert.doesNotMatch(fixList, /readBestScanRecord|loaded_local|localStorage\.(?:getItem|setItem)/);
});

test("merged results preserve authoritative durable release markers", () => {
  assert.match(scannerForm, /const authorityMarkers = buildAuthorityMarkers\(scanData, aiData\)/);
  assert.match(scannerForm, /\.\.\.authorityMarkers/);
  assert.match(scanRunModel, /authority_proof/);
  assert.match(persistence, /authority_seal_version/);
  assert.match(scanRunModel, /release_gate_eligible/);
  assert.match(persistence, /persistedScan\?\.authority_proof === authorityProof/);
  assert.match(persistence, /persistedScan\?\.release_gate_eligible === true/);
});


test("a missed browser response recovers the durable saved result before failing", () => {
  assert.match(scannerForm, /getScanRunWithFixList/);
  assert.match(scannerForm, /async function recoverPersistedCompletion/);
  assert.match(scannerForm, /browser_recovered_saved_result/);
  const catchBlock = scannerForm.match(/const recoveredCompletion = scanId[\s\S]*?console\.error\("Website scan submission failed\.", err\);/)?.[0] || "";
  assert.ok(catchBlock, "durable recovery must run in the catch path");
  assert.ok(
    catchBlock.indexOf("recoverPersistedCompletion") < catchBlock.indexOf('console.error("Website scan submission failed.", err)'),
    "the durable reread must happen before the UI declares failure",
  );
  assert.match(catchBlock, /navigate\(`\/dashboard\?scan=complete&scan_id=/);
});

test("active result pages poll automatically until the saved FixList is ready", () => {
  assert.match(fixList, /ACTIVE_SCAN_RUN_STATUSES\.has\(String\(durableBundle\.run\.status/);
  assert.match(fixList, /setReloadToken\(\(value\) => value \+ 1\)/);
  assert.match(fixList, /}, 2500\);/);
  assert.match(fixList, /This page refreshes automatically/);
  assert.doesNotMatch(fixList, /Check back in a minute or run a fresh scan/);
});
