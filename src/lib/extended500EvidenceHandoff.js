// Pure, unconnected Extended 500 evidence validator.
// This is NOT referenced by the deployed Standard 150 persistence entry.
// It cannot create a FixList, mark a scan complete, or grant entitlement.
import { verifyAuthoritySeal, stableSerialize } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";

export const EXTENDED500_HANDOFF_VERSION = "extended500_evidence_handoff_v1_unreviewed";
export const EXTENDED500_MODE = "extended_500";
export const EXTENDED500_MAX_PAGES = 500;
const MAX_HANDOFF_BYTES = 8 * 1024 * 1024;
const IDENTITY_KEYS = [
  "canonical_mode", "owner_user_id", "scan_id", "project_id",
  "request_id", "idempotency_key", "normalized_domain", "attempt_count",
];
const SCAN_KEYS = [
  "canonical_mode", "scan_id", "request_id", "idempotency_key",
  "normalized_domain", "pages_found", "pages_crawled", "scan_coverage",
  "scanner_source_sha", "beta_revision_fingerprint", "pages",
];
const COVERAGE_KEYS = ["urls_attempted", "usable_html_pages", "unique_retained_destinations"];
const REVIEW_KEYS = ["review_status", "pages_reviewed", "release_gate_eligible"];

function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function exactKeys(value, keys) {
  return plain(value) && Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}
function token(value) {
  return typeof value === "string" && value.length > 0 && value.length <= 256 && value.trim() === value;
}
function nonnegative(value) {
  return Number.isSafeInteger(value) && value >= 0;
}
function domain(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  let text = value.trim().toLowerCase();
  try {
    if (text.includes("://")) text = new URL(text).hostname;
  } catch { return ""; }
  return text.replace(/^www\./, "").replace(/\.$/, "");
}
function fail(reason) {
  return { valid: false, reason };
}

/**
 * Confirm HMAC and exact frozen-owner identity, then return a staged verdict.
 * Staged results are NEVER sufficient for production completion by themselves.
 */
export async function verifyExtended500EvidenceHandoff(
  envelope, frozenScan, secret, cryptoImpl = globalThis.crypto,
) {
  if (!exactKeys(envelope, ["version", "identity", "scan", "review", "proof"])) return fail("shape_invalid");
  if (envelope.version !== EXTENDED500_HANDOFF_VERSION) return fail("version_invalid");
  if (!plain(frozenScan) || frozenScan.scan_mode !== EXTENDED500_MODE) return fail("mode_invalid");
  const { identity, scan, review } = envelope;
  if (!exactKeys(identity, IDENTITY_KEYS) || !exactKeys(scan, SCAN_KEYS)
      || !exactKeys(scan.scan_coverage, COVERAGE_KEYS) || !exactKeys(review, REVIEW_KEYS)) {
    return fail("document_shape_invalid");
  }
  if (identity.canonical_mode !== EXTENDED500_MODE || scan.canonical_mode !== EXTENDED500_MODE) {
    return fail("mode_invalid");
  }
  if (review.review_status !== "not_reviewed" || review.pages_reviewed !== 0
      || review.release_gate_eligible !== false) return fail("premature_authority_claim");

  for (const key of ["owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key"]) {
    const frozenKey = key === "scan_id" ? "id" : key;
    if (!token(identity[key]) || identity[key] !== frozenScan[frozenKey]) return fail("identity_mismatch");
  }
  if (!token(identity.normalized_domain)
      || identity.normalized_domain !== domain(frozenScan.normalized_domain || frozenScan.website_url)
      || scan.normalized_domain !== identity.normalized_domain) return fail("domain_mismatch");
  if (!/^[1-9][0-9]*$/.test(identity.attempt_count)
      || !nonnegative(frozenScan.attempt_count)
      || Number(identity.attempt_count) !== frozenScan.attempt_count) return fail("attempt_mismatch");

  for (const key of ["scan_id", "request_id", "idempotency_key"]) {
    if (scan[key] !== identity[key]) return fail("identity_mismatch");
  }
  const n = scan.pages_crawled;
  if (!nonnegative(n) || n < 1 || n > EXTENDED500_MAX_PAGES
      || !Array.isArray(scan.pages) || scan.pages.length !== n
      || !nonnegative(scan.pages_found) || scan.pages_found < n) return fail("page_count_invalid");

  const coverage = scan.scan_coverage;
  if (!nonnegative(coverage.urls_attempted) || coverage.urls_attempted < n
      || !nonnegative(coverage.usable_html_pages)
      || coverage.usable_html_pages > coverage.urls_attempted
      || coverage.unique_retained_destinations !== n) return fail("coverage_invalid");

  const destinations = [];
  for (const page of scan.pages) {
    if (!plain(page)) return fail("page_shape_invalid");
    const url = page.final_url || page.url;
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return fail("page_url_invalid");
    destinations.push(url);
  }
  if (new Set(destinations).size !== destinations.length) return fail("duplicate_retained_destination");
  if (!/^[a-f0-9]{40}$/.test(scan.scanner_source_sha)
      || !/^[a-f0-9]{16}$/.test(scan.beta_revision_fingerprint)) return fail("source_identity_invalid");

  const signed = { version: envelope.version, identity, scan, review };
  if (new TextEncoder().encode(stableSerialize(signed)).byteLength > MAX_HANDOFF_BYTES) {
    return fail("byte_budget_exceeded");
  }
  if (typeof secret !== "string" || !secret
      || !await verifyAuthoritySeal(signed, secret, envelope.proof, cryptoImpl)) return fail("hmac_invalid");
  return { valid: true, state: "unreviewed_evidence_only", pages_retained: n };
}
