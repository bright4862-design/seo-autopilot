import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runAdvancedScan_v12_business_intent_screaming_frog_lite";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const USER_AGENT = "Mozilla/5.0 (compatible; FixListBot/1.2; +https://base44.app)";
const FETCH_TIMEOUT_MS = 12000;
const MAX_REDIRECTS = 4;
const MAX_BODY_CHARS = 1_500_000;

const MODE_LIMITS = {
  basic: { max_pages: 25, crawl_timeout_ms: 35000, use_sitemap: false },
  quick: { max_pages: 40, crawl_timeout_ms: 45000, use_sitemap: true },
  deep: { max_pages: 85, crawl_timeout_ms: 75000, use_sitemap: true },
  advanced: { max_pages: 150, crawl_timeout_ms: 90000, use_sitemap: true },
};

const INTERNAL_ROUTE_PATTERNS = [
  "/admin",
  "/developer",
  "/assistant",
  "/billing",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/dashboard",
  "/issues",
  "/reports",
  "/crawl-status",
  "/metadata",
  "/canonicals",
  "/redirects",
  "/js-rendering",
  "/competitors",
];

const TRUST_PAGE_PATTERNS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales"];
const UTILITY_SEGMENTS = ["/cart", "/checkout", "/login", "/logout", "/account", "/my-account", "/search", "/feed", "/wp-admin", "/wp-json", "/preview"];
const LOW_VALUE_SEGMENTS = ["/tag/", "/tags/", "/author/", "/archive/", "/archives/", "/feed/", "/rss/", "/page/"];

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
    if (!safety.ok) return jsonResponse({ success: false, version: VERSION, error: safety.reason }, 400);

    const crawlResult = await crawlWebsite({ startUrl: websiteUrl, budget, pathPrefix: body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "" });
    const rawFindings = buildFindings({ pages: crawlResult.pages, websiteUrl, crawlResult });
    const groupedFindings = groupFindings(rawFindings);
    const healthScore = calculateHealthScore({ pages: crawlResult.pages, findings: groupedFindings });
    const summary = buildScanSummary({ pages: crawlResult.pages, findings: groupedFindings, healthScore, crawlResult });

    return jsonResponse({
      success: true,
      version: VERSION,
      scanner_version: VERSION,
      scanner_profile: "screaming_frog_lite_business_intent_v12",
      screaming_frog_lite_enabled: true,
      website_url: websiteUrl,
      normalized_url: websiteUrl,
      scan_mode: body.scan_mode || body.audit_profile || "advanced",
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
      scan_summary: summary,
      technical_audit_summary: {
        scanner_version: VERSION,
        screaming_frog_lite_enabled: true,
        pages_crawled: crawlResult.pages.length,
        pages_found: crawlResult.pages_found,
        failed_pages: crawlResult.pages.filter((page) => page.status_code >= 400 || page.fetch_error).length,
        route_boundary_risk: routeBoundaryRisk(crawlResult.pages),
        duplicate_casing_routes: findDuplicateCasingRoutes(crawlResult.pages),
        free_base44_subdomain: safeHostname(websiteUrl).endsWith(".base44.app"),
        crawl_warnings: crawlResult.warnings,
      },
      crawl_warnings: crawlResult.warnings,
    });
  } catch (error) {
    console.error("runAdvancedScan failed", error);
    return jsonResponse({ success: false, version: VERSION, error: "Advanced scan failed. Please try again." }, 500);
  }
});

async function crawlWebsite({ startUrl, budget, pathPrefix }) {
  const start = new URL(startUrl);
  const origin = start.origin;
  const normalizedPrefix = normalizePathPrefix(pathPrefix || start.pathname || "/");
  const queue = [];
  const seen = new Set();
  const pages = [];
  const warnings = [];
  const startedAt = Date.now();

  queue.push(start.href);

  if (budget.use_sitemap) {
    const sitemapUrls = await loadSitemapUrls(origin, budget.max_pages * 2).catch((error) => {
      warnings.push(`Could not read sitemap: ${error?.message || "unknown error"}`);
      return [];
    });
    for (const url of sitemapUrls) {
      if (queue.length >= budget.max_pages * 3) break;
      if (shouldCrawlUrl(url, start, normalizedPrefix)) queue.push(url);
    }
  }

  while (queue.length > 0 && pages.length < budget.max_pages && Date.now() - startedAt < budget.crawl_timeout_ms) {
    const next = queue.shift();
    const clean = canonicalizeUrl(next);
    if (!clean || seen.has(clean)) continue;
    seen.add(clean);

    const safety = await validatePublicHttpUrl(clean);
    if (!safety.ok) {
      warnings.push(`Skipped unsafe URL ${clean}: ${safety.reason}`);
      continue;
    }

    const fetched = await safeFetchText(clean).catch((error) => ({ ok: false, url: clean, final_url: clean, status: 0, content_type: "", text: "", error: error?.message || "Fetch failed" }));
    const page = extractPageFromHtml({ requestedUrl: clean, fetched });
    pages.push(page);

    if (fetched.text && isHtmlContent(fetched.content_type) && fetched.status >= 200 && fetched.status < 400) {
      const links = extractLinks(fetched.text, fetched.final_url || clean);
      for (const link of links) {
        if (queue.length + seen.size >= budget.max_pages * 4) break;
        if (shouldCrawlUrl(link, start, normalizedPrefix) && !seen.has(canonicalizeUrl(link))) queue.push(link);
      }
    }
  }

  return {
    pages,
    pages_found: Math.max(seen.size + queue.length, pages.length),
    queued_remaining: queue.length,
    warnings,
  };
}

async function safeFetchText(url, redirectCount = 0) {
  if (redirectCount > MAX_REDIRECTS) throw new Error("Too many redirects");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "manual",
      signal: controller.signal,
      headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" },
    });
    const status = response.status;
    const location = response.headers.get("location");
    if ([301, 302, 303, 307, 308].includes(status) && location) {
      const redirected = new URL(location, url).href;
      const safety = await validatePublicHttpUrl(redirected);
      if (!safety.ok) throw new Error(`Unsafe redirect blocked: ${safety.reason}`);
      return await safeFetchText(redirected, redirectCount + 1);
    }
    const contentType = response.headers.get("content-type") || "";
    const text = isHtmlContent(contentType) || contentType.includes("xml") ? (await response.text()).slice(0, MAX_BODY_CHARS) : "";
    return { ok: response.ok, url, final_url: response.url || url, status, content_type: contentType, text, error: "" };
  } finally {
    clearTimeout(timer);
  }
}

async function loadSitemapUrls(origin, limit) {
  const urls = [];
  const robots = await safeFetchText(`${origin}/robots.txt`).catch(() => null);
  const sitemapCandidates = [];
  if (robots?.text) {
    const matches = robots.text.match(/^sitemap:\s*(.+)$/gim) || [];
    for (const match of matches) sitemapCandidates.push(match.replace(/^sitemap:\s*/i, "").trim());
  }
  sitemapCandidates.push(`${origin}/sitemap.xml`);

  for (const sitemapUrl of Array.from(new Set(sitemapCandidates))) {
    if (urls.length >= limit) break;
    const fetched = await safeFetchText(sitemapUrl).catch(() => null);
    if (!fetched?.text) continue;
    const locs = [...fetched.text.matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi)].map((match) => decodeHtml(match[1].trim()));
    for (const loc of locs) {
      if (urls.length >= limit) break;
      if (/\.xml(\.gz)?$/i.test(loc)) continue;
      urls.push(loc);
    }
  }
  return urls;
}

function shouldCrawlUrl(url, start, pathPrefix) {
  try {
    const parsed = new URL(url);
    if (parsed.origin !== start.origin) return false;
    if (!/^https?:$/i.test(parsed.protocol)) return false;
    parsed.hash = "";
    const path = parsed.pathname || "/";
    const lower = path.toLowerCase();
    if (/\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff2?|ttf|mp4|mov|avi)$/i.test(lower)) return false;
    if (UTILITY_SEGMENTS.some((segment) => lower === segment || lower.startsWith(`${segment}/`))) return false;
    if (pathPrefix && pathPrefix !== "/" && !path.startsWith(pathPrefix)) return false;
    return true;
  } catch {
    return false;
  }
}

function extractPageFromHtml({ requestedUrl, fetched }) {
  const html = fetched.text || "";
  const finalUrl = fetched.final_url || requestedUrl;
  const path = cleanPath(finalUrl);
  const status = Number(fetched.status || 0);
  const title = extractTagText(html, "title");
  const metaDescription = extractMeta(html, "description");
  const robots = extractMeta(html, "robots");
  const viewport = extractMeta(html, "viewport");
  const canonical = extractLinkRel(html, "canonical");
  const h1s = extractHeadingTexts(html, "h1");
  const h2s = extractHeadingTexts(html, "h2");
  const imageStats = extractImageStats(html);
  const linkStats = extractLinkStats(html, finalUrl);
  const schemaTypes = extractSchemaTypes(html);
  const visibleText = stripHtml(html);
  const wordCount = visibleText ? visibleText.split(/\s+/).filter(Boolean).length : 0;
  const clientRenderingSuspected = status >= 200 && status < 400 && html.length > 0 && wordCount < 80 && (html.includes("id=\"root\"") || html.includes("id=\"app\"") || html.includes("type=\"module\""));
  const indexable = status >= 200 && status < 400 && !robots.toLowerCase().includes("noindex");
  const pageTemplateFamily = classifyTemplateFamily(path);
  const estimatedPageIntent = estimatePageIntent(path, { title, h1: h1s[0] || "", robots, status });

  return {
    url: requestedUrl,
    final_url: finalUrl,
    path,
    status_code: status,
    fetch_error: fetched.error || "",
    content_type: fetched.content_type || "",
    title,
    title_length: title.length,
    meta_description: metaDescription,
    meta_description_length: metaDescription.length,
    robots,
    viewport,
    canonical,
    canonical_status: canonical ? (sameCanonicalPath(finalUrl, canonical) ? "self_or_equivalent" : "canonical_to_different_url") : "missing",
    robots_indexability_status: indexable ? "indexable" : "not_indexable",
    h1: h1s[0] || "",
    h1_count: h1s.length,
    h2_count: h2s.length,
    word_count: wordCount,
    image_count: imageStats.total,
    image_missing_alt_count: imageStats.missingAlt,
    internal_link_count: linkStats.internal,
    external_link_count: linkStats.external,
    schema_types: schemaTypes,
    has_schema: schemaTypes.length > 0,
    client_rendering_suspected: clientRenderingSuspected,
    page_template_family: pageTemplateFamily,
    estimated_page_intent: estimatedPageIntent,
    conversion_signals: extractSignals(path, visibleText, ["contact", "quote", "devis", "demo", "pricing", "booking", "reservation", "checkout", "buy", "cart", "appointment"]),
    trust_signals: extractSignals(path, visibleText, ["privacy", "terms", "about", "contact", "address", "phone", "security", "reviews", "testimonials", "legal"]),
    indexable,
  };
}

function buildFindings({ pages, websiteUrl }) {
  const findings = [];
  const hostname = safeHostname(websiteUrl);

  if (hostname.endsWith(".base44.app")) {
    findings.push(createFinding({ rule: "free_base44_subdomain", category: "indexability", priority: "high", title: "Move production SEO to a custom domain", pageUrl: "/", affectedPages: ["/"], explanation: "The site is on a Base44 subdomain. It can be crawled, but a branded custom domain is a stronger long-term SEO and trust setup.", recommendation: "Connect a branded custom domain before treating this as the permanent production SEO home.", difficulty: "developer" }));
  }

  for (const page of pages) {
    const path = cleanPath(page.final_url || page.url || "/");
    if (page.status_code >= 400 || page.fetch_error) {
      findings.push(createFinding({ rule: statusRule(page.status_code), category: "404_error", priority: page.status_code >= 500 ? "critical" : "high", title: "Fix pages that are not loading", pageUrl: path, affectedPages: [path], currentValue: page.fetch_error || `HTTP ${page.status_code}`, explanation: "This page did not load cleanly during the scan.", recommendation: "Check whether the page should exist, redirect it to a useful page, or fix the server/blocking issue.", difficulty: "developer", source: "screaming_frog_lite" }));
      continue;
    }

    if (isInternalAppRoute(path) && page.indexable) {
      findings.push(createFinding({ rule: "internal_route_indexable", category: "indexability", priority: "critical", title: "Keep internal app routes out of search", pageUrl: path, affectedPages: [path], currentValue: "Internal/app route appears crawlable and indexable", explanation: "This looks like an app, auth, dashboard, admin, billing, or report route rather than a public marketing page.", recommendation: "Require login or add noindex for internal/auth/app routes. Keep only true public landing/help pages indexable.", difficulty: "developer", source: "screaming_frog_lite" }));
    }

    if (!page.title) findings.push(createFinding({ rule: "missing_title", category: "meta_title", priority: page.estimated_page_intent === "money_or_conversion" ? "high" : "medium", title: "Add a clear search title", pageUrl: path, affectedPages: [path], explanation: "This page is missing a title for browser tabs and search results.", recommendation: "Add a short, specific page title that explains the page purpose.", difficulty: "easy" }));
    if (!page.meta_description && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "missing_meta_description", category: "meta_description", priority: page.estimated_page_intent === "money_or_conversion" ? "high" : "medium", title: "Add a clear search description", pageUrl: path, affectedPages: [path], explanation: "This page is missing a meta description.", recommendation: "Add a short description that explains the page and why someone should click.", difficulty: "easy" }));
    if (page.h1_count === 0 && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "missing_h1", category: "thin_content", priority: "medium", title: "Add one clear page heading", pageUrl: path, affectedPages: [path], explanation: "The page does not have a clear H1 heading.", recommendation: "Add one main heading that matches the page purpose.", difficulty: "easy" }));
    if (page.h1_count > 1) findings.push(createFinding({ rule: "multiple_h1", category: "thin_content", priority: "low", title: "Use one main page heading", pageUrl: path, affectedPages: [path], explanation: "The page has more than one H1 heading.", recommendation: "Keep one H1 as the main page heading and make the rest H2/H3 headings.", difficulty: "easy" }));
    if (!page.canonical && page.indexable && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "canonical_missing", category: "canonical", priority: "high", title: "Add a canonical URL", pageUrl: path, affectedPages: [path], explanation: "The page does not expose a canonical URL.", recommendation: "Add a self-referencing canonical or point to the preferred version of this page.", difficulty: "developer" }));
    if (page.canonical_status === "canonical_to_different_url") findings.push(createFinding({ rule: "canonical_to_other_url", category: "canonical", priority: "high", title: "Review canonical target", pageUrl: path, affectedPages: [path], currentValue: page.canonical, explanation: "The page points its canonical URL somewhere else.", recommendation: "Confirm whether this page should be indexed or whether the canonical target is correct.", difficulty: "developer" }));
    if (page.client_rendering_suspected) findings.push(createFinding({ rule: "client_rendering", category: "web_dev", priority: "high", title: "Check JavaScript-rendered content", pageUrl: path, affectedPages: [path], explanation: "The raw HTML looks thin and may rely heavily on JavaScript rendering.", recommendation: "Make sure search engines receive useful crawlable HTML for important public pages.", difficulty: "developer" }));
    if (page.image_missing_alt_count > 0 && page.estimated_page_intent !== "internal_or_auth") findings.push(createFinding({ rule: "image_alt_text", category: "image_alt_text", priority: page.image_missing_alt_count >= 10 ? "medium" : "low", title: "Add useful image descriptions", pageUrl: path, affectedPages: [path], currentValue: `${page.image_missing_alt_count} images missing alt text`, explanation: "Some meaningful images may not have text descriptions.", recommendation: "Add short, specific alt text to meaningful images. Decorative images can stay empty.", difficulty: "easy" }));
    if (page.estimated_page_intent === "money_or_conversion" && !page.has_schema) findings.push(createFinding({ rule: "schema", category: "schema", priority: "medium", title: "Add structured data to important pages", pageUrl: path, affectedPages: [path], explanation: "This looks like an important business page, but no structured data was detected.", recommendation: "Add appropriate schema such as Organization, LocalBusiness, Product, Service, Breadcrumb, or FAQ where relevant.", difficulty: "developer" }));
  }

  const duplicateCasing = findDuplicateCasingRoutes(pages);
  if (duplicateCasing.length > 0) {
    findings.push(createFinding({ rule: "duplicate_route_casing", category: "duplicate_content", priority: "high", title: "Consolidate duplicate URL casing", pageUrl: duplicateCasing[0], affectedPages: duplicateCasing, explanation: "The crawl found routes that differ mainly by capitalization.", recommendation: "Choose one canonical casing, update internal links, and redirect or noindex duplicates.", difficulty: "developer" }));
  }

  const trustPages = pages.map((page) => cleanPath(page.final_url || page.url || "").toLowerCase()).filter((path) => TRUST_PAGE_PATTERNS.some((pattern) => path.startsWith(pattern)));
  if (pages.length >= 4 && trustPages.length === 0) {
    findings.push(createFinding({ rule: "missing_trust_pages", category: "schema", priority: "medium", title: "Add public trust pages", pageUrl: "/", affectedPages: ["/"], explanation: "The scan did not find obvious About, Contact, Privacy, Terms, or Security pages.", recommendation: "Add or expose trust pages and link them from the footer.", difficulty: "moderate" }));
  }

  const repeatedSnapshots = findRepeatedSnapshotGroups(pages);
  if (repeatedSnapshots.length > 0) {
    findings.push(createFinding({ rule: "thin_repetitive_public_snapshots", category: "thin_content", priority: "high", title: "Reduce thin repetitive public snapshots", pageUrl: repeatedSnapshots[0], affectedPages: repeatedSnapshots, explanation: "Several public routes return very similar titles, headings, or descriptions.", recommendation: "Noindex private/app routes and add richer route-specific copy only to public pages that should rank or convert.", difficulty: "moderate" }));
  }

  return findings;
}

function groupFindings(findings) {
  const output = [];
  const groups = new Map();

  for (const finding of findings) {
    const affected = Array.isArray(finding.affected_pages) ? finding.affected_pages : [];
    const groupableFailure = isFailureRule(finding.rule) || String(finding.current_value || "").match(/\b(404|410|429|500|503)\b/);
    const lowValueCosmetic = isLowValuePage(finding.page_url) && ["missing_meta_description", "missing_title", "image_alt_text"].includes(finding.rule);

    if (!groupableFailure && !lowValueCosmetic) {
      output.push(finding);
      continue;
    }

    const family = classifyTemplateFamily(finding.page_url);
    const bucket = groupableFailure ? `failure|${finding.rule}|${family}|${statusBucket(finding)}` : `lowvalue|${finding.rule}|${family}`;
    const existing = groups.get(bucket) || {
      ...finding,
      id: stableId(`group|${bucket}`),
      fix_id: stableId(`group|${bucket}`),
      page_url: "",
      issue_title: groupableFailure ? groupFailureTitle(finding, family) : groupLowValueTitle(finding),
      title: groupableFailure ? groupFailureTitle(finding, family) : groupLowValueTitle(finding),
      plain_english_explanation: groupableFailure ? "Several similar pages are failing or blocked in the same way. Treat this as one shared crawlability/template problem." : "Several lower-priority archive/news/tag pages have the same cleanup issue.",
      plain_english_summary: groupableFailure ? "Several similar pages are failing or blocked in the same way. Treat this as one shared crawlability/template problem." : "Several lower-priority archive/news/tag pages have the same cleanup issue.",
      why_it_matters: groupableFailure ? "A repeated loading or blocking problem can hide important pages from users and search engines. Fixing the shared cause is more useful than editing pages one by one." : "These pages should not crowd out higher-value product, service, booking, quote, or trust pages.",
      recommended_value: groupableFailure ? "Check shared redirects, firewall/bot protection, server rules, or templates causing these failures, then rescan." : "Batch these lower-priority cleanup items after important business pages are fixed.",
      ai_recommendation: groupableFailure ? "Check shared redirects, firewall/bot protection, server rules, or templates causing these failures, then rescan." : "Batch these lower-priority cleanup items after important business pages are fixed.",
      priority: groupableFailure ? "high" : "low",
      difficulty: groupableFailure ? "developer" : "easy",
      requires_developer: groupableFailure,
      affected_pages: [],
      source: "screaming_frog_lite",
    };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...affected])).slice(0, 150);
    groups.set(bucket, existing);
  }

  return [...output, ...groups.values()].map((finding) => ({ ...finding, page_count: finding.affected_pages?.length || 1 }));
}

function createFinding({ rule, category, priority, title, pageUrl, affectedPages, currentValue = "", explanation, recommendation, difficulty = "moderate", source = "screaming_frog_lite" }) {
  const id = stableId(`${rule}|${pageUrl}|${title}`);
  const owner = difficulty === "developer" ? "your_web_person" : "you";
  const steps = difficulty === "developer" ? ["Send this item to your web person.", "Ask them to review the affected URL or shared template.", "Apply the safest fix and publish it.", "Run FixList again to confirm it is resolved."] : ["Open the affected page or template.", recommendation, "Save and publish the change.", "Run FixList again after publishing."];
  return {
    id,
    fix_id: id,
    type: "site_level",
    rule,
    category,
    customer_category: friendlyCategory(category),
    issue_title: title,
    title,
    page_url: cleanPath(pageUrl || "/"),
    affected_pages: Array.from(new Set((affectedPages || [pageUrl || "/"]).map((item) => cleanPath(item)).filter(Boolean))),
    plain_english_explanation: explanation,
    plain_english_summary: explanation,
    why_it_matters: explanation,
    current_value: currentValue,
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    priority,
    difficulty,
    status: difficulty === "developer" ? "needs_developer" : "needs_approval",
    can_auto_fix: false,
    requires_approval: difficulty !== "developer",
    requires_developer: difficulty === "developer",
    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,
    who_can_do_this: owner,
    estimated_time: difficulty === "developer" ? "about 1–2 hours" : "about 10–30 minutes",
    time_estimate: difficulty === "developer" ? "about 1–2 hours" : "about 10–30 minutes",
    confidence_score: 88,
    source,
  };
}

function calculateHealthScore({ pages, findings }) {
  let score = 92;
  const failedPages = pages.filter((page) => page.status_code >= 400 || page.fetch_error).length;
  score -= Math.min(35, failedPages * 4);
  for (const finding of findings) {
    if (finding.priority === "critical") score -= 14;
    else if (finding.priority === "high") score -= 8;
    else if (finding.priority === "medium") score -= 4;
    else score -= 1;
  }
  return Math.max(20, Math.min(95, Math.round(score)));
}

function buildScanSummary({ pages, findings, healthScore, crawlResult }) {
  const failedPages = pages.filter((page) => page.status_code >= 400 || page.fetch_error).length;
  const highPriority = findings.filter((finding) => ["critical", "high"].includes(finding.priority)).length;
  const routeRisk = routeBoundaryRisk(pages);
  return {
    score: healthScore,
    status_label: healthScore >= 90 ? "Excellent" : healthScore >= 75 ? "Good" : healthScore >= 55 ? "Fair" : "Needs work",
    plain_english_summary: `FixList crawled ${pages.length} pages and found ${findings.length} grouped finding${findings.length === 1 ? "" : "s"}. ${failedPages} page${failedPages === 1 ? "" : "s"} failed or were blocked. Route-boundary risk is ${routeRisk}.`,
    pages_scanned: pages.length,
    pages_failed: failedPages,
    high_priority_count: highPriority,
    technical_issue_count: findings.length,
    queued_remaining: crawlResult.queued_remaining,
    crawl_warnings: crawlResult.warnings,
  };
}

/* -------------------------------------------------------------------------- */
/* URL safety                                                                  */
/* -------------------------------------------------------------------------- */

async function validatePublicHttpUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    return { ok: false, reason: "Invalid URL." };
  }
  if (!["http:", "https:"].includes(url.protocol)) return { ok: false, reason: "Only http and https URLs can be scanned." };
  const hostname = url.hostname.toLowerCase();
  if (!hostname || hostname === "localhost" || hostname.endsWith(".localhost")) return { ok: false, reason: "Localhost URLs cannot be scanned." };
  if (isPrivateHostname(hostname)) return { ok: false, reason: "Private/internal hostnames cannot be scanned." };
  if (isIpAddress(hostname) && isPrivateIp(hostname)) return { ok: false, reason: "Private/internal IP addresses cannot be scanned." };

  if (typeof Deno.resolveDns === "function" && !isIpAddress(hostname)) {
    try {
      const records = await Deno.resolveDns(hostname, "A");
      if (records.some((ip) => isPrivateIp(ip))) return { ok: false, reason: "DNS resolves to a private/internal IP." };
    } catch {
      // DNS can fail in some edge runtimes. The fetch layer still validates redirects.
    }
  }
  return { ok: true };
}

function isPrivateHostname(hostname) {
  return hostname === "0.0.0.0" || hostname.endsWith(".internal") || hostname.endsWith(".local") || hostname.endsWith(".lan") || hostname.endsWith(".home") || hostname.endsWith(".corp");
}

function isIpAddress(value) { return /^\d{1,3}(\.\d{1,3}){3}$/.test(value) || value.includes(":"); }
function isPrivateIp(ip) {
  if (ip.includes(":")) {
    const lower = ip.toLowerCase();
    return lower === "::1" || lower.startsWith("fc") || lower.startsWith("fd") || lower.startsWith("fe80:");
  }
  const parts = ip.split(".").map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => Number.isNaN(part) || part < 0 || part > 255)) return true;
  const [a, b] = parts;
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254) || a === 0;
}

/* -------------------------------------------------------------------------- */
/* Extraction helpers                                                          */
/* -------------------------------------------------------------------------- */

function extractTagText(html, tag) {
  const match = html.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return decodeHtml(stripHtml(match?.[1] || "")).trim();
}

function extractHeadingTexts(html, tag) {
  const matches = [...html.matchAll(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "gi"))];
  return matches.map((match) => decodeHtml(stripHtml(match[1] || "")).trim()).filter(Boolean).slice(0, 20);
}

function extractMeta(html, name) {
  const patterns = [
    new RegExp(`<meta[^>]+name=["']${escapeRegExp(name)}["'][^>]*content=["']([^"']*)["'][^>]*>`, "i"),
    new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*name=["']${escapeRegExp(name)}["'][^>]*>`, "i"),
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) return decodeHtml(match[1]).trim();
  }
  return "";
}

function extractLinkRel(html, rel) {
  const patterns = [
    new RegExp(`<link[^>]+rel=["'][^"']*${escapeRegExp(rel)}[^"']*["'][^>]*href=["']([^"']*)["'][^>]*>`, "i"),
    new RegExp(`<link[^>]+href=["']([^"']*)["'][^>]*rel=["'][^"']*${escapeRegExp(rel)}[^"']*["'][^>]*>`, "i"),
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) return decodeHtml(match[1]).trim();
  }
  return "";
}

function extractLinks(html, baseUrl) {
  const links = [];
  const matches = html.matchAll(/<a\s+[^>]*href=["']([^"'#]+)["'][^>]*>/gi);
  for (const match of matches) {
    try {
      const url = new URL(decodeHtml(match[1]), baseUrl);
      url.hash = "";
      links.push(url.href);
    } catch {}
  }
  return Array.from(new Set(links)).slice(0, 500);
}

function extractImageStats(html) {
  const images = [...html.matchAll(/<img\s+[^>]*>/gi)].map((match) => match[0]);
  let missingAlt = 0;
  for (const img of images) {
    const alt = img.match(/\salt=["']([^"']*)["']/i);
    if (!alt || !String(alt[1] || "").trim()) missingAlt += 1;
  }
  return { total: images.length, missingAlt };
}

function extractLinkStats(html, baseUrl) {
  const base = new URL(baseUrl);
  let internal = 0;
  let external = 0;
  for (const href of extractLinks(html, baseUrl)) {
    try {
      const parsed = new URL(href);
      if (parsed.origin === base.origin) internal += 1;
      else external += 1;
    } catch {}
  }
  return { internal, external };
}

function extractSchemaTypes(html) {
  const types = new Set();
  for (const match of html.matchAll(/"@type"\s*:\s*"([^"]+)"/gi)) types.add(match[1]);
  for (const match of html.matchAll(/itemtype=["'][^"']*schema\.org\/([^"']+)["']/gi)) types.add(match[1]);
  return Array.from(types).slice(0, 20);
}

function extractSignals(path, text, values) {
  const haystack = `${path} ${String(text || "").slice(0, 4000)}`.toLowerCase();
  return values.filter((value) => haystack.includes(value)).slice(0, 12);
}

function stripHtml(value) {
  return String(value || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function decodeHtml(value) {
  return String(value || "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}

/* -------------------------------------------------------------------------- */
/* Classification helpers                                                      */
/* -------------------------------------------------------------------------- */

function classifyTemplateFamily(url) {
  const path = cleanPath(url).toLowerCase();
  if (isInternalAppRoute(path)) return "internal_app";
  if (isLowValuePage(path)) return "archive";
  if (path.includes("faq") || path.includes("questions-reponses")) return "qa";
  if (path.includes("privacy") || path.includes("terms") || path.includes("legal") || path.includes("mentions-legales")) return "legal_info";
  if (path.includes("/guide") || path.includes("/blog")) return "guide";
  if (hasAny(path, ["simulation", "simulateur", "calcul", "comparateur", "devis", "quote", "pricing", "demo", "booking", "reservation"])) return "conversion";
  if (hasAny(path, ["/collections/", "/collection/", "/category/", "/categorie/", "/listing", "/show", "/pass", "/ticket", "/stage", "/pilotage"])) return "category_listing";
  if (hasAny(path, ["/products/", "/product/", "/produit/", "/p/"])) return "product_detail";
  if (path.includes("contact")) return "contact";
  return "standard";
}

function estimatePageIntent(path, page) {
  const lower = cleanPath(path).toLowerCase();
  if (isInternalAppRoute(lower)) return "internal_or_auth";
  if (isLowValuePage(lower)) return "low_value_archive";
  if (hasAny(lower, ["contact", "devis", "quote", "simulation", "pricing", "demo", "booking", "reservation", "product", "collection", "ticket", "stage", "pass"])) return "money_or_conversion";
  if (hasAny(lower, ["privacy", "terms", "about", "security", "legal", "mentions-legales"])) return "trust";
  if (hasAny(`${lower} ${page?.title || ""} ${page?.h1 || ""}`, ["guide", "faq", "question", "blog", "news", "article"])) return "support_content";
  return "standard_public";
}

function routeBoundaryRisk(pages) {
  const count = (pages || []).filter((page) => isInternalAppRoute(page.url || page.final_url) && pageIsIndexable(page)).length;
  return count >= 4 ? "high" : count > 0 ? "medium" : "low";
}

function isInternalAppRoute(url) {
  const path = cleanPath(url).toLowerCase().replace(/\/$/, "");
  return INTERNAL_ROUTE_PATTERNS.some((pattern) => path === pattern || path.startsWith(`${pattern}/`));
}

function isLowValuePage(url) {
  const path = cleanPath(url).toLowerCase();
  if (/\/(20\d{2})([-/](janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december))?(\/|$)/i.test(path)) return true;
  if (/\/(20\d{2})[-/]?\d{1,2}(\/|$)/i.test(path)) return true;
  if (LOW_VALUE_SEGMENTS.some((segment) => path.includes(segment))) return true;
  return path.includes("?page=") || path.includes("&page=") || path.includes("?tag=") || path.includes("&tag=");
}

function findDuplicateCasingRoutes(pages) {
  const buckets = new Map();
  for (const page of pages || []) {
    const path = cleanPath(page.final_url || page.url || "");
    if (!path) continue;
    const lower = path.toLowerCase();
    const existing = buckets.get(lower) || new Set();
    existing.add(path);
    buckets.set(lower, existing);
  }
  const output = [];
  for (const variants of buckets.values()) if (variants.size > 1) output.push(...variants);
  return Array.from(new Set(output));
}

function findRepeatedSnapshotGroups(pages) {
  const buckets = new Map();
  for (const page of pages || []) {
    const path = cleanPath(page.final_url || page.url || "");
    if (!path || isInternalAppRoute(path)) continue;
    const title = normalizeSnapshotText(page.title || page.h1 || "");
    const description = normalizeSnapshotText(page.meta_description || "");
    const key = `${title}|${description}`;
    if (key.length < 18) continue;
    const existing = buckets.get(key) || [];
    existing.push(path);
    buckets.set(key, existing);
  }
  for (const pagesForKey of buckets.values()) if (pagesForKey.length >= 4) return pagesForKey;
  return [];
}

function normalizeSnapshotText(value) { return String(value || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 140); }
function pageIsIndexable(page) { const robots = String(page.robots || "").toLowerCase(); return page.indexable !== false && !robots.includes("noindex") && Number(page.status_code || 200) < 400; }
function statusRule(status) { if (status === 429) return "blocked_page_429"; if (status === 410) return "410_error"; if (status >= 500) return "server_error"; if (status >= 400) return "404_error"; return "fetch_error"; }
function isFailureRule(rule) { return ["404_error", "410_error", "server_error", "blocked_page_429", "fetch_error"].includes(rule); }
function statusBucket(finding) { const value = `${finding.current_value || ""} ${finding.rule || ""}`.toLowerCase(); for (const code of ["429", "404", "410", "500", "503"]) if (value.includes(code)) return code; if (value.includes("blocked")) return "blocked"; return finding.rule || "failed"; }
function groupFailureTitle(finding, family) { const bucket = statusBucket(finding); if (bucket === "429" || bucket === "blocked") return `Group blocked ${family} pages`; if (bucket === "404" || bucket === "410") return `Group missing ${family} pages`; if (bucket === "500" || bucket === "503") return `Group server errors on ${family} pages`; return "Group repeated page loading problems"; }
function groupLowValueTitle(finding) { if (finding.rule.includes("description")) return "Batch low-priority archive descriptions"; if (finding.rule.includes("title")) return "Batch low-priority archive titles"; if (finding.rule.includes("alt")) return "Batch low-priority archive image descriptions"; return "Batch low-priority archive cleanup"; }
function sameCanonicalPath(pageUrl, canonical) { try { const page = new URL(pageUrl); const canon = new URL(canonical, pageUrl); return page.origin === canon.origin && normalizeTrailingSlash(page.pathname) === normalizeTrailingSlash(canon.pathname); } catch { return false; } }
function normalizeTrailingSlash(path) { return path === "/" ? "/" : path.replace(/\/$/, ""); }

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

async function safeReadJson(req) { try { return await req.json(); } catch { return {}; } }
function resolveBudget(body) { const mode = String(body.scan_mode || body.audit_profile || "advanced").toLowerCase(); return MODE_LIMITS[mode] || MODE_LIMITS.advanced; }
function normalizeWebsiteUrl(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).href; } catch { return ""; } }
function normalizePathPrefix(value) { const path = cleanPath(value || "/"); if (!path || path === "/") return "/"; return path.endsWith("/") ? path.slice(0, -1) : path; }
function canonicalizeUrl(value) { try { const url = new URL(value); url.hash = ""; if ((url.protocol === "https:" && url.port === "443") || (url.protocol === "http:" && url.port === "80")) url.port = ""; return url.href; } catch { return ""; } }
function isHtmlContent(contentType) { return !contentType || contentType.includes("text/html") || contentType.includes("application/xhtml+xml"); }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { if (/^https?:\/\//i.test(raw)) return new URL(raw).pathname || "/"; } catch {} return raw.startsWith("/") ? raw : `/${raw}`; }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function hasAny(text, values) { const haystack = String(text || "").toLowerCase(); return values.some((value) => haystack.includes(String(value).toLowerCase())); }
function escapeRegExp(value) { return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function friendlyCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function jsonResponse(payload, status = 200) { return Response.json(payload, { status, headers: CORS_HEADERS }); }
