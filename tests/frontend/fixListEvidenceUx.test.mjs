import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildFixItemFields } from "../../src/lib/scanRunModel.js";

const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const scanFormSource = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
const fixItemEntity = JSON.parse(readFileSync(new URL("../../base44/entities/FixItem.jsonc", import.meta.url), "utf8"));

test("FixList exposes the complete affected URL list with copy and CSV controls", () => {
  assert.match(fixListSource, /Affected URLs/);
  assert.match(fixListSource, /Show all \{availableCount\} URLs/);
  assert.match(fixListSource, /Copy all/);
  assert.match(fixListSource, /Download CSV/);
  assert.match(fixListSource, /affected_url/);
});

test("FixList instructions are action-oriented and rule specific", () => {
  assert.match(fixListSource, /How to fix it/);
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

test("returned durable ScanRun authority is written into the browser scan record", () => {
  assert.match(scanFormSource, /const reviewAttestation = aiData\?\.authority_review_attestation/);
  assert.match(scanFormSource, /const usingAuthorityPersistence = Boolean\(reviewAttestation\)/);
  assert.match(scanFormSource, /const completion = usingAuthorityPersistence/);
  assert.match(scanFormSource, /scan_authority_persistence_failed/);
  assert.match(scanFormSource, /scan_authority_attestation_missing/);
  assert.match(scanFormSource, /aiData\?\.release_gate_eligible === true && !usingAuthorityPersistence/);
  assert.match(scanFormSource, /release_gate_eligible: false, is_authoritative: false/);
  assert.match(scanFormSource, /persistedCompletion\.scanRun\.authority_seal_version/);
  assert.match(scanFormSource, /persistedCompletion\.scanRun\.authority_sealed_at/);
  assert.match(scanFormSource, /"persistScanAuthority"/);
  assert.match(scanFormSource, /await completeScanRun\(scanRunHandle, durableRecord\)/);
  assert.match(scanFormSource, /mergePersistedScanRunRecord\(/);
  assert.match(scanFormSource, /persistedCompletion\.fixListId/);
  assert.match(scanFormSource, /meta_description_state/);
  assert.match(scanFormSource, /metadata_evidence_version/);
  assert.match(scanFormSource, /title_evidence_version/);
});
