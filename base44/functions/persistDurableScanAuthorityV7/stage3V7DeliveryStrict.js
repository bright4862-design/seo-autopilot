import {
  buildAuthoritySnapshot,
  buildPersistedAuthoritySnapshot,
} from "./authoritySnapshot.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export const STAGE3_AUTHORITY_VERSION = "standard_review_snapshot_hmac_stage3_delivery_v1";
export const STAGE3_V7_DELIVERY_VERSION = "stage3_v7_delivery_v1";
export const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";
export const STAGE3_DELIVERY_SOURCE_VERSION = "stage3_delivery_v1_rank_before_truncate";
export const STAGE3_PREVIEW_SOURCE_VERSION = "stage3_preview_source_v1_verified_evidence";
export const STAGE3_SCORE_CAP_VERSION = "stage3_health_score_caps_v1_verified_root_cause";
export const STAGE3_HANDOFF_VERSION = "fixlist_handoff_v2";

const SCORE_COVERAGE_STATES = new Set([
  "sufficient",
  "limited_coverage",
  "inventory_unproven",
  "access_limited",
  "unknown",
]);
const MAX_HANDOFF_FIXES = 100;
const MAX_PRESENTED_FIXES = 36;
const MAX_SAMPLES = 10;

const plainObject = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const cleanText = (value, limit = 2_000) => typeof value === "string" ? value.trim().slice(0, limit) : "";
const nullableText = (value, limit = 2_000) => value === null || value === undefined ? null : (typeof value === "string" ? value.trim().slice(0, limit) : null);
const nullableTextField = (value, limit = 2_000) => {
  if (value === null || value === undefined) return { valid: true, value: null };
  if (typeof value !== "string") return { valid: false, value: null };
  return { valid: true, value: value.trim().slice(0, limit) };
};
const exactInteger = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => Number.isInteger(value) && value >= min && value <= max ? value : null;
const exactNumber = (value, min, max) => typeof value === "number" && Number.isFinite(value) && value >= min && value <= max ? value : null;
const nullableNumber = (value, min, max) => value === null ? null : exactNumber(value, min, max);
const nullableInteger = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => value === null ? null : exactInteger(value, min, max);

function textArray(value, limit, itemLimit = 2_000) {
  if (!Array.isArray(value) || value.length > limit) return null;
  const output = [];
  const seen = new Set();
  for (const item of value) {
    const clean = cleanText(item, itemLimit);
    if (!clean || seen.has(clean)) return null;
    seen.add(clean);
    output.push(clean);
  }
  return output;
}

function stage3Attempted(review) {
  return [
    "stage3_delivery",
    "stage3_private_preview_source",
    "stage3_health_score_decision",
    "stage3_handoff_v2_source",
  ].some((key) => review?.[key] !== undefined)
    || (Array.isArray(review?.canonical_repairs) && review.canonical_repairs.some((fix) => fix?.stage3_priority_factors !== undefined || fix?.stage3_counts !== undefined));
}

function normalizePriorityFactors(value) {
  const source = plainObject(value);
  if (!source || cleanText(source.version, 120) !== STAGE3_PRIORITY_VERSION) return null;
  const impact = exactInteger(source.impact, 0, 5);
  const reach = nullableNumber(source.reach, 0, 1);
  const pageValue = nullableNumber(source.page_value, 0, 1);
  const confidence = nullableNumber(source.confidence, 0, 1);
  const score = nullableNumber(source.priority_factor_score, 0, 5);
  if (impact === null || reach === undefined || pageValue === undefined || confidence === undefined || score === undefined) return null;
  if (score !== null) {
    if (reach === null || pageValue === null || confidence === null) return null;
    const expected = Math.round(impact * reach * pageValue * confidence * 1_000_000) / 1_000_000;
    if (Math.abs(expected - score) > 1e-9) return null;
  }
  const affected = exactInteger(source.reach_affected_indexable, 0);
  const denominator = exactInteger(source.reach_observed_indexable_family, 0);
  if (affected === null || denominator === null || affected > denominator) return null;
  const explanation = textArray(source.explanation, 8, 1_000);
  if (!explanation) return null;
  const output = {
    version: STAGE3_PRIORITY_VERSION,
    impact,
    impact_reason: nullableText(source.impact_reason, 500),
    reach,
    reach_state: nullableText(source.reach_state, 80),
    reach_affected_indexable: affected,
    reach_observed_indexable_family: denominator,
    page_value: pageValue,
    page_value_state: nullableText(source.page_value_state, 80),
    page_value_role: nullableText(source.page_value_role, 120),
    page_value_source: nullableText(source.page_value_source, 120),
    confidence,
    confidence_state: nullableText(source.confidence_state, 80),
    priority_factor_score: score,
    score_state: nullableText(source.score_state, 80),
    technical_base_severity: nullableText(source.technical_base_severity, 80),
    technical_severity_source: nullableText(source.technical_severity_source, 160),
    explanation,
  };
  if ([output.impact_reason, output.reach_state, output.page_value_state, output.page_value_role, output.page_value_source, output.confidence_state, output.score_state, output.technical_base_severity, output.technical_severity_source].some((item) => item === null)) return null;
  return output;
}

function normalizeCounts(value) {
  const source = plainObject(value);
  if (!source) return null;
  const unique = exactInteger(source.unique_affected_page_count, 0);
  const observations = nullableInteger(source.observation_count, 0);
  const population = nullableInteger(source.known_population_count, 0);
  const displayed = exactInteger(source.displayed_sample_count, 0, MAX_SAMPLES);
  const truncated = exactInteger(source.truncated_sample_count, 0);
  const samples = textArray(source.displayed_samples, MAX_SAMPLES, 2_000);
  if (unique === null || observations === undefined || population === undefined || displayed === null || truncated === null || !samples) return null;
  if (population !== null && population < unique) return null;
  if (displayed !== samples.length || displayed > unique || truncated !== unique - displayed) return null;
  if (source.examples_partial !== (displayed < unique)) return null;
  return {
    unique_affected_page_count: unique,
    observation_count: observations,
    known_population_count: population,
    displayed_sample_count: displayed,
    displayed_samples: samples,
    examples_partial: source.examples_partial === true,
    truncated_sample_count: truncated,
  };
}

function normalizeDelivery(value, canonicalIds) {
  const source = plainObject(value);
  if (!source || cleanText(source.version, 120) !== STAGE3_DELIVERY_SOURCE_VERSION) return null;
  const eligible = exactInteger(source.eligible_candidate_count, 0, MAX_HANDOFF_FIXES);
  const displayed = exactInteger(source.displayed_candidate_count, 0, MAX_PRESENTED_FIXES);
  const omitted = exactInteger(source.presentation_omitted_count, 0, MAX_HANDOFF_FIXES);
  const ids = textArray(source.displayed_fix_ids, MAX_PRESENTED_FIXES, 160);
  if (eligible === null || displayed === null || omitted === null || !ids) return null;
  if (displayed !== ids.length || displayed > eligible || omitted !== eligible - displayed) return null;
  if (source.presentation_truncated !== (omitted > 0)) return null;
  if (ids.some((id) => !canonicalIds.has(id))) return null;
  return {
    version: STAGE3_DELIVERY_SOURCE_VERSION,
    eligible_candidate_count: eligible,
    displayed_candidate_count: displayed,
    presentation_truncated: source.presentation_truncated === true,
    presentation_omitted_count: omitted,
    displayed_fix_ids: ids,
  };
}

function normalizePreview(value, scanId, canonicalIds) {
  const source = plainObject(value);
  if (!source || cleanText(source.version, 120) !== STAGE3_PREVIEW_SOURCE_VERSION) return null;
  if (cleanText(source.scan_id, 160) !== scanId) return null;
  if (cleanText(source.entitlement_state, 160) !== "requires_authenticated_customer_gate") return null;
  const state = cleanText(source.state, 40);
  if (!["findings", "good_shape", "not_available"].includes(state)) return null;
  if (!Array.isArray(source.findings) || source.findings.length > 2) return null;
  const findings = [];
  const ids = new Set();
  for (const raw of source.findings) {
    const row = plainObject(raw);
    if (!row) return null;
    const ruleId = cleanText(row.rule_id, 160);
    const title = nullableTextField(row.title, 240);
    const evidenceSummary = nullableTextField(row.evidence_summary, 500);
    const impact = exactInteger(row.impact, 0, 5);
    if (!ruleId || !canonicalIds.has(ruleId) || ids.has(ruleId) || !title.valid || !evidenceSummary.valid || impact === null) return null;
    ids.add(ruleId);
    findings.push({ rule_id: ruleId, title: title.value, impact, evidence_summary: evidenceSummary.value });
  }
  if (state === "findings" && findings.length === 0) return null;
  if (state !== "findings" && findings.length !== 0) return null;
  const qualification = nullableTextField(source.coverage_qualification, 500);
  if (!qualification.valid) return null;
  return {
    version: STAGE3_PREVIEW_SOURCE_VERSION,
    scan_id: scanId,
    entitlement_state: "requires_authenticated_customer_gate",
    state,
    findings,
    coverage_qualification: qualification.value,
  };
}

function normalizeRootCapRows(value, { ignored = false } = {}) {
  if (!Array.isArray(value) || value.length > MAX_HANDOFF_FIXES) return null;
  const output = [];
  const seen = new Set();
  for (const raw of value) {
    const row = plainObject(raw);
    const id = cleanText(row?.root_cause_id, 200);
    const cap = nullableInteger(row?.score_cap, 0, 100);
    if (!row || !id || cap === undefined || seen.has(id)) return null;
    seen.add(id);
    if (ignored) {
      const reason = cleanText(row.reason, 160);
      if (!reason) return null;
      output.push({ root_cause_id: id, score_cap: cap, reason });
    } else {
      if (cap === null) return null;
      output.push({ root_cause_id: id, score_cap: cap });
    }
  }
  return output;
}

function normalizeScoreDecision(value) {
  const source = plainObject(value);
  if (!source || cleanText(source.version, 120) !== STAGE3_SCORE_CAP_VERSION || cleanText(source.state, 40) !== "decided") return null;
  const base = exactInteger(source.base_health_score, 0, 100);
  const existing = nullableInteger(source.existing_score_ceiling, 0, 100);
  const root = nullableInteger(source.root_cause_score_ceiling, 0, 100);
  const effective = nullableInteger(source.effective_score_ceiling, 0, 100);
  const adjusted = exactInteger(source.adjusted_health_score, 0, 100);
  const coverage = cleanText(source.coverage_state, 80);
  const applied = normalizeRootCapRows(source.applied_root_cause_caps);
  const ignored = normalizeRootCapRows(source.ignored_root_cause_caps, { ignored: true });
  if (base === null || existing === undefined || root === undefined || effective === undefined || adjusted === null || !SCORE_COVERAGE_STATES.has(coverage) || !applied || !ignored) return null;
  const ceilings = [existing, root].filter((item) => item !== null);
  const expectedEffective = ceilings.length ? Math.min(...ceilings) : null;
  if (effective !== expectedEffective || adjusted !== Math.min(base, effective ?? base)) return null;
  return {
    version: STAGE3_SCORE_CAP_VERSION,
    state: "decided",
    base_health_score: base,
    coverage_state: coverage,
    existing_score_ceiling: existing,
    root_cause_score_ceiling: root,
    effective_score_ceiling: effective,
    adjusted_health_score: adjusted,
    applied_root_cause_caps: applied,
    ignored_root_cause_caps: ignored,
    legacy_health_score_unchanged: source.legacy_health_score_unchanged === true,
  };
}

function normalizeHandoffCounts(value) {
  const source = plainObject(value);
  if (!source) return null;
  const unique = exactInteger(source.unique_affected_pages, 0);
  const observations = nullableInteger(source.observations, 0);
  const population = nullableInteger(source.known_population, 0);
  const displayed = exactInteger(source.displayed_examples, 0, MAX_SAMPLES);
  const indexable = nullableInteger(source.indexable_affected, 0);
  if (unique === null || observations === undefined || population === undefined || displayed === null || indexable === undefined) return null;
  if (population !== null && population < unique) return null;
  return { unique_affected_pages: unique, observations, known_population: population, displayed_examples: displayed, indexable_affected: indexable };
}

function normalizeHandoff(value, scanId, canonicalIds) {
  const source = plainObject(value);
  if (!source || cleanText(source.handoff_version, 80) !== STAGE3_HANDOFF_VERSION) return null;
  const scan = plainObject(source.scan);
  if (!scan || cleanText(scan.scan_id, 160) !== scanId || cleanText(scan.scan_run_id, 160) !== scanId) return null;
  if (!Array.isArray(source.fixes) || source.fixes.length > MAX_HANDOFF_FIXES || exactInteger(source.fix_count, 0, MAX_HANDOFF_FIXES) !== source.fixes.length) return null;
  const fixes = [];
  const ids = new Set();
  for (const raw of source.fixes) {
    const row = plainObject(raw);
    const ruleId = cleanText(row?.rule_id, 160);
    if (!row || !ruleId || !canonicalIds.has(ruleId) || ids.has(ruleId)) return null;
    ids.add(ruleId);
    const counts = normalizeHandoffCounts(row.counts);
    const factors = normalizePriorityFactors(row.priority_factors);
    const families = textArray(row.family_ids, MAX_HANDOFF_FIXES, 160);
    const examples = textArray(row.examples, MAX_SAMPLES, 2_000);
    const evidenceRefs = textArray(row.evidence_refs, MAX_HANDOFF_FIXES, 500);
    const verificationSteps = textArray(row.verification_steps, 20, 1_000);
    const provenance = plainObject(row.url_provenance);
    if (!counts || !factors || !families || !examples || !evidenceRefs || !verificationSteps || !provenance) return null;
    if (counts.displayed_examples !== examples.length || row.examples_partial !== (examples.length < counts.unique_affected_pages)) return null;
    const publishedUrl = nullableTextField(provenance.published_url, 2_000);
    const requestUrl = nullableTextField(provenance.request_url, 2_000);
    const finalUrl = nullableTextField(provenance.final_url, 2_000);
    const title = nullableTextField(row.title, 500);
    const rootCauseId = nullableTextField(row.root_cause_id, 200);
    const dependency = nullableTextField(row.dependency, 500);
    const vendorOwner = nullableTextField(row.vendor_owner, 200);
    if ([publishedUrl, requestUrl, finalUrl, title, rootCauseId, dependency, vendorOwner].some((item) => !item.valid)) return null;
    fixes.push({
      rule_id: ruleId,
      title: title.value,
      root_cause_id: rootCauseId.value,
      family_ids: families,
      url_provenance: { published_url: publishedUrl.value, request_url: requestUrl.value, final_url: finalUrl.value },
      counts,
      examples,
      examples_partial: row.examples_partial === true,
      priority_factors: factors,
      evidence_refs: evidenceRefs,
      verification_steps: verificationSteps,
      dependency: dependency.value,
      vendor_owner: vendorOwner.value,
    });
  }
  if (source.suppressed_findings !== undefined) return null;
  const normalizedDomain = nullableText(scan.normalized_domain, 300);
  const scanOrigin = nullableText(scan.scan_origin, 2_000);
  const identityVersion = nullableText(scan.evidence_url_identity_version, 160);
  const userAgent = nullableText(source.user_agent, 500);
  if ([normalizedDomain, scanOrigin, identityVersion, userAgent].some((item) => item === null)) return null;
  return {
    handoff_version: STAGE3_HANDOFF_VERSION,
    scan: {
      scan_id: scanId,
      scan_run_id: scanId,
      ...(normalizedDomain !== null ? { normalized_domain: normalizedDomain } : {}),
      ...(scanOrigin !== null ? { scan_origin: scanOrigin } : {}),
      ...(identityVersion !== null ? { evidence_url_identity_version: identityVersion } : {}),
    },
    user_agent: userAgent,
    fixes,
    fix_count: fixes.length,
  };
}

function normalizeStage3Sources(review, snapshot) {
  const canonicalRepairs = Array.isArray(review?.canonical_repairs) ? review.canonical_repairs : null;
  if (!canonicalRepairs || canonicalRepairs.length !== snapshot.recommendations.length) return null;
  const canonicalIds = new Set(snapshot.recommendations.map((fix) => cleanText(fix.fix_id, 160)).filter(Boolean));
  if (canonicalIds.size !== snapshot.recommendations.length) return null;
  const perFix = new Map();
  for (const repair of canonicalRepairs) {
    const id = cleanText(repair?.fix_id, 160);
    const factors = normalizePriorityFactors(repair?.stage3_priority_factors);
    const counts = normalizeCounts(repair?.stage3_counts);
    if (!id || !canonicalIds.has(id) || perFix.has(id) || !factors || !counts) return null;
    perFix.set(id, { version: STAGE3_V7_DELIVERY_VERSION, priority_factors: factors, counts });
  }
  const delivery = normalizeDelivery(review?.stage3_delivery, canonicalIds);
  const preview = normalizePreview(review?.stage3_private_preview_source, snapshot.scan_id, canonicalIds);
  const decision = normalizeScoreDecision(review?.stage3_health_score_decision);
  const handoff = normalizeHandoff(review?.stage3_handoff_v2_source, snapshot.scan_id, canonicalIds);
  if (!delivery || !preview || !decision || !handoff) return null;
  return {
    capsule: {
      version: STAGE3_V7_DELIVERY_VERSION,
      delivery,
      private_preview_source: preview,
      health_score_decision: decision,
      handoff_v2_source: handoff,
    },
    perFix,
  };
}

function withStage3(snapshot, sources) {
  const adjusted = sources.capsule.health_score_decision.adjusted_health_score;
  return {
    ...snapshot,
    version: STAGE3_AUTHORITY_VERSION,
    scan: {
      ...snapshot.scan,
      health_score: adjusted,
      health_score_explanation: {
        ...(plainObject(snapshot.scan?.health_score_explanation) || {}),
        stage3_delivery: sources.capsule,
      },
    },
    fix_list: { ...snapshot.fix_list, health_score: adjusted },
    recommendations: snapshot.recommendations.map((fix) => ({
      ...fix,
      raw_finding: {
        ...(plainObject(fix.raw_finding) || {}),
        stage3_delivery: sources.perFix.get(cleanText(fix.fix_id, 160)),
      },
    })),
  };
}

export function buildAuthoritySnapshotStage3(options) {
  const snapshot = buildAuthoritySnapshot(options);
  const review = plainObject(options?.review) || {};
  if (!stage3Attempted(review)) return snapshot;
  if (snapshot.version !== PUBLISHED_REVIEW_ATTESTATION_VERSION) {
    throw new Error("Stage3 durable delivery requires the published V7 authority contract");
  }
  const sources = normalizeStage3Sources(review, snapshot);
  if (!sources) throw new Error("Stage3 durable delivery source is invalid or incomplete");
  return withStage3(snapshot, sources);
}

function persistedReviewForStage3(run, fixItems) {
  const explanation = plainObject(run?.health_score_explanation);
  const capsule = plainObject(explanation?.stage3_delivery);
  if (!capsule) return null;
  return {
    stage3_delivery: capsule.delivery,
    stage3_private_preview_source: capsule.private_preview_source,
    stage3_health_score_decision: capsule.health_score_decision,
    stage3_handoff_v2_source: capsule.handoff_v2_source,
    canonical_repairs: (Array.isArray(fixItems) ? fixItems : []).map((item) => {
      const raw = plainObject(item?.raw_finding) || {};
      const perFix = plainObject(raw.stage3_delivery) || {};
      return {
        fix_id: item?.fix_id,
        stage3_priority_factors: perFix.priority_factors,
        stage3_counts: perFix.counts,
      };
    }),
  };
}

export function buildPersistedAuthoritySnapshotStage3(args) {
  const run = plainObject(args?.run) || {};
  if (run.authority_seal_version !== STAGE3_AUTHORITY_VERSION) {
    return buildPersistedAuthoritySnapshot(args);
  }
  const baseRun = { ...run, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION };
  const base = buildPersistedAuthoritySnapshot({ ...args, run: baseRun });
  const review = persistedReviewForStage3(run, args?.fixItems);
  if (!review) throw new Error("Persisted Stage3 delivery capsule is missing");
  const sources = normalizeStage3Sources(review, base);
  if (!sources) throw new Error("Persisted Stage3 delivery capsule is invalid");
  return withStage3(base, sources);
}

export function stage3CustomerFields(run, item) {
  if (run?.authority_seal_version !== STAGE3_AUTHORITY_VERSION) return {};
  const capsule = plainObject(run?.health_score_explanation)?.stage3_delivery;
  const perFix = plainObject(item?.raw_finding)?.stage3_delivery;
  return {
    ...(plainObject(capsule)?.health_score_decision ? { stage3_health_score_decision: capsule.health_score_decision } : {}),
    ...(plainObject(capsule)?.handoff_v2_source ? { stage3_handoff_v2: capsule.handoff_v2_source } : {}),
    ...(plainObject(perFix)?.priority_factors ? { stage3_priority_factors: perFix.priority_factors } : {}),
    ...(plainObject(perFix)?.counts ? { stage3_counts: perFix.counts } : {}),
  };
}

export function stage3PreviewFixIds(run) {
  if (run?.authority_seal_version !== STAGE3_AUTHORITY_VERSION) return null;
  const preview = plainObject(plainObject(run?.health_score_explanation)?.stage3_delivery)?.private_preview_source;
  if (!plainObject(preview) || preview.version !== STAGE3_PREVIEW_SOURCE_VERSION || preview.scan_id !== run?.id) return null;
  return Array.isArray(preview.findings) ? preview.findings.map((finding) => cleanText(finding?.rule_id, 160)).filter(Boolean) : null;
}
