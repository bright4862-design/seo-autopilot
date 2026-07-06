import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runAdvancedScan_v11_ssrf_hardened_screaming_frog_lite";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const USER_AGENT = "Mozilla/5.0 (compatible; SEOAutopilotBot/1.0; +https://base44.app)";
const FETCH_TIMEOUT_MS = 12000;
const SITEMAP_FETCH_TIMEOUT_MS = 8000;
const MAX_REDIRECTS = 4;
const MAX_BODY_CHARS = 1_500_000;

const MODE_LIMITS: Record<string, { max_pages: number; crawl_timeout_ms: number; concurrency: number; use_sitemap: boolean }> = {
  basic: { max_pages: 25, crawl_timeout_ms: 35000, concurrency: 3, use_sitemap: false },
  quick: { max_pages: 40, crawl_timeout_ms: 45000, concurrency: 3, use_sitemap: true },
  deep: { max_pages: 85, crawl_timeout_ms: 75000, concurrency: 4, use_sitemap: true },
  advanced: { max_pages: 150, crawl_timeout_ms: 90000, concurrency: 5, use_sitemap: true },
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, error: "Unauthorized" }, 401);

    const body = await safeReadJson(req);
    const budget = resolveBudget(body);
    const websiteUrl = normalizeWebsiteUrl(body.website_url || body.url || "");

    if (!websiteUrl) return jsonResponse({ success: false, error: "Missing or invalid website_url." }, 400);

    const safety = await validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) {
      return jsonResponse({ success: false, version: VERSION, error: safety.reason }, 400);
    }

    const deadlineAt = Date.now() + budget.crawl_timeout_ms - 3000;
    const crawlResult = await crawlWebsite({ startUrl: websiteUrl, body, budget, deadlineAt });
    const screamingFrogLite = runScreamingFrogLiteAudit({ pages: crawlResult.pages, startUrl: websiteUrl });
    const coverageFindings = buildCoverageFindings({ pages: crawlResult.pages, startUrl: websiteUrl });
    const allRawFindings = [...coverageFindings, ...screamingFrogLite.raw_findings];
    const groupedFindings = groupFindings(allRawFindings);
    const healthScore = calculateHealthScore({ pages: crawlResult.pages, findings: groupedFindings, technicalSummary: screamingFrogLite.technical_audit_summary });
    const scanSummary = buildScanSummary({ websiteUrl, body, healthScore, pages: crawlResult.pages, findings: groupedFindings, technicalSummary: screamingFrogLite.technical_audit_summary, crawlResult });

    return jsonResponse({
      success: true,
      version: VERSION,
      website_url: websiteUrl,
      business_name: body.business_name || "",
      scan_mode: budget.scan_mode,
      max_pages_requested: body.max_pages === undefined ? null : Number(body.max_pages),
      max_pages_effective: budget.max_pages,
      max_competitors_effective: 0,
      pages_found: crawlResult.pages_found,
      pages_crawled: crawlResult.pages.length,
      queued_remaining: crawlResult.queued_remaining,
      health_score: healthScore,
      seo_score: healthScore,
      scan_summary: scanSummary,
      site_summary: scanSummary,
      important_page_patterns: crawlResult.important_page_patterns,
      deprioritized_page_patterns: crawlResult.deprioritized_page_patterns,
      recommended_followup_scans: [],
      sitemap_priority_summary: crawlResult.sitemap_priority_summary,
      technical_audit_summary: screamingFrogLite.technical_audit_summary,
      screaming_frog_lite: {
        enabled: true,
        audit_profile: "screaming_frog_lite",
        raw_findings_count: screamingFrogLite.raw_findings.length,
        grouped_findings_count: groupedFindings.length,
      },
      browser_rendering: {
        enabled: false,
        provider: "",
        mode: "disabled_for_ssrf_safe_launch",
        max_attempts_per_scan: 0,
        crawl_attempts_used: 0,
        competitor_attempts_used: 0,
        crawl_attempts_max: 0,
        competitor_attempts_max: 0,
        usage_policy: "Browserless is disabled in this hardened launch build so user-entered URLs are not forwarded to a separate server-side browser service.",
      },
      crawl_scope: crawlResult.crawl_scope,
      crawl_warnings: crawlResult.warnings,
      competitor_results: [],
      competitor_opportunities: [],
      discovered_competitors: [],
      competitor_result: {
        competitor_results: [],
        competitor_opportunities: [],
        browser_render_attempts_used: 0,
        browser_render_attempts_max: 0,
        skipped: true,
        reason: "Competitor checks are disabled in this launch build so the main scan stays reliable and SSRF-safe.",
      },
      raw_findings: allRawFindings,
      grouped_findings: groupedFindings,
      raw_fixes: groupedFindings,
      fixes: groupedFindings,
      findings: groupedFindings,
      recommendations: groupedFindings,
      issues: groupedFindings,
      crawled_pages: crawlResult.pages,
      pages: crawlResult.pages,
      scanned_pages: crawlResult.pages,
      crawl_pages: crawlResult.pages,
      debug: {
        version: VERSION,
        budget,
        ssrf_hardened: true,
        security_policy: "Only public http/https URLs on the original same origin are fetched. Local, private, link-local, reserved, credentialed, custom-port, and cross-origin redirect targets are blocked before network requests continue.",
        skipped_urls: crawlResult.skipped_urls,
        sitemap_entries_found: crawlResult.sitemap_entries_found,
        request_received_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    return jsonResponse({ success: false, version: VERSION, error: getErrorMessage(error) }, 500);
  }
});

async function safeReadJson(req: Request) {
  try { return await req.json(); } catch { return {}; }
}

function jsonResponse(data: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...CORS_HEADERS, "Content-Type": "application/json; charset=utf-8" } });
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}

function resolveBudget(body: any) {
  const requestedMode = String(body.scan_mode || "deep").toLowerCase();
  const scanMode = MODE_LIMITS[requestedMode] ? requestedMode : "deep";
  const defaults = MODE_LIMITS[scanMode];
  const requestedMaxPages = Number(body.max_pages || 0);
  const requestedTimeout = Number(body.crawl_timeout_ms || 0);

  return {
    scan_mode: scanMode,
    max_pages: requestedMaxPages > 0 ? Math.max(1, Math.min(defaults.max_pages, requestedMaxPages)) : defaults.max_pages,
    max_competitors: 0,
    max_browser_render_attempts: 0,
    crawl_timeout_ms: requestedTimeout > 0 ? Math.max(20000, Math.min(defaults.crawl_timeout_ms, requestedTimeout)) : defaults.crawl_timeout_ms,
    concurrency: defaults.concurrency,
    use_sitemap: defaults.use_sitemap,
  };
}

function normalizeWebsiteUrl(value: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const parsed = new URL(withProtocol);
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "";
  }
}

async function validatePublicHttpUrl(value: string) {
  try {
    const parsed = new URL(value);
    const syntax = validateUrlSyntax(parsed);
    if (!syntax.ok) return syntax;
    const dns = await validateDnsPublic(parsed.hostname);
    if (!dns.ok) return dns;
    return { ok: true, reason: "" };
  } catch {
    return { ok: false, reason: "Invalid URL." };
  }
}

function validateUrlSyntax(parsed: URL) {
  if (!/^https?:$/i.test(parsed.protocol)) return { ok: false, reason: "Only http and https URLs can be scanned." };
  if (parsed.username || parsed.password) return { ok: false, reason: "URLs with embedded credentials cannot be scanned." };
  if (parsed.port && !["80", "443"].includes(parsed.port)) return { ok: false, reason: "Only standard web ports 80 and 443 can be scanned." };
  const host = normalizeHost(parsed.hostname);
  if (!host || isBlockedHost(host)) return { ok: false, reason: "Local, private, or reserved hosts cannot be scanned." };
  if (isIpLiteral(host) && isPrivateOrReservedIp(host)) return { ok: false, reason: "Private or reserved IP addresses cannot be scanned." };
  return { ok: true, reason: "" };
}

async function validateDnsPublic(hostname: string) {
  const host = normalizeHost(hostname);
  if (isIpLiteral(host)) return isPrivateOrReservedIp(host) ? { ok: false, reason: "Private or reserved IP addresses cannot be scanned." } : { ok: true, reason: "" };
  const addresses: string[] = [];
  try { addresses.push(...(await Deno.resolveDns(host, "A"))); } catch {}
  try { addresses.push(...(await Deno.resolveDns(host, "AAAA"))); } catch {}
  for (const address of addresses) {
    if (isPrivateOrReservedIp(address)) return { ok: false, reason: "This hostname resolves to a private or reserved network address." };
  }
  return { ok: true, reason: "" };
}

function normalizeHost(value: string) {
  return String(value || "").trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "").replace(/\.$/, "");
}

function isBlockedHost(hostname: string) {
  const host = normalizeHost(hostname);
  return !host || host === "localhost" || host.includes("localhost") || host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal") || host.endsWith(".lan") || host.endsWith(".home") || host.endsWith(".corp") || host.endsWith(".test") || host.endsWith(".invalid") || host.endsWith(".example");
}

function isIpLiteral(hostname: string) {
  const host = normalizeHost(hostname);
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.includes(":");
}

function isPrivateOrReservedIp(value: string) {
  const ip = normalizeHost(value);
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) {
    const parts = ip.split(".").map(Number);
    if (parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return true;
    const [a, b] = parts;
    if (a === 0 || a === 10 || a === 127 || a >= 224) return true;
    if (a === 169 && b === 254) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 100 && b >= 64 && b <= 127) return true;
    return false;
  }
  if (ip.includes(":")) {
    const compact = ip.toLowerCase();
    return compact === "::" || compact === "::1" || compact.startsWith("fc") || compact.startsWith("fd") || compact.startsWith("fe80") || compact.startsWith("ff") || compact.startsWith("0:");
  }
  return false;
}

async function safeFetch(url: string, timeoutMs: number, allowedOrigin: string) {
  let currentUrl = cleanUrl(url);
  for (let redirectCount = 0; redirectCount <= MAX_REDIRECTS; redirectCount += 1) {
    await assertAllowedFetchTarget(currentUrl, allowedOrigin);
    const response = await fetchWithTimeoutNoRedirect(currentUrl, timeoutMs);
    if (![301, 302, 303, 307, 308].includes(response.status)) return response;
    const location = response.headers.get("location") || "";
    if (!location) return response;
    const nextUrl = cleanUrl(new URL(location, currentUrl).toString());
    await assertAllowedFetchTarget(nextUrl, allowedOrigin);
    currentUrl = nextUrl;
  }
  throw new Error("Too many redirects while fetching page.");
}

async function assertAllowedFetchTarget(url: string, allowedOrigin: string) {
  const parsed = new URL(url);
  const syntax = validateUrlSyntax(parsed);
  if (!syntax.ok) throw new Error(syntax.reason);
  if (parsed.origin !== allowedOrigin) throw new Error("Cross-origin redirects or fetches are not allowed during scans.");
  const dns = await validateDnsPublic(parsed.hostname);
  if (!dns.ok) throw new Error(dns.reason);
}

async function fetchWithTimeoutNoRedirect(url: string, timeoutMs: number) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      method: "GET",
      redirect: "manual",
      signal: controller.signal,
      headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9" },
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function crawlWebsite({ startUrl, body, budget, deadlineAt }: { startUrl: string; body: any; budget: any; deadlineAt: number }) {
  const start = new URL(startUrl);
  const origin = start.origin;
  const requestedPathPrefix = normalizeRequestedPathPrefix(body.crawl_path_prefix || body.start_path_prefix || "");
  const crawlPathPrefix = requestedPathPrefix || detectLanguagePrefix(start.pathname);
  const queue: Array<{ url: string; source: string; in_sitemap: boolean }> = [];
  const discovered = new Set<string>();
  const fetched = new Set<string>();
  const skippedUrls: Record<string, number> = {};
  const warnings: string[] = [];

  function noteSkip(reason: string) { skippedUrls[reason] = Number(skippedUrls[reason] || 0) + 1; }
  function addToQueue(url: string, source: string, inSitemap = false) {
    const cleaned = cleanUrl(url);
    if (!cleaned || discovered.has(cleaned)) return;
    const check = shouldCrawlUrl({ url: cleaned, origin, pathPrefix: crawlPathPrefix });
    if (!check.ok) { noteSkip(check.reason); return; }
    discovered.add(cleaned);
    queue.push({ url: cleaned, source, in_sitemap: inSitemap });
  }

  addToQueue(startUrl, "start", false);

  if (budget.use_sitemap && Date.now() < deadlineAt - 5000) {
    for (const entry of await discoverSitemapEntries({ origin, pathPrefix: crawlPathPrefix, deadlineAt, maxUrls: budget.max_pages * 3, noteSkip })) {
      if (queue.length >= budget.max_pages * 3) break;
      addToQueue(entry.url, "sitemap", true);
    }
  }

  const pages: any[] = [];
  while (queue.length > 0 && pages.length < budget.max_pages && Date.now() < deadlineAt) {
    const batch = queue.splice(0, budget.concurrency).filter((item) => {
      const cleaned = cleanUrl(item.url);
      if (!cleaned || fetched.has(cleaned)) return false;
      fetched.add(cleaned);
      return true;
    });
    if (batch.length === 0) break;
    const results = await Promise.all(batch.map((item) => fetchAndExtractPage({ ...item, origin })));
    for (const page of results) {
      if (crawlPathPrefix && page.final_url && !isInsidePathPrefix(page.final_url, crawlPathPrefix)) { noteSkip("outside_prefix_after_redirect"); continue; }
      pages.push(page);
      if (page.status_code >= 200 && page.status_code < 300 && !page.is_scanner_blocked) {
        for (const link of page.internal_links || []) {
          if (pages.length + queue.length >= budget.max_pages * 3) break;
          addToQueue(link, page.source === "start" ? "homepage_link" : "internal", false);
        }
      }
    }
  }

  if (Date.now() >= deadlineAt) warnings.push("The scan returned a partial result before the function timeout limit.");
  if (crawlPathPrefix) warnings.push(`The scan was locked to ${crawlPathPrefix} pages so unrelated sections were ignored.`);
  if (pages.length > 0 && pages.filter(isReadablePage).length === 0) warnings.push("The scanner could not read normal page content. The website may be blocking crawler requests or requiring JavaScript rendering.");

  return {
    pages,
    pages_found: discovered.size,
    queued_remaining: queue.length,
    warnings,
    crawl_scope: { locked_to_start_language: Boolean(crawlPathPrefix), start_path_prefix: crawlPathPrefix || "", origin, security_scope: "same-origin-public-http-only" },
    sitemap_entries_found: Math.max(0, discovered.size - 1),
    important_page_patterns: crawlPathPrefix ? [crawlPathPrefix] : ["/"],
    deprioritized_page_patterns: ["/cart/", "/checkout/", "/login/", "/account/", "/search/", "/tag/", "/author/", "/feed/"],
    skipped_urls: skippedUrls,
    sitemap_priority_summary: { strategy: "The scanner reads same-origin sitemap URLs, manually validates redirects, and blocks private/local/reserved network targets before every fetch.", max_pages_enforced: budget.max_pages, skipped_urls: skippedUrls },
  };

  async function fetchAndExtractPage({ url, source, in_sitemap, origin }: { url: string; source: string; in_sitemap: boolean; origin: string }) {
    let html = "", statusCode = 0, finalUrl = url, fetchError = "", fetchErrorClass = "", contentType = "";
    try {
      const response = await safeFetch(url, FETCH_TIMEOUT_MS, origin);
      statusCode = response.status;
      finalUrl = cleanUrl(response.url || url);
      contentType = response.headers.get("content-type") || "";
      if (/text\/html|application\/xhtml/i.test(contentType)) html = (await response.text()).slice(0, MAX_BODY_CHARS);
      fetchErrorClass = classifyFetchError(new Error(`HTTP ${statusCode}`), statusCode);
      if (!fetchErrorClass || fetchErrorClass === "other") fetchErrorClass = "";
    } catch (error) {
      fetchError = getErrorMessage(error);
      fetchErrorClass = classifyFetchError(error);
    }
    return extractPageFromHtml({ url, finalUrl, html, statusCode, source, origin, inSitemap: in_sitemap, fetchError, fetchErrorClass });
  }
}

async function discoverSitemapEntries({ origin, pathPrefix, deadlineAt, maxUrls, noteSkip }: { origin: string; pathPrefix: string; deadlineAt: number; maxUrls: number; noteSkip: (reason: string) => void }) {
  const sitemapQueue = [`${origin}/sitemap.xml`, `${origin}/sitemap_index.xml`];
  const visited = new Set<string>();
  const pageEntries = new Map<string, any>();
  try {
    const robots = await fetchText(`${origin}/robots.txt`, SITEMAP_FETCH_TIMEOUT_MS, origin);
    for (const line of robots.split(/\r?\n/)) {
      const match = line.match(/^sitemap:\s*(.+)$/i);
      if (match?.[1]) {
        const cleaned = cleanUrl(new URL(match[1].trim(), origin).toString());
        const check = shouldCrawlUrl({ url: cleaned, origin, pathPrefix: "" });
        if (check.ok) sitemapQueue.push(cleaned);
      }
    }
  } catch {}
  while (sitemapQueue.length > 0 && pageEntries.size < maxUrls && Date.now() < deadlineAt - 5000) {
    const sitemapUrl = sitemapQueue.shift();
    if (!sitemapUrl || visited.has(sitemapUrl)) continue;
    visited.add(sitemapUrl);
    try {
      const xml = await fetchText(sitemapUrl, SITEMAP_FETCH_TIMEOUT_MS, origin);
      for (const loc of parseLocTags(xml)) {
        const cleaned = cleanUrl(new URL(loc, origin).toString());
        if (!cleaned) continue;
        if (/\.xml(\?|$)/i.test(cleaned)) { if (sitemapQueue.length < 25) sitemapQueue.push(cleaned); continue; }
        const check = shouldCrawlUrl({ url: cleaned, origin, pathPrefix });
        if (!check.ok) { noteSkip(check.reason); continue; }
        pageEntries.set(cleaned, { url: cleaned, source_sitemap: sitemapUrl });
      }
    } catch {}
  }
  return [...pageEntries.values()].slice(0, maxUrls);
}

async function fetchText(url: string, timeoutMs: number, origin: string) {
  const response = await safeFetch(url, timeoutMs, origin);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return (await response.text()).slice(0, MAX_BODY_CHARS);
}

function shouldCrawlUrl({ url, origin, pathPrefix }: { url: string; origin: string; pathPrefix: string }) {
  try {
    const parsed = new URL(url);
    if (parsed.origin !== origin) return { ok: false, reason: "external" };
    const syntax = validateUrlSyntax(parsed);
    if (!syntax.ok) return { ok: false, reason: "unsafe_url" };
    if (pathPrefix) {
      const path = normalizePath(parsed.pathname);
      if (path !== pathPrefix && !path.startsWith(`${pathPrefix}/`)) return { ok: false, reason: "outside_prefix" };
    }
    if (isProbablyAsset(parsed.pathname)) return { ok: false, reason: "asset" };
    if (isUtilityUrl(parsed.pathname)) return { ok: false, reason: "utility" };
    if (isLikelyEncodedOrJunkUrl(parsed.pathname)) return { ok: false, reason: "junk" };
    return { ok: true, reason: "" };
  } catch { return { ok: false, reason: "invalid" }; }
}

function cleanUrl(value: string) {
  try {
    const parsed = new URL(value);
    parsed.hash = "";
    for (const param of ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"]) parsed.searchParams.delete(param);
    parsed.search = parsed.searchParams.toString() ? `?${parsed.searchParams.toString()}` : "";
    return parsed.toString();
  } catch { return ""; }
}

function normalizeRequestedPathPrefix(value: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const cleaned = raw.startsWith("/") ? raw : `/${raw}`;
  const withoutTrailingSlash = cleaned !== "/" && cleaned.endsWith("/") ? cleaned.slice(0, -1) : cleaned;
  return withoutTrailingSlash === "/" ? "" : withoutTrailingSlash;
}

function detectLanguagePrefix(pathname: string) {
  const first = String(pathname || "/").split("/").filter(Boolean)[0] || "";
  return /^[a-z]{2}(-[a-z]{2})?$/i.test(first) ? `/${first}` : "";
}

function isInsidePathPrefix(value: string, prefix: string) {
  try { const path = normalizePath(new URL(value).pathname); return path === prefix || path.startsWith(`${prefix}/`); } catch { return false; }
}

function normalizePath(pathname: string) {
  let path = String(pathname || "/");
  path = path.startsWith("/") ? path : `/${path}`;
  path = path.replace(/\/+/g, "/");
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

function isProbablyAsset(pathname: string) {
  return /\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|rar|7z|css|js|mjs|woff|woff2|ttf|eot|mp4|mp3|avi|mov|xml)$/i.test(pathname);
}

function isUtilityUrl(pathname: string) {
  const blocked = new Set(["cart", "checkout", "login", "logout", "account", "my-account", "privacy", "terms", "cookie", "cookies", "legal", "search", "tag", "author", "feed", "preview", "wp-admin", "wp-json"]);
  return String(pathname || "").toLowerCase().split("/").filter(Boolean).some((segment) => blocked.has(segment));
}

function isLikelyEncodedOrJunkUrl(pathname: string) {
  for (const part of String(pathname || "").split("/").filter(Boolean).map(safeDecodeURIComponent)) {
    const cleaned = part.trim();
    if (!cleaned) continue;
    const base64ish = cleaned.length >= 22 && /^[A-Za-z0-9+/=_-]+$/.test(cleaned) && /[A-Z]/.test(cleaned) && /[a-z]/.test(cleaned) && !cleaned.includes("-");
    if (!base64ish) continue;
    try { const decoded = atob(cleaned.replace(/-/g, "+").replace(/_/g, "/")); if (/^https?:\/\//i.test(decoded) || decoded.startsWith("/")) return true; } catch { if (cleaned.length >= 32) return true; }
  }
  return false;
}

function safeDecodeURIComponent(value: string) { try { return decodeURIComponent(value); } catch { return value; } }
function parseLocTags(xml: string) { return [...String(xml || "").matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi)].map((match) => decodeHtmlEntities(match[1] || "").trim()).filter(Boolean); }

function extractPageFromHtml({ url, finalUrl, html, statusCode, source, origin, inSitemap, fetchError, fetchErrorClass }: { url: string; finalUrl: string; html: string; statusCode: number; source: string; origin: string; inSitemap: boolean; fetchError: string; fetchErrorClass: string }) {
  const title = extractTitle(html);
  const metaDescription = extractMeta(html, "description");
  const robotsMeta = extractMeta(html, "robots");
  const viewport = extractMeta(html, "viewport");
  const canonicalUrl = extractCanonical(html, finalUrl || url);
  const h1s = extractAllH1(html);
  const text = stripHtmlToText(html);
  const wordCount = text ? text.split(/\s+/).filter(Boolean).length : 0;
  const scriptCount = countMatches(html, /<script\b/gi);
  const imageCount = countMatches(html, /<img\b/gi);
  const missingAltImageCount = countImagesMissingAlt(html);
  const schemaCount = countMatches(html, /<script[^>]+type=["']application\/ld\+json["']/gi);
  const ogCount = countMatches(html, /<meta[^>]+property=["']og:/gi);
  const internalLinks = extractInternalLinks(html, finalUrl || url, origin);
  const externalLinks = extractExternalLinks(html, finalUrl || url, origin);
  const isScannerBlocked = detectBlocked({ html, text, statusCode, title });
  return {
    url: cleanUrl(url), final_url: cleanUrl(finalUrl || url), original_url: cleanUrl(url), source, status_code: statusCode, fetch_error: fetchError, fetch_error_class: fetchErrorClass || "",
    title, meta_description: metaDescription, h1: h1s[0] || "", h1s, h1_count: h1s.length, canonical_url: canonicalUrl, robots_meta: robotsMeta, viewport,
    word_count: wordCount, text_length: text.length, html_size: html.length, script_count: scriptCount, stylesheet_count: countMatches(html, /<link[^>]+rel=["']?stylesheet/gi), image_count: imageCount, missing_alt_image_count: missingAltImageCount, schema_count: schemaCount, open_graph_tag_count: ogCount,
    internal_links: internalLinks, internal_link_count: internalLinks.length, external_links: externalLinks, external_link_count: externalLinks.length, discovery_links: internalLinks, discovery_link_count: internalLinks.length,
    indexable: !/noindex/i.test(robotsMeta || ""), in_sitemap: inSitemap, is_scanner_blocked: isScannerBlocked, fetched_by_browser_render: false, importance_score: source === "start" ? 10000 : source === "sitemap" ? 150 : 80, importance_reasons: [source], client_rendering_suspected: !isScannerBlocked && wordCount < 100 && scriptCount >= 15, template: makeUrlTemplate(url), extracted_at: new Date().toISOString(),
  };
}

function extractInternalLinks(html: string, baseUrl: string, origin: string) { return unique(extractLinks(html, baseUrl).filter((link) => { try { return new URL(link).origin === origin; } catch { return false; } })).slice(0, 250); }
function extractExternalLinks(html: string, baseUrl: string, origin: string) { return unique(extractLinks(html, baseUrl).filter((link) => { try { return new URL(link).origin !== origin; } catch { return false; } })).slice(0, 250); }
function extractLinks(html: string, baseUrl: string) {
  const links: string[] = [];
  for (const match of String(html || "").matchAll(/<a\b[^>]+href=["']([^"']+)["']/gi)) {
    const raw = decodeHtmlEntities(match[1] || "").trim();
    if (!raw || /^(mailto:|tel:|javascript:|data:|#)/i.test(raw)) continue;
    try { links.push(cleanUrl(new URL(raw, baseUrl).toString())); } catch {}
  }
  return links.filter(Boolean);
}

function extractTitle(html: string) { const match = String(html || "").match(/<title[^>]*>([\s\S]*?)<\/title>/i); return decodeHtmlEntities((match?.[1] || "").replace(/\s+/g, " ").trim()); }
function extractMeta(html: string, name: string) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const regex of [new RegExp(`<meta[^>]+name=["']${escaped}["'][^>]+content=["']([^"']*)["'][^>]*>`, "i"), new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]+name=["']${escaped}["'][^>]*>`, "i")]) {
    const match = String(html || "").match(regex);
    if (match?.[1]) return decodeHtmlEntities(match[1].trim());
  }
  return "";
}
function extractCanonical(html: string, baseUrl: string) { const match = String(html || "").match(/<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["'][^>]*>/i); if (!match?.[1]) return ""; try { return cleanUrl(new URL(match[1], baseUrl).toString()); } catch { return match[1]; } }
function extractAllH1(html: string) { return [...String(html || "").matchAll(/<h1[^>]*>([\s\S]*?)<\/h1>/gi)].map((match) => decodeHtmlEntities(String(match[1] || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim())).filter(Boolean); }
function stripHtmlToText(html: string) { return decodeHtmlEntities(String(html || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<noscript[\s\S]*?<\/noscript>/gi, " ").replace(/<!--[\s\S]*?-->/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()); }
function countMatches(value: string, regex: RegExp) { return [...String(value || "").matchAll(regex)].length; }
function countImagesMissingAlt(html: string) { return [...String(html || "").matchAll(/<img\b[^>]*>/gi)].filter((match) => !/\salt=["'][^"']*["']/i.test(match[0])).length; }
function detectBlocked({ html, text, statusCode, title }: { html: string; text: string; statusCode: number; title: string }) { if ([403, 429, 503].includes(Number(statusCode || 0))) return true; const haystack = `${title || ""} ${text || ""} ${html || ""}`.toLowerCase().slice(0, 8000); return ["just a moment", "checking your browser", "enable javascript", "verify you are human", "captcha", "access denied", "are you a robot", "too many requests", "rate limit", "request blocked", "cloudflare", "datadome"].some((phrase) => haystack.includes(phrase)); }
function decodeHtmlEntities(value: string) { return String(value || "").replace(/&amp;/gi, "&").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&quot;/gi, '"').replace(/&#39;/g, "'").replace(/&#x2F;/gi, "/"); }
function unique<T>(items: T[]) { return [...new Set(items.filter(Boolean))]; }
function makeUrlTemplate(url: string) { try { return new URL(url).pathname.split("/").filter(Boolean).map((segment, index) => index < 2 ? segment : (/^\d+$/.test(segment) || segment.length > 45 ? "*" : segment)).join("/"); } catch { return ""; } }
function classifyFetchError(error: unknown, statusCode = 0) { const message = getErrorMessage(error).toLowerCase(); if ([403, 429, 503].includes(Number(statusCode || 0))) return "blocked"; if (statusCode >= 500) return "http_5xx"; if (message.includes("abort") || message.includes("timeout")) return "timeout"; if (message.includes("dns") || message.includes("not found") || message.includes("enotfound")) return "dns"; if (message.includes("tls") || message.includes("ssl") || message.includes("certificate")) return "tls"; if (!message || message === "http 0" || message === "http 200") return ""; return "other"; }

function runScreamingFrogLiteAudit({ pages, startUrl }: { pages: any[]; startUrl: string }) {
  const raw_findings: any[] = [];
  const readablePages = pages.filter(isReadablePage);
  const indexablePages = readablePages.filter((page) => page.indexable !== false);
  for (const page of pages) if (Number(page.status_code || 0) >= 400 || Number(page.status_code || 0) === 0) raw_findings.push(makeFinding("broken_page", "404_error", "Broken page", "high", page, "Fix pages that are not loading", "This page did not load successfully for the scanner.", "Restore the page, update the link, or redirect it to the closest useful page."));
  for (const page of readablePages) {
    if (!page.title) raw_findings.push(makeFinding("missing_title", "meta_title", "Search appearance", "high", page, "Add a search title", "This page is missing a title tag.", "Add a clear title that describes the page and includes the main topic."));
    else if (page.title.length > 65) raw_findings.push(makeFinding("long_title", "meta_title", "Search appearance", "medium", page, "Shorten long search titles", "This page title may be too long for search results.", "Keep the title focused and under about 60 characters where possible."));
    if (!page.meta_description) raw_findings.push(makeFinding("missing_meta_description", "meta_description", "Search appearance", "high", page, "Add a search description", "This page is missing a meta description.", "Add a helpful description that explains why someone should visit this page."));
    else if (page.meta_description.length > 160) raw_findings.push(makeFinding("long_meta_description", "meta_description", "Search appearance", "low", page, "Shorten long search descriptions", "This description may be too long for search results.", "Keep descriptions concise and useful."));
    if (!page.h1) raw_findings.push(makeFinding("missing_h1", "thin_content", "Page content", "medium", page, "Add a clear main heading", "This page does not appear to have a clear H1 heading.", "Add one main heading that clearly describes the page topic."));
    if (Number(page.h1_count || 0) > 1) raw_findings.push(makeFinding("multiple_h1", "thin_content", "Page content", "low", page, "Review pages with multiple main headings", "Multiple H1 headings can make the page structure less clear.", "Keep one main H1 and use H2/H3 headings for sections."));
    if (Number(page.word_count || 0) > 0 && Number(page.word_count || 0) < 200) raw_findings.push(makeFinding("thin_content", "thin_content", "Page content", "medium", page, "Improve thin pages", "This page has very little readable content.", "Add useful information, FAQs, examples, service details, or next steps where relevant."));
    if (!page.canonical_url) raw_findings.push(makeFinding("missing_canonical", "canonical", "Website setup", "low", page, "Review canonical settings", "This page does not show a canonical URL in the HTML.", "Add or confirm the preferred version of this page in your CMS or SEO plugin."));
    if (page.indexable === false) raw_findings.push(makeFinding("noindex", "canonical", "Website setup", "high", page, "Review pages marked noindex", "This page appears to tell search engines not to index it.", "If this page should appear in Google, remove the noindex setting."));
    if (!page.viewport) raw_findings.push(makeFinding("missing_viewport", "performance", "Mobile experience", "medium", page, "Add mobile viewport settings", "This page may not be set up correctly for mobile screens.", "Add a viewport meta tag in the site template or theme."));
    if (Number(page.schema_count || 0) === 0) raw_findings.push(makeFinding("missing_schema", "schema", "Trust signals", "low", page, "Add structured data where useful", "This page does not appear to include structured data.", "Add relevant schema such as Organization, LocalBusiness, Product, Article, FAQ, or Breadcrumb schema."));
    if (Number(page.open_graph_tag_count || 0) === 0) raw_findings.push(makeFinding("missing_open_graph", "web_dev", "Social sharing", "low", page, "Improve social sharing metadata", "This page may not have social sharing tags.", "Add Open Graph title, description, and image fields in the CMS or SEO plugin."));
    if (Number(page.missing_alt_image_count || 0) > 0) raw_findings.push(makeFinding("image_alt_text", "web_dev", "Images", "low", page, "Add missing image descriptions", "Some images on this page appear to be missing alt text.", "Add short, useful alt text to important images."));
    if (Number(page.html_size || 0) > 800000 || Number(page.script_count || 0) > 70) raw_findings.push(makeFinding("heavy_page", "performance", "Website performance", "medium", page, "Review heavy pages", "This page appears large or script-heavy.", "Compress images, reduce unused scripts, and review third-party apps or plugins."));
    if (page.client_rendering_suspected) raw_findings.push(makeFinding("client_rendering", "js_rendering", "Website setup", "medium", page, "Review JavaScript-rendered content", "This page may rely heavily on JavaScript before important content appears.", "Make sure the main content, title, links, and headings are available in the initial HTML where possible."));
    if (page.final_url !== page.url && cleanUrl(page.final_url) && cleanUrl(page.url)) raw_findings.push(makeFinding("redirect", "redirect", "Page redirect", "low", page, "Review redirected pages", "This page redirects to another URL.", "Update internal links so they point directly to the final URL."));
  }
  addDuplicateFindings(raw_findings, indexablePages, "title", "duplicate_title", "duplicate_content", "Search appearance", "Review duplicate search titles");
  addDuplicateFindings(raw_findings, indexablePages, "meta_description", "duplicate_meta_description", "duplicate_content", "Search appearance", "Review duplicate search descriptions");
  addDuplicateFindings(raw_findings, indexablePages, "h1", "duplicate_h1", "thin_content", "Page content", "Review duplicate main headings");
  const orphanPages = pages.filter((page) => page.in_sitemap && page.source === "sitemap" && Number(page.internal_link_count || 0) === 0 && isReadablePage(page));
  if (orphanPages.length > 0) raw_findings.push(makeGroupedFinding("orphan_page", "internal_link", "Internal links", "low", "Pages not linked from your website", orphanPages.map((page) => page.url), "Some pages were found in the sitemap but were not linked from the pages the scanner checked.", "Add internal links to important orphan pages from relevant menus, footers, or content."));
  return { raw_findings, technical_audit_summary: { audit_profile: "screaming_frog_lite", screaming_frog_lite_enabled: true, pages_checked: pages.length, readable_pages_checked: readablePages.length, scanner_blocked_pages: pages.filter((page) => page.is_scanner_blocked).length, important_pages_checked: readablePages.length, indexable_pages: indexablePages.length, missing_meta_description_count: raw_findings.filter((item) => item.rule === "missing_meta_description").length, heavy_page_count: raw_findings.filter((item) => item.rule === "heavy_page").length, average_word_count: Math.round(readablePages.reduce((sum, page) => sum + Number(page.word_count || 0), 0) / Math.max(1, readablePages.length)), checks_completed: ["status_codes", "titles", "meta_descriptions", "h1_headings", "canonicals", "indexability", "mobile_viewport", "schema", "open_graph", "image_alt_text", "thin_content", "redirects", "heavy_pages", "client_rendering", "duplicate_titles", "duplicate_meta_descriptions", "duplicate_h1_headings", "orphan_sitemap_pages"] } };
}

function makeFinding(rule: string, category: string, customer_category: string, priority: string, page: any, title: string, explanation: string, recommendation: string) { return { rule, category, customer_category, priority, difficulty: priority === "high" ? "moderate" : "easy", issue_title: title, title, plain_english_explanation: explanation, why_it_matters: explanation, recommendation, recommended_value: recommendation, affected_pages: [page.url], page_url: page.url, current_value: page.title || page.meta_description || page.h1 || page.status_code || "", fingerprint: fnv1a(`${rule}|${page.url}`), confidence_score: 90, source: "screaming_frog_lite", requires_approval: true, requires_developer: ["canonical", "performance", "js_rendering"].includes(category), can_auto_fix: false }; }
function makeGroupedFinding(rule: string, category: string, customer_category: string, priority: string, title: string, pages: string[], explanation: string, recommendation: string) { return { rule, category, customer_category, priority, difficulty: "easy", issue_title: title, title, plain_english_explanation: explanation, why_it_matters: explanation, recommendation, recommended_value: recommendation, affected_pages: pages, page_url: pages[0] || "", fingerprint: fnv1a(`${rule}|${pages.join("|")}`), confidence_score: 90, source: "screaming_frog_lite", requires_approval: true, requires_developer: false, can_auto_fix: false }; }
function addDuplicateFindings(output: any[], pages: any[], field: string, rule: string, category: string, customer_category: string, title: string) { const groups = new Map<string, string[]>(); for (const page of pages) { const value = String(page[field] || "").trim().toLowerCase(); if (!value) continue; if (!groups.has(value)) groups.set(value, []); groups.get(value)?.push(page.url); } for (const [value, urls] of groups) if (urls.length > 1) output.push(makeGroupedFinding(rule, category, customer_category, rule === "duplicate_title" ? "medium" : "low", title, urls, "Multiple pages use the same SEO field, which can make it harder for search engines to understand which page is most relevant.", `Rewrite this field so each affected page is unique. Duplicate value: ${value.slice(0, 120)}`)); }
function isReadablePage(page: any) { return Number(page.status_code || 0) >= 200 && Number(page.status_code || 0) < 300 && !page.is_scanner_blocked && Number(page.word_count || 0) > 50; }
function groupFindings(findings: any[]) { const seen = new Set<string>(); const output: any[] = []; for (const item of findings) { const key = item.fingerprint || `${item.rule}|${item.page_url}`; if (seen.has(key)) continue; seen.add(key); output.push(item); } return output.sort((a, b) => priorityWeight(b.priority) - priorityWeight(a.priority)).slice(0, 120); }
function priorityWeight(priority: string) { return { critical: 4, high: 3, medium: 2, low: 1 }[String(priority || "medium").toLowerCase()] || 2; }
function calculateHealthScore({ pages, findings, technicalSummary }: { pages: any[]; findings: any[]; technicalSummary: any }) { const readable = Number(technicalSummary?.readable_pages_checked || 0); const blocked = Number(technicalSummary?.scanner_blocked_pages || 0); if (readable === 0 && blocked > 0) return 35; if (pages.length === 0) return 25; let score = 92; for (const finding of findings) score -= { high: 8, medium: 4, low: 1 }[String(finding.priority || "medium").toLowerCase()] || 3; if (readable < Math.min(5, pages.length)) score -= 10; return Math.max(20, Math.min(98, Math.round(score))); }
function buildCoverageFindings({ pages, startUrl }: { pages: any[]; startUrl: string }) { if (pages.length > 0) return []; return [makeGroupedFinding("scanner_no_pages", "scanner_blocked", "Scan coverage", "high", "Scanner could not read the website", [startUrl], "The scanner could not fetch readable pages from this website.", "Check whether the website blocks crawler requests, requires JavaScript, or has firewall rules that need to allow the scanner.")]; }
function buildScanSummary({ websiteUrl, body, healthScore, pages, findings, technicalSummary, crawlResult }: { websiteUrl: string; body: any; healthScore: number; pages: any[]; findings: any[]; technicalSummary: any; crawlResult: any }) { const high = findings.filter((item) => item.priority === "high").length; return { website_url: websiteUrl, business_name: body.business_name || "", health_score: healthScore, pages_checked: pages.length, readable_pages_checked: technicalSummary.readable_pages_checked || 0, scanner_blocked_pages: technicalSummary.scanner_blocked_pages || 0, total_findings: findings.length, high_priority_findings: high, summary: `The scan checked ${pages.length} pages and found ${findings.length} SEO improvements, including ${high} high-priority items.`, scan_focus: crawlResult.crawl_scope || {} }; }
function fnv1a(value: string) { let hash = 0x811c9dc5; for (let i = 0; i < value.length; i += 1) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 0x01000193); } return `sf_${(hash >>> 0).toString(16)}`; }
