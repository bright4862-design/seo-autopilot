import { writeFile } from "node:fs/promises";
import { join } from "node:path";

export const ORDINARY_RECEIPT_PATH = "/ordinary-500-receipt.html";

export async function prepareOrdinaryReceiptEntry(directory, verifierModule) {
  const page = join(directory, ORDINARY_RECEIPT_PATH.slice(1));
  await Promise.all([
    writeFile(page, `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>FixList Standard 500 receipt</title>
<main>
  <h1>Standard 500 receipt</h1>
  <p><a href="/">Open FixList preview</a> to sign in as the approved pilot account.</p>
  <button id="verify" type="button" disabled>Verify saved scan</button>
  <button id="download" type="button" hidden>Download receipt</button>
  <p id="status" role="status"></p>
</main>
<script type="module" src="/ordinary-receipt-entry.js"></script>
</html>
`, { flag: "wx", mode: 0o600 }),
    writeFile(join(directory, "ordinary-receipt-verifier.js"), verifierModule, { flag: "wx", mode: 0o600 }),
    writeFile(join(directory, "ordinary-receipt-entry.js"), `
import { base44 } from "./src/api/base44Client.js";
import { verifyOrdinaryStaged500Readback } from "./ordinary-receipt-verifier.js";
const verify = document.getElementById("verify");
const download = document.getElementById("download");
const status = document.getElementById("status");
let report;

verify.addEventListener("click", async () => {
  verify.disabled = true;
  download.hidden = true;
  status.textContent = "Reading saved scan…";
  try {
    report = await verifyOrdinaryStaged500Readback(base44);
    status.textContent = report.terminal_outcome_verified
      ? "Saved scan verified."
      : "Receipt blocked: " + report.failure_code;
    download.hidden = false;
  } catch {
    status.textContent = "Receipt could not be verified.";
  } finally {
    verify.disabled = false;
  }
});

download.addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\\n"], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "fixlist-standard500-receipt.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
});

verify.disabled = false;
`, { flag: "wx", mode: 0o600 }),
  ]);
  return page;
}
