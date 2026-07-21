import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const main = readFileSync("src/main.jsx", "utf8");
const recovery = readFileSync("src/lib/scanStorageRecovery.js", "utf8");
const model = readFileSync("src/lib/scanRunModel.js", "utf8");
const schema = readFileSync("base44/entities/ScanRun.jsonc", "utf8");

test("scan recovery boundaries load before the application", () => {
  assert.match(main, /import ['"]@\/lib\/scanStorageRecovery['"]/);
});

test("browser quota errors cannot invalidate a completed scan", () => {
  assert.match(recovery, /QuotaExceededError/);
  assert.match(recovery, /durable scan history remains authoritative/);
  assert.match(recovery, /return undefined/);
  assert.doesNotMatch(recovery, /throw new Error/);
});

test("browser scan records use canonical arrays and compact history", () => {
  assert.match(recovery, /recommendations,/);
  assert.match(recovery, /pages,/);
  assert.match(recovery, /function compactHistoryEntry/);
  assert.match(recovery, /storage_key:/);
  assert.match(recovery, /startsWith\(SCAN_RECORD_PREFIX\)/);
  assert.doesNotMatch(recovery, /fixes: recommendations/);
  assert.doesNotMatch(recovery, /findings: recommendations/);
  assert.doesNotMatch(recovery, /scanned_pages: pages/);
});

test("emergency browser previews preserve the true crawl count", () => {
  assert.match(recovery, /const pagePreviewLimit = emergency \? 12 : limit/);
  assert.match(recovery, /const pagesCrawled = Math\.min\(limit, reportedPages \|\| pages\.length\)/);
  assert.match(recovery, /pages_retained: pages\.length/);
  assert.match(recovery, /local_cache_complete: pages\.length >= pagesCrawled/);
  assert.doesNotMatch(recovery, /pages\.length \|\| reportedPages/);
});

test("scanner responses are capped by selected mode before consumers receive them", () => {
  assert.match(recovery, /function capScannerContainer/);
  assert.match(recovery, /container\.pages_crawled = pagesCrawled/);
  assert.match(recovery, /container\.pages_retained = capped\.length/);
  assert.match(recovery, /slice\(0, limit\)/);
});

test("browser evidence retains v9 metadata and title states", () => {
  for (const field of [
    "meta_description_state",
    "meta_description_element_count",
    "meta_description_values",
    "metadata_evidence_version",
    "title_pixel_width_estimate",
    "title_width_state",
    "title_is_generic_fallback",
    "title_evidence_version",
  ]) {
    assert.match(recovery, new RegExp(`${field}:`));
  }
});

test("release eligibility requires exact v9 authority markers", () => {
  assert.match(recovery, /import { RELEASE_AUTHORITY_CONTRACT } from "@\/lib\/scanRunModel"/);
  assert.match(recovery, /betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT/);
  assert.doesNotMatch(recovery, /const CURRENT_BETA_REVISION_FINGERPRINT =/);
  assert.match(recovery, /classifierVersion === CURRENT_ARCHETYPE_CLASSIFIER_VERSION/);
  assert.match(recovery, /betaRevisionFingerprint === CURRENT_BETA_REVISION_FINGERPRINT/);
  assert.match(recovery, /beta_revision_fingerprint: betaRevisionFingerprint/);
});

test("durable ScanRun keeps release authority and coverage markers", () => {
  for (const field of [
    "scanner_build_revision",
    "advanced_scan_backend",
    "deno_fallback_used",
    "archetype_classifier_version",
    "review_evidence_calibration_version",
    "ai_review_backend",
    "python_review_fallback_used",
    "release_gate_eligible",
    "beta_revision_fingerprint",
    "metadata_evidence_version",
    "title_evidence_version",
    "pages_retained",
    "local_cache_complete",
  ]) {
    assert.match(model, new RegExp(`${field}:`));
    assert.match(schema, new RegExp(`"${field}"`));
  }
  assert.match(model, /pages_crawled: pagesCrawled/);
  assert.match(model, /pages_retained: pagesRetained/);
});
