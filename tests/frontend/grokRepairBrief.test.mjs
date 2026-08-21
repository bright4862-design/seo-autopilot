import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { GROK_MAX_MESSAGE_LENGTH } from "../../src/lib/grokChat.js";
import {
  GROK_REPAIR_BRIEF_STORAGE_KEY,
  buildGrokRepairBrief,
  grokRepairBriefContext,
  stashGrokRepairBrief,
  takeGrokRepairBrief,
} from "../../src/lib/grokRepairBrief.js";
import { CUSTOMER_SESSION_STORAGE_KEYS } from "../../src/lib/customerBrowserCache.js";
import { repairSuggestion } from "../../src/lib/repairSuggestions.js";

const fixListSource = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const assistantSource = fs.readFileSync(new URL("../../src/pages/Assistant.jsx", import.meta.url), "utf8");
const suggestedFixSource = fs.readFileSync(
  new URL("../../src/components/fixlist/SuggestedFix.jsx", import.meta.url),
  "utf8",
);

class MemoryStorage {
  constructor(values = {}) { this.values = { ...values }; }
  getItem(key) { return Object.prototype.hasOwnProperty.call(this.values, key) ? this.values[key] : null; }
  setItem(key, value) { this.values[key] = String(value); }
  removeItem(key) { delete this.values[key]; }
}

const REPAIR = {
  id: "fix_1",
  rule: "internal_link_redirect",
  title: "Remove unnecessary redirects",
  whyItMatters: "Redirect chains can slow crawling and make the preferred URL harder to understand.",
  explanation: "The homepage links through two redirects before reaching the final URL.",
  affected_pages: ["/", "/offers"],
  page_count: 2,
  websiteUrl: "https://example.com",
};
const MODEL = {
  title: "Remove unnecessary redirects",
  sectionLabel: "Important",
  surface: "Homepage",
  scope: "1 page",
  reason: "Redirect hops were confirmed on a page reached from the homepage.",
};

function briefInput(overrides = {}) {
  return {
    item: REPAIR,
    model: MODEL,
    suggestion: repairSuggestion(REPAIR),
    scan: { website_url: "https://example.com" },
    platform: "WordPress",
    ...overrides,
  };
}

test("Grok receives the repair title, evidence, affected URLs, platform, and FixList's suggested fix", () => {
  const context = grokRepairBriefContext(briefInput());

  assert.equal(context.repairTitle, "Remove unnecessary redirects");
  assert.equal(context.platform, "WordPress");
  assert.equal(context.priority, "Important");
  assert.ok(context.suggestedFix.length > 0);
  assert.deepEqual(context.affectedUrls, ["https://example.com/", "https://example.com/offers"]);
  assert.equal(context.evidence, REPAIR.explanation);
});

test("the brief hands Grok a finished diagnosis and asks only for implementation help", () => {
  const brief = buildGrokRepairBrief(briefInput());

  assert.match(brief, /help implementing a repair from my FixList/i);
  assert.match(brief, /FixList suggested fix:/);
  assert.match(brief, /Priority: Important/);
  assert.match(brief, /Platform: WordPress/);
  assert.match(brief, /Do not re-diagnose it, re-rank it, or replace the suggested fix/);
});

test("the diagnosis owner is FixList and Grok's role is implementation only", () => {
  const context = grokRepairBriefContext(briefInput());
  assert.equal(context.diagnosisOwner, "fixlist");
  assert.equal(context.grokRole, "implementation_help");
});

test("an unrecognized repair tells Grok there is no stored suggested fix rather than inviting a diagnosis", () => {
  const item = { ...REPAIR, rule: "future_rule", recommendation: "" };
  const brief = buildGrokRepairBrief(briefInput({ item, suggestion: repairSuggestion(item) }));

  assert.match(brief, /no stored suggested fix for this rule yet/);
  assert.match(brief, /treat the evidence above as the source of truth/);
  assert.match(brief, /Do not re-diagnose it/);
});

test("a large repair is trimmed by dropping affected URLs, never the diagnosis", () => {
  const pages = Array.from({ length: 150 }, (_, index) => `/very/long/category/path/page-${index + 1}`);
  const brief = buildGrokRepairBrief(briefInput({
    item: { ...REPAIR, affected_pages: pages, page_count: 150 },
    maxLength: 700,
  }));

  assert.ok(brief.length <= 700, `brief was ${brief.length} characters`);
  assert.match(brief, /FixList suggested fix:/);
  assert.match(brief, /Do not re-diagnose it/);
});

test("the brief always fits Grok's message limit", () => {
  const pages = Array.from({ length: 400 }, (_, index) => `/page-${index}`);
  const brief = buildGrokRepairBrief(briefInput({ item: { ...REPAIR, affected_pages: pages, page_count: 400 } }));
  assert.ok(brief.length <= GROK_MAX_MESSAGE_LENGTH);
});

test("the hand-off is a draft the customer sends, and signing out clears it", () => {
  const browserWindow = { sessionStorage: new MemoryStorage() };

  assert.equal(stashGrokRepairBrief("Help me fix this", browserWindow), true);
  assert.equal(browserWindow.sessionStorage.getItem(GROK_REPAIR_BRIEF_STORAGE_KEY), "Help me fix this");
  assert.equal(takeGrokRepairBrief(browserWindow), "Help me fix this");
  // Reading consumes it so a later visit does not resurrect a stale repair.
  assert.equal(takeGrokRepairBrief(browserWindow), "");
  assert.ok(CUSTOMER_SESSION_STORAGE_KEYS.includes(GROK_REPAIR_BRIEF_STORAGE_KEY));
});

test("storage failures never break the repair card", () => {
  const hostile = {
    sessionStorage: {
      getItem() { throw new Error("blocked"); },
      setItem() { throw new Error("blocked"); },
      removeItem() { throw new Error("blocked"); },
    },
  };

  assert.equal(stashGrokRepairBrief("brief", hostile), false);
  assert.equal(takeGrokRepairBrief(hostile), "");
  assert.equal(stashGrokRepairBrief("brief", undefined), false);
});

test("FixList composes the brief itself and never asks Grok for the recommendation", () => {
  assert.match(fixListSource, /import \{ buildGrokRepairBrief, stashGrokRepairBrief \} from "@\/lib\/grokRepairBrief"/);
  assert.match(fixListSource, /function askGrokAboutRepair/);
  assert.match(fixListSource, /stashGrokRepairBrief\(brief\)/);
  assert.match(fixListSource, /navigate\("\/assistant"\)/);
  // The suggested fix is built locally, so no model call can produce it.
  assert.doesNotMatch(fixListSource, /grokChat/);
  assert.doesNotMatch(fixListSource, /functions\.invoke/);
});

test("the assistant prefills the repair brief instead of auto-sending it", () => {
  assert.match(assistantSource, /import \{ takeGrokRepairBrief \} from "@\/lib\/grokRepairBrief"/);
  assert.match(assistantSource, /const brief = takeGrokRepairBrief\(\);/);
  assert.match(assistantSource, /setInput\(brief\.slice\(0, GROK_MAX_MESSAGE_LENGTH\)\)/);
  assert.doesNotMatch(assistantSource, /handleSend\(brief\)/);
});

test("the Ask Grok control is offered as optional implementation help", () => {
  assert.match(suggestedFixSource, /Need help implementing this\?/);
  assert.match(suggestedFixSource, /Ask Grok/);
  assert.match(suggestedFixSource, /FixList keeps the diagnosis and priority/);
  assert.match(suggestedFixSource, /typeof onAskGrok === "function"/);
});
