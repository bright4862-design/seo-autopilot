import { RELEASE_COMPONENT_VERSIONS } from "./generatedReleaseContract.js";

export const SAMPLING_DISCLOSURE_VERSION = "sampling_disclosure_v5_selection_language";

/**
 * What a scan chose to look at, in words that say so.
 *
 * Every number here comes from `sampling_report()`'s pre-crawl half -- the URLs
 * selected before the crawl ran -- and the copy called them "represented in the
 * sample" and "sampled", which a customer reads as an observation. It is the
 * same overstatement the section rows carried, in a block the section fix did
 * not reach.
 *
 * There is no outcome to substitute: the crawl records checked coverage per
 * path prefix, not per market or per page family. So the honest correction is
 * the wording. These say "chosen for this scan" and "not chosen", which is
 * exactly what the producer recorded.
 */

// Samplers whose evidence this module knows how to read. The versions below
// are historical records still held in the database; the sampler this build
// actually ships is taken from the release contract rather than restated here.
//
// It used to be restated here, and the checked-coverage change bumped
// SAMPLING_VERSION to v6 without touching the list -- so every new scan fell
// through to `return null` and the disclosure block vanished from the page.
// Nothing failed, because an absent block is indistinguishable from a scan with
// nothing to disclose. Deriving the shipped entry removes the step that has to
// be remembered; a genuinely incompatible rename would still have to add its
// predecessor here, which is a change a reader can see.
export const SUPPORTED_SAMPLING_VERSIONS = new Set([
  "balanced_sitemap_buckets_v2_locale_collapsed_identity_reserve",
  "balanced_sitemap_buckets_v3_locale_collapsed_identity_scope_discovery",
  "balanced_sitemap_buckets_v4_locale_collapsed_identity_scope_discovery_case_preserved",
  "balanced_sitemap_buckets_v5_locale_collapsed_identity_scope_discovery_bounded_prefixes",
  RELEASE_COMPONENT_VERSIONS.sampling_version,
].filter(Boolean));

function clean(value) {
  return String(value || "").trim();
}

function labelFamily(value) {
  return clean(value).replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}

export function samplingDisclosure(record = {}) {
  const evidence = record?.sampling_evidence && typeof record.sampling_evidence === "object"
    ? record.sampling_evidence
    : {};
  const version = clean(record?.sampling_version || evidence?.sampling_version);
  if (!SUPPORTED_SAMPLING_VERSIONS.has(version)) return null;

  const routesDiscovered = Math.max(0, Number(evidence.route_signatures_discovered) || 0);
  const routesSampled = Math.max(0, Number(evidence.route_signatures_sampled) || 0);
  if (routesDiscovered <= 0 && routesSampled <= 0) return null;

  const localeVariantsCollapsed = Math.max(0, Number(evidence.locale_variants_collapsed) || 0);
  const identityDiscovered = Math.max(0, Number(evidence.identity_pages_in_sitemap) || 0);
  const identitySampled = Math.max(0, Number(evidence.identity_pages_sampled) || 0);
  const marketsDiscovered = evidence.markets_discovered && typeof evidence.markets_discovered === "object"
    ? evidence.markets_discovered
    : {};
  const marketsSampled = evidence.markets_sampled && typeof evidence.markets_sampled === "object"
    ? evidence.markets_sampled
    : {};
  const unsampledMarkets = Array.isArray(evidence.markets_never_sampled)
    ? evidence.markets_never_sampled.map(clean).filter(Boolean)
    : [];
  const familyTotals = evidence.family_totals && typeof evidence.family_totals === "object"
    ? evidence.family_totals
    : {};
  const familySampled = evidence.family_sampled && typeof evidence.family_sampled === "object"
    ? evidence.family_sampled
    : {};
  const unsampledFamilies = Array.isArray(evidence.families_never_sampled)
    ? evidence.families_never_sampled.map(clean).filter(Boolean)
    : [];

  const marketNames = Object.keys(marketsDiscovered).filter(Boolean);
  const sampledMarketNames = Object.keys(marketsSampled).filter((market) => Number(marketsSampled[market]) > 0);
  const familyNames = Object.keys(familyTotals).filter(Boolean);
  const sampledFamilyNames = Object.keys(familySampled).filter((family) => Number(familySampled[family]) > 0);

  const marketSummary = marketNames.length > 0
    ? `Markets/languages: ${sampledMarketNames.length} of ${marketNames.length} chosen for this scan.`
    : "";
  const familySummary = familyNames.length > 0
    ? `Page families: ${sampledFamilyNames.length} of ${familyNames.length} chosen for this scan.`
    : "";

  const gaps = [];
  if (unsampledMarkets.length > 0) {
    gaps.push(`Markets not chosen: ${unsampledMarkets.slice(0, 6).join(", ")}${unsampledMarkets.length > 6 ? ` +${unsampledMarkets.length - 6} more` : ""}.`);
  }
  if (unsampledFamilies.length > 0) {
    gaps.push(`Page families not chosen: ${unsampledFamilies.slice(0, 4).map(labelFamily).join(", ")}${unsampledFamilies.length > 4 ? ` +${unsampledFamilies.length - 4} more` : ""}.`);
  }

  return {
    version: SAMPLING_DISCLOSURE_VERSION,
    routesDiscovered,
    routesSelected: routesSampled,
    routesSampled,
    localeVariantsCollapsed,
    identityDiscovered,
    identitySelected: identitySampled,
    identitySampled,
    marketSummary,
    familySummary,
    notChosenSummary: gaps.join(" "),
    unsampledSummary: gaps.join(" "),
  };
}
