import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildFixItemFields } from "../../src/lib/scanRunModel.js";

const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const scanFormSource = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
const durablePersistenceSource = readFileSync(new URL("../../base44/functions/persistDurableScanAuthority/index.ts", import.meta.url), "utf8");
const scanRunsSource = readFileSync(new URL("../../src/lib/scanRuns.js", import.meta.url), "utf8");
const fixItemEntity = JSON.parse(readFileSync(new URL("../../base44/entities/FixItem.jsonc", import.meta.url), "utf8"));

test("FixList exposes the complete affected URL list with copy and CSV controls", () => {
  assert.match(fixListSource, /Affected pages/);
  assert.match(fixListSource, /Show all \{availableCount\} pages/);
  assert.match(fixListSource, /Copy page list/);
  assert.match(fixListSource, /Download CSV/);
  assert.match(fixListSource, /affected_url/);
});

test("FixList instructions are action-oriented and rule specific", () => {
  assert.match(fixListSource, /What to do/);
  assert.match(fixListSource, /rule === "internal_link_redirect"/);
  assert.match(fixListSource, /rule === "sitemap_redirect"/);
  assert.match(fixListSource, /rule === "redirect_chain"/);
  assert.match(fixListSource, /redirect_destination_noindex/);
  assert.match(fixListSource, /Run FixList again/);
});

test("customer-facing URL evidence excludes obvious assets and system routes", () => {
  assert.ok(fixListSource.includes("cdn-cgi"));
  assert.match(fixListSource, /pdf\|png/);
  assert.match(fixListSource, /non-HTML or system URL/);
});

test("HTTP 429 customer copy is neutral and contains no cross-customer language", () => {
  assert.match(fixListSource, /Related site section/);
  assert.match(fixListSource, /same-parent-domain access evidence/);
  assert.match(fixListSource, /Related section on the same parent domain/);
  assert.doesNotMatch(fixListSource, /Meilleurtaux/i);
  assert.doesNotMatch(fixListSource, /Sibling sous-dossier/i);
  assert.doesNotMatch(fixListSource, /different business vertical/i);
  assert.doesNotMatch(fixListSource, /primary energy-comparison customer page/i);
  assert.doesNotMatch(fixListSource, /credit or loan content/i);
});

test("durable FixItems preserve the full 150-page crawl evidence and instructions", () => {
  const affected = Array.from({ length: 150 }, (_, index) => `/page-${index + 1}`);
  const fields = buildFixItemFields({
    issue_title: "Update internal links",
    rule: "internal_link_redirect",
    affected_pages: affected,
    page_count: 150,
    what_to_do_steps: ["Export URLs", "Update links", "Verify"],
    family_breakdown: { standard: 120, legal_info: 30 },
    representative_pages_by_family: { standard: ["/page-1"], legal_info: ["/page-121"] },
  }, { scanRunId: "run_1" });
  assert.equal(fields.affected_pages.length, 150);
  assert.equal(fields.page_count, 150);
  assert.deepEqual(fields.what_to_do_steps, ["Export URLs", "Update links", "Verify"]);
  assert.equal(fields.family_breakdown.standard, 120);
});

test("FixItem entity stores URL counts, family evidence, and fix steps", () => {
  for (const field of ["page_count", "family_breakdown", "representative_pages_by_family", "what_to_do_steps"]) {
    assert.ok(fixItemEntity.properties[field], `FixItem missing ${field}`);
  }
});

test("durable authority is written server-side and the browser only reads the exact sealed result", () => {
  assert.match(durablePersistenceSource, /verifyAuthoritySeal\(signedDocument, secret, proof\)/);
  assert.match(durablePersistenceSource, /buildAuthoritySnapshot\(\{/);
  assert.match(durablePersistenceSource, /persistedScan\?\.status === "complete"/);
  assert.match(durablePersistenceSource, /authority_proof/);
  assert.match(durablePersistenceSource, /persistExactAdmissionRelease\(\{/);
  assert.match(scanRunsSource, /base44\.functions\.invoke\("getCustomerScanResult"/);
  assert.match(scanFormSource, /submitStandardScanJob\(scanPayload\)/);
  assert.match(scanFormSource, /setWatchedScanId\(scanId\)/);
  const submitStart = scanFormSource.indexOf("async function handleSubmit");
  const submitEnd = scanFormSource.indexOf("\n  return (", submitStart);
  const submitSource = scanFormSource.slice(submitStart, submitEnd);
  assert.doesNotMatch(submitSource, /persistScanAuthority|completeScanRun|mergePersistedScanRunRecord/);
});
