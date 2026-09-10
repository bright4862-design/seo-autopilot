import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  OWNERSHIP_NOT_MANAGED,
  OWNERSHIP_OWNER_MANAGED,
  OWNERSHIP_UNANSWERED,
  ROBOTS_OBEYED_COPY,
  ROBOTS_OVERRIDE_COPY,
  SITE_OWNER_ATTESTATION_FIELD,
  isOwnerManaged,
  normalizeOwnershipAnswer,
  ownerManagedRobotsPolicy,
  ownershipHelpText,
  ownershipOnSiteChange,
  projectAttestationUpdate,
  readSiteOwnership,
  resolveScanOwnership,
  scanRunOwnership,
  scanSpecForOwnership,
  siteOwnershipStorageKey,
  writeSiteOwnership,
} from "../../src/lib/siteOwnershipPolicy.js";
import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";

const WAF_TITLE = "Your site's security service is blocking FixList.";
const WAF_ACTION = "Temporarily allow FixList in your firewall/bot protection, then Rescan.";

class MemoryStorage {
  constructor(seed = {}) { this.map = new Map(Object.entries(seed)); }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
}

function withStorage(store, run) {
  const had = Object.prototype.hasOwnProperty.call(globalThis, "localStorage");
  const previous = had ? globalThis.localStorage : undefined;
  Object.defineProperty(globalThis, "localStorage", { value: store, configurable: true, writable: true });
  try { return run(); }
  finally {
    if (had) Object.defineProperty(globalThis, "localStorage", { value: previous, configurable: true, writable: true });
    else delete globalThis.localStorage;
  }
}

test("ownership has one canonical closed-set representation", () => {
  assert.equal(normalizeOwnershipAnswer(" owner_or_manager "), OWNERSHIP_OWNER_MANAGED);
  assert.equal(normalizeOwnershipAnswer("not_owner"), OWNERSHIP_NOT_MANAGED);
  for (const value of [undefined, null, "", "yes", "owner", true, 1, {}]) {
    assert.equal(normalizeOwnershipAnswer(value), OWNERSHIP_UNANSWERED);
    assert.equal(isOwnerManaged(value), false);
  }
});

test("owner intent requests only the narrow robots.txt override", () => {
  assert.deepEqual(ownerManagedRobotsPolicy(OWNERSHIP_OWNER_MANAGED), {
    respect_robots_txt: false,
    owner_attested_robots_override: true,
    owner_managed_site: true,
    robots_policy: "owner_managed",
    site_ownership_answer: OWNERSHIP_OWNER_MANAGED,
    site_ownership_policy_version: "site_ownership_policy_v3_owner_robots_override",
  });
  assert.deepEqual(ownerManagedRobotsPolicy(OWNERSHIP_NOT_MANAGED), {
    respect_robots_txt: true,
    owner_attested_robots_override: false,
    owner_managed_site: false,
    robots_policy: "public_crawler",
    site_ownership_answer: OWNERSHIP_NOT_MANAGED,
    site_ownership_policy_version: "site_ownership_policy_v3_owner_robots_override",
  });
  assert.equal(ownerManagedRobotsPolicy(OWNERSHIP_UNANSWERED).respect_robots_txt, true);
  assert.equal(ownerManagedRobotsPolicy(OWNERSHIP_UNANSWERED).owner_attested_robots_override, false);
});

test("customer copy stays truthful for both robots policies", () => {
  assert.equal(ownershipHelpText(OWNERSHIP_NOT_MANAGED), ROBOTS_OBEYED_COPY.help);
  assert.equal(scanSpecForOwnership(OWNERSHIP_NOT_MANAGED), ROBOTS_OBEYED_COPY.spec);
  assert.match(ROBOTS_OBEYED_COPY.spec, /respects robots\.txt/);
  assert.equal(ownershipHelpText(OWNERSHIP_OWNER_MANAGED), ROBOTS_OVERRIDE_COPY.help);
  assert.equal(scanSpecForOwnership(OWNERSHIP_OWNER_MANAGED), ROBOTS_OVERRIDE_COPY.spec);
  assert.match(ROBOTS_OVERRIDE_COPY.help, /ignore robots\.txt/i);
  assert.match(ROBOTS_OVERRIDE_COPY.help, /does not bypass logins, firewalls, bot challenges, or rate limits/i);
  assert.doesNotMatch(ROBOTS_OVERRIDE_COPY.spec, /respects robots\.txt/i);
});

test("BusinessProject carries the durable attestation enum", () => {
  const schema = JSON.parse(readFileSync("base44/entities/BusinessProject.jsonc", "utf8"));
  assert.deepEqual(schema.properties[SITE_OWNER_ATTESTATION_FIELD].enum, [
    OWNERSHIP_OWNER_MANAGED,
    OWNERSHIP_NOT_MANAGED,
  ]);
});

test("project persistence is available before Standard 150 admission", () => {
  const activeProject = readFileSync("src/lib/activeProject.js", "utf8");
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  assert.match(activeProject, /siteOwnerAttestation = ""/);
  assert.match(activeProject, /normalizeOwnershipAnswer\(siteOwnerAttestation\)/);
  assert.match(activeProject, /site_owner_attestation: normalizedAttestation/);
  assert.match(form, /projectAttestationUpdate\(scanProject, siteOwnership\)/);
  const projectWrite = form.indexOf("base44.entities.BusinessProject.update(scanProject.id, attestation)");
  const admission = form.indexOf("submitStandardScanJob(scanPayload)");
  assert.ok(projectWrite >= 0 && admission > projectWrite, "project attestation must be written before admission");
});

test("project attestation updates only on a canonical change", () => {
  assert.deepEqual(projectAttestationUpdate({}, OWNERSHIP_OWNER_MANAGED), {
    site_owner_attestation: OWNERSHIP_OWNER_MANAGED,
  });
  assert.equal(projectAttestationUpdate({ site_owner_attestation: OWNERSHIP_OWNER_MANAGED }, OWNERSHIP_OWNER_MANAGED), null);
  assert.equal(projectAttestationUpdate({}, OWNERSHIP_UNANSWERED), null);
});

test("ownership is remembered per normalized website", () => {
  const keys = [
    "https://example.com",
    "https://www.example.com",
    "http://example.com/path",
    "example.com",
  ].map(siteOwnershipStorageKey);
  assert.equal(new Set(keys).size, 1);
  withStorage(new MemoryStorage(), () => {
    writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED);
    writeSiteOwnership("https://other.example", OWNERSHIP_NOT_MANAGED);
    assert.equal(readSiteOwnership("https://www.example.com/path"), OWNERSHIP_OWNER_MANAGED);
    assert.equal(readSiteOwnership("https://other.example"), OWNERSHIP_NOT_MANAGED);
  });
});

test("an answer made before a URL is typed can be carried to that first site", () => {
  assert.deepEqual(ownershipOnSiteChange({
    hadNoSite: true,
    pendingAnswer: OWNERSHIP_OWNER_MANAGED,
    storedAnswer: OWNERSHIP_UNANSWERED,
  }), { carry: true, answer: OWNERSHIP_OWNER_MANAGED });
  assert.deepEqual(ownershipOnSiteChange({
    hadNoSite: false,
    pendingAnswer: OWNERSHIP_OWNER_MANAGED,
    storedAnswer: OWNERSHIP_UNANSWERED,
  }), { carry: false, answer: OWNERSHIP_UNANSWERED });
});

test("historical presentation prefers the ScanRun policy over browser state", () => {
  const ownerRun = { owner_attested_robots_override: true, site_ownership_answer: OWNERSHIP_NOT_MANAGED };
  const nonOwnerRun = { owner_attested_robots_override: false, site_ownership_answer: OWNERSHIP_OWNER_MANAGED };
  assert.equal(scanRunOwnership(ownerRun), OWNERSHIP_OWNER_MANAGED);
  assert.equal(scanRunOwnership(nonOwnerRun), OWNERSHIP_NOT_MANAGED);
  assert.equal(resolveScanOwnership(ownerRun, OWNERSHIP_NOT_MANAGED), OWNERSHIP_OWNER_MANAGED);
  assert.equal(resolveScanOwnership(nonOwnerRun, OWNERSHIP_OWNER_MANAGED), OWNERSHIP_NOT_MANAGED);
});

test("only access-limited owner scans get the firewall recovery message", () => {
  const blocked = { status: "limited", coverage_state: "access_limited" };
  const owner = durableScanStatePresentation(blocked, { ownership: OWNERSHIP_OWNER_MANAGED });
  assert.equal(owner.kind, "security_service_blocked");
  assert.equal(owner.title, WAF_TITLE);
  assert.equal(owner.nextStep, WAF_ACTION);
  const visitor = durableScanStatePresentation(blocked, { ownership: OWNERSHIP_NOT_MANAGED });
  assert.equal(visitor.kind, "access_limited");
  assert.notEqual(visitor.title, WAF_TITLE);
  for (const record of [
    { status: "failed", error_code: "authority_write_failed" },
    { status: "failed", status_detail: "heartbeat missing for 4 minutes" },
    { status: "limited", coverage_state: "too_few_usable_pages" },
    { status: "failed", error_code: "scanner_wall_timeout" },
  ]) {
    assert.notEqual(durableScanStatePresentation(record, { ownership: OWNERSHIP_OWNER_MANAGED }).kind, "security_service_blocked");
  }
});

test("the form asks explicitly before scanning and sends policy intent", () => {
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  assert.match(form, /Do you own or manage this website\?/);
  assert.match(form, /OWNERSHIP_OWNER_MANAGED/);
  assert.match(form, /OWNERSHIP_NOT_MANAGED/);
  assert.match(form, /\.\.\.ownerManagedRobotsPolicy\(siteOwnership\)/);
});
