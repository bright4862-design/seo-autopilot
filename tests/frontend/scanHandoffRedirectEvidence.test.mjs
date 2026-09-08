import assert from "node:assert/strict";
import test from "node:test";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV3/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV3/authorityRows.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV3/projection.js";
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
    },
  ]);
  assert.equal(handoff.fixes[0].redirect_evidence[0].classification, "redirect_to_usable_page");
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
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_status, 200);
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_url, "https://example.com/");
});

test("wrong-destination redirect evidence survives authority persistence and customer projection", () => {
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
    robots_status: "allowed",
    canonical_url: "https://example.com/",
    noindex: false,
    classification: "redirect_to_wrong_destination",
  };
  const snapshot = buildAuthoritySnapshot({
    scan: {
      website_url: "https://example.com/",
      pages_found: 2,
      pages_crawled: 2,
    },
    review: {
      recommendations: [{
        fix_id: "wrong-redirect-persisted",
        rule: "redirect_wrong_destination",
        category: "redirect",
        issue_title: "Fix a redirect that sends visitors to the wrong page",
        why_it_matters: "The source URL should reach a relevant replacement.",
        recommendation: "Map it to the closest relevant page.",
        affected_pages: ["/section/deep-page"],
        source_pages: ["/section"],
        page_count: 1,
        priority: "critical",
        raw_finding: {
          redirect_outcome: "redirect_to_wrong_destination",
          redirect_fetch_evidence_samples: [evidence],
        },
      }],
    },
    identity: {
      scan_id: "scan-redirect-evidence",
      project_id: "project-1",
      normalized_domain: "example.com",
    },
    userId: "user-1",
    now: "2026-09-08T23:10:00.000Z",
  });

  assert.equal(
    snapshot.recommendations[0].raw_finding.redirect_outcome,
    "redirect_to_wrong_destination",
    "authority snapshot dropped redirect outcome",
  );
  assert.deepEqual(
    snapshot.recommendations[0].raw_finding.redirect_fetch_evidence_samples,
    [evidence],
    "authority snapshot dropped redirect chain evidence",
  );

  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist-redirect-evidence",
    ownerUserId: "user-1",
    proof: "a".repeat(64),
  });
  const projection = buildCustomerProjection({
    run: { id: "scan-redirect-evidence", project_id: "project-1", ...rows.scanRun },
    fixList: { id: "fixlist-redirect-evidence", ...rows.fixList },
    fixItems: rows.fixItems.map((item, index) => ({ id: `row-${index + 1}`, ...item })),
    fullAccess: true,
    authorityVerified: true,
    resultIntegrityVerified: false,
  });

  assert.equal(
    projection.fixItems[0].raw_finding.redirect_outcome,
    "redirect_to_wrong_destination",
    "customer projection dropped redirect outcome",
  );
  assert.deepEqual(
    projection.fixItems[0].raw_finding.redirect_fetch_evidence_samples,
    [evidence],
    "customer projection dropped redirect chain evidence",
  );

  const handoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com", created_at: "2026-09-08T23:10:00Z" },
    cards: buildRepairCards(projection.fixItems),
  });
  assert.equal(handoff.fixes[0].redirect_evidence[0].classification, "redirect_to_wrong_destination");
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_url, "https://example.com/");
  assert.equal(handoff.fixes[0].redirect_evidence[0].final_status, 200);
});
