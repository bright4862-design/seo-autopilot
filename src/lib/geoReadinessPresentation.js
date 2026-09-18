import { evidenceLink, resolveEvidenceUrl } from "./evidenceUrl.js";

const VERSION = "geo_readiness_v1_experimental";
const ADAPTER_VERSION = "geo_evidence_v1";
const BOUNDS_KIND = "unknown_outcome_range_not_statistical_confidence";
const STATUSES = new Set(["assessed", "insufficient_evidence", "access_limited", "not_assessed", "evaluation_error"]);
const DETAIL_CHECKS = new Set(["search_policy", "indexability", "template_integrity"]);
const REPAIR_RULES = Object.freeze({
  search_policy: new Set(["oai_searchbot_blocked", "oai_searchbot_policy", "search_policy", "geo_search_policy"]),
  indexability: new Set(["sitemap_indexability_conflict", "noindex_sitemap_conflict", "geo_indexability"]),
  template_integrity: new Set(["broken_location_template_content", "template_token", "template_integrity", "unresolved_placeholder", "geo_template_integrity"]),
});

const clean = (value) => typeof value === "string" ? value.trim() : "";
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const percent = (value) => `${Math.round(value * 100)}%`;

function validSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  if (value.geo_readiness_version !== VERSION || value.evidence_adapter_version !== ADAPTER_VERSION) return false;
  if (!STATUSES.has(value.assessment_status) || value.bounds_kind !== BOUNDS_KIND) return false;
  if (!Number.isInteger(value.sample_pages) || value.sample_pages < 0 || value.sample_pages > 150) return false;
  if (!finite(value.coverage) || value.coverage < 0 || value.coverage > 1) return false;
  const scored = value.assessment_status === "assessed";
  if (scored !== (Number.isInteger(value.score) && value.score >= 0 && value.score <= 100)) return false;
  if (!scored && value.score !== null) return false;
  if (scored && (value.sample_pages === 0 || value.coverage < 0.8 || value.score_bounds === null)) return false;
  if (value.score_bounds !== null) {
    const bounds = value.score_bounds;
    if (!bounds || typeof bounds !== "object" || Array.isArray(bounds)) return false;
    if (!finite(bounds.lower) || !finite(bounds.upper) || bounds.lower < 0 || bounds.upper > 100 || bounds.lower > bounds.upper) return false;
  }
  return true;
}

function statusLabel(status) {
  if (status === "not_assessed") return "Not assessed for this scan";
  if (status === "evaluation_error") return "GEO readiness unavailable";
  if (status === "access_limited") return "Could not assess because access was limited";
  if (status === "insufficient_evidence") return "Not enough verified evidence to score";
  return "Experimental readiness score";
}

function normalizedUrl(value, origin) {
  const resolved = resolveEvidenceUrl(value, origin);
  if (!resolved) return "";
  try {
    const url = new URL(resolved);
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

function findingUrls(finding, siteOrigin) {
  if (!Array.isArray(finding?.evidence_samples)) return [];
  const seen = new Set();
  return finding.evidence_samples.flatMap((sample) => {
    const link = evidenceLink(sample?.page_url, siteOrigin);
    const key = normalizedUrl(link.href, siteOrigin);
    if (!key || seen.has(key)) return [];
    seen.add(key);
    return [link];
  }).slice(0, 5);
}

function matchingCard(finding, cards, siteOrigin) {
  const supported = REPAIR_RULES[finding.check_id];
  if (!supported) return null;
  const geoUrls = new Set(findingUrls(finding, siteOrigin).map((link) => normalizedUrl(link.href, siteOrigin)));
  if (geoUrls.size === 0) return null;
  return cards.find((card) => {
    const identities = [card?.rule, card?.rootCauseId, card?.root_cause_id].map((value) => clean(value).toLowerCase());
    if (!identities.some((identity) => supported.has(identity))) return false;
    const pages = Array.isArray(card?.evidence?.affectedPages) ? card.evidence.affectedPages : [];
    return pages.some((page) => geoUrls.has(normalizedUrl(page, siteOrigin)));
  }) || null;
}

function fullActions(value, cards, siteOrigin) {
  if (!Array.isArray(value.findings)) return [];
  return value.findings.filter((finding) => {
    return finding && typeof finding === "object" && DETAIL_CHECKS.has(finding.check_id);
  }).map((finding) => {
    const existing = matchingCard(finding, cards, siteOrigin);
    return {
      checkId: finding.check_id,
      label: clean(finding.label),
      affectedPageCount: Number.isInteger(finding.affected_page_count) && finding.affected_page_count >= 0
        ? finding.affected_page_count : 0,
      pages: findingUrls(finding, siteOrigin),
      pagesArePartial: finding.sample_truncated === true,
      existingRepairTitle: clean(existing?.title),
      suggestedAction: existing ? "" : clean(finding.suggested_action),
      verificationStep: existing ? "" : clean(finding.verification_step),
    };
  });
}

function neutral(state, label) {
  return {
    state,
    score: null,
    scoreAvailable: false,
    statusLabel: label,
    sampleLabel: "Assessment sample unavailable",
    coverageLabel: "Evidence coverage unavailable",
    boundsLabel: "",
    methodologyLabel: "Experimental v1 assessment of accepted raw HTML evidence.",
    nonCitationLabel: "This readiness assessment does not measure AI citations, inclusion, visibility, or traffic.",
    completedAt: "",
    actions: [],
  };
}

export function buildGeoReadinessPresentation({
  geoReadiness,
  customerAccess = "",
  cards = [],
  siteOrigin = "",
  completedAt = "",
} = {}) {
  if (geoReadiness == null) return neutral("not_assessed", "Not assessed for this scan");
  if (!validSummary(geoReadiness)) return neutral("unavailable", "GEO readiness unavailable");

  const bounds = geoReadiness.score_bounds;
  const date = new Date(completedAt);
  const canShowDetails = customerAccess === "full" && geoReadiness.authority_verified === true;
  return {
    state: geoReadiness.assessment_status,
    score: geoReadiness.score,
    scoreAvailable: geoReadiness.assessment_status === "assessed",
    statusLabel: statusLabel(geoReadiness.assessment_status),
    sampleLabel: `${geoReadiness.sample_pages} assessed ${geoReadiness.sample_pages === 1 ? "page" : "pages"}`,
    coverageLabel: `${percent(geoReadiness.coverage)} evidence coverage`,
    boundsLabel: bounds ? `${bounds.lower}–${bounds.upper} possible as unresolved checks are completed` : "",
    methodologyLabel: "Experimental v1 assessment of accepted raw HTML evidence.",
    nonCitationLabel: "This readiness assessment does not measure AI citations, inclusion, visibility, or traffic.",
    completedAt: Number.isNaN(date.getTime()) ? "" : date.toISOString(),
    actions: canShowDetails ? fullActions(geoReadiness, Array.isArray(cards) ? cards : [], siteOrigin) : [],
  };
}
