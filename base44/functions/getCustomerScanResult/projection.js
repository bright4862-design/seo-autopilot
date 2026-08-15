const ENCODER = new TextEncoder();

export const ACCESS_APP_ID = "6a498732ec779dfaaeab0e53";
export const ACCESS_PLAN_ID = "standard150_lifetime";
export const OWNER_TEST_EMAIL = "bright4862@gmail.com";
export const OWNER_TEST_USER_ID = "6a498da58ef5cec1f5cd4486";

const PUBLIC_RUN_FIELDS = [
  "id",
  "project_id",
  "website_url",
  "submitted_url",
  "final_url",
  "normalized_domain",
  "scan_mode",
  "status",
  "status_detail",
  "pages_found",
  "pages_crawled",
  "pages_retained",
  "queued_remaining",
  "queued_at",
  "started_at",
  "reviewing_at",
  "completed_at",
  "created_date",
  "updated_date",
  "error_code",
];

// History is intentionally narrower than the progress projection used for one
// exact ScanRun. It must remain safe before entitlement is checked and never
// carry score, evidence, request identity, release identity, or authority data.
export function buildScanHistoryProjection(rows = []) {
  return uniqueRows(rows).map((run) => ({
    id: text(run?.id, 160),
    project_id: text(run?.project_id, 160),
    website_url: text(run?.website_url || run?.submitted_url, 2_000),
    normalized_domain: domain(run?.normalized_domain || run?.website_url || run?.submitted_url),
    status: text(run?.status, 80),
    pages_found: nonNegativeInteger(run?.pages_found),
    pages_crawled: nonNegativeInteger(run?.pages_crawled),
    queued_at: text(run?.queued_at, 80),
    started_at: text(run?.started_at, 80),
    reviewing_at: text(run?.reviewing_at, 80),
    completed_at: text(run?.completed_at, 80),
  })).filter((run) => run.id && run.project_id);
}

export function recordOwnedByUser(record, userIdValue) {
  const userId = text(userIdValue, 160);
  if (!userId) return false;
  const explicitOwner = text(record?.owner_user_id, 160);
  if (explicitOwner) return explicitOwner === userId;
  return text(record?.created_by_id, 160) === userId;
}

const DETAILED_RUN_FIELDS = [
  "scanner_version",
  "scanner_build_revision",
  "scanner_wrapper_version",
  "release_id",
  "advanced_scan_backend",
  "deno_fallback_used",
  "archetype_classifier_version",
  "review_version",
  "review_evidence_calibration_version",
  "ai_review_backend",
  "python_review_fallback_used",
  "release_gate_eligible",
  "beta_revision_fingerprint",
  "metadata_evidence_version",
  "title_evidence_version",
  "local_cache_complete",
  "sampling_evidence",
  "crawl_timing",
  "scan_status",
  "review_confidence_state",
  "score_is_provisional",
  "access_evidence_state",
  "evidence_quality_state",
  "evidence_quality_score",
  "evidence_quality_reasons",
  "discovery_quality_state",
  "representative_html_page_count",
  "usable_html_page_count",
  "default_route_page_count",
  "evidence_quality_blocking",
  "evidence_quality_gate_version",
  "no_high_confidence_findings",
  "limitation",
  "render_evidence",
  "health_score",
  "health_grade",
  "customer_summary",
  "next_best_step",
  "fix_list_id",
];

const FIX_LIST_FIELDS = [
  "id",
  "scan_run_id",
  "project_id",
  "website_url",
  "ai_review_backend",
  "python_review_fallback_used",
  "is_authoritative",
  "health_score",
  "health_grade",
  "scan_status",
  "score_is_provisional",
  "no_high_confidence_findings",
  "total_fixes",
  "critical_count",
  "high_count",
  "medium_count",
  "low_count",
  "completed_count",
  "top_action_fix_ids",
  "generated_at",
  "created_date",
  "updated_date",
];

const FIX_ITEM_FIELDS = [
  "id",
  "fix_list_id",
  "scan_run_id",
  "project_id",
  "fix_id",
  "rule",
  "category",
  "customer_category",
  "issue_title",
  "plain_english_explanation",
  "why_it_matters",
  "current_value",
  "recommended_value",
  "simple_next_step",
  "page_scope",
  "page_template_family",
  "page_url",
  "affected_pages",
  "source_pages",
  "evidence_status",
  "verification_state",
  "limitation_code",
  "confidence_score",
  "priority",
  "difficulty",
  "who_can_do_this",
  "requires_developer",
  "requires_approval",
  "can_auto_fix",
  "estimated_time",
  "user_status",
  "completed_at",
  "completed_by_user_id",
  "first_seen_scan_run_id",
  "carried_over",
  "page_count",
  "family_breakdown",
  "representative_pages_by_family",
  "what_to_do_steps",
  "metadata_state_counts",
  "combined_rules",
  "grouping_explanation",
  "created_date",
  "updated_date",
];

export function evaluatePaidAccess({ rows, user }) {
  const records = uniqueRows(rows);
  if (records.length !== 1) return { ok: false, failureCode: records.length > 1 ? "paid_access_conflict" : "paid_access_required" };

  const row = records[0];
  const email = normalizedEmail(user?.email);
  const userId = text(user?.id, 160);
  const paidAt = Date.parse(text(row?.paid_at, 80));
  const grantedAt = Date.parse(text(row?.granted_at, 80));
  const identityMatches = Boolean(
    email
    && userId
    && normalizedEmail(row?.user_email) === email
    && text(row?.owner_user_id, 160) === userId
  );
  const activeGrant = Boolean(
    row?.has_full_access === true
    && row?.access_status === "active"
    && row?.plan_id === ACCESS_PLAN_ID
    && row?.app_id === ACCESS_APP_ID
  );
  const paidGrant = Boolean(
    activeGrant
    && row?.grant_source === "stripe_checkout"
    && text(row?.stripe_checkout_session_id, 200)
    && Number.isFinite(paidAt)
  );
  const ownerGrant = Boolean(
    activeGrant
    && row?.grant_source === "owner_test"
    && email === OWNER_TEST_EMAIL
    && userId === OWNER_TEST_USER_ID
    && Number.isFinite(grantedAt)
  );
  const manualGrant = Boolean(
    activeGrant
    && row?.grant_source === "manual_grant"
    && Number.isFinite(grantedAt)
  );
  return identityMatches && (paidGrant || ownerGrant || manualGrant)
    ? { ok: true, record: row }
    : { ok: false, failureCode: "paid_access_required" };
}

export function buildCustomerProjection({ run, fixList, fixItems, fullAccess, authorityVerified }) {
  const canReadResult = fullAccess === true && authorityVerified === true;
  return {
    success: true,
    access: fullAccess === true ? "full" : "locked",
    authority_verified: canReadResult,
    scan_id: text(run?.id, 160),
    fix_list_id: canReadResult ? text(fixList?.id, 160) : "",
    run: sanitizeRun(run, { detailed: canReadResult }),
    fixList: canReadResult ? pickFields(fixList, FIX_LIST_FIELDS) : null,
    fixItems: canReadResult ? (fixItems || []).map(sanitizeFixItem) : [],
  };
}

export function authoritySnapshotFromRows({ run, fixList, fixItems, userId }) {
  return {
    version: text(run?.authority_seal_version, 160),
    sealed_at: text(run?.authority_sealed_at, 80),
    owner_user_id: text(userId, 160),
    scan_id: text(run?.id, 160),
    project_id: text(run?.project_id, 160),
    normalized_domain: domain(run?.normalized_domain || run?.website_url),
    release_fingerprint: text(run?.beta_revision_fingerprint, 160),
    scan: {
      status: text(run?.status, 80),
      release_gate_eligible: run?.release_gate_eligible === true,
      score_is_provisional: run?.score_is_provisional === true,
      evidence_quality_blocking: run?.evidence_quality_blocking === true,
      website_url: text(run?.website_url, 2_000),
      normalized_domain: domain(run?.normalized_domain || run?.website_url),
      scanner_version: text(run?.scanner_version, 160),
      scanner_build_revision: text(run?.scanner_build_revision, 160),
      scanner_wrapper_version: text(run?.scanner_wrapper_version, 160),
      advanced_scan_backend: text(run?.advanced_scan_backend, 160),
      deno_fallback_used: run?.deno_fallback_used === true,
      archetype_classifier_version: text(run?.archetype_classifier_version, 160),
      review_version: text(run?.review_version, 160),
      review_evidence_calibration_version: text(run?.review_evidence_calibration_version, 160),
      ai_review_backend: text(run?.ai_review_backend, 160),
      python_review_fallback_used: run?.python_review_fallback_used === true,
      beta_revision_fingerprint: text(run?.beta_revision_fingerprint, 160),
      metadata_evidence_version: text(run?.metadata_evidence_version, 160),
      title_evidence_version: text(run?.title_evidence_version, 160),
      pages_found: number(run?.pages_found),
      pages_crawled: number(run?.pages_crawled),
      scan_status: text(run?.scan_status, 120),
      review_confidence_state: text(run?.review_confidence_state, 120),
      evidence_quality_state: text(run?.evidence_quality_state, 120),
      evidence_quality_score: number(run?.evidence_quality_score),
      evidence_quality_reasons: textArray(run?.evidence_quality_reasons, 12, 500),
      health_score: number(run?.health_score),
      health_grade: text(run?.health_grade, 80),
      customer_summary: text(run?.customer_summary, 4_000),
      next_best_step: text(run?.next_best_step, 2_000),
      no_high_confidence_findings: run?.no_high_confidence_findings === true,
      completed_at: text(run?.completed_at, 80),
    },
    fix_list: {
      website_url: text(fixList?.website_url, 2_000),
      ai_review_backend: text(fixList?.ai_review_backend, 160),
      python_review_fallback_used: fixList?.python_review_fallback_used === true,
      is_authoritative: fixList?.is_authoritative === true,
      health_score: number(fixList?.health_score),
      health_grade: text(fixList?.health_grade, 80),
      scan_status: text(fixList?.scan_status, 120),
      score_is_provisional: fixList?.score_is_provisional === true,
      no_high_confidence_findings: fixList?.no_high_confidence_findings === true,
      total_fixes: number(fixList?.total_fixes),
      critical_count: number(fixList?.critical_count),
      high_count: number(fixList?.high_count),
      medium_count: number(fixList?.medium_count),
      low_count: number(fixList?.low_count),
      completed_count: number(fixList?.completed_count),
      top_action_fix_ids: textArray(fixList?.top_action_fix_ids, 3, 160),
      generated_at: text(fixList?.generated_at, 80),
    },
    recommendations: (fixItems || []).map(authorityFixFromRow)
      .sort((left, right) => left.fix_id.localeCompare(right.fix_id)),
  };
}

export async function createAuthoritySeal(payload, secret, cryptoImpl = globalThis.crypto) {
  const key = await importHmacKey(secret, cryptoImpl, ["sign"]);
  const signature = await cryptoImpl.subtle.sign(
    "HMAC",
    key,
    ENCODER.encode(stableSerialize(payload)),
  );
  return bytesToHex(new Uint8Array(signature));
}

export async function verifyAuthoritySeal(payload, secret, proof, cryptoImpl = globalThis.crypto) {
  const cleanProof = typeof proof === "string" ? proof.trim().toLowerCase() : "";
  if (!/^[a-f0-9]{64}$/.test(cleanProof)) return false;
  try {
    const key = await importHmacKey(secret, cryptoImpl, ["verify"]);
    return await cryptoImpl.subtle.verify(
      "HMAC",
      key,
      hexToBytes(cleanProof),
      ENCODER.encode(stableSerialize(payload)),
    );
  } catch {
    return false;
  }
}

export function stableSerialize(value) {
  return JSON.stringify(canonicalize(value));
}

function authorityFixFromRow(item) {
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  return {
    fix_id: text(item?.fix_id, 160),
    rule: text(item?.rule, 200),
    category: text(item?.category, 200),
    customer_category: text(item?.customer_category, 200),
    issue_title: text(item?.issue_title, 500),
    plain_english_explanation: text(item?.plain_english_explanation, 2_000),
    why_it_matters: text(item?.why_it_matters, 2_000),
    current_value: text(item?.current_value, 2_000),
    recommended_value: text(item?.recommended_value, 2_000),
    simple_next_step: text(item?.simple_next_step, 2_000),
    page_scope: text(item?.page_scope, 80),
    page_template_family: text(item?.page_template_family, 200),
    page_url: text(item?.page_url, 2_000),
    affected_pages: textArray(item?.affected_pages, 150, 2_000),
    source_pages: textArray(item?.source_pages, 150, 2_000),
    evidence_status: text(item?.evidence_status, 120),
    verification_state: text(item?.verification_state, 120),
    confidence_score: number(item?.confidence_score),
    priority: text(item?.priority, 40),
    difficulty: text(item?.difficulty, 120),
    who_can_do_this: text(item?.who_can_do_this, 120),
    requires_developer: item?.requires_developer === true,
    requires_approval: item?.requires_approval === true,
    can_auto_fix: false,
    estimated_time: text(item?.estimated_time, 120),
    user_status: text(item?.user_status, 80),
    what_to_do_steps: textArray(item?.what_to_do_steps, 12, 1_000),
    raw_finding: { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) },
  };
}

function sanitizeRun(run, { detailed }) {
  const result = pickFields(run, detailed ? [...PUBLIC_RUN_FIELDS, ...DETAILED_RUN_FIELDS] : PUBLIC_RUN_FIELDS);
  result.id = text(run?.id, 160);
  result.scan_id = result.id;
  if (!detailed) {
    result.release_gate_eligible = false;
    result.is_authoritative = false;
  }
  return result;
}

function sanitizeFixItem(item) {
  const result = pickFields(item, FIX_ITEM_FIELDS);
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  result.raw_finding = { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) };
  return result;
}

function pickFields(value, fields) {
  const source = value && typeof value === "object" ? value : {};
  return fields.reduce((result, field) => {
    if (source[field] !== undefined) result[field] = source[field];
    return result;
  }, {});
}

function uniqueRows(rows) {
  return Array.from(new Map(
    (Array.isArray(rows) ? rows : [])
      .filter((row) => row && text(row.id, 160))
      .map((row) => [text(row.id, 160), row]),
  ).values());
}

function normalizedEmail(value) {
  return text(value, 320).toLowerCase();
}

function verifiedUrls(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 25).map((item) => typeof item === "string"
    ? { url: text(item, 2_000) }
    : {
      url: text(item?.url, 2_000),
      final_url: text(item?.final_url, 2_000),
      status_code: number(item?.status_code),
      verification_state: text(item?.verification_state, 120),
    }).filter((item) => item.url || item.final_url);
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

function nonNegativeInteger(value) {
  return Math.max(0, Math.trunc(number(value)));
}

function domain(value) {
  const raw = text(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(parsed.protocol)
      ? parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "")
      : "";
  } catch {
    return "";
  }
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
  if (!cleanSecret || !cryptoImpl?.subtle) throw new Error("Authority seal key is unavailable.");
  return cryptoImpl.subtle.importKey(
    "raw",
    ENCODER.encode(cleanSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    usages,
  );
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) {
    bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  }
  return bytes;
}
