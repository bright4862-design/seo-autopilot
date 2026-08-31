export const FOCUSED_SCAN_SCOPE_VERSION = "focused_scan_scope_v1_same_origin_path_prefix";

const LOCALE_SEGMENT_RE = /^[a-z]{2}(?:-[a-z]{2})?$/i;
const SAFE_DISCOVERY_SOURCES = new Set(["sitemap", "internal_link", "canonical", "hreflang"]);
const BLOCKED_SECTION_SEGMENTS = new Set([
  "api", "assets", "asset", "static", "media", "images", "img", "fonts", "scripts", "js", "css",
  "cdn-cgi", "wp-admin", "wp-content", "login", "signin", "sign-in", "signup", "sign-up", "register",
  "account", "my-account", "cart", "basket", "panier", "checkout", "admin", "auth",
]);

function clean(value) {
  return String(value || "").trim();
}

export function normalizeScopeOrigin(value) {
  const raw = clean(value);
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/.test(url.protocol) || !url.hostname || url.username || url.password) return "";
    url.hash = "";
    url.search = "";
    url.pathname = "/";
    return url.origin;
  } catch {
    return "";
  }
}

export function normalizeRequestedPathPrefix(value) {
  const raw = clean(value);
  if (!raw || raw === "/") return "";
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith("//")) return "";
  try {
    const parsed = new URL(raw.startsWith("/") ? raw : `/${raw}`, "https://scope.invalid");
    if (parsed.origin !== "https://scope.invalid" || parsed.search || parsed.hash) return "";
    const segments = parsed.pathname.split("/").filter(Boolean);
    if (segments.length === 0) return "";
    for (const segment of segments) {
      let decoded = segment;
      try {
        decoded = decodeURIComponent(segment);
      } catch {
        return "";
      }
      if (!decoded || decoded === "." || decoded === ".." || decoded.includes("/") || decoded.includes("\\")) return "";
    }
    return `/${segments.join("/")}`;
  } catch {
    return "";
  }
}

export function displayPathPrefix(value) {
  const prefix = normalizeRequestedPathPrefix(value);
  return prefix ? `${prefix}/` : "/";
}

export function focusedScanFingerprintTarget(websiteUrl, pathPrefix = "") {
  const raw = clean(websiteUrl);
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/.test(url.protocol) || !url.hostname) return "";
    url.hash = "";
    url.hostname = url.hostname.toLowerCase().replace(/\.$/, "");
    url.pathname = (url.pathname || "/").replace(/\/{2,}/g, "/");
    url.searchParams.sort();
    const target = url.href;
    const prefix = normalizeRequestedPathPrefix(pathPrefix);
    return prefix ? `${target}|path:${prefix}` : target;
  } catch {
    return "";
  }
}

export function normalizeDiscoverySource(value) {
  const source = clean(value).toLowerCase();
  return SAFE_DISCOVERY_SOURCES.has(source) ? source : "sitemap";
}


export function focusedScopeFromSearchParams(params) {
  if (!params || typeof params.get !== "function") return null;
  const scopeType = clean(params.get("scope_type")).toLowerCase();
  if (scopeType !== "path_prefix") return null;
  const parentScanId = clean(params.get("parent_scan_id"));
  const requestedOrigin = normalizeScopeOrigin(params.get("origin") || params.get("requested_origin"));
  const requestedPathPrefix = normalizeRequestedPathPrefix(params.get("path_prefix") || params.get("requested_path_prefix"));
  const discoveredFrom = normalizeDiscoverySource(params.get("discovered_from"));
  if (!parentScanId || !requestedOrigin || !requestedPathPrefix) return null;
  return {
    scope_type: "path_prefix",
    parent_scan_id: parentScanId,
    requested_origin: requestedOrigin,
    requested_path_prefix: requestedPathPrefix,
    discovered_from: discoveredFrom,
  };
}

export function focusedSectionUrl(scope = {}) {
  const origin = normalizeScopeOrigin(scope.requested_origin);
  const prefix = normalizeRequestedPathPrefix(scope.requested_path_prefix);
  if (!origin || !prefix) return "";
  return `${origin}${prefix}/`;
}


export function focusedSectionOnboardingPath(parentScanId, section = {}) {
  const parent = clean(parentScanId);
  const origin = normalizeScopeOrigin(section.requested_origin);
  const prefix = normalizeRequestedPathPrefix(section.requested_path_prefix);
  const source = normalizeDiscoverySource(section.discovered_from);
  if (!parent || !origin || !prefix) return "";
  const params = new URLSearchParams({
    scope_type: "path_prefix",
    parent_scan_id: parent,
    origin,
    path_prefix: prefix,
    discovered_from: source,
  });
  return `/onboarding?${params.toString()}`;
}

function sectionLabel(prefix) {
  const segment = normalizeRequestedPathPrefix(prefix).split("/").filter(Boolean)[0] || "";
  if (LOCALE_SEGMENT_RE.test(segment)) return `${segment.toUpperCase()} folder`;
  return segment ? `${segment.replace(/[-_]+/g, " ")} section` : "Site section";
}

export function focusedPathSections(record = {}) {
  const evidence = record?.sampling_evidence && typeof record.sampling_evidence === "object"
    ? record.sampling_evidence
    : {};
  const pagesFound = Math.max(0, Number(record?.pages_found || evidence?.sitemap_urls_discovered) || 0);
  if (pagesFound <= 150) return [];

  const discovered = evidence.path_prefixes_discovered && typeof evidence.path_prefixes_discovered === "object"
    ? evidence.path_prefixes_discovered
    : {};
  const sampled = evidence.path_prefixes_sampled && typeof evidence.path_prefixes_sampled === "object"
    ? evidence.path_prefixes_sampled
    : {};
  const marketDiscovered = evidence.markets_discovered && typeof evidence.markets_discovered === "object"
    ? evidence.markets_discovered
    : {};
  const marketSampled = evidence.markets_sampled && typeof evidence.markets_sampled === "object"
    ? evidence.markets_sampled
    : {};

  const candidates = new Map();
  for (const [rawPrefix, count] of Object.entries(discovered)) {
    const prefix = normalizeRequestedPathPrefix(rawPrefix);
    const discoveredCount = Math.max(0, Number(count) || 0);
    const segment = prefix.split("/").filter(Boolean)[0]?.toLowerCase() || "";
    if (!prefix || discoveredCount < 8 || BLOCKED_SECTION_SEGMENTS.has(segment)) continue;
    candidates.set(prefix, {
      prefix,
      discovered: discoveredCount,
      sampled: Math.max(0, Number(sampled[rawPrefix] ?? sampled[prefix]) || 0),
      discoveredFrom: "sitemap",
    });
  }
  for (const [market, count] of Object.entries(marketDiscovered)) {
    const prefix = normalizeRequestedPathPrefix(`/${market}`);
    const discoveredCount = Math.max(0, Number(count) || 0);
    const marketSegment = prefix.split("/").filter(Boolean)[0]?.toLowerCase() || "";
    if (!prefix || discoveredCount < 8 || BLOCKED_SECTION_SEGMENTS.has(marketSegment)) continue;
    const existing = candidates.get(prefix);
    candidates.set(prefix, {
      prefix,
      discovered: Math.max(existing?.discovered || 0, discoveredCount),
      sampled: Math.max(existing?.sampled || 0, Math.max(0, Number(marketSampled[market]) || 0)),
      discoveredFrom: "sitemap",
    });
  }

  const origin = normalizeScopeOrigin(record?.website_url || record?.submitted_url || record?.final_url);
  if (!origin) return [];

  return [...candidates.values()]
    .map((section) => ({
      scope_type: "path_prefix",
      requested_origin: origin,
      requested_path_prefix: section.prefix,
      discovered_from: section.discoveredFrom,
      user_confirmed: true,
      label: sectionLabel(section.prefix),
      discovered: section.discovered,
      sampled: section.sampled,
      coverage: section.discovered > 0 ? Math.min(1, section.sampled / section.discovered) : 0,
    }))
    .sort((a, b) => (a.coverage - b.coverage) || (b.discovered - a.discovered) || a.requested_path_prefix.localeCompare(b.requested_path_prefix))
    .slice(0, 8);
}
