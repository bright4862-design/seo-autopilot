import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const activeProject = readFileSync("src/lib/activeProject.js", "utf8");
const projectSchema = JSON.parse(readFileSync("base44/entities/BusinessProject.jsonc", "utf8"));
const startV3 = readFileSync("base44/functions/startStandardScanJobV3/entry.ts", "utf8");
const gateway = readFileSync("dispatch-gateway/main.py", "utf8");
const scannerMain = readFileSync("scanner-api/app/main.py", "utf8");
const robotsPolicy = readFileSync("scanner-api/app/robots_policy.py", "utf8");

test("first Standard 150 scan asks whether the customer owns or manages the site", () => {
  assert.match(scanForm, /Do you own or manage this website\?/);
  assert.match(scanForm, /owner_or_manager/);
  assert.match(scanForm, /not_owner/);
  assert.match(scanForm, /Choose whether you own or manage this website before starting the scan/);
});

test("site-owner attestation is durable on the website project", () => {
  assert.deepEqual(projectSchema.properties.site_owner_attestation.enum, ["owner_or_manager", "not_owner"]);
  assert.match(activeProject, /siteOwnerAttestation/);
  assert.match(activeProject, /site_owner_attestation/);
  assert.match(activeProject, /BusinessProject\.update\([\s\S]*site_owner_attestation/);
});

test("owner-managed scans request the narrow robots.txt override while other scans still respect robots", () => {
  assert.match(scanForm, /const respectRobotsTxt = ownerAttestation !== "owner_or_manager"/);
  assert.match(scanForm, /respect_robots_txt: respectRobotsTxt/);
  assert.match(scanForm, /owner_attested_robots_override: !respectRobotsTxt/);
  assert.doesNotMatch(scanForm, /respect_robots_txt: false,/);
});

test("server and gateway require explicit owner attestation before allowing robots.txt override", () => {
  assert.match(startV3, /owner_attested_robots_override/);
  assert.match(startV3, /site_owner_attestation/);
  assert.match(gateway, /owner_attested_robots_override/);
  assert.match(scannerMain, /owner_attested_robots_override/);
});

test("FixList crawler identifies itself", () => {
  assert.match(robotsPolicy, /SCANNER_USER_AGENT\s*=\s*"FixListBot\/1\.0 \(\+https:\/\/getfixlist\.com\/crawler\)"/);
});

test("security-service blocks give the owner one clear recovery action", () => {
  const presentation = durableScanStatePresentation({
    status: "failed",
    coverage_state: "access_limited",
    error_code: "scan_access_limited",
  });
  assert.equal(presentation.title, "Your site’s security service is blocking FixList.");
  assert.equal(
    presentation.nextStep,
    "Temporarily allow FixList in your firewall or bot protection, then run the scan again.",
  );
});
