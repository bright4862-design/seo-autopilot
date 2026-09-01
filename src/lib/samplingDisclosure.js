export const SAMPLING_DISCLOSURE_VERSION = "sampling_disclosure_v2_scope_discovery_compatible";

const SUPPORTED_SAMPLING_VERSIONS = new Set([
  "balanced_sitemap_buckets_v2_locale_collapsed_identity_reserve",
  "balanced_sitemap_buckets_v3_locale_collapsed_identity_scope_discovery",
]);

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
    ? `Markets/languages: ${sampledMarketNames.length} of ${marketNames.length} represented in the sample.`
    : "";
  const familySummary = familyNames.length > 0
    ? `Page families: ${sampledFamilyNames.length} of ${familyNames.length} represented in the sample.`
    : "";

  const gaps = [];
  if (unsampledMarkets.length > 0) {
    gaps.push(`Unsampled markets: ${unsampledMarkets.slice(0, 6).join(", ")}${unsampledMarkets.length > 6 ? ` +${unsampledMarkets.length - 6} more` : ""}.`);
  }
  if (unsampledFamilies.length > 0) {
    gaps.push(`Unsampled page families: ${unsampledFamilies.slice(0, 4).map(labelFamily).join(", ")}${unsampledFamilies.length > 4 ? ` +${unsampledFamilies.length - 4} more` : ""}.`);
  }

  return {
    version: SAMPLING_DISCLOSURE_VERSION,
    routesDiscovered,
    routesSampled,
    localeVariantsCollapsed,
    identityDiscovered,
    identitySampled,
    marketSummary,
    familySummary,
    unsampledSummary: gaps.join(" "),
  };
}
