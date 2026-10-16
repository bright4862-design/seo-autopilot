// Stage-4 compatibility contract for evidence readers.
//
// This module is intentionally side-effect free. It does not sign, persist, or
// rewrite reports. The serialized integrator can use it when wiring new Stage-2
// and Stage-3 evidence into the existing authority readers.

export const HISTORICAL_AUTHORITY_VERSIONS = Object.freeze([
  "standard_review_snapshot_hmac_v1",
  "standard_review_snapshot_hmac_v2_coverage",
  "standard_review_snapshot_hmac_v3_acceptance_evidence",
  "standard_review_snapshot_hmac_v4_focused_scope",
  "standard_review_snapshot_hmac_v5_score_explanation",
  "standard_review_snapshot_hmac_v6_report_evidence",
  "standard_review_snapshot_hmac_geo_v1",
]);

export const CURRENT_IDENTITY_AUTHORITY_VERSION = "standard_review_snapshot_hmac_identity_v1";
export const CURRENT_IDENTITY_EVIDENCE_VERSION = "evidence_url_identity_v2_published_route";
export const CURRENT_REPAIR_COVERAGE_VERSION = "repair_coverage_v5_published_route_identity";

// These are versioned evidence records already produced by isolated Stage-2
// lanes. Listing them here does not make them authoritative by itself: they
// still have to be covered by the signed canonical report before customer use.
export const KNOWN_STAGE2_OBSERVED_EVIDENCE_VERSIONS = Object.freeze([
  "link_integrity_probe_v1_unsampled_same_site",
  "soft_404_probe_v1_active_baseline",
  "redirect_meaning_v1_semantic_destination_fit",
  "sitemap_integrity_probe_v1_shared_scheduler",
  "url_variant_probe_v1_bounded_exact_identity",
]);

const HISTORICAL = new Set(HISTORICAL_AUTHORITY_VERSIONS);
const KNOWN_STAGE2 = new Set(KNOWN_STAGE2_OBSERVED_EVIDENCE_VERSIONS);

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Classify an authority/evidence envelope without mutating it.
 *
 * Historical seals intentionally ignore new evidence markers so their original
 * reconstruction bytes remain unchanged. The identity seal requires the
 * current identity/coverage versions. Any explicit observed-evidence marker is
 * fail-closed unless it is in the approved Stage-2 registry.
 */
export function classifyEvidenceCompatibility(envelope) {
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
    return { readable: false, mode: "rejected", reason: "invalid_envelope" };
  }
  const seal = clean(envelope.authority_seal_version);
  if (HISTORICAL.has(seal)) {
    return { readable: true, mode: "historical", reason: "historical_reconstruction_unchanged" };
  }
  if (seal !== CURRENT_IDENTITY_AUTHORITY_VERSION) {
    return { readable: false, mode: "rejected", reason: "unknown_authority_seal_version" };
  }

  const identity = clean(envelope.evidence_url_identity_version);
  if (identity !== CURRENT_IDENTITY_EVIDENCE_VERSION) {
    return { readable: false, mode: "rejected", reason: "unknown_evidence_url_identity_version" };
  }
  const coverage = clean(envelope.repair_coverage_version);
  if (coverage !== CURRENT_REPAIR_COVERAGE_VERSION) {
    return { readable: false, mode: "rejected", reason: "unknown_repair_coverage_version" };
  }

  const observed = clean(envelope.observed_evidence_version);
  if (observed && !KNOWN_STAGE2.has(observed)) {
    return { readable: false, mode: "rejected", reason: "unknown_observed_evidence_version" };
  }
  if (observed) {
    const pages = envelope.verified_observed_pages;
    if (!Array.isArray(pages) || pages.length === 0 || pages.length > 150
        || pages.some((value) => typeof value !== "string" || !value.trim() || value.length > 2000)) {
      return { readable: false, mode: "rejected", reason: "invalid_verified_observed_pages" };
    }
  }

  return {
    readable: true,
    mode: observed ? "current_with_observed_evidence" : "current_identity",
    reason: "supported_current_evidence",
  };
}

/** Throwing form for call sites that must fail closed before reconstruction. */
export function requireReadableEvidence(envelope) {
  const result = classifyEvidenceCompatibility(envelope);
  if (!result.readable) throw new Error(`unsupported evidence compatibility: ${result.reason}`);
  return result;
}
