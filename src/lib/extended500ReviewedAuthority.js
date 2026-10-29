// Extended 500 REVIEWED evidence authority verifier -- NON-OPERATIONAL.
//
// Pure, unconnected verifier mirroring scanner-api/app/extended500_reviewed_authority.py.
// NOT referenced by any Base44 function, route, page or Standard 150 path.
// There is no verified Extended 500 terminal issuer, so a valid verdict is a
// signed *candidate* only: operational=false, customer_publishable=false and
// release_gate_eligible=false, always. It cannot create a FixList, mark a scan
// complete, set release_gate_eligible=true on a live record or grant entitlement.
//
// The unreviewed `extended500_evidence_handoff_v1_unreviewed` collection is never
// promotable: this contract has its own version, a purpose-derived HMAC key
// (HMAC-SHA256(root, purpose)), typed per-page review states, findings that
// reference reviewed retained pages, exact denominators, and it cites the exact
// signed handoff, which is re-verified here with its own verifier.
import {
  EXTENDED500_HANDOFF_VERSION,
  verifyExtended500EvidenceHandoff,
} from "./extended500EvidenceHandoff.js";

export const EXTENDED500_REVIEWED_VERSION = "extended500_reviewed_authority_v1";
export const EXTENDED500_REVIEWED_PURPOSE = "fixlist-extended500-reviewed-authority-v1";
export const EXTENDED500_REVIEWED_OPERATIONAL_STATUS = "non_operational_no_verified_terminal_issuer";
export const EXTENDED500_REVIEWED_TERMINAL_STATE = "not_issued";
export const EXTENDED500_REVIEWED_VERDICT_STATE = "reviewed_authority_candidate_non_operational";
export const EXTENDED500_REVIEWED_OPERATIONAL = false;
export const EXTENDED500_REVIEWED_MAX_PAGES = 500;
export const EXTENDED500_REVIEWED_MAX_FINDINGS = 200;
export const EXTENDED500_REVIEWED_MAX_BYTES = 2 * 1024 * 1024;
export const EXTENDED500_REVIEWED_MIN_ROOT_BYTES = 32;
const MODE = "extended_500";

// Mirrors Python EXTENDED500_REVIEWED_RESTRICTED_FIELDS (INTERNAL_PAGE_EVIDENCE_FIELDS
// plus raw body/HTML/header names); a cross-runtime test pins the two sets.
export const EXTENDED500_REVIEWED_RESTRICTED_FIELDS = Object.freeze([
  "main_text", "main_text_evidence_version", "main_text_signature",
  "main_text_representation", "main_text_token_count", "main_text_char_count",
  "main_text_source", "main_text_verified", "main_text_reason", "main_text_truncated",
  "local_entity_observations", "location_context", "contextual_freshness_evidence",
  "_reachability_links",
  "raw_html", "html", "page_html", "body_html", "rendered_html", "dom_snapshot",
  "response_body", "response_text", "body_text", "text_content", "visible_text",
  "raw_headers", "set_cookie", "cookies", "authorization",
]);
const RESTRICTED = new Set(EXTENDED500_REVIEWED_RESTRICTED_FIELDS);
const RESTRICTED_PREFIX = "main_text";

const PRIORITIES = ["critical", "high", "medium", "low"];
const ACTION_PRIORITIES = ["fix_first", "important", "improve", "review"];
const EVIDENCE_CLASSES = ["confirmed_problem", "improvement", "opportunity"];
const PAGE_SCOPES = ["page", "family", "mixed", "cross_cutting", "sitewide"];
const EVIDENCE_STATUSES = [
  "confirmed", "confirmed_by_high_confidence_heuristic", "confirmed_active_baseline",
  "needs_verification",
];
const VERIFICATION_STATES = ["verified", "confirmed", "needs_verification", "conflicted"];
const PAGE_REVIEW_STATES = ["reviewed", "not_reviewed"];
const CONFIDENCE_STATES = [
  "complete", "complete_with_incidental_access_checks", "no_high_confidence_findings",
  "partial_access_needs_verification", "blocked_access_needs_verification",
  "incomplete_evidence", "insufficient_evidence", "insufficient_discovery_quality",
];
const PROVISIONAL_STATES = new Set([
  "partial_access_needs_verification", "blocked_access_needs_verification",
  "incomplete_evidence", "insufficient_evidence", "insufficient_discovery_quality",
]);
const ACTION_RANK = { fix_first: 4, important: 3, improve: 2, review: 1 };
const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1 };
const FIX_CLAIM_TOKENS = new Set(["fixed", "resolved", "done", "completed"]);

const ENVELOPE_KEYS = [
  "version", "purpose", "operational_status", "identity", "release",
  "evidence_binding", "coverage", "review", "pages", "findings",
  "fix_list_summary", "proof",
];
const SIGNED_KEYS = ENVELOPE_KEYS.slice(0, -1);
const IDENTITY_KEYS = [
  "canonical_mode", "owner_user_id", "scan_id", "project_id",
  "request_id", "idempotency_key", "normalized_domain", "attempt_count",
];
const RELEASE_KEYS = ["scanner_source_sha", "beta_revision_fingerprint", "review_version"];
const BINDING_KEYS = ["handoff_version", "handoff_proof"];
const COVERAGE_KEYS = [
  "pages_found", "urls_attempted", "usable_html_pages", "pages_assessed",
  "pages_reviewed", "pages_not_reviewed", "review_coverage_basis_points",
  "pages_with_findings",
];
const REVIEW_KEYS = [
  "review_status", "review_coverage_state", "sampling_policy_version",
  "review_confidence_state", "score_is_provisional", "no_high_confidence_findings",
  "health_score", "release_gate_eligible", "terminal_receipt_state",
];
const PAGE_KEYS = ["page_id", "final_url", "review_state"];
const FINDING_KEYS = [
  "fix_id", "rule", "category", "issue_title", "plain_english_explanation",
  "simple_next_step", "priority", "evidence_class", "action_priority",
  "action_priority_score", "canonical_action_rank", "page_scope",
  "page_template_family", "affected_page_ids", "page_count", "page_url",
  "evidence_status", "verification_state", "confidence_score",
  "repair_fingerprint", "user_status", "repair_verification_state",
];
const SUMMARY_KEYS = [
  "total_fixes", "critical_count", "high_count", "medium_count", "low_count",
  "fix_first_count", "important_count", "improve_count", "review_count",
  "completed_count", "top_action_fix_ids", "canonical_action_fix_ids",
];

const MAX_DEPTH = 32;
const ASCII_KEY = /^[\x20-\x7e]{1,128}$/;
const ID_TOKEN = /^[A-Za-z0-9_.:-]{1,256}$/;
const VERSION_TOKEN = /^[A-Za-z0-9_.:-]{1,160}$/;
const RULE = /^[a-z0-9][a-z0-9_.:-]{0,119}$/;
const DOMAIN = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/;
const ATTEMPT = /^[1-9][0-9]{0,15}$/;
const SHA40 = /^[0-9a-f]{40}$/;
const FP16 = /^[0-9a-f]{16}$/;
const HEX64 = /^[0-9a-f]{64}$/;
// eslint-disable-next-line no-control-regex
const URL_SHAPE = /^https?:\/\/([A-Za-z0-9.-]+)(?::[0-9]{1,5})?(?:[/?#][^\x00-\x20\x7f]*)?$/;
// eslint-disable-next-line no-control-regex
const CONTROL = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/;
const EDGE_SPACE = /^[ \t\r\n]|[ \t\r\n]$/;
const STATE_LIKE = /^[A-Za-z0-9_ -]{1,120}$/;
const LONE_SURROGATE = /\p{Surrogate}/u;
const ENCODER = new TextEncoder();

class ContractError extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}
function fail(reason) {
  throw new ContractError(reason);
}

function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function exactKeys(value, keys) {
  return plain(value) && Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}
function nonneg(value) {
  return Number.isSafeInteger(value) && value >= 0;
}
function matches(pattern, value) {
  return typeof value === "string" && pattern.test(value);
}
function codePoints(value) {
  let count = 0;
  for (const _char of value) count += 1;
  return count;
}
function text(value, limit, required) {
  return typeof value === "string" && (value.length > 0 || !required)
    && codePoints(value) <= limit && !CONTROL.test(value) && !EDGE_SPACE.test(value);
}
function same(left, right) {
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length
      && left.every((item, index) => same(item, right[index]));
  }
  if (plain(left) || plain(right)) {
    if (!plain(left) || !plain(right)) return false;
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length
      && keys.every((key) => Object.hasOwn(right, key) && same(left[key], right[key]));
  }
  return left === right;
}
function claimsFix(value) {
  if (!matches(STATE_LIKE, value)) return false;
  return value.toLowerCase().split(/[_ -]+/).some((part) => FIX_CLAIM_TOKENS.has(part));
}
function urlHost(value) {
  if (typeof value !== "string" || codePoints(value) > 2048) return "";
  const found = URL_SHAPE.exec(value);
  if (!found) return "";
  let host = found[1].toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);
  return host.endsWith(".") ? host.slice(0, -1) : host;
}
function frozenDomain(value) {
  if (typeof value !== "string") return "";
  const clean = value.replace(/^[ \t\n\r\f\v]+|[ \t\n\r\f\v]+$/g, "");
  if (clean.includes("://")) return urlHost(clean);
  // eslint-disable-next-line no-control-regex
  if (!/^[\x00-\x7f]*$/.test(clean)) return "";
  let host = clean.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);
  return host.endsWith(".") ? host.slice(0, -1) : host;
}
function restrictedPresent(value) {
  const stack = [value];
  const seen = new Set();
  while (stack.length) {
    const item = stack.pop();
    if (item === null || typeof item !== "object") continue;
    if (seen.has(item)) continue;
    seen.add(item);
    if (Array.isArray(item)) {
      for (const child of item) stack.push(child);
      continue;
    }
    for (const key of Object.keys(item)) {
      if (RESTRICTED.has(key) || key.startsWith(RESTRICTED_PREFIX)) return true;
      stack.push(item[key]);
    }
  }
  return false;
}
function pageId(index) {
  return `p${String(index + 1).padStart(3, "0")}`;
}

function canonical(value, depth) {
  if (depth > MAX_DEPTH) fail("canonical_value_invalid");
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("canonical_value_invalid");
    return String(value);
  }
  if (typeof value === "string") {
    if (LONE_SURROGATE.test(value)) fail("canonical_value_invalid");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    const parts = [];
    for (let index = 0; index < value.length; index += 1) {
      if (!(index in value)) fail("canonical_value_invalid");
      parts.push(canonical(value[index], depth + 1));
    }
    return `[${parts.join(",")}]`;
  }
  if (typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) fail("canonical_value_invalid");
    const keys = Object.keys(value).sort();
    const parts = [];
    for (const key of keys) {
      if (!ASCII_KEY.test(key)) fail("canonical_value_invalid");
      parts.push(`${JSON.stringify(key)}:${canonical(value[key], depth + 1)}`);
    }
    return `{${parts.join(",")}}`;
  }
  return fail("canonical_value_invalid");
}

/** Strict canonical JSON, byte-identical to Python canonical_reviewed_bytes. Throws on non-canonical values. */
export function canonicalReviewedJson(value) {
  return canonical(value, 0);
}

function summaryOf(findings) {
  const ids = findings.map((finding) => finding.fix_id);
  const summary = { total_fixes: findings.length };
  for (const level of PRIORITIES) summary[`${level}_count`] = findings.filter((f) => f.priority === level).length;
  for (const band of ACTION_PRIORITIES) summary[`${band}_count`] = findings.filter((f) => f.action_priority === band).length;
  summary.completed_count = 0;
  summary.top_action_fix_ids = ids.slice(0, 3);
  summary.canonical_action_fix_ids = ids;
  return summary;
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  return bytes;
}

async function proofValid(signedBytes, secret, proof, cryptoImpl) {
  if (!matches(HEX64, proof) || !cryptoImpl?.subtle) return false;
  try {
    const { subtle } = cryptoImpl;
    const root = await subtle.importKey("raw", ENCODER.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const derived = new Uint8Array(await subtle.sign("HMAC", root, ENCODER.encode(EXTENDED500_REVIEWED_PURPOSE)));
    const key = await subtle.importKey("raw", derived, { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
    return await subtle.verify("HMAC", key, hexToBytes(proof), signedBytes);
  } catch {
    return false;
  }
}

function checkFrozenScan(frozenScan) {
  if (!plain(frozenScan) || frozenScan.scan_mode !== MODE) fail("mode_invalid");
  const proof = frozenScan.authority_proof;
  if (!["crawling", "reviewing"].includes(frozenScan.status)
      || frozenScan.release_gate_eligible === true
      || (proof !== undefined && proof !== null && proof !== "")) fail("scan_state_invalid");
}

function checkIdentity(identity, frozenScan) {
  if (identity.canonical_mode !== MODE) fail("mode_invalid");
  for (const key of ["owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key"]) {
    const frozenKey = key === "scan_id" ? "id" : key;
    if (!matches(ID_TOKEN, identity[key]) || identity[key] !== frozenScan[frozenKey]) fail("identity_mismatch");
  }
  const domain = frozenDomain(frozenScan.normalized_domain || frozenScan.website_url);
  if (!matches(DOMAIN, identity.normalized_domain) || identity.normalized_domain !== domain) fail("domain_mismatch");
  const frozenAttempt = frozenScan.attempt_count;
  if (!matches(ATTEMPT, identity.attempt_count) || !nonneg(frozenAttempt) || frozenAttempt < 1
      || Number(identity.attempt_count) !== frozenAttempt) fail("attempt_mismatch");
}

async function validateSigned(signed, options, cryptoImpl) {
  const { frozenScan, expectedRelease, secret, evidenceHandoff, handoffSecret } = options;
  if (signed.version === EXTENDED500_HANDOFF_VERSION) fail("unreviewed_handoff_not_promotable");
  if (signed.version !== EXTENDED500_REVIEWED_VERSION) fail("version_invalid");
  if (signed.purpose !== EXTENDED500_REVIEWED_PURPOSE) fail("purpose_invalid");
  if (signed.operational_status !== EXTENDED500_REVIEWED_OPERATIONAL_STATUS) fail("non_operational_marker_invalid");
  checkFrozenScan(frozenScan);
  const { identity, release, evidence_binding: binding, coverage, review, pages, findings } = signed;
  const summary = signed.fix_list_summary;
  if (!exactKeys(identity, IDENTITY_KEYS) || !exactKeys(release, RELEASE_KEYS)
      || !exactKeys(binding, BINDING_KEYS) || !exactKeys(coverage, COVERAGE_KEYS)
      || !exactKeys(review, REVIEW_KEYS) || !exactKeys(summary, SUMMARY_KEYS)
      || !Array.isArray(pages) || !Array.isArray(findings)) fail("document_shape_invalid");
  checkIdentity(identity, frozenScan);

  if (review.release_gate_eligible !== false
      || review.terminal_receipt_state !== EXTENDED500_REVIEWED_TERMINAL_STATE) fail("premature_release_gate");
  if (review.review_status !== "reviewed") fail("review_not_reviewed");

  if (!exactKeys(expectedRelease, RELEASE_KEYS)
      || !matches(SHA40, expectedRelease.scanner_source_sha)
      || !matches(FP16, expectedRelease.beta_revision_fingerprint)
      || !matches(VERSION_TOKEN, expectedRelease.review_version)) fail("release_expectation_missing");
  if (RELEASE_KEYS.some((key) => release[key] !== expectedRelease[key])) fail("release_mismatch");

  if (typeof secret !== "string" || ENCODER.encode(secret).byteLength < EXTENDED500_REVIEWED_MIN_ROOT_BYTES) {
    fail("signing_root_invalid");
  }
  if (typeof handoffSecret !== "string" || !handoffSecret) fail("signing_root_invalid");
  if (secret === handoffSecret) fail("signing_root_not_distinct");

  const handoffVerdict = await verifyExtended500EvidenceHandoff(evidenceHandoff, frozenScan, handoffSecret, cryptoImpl);
  if (!handoffVerdict || handoffVerdict.valid !== true) fail("evidence_handoff_invalid");
  const handoffScan = evidenceHandoff.scan;
  if (IDENTITY_KEYS.some((key) => identity[key] !== evidenceHandoff.identity[key])
      || binding.handoff_version !== EXTENDED500_HANDOFF_VERSION
      || !matches(HEX64, binding.handoff_proof)
      || binding.handoff_proof !== evidenceHandoff.proof) fail("evidence_binding_mismatch");
  if (release.scanner_source_sha !== handoffScan.scanner_source_sha
      || release.beta_revision_fingerprint !== handoffScan.beta_revision_fingerprint) fail("release_mismatch");

  const count = pages.length;
  if (count < 1 || count > EXTENDED500_REVIEWED_MAX_PAGES || count !== handoffScan.pages_crawled) fail("page_count_invalid");
  const retained = handoffScan.pages.map((page) => page.final_url || page.url);
  const states = new Map();
  const urls = new Map();
  pages.forEach((page, index) => {
    if (!exactKeys(page, PAGE_KEYS) || page.page_id !== pageId(index)
        || page.final_url !== retained[index] || !PAGE_REVIEW_STATES.includes(page.review_state)) {
      fail("page_index_invalid");
    }
    if (urlHost(page.final_url) !== identity.normalized_domain) fail("page_host_mismatch");
    states.set(page.page_id, page.review_state);
    urls.set(page.page_id, page.final_url);
  });
  const reviewed = [...states.values()].filter((state) => state === "reviewed").length;

  if (!COVERAGE_KEYS.every((key) => nonneg(coverage[key]))) fail("denominator_mismatch");
  if (reviewed === 0 || coverage.pages_reviewed === 0) fail("review_not_reviewed");
  const handoffCoverage = handoffScan.scan_coverage;
  const scaled = reviewed * 10000;
  if (coverage.pages_assessed !== count
      || coverage.pages_found !== handoffScan.pages_found
      || coverage.urls_attempted !== handoffCoverage.urls_attempted
      || coverage.usable_html_pages !== handoffCoverage.usable_html_pages
      || coverage.pages_found < count || coverage.urls_attempted < count
      || coverage.usable_html_pages > coverage.urls_attempted
      || coverage.pages_reviewed !== reviewed
      || coverage.pages_not_reviewed !== count - reviewed
      || coverage.review_coverage_basis_points !== (scaled - (scaled % count)) / count) fail("denominator_mismatch");

  const expectedCoverageState = reviewed === count ? "all_assessed_pages_reviewed" : "bounded_sample_reviewed";
  if (review.review_coverage_state !== expectedCoverageState
      || !matches(VERSION_TOKEN, review.sampling_policy_version)) fail("review_coverage_invalid");

  if (findings.length > EXTENDED500_REVIEWED_MAX_FINDINGS) fail("finding_shape_invalid");
  const state = review.review_confidence_state;
  const health = review.health_score;
  if (!CONFIDENCE_STATES.includes(state)
      || typeof review.score_is_provisional !== "boolean"
      || typeof review.no_high_confidence_findings !== "boolean"
      || !(health === null || (nonneg(health) && health <= 100))
      || ((PROVISIONAL_STATES.has(state) || reviewed < count) && review.score_is_provisional !== true)
      || review.no_high_confidence_findings !== (findings.length === 0)
      || (state === "no_high_confidence_findings") !== (findings.length === 0)) fail("review_confidence_invalid");

  const fixIds = [];
  const fingerprints = new Set();
  const referenced = new Set();
  let previous = null;
  findings.forEach((finding, index) => {
    if (!exactKeys(finding, FINDING_KEYS)) fail("finding_shape_invalid");
    if (finding.user_status === "done" || claimsFix(finding.repair_verification_state)
        || claimsFix(finding.evidence_status) || claimsFix(finding.verification_state)) fail("false_fix_claim");
    if (!(matches(VERSION_TOKEN, finding.fix_id)
        && matches(RULE, finding.rule)
        && text(finding.category, 120, false)
        && text(finding.issue_title, 500, true)
        && text(finding.plain_english_explanation, 2000, false)
        && text(finding.simple_next_step, 2000, false)
        && PRIORITIES.includes(finding.priority)
        && EVIDENCE_CLASSES.includes(finding.evidence_class)
        && ACTION_PRIORITIES.includes(finding.action_priority)
        && nonneg(finding.action_priority_score) && finding.action_priority_score <= 100000
        && PAGE_SCOPES.includes(finding.page_scope)
        && text(finding.page_template_family, 200, false)
        && EVIDENCE_STATUSES.includes(finding.evidence_status)
        && VERIFICATION_STATES.includes(finding.verification_state)
        && nonneg(finding.confidence_score) && finding.confidence_score <= 100
        && matches(VERSION_TOKEN, finding.repair_fingerprint)
        && finding.user_status === "open"
        && finding.repair_verification_state === "not_compared")) fail("finding_field_invalid");
    if (fixIds.includes(finding.fix_id) || fingerprints.has(finding.repair_fingerprint)) fail("duplicate_finding");
    const affected = finding.affected_page_ids;
    if (!Array.isArray(affected) || affected.length === 0) fail("finding_evidence_missing");
    for (const id of affected) {
      if (typeof id !== "string" || !states.has(id)) fail("finding_evidence_missing");
      if (states.get(id) !== "reviewed") fail("finding_evidence_not_reviewed");
    }
    if (new Set(affected).size !== affected.length
        || finding.page_count !== affected.length
        || finding.page_url !== urls.get(affected[0])
        || (finding.page_scope === "page" && affected.length !== 1)
        || (finding.page_scope === "sitewide" && finding.page_template_family !== "")) fail("finding_field_invalid");
    const key = [ACTION_RANK[finding.action_priority], finding.action_priority_score, SEVERITY_RANK[finding.priority]];
    const greater = previous !== null && (key[0] !== previous[0] ? key[0] > previous[0]
      : key[1] !== previous[1] ? key[1] > previous[1] : key[2] > previous[2]);
    if (finding.canonical_action_rank !== index + 1 || greater) fail("priority_order_invalid");
    previous = key;
    fixIds.push(finding.fix_id);
    fingerprints.add(finding.repair_fingerprint);
    for (const id of affected) referenced.add(id);
  });

  if (summary.completed_count !== 0) fail("false_fix_claim");
  if (!same(summary, summaryOf(findings))) fail("aggregation_mismatch");
  if (coverage.pages_with_findings !== referenced.size) fail("denominator_mismatch");

  const bytes = ENCODER.encode(canonicalReviewedJson(signed));
  if (bytes.byteLength > EXTENDED500_REVIEWED_MAX_BYTES) fail("byte_budget_exceeded");
  return bytes;
}

/**
 * Verify a reviewed Extended 500 envelope against the fresh server-read frozen
 * ScanRun, the server-owned expected release, its distinct reviewed root and
 * the exact signed unreviewed handoff it cites. A valid verdict is NEVER
 * customer-publishable: no verified terminal issuer exists.
 */
export async function verifyExtended500ReviewedAuthority(envelope, options = {}, cryptoImpl = globalThis.crypto) {
  try {
    if (!plain(envelope)) fail("shape_invalid");
    if (restrictedPresent(envelope)) fail("restricted_field_present");
    if (envelope.version === EXTENDED500_HANDOFF_VERSION) fail("unreviewed_handoff_not_promotable");
    if (envelope.version !== EXTENDED500_REVIEWED_VERSION) fail("version_invalid");
    if (!exactKeys(envelope, ENVELOPE_KEYS)) fail("shape_invalid");
    const signed = Object.fromEntries(SIGNED_KEYS.map((key) => [key, envelope[key]]));
    const bytes = await validateSigned(signed, plain(options) ? options : {}, cryptoImpl);
    if (!await proofValid(bytes, options.secret, envelope.proof, cryptoImpl)) fail("hmac_invalid");
    return {
      valid: true,
      state: EXTENDED500_REVIEWED_VERDICT_STATE,
      operational: EXTENDED500_REVIEWED_OPERATIONAL,
      customer_publishable: false,
      release_gate_eligible: false,
      pages_assessed: signed.coverage.pages_assessed,
      pages_reviewed: signed.coverage.pages_reviewed,
      total_fixes: signed.fix_list_summary.total_fixes,
    };
  } catch (error) {
    if (error instanceof ContractError) return { valid: false, reason: error.reason };
    return { valid: false, reason: "verifier_error" };
  }
}
