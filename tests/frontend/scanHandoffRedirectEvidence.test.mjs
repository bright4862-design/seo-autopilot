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
  classification: "redirect_to_usable_page",
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
      verification_state: "verified",
    },
  ]);
  assert.equal(handoff.fixes[0].redirect_evidence[0].classification, "redirect_to_usable_page");
  assert.equal(handoff.fixes[0].redirect_evidence[0].verification_state, "verified");
});

test("wrong-destination classification survives grouped redirect evidence", () => {
  const evidence = {
    requested_url: "https://example.com/section/deep-page",
    redirect_chain: [{
      url: "https://example.com/section/deep-page",
      status: 301,
      location: "https://example.com/",
    }],
    final_url: "https://example.com/",
    final_status: 200,
    final_content_type: "text/html",
    body_bytes: 9000,
    html_parse_ok: true,
    fetch_error: null,
    robots_status: "Indexable",
    canonical_url: "https://example.com/",
    noindex: false,
    classification: "redirect_to_wrong_destination",
  };
  const issue = {
    id: "wrong-redirect",
    fix_id: "wrong-redirect",
    rule: "redirect_wrong_destination",
    repair_fingerprint: "wrong-destination",
    status: "needs_developer",
    priority: "high",
    issue_title: "Fix a redirect that sends visitors to the wrong page",
    why_it_matters: "The source URL should reach a relevant replacement.",
    recommendation: "Map it to the closest relevant page.",
    affected_pages: ["/section/deep-page"],
    page_count: 1,
    raw_finding: {
      rule: "redirect_wrong_destination",
      redirect_outcome: "redirect_to_wrong_destination",
      redirect_fetch_evidence: evidence,
    },
  };

  const handoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com", created_at: "2026-09-08T10:00:00Z" },
    cards: buildRepairCards([issue]),
  });

  assert.equal(handoff.fixes[0].redirect_evidence[0].classification, "redirect_to_wrong_destination");
  assert.equal(handoff.fixes[0].redirect_evidence[0].verification_state, "verified");
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_status, 200);
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_url, "https://example.com/");
});
