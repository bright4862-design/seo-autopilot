import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runAdvancedScan_v21_python_first";
const PYTHON_SCANNER_VERSION = "python_scanner_v2_contract_parity";
const DENO_FALLBACK_PROFILE = "deno_screaming_frog_lite_fallback_v21";
const CORS_HEADERS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const USER_AGENT = "Mozilla/5.0 (compatible; FixListBot/2.1; +https://base44.app)";
const FETCH_TIMEOUT_MS = 12000;
const FUNCTION_RESPONSE_BUDGET_MS = 95000;
const RESPONSE_RESERVE_MS = 4000;
const MIN_FALLBACK_CRAWL_MS = 5000;
const PYTHON_TIMEOUTS_MS = {
  basic: 45000,
  quick: 55000,
  deep: 70000,
  advanced: 85000,
};
const MAX_BODY_CHARS = 1_500_000;
const MAX_SITEMAP_FETCHES = 12;
const MAX_ARTIFACT_EVIDENCE = 100;
const DEFAULT_POLICY = { rendering_mode: "unknown", platform_guess: "", priority_boost_patterns: [], priority_deprioritize_patterns: [], skip_patterns: [], source: "default", error: "" };
const MODE_LIMITS = {
  basic: { max_pages: 25, crawl_timeout_ms: 35000, use_sitemap: false, derive_policy: false },
  quick: { max_pages: 40, crawl_timeout_ms: 45000, use_sitemap: true, derive_policy: false },
  deep: { max_pages: 85, crawl_timeout_ms: 75000, use_sitemap: true, derive_policy: true },
  advanced: { max_pages: 150, crawl_timeout_ms: 90000, use_sitemap: true, derive_policy: true },
};
const TRUST = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv"];
const ROUTE_SEGMENTS = ["/login", "/register", "/account", "/my-account", "/dashboard", "/cart", "/checkout", "/billing", "/admin"];
const HARD_SKIP = ["/logout", "/search", "/feed", "/rss", "/wp-admin", "/wp-json", "/preview"];

Deno.serve(async (req) => {
  const functionStartedAt = Date.now();
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (req.method !== "POST") return jsonResponse({ success: false, version: VERSION, error: "Method not allowed" }, 405);

  let rawBody = {}, body = {};
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, version: VERSION, error: "Unauthorized" }, 401);

    rawBody = await safeReadJson(req);
    body = unwrapRequestBody(rawBody);
    const budget = resolveBudget(body);
    const websiteUrl = normalizeWebsiteUrl(body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || body.target_url || "");
    if (!websiteUrl) return jsonResponse({ success: false, version: VERSION, error: "Missing or invalid website_url.", received_keys: Object.keys(rawBody || {}), resolved_keys: Object.keys(body || {}) }, 400);
    const safety = await validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) return jsonResponse({ success: false, version: VERSION, error: safety.reason, received_keys: Object.keys(rawBody || {}), resolved_keys: Object.keys(body || {}) }, 400);

    const pathPrefix = body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "";
    const scanMode = body.scan_mode || body.audit_profile || "advanced";
    const pythonTimeoutMs = resolvePythonTimeout(scanMode);
    const pythonAttempt = await tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs: pythonTimeoutMs });
    if (pythonAttempt.ok) return jsonResponse(toPythonAdvancedScanResponse(pythonAttempt.result, scanMode));

    const fallbackReason = pythonAttempt.reason || "Python scanner unavailable; used Deno fallback.";
    const remainingMs = FUNCTION_RESPONSE_BUDGET_MS - (Date.now() - functionStartedAt);
    if (remainingMs < MIN_FALLBACK_CRAWL_MS + RESPONSE_RESERVE_MS) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The Python scanner did not finish in time and there was not enough request time left for a safe fallback scan. Please retry with Quick check.",
        detail: fallbackReason,
        retryable: true,
        scanner_api_url_configured: pythonAttempt.configured,
        elapsed_ms: Date.now() - functionStartedAt,
      }, 503);
    }

    const fallbackBudget = {
      ...budget,
      crawl_timeout_ms: Math.min(
        budget.crawl_timeout_ms,
        Math.max(MIN_FALLBACK_CRAWL_MS, remainingMs - RESPONSE_RESERVE_MS),
      ),
      derive_policy: Boolean(budget.derive_policy && remainingMs >= 25000),
    };
    const invokeLLM = typeof base44.integrations?.Core?.InvokeLLM === "function" ? async (prompt) => await base44.integrations.Core.InvokeLLM({ prompt }) : null;
    const crawlResult = await crawlWebsite({ startUrl: websiteUrl, budget: fallbackBudget, pathPrefix, invokeLLM });
    crawlResult.warnings = unique([...(crawlResult.warnings || []), `Python scanner fallback used: ${fallbackReason}`]);

    const rawFindings = [...buildFindings(crawlResult.pages, websiteUrl, budget), ...duplicateCasingFindings(crawlResult.pages)];
    const groupedFindings = groupFindings(rawFindings);
    const healthScore = calculateHealthScore(crawlResult.pages, groupedFindings);
    const verifiedFailedPages = crawlResult.pages.filter(isVerifiedFailedPage).map(pageEvidenceObject);
    const suspiciousUrlArtifacts = uniqueArtifacts([...(crawlResult.suspicious_url_artifacts || []), ...crawlResult.pages.filter((page) => page.url_confidence === "crawler_artifact").map(pageEvidenceObject)]);
    const evidenceSummary = buildUrlEvidenceSummary(crawlResult.pages, suspiciousUrlArtifacts);

    return jsonResponse({
      success: true,
      version: VERSION,
      scanner_version: VERSION,
      scanner_profile: DENO_FALLBACK_PROFILE,
      screaming_frog_lite_enabled: true,
      advanced_scan_backend: "deno_fallback",
      deno_fallback_used: true,
      scanner_api_url_configured: pythonAttempt.configured,
      python_scanner_fallback_reason: fallbackReason,
      website_url: websiteUrl,
      normalized_url: websiteUrl,
      scan_mode: scanMode,
      audit_profile: body.audit_profile || body.scan_mode || "advanced",
      pages_found: crawlResult.pages_found,
      pages_crawled: crawlResult.pages.length,
      queued_remaining: crawlResult.queued_remaining,
      crawled_pages: crawlResult.pages,
      pages: crawlResult.pages,
      raw_fixes: groupedFindings,
      raw_findings: rawFindings,
      grouped_findings: groupedFindings,
      findings: groupedFindings,
      recommendations: groupedFindings,
      health_score: healthScore,
      scan_summary: buildScanSummary(crawlResult.pages, groupedFindings, healthScore, crawlResult.pages_found, suspiciousUrlArtifacts.length),
      crawl_policy: crawlResult.crawl_policy,
      crawl_policy_source: crawlResult.crawl_policy?.source || "default",
      verified_failed_pages: verifiedFailedPages,
      suspicious_url_artifacts: suspiciousUrlArtifacts,
      verified_failed_page_count: verifiedFailedPages.length,
      suspicious_url_artifact_count: suspiciousUrlArtifacts.length,
      url_evidence_summary: evidenceSummary,
      technical_audit_summary: {
        scanner_version: VERSION,
        scanner_profile: DENO_FALLBACK_PROFILE,
        screaming_frog_lite_enabled: true,
        advanced_scan_backend: "deno_fallback",
        deno_fallback_used: true,
        python_scanner_fallback_reason: fallbackReason,
        pages_crawled: crawlResult.pages.length,
        pages_found: crawlResult.pages_found,
        failed_pages: crawlResult.pages.filter((page) => page.status_code >= 400 || page.fetch_error).length,
        verified_failed_pages: verifiedFailedPages.length,
        suspicious_url_artifacts: suspiciousUrlArtifacts.length,
        route_boundary_candidates_crawled: crawlResult.pages.filter((page) => page.route_boundary_candidate).length,
        duplicate_casing_routes: detectDuplicateCasingRoutes(crawlResult.pages),
        crawl_policy: crawlResult.crawl_policy,
        crawl_policy_source: crawlResult.crawl_policy?.source || "default",
        url_evidence_summary: evidenceSummary,
        crawl_warnings: crawlResult.warnings,
      },
      crawl_warnings: crawlResult.warnings,
    });
  } catch (error) {
    console.error("runAdvancedScan failed", error);
    return jsonResponse({ success: false, version: VERSION, error: "Advanced scan failed. Please try again.", detail: String(error?.message || error || "unknown error").slice(0, 240), received_keys: Object.keys(rawBody || {}), resolved_keys: Object.keys(body || {}) }, 500);
  }
});

async function tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs }) {
  const scannerUrl = String(Deno.env.get("SCANNER_API_URL") || Deno.env.get("PYTHON_SCANNER_API_URL") || Deno.env.get("PYTHON_SCANNER_URL") || Deno.env.get("SCANNER_URL") || Deno.env.get("cloud_api") || Deno.env.get("CLOUD_API") || "").replace(/\/+$/, "");
  const scannerKey = String(Deno.env.get("SCANNER_API_KEY") || Deno.env.get("PYTHON_SCANNER_API_KEY") || "");
  if (!scannerUrl) return { ok: false, configured: false, reason: "SCANNER_API_URL/cloud_api is not configured." };
  if (!scannerKey) return { ok: false, configured: true, reason: "SCANNER_API_KEY is not configured." };
  try {
    const response = await fetchWithTimeout(`${scannerUrl}/scan`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-scanner-key": scannerKey },
      body: JSON.stringify({
        website_url: websiteUrl,
        path_prefix: pathPrefix || null,
        scan_mode: scanMode || "advanced",
        business_name: body.business_name || body.project_name || "",
        cms_platform: body.cms_platform || body.platform || "",
      }),
    }, Math.max(1000, Number(timeoutMs || PYTHON_TIMEOUTS_MS.advanced)));
    const text = await response.text();
    const result = parseJson(text) || { success: false, error: text.slice(0, 400) };
    if (!response.ok) return { ok: false, configured: true, reason: `Python scanner HTTP ${response.status}: ${String(result.detail || result.error || "request failed").slice(0, 180)}` };
    if (result.success === false) return { ok: false, configured: true, reason: `Python scanner returned success=false: ${String(result.error || "unknown error").slice(0, 180)}` };
    if (result.scanner_version !== PYTHON_SCANNER_VERSION) return { ok: false, configured: true, reason: `Python scanner version ${result.scanner_version || "missing"} did not match ${PYTHON_SCANNER_VERSION}.` };
    return { ok: true, configured: true, result };
  } catch (error) {
    return { ok: false, configured: true, reason: `Python scanner request failed: ${String(error?.message || error || "unknown error").slice(0, 180)}` };
  }
}

function toPythonAdvancedScanResponse(result, scanMode) {
  const warnings = Array.isArray(result.crawl_warnings) ? result.crawl_warnings : [];
  const technical = result.technical_audit_summary && typeof result.technical_audit_summary === "object" ? result.technical_audit_summary : {};
  return {
    ...result,
    success: result.success !== false,
    version: VERSION,
    scanner_version: result.scanner_version,
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    scanner_api_url_configured: true,
    scan_mode: result.scan_mode || scanMode || "advanced",
    audit_profile: result.audit_profile || result.scan_mode || scanMode || "advanced",
    technical_audit_summary: {
      ...technical,
      scanner_version: result.scanner_version,
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      python_scanner_fallback_reason: "",
    },
    crawl_warnings: warnings,
  };
}

async function crawlWebsite({ startUrl, budget, pathPrefix, invokeLLM }) {
  const start = new URL(startUrl);
  const origin = start.origin;
  const normalizedPrefix = normalizePathPrefix(pathPrefix || start.pathname || "/");
  const policy = await deriveCrawlPolicy({ origin, start, budget, invokeLLM });
  const queue = [], seen = new Set(), discoveryMap = new Map(), pages = [], warnings = [], artifacts = [];
  const startedAt = Date.now();
  if (policy?.source === "failed" && policy?.error) warnings.push(`Crawl policy fell back to default: ${policy.error}`);
  enqueueUrl({ queue, discoveryMap, url: start.href, discoveredFrom: "seed", sourcePage: "", linkText: "", artifactSink: artifacts, policy });

  if (budget.use_sitemap) {
    const deadline = Date.now() + Math.min(20000, Math.floor(budget.crawl_timeout_ms * 0.25));
    const sitemapUrls = await loadSitemapUrls(origin, budget.max_pages * 4, normalizedPrefix, deadline, artifacts).catch((error) => { warnings.push(`Could not read sitemap: ${error?.message || "unknown error"}`); return []; });
    for (const url of sitemapUrls) if (queue.length < budget.max_pages * 5 && shouldCrawlUrl(url, start, normalizedPrefix)) enqueueUrl({ queue, discoveryMap, url, discoveredFrom: "sitemap", sourcePage: `${origin}/sitemap.xml`, linkText: "", artifactSink: artifacts, policy });
  }

  while (queue.length > 0 && pages.length < budget.max_pages && Date.now() - startedAt < budget.crawl_timeout_ms) {
    const next = dequeueByPriority(queue);
    const clean = canonicalizeUrl(next?.url || next);
    if (!clean || seen.has(clean)) continue;
    seen.add(clean);
    const safety = await validatePublicHttpUrl(clean);
    if (!safety.ok) { warnings.push(`Skipped unsafe URL ${clean}: ${safety.reason}`); continue; }
    const discovery = discoveryMap.get(clean) || emptyDiscovery("unknown");
    const fetched = await safeFetchText(clean).catch((error) => ({ ok: false, url: clean, final_url: clean, status: 0, content_type: "", text: "", error: error?.message || "Fetch failed" }));
    const page = extractPageFromHtml({ requestedUrl: clean, fetched, discovery });
    pages.push(page);
    if (fetched.text && isHtmlContent(fetched.content_type) && fetched.status >= 200 && fetched.status < 400) {
      for (const link of extractLinks(fetched.text, fetched.final_url || clean)) {
        if (queue.length + seen.size >= budget.max_pages * 6) break;
        if (isEncodedArtifactPath(link.href)) { recordArtifact(artifacts, { url: link.href, discoveredFrom: "internal_link", sourcePage: fetched.final_url || clean, linkText: link.text }); continue; }
        if (shouldCrawlUrl(link.href, start, normalizedPrefix) && !seen.has(canonicalizeUrl(link.href))) enqueueUrl({ queue, discoveryMap, url: link.href, discoveredFrom: "internal_link", sourcePage: fetched.final_url || clean, linkText: link.text, artifactSink: artifacts, policy });
      }
    }
  }
  return { pages, pages_found: Math.max(seen.size + queue.length, pages.length), queued_remaining: queue.length, warnings, crawl_policy: policy, suspicious_url_artifacts: uniqueArtifacts(artifacts) };
}

async function deriveCrawlPolicy({ origin, start, budget, invokeLLM }) {
  if (!budget.derive_policy) return { ...DEFAULT_POLICY, source: "disabled" };
  if (typeof invokeLLM !== "function") return { ...DEFAULT_POLICY, source: "unavailable", error: "InvokeLLM unavailable" };
  try {
    const [home, robots, sitemapIndex] = await Promise.all([safeFetchText(start.href).catch(() => null), safeFetchText(`${origin}/robots.txt`).catch(() => null), safeFetchText(`${origin}/sitemap.xml`).catch(() => null)]);
    const prompt = `Return only JSON for an SEO crawl policy with keys rendering_mode, platform_guess, priority_boost_patterns, priority_deprioritize_patterns, skip_patterns. Origin: ${origin}. Home words: ${stripHtml(home?.text || "").slice(0, 1200)}. Robots: ${(robots?.text || "").slice(0, 1200)}. Sitemap sample: ${(sitemapIndex?.text || "").slice(0, 1800)}`;
    const raw = await withTimeoutPromise(invokeLLM(prompt), 9000);
    return { ...sanitizePolicy(raw), source: "ai", error: "" };
  } catch (error) {
    return { ...DEFAULT_POLICY, source: "failed", error: String(error?.message || error || "policy failed").slice(0, 180) };
  }
}

function sanitizePolicy(raw) {
  const parsed = parsePolicyResponse(raw);
  const cleanList = (value) => unique((Array.isArray(value) ? value : []).map(cleanPolicyPattern).filter(Boolean)).slice(0, 8);
  const protectedPatterns = ["/", "/contact", "/about", "/privacy", "/terms", "/product", "/products", "/category", "/listing", "/login", "/account", "/cart", "/checkout", "/dashboard", "/devis", "/quote", "/booking", "/reservation", "/simulation", "/calculator", "/pricing", "/demo"];
  const skipPatterns = cleanList(parsed.skip_patterns).filter((p) => !isRouteBoundaryCandidate(p) && !matchesAnyPattern(p, protectedPatterns));
  return { rendering_mode: ["ssr", "csr", "hybrid", "unknown"].includes(parsed.rendering_mode) ? parsed.rendering_mode : "unknown", platform_guess: String(parsed.platform_guess || "").slice(0, 60), priority_boost_patterns: cleanList(parsed.priority_boost_patterns), priority_deprioritize_patterns: cleanList(parsed.priority_deprioritize_patterns), skip_patterns: skipPatterns };
}

function parsePolicyResponse(raw) {
  if (raw && typeof raw === "object") {
    if (raw.rendering_mode || raw.priority_boost_patterns || raw.priority_deprioritize_patterns || raw.skip_patterns) return raw;
    if (raw.data?.data) return parsePolicyResponse(raw.data.data);
    if (raw.data?.result) return parsePolicyResponse(raw.data.result);
    if (raw.result?.data) return parsePolicyResponse(raw.result.data);
    if (raw.result) return parsePolicyResponse(raw.result);
    if (raw.content?.[0]?.text) return parsePolicyResponse(raw.content[0].text);
    if (raw.text) return parsePolicyResponse(raw.text);
  }
  try {
    const text = String(raw || "").replace(/```json|```/g, "").trim();
    const first = text.indexOf("{");
    const last = text.lastIndexOf("}");
    return first >= 0 && last > first ? JSON.parse(text.slice(first, last + 1)) : DEFAULT_POLICY;
  } catch { return DEFAULT_POLICY; }
}

function cleanPolicyPattern(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw || raw.length > 120) return "";
  if (/^https?:\/\//i.test(raw)) { try { return new URL(raw).pathname || "/"; } catch { return ""; } }
  return raw.startsWith("/") || raw.includes("*") ? raw : `/${raw}`;
}

async function safeFetchText(url, redirectCount = 0) {
  if (redirectCount > 4) throw new Error("Too many redirects");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { method: "GET", redirect: "manual", signal: controller.signal, headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" } });
    const status = response.status;
    const location = response.headers.get("location");
    if ([301, 302, 303, 307, 308].includes(status) && location) return await safeFetchText(new URL(location, url).href, redirectCount + 1);
    const contentType = response.headers.get("content-type") || "";
    const text = isHtmlContent(contentType) || contentType.includes("xml") || url.toLowerCase().endsWith(".txt") ? (await response.text()).slice(0, MAX_BODY_CHARS) : "";
    return { ok: response.ok, url, final_url: response.url || url, status, content_type: contentType, text, error: "" };
  } finally { clearTimeout(timer); }
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...options, signal: controller.signal }); }
  finally { clearTimeout(timer); }
}

async function loadSitemapUrls(origin, limit, pathPrefix = "/", deadline = Infinity, artifactSink = []) {
  const urls = [], childQueue = [], fetchedSitemaps = new Set();
  const robots = await safeFetchText(`${origin}/robots.txt`).catch(() => null);
  const roots = [];
  if (robots?.text) for (const match of robots.text.match(/^sitemap:\s*(.+)$/gim) || []) roots.push(match.replace(/^sitemap:\s*/i, "").trim());
  roots.push(`${origin}/sitemap.xml`);
  for (const sitemapUrl of unique(roots)) {
    if (urls.length >= limit || fetchedSitemaps.size >= MAX_SITEMAP_FETCHES || Date.now() >= deadline) break;
    for (const loc of await fetchSitemapLocs(sitemapUrl, fetchedSitemaps, artifactSink)) {
      if (/\.xml(\.gz)?$/i.test(loc)) childQueue.push(loc); else if (urls.length < limit) urls.push(loc);
    }
  }
  for (const child of rankChildSitemaps(childQueue, pathPrefix)) {
    if (urls.length >= limit || fetchedSitemaps.size >= MAX_SITEMAP_FETCHES || Date.now() >= deadline) break;
    if (/\.gz$/i.test(child)) continue;
    for (const loc of await fetchSitemapLocs(child, fetchedSitemaps, artifactSink)) {
      if (urls.length >= limit) break;
      if (!/\.xml(\.gz)?$/i.test(loc)) urls.push(loc);
    }
  }
  return unique(urls).slice(0, limit);
}

async function fetchSitemapLocs(sitemapUrl, fetchedSitemaps, artifactSink = []) {
  const clean = String(sitemapUrl || "").trim();
  if (!clean || fetchedSitemaps.has(clean)) return [];
  fetchedSitemaps.add(clean);
  const safety = await validatePublicHttpUrl(clean).catch(() => ({ ok: false }));
  if (!safety.ok) return [];
  const fetched = await safeFetchText(clean).catch(() => null);
  if (!fetched?.text) return [];
  const output = [];
  for (const match of fetched.text.matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi)) {
    const loc = decodeHtml(match[1].trim());
    if (isEncodedArtifactPath(loc)) recordArtifact(artifactSink, { url: loc, discoveredFrom: "sitemap", sourcePage: clean, linkText: "" });
    else output.push(loc);
  }
  return output;
}

function enqueueUrl({ queue, discoveryMap, url, discoveredFrom, sourcePage, linkText, artifactSink = [], policy }) {
  const clean = canonicalizeUrl(url);
  if (!clean) { if (isEncodedArtifactPath(url)) recordArtifact(artifactSink, { url, discoveredFrom, sourcePage, linkText }); return; }
  if (isEncodedArtifactPath(clean)) { recordArtifact(artifactSink, { url: clean, discoveredFrom, sourcePage, linkText }); return; }
  const record = discoveryMap.get(clean) || { discovered_from: [], source_pages: [], link_text_samples: [] };
  record.discovered_from = unique([...record.discovered_from, discoveredFrom]).slice(0, 6);
  record.source_pages = unique([...record.source_pages, cleanPath(sourcePage || "")].filter(Boolean)).slice(0, 8);
  record.link_text_samples = unique([...record.link_text_samples, cleanText(linkText || "")].filter(Boolean)).slice(0, 5);
  discoveryMap.set(clean, record);
  const priority = computeQueuePriority(cleanPath(clean), record, policy);
  const existing = queue.find((item) => canonicalizeUrl(item.url || item) === clean);
  if (existing) existing.priority = Math.max(existing.priority || 0, priority); else queue.push({ url: clean, priority });
}

function computeQueuePriority(path, discovery, policy) {
  const clean = cleanPath(path).toLowerCase();
  if (isEncodedArtifactPath(clean)) return 0;
  const sources = discovery?.discovered_from || [];
  const family = classifyTemplateFamily(clean);
  const route = isRouteBoundaryCandidate(clean);
  let score = sources.includes("seed") ? 100 : sources.includes("sitemap") ? 70 : 50;
  if (sources.includes("sitemap") && sources.includes("internal_link")) score = 82;
  if (TRUST.some((p) => clean.startsWith(p))) score += 25;
  if (["conversion", "product_detail", "category_listing", "contact"].includes(family)) score += 22;
  if (route) score += 12;
  if (isLowValuePage(clean)) score -= 25;
  if (policy) {
    if (matchesAnyPattern(clean, policy.priority_boost_patterns)) score += route ? 8 : 35;
    if (matchesAnyPattern(clean, policy.priority_deprioritize_patterns)) score -= route ? 10 : 35;
    if (matchesAnyPattern(clean, policy.skip_patterns) && !route) score -= 45;
  }
  return Math.max(0, Math.min(150, score));
}

function buildFindings(pages, websiteUrl, budget = MODE_LIMITS.advanced) {
  const findings = [];
  if (safeHostname(websiteUrl).endsWith(".base44.app")) findings.push(createFinding({ rule: "free_base44_subdomain", category: "indexability", priority: "high", title: "Move production SEO to a custom domain", pageUrl: "/", explanation: "The site is on a Base44 subdomain. A branded custom domain is stronger for SEO and trust.", recommendation: "Connect a branded custom domain before treating this as the permanent production SEO home.", difficulty: "developer" }));
  for (const page of pages) {
    const path = cleanPath(page.final_url || page.url || "/");
    if (page.url_confidence === "crawler_artifact" || isEncodedArtifactPath(path)) continue;
    if (page.status_code >= 400 || page.fetch_error) {
      findings.push(createFinding({ rule: statusRule(page.status_code), category: page.status_code === 429 ? "web_dev" : "404_error", priority: page.status_code >= 500 || page.status_code === 429 ? "high" : "medium", title: page.status_code === 429 ? "Check pages blocked by rate limiting" : "Fix pages that are not loading", pageUrl: path, currentValue: page.fetch_error || `HTTP ${page.status_code}`, explanation: page.status_code === 429 ? "The scanner saw HTTP 429 or rate limiting. Treat this as crawler-access evidence, not a confirmed broken customer page." : "This page did not load cleanly during the scan and has a real discovery source.", recommendation: page.status_code === 429 ? "Ask your web person to check server, CDN, firewall, and rate-limit logs. Confirm Googlebot and normal users can access this URL." : "Check whether the page should exist, redirect it, or fix the server issue.", difficulty: "developer", sourcePages: page.source_pages, linkTextSamples: page.link_text_samples }));
      continue;
    }
    if (page.route_boundary_candidate && page.indexable) findings.push(createFinding({ rule: "route_boundary_candidate_indexable", category: "indexability", priority: "critical", title: "Keep checkout, login, account, and app routes out of search", pageUrl: path, currentValue: "Route-boundary page appears indexable", explanation: "Private or account-style routes usually should not be public SEO pages.", recommendation: "Require login, add noindex, or keep private routes out of public search.", difficulty: "developer" }));
    if (!page.title) findings.push(createFinding({ rule: "missing_title", category: "meta_title", priority: page.estimated_page_intent === "money_or_conversion" ? "high" : "medium", title: "Add a clear search title", pageUrl: path, explanation: "This page is missing a title.", recommendation: "Add a short, specific page title.", difficulty: "easy" }));
    if (!page.meta_description && !page.route_boundary_candidate && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "missing_meta_description", category: "meta_description", priority: page.estimated_page_intent === "money_or_conversion" ? "high" : "medium", title: "Add a clear search description", pageUrl: path, explanation: "This page is missing a meta description.", recommendation: "Add a short description that explains the page and why someone should click.", difficulty: "easy" }));
    if (page.h1_count === 0 && !page.route_boundary_candidate && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "missing_h1", category: "thin_content", priority: "medium", title: "Add one clear page heading", pageUrl: path, explanation: "The page does not have a clear H1 heading.", recommendation: "Add one main heading that matches the page purpose.", difficulty: "easy" }));
    if (page.h1_count > 1) findings.push(createFinding({ rule: "multiple_h1", category: "thin_content", priority: "low", title: "Use one main page heading", pageUrl: path, explanation: "The page has more than one H1 heading.", recommendation: "Keep one H1 as the main page heading and make the rest H2/H3 headings.", difficulty: "easy" }));
    if (!page.canonical && page.indexable && !page.route_boundary_candidate && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "canonical_missing", category: "canonical", priority: page.estimated_page_intent === "money_or_conversion" ? "high" : "medium", title: "Add a canonical URL", pageUrl: path, explanation: "The page does not expose a canonical URL.", recommendation: "Add a self-referencing canonical or point to the preferred version.", difficulty: "developer" }));
    if (page.client_rendering_suspected) findings.push(createFinding({ rule: "client_rendering", category: "web_dev", priority: "high", title: "Check JavaScript-rendered content", pageUrl: path, explanation: "The raw HTML looks thin and may rely heavily on JavaScript rendering.", recommendation: "Make sure search engines receive useful crawlable HTML for important public pages.", difficulty: "developer" }));
    if (page.image_missing_alt_count > 0 && !page.route_boundary_candidate && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "image_alt_text", category: "image_alt_text", priority: page.image_missing_alt_count >= 10 ? "medium" : "low", title: "Add useful image descriptions", pageUrl: path, currentValue: `${page.image_missing_alt_count} images missing alt text`, explanation: "Some meaningful images may not have text descriptions.", recommendation: "Add short, specific alt text to meaningful images.", difficulty: "easy" }));
    if (page.estimated_page_intent === "money_or_conversion" && !page.has_schema) findings.push(createFinding({ rule: "schema", category: "schema", priority: "medium", title: "Add structured data to important pages", pageUrl: path, explanation: "This looks like an important business page, but no structured data was detected.", recommendation: "Add appropriate schema such as Organization, Product, Service, Breadcrumb, or FAQ where relevant.", difficulty: "developer" }));
  }
  const trustPages = pages.map((p) => cleanPath(p.final_url || p.url || "").toLowerCase()).filter((p) => TRUST.some((t) => p.startsWith(t)));
  if (pages.length >= 15 && trustPages.length === 0) findings.push(createFinding({ rule: "missing_trust_pages", category: "schema", priority: "medium", title: "Add public trust pages", pageUrl: "/", explanation: "The scan did not find obvious About, Contact, Privacy, Terms, or Security pages.", recommendation: "Add or expose trust pages and link them from the footer.", difficulty: "moderate" }));
  if (budget.max_pages >= 80 && pages.length > 0 && pages.length < 15 && findings.length === 0) findings.push(createFinding({ rule: "limited_crawl_coverage", category: "web_dev", priority: "medium", title: "Scan coverage was limited", pageUrl: "/", currentValue: `${pages.length} pages checked`, explanation: "FixList loaded only a small sample of this section. The pages it did check looked mostly clean, so recommendations would be low-confidence until coverage improves.", recommendation: "Run a broader scan or ask your web person to confirm sitemap and internal links expose the rest of this section. Then rerun FixList before making SEO changes.", difficulty: "developer" }));
  return findings;
}

function createFinding({ rule, category, priority, title, pageUrl, affectedPages, currentValue = "", explanation, recommendation, difficulty = "easy", source = "screaming_frog_lite", sourcePages = [], linkTextSamples = [] }) {
  const id = stableId(`${rule}|${pageUrl}|${title}`);
  const developer = difficulty === "developer" || /429|server|firewall|render|schema|canonical|route|index|redirect|coverage|sitemap/i.test(`${rule} ${category} ${title} ${recommendation}`);
  return { id, fix_id: id, rule, category, customer_category: friendlyCategory(category), priority, difficulty: developer ? "developer" : difficulty, status: developer ? "needs_developer" : "needs_approval", issue_title: title, title, plain_english_explanation: explanation, plain_english_summary: explanation, why_it_matters: explanation, current_value: currentValue, recommended_value: recommendation, recommendation, ai_recommendation: recommendation, page_url: pageUrl, affected_pages: unique(affectedPages || [pageUrl]), source_pages: unique(sourcePages), link_text_samples: unique(linkTextSamples), requires_developer: developer, requires_approval: !developer, can_auto_fix: false, who_can_do_this: developer ? "your_web_person" : "you", estimated_time: developer ? "about 1–2 hours" : "about 10–20 minutes", confidence_score: 88, source, page_template_family: classifyTemplateFamily(pageUrl), estimated_page_intent: estimatePageIntent(pageUrl, {}), primary_defect_class: rule.includes("429") || rule.includes("blocked") ? "blocked_access" : developer ? "structural" : "content", meta_regeneration_gate: /meta|title|description/i.test(`${rule} ${category}`) ? "allowed_metadata_is_primary_gap" : "not_metadata" };
}

function groupFindings(findings) {
  const direct = [], groups = new Map();
  for (const finding of findings) {
    const key = groupingKey(finding);
    if (!key) { direct.push(finding); continue; }
    const list = groups.get(key) || [];
    list.push(finding);
    groups.set(key, list);
  }
  for (const [key, list] of groups.entries()) {
    const affected = unique(list.flatMap((f) => f.affected_pages || [f.page_url]).map(cleanPath).filter(Boolean)).slice(0, 150);
    if (affected.length < 3) { direct.push(...list); continue; }
    const sample = list[0];
    const family = classifyTemplateFamily(sample.page_url);
    const blocked = key.startsWith("failure|rate_limited_page") || sample.rule === "rate_limited_page";
    const title = blocked ? "Check pages blocked by rate limiting" : groupTemplateTitle(sample, family);
    const explanation = blocked ? "Several similar pages returned HTTP 429 or rate limiting. Treat this as one crawler-access problem." : "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page.";
    const recommendation = blocked ? "Ask your web person to check server, CDN, firewall, and rate-limit logs. Confirm Googlebot and normal users can access the affected URLs." : "Fix one representative page/template first, then roll out the same rule across the affected group.";
    direct.push({ ...sample, id: stableId(`group|${key}`), fix_id: stableId(`group|${key}`), page_url: "", issue_title: title, title, plain_english_explanation: explanation, plain_english_summary: explanation, why_it_matters: explanation, recommended_value: recommendation, recommendation, ai_recommendation: recommendation, priority: blocked ? "high" : sample.priority === "high" ? "medium" : sample.priority, difficulty: blocked ? "developer" : sample.difficulty, requires_developer: blocked || sample.requires_developer, who_can_do_this: blocked ? "your_web_person" : sample.who_can_do_this, affected_pages: affected, page_count: affected.length, source_pages: unique(list.flatMap((f) => f.source_pages || [])), link_text_samples: unique(list.flatMap((f) => f.link_text_samples || [])) });
  }
  return direct;
}

function groupingKey(finding) { const family = classifyTemplateFamily(finding.page_url || finding.affected_pages?.[0] || ""); if (["rate_limited_page", "server_error", "404_error", "410_error", "failed_page"].includes(finding.rule)) return `failure|${finding.rule}|${family}`; if (["client_rendering", "canonical_missing", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description"].includes(finding.rule)) return `template|${finding.rule}|${family}`; return ""; }
function groupTemplateTitle(finding, family) { if (finding.rule === "schema") return `Add structured data to ${humanize(family)} templates`; if (finding.rule === "image_alt_text") return `Batch image descriptions on ${humanize(family)} pages`; if (finding.rule === "missing_meta_description") return `Batch meta descriptions on ${humanize(family)} pages`; if (finding.rule === "missing_h1") return `Batch page headings on ${humanize(family)} pages`; return `Fix repeated ${humanize(family)} template issue`; }

function detectDuplicateCasingRoutes(pages) {
  const byLower = new Map();
  for (const page of pages || []) {
    const path = cleanPath(page.path || page.final_url || page.url || "").split("?")[0];
    if (!path) continue;
    const lower = path.toLowerCase();
    const variants = byLower.get(lower) || [];
    if (!variants.includes(path)) variants.push(path);
    byLower.set(lower, variants);
  }
  return Array.from(byLower.entries()).filter(([, variants]) => variants.length > 1).map(([path, variants]) => ({ path, variants })).slice(0, 20);
}

function duplicateCasingFindings(pages) {
  return detectDuplicateCasingRoutes(pages).map((item) => {
    const highRisk = item.variants.some((path) => ["/dashboard", "/account", "/login", "/cart", "/checkout", "/admin"].some((part) => path.toLowerCase().includes(part)));
    const finding = createFinding({ rule: "duplicate_route_casing", category: "indexability", priority: highRisk ? "high" : "medium", title: "Fix duplicate URL casing variants", pageUrl: "", affectedPages: item.variants, currentValue: item.variants.slice(0, 6).join(", "), explanation: "The crawler found URLs that differ only by uppercase/lowercase letters. These can create duplicate crawlable pages or expose app-route variants.", recommendation: "Ask your web person to choose one canonical casing, redirect the other variants, and make sure internal links use the preferred version.", difficulty: "developer" });
    return { ...finding, id: stableId(`duplicate_route_casing|${item.variants.join("|")}`), fix_id: stableId(`duplicate_route_casing|${item.variants.join("|")}`), affected_pages: item.variants, page_count: item.variants.length, page_template_family: highRisk ? "route_boundary" : "standard", primary_defect_class: "structural" };
  });
}

function extractPageFromHtml({ requestedUrl, fetched, discovery }) {
  const html = fetched.text || "";
  const finalUrl = fetched.final_url || requestedUrl;
  const path = cleanPath(finalUrl);
  const status = Number(fetched.status || 0);
  const title = extractTagText(html, "title");
  const metaDescription = extractMeta(html, "description");
  const robots = extractMeta(html, "robots");
  const canonical = extractLinkRel(html, "canonical");
  const h1s = extractHeadingTexts(html, "h1");
  const schemaTypes = extractSchemaTypes(html);
  const visibleText = stripHtml(html);
  const wordCount = visibleText ? visibleText.split(/\s+/).filter(Boolean).length : 0;
  const imageStats = extractImageStats(html);
  const indexable = status >= 200 && status < 400 && !robots.toLowerCase().includes("noindex");
  const evidence = classifyUrlEvidence({ path, status, discovery });
  const route = isRouteBoundaryCandidate(path);
  return { url: requestedUrl, final_url: finalUrl, path, discovered_from: discovery?.discovered_from || [], source_pages: discovery?.source_pages || [], link_text_samples: discovery?.link_text_samples || [], url_confidence: evidence.confidence, url_suspicion_reasons: evidence.reasons, route_boundary_candidate: route, route_boundary_type: route ? "route_boundary" : "", status_code: status, fetch_error: fetched.error || "", content_type: fetched.content_type || "", title, title_length: title.length, meta_description: metaDescription, meta_description_length: metaDescription.length, robots, canonical, canonical_status: canonical ? (sameCanonicalPath(finalUrl, canonical) ? "self_or_equivalent" : "canonical_to_different_url") : "missing", robots_indexability_status: indexable ? "indexable" : "not_indexable", h1: h1s[0] || "", h1_count: h1s.length, word_count: wordCount, image_count: imageStats.total, image_missing_alt_count: imageStats.missingAlt, schema_types: schemaTypes, has_schema: schemaTypes.length > 0, client_rendering_suspected: status >= 200 && status < 400 && html.length > 0 && wordCount < 80 && (html.includes("id=\"root\"") || html.includes("id=\"app\"") || html.includes("type=\"module\"")), page_template_family: classifyTemplateFamily(path), estimated_page_intent: estimatePageIntent(path, { title, h1: h1s[0] || "", robots, status }), indexable };
}

function classifyUrlEvidence({ path, status, discovery }) { const sources = discovery?.discovered_from || []; const clean = cleanPath(path); const reasons = []; if (isEncodedArtifactPath(clean)) reasons.push("encoded_or_base64_like_path"); if (/https?:/i.test(clean.replace(/^\//, "")) || /%2f%2f/i.test(clean)) reasons.push("external_url_embedded_in_path"); if (reasons.length) return { confidence: "crawler_artifact", reasons }; if (sources.includes("seed")) return { confidence: "confirmed_seed", reasons }; if (sources.includes("sitemap") && sources.includes("internal_link")) return { confidence: "confirmed_sitemap_and_linked", reasons }; if (sources.includes("sitemap")) return { confidence: "sitemap_listed", reasons }; if (sources.includes("internal_link")) return { confidence: status >= 400 ? "linked_but_failed" : "internally_linked", reasons }; return { confidence: "unknown_discovery", reasons: ["missing_discovery_source"] }; }
function shouldCrawlUrl(url, start, pathPrefix) { try { const parsed = new URL(url); if (parsed.origin !== start.origin || !/^https?:$/i.test(parsed.protocol)) return false; parsed.hash = ""; const path = parsed.pathname || "/"; const lower = path.toLowerCase(); if (isEncodedArtifactPath(path)) return false; if (/\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff2?|ttf|mp4|mov|avi)$/i.test(lower)) return false; if (HARD_SKIP.some((s) => lower === s || lower.startsWith(`${s}/`))) return false; if (pathPrefix && pathPrefix !== "/" && !path.startsWith(pathPrefix)) return false; return true; } catch { return false; } }
function rankChildSitemaps(children, pathPrefix) { const tokens = String(pathPrefix || "/").toLowerCase().split("/").filter(Boolean); const score = (url) => { const target = String(url || "").toLowerCase(); let value = 0; if (tokens.length && tokens.every((token) => target.includes(token))) value += 40; else if (tokens.some((token) => target.includes(token))) value += 20; if (/(page|product|categor|service|listing|collection|post|article)/.test(target)) value += 8; if (/(tag|author|archive|news-\d{4}|blog-\d{4}|image|video)/.test(target)) value -= 15; return value; }; return unique(children).sort((a, b) => score(b) - score(a)); }
function dequeueByPriority(queue) { queue.sort((a, b) => (b.priority || 0) - (a.priority || 0)); return queue.shift(); }
function pageEvidenceObject(page) { return { url: page.url || "", final_url: page.final_url || page.url || "", path: page.path || cleanPath(page.final_url || page.url || ""), status_code: Number(page.status_code || 0), fetch_error: page.fetch_error || "", url_confidence: page.url_confidence || "", url_suspicion_reasons: page.url_suspicion_reasons || [], discovered_from: page.discovered_from || [], source_pages: page.source_pages || [], link_text_samples: page.link_text_samples || [], page_template_family: page.page_template_family || "", estimated_page_intent: page.estimated_page_intent || "", title: page.title || "", h1: page.h1 || "" }; }
function recordArtifact(target, { url, discoveredFrom, sourcePage, linkText, reason = "encoded_or_base64_like_path" }) { if (!Array.isArray(target) || target.length >= MAX_ARTIFACT_EVIDENCE) return; const value = String(url || "").trim(); if (!value) return; target.push({ url: value.slice(0, 500), path: cleanPath(value).slice(0, 500), url_confidence: "crawler_artifact", url_suspicion_reasons: [reason], discovered_from: [String(discoveredFrom || "unknown")], source_pages: unique([cleanPath(sourcePage || "")].filter(Boolean)), link_text_samples: unique([cleanText(linkText || "")].filter(Boolean)), suppressed_from_crawl: true }); }
function uniqueArtifacts(items) { const seen = new Set(), output = []; for (const item of items || []) { const key = `${item.url || item.final_url || item.path}|${(item.source_pages || []).join("|")}`; if (!key || seen.has(key)) continue; seen.add(key); output.push(item); } return output.slice(0, MAX_ARTIFACT_EVIDENCE); }
function buildUrlEvidenceSummary(pages, artifacts = []) { const out = { confirmed_seed: 0, confirmed_sitemap_and_linked: 0, sitemap_listed: 0, internally_linked: 0, linked_but_failed: 0, crawler_artifact: artifacts.length || 0, unknown_discovery: 0, route_boundary_candidates: { crawled: 0, indexable: 0, examples: [] } }; for (const page of pages) { out[page.url_confidence] = Number(out[page.url_confidence] || 0) + 1; if (page.route_boundary_candidate) { out.route_boundary_candidates.crawled += 1; if (page.indexable) out.route_boundary_candidates.indexable += 1; if (out.route_boundary_candidates.examples.length < 10) out.route_boundary_candidates.examples.push(page.path || cleanPath(page.url)); } } return out; }
function buildScanSummary(pages, findings, healthScore, pagesFound, artifactCount = 0) { const verified = pages.filter(isVerifiedFailedPage).length; const suspicious = pages.filter((p) => p.url_confidence === "crawler_artifact").length + Number(artifactCount || 0); return { health_score: healthScore, score: healthScore, pages_scanned: pages.length, pages_crawled: pages.length, pages_found: pagesFound, verified_failed_pages: verified, suspicious_url_artifacts: suspicious, high_priority_count: findings.filter((f) => ["critical", "high"].includes(f.priority)).length, technical_issue_count: findings.length, status_label: healthScore >= 75 ? "Good" : healthScore >= 55 ? "Fair" : "Needs work", plain_english_summary: `The scanner reviewed ${pages.length} pages${pagesFound ? ` out of about ${pagesFound} discovered URLs` : ""}. ${verified ? `${verified} verified failed page checks need review. ` : ""}${suspicious ? `${suspicious} suspicious crawler artifacts were separated from customer-facing issues. ` : ""}Start with grouped technical and money-page issues first.` }; }
function calculateHealthScore(pages, findings) { let score = 92; score -= Math.min(35, pages.filter(isVerifiedFailedPage).length * 8); score -= Math.min(20, pages.filter((p) => p.status_code === 429 && p.url_confidence !== "crawler_artifact").length * 4); for (const f of findings) score -= f.priority === "critical" ? 10 : f.priority === "high" ? 6 : f.priority === "medium" ? 2 : 0; return Math.max(20, Math.min(98, Math.round(score))); }
function isVerifiedFailedPage(page) { return (page.status_code >= 400 || page.fetch_error) && page.url_confidence !== "crawler_artifact"; }
function statusRule(status) { if (status === 429) return "rate_limited_page"; if (status >= 500) return "server_error"; if (status === 410) return "410_error"; return "404_error"; }
function friendlyCategory(category) { return ({ meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", web_dev: "Website setup", image_alt_text: "Images", indexability: "Indexability" })[category] || "Website improvement"; }
function classifyTemplateFamily(url = "") { const p = cleanPath(url).toLowerCase(); if (isEncodedArtifactPath(p)) return "crawler_artifact"; if (isRouteBoundaryCandidate(p)) return "route_boundary"; if (isLowValuePage(p)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(p)) return "booking_or_checkout"; if (/\/products?\/|\/p\//.test(p)) return "product_detail"; if (/\/collections?\/|\/category\/|\/categorie\/|listing|show|marque|brand/.test(p)) return "category_listing"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(p)) return "conversion"; if (/contact/.test(p)) return "contact"; if (/faq|question/.test(p)) return "qa"; if (/guide|blog|article/.test(p)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(p)) return "legal_info"; return "standard"; }
function estimatePageIntent(path = "", { title = "", h1 = "", robots = "", status = 200 }) { const t = `${path} ${title} ${h1}`.toLowerCase(); if (isEncodedArtifactPath(t)) return "crawler_artifact"; if (status >= 400 || t.includes("429")) return status === 429 ? "blocked_access" : "failed"; if (robots.toLowerCase().includes("noindex")) return "not_indexed"; if (isRouteBoundaryCandidate(t)) return "internal_or_auth"; if (/devis|quote|pricing|tarif|contact|booking|reservation|checkout|ticket|voucher|pass|show|listing|product|produit|collection|category|simulation|simulateur|calcul|calculator|comparateur|demo|signup|energie|electricite|gaz|fournisseur/.test(t)) return "money_or_conversion"; if (/privacy|terms|legal|about|contact|security/.test(t)) return "trust_or_legal"; if (/faq|guide|blog|article|question/.test(t)) return "support_content"; if (isLowValuePage(t)) return "archive"; return "standard"; }
function isRouteBoundaryCandidate(url = "") { const p = cleanPath(url).toLowerCase(); return ROUTE_SEGMENTS.some((s) => p.includes(s)); }
function isLowValuePage(url = "") { const p = cleanPath(url).toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(p)) return true; return ["/tag/", "/tags/", "/author/", "/archive/", "/archives/", "/feed/", "/rss/", "/page/"].some((s) => p.includes(s)); }
function isEncodedArtifactPath(value = "") { const p = cleanPath(value).split("?")[0]; return p.split("/").filter(Boolean).some((segment) => { const decoded = safeDecodeURIComponent(segment); if (/^(L2|aHR0c|aHR0p|eyJ|PGE|PHN)[A-Za-z0-9+/_-]{10,}={0,2}$/.test(segment)) return true; if (/^[A-Za-z0-9+/_-]{24,}={1,2}$/.test(segment)) return true; if (/%2f/i.test(segment) && /%3a|%2f/i.test(segment)) return true; if (/^https?:/i.test(decoded) || decoded.startsWith("/")) return true; return false; }); }
function safeDecodeURIComponent(value) { try { return decodeURIComponent(String(value || "")); } catch { return String(value || ""); } }
function extractLinks(html, baseUrl) { const out = []; const re = /<a\s+[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi; let m; while ((m = re.exec(html)) && out.length < 2000) { try { out.push({ href: new URL(decodeHtml(m[1]), baseUrl).href, text: cleanText(stripHtml(m[2] || "")) }); } catch {} } return out; }
function extractTagText(html, tag) { const m = String(html || "").match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i")); return cleanText(decodeHtml(m?.[1] || "")); }
function extractHeadingTexts(html, tag) { const out = []; const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "gi"); let m; while ((m = re.exec(String(html || ""))) && out.length < 10) out.push(cleanText(stripHtml(decodeHtml(m[1] || "")))); return out.filter(Boolean); }
function extractMeta(html, name) { const re = new RegExp(`<meta[^>]+(?:name|property)=["']${escapeRegExp(name)}["'][^>]+content=["']([^"']*)["'][^>]*>`, "i"); return cleanText(decodeHtml(String(html || "").match(re)?.[1] || "")); }
function extractLinkRel(html, rel) { const re = new RegExp(`<link[^>]+rel=["'][^"']*${escapeRegExp(rel)}[^"']*["'][^>]+href=["']([^"']+)["'][^>]*>`, "i"); return decodeHtml(String(html || "").match(re)?.[1] || "").trim(); }
function extractImageStats(html) { let total = 0, missingAlt = 0; for (const img of String(html || "").match(/<img\b[^>]*>/gi) || []) { total += 1; if (!/\salt\s*=\s*["'][^"']+["']/i.test(img)) missingAlt += 1; } return { total, missingAlt }; }
function extractSchemaTypes(html) { const types = new Set(); const re = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi; let m; while ((m = re.exec(String(html || "")))) { try { collectSchemaTypes(JSON.parse(m[1]), types); } catch {} } return Array.from(types).slice(0, 20); }
function collectSchemaTypes(value, types) { if (!value) return; if (Array.isArray(value)) return value.forEach((x) => collectSchemaTypes(x, types)); if (typeof value === "object") { const type = value["@type"]; if (Array.isArray(type)) type.forEach((x) => types.add(String(x))); else if (type) types.add(String(type)); collectSchemaTypes(value["@graph"], types); } }
function normalizeScanMode(value) { const mode = String(value || "advanced").toLowerCase(); if (mode === "standard") return "deep"; if (["full", "full_site", "full-site"].includes(mode)) return "advanced"; return mode; }
function resolvePythonTimeout(scanMode) { const mode = normalizeScanMode(scanMode); return PYTHON_TIMEOUTS_MS[mode] || PYTHON_TIMEOUTS_MS.advanced; }
function resolveBudget(body) { const mode = normalizeScanMode(body.scan_mode || body.audit_profile || "advanced"); return MODE_LIMITS[mode] || MODE_LIMITS.advanced; }
function unwrapRequestBody(raw) { if (!raw || typeof raw !== "object") return {}; if (raw.website_url || raw.url || raw.normalized_url || raw.requested_start_url || raw.start_url || raw.target_url) return raw; if (raw.data && typeof raw.data === "object") return raw.data; if (raw.body && typeof raw.body === "object") return raw.body; if (raw.payload && typeof raw.payload === "object") return raw.payload; if (raw.input && typeof raw.input === "object") return raw.input; if (raw.args && typeof raw.args === "object") return raw.args; return raw; }
async function safeReadJson(req) { try { return await req.json(); } catch { return {}; } }
function parseJson(text) { try { return JSON.parse(text || "{}"); } catch { return null; } }
function jsonResponse(payload, status = 200) { return Response.json(payload, { status, headers: CORS_HEADERS }); }
function normalizeWebsiteUrl(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`); if (!/^https?:$/i.test(url.protocol) || !url.hostname || url.username || url.password) return ""; url.hash = ""; return url.href; } catch { return ""; } }
function canonicalizeUrl(value) { try { const url = new URL(String(value || "")); if (!/^https?:$/i.test(url.protocol)) return ""; url.hash = ""; if (url.pathname !== "/") url.pathname = url.pathname.replace(/\/{2,}/g, "/").replace(/\/$/, ""); const params = [...url.searchParams.entries()].filter(([key]) => !/^utm_|^(fbclid|gclid|mc_cid|mc_eid|ref|session|sid)$/i.test(key)); url.search = ""; for (const [key, val] of params.slice(0, 8)) url.searchParams.append(key, val); return url.href; } catch { return ""; } }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const url = new URL(raw); return `${url.pathname || "/"}${url.search || ""}` || "/"; } catch { return raw.startsWith("/") ? raw : `/${raw}`; } }
function normalizePathPrefix(value) { const path = cleanPath(value || "/").split("?")[0] || "/"; return path === "/" ? "" : path.replace(/\/$/, ""); }
async function validatePublicHttpUrl(value) { try { const url = new URL(value); if (!/^https?:$/i.test(url.protocol)) return { ok: false, reason: "URL must use http or https." }; const host = url.hostname.toLowerCase(); if (!host || host === "localhost" || host.endsWith(".localhost")) return { ok: false, reason: "Localhost URLs are not allowed." }; if (/^(127\.|10\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(host)) return { ok: false, reason: "Private network URLs are not allowed." }; if (host === "::1" || host.startsWith("[::1")) return { ok: false, reason: "Private network URLs are not allowed." }; return { ok: true, reason: "" }; } catch { return { ok: false, reason: "Missing or invalid website_url." }; } }
function emptyDiscovery(source) { return { discovered_from: [source], source_pages: [], link_text_samples: [] }; }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function sameCanonicalPath(pageUrl, canonical) { try { const page = new URL(pageUrl); const canon = new URL(canonical, page.origin); return page.origin === canon.origin && page.pathname.replace(/\/$/, "") === canon.pathname.replace(/\/$/, ""); } catch { return false; } }
function isHtmlContent(contentType = "") { return /text\/html|application\/xhtml\+xml|application\/xml|text\/xml/i.test(contentType); }
function stripHtml(html) { return cleanText(String(html || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ")); }
function cleanText(value) { return decodeHtml(String(value || "")).replace(/\s+/g, " ").trim(); }
function decodeHtml(value) { return String(value || "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'"); }
function escapeRegExp(value) { return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
function matchesAnyPattern(path, patterns = []) { const clean = cleanPath(path).toLowerCase(); return (patterns || []).some((pattern) => { const p = cleanPolicyPattern(pattern); if (!p) return false; if (p.includes("*")) return new RegExp(`^${escapeRegExp(p).replace(/\\\*/g, ".*")}`).test(clean); return clean.includes(p); }); }
function unique(values) { return Array.from(new Set((values || []).filter((value) => value !== undefined && value !== null && String(value).trim() !== ""))); }
function humanize(value) { return String(value || "template").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim(); }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function withTimeoutPromise(promise, timeoutMs) { let timeoutId; const timeout = new Promise((_, reject) => { timeoutId = setTimeout(() => reject(new Error(`Policy derivation timed out after ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs); }); return Promise.race([promise, timeout]).finally(() => clearTimeout(timeoutId)); }
