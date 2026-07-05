import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/2.5; +https://seoautopilot.app/bot)";

const ROBOTS_AGENT_TOKEN = "seo-autopilot";
const CRAWL_TIME_BUDGET_MS = 95000;
const MAX_HTML_BYTES = 800000;

// Screaming Frog Lite stays active by default.
const SCREAMING_FROG_LITE_DEFAULT = true;
const LARGE_HTML_BYTES = 500000;
const HEAVY_SCRIPT_TAG_COUNT = 50;
const LOW_TEXT_TO_HTML_RATIO = 3;
const MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE = 2;

const SCAN_LIMITS = {
  basic: {
    maxPages: 25,
    concurrency: 5,
    timeoutMs: 10000,
    useSitemap: false,
    discoverCompetitors: false,
    maxCompetitorSnapshots: 0,
    maxKeywords: 0,
  },
  quick: {
    maxPages: 75,
    concurrency: 8,
    timeoutMs: 12000,
    useSitemap: true,
    discoverCompetitors: false,
    maxCompetitorSnapshots: 3,
    maxKeywords: 0,
  },
  deep: {
    maxPages: 200,
    concurrency: 10,
    timeoutMs: 15000,
    useSitemap: true,
    discoverCompetitors: false,
    maxCompetitorSnapshots: 5,
    maxKeywords: 0,
  },
  advanced: {
    maxPages: 350,
    concurrency: 12,
    timeoutMs: 18000,
    useSitemap: true,
    discoverCompetitors: false,
    maxCompetitorSnapshots: 7,
    maxKeywords: 0,
  },
};

const UTILITY_PATH_RE =
  /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer|tag|category|author|feed|rss|print|share)/i;

const IMPORTANT_PAGE_RE =
  /(home|service|services|product|products|loan|loans|program|programs|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve|fix-and-flip|new-construction|bridge|rental|dscr|apply|application|menu|treatment|treatments|repair|installation|financing|mortgage|lending|case-study|case-studies)/i;

const SERVICE_LIKE_RE =
  /(service|services|product|products|loan|loans|program|programs|pricing|packages|location|locations|area|areas|repair|installation|treatment|treatments|financing|mortgage|lending|fix-and-flip|bridge|rental|dscr|hard-money)/i;

const ASSET_RE =
  /\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff|woff2|ttf|mp4|mp3|mov|avi|xml|json)$/i;

const HEADING_JUNK_RE =
  /(menu|navigation|footer|subscribe|newsletter|follow us|share|related|copyright|sign in|log in|search|cookie)/i;

const MEANINGFUL_SCHEMA_TYPES = new Set([
  "LocalBusiness",
  "Organization",
  "Product",
  "Service",
  "Review",
  "AggregateRating",
  "FAQPage",
  "BreadcrumbList",
  "HowTo",
  "Article",
  "WebSite",
]);

const PLACEHOLDER_STRONG = [
  [/\[object Object\]/, "[object Object]"],
  [/\{\{[^}]*\}\}/, "{{ }}"],
  [/\bgvar\+?\b/i, "gvar"],
];

const PLACEHOLDER_WEAK = [
  [/\bundefined\b/i, "undefined"],
  [/\bnull\b/i, "null"],
  [/\bNaN\b/, "NaN"],
  [/lorem ipsum/i, "lorem ipsum"],
  [/\bplaceholder\b/i, "placeholder"],
];

const EXCLUDED_COMPETITOR_DOMAINS = [
  "google.com",
  "facebook.com",
  "instagram.com",
  "linkedin.com",
  "youtube.com",
  "twitter.com",
  "x.com",
  "yelp.com",
  "bbb.org",
  "yellowpages.com",
  "mapquest.com",
  "chamberofcommerce.com",
  "wikipedia.org",
  "reddit.com",
  "angi.com",
  "thumbtack.com",
  "houzz.com",
  "pinterest.com",
];

Deno.serve(async (req) => {
  const startedAt = Date.now();

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        { success: false, error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await req.json();

    const {
      website_url,
      business_name = "",
      business_type = "",
      city = "",
      project_id = "",
      crawl_job_id = "",
      competitor_urls = [],
      enable_screaming_frog_lite = SCREAMING_FROG_LITE_DEFAULT,
    } = body;

    const scanMode = SCAN_LIMITS[body.scan_mode] ? body.scan_mode : "quick";
    const limits = SCAN_LIMITS[scanMode];
    const screamingFrogLiteEnabled = enable_screaming_frog_lite !== false;

    if (!website_url) {
      return Response.json(
        { success: false, error: "website_url is required" },
        { status: 400 }
      );
    }

    const normalizedUrl = normalizeStartUrl(website_url);
    const startUrl = new URL(normalizedUrl);
    const origin = startUrl.origin;
    const domain = getDomain(normalizedUrl);

    const crawlWarnings = [];
    const competitorWarnings = [];

    const [site, competitors] = await Promise.all([
      runSitePipeline({
        origin,
        domain,
        normalizedUrl,
        limits,
        crawlWarnings,
      }),
      runCompetitorPipeline({
        base44,
        user,
        project_id,
        normalizedUrl,
        domain,
        competitor_urls,
        limits,
        warnings: competitorWarnings,
      }),
    ]);

    crawlWarnings.push(...competitorWarnings);

    const { robots, sitemapUrls, crawlResult } = site;

    const {
      discoveredCompetitors,
      createdCompetitors,
      competitorResults,
      competitorPageSnapshots,
    } = competitors;

    const brokenLinks = detectBrokenInternalLinks(crawlResult.pages);
    const clientRendering = detectClientRendering(crawlResult.pages);
    const technicalAuditSummary = buildTechnicalAuditSummary(crawlResult.pages);

    const competitorComparison = buildCompetitorComparison({
      pages: crawlResult.pages,
      snapshots: competitorPageSnapshots,
    });

    const rawFindings = analyzePages({
      pages: crawlResult.pages,
      brokenLinks,
      competitorPageSnapshots,
      competitorComparison,
      clientRendering,
      business_name,
      business_type,
      city,
      screamingFrogLiteEnabled,
    });

    const groupedFindings = groupAndPrioritizeFindings(rawFindings);
    const healthScore = calculateHealthScore(groupedFindings);

    const siteSummary = buildSiteSummary({
      pages: crawlResult.pages,
      rawFindings,
      groupedFindings,
      scanMode,
      sitemapUrls,
      discoveredCompetitors,
      competitorPageSnapshots,
      brokenLinks,
      robots,
      clientRendering,
      competitorComparison,
      technicalAuditSummary,
    });

    const scanSummary = {
      score: healthScore,
      status_label:
        healthScore >= 80
          ? "Strong"
          : healthScore >= 60
            ? "Good start"
            : healthScore >= 40
              ? "Needs work"
              : "Needs urgent attention",
      plain_english_summary:
        siteSummary.plain_english_summary ||
        "The scan completed. Review the recommended actions below.",
      pages_scanned: crawlResult.pages.length,
      pages_failed: crawlResult.failed.length,
      high_priority_count: groupedFindings.filter((fix) =>
        ["critical", "high"].includes(fix.priority)
      ).length,
      competitor_gap_count: groupedFindings.filter(
        (fix) =>
          fix.category === "competitor_gap" ||
          fix.customer_category === "Competitor opportunities"
      ).length,
      technical_issue_count: groupedFindings.filter(
        (fix) => fix.customer_category === "Technical SEO"
      ).length,
      positive_findings: siteSummary.positives.join(" "),
    };

    return Response.json({
      success: true,

      scan_mode: scanMode,
      website_url,
      normalized_url: normalizedUrl,
      domain,
      scan_duration_ms: Date.now() - startedAt,

      pages_crawled: crawlResult.pages.length,
      pages_found: crawlResult.pagesFound,
      queued_remaining: crawlResult.queuedRemaining,
      health_score: healthScore,

      crawled_pages: crawlResult.pages,
      pages: crawlResult.pages,

      raw_findings: rawFindings,
      grouped_findings: groupedFindings,

      raw_fixes: groupedFindings,
      fixes: groupedFindings,
      findings: groupedFindings,
      recommendations: groupedFindings,

      scan_summary: scanSummary,
      site_summary: siteSummary,

      broken_links: brokenLinks,
      discovered_competitors: discoveredCompetitors,
      created_competitors: createdCompetitors,
      competitor_results: competitorResults,
      competitor_page_snapshots: competitorPageSnapshots,
      competitor_comparison: competitorComparison,

      client_rendering: clientRendering,
      technical_audit_summary: technicalAuditSummary,
      screaming_frog_lite_enabled: screamingFrogLiteEnabled,
      audit_profile: screamingFrogLiteEnabled ? "screaming_frog_lite" : "standard",

      competitor_urls,
      crawl_job_id,
      crawl_warnings: crawlWarnings,

      serpapi_enabled: false,
      external_serp_discovery_enabled: false,
      html_only_scan: true,
      javascript_rendering_used: false,
      deterministic_scan: true,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Advanced scan failed",
        stack: error?.stack || "",
      },
      { status: 500 }
    );
  }
});

/* ----------------------------- Pipelines ----------------------------- */

async function runSitePipeline({
  origin,
  domain,
  normalizedUrl,
  limits,
  crawlWarnings,
}) {
  const robots = await readRobotsTxt(origin, crawlWarnings);

  const sitemapUrls = limits.useSitemap
    ? await discoverSitemapUrls(origin, domain, robots, crawlWarnings)
    : [];

  const crawlResult = await crawlWebsite({
    startUrl: normalizedUrl,
    domain,
    sitemapUrls,
    robots,
    maxPages: limits.maxPages,
    concurrency: limits.concurrency,
    timeoutMs: limits.timeoutMs,
    crawlWarnings,
  });

  return { robots, sitemapUrls, crawlResult };
}

async function runCompetitorPipeline({
  base44,
  user,
  project_id,
  normalizedUrl,
  domain,
  competitor_urls,
  limits,
  warnings,
}) {
  const existing = await getExistingCompetitors(base44, project_id);

  const manual = await saveProvidedCompetitors({
    base44,
    user,
    project_id,
    competitor_urls,
    ownDomain: domain,
  });

  const discoveredCompetitors = [];
  const createdCompetitors = [];

  const competitorResults = mergeCompetitorResults({
    own_url: normalizedUrl,
    existing,
    manual,
    discovered: discoveredCompetitors,
    created: createdCompetitors,
  });

  const competitorPageSnapshots =
    limits.maxCompetitorSnapshots > 0
      ? await crawlCompetitorSnapshots({
          competitorResults,
          maxSnapshots: limits.maxCompetitorSnapshots,
          timeoutMs: 14000,
        })
      : [];

  if (
    limits.maxCompetitorSnapshots > 0 &&
    competitorResults.length === 0 &&
    Array.isArray(competitor_urls) &&
    competitor_urls.length === 0
  ) {
    warnings.push(
      "Competitor comparison uses saved or manually provided competitor URLs. No external SERP discovery is used."
    );
  }

  return {
    discoveredCompetitors,
    createdCompetitors,
    competitorResults,
    competitorPageSnapshots,
  };
}

/* ------------------------------- Crawl -------------------------------- */

async function crawlWebsite({
  startUrl,
  domain,
  sitemapUrls = [],
  robots,
  maxPages,
  concurrency,
  timeoutMs,
  crawlWarnings,
}) {
  const startedAt = Date.now();

  const queue = [];
  const queued = new Set();
  const seen = new Set();
  const pages = [];
  const failed = [];

  let queueDirty = false;
  let inFlight = 0;
  let timeBudgetHit = false;

  const prioCache = new Map();

  const prio = (url) => {
    if (!prioCache.has(url)) prioCache.set(url, priorityScore(url));
    return prioCache.get(url);
  };

  const addToQueue = (url, source = "link") => {
    const clean = canonicalizeUrl(url);

    if (!clean) return;
    if (seen.has(clean) || queued.has(clean)) return;
    if (!isSameDomain(clean, domain)) return;
    if (isAssetUrl(clean)) return;
    if (isUtilityUrl(clean)) return;
    if (isBlockedByRobots(clean, robots)) return;

    queued.add(clean);
    queue.push({ url: clean, source, priority: prio(clean) });
    queueDirty = true;
  };

  addToQueue(startUrl, "start");

  for (const url of (sitemapUrls || []).slice(0, maxPages * 2)) {
    addToQueue(url, "sitemap");
  }

  const nextItem = () => {
    if (queueDirty) {
      queue.sort(
        (a, b) => b.priority - a.priority || a.url.localeCompare(b.url)
      );
      queueDirty = false;
    }

    return queue.shift();
  };

  async function worker() {
    while (true) {
      if (pages.length + inFlight >= maxPages) return;

      if (Date.now() - startedAt > CRAWL_TIME_BUDGET_MS) {
        timeBudgetHit = true;
        return;
      }

      const item = nextItem();

      if (!item) {
        if (inFlight === 0) return;
        await sleep(100);
        continue;
      }

      queued.delete(item.url);

      if (seen.has(item.url)) continue;

      seen.add(item.url);
      inFlight++;

      try {
        const page = await fetchAndExtractPage(
          item.url,
          domain,
          timeoutMs,
          item.source
        );

        const finalUrl = canonicalizeUrl(page.url || page.final_url || item.url);

        if (finalUrl && finalUrl !== item.url) {
          if (!seen.has(finalUrl)) seen.add(finalUrl);
        }

        pages.push(page);

        if (page.fetch_error) {
          failed.push({ url: item.url, error: page.fetch_error });
        }

        if (page.status_code >= 200 && page.status_code < 400) {
          for (const link of page.internal_links || []) {
            addToQueue(link, "internal");
          }
        }
      } finally {
        inFlight--;
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));

  const finalPages = pages
    .slice(0, maxPages)
    .sort((a, b) => String(a.url || "").localeCompare(String(b.url || "")));

  if (failed.length > 0) {
    crawlWarnings.push(
      `${failed.length} page${failed.length === 1 ? "" : "s"} could not be fully read.`
    );
  }

  if (finalPages.length >= maxPages && queue.length > 0) {
    crawlWarnings.push(
      `Scan limit reached at ${maxPages} pages. A larger scan may find more pages.`
    );
  }

  if (timeBudgetHit) {
    crawlWarnings.push(
      "The scan stopped early to stay within the time limit, so some pages were not reviewed."
    );
  }

  return {
    pages: finalPages,
    pagesFound: finalPages.length + queue.length,
    queuedRemaining: queue.length,
    failed,
  };
}

async function fetchAndExtractPage(url, domain, timeoutMs, source = "unknown") {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": USER_AGENT,
        accept:
          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
      },
    });

    const contentType = response.headers.get("content-type") || "";
    const finalUrl = response.url || url;

    if (!contentType.toLowerCase().includes("text/html")) {
      return emptyPage({
        url: finalUrl,
        originalUrl: url,
        status: response.status,
        contentType,
        source,
        error: `Skipped non-HTML content: ${contentType}`,
      });
    }

    let html = await response.text();

    if (html.length > MAX_HTML_BYTES) {
      html = html.slice(0, MAX_HTML_BYTES);
    }

    return extractPageData({
      url: finalUrl,
      originalUrl: url,
      status: response.status,
      contentType,
      html,
      domain,
      source,
    });
  } catch (error) {
    const message =
      error?.name === "AbortError"
        ? "Page timed out"
        : error?.message || "Fetch failed";

    return emptyPage({
      url,
      originalUrl: url,
      status: 0,
      contentType: "",
      source,
      error: message,
    });
  } finally {
    clearTimeout(timeout);
  }
}

function extractPageData({
  url,
  originalUrl,
  status,
  contentType,
  html,
  domain,
  source = "unknown",
}) {
  const normalizedUrl = canonicalizeUrl(url);
  const originalNormalized = canonicalizeUrl(originalUrl);
  const decodedHtml = decodeHtml(html);

  const titleMatches = matchAllClean(
    decodedHtml,
    /<title[^>]*>([\s\S]*?)<\/title>/gi
  );
  const title = cleanText(titleMatches[0] || "");
  const titleCount = titleMatches.length;

  const metaDescription = cleanText(
    getMetaContent(decodedHtml, "description") ||
      getMetaProperty(decodedHtml, "og:description") ||
      getMetaName(decodedHtml, "twitter:description")
  );
  const metaDescriptionCount = countMetaNameTags(decodedHtml, "description");

  const h1s = matchAllClean(decodedHtml, /<h1[^>]*>([\s\S]*?)<\/h1>/gi)
    .filter((h) => !HEADING_JUNK_RE.test(h))
    .slice(0, 20);
  const h1 = cleanText(h1s[0] || "");

  const canonicalRaw =
    matchFirst(
      decodedHtml,
      /<link[^>]+rel=["'][^"']*canonical[^"']*["'][^>]*href=["']([^"']+)["'][^>]*>/i
    ) ||
    matchFirst(
      decodedHtml,
      /<link[^>]+href=["']([^"']+)["'][^>]*rel=["'][^"']*canonical[^"']*["'][^>]*>/i
    ) ||
    "";

  const canonicalUrl = absolutizeUrl(canonicalRaw, url);

  const robotsMeta =
    getMetaContent(decodedHtml, "robots") ||
    getMetaContent(decodedHtml, "googlebot") ||
    "";

  const pageText = extractVisibleText(decodedHtml);
  const wordCount = countWords(pageText);
  const headings = extractHeadings(decodedHtml);
  const links = extractLinks(decodedHtml, url);
  const internalLinks = links.filter((link) => isSameDomain(link, domain));
  const externalLinks = links.filter((link) => !isSameDomain(link, domain));
  const images = extractImages(decodedHtml, url);
  const faqQuestions = extractQuestions(pageText);
  const schemaTypes = detectSchemaTypes(decodedHtml);
  const trustSignals = detectTrustSignals(pageText);
  const ctaPhrases = detectCtas(pageText);
  const placeholder = detectPlaceholderText(pageText);
  const path = getPath(normalizedUrl || url);
  const scriptTagCount = (html.match(/<script/gi) || []).length;

  const responseSizeBytes = new TextEncoder().encode(String(html || "")).length;
  const textToHtmlRatio =
    Math.round(
      (String(pageText || "").length / Math.max(String(html || "").length, 1)) *
        1000
    ) / 10;

  const socialMeta = detectSocialMeta(decodedHtml);
  const hreflangs = extractHreflangs(decodedHtml, url);
  const canonicalDiagnostics = buildCanonicalDiagnostics({
    pageUrl: normalizedUrl || url,
    canonicalUrl,
    domain,
  });
  const indexability = buildIndexability({
    status,
    robotsMeta,
    canonicalDiagnostics,
  });

  return {
    url: normalizedUrl,
    original_url: originalNormalized || originalUrl,
    final_url: normalizedUrl,
    crawl_source: source,
    status_code: status,
    content_type: contentType,
    redirected: Boolean(originalNormalized && originalNormalized !== normalizedUrl),

    title,
    title_length: title.length,
    title_count: titleCount,
    meta_description: metaDescription,
    meta_description_length: metaDescription.length,
    meta_description_count: metaDescriptionCount,
    h1,
    h1s,
    h1_count: h1s.length,
    h2s: headings.h2s,
    h2_count: headings.h2s.length,
    h3s: headings.h3s,
    h3_count: headings.h3s.length,

    canonical_url: canonicalUrl,
    robots_meta: robotsMeta,
    noindex: /noindex/i.test(robotsMeta),
    nofollow: /nofollow/i.test(robotsMeta),
    indexability: indexability.status,
    indexability_reasons: indexability.reasons,
    canonical_status: canonicalDiagnostics.status,
    canonical_issue: canonicalDiagnostics.issue,
    canonical_is_self_reference: canonicalDiagnostics.isSelfReference,
    canonical_points_off_domain: canonicalDiagnostics.pointsOffDomain,

    word_count: wordCount,
    response_size_bytes: responseSizeBytes,
    html_truncated: String(html || "").length >= MAX_HTML_BYTES,
    text_to_html_ratio: textToHtmlRatio,
    visible_text_sample: pageText.slice(0, 2500),

    internal_links: stableSortUrls(Array.from(new Set(internalLinks))).slice(
      0,
      500
    ),
    external_links: stableSortUrls(Array.from(new Set(externalLinks))).slice(
      0,
      200
    ),
    internal_link_count: Array.from(new Set(internalLinks)).length,
    external_link_count: Array.from(new Set(externalLinks)).length,

    images,
    image_count: images.length,
    images_missing_alt_count: images.filter((img) => !img.has_alt).length,

    has_faq:
      faqQuestions.length >= 2 ||
      /frequently asked questions|faqs|\bfaq\b/i.test(pageText),
    faq_questions: faqQuestions,

    has_schema:
      schemaTypes.length > 0 ||
      /application\/ld\+json|schema\.org/i.test(decodedHtml),
    schema_types: schemaTypes,

    viewport_present: Boolean(getMetaContent(decodedHtml, "viewport")),
    charset_present: /<meta[^>]+charset=["']?[^"'>\s]+/i.test(decodedHtml),
    open_graph_present: socialMeta.open_graph,
    twitter_card_present: socialMeta.twitter_card,
    hreflang_count: hreflangs.length,
    hreflangs,

    has_phone: /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.test(pageText),
    has_email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(pageText),

    cta_phrases: ctaPhrases,
    trust_signals: trustSignals,

    placeholder_text: placeholder.hits,
    placeholder_strong: placeholder.strong,

    script_tag_count: scriptTagCount,
    likely_client_rendered:
      status >= 200 && status < 300 && wordCount < 80 && scriptTagCount > 10,

    is_utility_page: isUtilityPath(path),
    is_important_page: isImportantPage(path, title, h1),
    is_service_like: isServiceLikePage(path, title, h1),

    fetch_error: "",
  };
}

function emptyPage({
  url,
  originalUrl,
  status,
  contentType,
  source = "unknown",
  error = "",
}) {
  const normalizedUrl = canonicalizeUrl(url);
  const path = getPath(normalizedUrl || url);

  return {
    url: normalizedUrl || url,
    original_url: canonicalizeUrl(originalUrl) || originalUrl,
    final_url: normalizedUrl || url,
    crawl_source: source,
    status_code: status,
    content_type: contentType,
    redirected: false,

    title: "",
    title_length: 0,
    title_count: 0,
    meta_description: "",
    meta_description_length: 0,
    meta_description_count: 0,
    h1: "",
    h1s: [],
    h1_count: 0,
    h2s: [],
    h2_count: 0,
    h3s: [],
    h3_count: 0,

    canonical_url: "",
    robots_meta: "",
    noindex: false,
    nofollow: false,
    indexability: "not_indexable",
    indexability_reasons: error ? [error] : ["Page was not successfully fetched"],
    canonical_status: "missing",
    canonical_issue: "No canonical tag was found",
    canonical_is_self_reference: false,
    canonical_points_off_domain: false,

    word_count: 0,
    response_size_bytes: 0,
    html_truncated: false,
    text_to_html_ratio: 0,
    visible_text_sample: "",

    internal_links: [],
    external_links: [],
    internal_link_count: 0,
    external_link_count: 0,

    images: [],
    image_count: 0,
    images_missing_alt_count: 0,

    has_faq: false,
    faq_questions: [],

    has_schema: false,
    schema_types: [],

    viewport_present: false,
    charset_present: false,
    open_graph_present: false,
    twitter_card_present: false,
    hreflang_count: 0,
    hreflangs: [],

    has_phone: false,
    has_email: false,

    cta_phrases: [],
    trust_signals: [],

    placeholder_text: [],
    placeholder_strong: false,

    script_tag_count: 0,
    likely_client_rendered: false,

    is_utility_page: isUtilityPath(path),
    is_important_page: isImportantPage(path, "", ""),
    is_service_like: isServiceLikePage(path, "", ""),

    fetch_error: error,
  };
}

/* ---------------------- Competitor snapshots ------------------------- */

async function crawlCompetitorSnapshots({
  competitorResults,
  maxSnapshots,
  timeoutMs,
}) {
  const selected = stableDedupeCompetitors(competitorResults).slice(
    0,
    maxSnapshots
  );

  const snapshots = await Promise.all(
    selected.map(async (competitor) => {
      const url = competitor.url || competitor.website_url;
      const domain = getDomain(url);

      if (!url || !domain) return null;

      const base = {
        competitor_name: competitor.name || formatDomainName(domain),
        competitor_domain: domain,
        competitor_url: url,
        source: competitor.source || "saved",
        keyword: competitor.keyword || "",
        serp_position: competitor.position || null,
        serp_title: competitor.title || "",
        serp_snippet: competitor.snippet || "",
      };

      try {
        const page = await withTimeout(
          fetchAndExtractPage(url, domain, timeoutMs, "competitor_snapshot"),
          timeoutMs + 2000,
          "Competitor page crawl"
        );

        return {
          ...base,
          status_code: page.status_code,
          title: page.title,
          meta_description: page.meta_description,
          h1: page.h1,
          h2s: page.h2s || [],
          h3s: page.h3s || [],
          word_count: page.word_count || 0,
          has_faq: Boolean(page.has_faq),
          faq_questions: page.faq_questions || [],
          has_schema: Boolean(page.has_schema),
          schema_types: page.schema_types || [],
          has_phone: Boolean(page.has_phone),
          has_email: Boolean(page.has_email),
          cta_phrases: page.cta_phrases || [],
          trust_signals: page.trust_signals || [],
          visible_text_sample: String(page.visible_text_sample || "").slice(
            0,
            1800
          ),
        };
      } catch {
        return {
          ...base,
          ...emptySnapshotFields(),
          fetch_error: "Could not read competitor page",
        };
      }
    })
  );

  return snapshots
    .filter(Boolean)
    .sort((a, b) => {
      const aPos = a.serp_position || 99;
      const bPos = b.serp_position || 99;

      if (aPos !== bPos) return aPos - bPos;

      return String(a.competitor_domain).localeCompare(
        String(b.competitor_domain)
      );
    });
}

function emptySnapshotFields() {
  return {
    status_code: 0,
    title: "",
    meta_description: "",
    h1: "",
    h2s: [],
    h3s: [],
    word_count: 0,
    has_faq: false,
    faq_questions: [],
    has_schema: false,
    schema_types: [],
    has_phone: false,
    has_email: false,
    cta_phrases: [],
    trust_signals: [],
    visible_text_sample: "",
  };
}

/* --------------------- Client rendering / comparison ------------------ */

function detectClientRendering(pages) {
  const candidates = (pages || []).filter(
    (p) =>
      p.status_code >= 200 &&
      p.status_code < 300 &&
      p.is_important_page &&
      !p.is_utility_page
  );

  const flagged = candidates.filter((p) => p.likely_client_rendered);
  const fraction = candidates.length > 0 ? flagged.length / candidates.length : 0;

  return {
    detected: candidates.length >= 3 && fraction > 0.4,
    flagged_pages: flagged.map((p) => getPath(p.url)),
    checked_pages: candidates.length,
    fraction: Math.round(fraction * 100) / 100,
  };
}

function buildCompetitorComparison({ pages, snapshots }) {
  const yours = (pages || []).filter(
    (p) =>
      p.is_important_page &&
      !p.is_utility_page &&
      p.status_code >= 200 &&
      p.status_code < 300 &&
      !p.likely_client_rendered
  );

  const theirs = (snapshots || []).filter(
    (s) =>
      s.status_code >= 200 &&
      s.status_code < 400 &&
      Number(s.word_count || 0) > 100
  );

  if (yours.length === 0 || theirs.length === 0) return null;

  const yourHeadingText = yours
    .flatMap((p) => [p.h1, ...(p.h2s || []), ...(p.h3s || [])])
    .map(normalizeHeading)
    .filter(Boolean)
    .join(" | ");

  const topicMap = new Map();

  for (const c of theirs) {
    for (const heading of [...(c.h2s || []), ...(c.h3s || [])]) {
      const normalized = normalizeHeading(heading);

      if (!normalized) continue;

      const words = normalized.split(" ");

      if (words.length < 2 || words.length > 10) continue;
      if (HEADING_JUNK_RE.test(normalized)) continue;

      const meaningful = words.filter((w) => w.length > 3);

      if (
        meaningful.length > 0 &&
        meaningful.every((w) => yourHeadingText.includes(w))
      ) {
        continue;
      }

      const entry =
        topicMap.get(normalized) || {
          topic: cleanText(heading),
          competitors: [],
          keyword: c.keyword || "",
          serp_position: c.serp_position || null,
        };

      if (!entry.competitors.includes(c.competitor_name)) {
        entry.competitors.push(c.competitor_name);
      }

      topicMap.set(normalized, entry);
    }
  }

  const yourSchema = new Set(yours.flatMap((p) => p.schema_types || []));
  const yourTrust = new Set(yours.flatMap((p) => p.trust_signals || []));

  const theirSchema = Array.from(
    new Set(theirs.flatMap((c) => c.schema_types || []))
  );

  const theirTrust = Array.from(
    new Set(theirs.flatMap((c) => c.trust_signals || []))
  );

  return {
    competitors_compared: theirs.map((c) => ({
      name: c.competitor_name,
      domain: c.competitor_domain,
      url: c.competitor_url,
      keyword: c.keyword || "",
      serp_position: c.serp_position || null,
      word_count: c.word_count || 0,
      has_faq: Boolean(c.has_faq),
    })),
    content_depth: {
      your_median_words: median(yours.map((p) => p.word_count || 0)),
      competitor_median_words: median(theirs.map((c) => c.word_count || 0)),
      your_pages_measured: yours.length,
      competitor_pages_measured: theirs.length,
    },
    faq_coverage: {
      your_pages_with_faq: yours.filter((p) => p.has_faq).length,
      your_important_pages: yours.length,
      competitors_with_faq: theirs.filter((c) => c.has_faq).length,
      competitors_measured: theirs.length,
      competitor_faq_examples: Array.from(
        new Set(theirs.flatMap((c) => c.faq_questions || []))
      ).slice(0, 8),
    },
    schema_gaps: theirSchema
      .filter((t) => MEANINGFUL_SCHEMA_TYPES.has(t) && !yourSchema.has(t))
      .sort(),
    trust_signal_gaps: theirTrust.filter((t) => !yourTrust.has(t)).sort(),
    topic_gaps: Array.from(topicMap.values())
      .sort(
        (a, b) =>
          b.competitors.length - a.competitors.length ||
          a.topic.localeCompare(b.topic)
      )
      .slice(0, 10),
  };
}

/* ------------------------------ Analysis ------------------------------ */

function analyzePages({
  pages,
  brokenLinks,
  competitorPageSnapshots,
  competitorComparison,
  clientRendering,
  business_name,
  business_type,
  city,
  screamingFrogLiteEnabled = true,
}) {
  const findings = [];

  const importantPages = pages.filter(
    (page) => page.is_important_page && !page.is_utility_page
  );

  const brokenPages = [];
  const weakTitlePages = [];
  const missingDescriptionPages = [];
  const missingHeadingPages = [];
  const noindexPages = [];
  const canonicalPages = [];
  const thinPages = [];
  const placeholderPages = [];
  const faqGapPages = [];
  const ctaGapPages = [];
  const trustGapPages = [];
  const imageAltPages = [];

  for (const page of pages) {
    const path = getPath(page.url);

    const isUtility = page.is_utility_page || isUtilityPath(path);
    const isImportant =
      page.is_important_page || isImportantPage(path, page.title, page.h1);

    const contentSuppressed = Boolean(
      clientRendering?.detected && page.likely_client_rendered
    );

    if (page.status_code === 0 || page.status_code >= 400) {
      brokenPages.push(page);
      continue;
    }

    if (isUtility) continue;
    if (!isImportant) continue;

    if (!page.title || page.title.length < 20 || page.title.length > 70) {
      weakTitlePages.push(page);
    }

    if (!page.meta_description || page.meta_description.length < 50) {
      missingDescriptionPages.push(page);
    }

    if (!contentSuppressed && !page.h1) {
      missingHeadingPages.push(page);
    }

    if (page.noindex) {
      noindexPages.push(page);
    }

    if (!page.canonical_url) {
      canonicalPages.push(page);
    }

    if (!contentSuppressed && page.word_count < 300) {
      thinPages.push(page);
    }

    if (
      !contentSuppressed &&
      (page.placeholder_strong || (page.placeholder_text?.length || 0) >= 2)
    ) {
      placeholderPages.push({ page: path, hits: page.placeholder_text });
    }

    if (page.is_service_like && !contentSuppressed) {
      if (!page.has_faq) faqGapPages.push(page);

      if (!page.cta_phrases || page.cta_phrases.length === 0) {
        ctaGapPages.push(page);
      }

      if (!page.trust_signals || page.trust_signals.length === 0) {
        trustGapPages.push(page);
      }
    }

    if (
      page.image_count >= 5 &&
      page.images_missing_alt_count > 0 &&
      page.images_missing_alt_count / page.image_count > 0.5
    ) {
      imageAltPages.push(page);
    }
  }

  if (clientRendering?.detected) {
    findings.push(
      groupedFinding({
        id: "client-side-rendering",
        category: "js_rendering",
        customer_category: "Website setup",
        title:
          "Your website builds pages in the browser, which limits what search engines read first",
        explanation:
          "Several important pages send very little text in their initial code and rely on scripts to fill in the content afterwards.",
        why:
          "When key content only appears after scripts run, search engines can take longer to read it or may miss parts of it.",
        recommendation:
          "Ask your website platform or developer whether important pages can include their main content directly in the page code.",
        current: `${clientRendering.flagged_pages.length} of ${clientRendering.checked_pages} important pages affected`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: clientRendering.flagged_pages,
        details: {
          technical_term: "client-side rendering",
          flagged_fraction: clientRendering.fraction,
        },
      })
    );
  }

  if (brokenPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "broken-pages",
        category: "broken_page",
        customer_category: "Broken pages",
        title:
          brokenPages.length === 1
            ? "One page may not be loading correctly"
            : "Some pages may not be loading correctly",
        explanation:
          "We found pages that did not load successfully during the scan.",
        why:
          "Broken pages can frustrate visitors and make it harder for search engines to understand your website.",
        recommendation:
          "Ask your website editor or developer to review these pages and fix the links or page setup.",
        current: `${brokenPages.length} page${brokenPages.length === 1 ? "" : "s"} affected`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: brokenPages.map((p) => getPath(p.url)),
        details: { affected_count: brokenPages.length },
      })
    );
  }

  if (weakTitlePages.length > 0) {
    const examples = weakTitlePages.slice(0, 12);

    findings.push(
      groupedFinding({
        id: "weak-search-titles",
        category: "meta_title",
        customer_category: "Search appearance",
        title:
          weakTitlePages.length === 1
            ? "Improve this page’s search title"
            : "Improve search titles on important pages",
        explanation: "Some important pages may need clearer search titles.",
        why:
          "Clear search titles help people understand what each page is about before they click.",
        recommendation:
          examples.length === 1
            ? suggestSearchTitle(examples[0], business_name, business_type, city)
            : "Prepare short, unique search titles for the affected pages.",
        current: `${weakTitlePages.length} page${weakTitlePages.length === 1 ? "" : "s"} affected`,
        priority: "high",
        status: "auto_fixed",
        difficulty: "easy",
        affected_pages: weakTitlePages.map((p) => getPath(p.url)),
        details: {
          affected_count: weakTitlePages.length,
          examples: examples.map((p) => ({
            page: getPath(p.url),
            current_title: p.title || "Not found",
            suggested_title: suggestSearchTitle(
              p,
              business_name,
              business_type,
              city
            ),
          })),
        },
      })
    );
  }

  if (missingDescriptionPages.length > 0) {
    const examples = missingDescriptionPages.slice(0, 12);

    findings.push(
      groupedFinding({
        id: "missing-search-descriptions",
        category: "meta_description",
        customer_category: "Search appearance",
        title:
          missingDescriptionPages.length === 1
            ? "Add a helpful search description"
            : "Add helpful search descriptions to important pages",
        explanation:
          "Some important pages do not appear to have clear search descriptions.",
        why:
          "Search descriptions can help people understand what the page offers before they click.",
        recommendation:
          examples.length === 1
            ? suggestSearchDescription(
                examples[0],
                business_name,
                business_type,
                city
              )
            : "Prepare short, helpful search descriptions for the affected pages.",
        current: `${missingDescriptionPages.length} page${missingDescriptionPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "auto_fixed",
        difficulty: "easy",
        affected_pages: missingDescriptionPages.map((p) => getPath(p.url)),
        details: {
          affected_count: missingDescriptionPages.length,
          examples: examples.map((p) => ({
            page: getPath(p.url),
            current_description: p.meta_description || "Not found",
            suggested_description: suggestSearchDescription(
              p,
              business_name,
              business_type,
              city
            ),
          })),
        },
      })
    );
  }

  if (missingHeadingPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "missing-main-headings",
        category: "page_heading",
        customer_category: "Page content",
        title:
          missingHeadingPages.length === 1
            ? "Add a clear main heading"
            : "Add clear main headings to important pages",
        explanation: "Some important pages may not have a clear main heading.",
        why:
          "A clear heading helps visitors quickly understand what a page is about.",
        recommendation: "Add one clear main heading to each affected page.",
        current: `${missingHeadingPages.length} page${missingHeadingPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_approval",
        difficulty: "moderate",
        affected_pages: missingHeadingPages.map((p) => getPath(p.url)),
        details: { affected_count: missingHeadingPages.length },
      })
    );
  }

  if (noindexPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "noindex-important-pages",
        category: "robots_txt",
        customer_category: "Search visibility",
        title: "Review search visibility on important pages",
        explanation:
          "Some important pages may be telling search engines not to include them in search results.",
        why:
          "Important service or business pages usually need to be visible to search engines.",
        recommendation:
          "Ask your website editor or developer to confirm whether these pages should be hidden from search engines.",
        current: `${noindexPages.length} page${noindexPages.length === 1 ? "" : "s"} may be hidden`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: noindexPages.map((p) => getPath(p.url)),
        details: {
          affected_count: noindexPages.length,
          technical_term: "noindex",
        },
      })
    );
  }

  if (canonicalPages.length >= 2) {
    findings.push(
      groupedFinding({
        id: "preferred-page-settings",
        category: "canonical",
        customer_category: "Website setup",
        title: "Review preferred-page settings across important pages",
        explanation:
          "Several important pages may not clearly tell search engines which version of the page is preferred.",
        why:
          "Preferred-page settings help search engines understand the main version of important pages.",
        recommendation:
          "Ask your website editor or SEO cleanup provider to review preferred-page settings across the affected pages.",
        current: `${canonicalPages.length} page${canonicalPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: canonicalPages.map((p) => getPath(p.url)),
        details: {
          affected_count: canonicalPages.length,
          technical_term: "canonical",
        },
      })
    );
  }

  if (
    thinPages.length > 0 &&
    thinPages.length <= Math.max(5, importantPages.length * 0.75)
  ) {
    findings.push(
      groupedFinding({
        id: "thin-important-pages",
        category: "thin_content",
        customer_category: "Page content",
        title:
          thinPages.length === 1
            ? "Add more helpful content to this page"
            : "Add more helpful content to important pages",
        explanation:
          "Some important pages may not have enough useful content for visitors.",
        why:
          "Helpful pages usually explain the service, benefits, common questions, proof points, and next steps.",
        recommendation:
          "Add clearer service details, benefits, common questions, proof points, and a stronger next step.",
        current: `${thinPages.length} page${thinPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: thinPages.map((p) => getPath(p.url)),
        details: {
          affected_count: thinPages.length,
          examples: thinPages.slice(0, 12).map((p) => ({
            page: getPath(p.url),
            word_count: p.word_count,
          })),
        },
      })
    );
  }

  if (placeholderPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "placeholder-text",
        category: "placeholder_text",
        customer_category: "Website setup",
        title:
          "Important numbers may not be showing correctly to search engines",
        explanation:
          "We found placeholder-like text where important business proof or page content may belong.",
        why:
          "Important proof points, service details, and trust signals should be easy for search engines and visitors to understand.",
        recommendation:
          "Ask a developer to make sure final text and numbers appear directly in the page content, not only through scripts or placeholders.",
        current: `${placeholderPages.length} page${placeholderPages.length === 1 ? "" : "s"} affected`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: placeholderPages.map((p) => p.page),
        details: {
          affected_count: placeholderPages.length,
          examples: placeholderPages.slice(0, 12),
          technical_term: "placeholder text",
        },
      })
    );
  }

  if (faqGapPages.length > 0 && faqGapPages.length <= 25) {
    findings.push(
      groupedFinding({
        id: "faq-gaps",
        category: "faq_gap",
        customer_category: "Page content",
        title: "Add answers to common customer questions",
        explanation:
          "Some important service pages do not appear to answer common customer questions.",
        why:
          "Question-and-answer sections can help visitors make decisions and understand your services.",
        recommendation:
          "Add 4–6 common questions and answers that customers usually ask before contacting you.",
        current: `${faqGapPages.length} page${faqGapPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: faqGapPages.map((p) => getPath(p.url)),
        details: { affected_count: faqGapPages.length },
      })
    );
  }

  if (ctaGapPages.length > 0 && ctaGapPages.length <= 25) {
    findings.push(
      groupedFinding({
        id: "cta-gaps",
        category: "cta_gap",
        customer_category: "Page content",
        title: "Add clearer next steps on important pages",
        explanation:
          "Some important service pages may not clearly tell visitors what to do next.",
        why:
          "A clear next step can help more visitors contact you, book, apply, or request help.",
        recommendation:
          "Add a simple next step such as “Contact us,” “Request a quote,” “Book a call,” or “Apply now.”",
        current: `${ctaGapPages.length} page${ctaGapPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: ctaGapPages.map((p) => getPath(p.url)),
        details: { affected_count: ctaGapPages.length },
      })
    );
  }

  if (trustGapPages.length > 0 && trustGapPages.length <= 25) {
    findings.push(
      groupedFinding({
        id: "trust-signal-gaps",
        category: "trust_signal_gap",
        customer_category: "Trust signals",
        title: "Add more trust signals to important pages",
        explanation:
          "Some important service pages may not show enough proof that visitors can trust the business.",
        why:
          "Reviews, testimonials, project examples, credentials, and proof points can help visitors feel more confident.",
        recommendation:
          "Add reviews, testimonials, proof numbers, case studies, certifications, or project examples where appropriate.",
        current: `${trustGapPages.length} page${trustGapPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: trustGapPages.map((p) => getPath(p.url)),
        details: { affected_count: trustGapPages.length },
      })
    );
  }

  if (imageAltPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "image-descriptions",
        category: "image_alt_text",
        customer_category: "Images",
        title: "Improve image descriptions on important pages",
        explanation:
          "Some important pages have several images that may not have helpful descriptions.",
        why:
          "Image descriptions can help accessibility and give search engines more context.",
        recommendation:
          "Add short, useful descriptions to important images on the affected pages.",
        current: `${imageAltPages.length} page${imageAltPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: imageAltPages.map((p) => getPath(p.url)),
        details: {
          affected_count: imageAltPages.length,
          examples: imageAltPages.slice(0, 12).map((p) => ({
            page: getPath(p.url),
            image_count: p.image_count,
            missing_alt_count: p.images_missing_alt_count,
          })),
        },
      })
    );
  }

  if (brokenLinks.length > 0) {
    findings.push(
      groupedFinding({
        id: "broken-internal-links",
        category: "internal_link",
        customer_category: "Internal links",
        title: "Fix broken internal links",
        explanation:
          "Some links inside the website point to pages that may not load correctly.",
        why:
          "Broken links can frustrate visitors and make the site harder for search engines to understand.",
        recommendation:
          "Update or remove the broken links shown in the technical details.",
        current: `${brokenLinks.length} broken internal link${brokenLinks.length === 1 ? "" : "s"} found`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: brokenLinks
          .map((item) => getPath(item.source_page))
          .filter(Boolean),
        details: {
          affected_count: brokenLinks.length,
          examples: brokenLinks.slice(0, 25),
        },
      })
    );
  }

  findings.push(
    ...buildComparisonFindings({
      comparison: competitorComparison,
      snapshots: competitorPageSnapshots,
    })
  );

  if (screamingFrogLiteEnabled) {
    findings.push(...detectScreamingFrogLiteFindings(pages));
  }

  findings.push(...detectDuplicateTitles(pages));
  findings.push(...detectDuplicateDescriptions(pages));

  return dedupeFindings(findings);
}

function detectScreamingFrogLiteFindings(pages) {
  const findings = [];

  const importantPages = (pages || []).filter(
    (page) =>
      page.is_important_page &&
      !page.is_utility_page &&
      page.status_code >= 200 &&
      page.status_code < 400
  );

  const multipleTitlePages = importantPages.filter((page) => page.title_count > 1);
  const multipleMetaDescriptionPages = importantPages.filter(
    (page) => page.meta_description_count > 1
  );
  const longDescriptionPages = importantPages.filter(
    (page) => page.meta_description && page.meta_description.length > 165
  );
  const multipleH1Pages = importantPages.filter((page) => page.h1_count > 1);
  const canonicalIssuePages = importantPages.filter(
    (page) =>
      page.canonical_points_off_domain ||
      page.canonical_status === "invalid" ||
      page.canonical_status === "canonicalized"
  );
  const missingViewportPages = importantPages.filter(
    (page) => !page.viewport_present
  );
  const missingSchemaPages = importantPages.filter(
    (page) => page.is_service_like && !page.has_schema
  );
  const heavyPages = importantPages.filter(
    (page) =>
      Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
      Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT ||
      (Number(page.text_to_html_ratio || 0) > 0 &&
        Number(page.text_to_html_ratio || 0) < LOW_TEXT_TO_HTML_RATIO)
  );
  const lowInternalLinkPages = importantPages.filter(
    (page) =>
      getPath(page.url) !== "/" &&
      Number(page.internal_link_count || 0) < MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE
  );
  const missingSocialPages = importantPages.filter(
    (page) => !page.open_graph_present
  );
  const nonIndexableImportantPages = importantPages.filter(
    (page) => page.indexability !== "indexable" && !page.noindex
  );

  if (multipleTitlePages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-multiple-title-tags",
        category: "meta_title",
        customer_category: "Technical SEO",
        title: "Some pages have more than one search title tag",
        explanation:
          "We found important pages with multiple title tags in the page code.",
        why:
          "Multiple title tags can make the search result title less predictable.",
        recommendation:
          "Keep one title tag per page and remove duplicate title tags from the template or page builder.",
        current: `${multipleTitlePages.length} page${multipleTitlePages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: multipleTitlePages.map((page) => getPath(page.url)),
        details: {
          affected_count: multipleTitlePages.length,
          examples: multipleTitlePages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            title_count: page.title_count,
            title: page.title,
          })),
        },
      })
    );
  }

  if (multipleMetaDescriptionPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-multiple-meta-descriptions",
        category: "meta_description",
        customer_category: "Technical SEO",
        title: "Some pages have more than one search description tag",
        explanation:
          "We found important pages with multiple meta description tags in the page code.",
        why:
          "Multiple descriptions can make search snippets inconsistent or confusing.",
        recommendation:
          "Keep one meta description tag per page and remove duplicate description tags from the page template.",
        current: `${multipleMetaDescriptionPages.length} page${multipleMetaDescriptionPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: multipleMetaDescriptionPages.map((page) =>
          getPath(page.url)
        ),
        details: {
          affected_count: multipleMetaDescriptionPages.length,
          examples: multipleMetaDescriptionPages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            meta_description_count: page.meta_description_count,
            meta_description: page.meta_description,
          })),
        },
      })
    );
  }

  if (longDescriptionPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-long-meta-descriptions",
        category: "meta_description",
        customer_category: "Search appearance",
        title: "Shorten long search descriptions",
        explanation:
          "Some important pages have search descriptions that are likely too long to display cleanly.",
        why:
          "Shorter descriptions are easier to scan and are less likely to be cut off in search results.",
        recommendation:
          "Rewrite each affected search description so it clearly explains the page in about 140–160 characters.",
        current: `${longDescriptionPages.length} page${longDescriptionPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "auto_fixed",
        difficulty: "easy",
        affected_pages: longDescriptionPages.map((page) => getPath(page.url)),
        details: {
          affected_count: longDescriptionPages.length,
          examples: longDescriptionPages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            length: page.meta_description_length,
            current_description: page.meta_description,
            suggested_max_length: 160,
          })),
        },
      })
    );
  }

  if (multipleH1Pages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-multiple-main-headings",
        category: "page_heading",
        customer_category: "Technical SEO",
        title: "Some pages have multiple main headings",
        explanation:
          "We found important pages with more than one H1 heading.",
        why:
          "A single clear main heading helps visitors and search engines understand the page focus.",
        recommendation:
          "Keep one clear H1 per page and change extra H1s to H2 or H3 headings where appropriate.",
        current: `${multipleH1Pages.length} page${multipleH1Pages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_approval",
        difficulty: "moderate",
        affected_pages: multipleH1Pages.map((page) => getPath(page.url)),
        details: {
          affected_count: multipleH1Pages.length,
          examples: multipleH1Pages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            h1_count: page.h1_count,
            h1s: page.h1s,
          })),
        },
      })
    );
  }

  if (canonicalIssuePages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-canonical-issues",
        category: "canonical",
        customer_category: "Technical SEO",
        title: "Review canonical settings on important pages",
        explanation:
          "Some important pages point their preferred-page tag to another URL or to a URL that may not be valid.",
        why:
          "Canonical tags tell search engines which URL should be treated as the main version of a page.",
        recommendation:
          "Confirm that each important page has a self-referencing canonical URL unless you intentionally want another page indexed instead.",
        current: `${canonicalIssuePages.length} page${canonicalIssuePages.length === 1 ? "" : "s"} affected`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: canonicalIssuePages.map((page) => getPath(page.url)),
        details: {
          affected_count: canonicalIssuePages.length,
          examples: canonicalIssuePages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            canonical_url: page.canonical_url,
            canonical_status: page.canonical_status,
            canonical_issue: page.canonical_issue,
          })),
        },
      })
    );
  }

  if (nonIndexableImportantPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-non-indexable-important-pages",
        category: "indexability",
        customer_category: "Technical SEO",
        title: "Some important pages may not be indexable",
        explanation:
          "We found important pages that may be hard for search engines to include as standalone results.",
        why:
          "Important service, location, and conversion pages usually need to be indexable.",
        recommendation:
          "Review the technical reasons and make sure important pages return a successful status and are not canonicalized away by mistake.",
        current: `${nonIndexableImportantPages.length} page${nonIndexableImportantPages.length === 1 ? "" : "s"} affected`,
        priority: "high",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: nonIndexableImportantPages.map((page) =>
          getPath(page.url)
        ),
        details: {
          affected_count: nonIndexableImportantPages.length,
          examples: nonIndexableImportantPages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            status_code: page.status_code,
            indexability: page.indexability,
            reasons: page.indexability_reasons,
          })),
        },
      })
    );
  }

  if (missingViewportPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-missing-viewport",
        category: "mobile_setup",
        customer_category: "Technical SEO",
        title: "Add mobile viewport settings",
        explanation:
          "Some important pages are missing a viewport meta tag.",
        why:
          "Viewport settings help pages display correctly on mobile devices.",
        recommendation:
          "Add a standard viewport tag to the site template, such as width=device-width and initial-scale=1.",
        current: `${missingViewportPages.length} page${missingViewportPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: missingViewportPages.map((page) => getPath(page.url)),
        details: { affected_count: missingViewportPages.length },
      })
    );
  }

  if (missingSchemaPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-missing-service-schema",
        category: "schema",
        customer_category: "Technical SEO",
        title: "Add structured information to key service pages",
        explanation:
          "Some key service-style pages do not appear to include structured data.",
        why:
          "Structured data can help search engines understand services, business details, breadcrumbs, FAQs, and reviews.",
        recommendation:
          "Add appropriate schema such as LocalBusiness, Service, FAQPage, BreadcrumbList, Review, or AggregateRating where it genuinely fits.",
        current: `${missingSchemaPages.length} page${missingSchemaPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: missingSchemaPages.map((page) => getPath(page.url)),
        details: { affected_count: missingSchemaPages.length },
      })
    );
  }

  if (heavyPages.length > 0) {
    findings.push(
      groupedFinding({
        id: "sf-lite-heavy-pages",
        category: "performance_hint",
        customer_category: "Technical SEO",
        title: "Some important pages look heavy or script-heavy",
        explanation:
          "Some pages have very large HTML, many scripts, or a low amount of visible text compared with the page code.",
        why:
          "Heavy pages can load slower and make it harder for crawlers to quickly understand the main content.",
        recommendation:
          "Review scripts, page-builder output, unused app embeds, oversized templates, and content loaded only by JavaScript.",
        current: `${heavyPages.length} page${heavyPages.length === 1 ? "" : "s"} affected`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: heavyPages.map((page) => getPath(page.url)),
        details: {
          affected_count: heavyPages.length,
          examples: heavyPages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            response_size_bytes: page.response_size_bytes,
            script_tag_count: page.script_tag_count,
            text_to_html_ratio: page.text_to_html_ratio,
          })),
        },
      })
    );
  }

  if (lowInternalLinkPages.length > 0 && lowInternalLinkPages.length <= 30) {
    findings.push(
      groupedFinding({
        id: "sf-lite-low-internal-links",
        category: "internal_link",
        customer_category: "Technical SEO",
        title: "Add more internal links to important pages",
        explanation:
          "Some important pages have very few internal links pointing visitors onward to related pages.",
        why:
          "Internal links help visitors find related services and help search engines understand page relationships.",
        recommendation:
          "Add relevant links to related services, location pages, FAQs, case studies, contact pages, or conversion pages.",
        current: `${lowInternalLinkPages.length} page${lowInternalLinkPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "needs_approval",
        difficulty: "moderate",
        affected_pages: lowInternalLinkPages.map((page) => getPath(page.url)),
        details: {
          affected_count: lowInternalLinkPages.length,
          examples: lowInternalLinkPages.slice(0, 12).map((page) => ({
            page: getPath(page.url),
            internal_link_count: page.internal_link_count,
          })),
        },
      })
    );
  }

  if (missingSocialPages.length > 0 && missingSocialPages.length <= 30) {
    findings.push(
      groupedFinding({
        id: "sf-lite-missing-open-graph",
        category: "social_metadata",
        customer_category: "Technical SEO",
        title: "Add social preview information to important pages",
        explanation:
          "Some important pages are missing Open Graph metadata for link previews.",
        why:
          "Social preview information helps pages look clearer when shared in messaging apps and social platforms.",
        recommendation:
          "Add Open Graph title, description, URL, and image tags to important page templates.",
        current: `${missingSocialPages.length} page${missingSocialPages.length === 1 ? "" : "s"} affected`,
        priority: "low",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: missingSocialPages.map((page) => getPath(page.url)),
        details: { affected_count: missingSocialPages.length },
      })
    );
  }

  return findings;
}

function buildTechnicalAuditSummary(pages) {
  const safePages = pages || [];
  const importantPages = safePages.filter(
    (page) => page.is_important_page && !page.is_utility_page
  );

  return {
    pages_checked: safePages.length,
    important_pages_checked: importantPages.length,
    indexable_pages: safePages.filter((page) => page.indexability === "indexable")
      .length,
    non_indexable_pages: safePages.filter(
      (page) => page.indexability !== "indexable"
    ).length,
    missing_title_count: safePages.filter((page) => !page.title).length,
    missing_meta_description_count: safePages.filter(
      (page) => !page.meta_description
    ).length,
    missing_h1_count: safePages.filter((page) => !page.h1).length,
    multiple_h1_count: safePages.filter(
      (page) => Number(page.h1_count || 0) > 1
    ).length,
    missing_canonical_count: safePages.filter((page) => !page.canonical_url)
      .length,
    canonical_issue_count: safePages.filter(
      (page) =>
        page.canonical_status === "invalid" || page.canonical_points_off_domain
    ).length,
    missing_viewport_count: safePages.filter((page) => !page.viewport_present)
      .length,
    missing_schema_count: importantPages.filter((page) => !page.has_schema)
      .length,
    heavy_page_count: safePages.filter(
      (page) =>
        Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
        Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT
    ).length,
    average_word_count: Math.round(
      safePages.reduce((sum, page) => sum + Number(page.word_count || 0), 0) /
        Math.max(safePages.length, 1)
    ),
  };
}

function buildComparisonFindings({ comparison, snapshots }) {
  const findings = [];

  if (!comparison) {
    if ((snapshots || []).length > 0) {
      findings.push(
        groupedFinding({
          id: "competitor-content-opportunities",
          category: "competitor_gap",
          customer_category: "Competitor opportunities",
          title: "Review competitor pages for content opportunities",
          explanation:
            "We reviewed competitor pages that were saved on the project or manually provided.",
          why:
            "Competitor pages can show what services, questions, proof points, and page sections customers may expect to see.",
          recommendation:
            "Compare your most important pages against these competitor pages and add helpful sections where appropriate.",
          current: `${snapshots.length} competitor page${snapshots.length === 1 ? "" : "s"} reviewed`,
          priority: "medium",
          status: "needs_developer",
          difficulty: "moderate",
          affected_pages: ["/"],
          details: { competitor_page_snapshots: snapshots.slice(0, 5) },
        })
      );
    }

    return findings;
  }

  const depth = comparison.content_depth || {};

  if (
    depth.your_pages_measured >= 2 &&
    depth.competitor_pages_measured >= 2 &&
    depth.your_median_words > 0 &&
    depth.competitor_median_words >= depth.your_median_words * 2
  ) {
    findings.push(
      groupedFinding({
        id: "competitor-content-depth",
        category: "competitor_gap",
        customer_category: "Competitor opportunities",
        title: "Competitor pages we reviewed go much deeper than yours",
        explanation: `Competitor pages we reviewed have a typical length of about ${depth.competitor_median_words} words. Your important pages have a typical length of about ${depth.your_median_words} words.`,
        why:
          "Pages that fully explain the service, the process, pricing context, and common questions give visitors more reasons to choose you.",
        recommendation:
          "Expand your key service pages with the sections competitors cover. The topic list in the technical details shows exactly what they include that you may not.",
        current: `About ${depth.your_median_words} words on your pages vs about ${depth.competitor_median_words} on competitor pages`,
        priority: "high",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: ["/"],
        details: {
          content_depth: depth,
          competitors_compared: comparison.competitors_compared,
        },
      })
    );
  }

  const faq = comparison.faq_coverage || {};

  if (faq.competitors_with_faq >= 2 && faq.your_pages_with_faq === 0) {
    findings.push(
      groupedFinding({
        id: "competitor-faq-coverage",
        category: "competitor_gap",
        customer_category: "Competitor opportunities",
        title:
          "Competitors answer customer questions on their pages — yours don’t yet",
        explanation: `${faq.competitors_with_faq} of ${faq.competitors_measured} competitor pages we reviewed include a question-and-answer section. We did not find one on your important pages.`,
        why:
          "Customers often compare businesses by the questions their pages answer before making contact.",
        recommendation:
          "Add 4–6 real customer questions and answers to your key service pages. The technical details include example questions competitors answer.",
        current: `${faq.competitors_with_faq} of ${faq.competitors_measured} competitors have Q&A sections; your pages have 0`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: ["/"],
        details: { faq_coverage: faq },
      })
    );
  }

  if ((comparison.topic_gaps || []).length >= 3) {
    const top = comparison.topic_gaps.slice(0, 6);
    const topExamples = top
      .slice(0, 3)
      .map((t) => `“${t.topic}”`)
      .join(", ");

    findings.push(
      groupedFinding({
        id: "competitor-topic-gaps",
        category: "competitor_gap",
        customer_category: "Competitor opportunities",
        title: "Competitor pages cover topics your pages don’t mention",
        explanation: `Competitor pages include sections such as ${topExamples} that we could not find on your important pages.`,
        why:
          "These sections often answer the exact things customers compare before contacting a business.",
        recommendation:
          "Review the full topic list in the technical details and add the sections that genuinely fit your services.",
        current: `${comparison.topic_gaps.length} topic${comparison.topic_gaps.length === 1 ? "" : "s"} found on competitor pages but not yours`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: ["/"],
        details: { topic_gaps: comparison.topic_gaps },
      })
    );
  }

  if ((comparison.schema_gaps || []).length > 0) {
    findings.push(
      groupedFinding({
        id: "competitor-schema-gaps",
        category: "schema",
        customer_category: "Competitor opportunities",
        title:
          "Competitors give search engines structured business information you don’t",
        explanation: `Competitor pages include structured information types (${comparison.schema_gaps.slice(0, 4).join(", ")}) that we did not find on your pages.`,
        why:
          "Structured business information helps search engines show richer results such as stars, FAQs, and business details.",
        recommendation:
          "Ask your website platform or developer to add the missing structured information types where they fit your pages.",
        current: `Missing: ${comparison.schema_gaps.join(", ")}`,
        priority: "low",
        status: "needs_developer",
        difficulty: "developer",
        affected_pages: ["/"],
        details: {
          schema_gaps: comparison.schema_gaps,
          technical_term: "schema markup",
        },
      })
    );
  }

  if ((comparison.trust_signal_gaps || []).length >= 3) {
    findings.push(
      groupedFinding({
        id: "competitor-trust-gaps",
        category: "competitor_gap",
        customer_category: "Competitor opportunities",
        title: "Competitor pages show trust proof your pages don’t mention",
        explanation: `Competitor pages mention ${joinHumanList(comparison.trust_signal_gaps.slice(0, 4))} — signals we could not find on your important pages.`,
        why:
          "Visible proof points help visitors feel confident enough to make contact.",
        recommendation:
          "Add the proof you genuinely have — reviews, credentials, project counts, guarantees — to your key pages.",
        current: `${comparison.trust_signal_gaps.length} trust signal${comparison.trust_signal_gaps.length === 1 ? "" : "s"} found on competitor pages but not yours`,
        priority: "medium",
        status: "needs_developer",
        difficulty: "moderate",
        affected_pages: ["/"],
        details: { trust_signal_gaps: comparison.trust_signal_gaps },
      })
    );
  }

  return findings;
}

function groupedFinding({
  id,
  category,
  customer_category,
  title,
  explanation,
  why,
  recommendation,
  current,
  priority,
  status,
  difficulty,
  affected_pages,
  details = {},
}) {
  return {
    id: stableId(id),
    type: "site_level",
    page_url: affected_pages?.[0] || "/",
    category,
    customer_category,
    issue_title: title,
    title,
    plain_english_explanation: explanation,
    why_it_matters: why,
    current_value: current,
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    priority,
    difficulty,
    status,
    can_auto_fix: status === "auto_fixed",
    requires_approval: status === "needs_approval",
    requires_developer: status === "needs_developer",
    affected_pages: Array.from(new Set(affected_pages || [])).slice(0, 150),
    details,
    confidence_score: 90,
  };
}

function groupAndPrioritizeFindings(findings) {
  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const statusOrder = {
    needs_approval: 0,
    auto_fixed: 1,
    needs_developer: 2,
    open: 3,
  };

  return dedupeFindings(findings)
    .sort((a, b) => {
      const aPriority = priorityOrder[a.priority] ?? 9;
      const bPriority = priorityOrder[b.priority] ?? 9;

      if (aPriority !== bPriority) return aPriority - bPriority;

      const aStatus = statusOrder[a.status] ?? 9;
      const bStatus = statusOrder[b.status] ?? 9;

      if (aStatus !== bStatus) return aStatus - bStatus;

      const aTitle = String(a.issue_title || "");
      const bTitle = String(b.issue_title || "");

      if (aTitle !== bTitle) return aTitle.localeCompare(bTitle);

      return String(a.page_url || "").localeCompare(String(b.page_url || ""));
    })
    .slice(0, 28);
}

function dedupeFindings(findings) {
  const map = new Map();

  for (const finding of findings || []) {
    const key =
      finding.id ||
      `${finding.category}|${finding.issue_title}|${(finding.affected_pages || []).join(",")}`;

    if (!map.has(key)) {
      map.set(key, finding);
      continue;
    }

    const existing = map.get(key);

    map.set(key, {
      ...existing,
      affected_pages: Array.from(
        new Set([...(existing.affected_pages || []), ...(finding.affected_pages || [])])
      ).slice(0, 150),
    });
  }

  return Array.from(map.values());
}

function detectDuplicateTitles(pages) {
  const map = new Map();
  const findings = [];

  for (const page of pages || []) {
    if (!page.title) continue;
    if (!page.is_important_page) continue;
    if (page.is_utility_page) continue;

    const key = page.title.trim().toLowerCase();

    if (!map.has(key)) map.set(key, []);

    map.get(key).push(getPath(page.url));
  }

  for (const [title, affectedPages] of Array.from(map.entries()).sort()) {
    const unique = Array.from(new Set(affectedPages)).sort();

    if (unique.length <= 1) continue;

    findings.push(
      groupedFinding({
        id: `duplicate-title-${title}`,
        category: "duplicate_search_titles",
        customer_category: "Search appearance",
        title: "Several important pages use the same search title",
        explanation:
          "Multiple important pages appear to use the same search title.",
        why:
          "Unique search titles help visitors and search engines understand the purpose of each page.",
        recommendation:
          "Review the affected pages and prepare unique search titles for each one.",
        current: title,
        priority: "medium",
        status: "needs_approval",
        difficulty: "easy",
        affected_pages: unique,
        details: {
          affected_count: unique.length,
          technical_term: "duplicate title",
        },
      })
    );
  }

  return findings;
}

function detectDuplicateDescriptions(pages) {
  const map = new Map();
  const findings = [];

  for (const page of pages || []) {
    if (!page.meta_description) continue;
    if (!page.is_important_page) continue;
    if (page.is_utility_page) continue;

    const key = page.meta_description.trim().toLowerCase();

    if (!map.has(key)) map.set(key, []);

    map.get(key).push(getPath(page.url));
  }

  for (const [description, affectedPages] of Array.from(map.entries()).sort()) {
    const unique = Array.from(new Set(affectedPages)).sort();

    if (unique.length <= 1) continue;

    findings.push(
      groupedFinding({
        id: `duplicate-description-${description}`,
        category: "meta_description",
        customer_category: "Search appearance",
        title: "Several important pages use the same search description",
        explanation:
          "Multiple important pages appear to use the same search description.",
        why:
          "Unique search descriptions can make each important page clearer in search results.",
        recommendation:
          "Prepare a unique search description for each affected page.",
        current: clamp(description, 160),
        priority: "medium",
        status: "auto_fixed",
        difficulty: "easy",
        affected_pages: unique,
        details: {
          affected_count: unique.length,
          technical_term: "duplicate search description",
        },
      })
    );
  }

  return findings;
}

/* ---------------------- Competitor records ---------------------- */

async function getExistingCompetitors(base44, project_id) {
  if (!project_id) return [];

  try {
    if (!base44.entities?.Competitor?.filter) return [];

    const rows = await base44.entities.Competitor.filter({ project_id });

    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

async function saveProvidedCompetitors({
  base44,
  user,
  project_id,
  competitor_urls,
  ownDomain,
}) {
  const urls = (competitor_urls || [])
    .map((url) => String(url || "").trim())
    .filter(Boolean);

  if (!project_id || urls.length === 0) {
    return urls.map((url) => ({
      name: formatDomainName(getDomain(url)),
      website_url: normalizeUrl(url),
      url: normalizeUrl(url),
      domain: getDomain(url),
      source: "manual",
      position: 99,
    }));
  }

  const existing = await getExistingCompetitors(base44, project_id);

  const existingDomains = new Set(
    existing.map((item) => getDomain(item.website_url))
  );

  const manualItems = [];
  const toCreate = [];

  for (const rawUrl of urls) {
    const normalized = normalizeUrl(rawUrl);
    const domain = getDomain(normalized);

    if (!isValidCompetitorDomain(domain, ownDomain)) continue;

    const item = {
      project_id,
      owner_user_id: user.id,
      name: formatDomainName(domain),
      website_url: normalized,
      url: normalized,
      domain,
      source: "manual",
      position: 99,
      notes: "Added from Scan Website.",
      service_pages_count: 0,
      title_quality_score: 0,
      meta_coverage_pct: 0,
      content_depth_score: 0,
      faq_usage: false,
      schema_usage: false,
      broken_links_count: 0,
    };

    manualItems.push(item);

    if (!existingDomains.has(domain)) {
      toCreate.push(item);
    }
  }

  try {
    if (
      project_id &&
      toCreate.length > 0 &&
      base44.entities?.Competitor?.bulkCreate
    ) {
      await base44.entities.Competitor.bulkCreate(toCreate);
    }
  } catch {
    // Do not fail the scan if competitor saving fails.
  }

  return manualItems;
}

function mergeCompetitorResults({
  own_url,
  existing,
  manual,
  discovered,
  created,
}) {
  const ownDomain = getDomain(own_url);
  const map = new Map();

  for (const item of [
    ...(discovered || []),
    ...(created || []),
    ...(manual || []),
    ...(existing || []),
  ]) {
    const website_url =
      item.website_url || item.url || item.original_result_url || "";

    const domain = item.domain || getDomain(website_url);

    if (!isValidCompetitorDomain(domain, ownDomain)) continue;

    const current = map.get(domain);

    const candidate = {
      name: item.name || formatDomainName(domain),
      website_url,
      url: item.original_result_url || website_url,
      domain,
      source: item.source || "saved",
      keyword: item.keyword || "",
      title: item.title || "",
      snippet: item.snippet || "",
      position: item.position || 99,
      query: item.query || "",
    };

    if (!current || candidate.position < current.position) {
      map.set(domain, candidate);
    }
  }

  return Array.from(map.values())
    .sort((a, b) => {
      const posDiff = (a.position || 99) - (b.position || 99);

      if (posDiff !== 0) return posDiff;

      return String(a.domain).localeCompare(String(b.domain));
    })
    .slice(0, 10);
}

function stableDedupeCompetitors(items) {
  const map = new Map();

  for (const item of items || []) {
    const url = item.website_url || item.url || "";
    const domain = item.domain || getDomain(url);

    if (!domain) continue;

    const current = map.get(domain);
    const candidate = { ...item, domain };

    if (!current || (candidate.position || 99) < (current.position || 99)) {
      map.set(domain, candidate);
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    const posDiff = (a.position || 99) - (b.position || 99);

    if (posDiff !== 0) return posDiff;

    return String(a.domain).localeCompare(String(b.domain));
  });
}

function isValidCompetitorDomain(domain, ownDomain) {
  if (!domain) return false;
  if (!ownDomain) return false;
  if (domain === ownDomain) return false;
  if (domain.endsWith(`.${ownDomain}`)) return false;

  return !EXCLUDED_COMPETITOR_DOMAINS.some(
    (blocked) => domain === blocked || domain.endsWith(`.${blocked}`)
  );
}

/* --------------------------- robots / sitemap -------------------------- */

async function readRobotsTxt(origin, warnings) {
  try {
    const response = await withTimeout(
      fetch(`${origin}/robots.txt`, {
        headers: {
          "user-agent": USER_AGENT,
          accept: "text/plain,*/*",
        },
      }),
      5000,
      "robots.txt"
    );

    if (!response.ok) {
      return { found: false, disallow: [], sitemaps: [] };
    }

    const text = await response.text();

    return parseRobotsTxt(text);
  } catch {
    warnings.push("Could not read robots.txt.");
    return { found: false, disallow: [], sitemaps: [] };
  }
}

function parseRobotsTxt(text) {
  const lines = String(text || "").split(/\r?\n/);
  const disallow = [];
  const sitemaps = [];

  let currentAgents = [];
  let collectingAgents = true;

  const groupApplies = () =>
    currentAgents.some(
      (agent) => agent === "*" || agent.includes(ROBOTS_AGENT_TOKEN)
    );

  for (const rawLine of lines) {
    const line = rawLine.split("#")[0].trim();

    if (!line) continue;

    const separatorIndex = line.indexOf(":");

    if (separatorIndex === -1) continue;

    const key = line.slice(0, separatorIndex).trim().toLowerCase();
    const value = line.slice(separatorIndex + 1).trim();

    if (key === "sitemap") {
      if (value) sitemaps.push(value);
      continue;
    }

    if (key === "user-agent") {
      if (!collectingAgents) {
        currentAgents = [];
        collectingAgents = true;
      }

      if (value) currentAgents.push(value.toLowerCase());

      continue;
    }

    if (key === "disallow" || key === "allow") {
      collectingAgents = false;

      if (key === "disallow" && value && value !== "/" && groupApplies()) {
        disallow.push(value);
      }

      continue;
    }

    collectingAgents = false;
  }

  return {
    found: true,
    disallow: Array.from(new Set(disallow)).sort(),
    sitemaps: Array.from(new Set(sitemaps)).sort(),
  };
}

function isBlockedByRobots(url, robots) {
  if (!robots?.disallow?.length) return false;

  const path = getPath(url);

  return robots.disallow.some((rule) => {
    if (!rule || rule === "/") return false;

    const cleanRule = rule.split("*")[0];

    if (!cleanRule) return false;

    return path.startsWith(cleanRule);
  });
}

async function discoverSitemapUrls(origin, domain, robots, warnings) {
  const candidates = [
    ...(robots?.sitemaps || []),
    `${origin}/sitemap.xml`,
    `${origin}/sitemap_index.xml`,
  ];

  const all = [];

  for (const sitemapUrl of Array.from(new Set(candidates))) {
    try {
      const urls = await fetchSitemapUrls(sitemapUrl, domain, 0);

      all.push(...urls);
    } catch {
      warnings.push(`Could not read sitemap: ${sitemapUrl}`);
    }
  }

  return stableSortUrls(
    Array.from(new Set(all))
      .filter((url) => isSameDomain(url, domain))
      .filter((url) => !isAssetUrl(url))
      .filter((url) => !isUtilityUrl(url))
  );
}

async function fetchSitemapUrls(sitemapUrl, domain, depth) {
  if (depth > 2) return [];

  const response = await withTimeout(
    fetch(sitemapUrl, {
      headers: {
        "user-agent": USER_AGENT,
        accept: "application/xml,text/xml,*/*",
      },
    }),
    8000,
    "sitemap"
  );

  if (!response.ok) return [];

  const xml = await response.text();
  const locs = extractUrlsFromSitemap(xml);

  const sitemapLocs = locs.filter((url) => /\.xml($|\?)/i.test(url));
  const pageUrls = locs.filter((url) => !/\.xml($|\?)/i.test(url));

  const childResults = await Promise.all(
    sitemapLocs.slice(0, 10).map((child) =>
      fetchSitemapUrls(child, domain, depth + 1).catch(() => [])
    )
  );

  pageUrls.push(...childResults.flat());

  return stableSortUrls(pageUrls);
}

function extractUrlsFromSitemap(xml) {
  const urls = [];
  const re = /<loc>\s*([^<]+)\s*<\/loc>/gi;

  let match;

  while ((match = re.exec(xml)) !== null) {
    urls.push(decodeHtml(match[1].trim()));
  }

  return urls;
}

/* ---------------------------- Broken links ----------------------------- */

function detectBrokenInternalLinks(pages) {
  const statusMap = new Map();

  for (const page of pages || []) {
    statusMap.set(canonicalizeUrl(page.url), page.status_code);
  }

  const broken = [];

  for (const page of pages || []) {
    for (const link of page.internal_links || []) {
      const clean = canonicalizeUrl(link);
      const status = statusMap.get(clean);

      if (status && status >= 400) {
        broken.push({
          source_page: page.url,
          broken_link: clean,
          status_code: status,
        });
      }
    }
  }

  return dedupeBrokenLinks(broken);
}

function dedupeBrokenLinks(items) {
  const seen = new Set();
  const output = [];

  for (const item of items || []) {
    const key = `${item.source_page}|${item.broken_link}|${item.status_code}`;

    if (seen.has(key)) continue;

    seen.add(key);
    output.push(item);
  }

  return output.sort((a, b) => {
    const sourceDiff = String(a.source_page).localeCompare(
      String(b.source_page)
    );

    if (sourceDiff !== 0) return sourceDiff;

    return String(a.broken_link).localeCompare(String(b.broken_link));
  });
}

/* ------------------------------ Summary -------------------------------- */

function buildSiteSummary({
  pages,
  rawFindings,
  groupedFindings,
  scanMode,
  sitemapUrls,
  discoveredCompetitors,
  competitorPageSnapshots,
  brokenLinks,
  robots,
  clientRendering,
  competitorComparison,
  technicalAuditSummary,
}) {
  const importantPages = pages.filter((p) => p.is_important_page);
  const pagesWithFaq = pages.filter((p) => p.has_faq);
  const pagesWithTrust = pages.filter((p) => p.trust_signals?.length > 0);
  const pagesWithCta = pages.filter((p) => p.cta_phrases?.length > 0);
  const pagesWithSchema = pages.filter((p) => p.has_schema);
  const noindexPages = pages.filter((p) => p.noindex);

  const positives = [];

  if (importantPages.length >= 4) {
    positives.push("Your site has several important service or business pages.");
  }

  if (pagesWithTrust.length >= 1) {
    positives.push(
      "Your site includes trust signals such as reviews, proof points, or testimonials."
    );
  }

  if (pagesWithCta.length >= 1) {
    positives.push(
      "Your site includes calls to action that help visitors take the next step."
    );
  }

  if (pagesWithFaq.length >= 1) {
    positives.push("Your site answers some customer questions.");
  }

  if (pagesWithSchema.length >= 1) {
    positives.push("Your site includes structured trust or business information.");
  }

  const plainParts = [];

  if (groupedFindings.length === 0) {
    plainParts.push("No major issues stood out from the pages we could access.");
  } else {
    const high = groupedFindings.filter((f) =>
      ["critical", "high"].includes(f.priority)
    ).length;

    plainParts.push(
      high > 0
        ? `We found ${high} high-priority improvement${high === 1 ? "" : "s"} to review first.`
        : "We found a few medium and low-priority improvements to review."
    );
  }

  if (competitorComparison?.competitors_compared?.length) {
    plainParts.push(
      `We compared your site with ${competitorComparison.competitors_compared.length} saved or manually provided competitor page${competitorComparison.competitors_compared.length === 1 ? "" : "s"}.`
    );
  }

  if (clientRendering?.detected) {
    plainParts.push(
      "Some important pages appear to rely heavily on browser-rendered content, so content checks may need manual review."
    );
  }

  return {
    positives,
    plain_english_summary: plainParts.join(" "),
    raw_findings_count: rawFindings.length,
    total_findings: groupedFindings.length,
    important_pages_found: importantPages.length,
    pages_with_faq: pagesWithFaq.length,
    pages_with_trust_signals: pagesWithTrust.length,
    pages_with_cta: pagesWithCta.length,
    pages_with_schema: pagesWithSchema.length,
    noindex_pages: noindexPages.length,
    scan_mode: scanMode,
    sitemap_urls_found: sitemapUrls.length,
    robots_found: Boolean(robots?.found),
    broken_links_count: brokenLinks.length,
    competitors_found: discoveredCompetitors.length,
    competitor_snapshots_read: competitorPageSnapshots.length,
    client_rendering: clientRendering,
    technical_audit_summary: technicalAuditSummary || buildTechnicalAuditSummary(pages),
  };
}

function calculateHealthScore(findings) {
  let score = 100;

  for (const finding of findings || []) {
    if (finding.priority === "critical") score -= 16;
    else if (finding.priority === "high") score -= 10;
    else if (finding.priority === "medium") score -= 5;
    else if (finding.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

/* --------------------------- Screaming Frog Lite helpers --------------------------- */

function countMetaNameTags(html, name) {
  const escaped = escapeRegExp(name);
  const re = new RegExp(
    `<meta[^>]+(?:name|property)=["']${escaped}["'][^>]*>`,
    "gi"
  );

  return (String(html || "").match(re) || []).length;
}

function detectSocialMeta(html) {
  return {
    open_graph: /<meta[^>]+property=["']og:/i.test(String(html || "")),
    twitter_card: /<meta[^>]+name=["']twitter:/i.test(String(html || "")),
  };
}

function extractHreflangs(html, baseUrl) {
  const output = [];
  const re = /<link\b[^>]*rel=["'][^"']*alternate[^"']*["'][^>]*>/gi;

  let match;

  while ((match = re.exec(String(html || ""))) !== null) {
    const tag = match[0];
    const hreflang = matchFirst(tag, /\bhreflang=["']([^"']+)["']/i);
    const href = matchFirst(tag, /\bhref=["']([^"']+)["']/i);

    if (!hreflang || !href) continue;

    output.push({
      hreflang: hreflang.toLowerCase(),
      href: absolutizeUrl(href, baseUrl),
    });
  }

  return output.slice(0, 50);
}

function buildCanonicalDiagnostics({ pageUrl, canonicalUrl, domain }) {
  const page = canonicalizeUrl(pageUrl);
  const canonical = canonicalizeUrl(canonicalUrl);

  if (!canonicalUrl) {
    return {
      status: "missing",
      issue: "No canonical tag was found",
      isSelfReference: false,
      pointsOffDomain: false,
    };
  }

  if (!canonical) {
    return {
      status: "invalid",
      issue: "Canonical URL could not be read",
      isSelfReference: false,
      pointsOffDomain: false,
    };
  }

  const canonicalDomain = getDomain(canonical);
  const pointsOffDomain = Boolean(domain && canonicalDomain && canonicalDomain !== domain);
  const isSelfReference = Boolean(page && canonical && page === canonical);

  if (pointsOffDomain) {
    return {
      status: "off_domain",
      issue: "Canonical URL points to a different domain",
      isSelfReference,
      pointsOffDomain,
    };
  }

  if (!isSelfReference) {
    return {
      status: "canonicalized",
      issue: "Canonical URL points to a different page",
      isSelfReference,
      pointsOffDomain,
    };
  }

  return {
    status: "self_reference",
    issue: "",
    isSelfReference,
    pointsOffDomain,
  };
}

function buildIndexability({ status, robotsMeta, canonicalDiagnostics }) {
  const reasons = [];

  if (status < 200 || status >= 300) {
    reasons.push(`HTTP status ${status}`);
  }

  if (/noindex/i.test(robotsMeta || "")) {
    reasons.push("Meta robots noindex");
  }

  if (canonicalDiagnostics?.status === "canonicalized") {
    reasons.push("Canonical points to another URL");
  }

  if (canonicalDiagnostics?.status === "off_domain") {
    reasons.push("Canonical points to another domain");
  }

  if (canonicalDiagnostics?.status === "invalid") {
    reasons.push("Canonical URL is invalid");
  }

  return {
    status: reasons.length === 0 ? "indexable" : "not_indexable",
    reasons,
  };
}

/* ------------------------------- Helpers ------------------------------- */

function normalizeStartUrl(input) {
  let url = String(input || "").trim();

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  return canonicalizeUrl(url);
}

function normalizeUrl(input) {
  let url = String(input || "").trim();

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  return canonicalizeUrl(url);
}

function normalizeCompetitorUrl(input) {
  try {
    const url = new URL(normalizeUrl(input));

    url.hash = "";
    url.search = "";

    return url.origin;
  } catch {
    return input;
  }
}

function canonicalizeUrl(input) {
  try {
    const url = new URL(input);

    url.hash = "";

    const removable = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content",
      "gclid",
      "fbclid",
      "msclkid",
    ];

    for (const param of removable) {
      url.searchParams.delete(param);
    }

    if (url.pathname !== "/" && url.pathname.endsWith("/")) {
      url.pathname = url.pathname.slice(0, -1);
    }

    return url.toString();
  } catch {
    return "";
  }
}

function absolutizeUrl(href, base) {
  if (!href) return "";

  try {
    return canonicalizeUrl(new URL(href, base).toString());
  } catch {
    return "";
  }
}

function getDomain(input) {
  try {
    const value = String(input || "");
    const url = /^https?:\/\//i.test(value) ? value : `https://${value}`;

    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return "";
  }
}

function getPath(input) {
  try {
    return new URL(input).pathname || "/";
  } catch {
    return input || "/";
  }
}

function isSameDomain(input, domain) {
  return getDomain(input) === domain;
}

function isAssetUrl(input) {
  return ASSET_RE.test(String(input || "").split("?")[0]);
}

function isUtilityUrl(input) {
  return isUtilityPath(getPath(input));
}

function isUtilityPath(path) {
  return UTILITY_PATH_RE.test(path);
}

function isImportantPage(path, title = "", h1 = "") {
  if (path === "/") return true;

  return IMPORTANT_PAGE_RE.test(`${path}|${title}|${h1}`);
}

function isServiceLikePage(path, title = "", h1 = "") {
  if (path === "/") return true;

  return SERVICE_LIKE_RE.test(`${path}|${title}|${h1}`);
}

function priorityScore(url) {
  const path = getPath(url).toLowerCase();

  if (path === "/") return 100;

  if (
    /service|services|product|products|program|programs|loan|loans|pricing|packages|fix-and-flip|bridge|rental|dscr|hard-money/.test(
      path
    )
  ) {
    return 90;
  }

  if (/about|contact|location|locations|areas-we-serve|service-area/.test(path)) {
    return 80;
  }

  if (/case-study|case-studies|portfolio|work|projects/.test(path)) {
    return 70;
  }

  if (/blog|article|news|guide/.test(path)) {
    return 45;
  }

  return 50;
}

function extractVisibleText(html) {
  return cleanText(
    decodeHtml(
      String(html || "")
        .replace(/<script[\s\S]*?<\/script>/gi, " ")
        .replace(/<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
        .replace(/<!--[\s\S]*?-->/g, " ")
        .replace(/<[^>]+>/g, " ")
    )
  );
}

function extractLinks(html, baseUrl) {
  const links = [];
  const re = /<a[^>]+href=["']([^"']+)["'][^>]*>/gi;

  let match;

  while ((match = re.exec(String(html || ""))) !== null) {
    const href = match[1];

    if (!href) continue;
    if (/^(mailto:|tel:|javascript:|#)/i.test(href)) continue;

    const absolute = absolutizeUrl(href, baseUrl);

    if (absolute) links.push(absolute);
  }

  return stableSortUrls(Array.from(new Set(links)));
}

function extractImages(html, baseUrl) {
  const images = [];
  const re = /<img\b[^>]*>/gi;

  let match;

  while ((match = re.exec(String(html || ""))) !== null) {
    const tag = match[0];

    const src =
      matchFirst(tag, /\bsrc=["']([^"']+)["']/i) ||
      matchFirst(tag, /\bdata-src=["']([^"']+)["']/i) ||
      "";

    if (!src) continue;

    const alt = matchFirst(tag, /\balt=["']([^"']*)["']/i);

    images.push({
      src: absolutizeUrl(src, baseUrl),
      alt: cleanText(alt),
      has_alt: Boolean(cleanText(alt)),
    });
  }

  return images.slice(0, 200);
}

function extractHeadings(html) {
  return {
    h2s: matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi)
      .filter((h) => !HEADING_JUNK_RE.test(h))
      .slice(0, 30),
    h3s: matchAllClean(html, /<h3[^>]*>([\s\S]*?)<\/h3>/gi)
      .filter((h) => !HEADING_JUNK_RE.test(h))
      .slice(0, 40),
  };
}

function extractQuestions(text) {
  const output = [];
  const re = /([^?.!]{8,120}\?)/g;

  let match;

  while ((match = re.exec(String(text || ""))) !== null) {
    const question = cleanText(match[1]);

    if (question && !HEADING_JUNK_RE.test(question)) {
      output.push(question);
    }
  }

  return Array.from(new Set(output)).slice(0, 10);
}

function detectSchemaTypes(html) {
  const found = new Set();

  for (const type of MEANINGFUL_SCHEMA_TYPES) {
    const re = new RegExp(
      `["']@type["']\\s*:\\s*["']${escapeRegExp(type)}["']`,
      "i"
    );

    if (re.test(html)) found.add(type);
  }

  const schemaOrgMatches = matchAllRaw(html, /schema\.org\/([A-Za-z0-9]+)/gi);

  for (const type of schemaOrgMatches) {
    if (MEANINGFUL_SCHEMA_TYPES.has(type)) found.add(type);
  }

  return Array.from(found).sort();
}

function detectTrustSignals(text) {
  const signals = [];

  const checks = [
    [/reviews?|testimonials?/i, "reviews or testimonials"],
    [/\blicen[cs]ed\b/i, "licensed"],
    [/\binsured\b/i, "insured"],
    [/\bbonded\b/i, "bonded"],
    [/certified|certification|accredited/i, "certifications"],
    [/guarantee|warranty/i, "guarantees"],
    [/case studies?|success stories?/i, "case studies"],
    [/\b\d+\+?\s*(years|clients|customers|projects|homes|businesses)\b/i, "proof numbers"],
    [/award|rated|rating|stars/i, "ratings or awards"],
  ];

  for (const [re, label] of checks) {
    if (re.test(text)) signals.push(label);
  }

  return Array.from(new Set(signals)).sort();
}

function detectCtas(text) {
  const phrases = [];

  const checks = [
    [/contact us|contact today|get in touch/i, "contact"],
    [/request (a )?(quote|consultation|callback)/i, "request quote"],
    [/book (now|online|a call|an appointment)/i, "book"],
    [/schedule (a )?(call|consultation|appointment)/i, "schedule"],
    [/apply (now|today|online)/i, "apply"],
    [/call (now|today)|phone/i, "call"],
    [/get started|start now/i, "get started"],
  ];

  for (const [re, label] of checks) {
    if (re.test(text)) phrases.push(label);
  }

  return Array.from(new Set(phrases)).sort();
}

function detectPlaceholderText(text) {
  const hits = [];
  let strong = false;

  for (const [re, label] of PLACEHOLDER_STRONG) {
    if (re.test(text)) {
      hits.push(label);
      strong = true;
    }
  }

  for (const [re, label] of PLACEHOLDER_WEAK) {
    if (re.test(text)) {
      hits.push(label);
    }
  }

  return {
    strong,
    hits: Array.from(new Set(hits)),
  };
}

function normalizeHeading(input) {
  return cleanText(input)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function countWords(text) {
  return String(text || "")
    .split(/\s+/)
    .filter((word) => /[A-Za-z0-9]/.test(word)).length;
}

function suggestSearchTitle(page, businessName, businessType, city) {
  const path = getPath(page.url);

  if (path === "/") {
    return clamp(
      [businessName || "Home", businessType, city].filter(Boolean).join(" | "),
      65
    );
  }

  const pageName =
    path.split("/").filter(Boolean).pop()?.replace(/[-_]/g, " ") ||
    page.h1 ||
    page.title ||
    "Service";

  return clamp([pageName, businessName, city].filter(Boolean).join(" | "), 65);
}

function suggestSearchDescription(page, businessName, businessType, city) {
  const path = getPath(page.url);
  const name = businessName || "This business";

  if (path === "/") {
    const type = businessType || "services";

    return clamp(
      city
        ? `${name} provides ${type} in ${city}. Learn more, review your options, and contact the team today.`
        : `${name} provides ${type}. Learn more, review your options, and contact the team today.`,
      160
    );
  }

  const pageName =
    path.split("/").filter(Boolean).pop()?.replace(/[-_]/g, " ") ||
    "this service";

  return clamp(
    `Learn about ${pageName} from ${name}. See key details, benefits, common questions, and how to get started.`,
    160
  );
}

function getMetaContent(html, name) {
  return getMetaName(html, name);
}

function getMetaName(html, name) {
  const escaped = escapeRegExp(name);

  return (
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+name=["']${escaped}["'][^>]*content=["']([^"']*)["'][^>]*>`,
        "i"
      )
    ) ||
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+content=["']([^"']*)["'][^>]*name=["']${escaped}["'][^>]*>`,
        "i"
      )
    ) ||
    ""
  );
}

function getMetaProperty(html, property) {
  const escaped = escapeRegExp(property);

  return (
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+property=["']${escaped}["'][^>]*content=["']([^"']*)["'][^>]*>`,
        "i"
      )
    ) ||
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+content=["']([^"']*)["'][^>]*property=["']${escaped}["'][^>]*>`,
        "i"
      )
    ) ||
    ""
  );
}

function clamp(value, max) {
  const text = String(value || "").trim();

  if (text.length <= max) return text;

  return text.slice(0, max - 1).trim();
}

function matchFirst(input, re) {
  const match = String(input || "").match(re);

  return match?.[1] || "";
}

function matchAllClean(input, re) {
  const output = [];

  let match;

  while ((match = re.exec(String(input || ""))) !== null) {
    const value = cleanText(decodeHtml(match[1]));

    if (value) output.push(value);
  }

  return Array.from(new Set(output)).sort();
}

function matchAllRaw(input, re) {
  const output = [];

  let match;

  while ((match = re.exec(String(input || ""))) !== null) {
    if (match[1]) output.push(match[1]);
  }

  return output;
}

function cleanText(input) {
  return String(input || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function decodeHtml(input) {
  return String(input || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ");
}

function escapeRegExp(input) {
  return String(input || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function stableSortUrls(urls) {
  return Array.from(new Set((urls || []).filter(Boolean))).sort((a, b) =>
    String(a).localeCompare(String(b))
  );
}

function median(values) {
  const nums = (values || [])
    .map((value) => Number(value || 0))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);

  if (nums.length === 0) return 0;

  const mid = Math.floor(nums.length / 2);

  if (nums.length % 2) return nums[mid];

  return Math.round((nums[mid - 1] + nums[mid]) / 2);
}

function joinHumanList(items) {
  const safe = (items || []).filter(Boolean);

  if (safe.length === 0) return "";
  if (safe.length === 1) return safe[0];
  if (safe.length === 2) return `${safe[0]} and ${safe[1]}`;

  return `${safe.slice(0, -1).join(", ")}, and ${safe[safe.length - 1]}`;
}

function formatDomainName(domain) {
  return String(domain || "")
    .replace(/^www\./, "")
    .split(".")[0]
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function stableId(input) {
  let hash = 0;
  const value = String(input || "");

  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }

  return `finding_${Math.abs(hash)}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function withTimeout(promise, ms, label = "Operation") {
  let timeoutId;

  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        new Error(`${label} timed out after ${Math.round(ms / 1000)} seconds.`)
      );
    }, ms);
  });

  return Promise.race([promise, timeoutPromise]).finally(() => {
    clearTimeout(timeoutId);
  });
}