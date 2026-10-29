// Pure, unreleased Extended 500 dual-signature verifier. No Base44 imports,
// customer writer, Stripe authorization or Standard 150 completion activation.
import { verifyAuthoritySeal, stableSerialize } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";

export const REVIEWED500_AUTHORITY_VERSION = "extended500_reviewed_authority_v1_unreleased";
export const REVIEWED500_REVIEW_VERSION = "extended500_reviewer_attestation_v1";
export const REVIEWED500_MAX_PAGES = 500;
const BYTE_LIMIT = 8 * 1024 * 1024;
const IDs = ["canonical_mode", "owner_user_id", "scan_id", "project_id",
  "request_id", "idempotency_key", "normalized_domain", "attempt_count"];
const SCAN = ["canonical_mode", "scan_id", "request_id", "idempotency_key",
  "normalized_domain", "pages_found", "pages_crawled", "scan_coverage",
  "scanner_source_sha", "beta_revision_fingerprint", "pages"];
const REVIEW = ["version", "review_status", "identity", "scanner_source_sha",
  "beta_revision_fingerprint", "pages_reviewed", "reviewed_destinations", "findings"];
const COV = ["urls_attempted", "usable_html_pages", "unique_retained_destinations"];
const SEVERITY = new Set(["critical", "high", "medium", "low", "info"]);
const EVIDENCE = new Set(["observed", "verified"]);
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const SOURCE = /^[a-f0-9]{40}$/;
const MARKER = /^[a-f0-9]{16}$/;
const fail = (reason) => ({ valid: false, reason });
const obj = (o) => o !== null && typeof o === "object" && !Array.isArray(o);
const exact = (o, keys) => obj(o) && Object.keys(o).length === keys.length
  && keys.every((k) => Object.hasOwn(o, k));
const count = (n) => Number.isSafeInteger(n) && n >= 0;
function origin(value) {
  try {
    const u = new URL(value);
    if (!["https:", "http:"].includes(u.protocol) || u.username || u.password
        || u.port || u.search || u.hash) return "";
    return `${u.protocol}//${u.hostname.replace(/\.$/, "").toLowerCase()}`;
  } catch { return ""; }
}
function host(value) {
  const o = origin(value);
  return o ? new URL(o).hostname.replace(/^www\./, "") : "";
}

/**
 * Accept reviewed-but-UNRELEASED authority only. This does not establish that
 * a reviewer implementation exists, that source markers match PRODUCTION,
 * that a terminal result was persisted, or that the customer can reopen it.
 */
export async function verifyExtended500ReviewedAuthority(envelope, frozen, {
  reviewerSigningKey, authoritySigningKey, expectedSourceSha, expectedFingerprint,
  cryptoImpl = globalThis.crypto,
} = {}) {
  if (!exact(envelope, [
    "version", "identity", "scan", "review", "reviewer_proof",
    "release_gate_eligible", "proof",
  ]) || envelope.version !== REVIEWED500_AUTHORITY_VERSION
      || envelope.release_gate_eligible !== false) return fail("envelope_invalid");
  if (!obj(frozen) || frozen.scan_mode !== "extended_500") return fail("frozen_mode_invalid");
  if (!exact(envelope.identity, IDs) || !exact(envelope.scan, SCAN)
      || !exact(envelope.scan.scan_coverage, COV)
      || !exact(envelope.review, REVIEW)) return fail("review_shape_invalid");
  if (!SOURCE.test(expectedSourceSha) || !MARKER.test(expectedFingerprint)
      || envelope.scan.scanner_source_sha !== expectedSourceSha
      || envelope.scan.beta_revision_fingerprint !== expectedFingerprint
      || envelope.review.scanner_source_sha !== expectedSourceSha
      || envelope.review.beta_revision_fingerprint !== expectedFingerprint) {
    return fail("release_identity_mismatch");
  }
  const identity = envelope.identity;
  for (const field of ["owner_user_id", "project_id", "request_id", "idempotency_key"]) {
    if (typeof identity[field] !== "string" || !ID.test(identity[field])
        || identity[field] !== frozen[field]) return fail("owner_request_identity_mismatch");
  }
  if (!ID.test(identity.scan_id) || identity.scan_id !== frozen.id
      || identity.canonical_mode !== "extended_500"
      || !count(frozen.attempt_count) || frozen.attempt_count < 1
      || identity.attempt_count !== String(frozen.attempt_count)
      || host(frozen.website_url) !== identity.normalized_domain) {
    return fail("scan_identity_mismatch");
  }
  const scan = envelope.scan;
  for (const field of ["scan_id", "request_id", "idempotency_key", "normalized_domain"]) {
    if (scan[field] !== identity[field]) return fail("collection_identity_mismatch");
  }
  if (scan.canonical_mode !== "extended_500") return fail("collection_mode_invalid");
  const n = scan.pages_crawled;
  if (!count(n) || n < 1 || n > REVIEWED500_MAX_PAGES
      || !count(scan.pages_found) || scan.pages_found < n
      || !Array.isArray(scan.pages) || scan.pages.length !== n) return fail("count_invalid");
  const c = scan.scan_coverage;
  if (!count(c.urls_attempted) || c.urls_attempted < n
      || !count(c.usable_html_pages) || c.usable_html_pages > n
      || c.unique_retained_destinations !== n) return fail("coverage_invalid");
  const expectedOrigin = origin(frozen.website_url);
  if (!expectedOrigin) return fail("frozen_target_invalid");
  const destinations = [];
  for (const page of scan.pages) {
    if (!obj(page)) return fail("page_invalid");
    if (["main_text", "_reachability_links", "future_internal_field"].some(k => Object.hasOwn(page, k)))
      return fail("private_page_field");
    const url = page.final_url || page.url;
    if (typeof url !== "string" || origin(url) !== expectedOrigin) return fail("foreign_page");
    destinations.push(url);
  }
  if (new Set(destinations).size !== n) return fail("duplicate_page");
  const review = envelope.review;
  if (review.version !== REVIEWED500_REVIEW_VERSION || review.review_status !== "reviewed"
      || JSON.stringify(review.identity) !== JSON.stringify(identity)
      || review.pages_reviewed !== n
      || !Array.isArray(review.reviewed_destinations)
      || review.reviewed_destinations.length !== n
      || review.reviewed_destinations.some((url, i) => url !== destinations[i])
      || !Array.isArray(review.findings) || review.findings.length > 2000) {
    return fail("review_coverage_invalid");
  }
  for (const f of review.findings) {
    if (!exact(f, ["rule_id", "page_url", "severity", "evidence_state"])
        || !ID.test(f.rule_id) || !destinations.includes(f.page_url)
        || !SEVERITY.has(f.severity) || !EVIDENCE.has(f.evidence_state)) {
      return fail("finding_invalid");
    }
  }
  if (typeof reviewerSigningKey !== "string" || reviewerSigningKey.length < 32
      || typeof authoritySigningKey !== "string" || authoritySigningKey.length < 32
      || reviewerSigningKey === authoritySigningKey
      || typeof envelope.reviewer_proof !== "string"
      || !await verifyAuthoritySeal(review, reviewerSigningKey, envelope.reviewer_proof, cryptoImpl)) {
    return fail("reviewer_hmac_invalid");
  }
  const body = {
    version: envelope.version, identity, scan, review,
    reviewer_proof: envelope.reviewer_proof, release_gate_eligible: false,
  };
  if (new TextEncoder().encode(stableSerialize(body)).byteLength > BYTE_LIMIT) {
    return fail("review_authority_bytes_exceeded");
  }
  if (typeof envelope.proof !== "string"
      || !await verifyAuthoritySeal(body, authoritySigningKey, envelope.proof, cryptoImpl)) {
    return fail("authority_hmac_invalid");
  }
  return { valid: true, state: "reviewed_but_unreleased", pages_reviewed: n };
}
