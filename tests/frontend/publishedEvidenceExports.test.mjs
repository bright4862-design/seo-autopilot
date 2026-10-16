import assert from "node:assert/strict";
import test from "node:test";
import { evidenceLink } from "../../src/lib/evidenceUrl.js";
import { buildRepairCards, customerEvidenceGroupRows } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff, serializeScanHandoff } from "../../src/lib/scanHandoff.js";
import * as pdf from "../../src/lib/exportScanReport.js";

const identityVersion = "evidence_url_identity_v2_published_route";
const origin = "https://example.com";
const routes = ["/x", "/x/", "/X", "/a%2Fb", "/a/b", "/a/../x", "/café", "/caf%C3%A9", "/q?b=2&a=1&a=0", "/q?a=0&a=1&b=2"];
const urls = routes.map(route => origin + route);
function repair() {
  return { fix_id: "descriptions", rule: "missing_meta_description", issue_title: 'Describe "these" pages',
    category: "meta_description", priority: "medium", status: "open", page_count: 10,
    affected_pages: urls, evidence_url_identity_version: identityVersion,
    repair_fingerprint: "ten-observed-routes", family_breakdown: { product_page: 10 } };
}

test("published display and links retain dot segments, Unicode, escapes and query order", () => {
  for (const route of routes) {
    assert.deepEqual(evidenceLink(origin + route, origin, { identityVersion }), {
      href: origin + route, label: route, path: route, title: origin + route,
      linkName: `Open affected page: ${route}`, isLinkable: true,
    });
  }
  assert.equal(evidenceLink("/x", "https://example.com/section", { identityVersion }).href, origin + "/x");
  assert.equal(evidenceLink("https://foreign.example/x", origin, { identityVersion }).href, "https://foreign.example/x");
});

test("published links reject unsafe or unknown identities and do not invent an origin", () => {
  for (const url of ["javascript:alert(1)", "//foreign.example/x", "https://user:secret@example.com/x", "/x\\y", "/x\ny"]) {
    assert.equal(evidenceLink(url, origin, { identityVersion }).isLinkable, false, url);
  }
  assert.equal(evidenceLink("/x", "", { identityVersion }).isLinkable, false);
  assert.equal(evidenceLink("/x", origin, { identityVersion: "future" }).isLinkable, false);
});

test("historical links retain their original serialization", () => {
  assert.equal(evidenceLink("/a/../x", origin).href, origin + "/x");
  assert.equal(evidenceLink("/café", origin).href, origin + "/caf%C3%A9");
});

test("new card and serialized JSON handoff keep all ten observed spellings", () => {
  const cards = buildRepairCards([repair()]);
  assert.equal(cards[0].evidence.identityVersion, identityVersion);
  assert.equal(cards[0].evidence.pageCount, 10);
  const handoff = JSON.parse(serializeScanHandoff(buildScanHandoff({scanRecord: { website_url: origin }, cards})));
  assert.equal(handoff.fixes[0].pages_affected, 10);
  assert.deepEqual(handoff.fixes[0].example_pages, urls);
  assert.equal(handoff.fixes[0].example_pages_are_partial, false);
  const groups = customerEvidenceGroupRows(cards[0], origin);
  assert.equal(groups[0].representativeLink.href, urls[0]);
});

test("real PDF annotations preserve the published route, while old reports keep legacy links", () => {
  assert.equal(typeof pdf.buildScanReportPdf, "function", "PDF generation must be exercised before the download side effect");
  const report = pdf.buildScanReportPdf({ project: { business_name: "Fixture", website_url: origin }, issues: [repair()] });
  const bytes = report.output();
  for (const url of urls) assert.ok(bytes.includes(`/URI (${url})`), url);
  const old = repair(); delete old.evidence_url_identity_version;
  const oldBytes = pdf.buildScanReportPdf({ project: { website_url: origin }, issues: [old] }).output();
  assert.equal(oldBytes.includes(`/URI (${origin}/a/../x)`), false);
});
