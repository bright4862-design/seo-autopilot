import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  OWNERSHIP_NOT_MANAGED,
  OWNERSHIP_OWNER_MANAGED,
  OWNERSHIP_UNANSWERED,
  isOwnerManaged,
  normalizeOwnershipAnswer,
  ownerManagedRobotsPolicy,
  readSiteOwnership,
  siteOwnershipStorageKey,
  writeSiteOwnership,
} from "../../src/lib/siteOwnershipPolicy.js";
import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";

/** The exact copy this patch exists to put in front of a blocked owner. */
const WAF_TITLE = "Your site's security service is blocking FixList.";
const WAF_ACTION = "Temporarily allow FixList in your firewall/bot protection, then Rescan.";

class MemoryStorage {
  constructor(seed = {}) { this.map = new Map(Object.entries(seed)); }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
}

/** Storage that refuses every operation, as a private window does. */
class HostileStorage {
  getItem() { throw new Error("storage disabled"); }
  setItem() { throw new Error("storage disabled"); }
  removeItem() { throw new Error("storage disabled"); }
}

function withStorage(store, run) {
  const had = Object.prototype.hasOwnProperty.call(globalThis, "localStorage");
  const previous = had ? globalThis.localStorage : undefined;
  Object.defineProperty(globalThis, "localStorage", { value: store, configurable: true, writable: true });
  try {
    return run();
  } finally {
    if (had) Object.defineProperty(globalThis, "localStorage", { value: previous, configurable: true, writable: true });
    else delete globalThis.localStorage;
  }
}

// ------------------------------------------------------------- the policy --

test("both answers still tell the scanner to respect robots.txt", () => {
  // The scanner API rejects a Standard 150 submission whose respect_robots_txt
  // is not exactly true, on the admission path and again on dispatch. Sending
  // false for an owner would not widen their crawl, it would 400 their scan.
  // This is the single most important property in this patch.
  const api = readFileSync("scanner-api/app/main.py", "utf8");
  assert.equal(
    (api.match(/if payload\.respect_robots_txt is not True:/g) || []).length,
    2,
    "both server guards must still exist for this test to mean anything",
  );

  for (const answer of [OWNERSHIP_OWNER_MANAGED, OWNERSHIP_NOT_MANAGED, OWNERSHIP_UNANSWERED, "nonsense"]) {
    assert.equal(
      ownerManagedRobotsPolicy(answer).respect_robots_txt,
      true,
      `${answer || "(unanswered)"} must not loosen robots.txt`,
    );
  }
});

test("owner and non-owner submit different policy, same obedience", () => {
  const owner = ownerManagedRobotsPolicy(OWNERSHIP_OWNER_MANAGED);
  const visitor = ownerManagedRobotsPolicy(OWNERSHIP_NOT_MANAGED);

  assert.equal(owner.owner_managed_site, true);
  assert.equal(owner.robots_policy, "owner_managed");
  assert.equal(owner.site_ownership_answer, OWNERSHIP_OWNER_MANAGED);

  assert.equal(visitor.owner_managed_site, false);
  assert.equal(visitor.robots_policy, "public_crawler");
  assert.equal(visitor.site_ownership_answer, OWNERSHIP_NOT_MANAGED);

  assert.equal(owner.respect_robots_txt, visitor.respect_robots_txt);
});

test("an unanswered or unrecognised answer is treated as not-managed", () => {
  // Never assume ownership. Claiming it for someone who never said so is what
  // puts firewall instructions in front of a person scanning a competitor.
  for (const value of [undefined, null, "", "  ", "yes", "true", "owner", 1, {}]) {
    assert.equal(normalizeOwnershipAnswer(value), OWNERSHIP_UNANSWERED, String(value));
    assert.equal(isOwnerManaged(value), false, String(value));
    assert.equal(ownerManagedRobotsPolicy(value).owner_managed_site, false, String(value));
  }
});

// -------------------------------------------------------------- persistence --

test("an answer survives a reload of the same site", () => {
  withStorage(new MemoryStorage(), () => {
    assert.equal(readSiteOwnership("https://example.com"), OWNERSHIP_UNANSWERED);
    assert.equal(writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED), true);
    // A reload is a fresh read against the same storage.
    assert.equal(readSiteOwnership("https://example.com"), OWNERSHIP_OWNER_MANAGED);
  });
});

test("the answer is remembered per website, not globally", () => {
  withStorage(new MemoryStorage(), () => {
    writeSiteOwnership("https://mine.example", OWNERSHIP_OWNER_MANAGED);
    writeSiteOwnership("https://theirs.example", OWNERSHIP_NOT_MANAGED);

    assert.equal(readSiteOwnership("https://mine.example"), OWNERSHIP_OWNER_MANAGED);
    assert.equal(readSiteOwnership("https://theirs.example"), OWNERSHIP_NOT_MANAGED);
    assert.equal(readSiteOwnership("https://unseen.example"), OWNERSHIP_UNANSWERED);
  });
});

test("the same site is recognised across www, scheme and path", () => {
  // Someone who answers on example.com and comes back via www.example.com/pricing
  // is looking at the same site and must not be asked again.
  const keys = [
    "https://example.com",
    "https://www.example.com",
    "http://example.com/pricing",
    "example.com",
  ].map(siteOwnershipStorageKey);
  assert.equal(new Set(keys).size, 1, `expected one key, got ${JSON.stringify(keys)}`);

  withStorage(new MemoryStorage(), () => {
    writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED);
    assert.equal(readSiteOwnership("https://www.example.com/pricing"), OWNERSHIP_OWNER_MANAGED);
  });
});

test("changing the answer replaces it, and clearing it asks again", () => {
  withStorage(new MemoryStorage(), () => {
    writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED);
    writeSiteOwnership("https://example.com", OWNERSHIP_NOT_MANAGED);
    assert.equal(readSiteOwnership("https://example.com"), OWNERSHIP_NOT_MANAGED);

    // Clearing removes the row rather than storing a blank, so "no answer" and
    // "never asked" stay the same state.
    writeSiteOwnership("https://example.com", OWNERSHIP_UNANSWERED);
    assert.equal(readSiteOwnership("https://example.com"), OWNERSHIP_UNANSWERED);
  });
});

test("storage failures never reach the customer", () => {
  withStorage(new HostileStorage(), () => {
    assert.doesNotThrow(() => readSiteOwnership("https://example.com"));
    assert.doesNotThrow(() => writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED));
    assert.equal(readSiteOwnership("https://example.com"), OWNERSHIP_UNANSWERED);
    assert.equal(writeSiteOwnership("https://example.com", OWNERSHIP_OWNER_MANAGED), false);
  });

  // A site with no resolvable host has no key, and must not throw either.
  withStorage(new MemoryStorage(), () => {
    assert.equal(siteOwnershipStorageKey(""), "");
    assert.equal(writeSiteOwnership("", OWNERSHIP_OWNER_MANAGED), false);
    assert.equal(readSiteOwnership(""), OWNERSHIP_UNANSWERED);
  });
});

// ------------------------------------------------------------- the WAF state --

const BLOCKED_RECORD = { status: "limited", coverage_state: "access_limited" };

test("a blocked owner is told to allow FixList through and rescan", () => {
  const shown = durableScanStatePresentation(BLOCKED_RECORD, { ownership: OWNERSHIP_OWNER_MANAGED });
  assert.equal(shown.kind, "security_service_blocked");
  assert.equal(shown.title, WAF_TITLE);
  assert.equal(shown.nextStep, WAF_ACTION);
});

test("a blocked visitor is told to ask whoever runs the site", () => {
  // The owner copy would send them to a firewall they cannot open.
  const shown = durableScanStatePresentation(BLOCKED_RECORD, { ownership: OWNERSHIP_NOT_MANAGED });
  assert.equal(shown.kind, "access_limited");
  assert.notEqual(shown.title, WAF_TITLE);
  assert.match(shown.nextStep, /Ask whoever manages/);
});

test("an unanswered question keeps the visitor copy", () => {
  for (const ownership of [undefined, "", "nonsense"]) {
    const shown = durableScanStatePresentation(BLOCKED_RECORD, ...(ownership === undefined ? [] : [{ ownership }]));
    assert.equal(shown.kind, "access_limited", String(ownership));
  }
});

test("ownership only rewrites a block, never another failure", () => {
  // An owner whose result failed to save must not be sent to their firewall.
  const others = [
    ["save_failed", { status: "failed", error_code: "authority_write_failed" }],
    ["worker_stalled", { status: "failed", status_detail: "heartbeat missing for 4 minutes" }],
    ["too_few_usable_pages", { status: "limited", coverage_state: "no_usable_html" }],
    ["deadline_reached", { status: "limited", crawl_timing: { crawl_deadline_reached: true } }],
    ["unknown_limited", { status: "limited" }],
    ["cancelled", { status: "cancelled" }],
    ["no_results", { status: "complete" }],
  ];
  for (const [expected, record] of others) {
    const shown = durableScanStatePresentation(record, { ownership: OWNERSHIP_OWNER_MANAGED });
    assert.equal(shown.kind, expected, JSON.stringify(record));
    assert.notEqual(shown.title, WAF_TITLE, JSON.stringify(record));
  }
});

test("a running scan is unaffected by the ownership answer", () => {
  const running = { status: "crawling", started_at: new Date().toISOString() };
  const asOwner = durableScanStatePresentation(running, { ownership: OWNERSHIP_OWNER_MANAGED });
  const asVisitor = durableScanStatePresentation(running, { ownership: OWNERSHIP_NOT_MANAGED });
  assert.equal(asOwner.kind, "in_progress");
  assert.deepEqual(asOwner, asVisitor);
});

test("the blocked-owner copy carries no internal detail", () => {
  const shown = durableScanStatePresentation(BLOCKED_RECORD, { ownership: OWNERSHIP_OWNER_MANAGED });
  for (const line of [shown.title, shown.detail, shown.nextStep, shown.retryAdvice]) {
    assert.doesNotMatch(line, /http|worker|cloud ?run|revision|token|traceback|\b[0-9a-f]{16,}\b/i, line);
  }
});

// ------------------------------------------------------------------ wiring --

test("the scan form asks the question and submits one robots policy", () => {
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");

  // The question is rendered, not merely imported.
  assert.match(form, /<legend[^>]*>\{OWNERSHIP_QUESTION\}<\/legend>/);
  assert.match(form, /name="fixlist-site-ownership"/);
  assert.match(form, /onChange=\{\(\) => handleOwnershipChange\(answer\)\}/);

  // The answer is written on change, so a reload has something to restore.
  assert.match(form, /writeSiteOwnership\(websiteUrl, value\)/);

  // The payload takes its robots fields from one place. A second hard-coded
  // respect_robots_txt in the submission would silently outrank the policy
  // depending on key order.
  const payload = form.slice(form.indexOf("const scanPayload = {"), form.indexOf("// PRIMARY PATH"));
  assert.ok(payload.includes("...ownerManagedRobotsPolicy(siteOwnership)"), "payload must spread the policy");
  assert.doesNotMatch(payload, /respect_robots_txt:\s*(true|false)/, "payload must not hard-code robots obedience beside the policy");
});

test("the FixList page passes what the customer told us into the copy", () => {
  const page = readFileSync("src/pages/FixList.jsx", "utf8");
  assert.match(page, /ownership: readSiteOwnership\(scanRecord\.website_url\)/);
});
