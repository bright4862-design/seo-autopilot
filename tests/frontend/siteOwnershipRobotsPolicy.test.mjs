import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  OWNERSHIP_NOT_MANAGED,
  OWNERSHIP_OWNER_MANAGED,
  OWNERSHIP_UNANSWERED,
  isOwnerManaged,
  normalizeOwnershipAnswer,
  ROBOTS_OBEYED_COPY,
  ownerManagedRobotsPolicy,
  helpTextForPolicy,
  ownershipHelpText,
  ownershipOnSiteChange,
  readSiteOwnership,
  submissionObeysRobots,
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

test("the submitted pair matches the server's attestation contract", () => {
  // The scanner API pairs the two fields and rejects them when they disagree:
  // owner_attested_robots_override must be true exactly when
  // respect_robots_txt is false. Sending a mismatched pair is a 400, so this
  // reads the live guard rather than trusting a remembered one -- an earlier
  // revision of this patch was written against a hard "must be true" rule that
  // main has since replaced, and asserted a premise that had already moved.
  const api = readFileSync("scanner-api/app/main.py", "utf8");
  assert.match(
    api,
    /owner_robots_override != \(payload\.respect_robots_txt is False\)/,
    "the server's pairing guard must still exist for this test to mean anything",
  );

  for (const answer of [OWNERSHIP_OWNER_MANAGED, OWNERSHIP_NOT_MANAGED, OWNERSHIP_UNANSWERED, "nonsense"]) {
    const policy = ownerManagedRobotsPolicy(answer);
    assert.equal(
      policy.owner_attested_robots_override,
      policy.respect_robots_txt === false,
      `${answer || "(unanswered)"} must submit a pair the server accepts`,
    );
  }
});

test("no browser answer alone asks for a robots.txt override", () => {
  // The override may only be honoured against durable owned state. Until
  // BusinessProject.site_owner_attestation exists, a radio button in a browser
  // is not an attestation, and the frontend must not spend one.
  const entity = readFileSync("base44/entities/BusinessProject.jsonc", "utf8");
  const durableAttestationExists = /site_owner_attestation/.test(entity);
  if (!durableAttestationExists) {
    for (const answer of [OWNERSHIP_OWNER_MANAGED, OWNERSHIP_NOT_MANAGED, OWNERSHIP_UNANSWERED]) {
      assert.equal(ownerManagedRobotsPolicy(answer).owner_attested_robots_override, false, String(answer));
      assert.equal(ownerManagedRobotsPolicy(answer).respect_robots_txt, true, String(answer));
    }
  }
});

test("the robots promise cannot outlive the behaviour", () => {
  // The failure this prevents: the crawl starts overriding robots.txt while the
  // form still tells the customer it "does not change how the site is scanned".
  // Both sentences are downstream of submissionObeysRobots, and this fails the
  // moment they disagree.
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  // The literal stays in the form because three other contract tests assert the
  // customer sees this exact line. Equality here is what keeps the two in step.
  const specLiteral = form.match(/const SCAN_SPEC_LINE = "([^"]+)"/)?.[1];
  assert.equal(specLiteral, ROBOTS_OBEYED_COPY.spec,
    "the form's scan spec line and the policy's copy must not drift apart");
  assert.match(form, /\{ownershipHelpText\(siteOwnership\)\}/,
    "the help text must be derived per answer");

  for (const answer of [OWNERSHIP_OWNER_MANAGED, OWNERSHIP_NOT_MANAGED, OWNERSHIP_UNANSWERED]) {
    const obeys = submissionObeysRobots(answer);
    assert.equal(
      ownershipHelpText(answer) === ROBOTS_OBEYED_COPY.help,
      obeys,
      `${answer || "(unanswered)"}: the "does not change how the site is scanned" promise must track the policy`,
    );
    if (obeys) assert.match(ROBOTS_OBEYED_COPY.spec, /respects robots\.txt/);
  }

  // Every policy today obeys robots.txt, so the assertions above cannot reach
  // the withholding branch and would pass against copy that never checks. Drive
  // the branch directly with the policy the backend override will produce.
  assert.equal(
    helpTextForPolicy({ respect_robots_txt: true, owner_attested_robots_override: false }),
    ROBOTS_OBEYED_COPY.help,
  );
  for (const overriding of [
    { respect_robots_txt: false, owner_attested_robots_override: true },
    { respect_robots_txt: false, owner_attested_robots_override: false },
    { respect_robots_txt: true, owner_attested_robots_override: true },
  ]) {
    assert.equal(
      helpTextForPolicy(overriding),
      "",
      `a scan that no longer plainly obeys robots.txt must not claim it does: ${JSON.stringify(overriding)}`,
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

test("an answer given before the URL is typed is not thrown away", () => {
  // The form asks the question whether or not a URL is present, but storage is
  // keyed on the host, so an early answer has nowhere to go. Reading storage
  // for the newly typed site then cleared the selection the customer had just
  // made -- they answered, and it vanished as they finished the URL field.
  const early = ownershipOnSiteChange({
    hadNoSite: true, pendingAnswer: OWNERSHIP_OWNER_MANAGED, storedAnswer: OWNERSHIP_UNANSWERED,
  });
  assert.deepEqual(early, { carry: true, answer: OWNERSHIP_OWNER_MANAGED });

  // Whatever that site already knows about itself still wins: that answer was
  // given while looking at the site, this one before the site was known.
  assert.deepEqual(
    ownershipOnSiteChange({
      hadNoSite: true, pendingAnswer: OWNERSHIP_OWNER_MANAGED, storedAnswer: OWNERSHIP_NOT_MANAGED,
    }),
    { carry: false, answer: OWNERSHIP_NOT_MANAGED },
  );

  // Moving between two real sites reads the new one; nothing is carried across.
  assert.deepEqual(
    ownershipOnSiteChange({
      hadNoSite: false, pendingAnswer: OWNERSHIP_OWNER_MANAGED, storedAnswer: OWNERSHIP_UNANSWERED,
    }),
    { carry: false, answer: OWNERSHIP_UNANSWERED },
  );
  assert.deepEqual(
    ownershipOnSiteChange({
      hadNoSite: false, pendingAnswer: OWNERSHIP_OWNER_MANAGED, storedAnswer: OWNERSHIP_NOT_MANAGED,
    }),
    { carry: false, answer: OWNERSHIP_NOT_MANAGED },
  );

  // Nothing to carry, and junk never becomes an answer.
  assert.deepEqual(
    ownershipOnSiteChange({ hadNoSite: true, pendingAnswer: "", storedAnswer: "" }),
    { carry: false, answer: OWNERSHIP_UNANSWERED },
  );
  assert.deepEqual(
    ownershipOnSiteChange({ hadNoSite: true, pendingAnswer: "nonsense", storedAnswer: "" }),
    { carry: false, answer: OWNERSHIP_UNANSWERED },
  );
  assert.deepEqual(ownershipOnSiteChange(), { carry: false, answer: OWNERSHIP_UNANSWERED });
});

test("the form routes its site change through that decision", () => {
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  assert.match(form, /ownershipOnSiteChange\(\{ hadNoSite, pendingAnswer: siteOwnership, storedAnswer: stored \}\)/);
  assert.match(form, /if \(next\.carry\) writeSiteOwnership\(websiteUrl, next\.answer\);/);
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
