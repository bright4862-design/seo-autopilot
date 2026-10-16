import { usesGeoSnapshotVersion, customerGeoReadiness } from "./geoReadiness.js";
import { createAuthoritySeal, stableSerialize, verifyAuthoritySeal } from "./projection.js";

export const CUSTOMER_PREVIEW_SEAL_VERSION = "standard_customer_preview_hmac_v2_geo_readiness";
export const CUSTOMER_PREVIEW_SEAL_VERSION_V1 = "standard_customer_preview_hmac_v1";
export const CUSTOMER_PREVIEW_SEAL_DOMAIN = "fixlist_customer_preview_v1";
export const CUSTOMER_PREVIEW_VISIBLE_FIX_COUNT = 2;

const PREVIEW_RUN_FIELDS = [
  "id",
  "project_id",
  "website_url",
  "normalized_domain",
  "status",
  "status_detail",
  "pages_found",
  "pages_crawled",
  "pages_retained",
  "queued_at",
  "started_at",
  "reviewing_at",
  "worker_heartbeat_at",
  "completed_at",
  "health_score",
  "health_grade",
  "release_gate_eligible",
  "beta_revision_fingerprint",
];

const PREVIEW_FIX_LIST_FIELDS = [
  "id",
  "scan_run_id",
  "project_id",
  "website_url",
  "health_score",
  "health_grade",
  "total_fixes",
  "critical_count",
  "high_count",
  "medium_count",
  "low_count",
  "generated_at",
];

const PREVIEW_FIX_ITEM_FIELDS = [
  "id",
  "fix_id",
  "issue_title",
  "customer_category",
  "priority",
  "action_priority",
  "page_count",
  "plain_english_explanation",
  "why_it_matters",
  "recommended_value",
  "simple_next_step",
  "difficulty",
  "who_can_do_this",
  "requires_developer",
  "evidence_class",
];

export function buildCustomerPreviewPayload({ run, fixList, fixItems, ownerUserId, fullAuthorityProof }) {
  const customerRun = pickFields(run, PREVIEW_RUN_FIELDS);
  customerRun.health_score_status = "authoritative";
  if (usesGeoSnapshotVersion(run?.authority_seal_version)) customerRun.geo_readiness = customerGeoReadiness(run);
  const customerFixList = pickFields(fixList, PREVIEW_FIX_LIST_FIELDS);
  const customerFixItems = [...(Array.isArray(fixItems) ? fixItems : [])]
    .sort((left, right) => {
      const leftRank = positiveRank(left?.canonical_action_rank);
      const rightRank = positiveRank(right?.canonical_action_rank);
      if (leftRank !== rightRank) return leftRank - rightRank;
      return number(right?.action_priority_score) - number(left?.action_priority_score);
    })
    .slice(0, CUSTOMER_PREVIEW_VISIBLE_FIX_COUNT)
    .map((item) => {
      const projected = pickFields(item, PREVIEW_FIX_ITEM_FIELDS);
      projected.preview_locked_detail = false;
      const examplePage = previewExamplePage(item);
      if (examplePage) projected.preview_example_page = examplePage;
      return projected;
    });

  return {
    scan_id: text(run?.id, 160),
    project_id: text(run?.project_id, 160),
    owner_user_id: text(ownerUserId, 160),
    normalized_domain: text(run?.normalized_domain || run?.website_url, 2_000),
    release_fingerprint: text(run?.beta_revision_fingerprint, 64),
    authority_seal_version: text(run?.authority_seal_version, 160),
    authority_sealed_at: text(run?.authority_sealed_at, 80),
    full_authority_proof: cleanProof(fullAuthorityProof),
    sealed_at: text(run?.authority_sealed_at || run?.completed_at, 80),
    run: customerRun,
    fixList: customerFixList,
    fixItems: customerFixItems,
  };
}

export function customerPreviewSealEnvelope(payload) {
  return {
    domain: CUSTOMER_PREVIEW_SEAL_DOMAIN,
    version: usesGeoSnapshotVersion(payload?.authority_seal_version) ? CUSTOMER_PREVIEW_SEAL_VERSION : CUSTOMER_PREVIEW_SEAL_VERSION_V1,
    payload,
  };
}

export function serializeCustomerPreviewPayload(payload) {
  return stableSerialize(payload);
}

export function parseCustomerPreviewPayload(value) {
  const source = typeof value === "string" ? value : "";
  if (!source || source.length > 64_000) return null;
  try {
    const parsed = JSON.parse(source);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function hasCustomerPreviewArtifact(run) {
  return Boolean(
    [CUSTOMER_PREVIEW_SEAL_VERSION, CUSTOMER_PREVIEW_SEAL_VERSION_V1].includes(text(run?.customer_preview_seal_version, 160))
    && text(run?.customer_preview_payload, 64_000)
    && cleanProof(run?.customer_preview_proof)
    && text(run?.customer_preview_sealed_at, 80)
  );
}

export function customerPreviewPayloadMatchesRun(payload, { run, userId }) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  const items = Array.isArray(payload.fixItems) ? payload.fixItems : null;
  const fixList = payload.fixList && typeof payload.fixList === "object" ? payload.fixList : null;
  const previewRun = payload.run && typeof payload.run === "object" ? payload.run : null;
  if (!items || !fixList || !previewRun || items.length > CUSTOMER_PREVIEW_VISIBLE_FIX_COUNT) return false;
  if (items.some((item) => !item || typeof item !== "object" || Array.isArray(item))) return false;
  return Boolean(
    text(payload.scan_id, 160) === text(run?.id, 160)
    && text(payload.project_id, 160) === text(run?.project_id, 160)
    && text(payload.owner_user_id, 160) === text(userId, 160)
    && text(payload.normalized_domain, 2_000) === text(run?.normalized_domain || run?.website_url, 2_000)
    && text(payload.release_fingerprint, 64) === text(run?.beta_revision_fingerprint, 64)
    && text(payload.authority_seal_version, 160) === text(run?.authority_seal_version, 160)
    && text(payload.authority_sealed_at, 80) === text(run?.authority_sealed_at, 80)
    && cleanProof(payload.full_authority_proof) === cleanProof(run?.authority_proof)
    && text(payload.sealed_at, 80) === text(run?.customer_preview_sealed_at || run?.authority_sealed_at, 80)
    && text(previewRun.id, 160) === text(run?.id, 160)
    && text(previewRun.project_id, 160) === text(run?.project_id, 160)
    && text(previewRun.beta_revision_fingerprint, 64) === text(run?.beta_revision_fingerprint, 64)
    && text(fixList.id, 160) === text(run?.fix_list_id, 160)
    && text(fixList.scan_run_id, 160) === text(run?.id, 160)
    && text(fixList.project_id, 160) === text(run?.project_id, 160)
    && number(fixList.total_fixes) >= items.length
  );
}

export async function createCustomerPreviewProof(payload, secret, cryptoImpl = globalThis.crypto) {
  return createAuthoritySeal(customerPreviewSealEnvelope(payload), secret, cryptoImpl);
}

export async function verifyCustomerPreviewProof(payload, secret, proof, cryptoImpl = globalThis.crypto) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  return verifyAuthoritySeal(customerPreviewSealEnvelope(payload), secret, proof, cryptoImpl);
}

function previewExamplePage(item = {}) {
  const candidates = [
    item?.preview_example_page,
    ...(Array.isArray(item?.affected_pages) ? item.affected_pages : []),
    item?.page_url,
  ];
  return candidates.map((value) => text(value, 2_000)).find(Boolean) || "";
}

function pickFields(value, fields) {
  const source = value && typeof value === "object" ? value : {};
  const result = {};
  for (const field of fields) {
    if (source[field] !== undefined) result[field] = source[field];
  }
  return result;
}

function positiveRank(value) {
  const rank = number(value);
  return rank > 0 ? rank : Number.MAX_SAFE_INTEGER;
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function text(value, maxLength) {
  return String(value ?? "").slice(0, maxLength);
}

function cleanProof(value) {
  const proof = String(value || "").trim().toLowerCase();
  return /^[a-f0-9]{64}$/.test(proof) ? proof : "";
}
