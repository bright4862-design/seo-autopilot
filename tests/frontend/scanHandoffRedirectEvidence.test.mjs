import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

const REDIRECT_EVIDENCE = {
  requested_url: "https://example.com/about",
  redirect_chain: [
    {
      url: "https://example.com/about",
      status: 301,
      location: "https://example.com/about/",
    },
  ],
  final_url: "https://example.com/about/",
  final_status: 200,
  final_content_type: "text/html; charset=utf-8",
  body_bytes: 12345,
  html_parse_ok: true,
  fetch_error: null,
  robots_status: "allowed",
  canonical_url: "https://example.com/about/",
  noindex: false,
};

function redirectIssue() {
  return {
    id: "redirect-1",
    fix_id: "redirect-1",
    rule: "sitemap_redirect",
    repair_fingerprint: "redirect-normalization",
    status: "needs_approval",
    priority: "medium",
    issue_title: "Replace redirecting sitemap URL with its final URL",
    why_it_matters: "A sitemap should list the preferred final URL.",
    recommendation: "Use the final URL in the sitemap.",
    affected_pages: ["/about"],
    page_count: 1,
    raw_finding: {
      rule: "sitemap_redirect",
      redirect_outcome: "redirect_to_usable_page",
      redirect_fetch_evidence: REDIRECT_EVIDENCE,
    },
  };
}

test("redirect evidence survives the customer card and JSON handoff export", () => {
  const cards = buildRepairCards([redirectIssue()]);
  const handoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com", created_at: "2026-09-08T10:00:00Z" },
    cards,
  });

  assert.equal(cards.length, 1);
  assert.equal(handoff.fixes.length, 1);
  assert.deepEqual(handoff.fixes[0].redirect_evidence, [
    {
      outcome: "redirect_to_usable_page",
      ...REDIRECT_EVIDENCE,
    },
  ]);
});
