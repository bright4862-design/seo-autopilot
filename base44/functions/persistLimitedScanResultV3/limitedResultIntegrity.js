import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";

const ENCODER = new TextEncoder();

export const LIMITED_RESULT_INTEGRITY_VERSION = "standard_limited_result_integrity_v4_focused_scope_effective_path";
export const LIMITED_RESULT_INTEGRITY_VERSION_V1 = "standard_limited_result_integrity_v1";
export const LIMITED_RESULT_INTEGRITY_VERSION_V2 = "standard_limited_result_integrity_v2_acceptance_evidence";
export const LIMITED_RESULT_INTEGRITY_VERSION_V3 = "standard_limited_result_integrity_v3_focused_scope";

/**
 * The HMAC domain label, bound *inside* the signed payload rather than kept as
 * a naming convention. Both proofs are computed with the same server signing
 * secret, so the only thing preventing a limited proof from being replayed as
 * an authority seal is that the two payloads can never be equal. Putting the
 * label in the payload is what guarantees that, whatever else the rows carry.
 */
export const LIMITED_RESULT_HMAC_DOMAIN = "standard_limited_result_hmac_v4_focused_scope_effective_path";
export const LIMITED_RESULT_HMAC_DOMAIN_V1 = "standard_limited_result_hmac_v1";
export const LIMITED_RESULT_HMAC_DOMAIN_V2 = "standard_limited_result_hmac_v2_acceptance_evidence";
export const LIMITED_RESULT_HMAC_DOMAIN_V3 = "standard_limited_result_hmac_v3_focused_scope";

export const MAX_LIMITED_FIXES = 100;

const PRIORITIES = new Set(["critical", "high", "medium", "low"]);

/**
 * A limited result is what an honest scan says when it saw something real but
 * not enough to be authoritative. It is never a downgraded authority record:
 * there is no authority proof anywhere in it, and nothing here can be promoted
 * by editing rows.
 */
export function buildLimitedResultSnapshot({
  identity,
  scan,
  review,
  now,
  version = LIMITED_RESULT_INTEGRITY_VERSION,
}) {
  const fixes = firstArray([review?.recommendations, review?.fixes, review?.cleaned_fixes])
    .slice(0, MAX_LIMITED_FIXES)
    .map(toLimitedFix)
    .sort((left, right) => left.fix_id.localeCompare(right.fix_id));

  const coverageReasons = textArray(review?.coverage_reasons, 12, 200);
  const scanStatus = text(review?.scan_status, 120);

  const integrityDomain = limitedIntegrityDomain(version);
  return {
    version,
    integrity_domain: integrityDomain,
    // One stable timestamp, supplied by the caller from durable state, so a
    // retry rebuilds the identical payload and reaches the identical proof
    // instead of creating a second result.
    sealed_at: String(now || ""),
    scan_id: text(identity?.scan_id, 160),
    project_id: text(identity?.project_id, 160),
    owner_user_id: text(identity?.owner_user_id, 160),
    request_id: text(identity?.request_id, 160),
    attempt_count: attempt(identity?.attempt_count),
    normalized_domain: text(identity?.normalized_domain, 400),
    release_fingerprint: text(scan?.beta_revision_fingerprint, 160) || RELEASE_FINGERPRINT,
    // A limited result is only worth persisting when it carries evidence. Zero
    // useful findings stays a failure rather than becoming an empty record that
    // reads as "we looked and found nothing".
    eligible_for_limited_result: fixes.length > 0,
    scan: {
      status: "limited",
      release_gate_eligible: false,
      score_is_provisional: true,
      website_url: text(scan?.submitted_url || scan?.website_url, 2_000),
      ...focusedScopeFields(scan, version),
      scanner_version: text(scan?.scanner_version, 160),
      scanner_build_revision: text(scan?.scanner_build_revision, 160),
      worker_source_sha: text(scan?.worker_source_sha, 80),
      beta_revision_fingerprint: text(scan?.beta_revision_fingerprint, 160),
      pages_found: number(scan?.pages_found),
      pages_crawled: number(scan?.pages_crawled),
      scan_status: scanStatus,
      health_score: number(review?.health_score),
      health_grade: text(review?.health_grade, 80),
      limitation: text(review?.limitation, 2_000),
      // The limitation is the entire point of this record, so it is bound by
      // the proof: nothing can quietly relabel a limited scan as sufficient.
      coverage_state: text(review?.coverage_state, 120),
      coverage_reasons: coverageReasons,
      coverage_authority_version: text(review?.coverage_authority_version, 160),
      ...([
        LIMITED_RESULT_INTEGRITY_VERSION,
        LIMITED_RESULT_INTEGRITY_VERSION_V3,
        LIMITED_RESULT_INTEGRITY_VERSION_V2,
      ].includes(version)
        ? acceptanceEvidenceFields(scan, review)
        : {}),
    },
    fix_list: {
      is_authoritative: false,
      score_is_provisional: true,
      scan_status: scanStatus,
      health_score: number(review?.health_score),
      health_grade: text(review?.health_grade, 80),
      total_fixes: fixes.length,
      coverage_state: text(review?.coverage_state, 120),
    },
    recommendations: fixes,
  };
}

export async function createLimitedResultProof(snapshot, secret, cryptoImpl = globalThis.crypto) {
  const key = await importHmacKey(secret, cryptoImpl, ["sign"]);
  const signature = await cryptoImpl.subtle.sign("HMAC", key, ENCODER.encode(limitedPayload(snapshot)));
  return bytesToHex(new Uint8Array(signature));
}

export async function verifyLimitedResultProof(snapshot, secret, proof, cryptoImpl = globalThis.crypto) {
  const cleanProof = typeof proof === "string" ? proof.trim().toLowerCase() : "";
  if (!/^[a-f0-9]{64}$/.test(cleanProof)) return false;
  try {
    const key = await importHmacKey(secret, cryptoImpl, ["verify"]);
    return await cryptoImpl.subtle.verify(
      "HMAC",
      key,
      hexToBytes(cleanProof),
      ENCODER.encode(limitedPayload(snapshot)),
    );
  } catch {
    return false;
  }
}

export function limitedRowsFromSnapshot(snapshot, { fixListId, proof } = {}) {
  const cleanProof = String(proof || "").toLowerCase();
  const owner = { owner_user_id: String(snapshot?.owner_user_id || "") };
  return {
    scanRun: {
      ...snapshot.scan,
      status: "limited",
      status_detail: text(snapshot?.scan?.limitation, 2_000),
      fix_list_id: String(fixListId || ""),
      release_gate_eligible: false,
      score_is_provisional: true,
      result_integrity_version: snapshot.version,
      result_integrity_domain: snapshot.integrity_domain,
      result_integrity_sealed_at: snapshot.sealed_at,
      result_integrity_proof: cleanProof,
    },
    fixList: {
      scan_run_id: snapshot.scan_id,
      project_id: snapshot.project_id,
      ...snapshot.fix_list,
      is_authoritative: false,
      result_integrity_version: snapshot.version,
      result_integrity_proof: cleanProof,
      ...owner,
    },
    fixItems: snapshot.recommendations.map((fix) => ({
      fix_list_id: String(fixListId || ""),
      scan_run_id: snapshot.scan_id,
      project_id: snapshot.project_id,
      ...fix,
      is_authoritative: false,
      result_integrity_proof: cleanProof,
      ...owner,
    })),
  };
}

/**
 * The signed bytes. The domain label leads the payload so the two contracts can
 * never produce identical input, even if every other field somehow matched.
 */
function limitedPayload(snapshot) {
  const expectedDomain = limitedIntegrityDomain(snapshot?.version);
  if (snapshot?.integrity_domain !== expectedDomain) {
    throw new Error("Limited result integrity domain does not match its version.");
  }
  return JSON.stringify(canonicalize({
    integrity_domain: expectedDomain,
    snapshot,
  }));
}

function limitedIntegrityDomain(version) {
  if (version === LIMITED_RESULT_INTEGRITY_VERSION) return LIMITED_RESULT_HMAC_DOMAIN;
  if (version === LIMITED_RESULT_INTEGRITY_VERSION_V3) return LIMITED_RESULT_HMAC_DOMAIN_V3;
  if (version === LIMITED_RESULT_INTEGRITY_VERSION_V2) return LIMITED_RESULT_HMAC_DOMAIN_V2;
  if (version === LIMITED_RESULT_INTEGRITY_VERSION_V1) return LIMITED_RESULT_HMAC_DOMAIN_V1;
  throw new Error("Unsupported limited result integrity version.");
}

function focusedScopeFields(scan, version) {
  if (![LIMITED_RESULT_INTEGRITY_VERSION, LIMITED_RESULT_INTEGRITY_VERSION_V3].includes(version)) return {};
  const fields = {
    scope_type: text(scan?.scope_type, 40),
    parent_scan_id: text(scan?.parent_scan_id, 160),
    requested_origin: text(scan?.requested_origin, 2_000),
    requested_path_prefix: text(scan?.requested_path_prefix || scan?.path_prefix, 1_000),
    discovered_from: text(scan?.discovered_from, 80),
    user_confirmed: scan?.user_confirmed === true,
  };
  if (version === LIMITED_RESULT_INTEGRITY_VERSION) {
    fields.effective_path_prefix = text(
      scan?.effective_path_prefix || scan?.path_prefix || scan?.requested_path_prefix,
      1_000,
    );
  }
  return fields;
}

export function requiresCompleteAcceptanceEvidence(scanStatus, resultIntegrityVersion) {
  return !(
    String(scanStatus || "").toLowerCase() === "limited"
    && text(resultIntegrityVersion, 160) === LIMITED_RESULT_INTEGRITY_VERSION_V1
  );
}

export function hasCompleteAcceptanceEvidence(scan, review = scan) {
  const coverage = plainObject(review?.coverage_authority_evidence);
  const classification = plainObject(review?.classification_integrity);
  const state = text(classification.state, 120);
  const verdict = text(classification.verdict, 120);
  return Boolean(
    text(coverage.coverage_authority_evidence_version, 160)
    && text(coverage.assessment, 120)
    && text(classification.version, 160) === RELEASE_COMPONENT_VERSIONS.acceptance_evidence_version
    && state
    && verdict
    && state === verdict
    && text(classification.classifier_version, 160)
    && text(classification.evidence_sufficiency, 120)
    && finiteNonNegativeNumber(classification.usable_pages) !== null
    && typeof classification.complete_small_site_inventory === "boolean"
    && positiveNumber(scan?.worker_peak_memory_bytes ?? scan?.peak_memory_bytes) !== null
  );
}

function acceptanceEvidenceFields(scan, review) {
  if (!hasCompleteAcceptanceEvidence(scan, review)) return {};
  const coverage = plainObject(review?.coverage_authority_evidence);
  const classification = plainObject(review?.classification_integrity);
  const workerPeak = positiveNumber(scan?.worker_peak_memory_bytes ?? scan?.peak_memory_bytes);
  return {
    coverage_authority_evidence: coverage,
    classification_integrity: {
      version: text(classification.version, 160),
      state: text(classification.state, 120),
      verdict: text(classification.verdict, 120),
      classifier_version: text(classification.classifier_version, 160),
      evidence_sufficiency: text(classification.evidence_sufficiency, 120),
      usable_pages: finiteNonNegativeNumber(classification.usable_pages),
      complete_small_site_inventory: classification.complete_small_site_inventory,
    },
    classification_verdict: text(classification.verdict, 120),
    peak_memory_bytes: workerPeak,
    worker_peak_memory_bytes: workerPeak,
  };
}

function finiteNonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function positiveNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function toLimitedFix(fix) {
  const priority = String(fix?.priority || "").toLowerCase();
  return {
    fix_id: text(fix?.fix_id, 160),
    issue_title: text(fix?.issue_title || fix?.title, 400),
    rule: text(fix?.rule, 160),
    priority: PRIORITIES.has(priority) ? priority : "low",
    page_url: text(fix?.page_url, 2_000),
    affected_pages: textArray(fix?.affected_pages, 50, 2_000),
    evidence_status: text(fix?.evidence_status, 120),
  };
}

function canonicalize(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((result, key) => {
      const item = value[key];
      if (!["undefined", "function", "symbol"].includes(typeof item)) result[key] = canonicalize(item);
      return result;
    }, {});
  }
  return null;
}

async function importHmacKey(secret, cryptoImpl, usages) {
  const cleanSecret = typeof secret === "string" ? secret : "";
  if (!cleanSecret || !cryptoImpl?.subtle) throw new Error("Limited result integrity key is unavailable.");
  return cryptoImpl.subtle.importKey("raw", ENCODER.encode(cleanSecret), { name: "HMAC", hash: "SHA-256" }, false, usages);
}

function firstArray(candidates) {
  for (const candidate of candidates) if (Array.isArray(candidate) && candidate.length) return candidate;
  return [];
}

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function text(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function textArray(value, limit, itemLimit) {
  return Array.isArray(value) ? value.slice(0, limit).map((item) => text(item, itemLimit)).filter(Boolean) : [];
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function attempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  return bytes;
}
