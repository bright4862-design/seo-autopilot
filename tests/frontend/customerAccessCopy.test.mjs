import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const customerFiles = [
  "src/pages/Landing.jsx",
  "src/pages/Billing.jsx",
  "src/components/scan/ScanWebsiteForm.jsx",
  "src/pages/FixList.jsx",
  "src/lib/checkout.js",
];

test("customer-facing Standard 150 access no longer uses beta invitation language", () => {
  const source = customerFiles.map((path) => readFileSync(path, "utf8")).join("\n");
  assert.doesNotMatch(
    source,
    /Get beta access|Standard 150 beta|beta access|beta pass|invite-only|beta cohort|New beta scans/i,
  );
});
