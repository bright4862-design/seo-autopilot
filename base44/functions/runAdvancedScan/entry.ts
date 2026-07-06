import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/3.7; +https://seoautopilot.app/bot)";

const MAX_HTML_BYTES = 800000;
const CRAWL_TIME_BUDGET_MS = 95000;
const LARGE_HTML_BYTES = 500000;
const HEAVY_SCRIPT_TAG_COUNT = 50;
const LOW_TEXT_TO_HTML_RATIO = 3;
const MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE = 2;

const BROWSERLESS_TOKEN = Deno.env.get("BROWSERLESS_TOKEN") || "";
const BROWSERLESS_CONTENT_ENDPOINT =
  Deno.env.get("BROWSERLESS_CONTENT_ENDPOINT") ||
  "https://production-sfo.browserless.io/content";

const BROWSER_RENDER_TIMEOUT_MS = Number(
  Deno.env.get("BROWSER_RENDER_TIMEOUT_MS") || 30000
);

const BROWSER_RENDER_MODE = String(
  Deno.env.get("BROWSER_RENDER_MODE") || "blocked_only"
).toLowerCase();

const MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN = Math.max(
  0,
  Number(Deno.env.get("MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN") || 3)
);

const LANGUAGE_PATHS = ["en", "fr", "es", "de", "it", "pt", "nl"];

const SCAN_MODES = {
  basic: {
    maxPages: 25,
    concurrency: 5,
    timeoutMs: 10000,
    useSitemap: false,
    maxCompetitorSnapshots: 0,
  },
  quick: {
    maxPages: 75,
    concurrency: 8,
    timeoutMs: 12000,
    useSitemap: true,
    maxCompetitorSnapshots: 3,
  },
  deep: {
    maxPages: 200,
    concurrency: 10,
    timeoutMs: 15000,
    useSitemap: true,
    maxCompetitorSnapshots: 5,
  },
  advanced: {
    maxPages: 350,
    concurrency: 12,
    timeoutMs: 18000,
    useSitemap: true,
    maxCompetitorSnapshots: 7,
  },
};

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        {
          success: false,
          error: "Unauthorized",
        },
        { status: 401 }
      );
    }

    const body = await req.json().catch(() => ({}));

    const websiteUrl = String(
      body.website_url || body.url || body.normalized_url || ""
    ).trim();

    if (!websiteUrl) {
      return Response.json(
        {
          success: false,
          error: "website_url is required.",
        },
        { status: 400 }
      );
    }

    const scanMode = normalizeScanMode(body.scan_mode);
    const config = SCAN_MODES[scanMode] || SCAN_MODES.quick;

    const competitorUrls = normalizeUrlList(body.competitor_urls || []);

    const forceInternalCrawl =
      body.force_internal_crawl === true ||
      body.respect_robots_txt === false ||
      body.allow_robots_override === true;

    const normalizedUrl = normalizeStartUrl(websiteUrl);
    const domain = getDomain(normalizedUrl);

    const crawlResult = await crawlWebsite({
      websiteUrl: normalizedUrl,
      domain,
      scanMode,
      config,
      forceInternalCrawl,
    });

    const competitorResult = await analyzeCompetitors({
      competitorUrls,
      config,
      userPages: crawlResult.crawled_pages,
    });

    const technicalAuditSummary = buildTechnicalAuditSummary(
      crawlResult.crawled_pages
    );

    const rawFixes = buildFindings({
      pages: crawlResult.crawled_pages,
      technicalAuditSummary,
      competitorComparison: competitorResult.competitor_comparison,
      competitorSnapshots: competitorResult.competitor_page_snapshots,
    });

    const healthScore = calculateHealthScore({
      fixes: rawFixes,
      pages: crawlResult.crawled_pages,
    });

    const scanSummary = buildScanSummary({
      pages: crawlResult.crawled_pages,
      fixes: rawFixes,
      technicalAuditSummary,
      competitorSnapshots: competitorResult.competitor_page_snapshots,
      crawlWarnings: crawlResult.crawl_warnings,
      healthScore,
    });

    return Response.json({
      success: true,

      website_url: websiteUrl,
      normalized_url: normalizedUrl,
      domain,
      scan_mode: scanMode,

      pages_found: crawlResult.pages_found,
      pages_crawled: crawlResult.pages_crawled,
      queued_remaining: crawlResult.queued_remaining,

      crawl_scope: {
        locked_to_start_language: Boolean(crawlResult.start_path_prefix),
        start_path_prefix: crawlResult.start_path_prefix || "",
        explanation: crawlResult.start_path_prefix
          ? `The crawl was locked to ${crawlResult.start_path_prefix} because the starting URL used that language path.`
          : "The crawl was not locked to a language path because the starting URL did not use one.",
      },

      crawled_pages: crawlResult.crawled_pages,
      pages: crawlResult.crawled_pages,
      scanned_pages: crawlResult.crawled_pages,
      crawl_pages: crawlResult.crawled_pages,

      raw_fixes: rawFixes,
      grouped_findings: rawFixes,
      raw_findings: rawFixes,
      fixes: rawFixes,
      findings: rawFixes,
      recommendations: rawFixes,
      issues: rawFixes,

      health_score: healthScore,
      scan_summary: scanSummary,
      site_summary: scanSummary,

      crawl_warnings: crawlResult.crawl_warnings,
      client_rendering: buildClientRenderingSummary(crawlResult.crawled_pages),

      competitor_urls: competitorUrls,
      competitor_results: competitorResult.competitor_results,
      competitor_page_snapshots: competitorResult.competitor_page_snapshots,
      competitor_comparison: competitorResult.competitor_comparison,

      technical_audit_summary: technicalAuditSummary,
      screaming_frog_lite_enabled: true,
      audit_profile: "screaming_frog_lite",
      robots_override_enabled: forceInternalCrawl,

      browser_rendering: {
        enabled: Boolean(BROWSERLESS_TOKEN),
        provider: BROWSERLESS_TOKEN ? "browserless" : "",
        mode: BROWSER_RENDER_MODE,
        max_attempts_per_scan: MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN,
        crawl_attempts_used: crawlResult.browser_render_attempts_used || 0,
        competitor_attempts_used:
          competitorResult.browser_render_attempts_used || 0,
        crawl_attempts_max: crawlResult.browser_render_attempts_max || 0,
        competitor_attempts_max:
          competitorResult.browser_render_attempts_max || 0,
        usage_policy:
          "Browser rendering is only used for blocked start pages and blocked manual competitor URLs.",
      },
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "runAdvancedScan failed",
        stack: error?.stack || "",
      },
      { status: 500 }
    );
  }
});

/* -------------------------------------------------------------------------- */
/* Crawl                                                                       */
/* -------------------------------------------------------------------------- */

async function crawlWebsite({
  websiteUrl,
  domain,
  scanMode,
  config,
  forceInternalCrawl,
}) {
  const startedAt = Date.now();
  const crawlWarnings = [];
  const crawledPages = [];
  const queue = [];
  const queued = new Set();
  const crawled = new Set();
  const finalPageKeys = new Set();

  const browserRenderBudget = {
    used: 0,
    max: MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN,
  };

  const startPathPrefix = getStartPathPrefix(websiteUrl);

  const robots = await fetchRobotsRules(websiteUrl, config.timeoutMs);

  function addToQueue(candidateUrl, source = "internal") {
    const normalized = normalizeCrawlUrl(candidateUrl, websiteUrl);

    if (!normalized) return false;
    if (!isSameRegistrableSite(normalized, websiteUrl)) return false;
    if (!matchesStartPathPrefix(normalized, startPathPrefix)) return false;
    if (isUtilityUrl(normalized)) return false;

    const key = canonicalQueueKey(normalized);

    if (queued.has(key) || crawled.has(key)) return false;

    const robotsAllowed = robotsAllows(robots, normalized);

    if (!robotsAllowed) {
      if (source === "start") {
        pushUniqueWarning(
          crawlWarnings,
          "The start URL appears restricted by robots.txt, but the scanner checked it because it was entered manually."
        );
      } else if (forceInternalCrawl) {
        pushUniqueWarning(
          crawlWarnings,
          "Advanced crawl mode is enabled. Internal URLs from the manually entered website were crawled even though robots.txt restricts ordinary crawler access."
        );
      } else {
        return false;
      }
    }

    queued.add(key);

    queue.push({
      url: normalized,
      key,
      source,
      priority: source === "start" ? 999 : scoreUrlPriority(normalized),
      depth: urlDepth(normalized),
    });

    sortQueue(queue);

    return true;
  }

  addToQueue(websiteUrl, "start");

  if (config.useSitemap) {
    const sitemapUrls = await discoverSitemapUrls({
      websiteUrl,
      robots,
      timeoutMs: config.timeoutMs,
      maxUrls: config.maxPages * 3,
      startPathPrefix,
    });

    for (const url of sitemapUrls.slice(0, config.maxPages * 3)) {
      addToQueue(url, "sitemap");
    }
  }

  while (
    queue.length > 0 &&
    crawledPages.length < config.maxPages &&
    Date.now() - startedAt < CRAWL_TIME_BUDGET_MS
  ) {
    const remainingSlots = Math.max(0, config.maxPages - crawledPages.length);
    const batchSize = Math.min(config.concurrency, remainingSlots);
    const batch = queue.splice(0, batchSize);

    const pages = await Promise.all(
      batch.map(async (item) => {
        crawled.add(item.key || canonicalQueueKey(item.url));

        return await fetchAndExtractPage({
          url: item.url,
          domain,
          source: item.source,
          timeoutMs: config.timeoutMs,

          // Save Browserless units:
          // only the manually entered start page can use browser rendering.
          allowBrowserRender: item.source === "start",
          browserRenderBudget,
        });
      })
    );

    for (const page of pages) {
      if (crawledPages.length >= config.maxPages) break;

      const pageKey = canonicalQueueKey(page.url || page.original_url);

      if (finalPageKeys.has(pageKey)) {
        continue;
      }

      finalPageKeys.add(pageKey);
      crawledPages.push(page);

      if (page.is_scanner_blocked) {
        pushUniqueWarning(
          crawlWarnings,
          "This website showed a protection, rate-limit, or browser-check page, so the scan could not review the real content for at least one page."
        );

        if (!BROWSERLESS_TOKEN) {
          pushUniqueWarning(
            crawlWarnings,
            "Browser rendering is not configured. Add BROWSERLESS_TOKEN in Base44 secrets to improve scans on protected websites."
          );
        } else if (page.browser_render_attempted && !page.browser_rendered) {
          pushUniqueWarning(
            crawlWarnings,
            "Browser rendering was attempted, but the website still appeared to block the scan."
          );
        } else if (page.browser_render_skipped) {
          pushUniqueWarning(crawlWarnings, page.browser_render_skip_reason);
        }
      }

      if (
        page.status_code >= 200 &&
        page.status_code < 300 &&
        !page.fetch_error &&
        !page.is_scanner_blocked
      ) {
        const sortedLinks = stableSortUrls(page.internal_links || []);

        for (const link of sortedLinks) {
          if (crawledPages.length + queue.length >= config.maxPages * 2) break;
          addToQueue(link, "internal");
        }
      }
    }
  }

  if (crawledPages.length === 0) {
    pushUniqueWarning(
      crawlWarnings,
      "The scanner could not read the start page. The site may be blocking server-side crawlers or returning non-HTML content."
    );
  }

  if (Date.now() - startedAt >= CRAWL_TIME_BUDGET_MS) {
    pushUniqueWarning(
      crawlWarnings,
      "The scan reached its time limit, so some pages may not have been checked."
    );
  }

  if (startPathPrefix) {
    pushUniqueWarning(
      crawlWarnings,
      `The scan was locked to ${startPathPrefix} pages so other language versions were ignored.`
    );
  }

  return {
    crawled_pages: crawledPages,
    pages_found: queued.size,
    pages_crawled: crawledPages.length,
    queued_remaining: queue.length,
    crawl_warnings: crawlWarnings,
    start_path_prefix: startPathPrefix,
    browser_render_attempts_used: browserRenderBudget.used,
    browser_render_attempts_max: browserRenderBudget.max,
  };
}

async function fetchAndExtractPage({
  url,
  domain,
  source,
  timeoutMs,
  allowBrowserRender = false,
  browserRenderBudget = null,
}) {
  let firstPage = null;

  try {
    const response = await fetchWithTimeout(
      url,
      {
        method: "GET",
        redirect: "follow",
        headers: {
          "User-Agent": USER_AGENT,
          Accept:
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
          "Cache-Control": "no-cache",
        },
      },
      timeoutMs
    );

    const finalUrl = response.url || url;
    const contentType = response.headers.get("content-type") || "";
    const html = await readLimitedText(response, MAX_HTML_BYTES);

    firstPage = extractPageData({
      url: finalUrl,
      originalUrl: url,
      status: response.status,
      contentType,
      html,
      domain,
      source,
      fetchError: "",
      browserRendered: false,
      browserRenderAttempted: false,
    });

    if (shouldRetryWithBrowser(firstPage)) {
      if (
        reserveBrowserRenderAttempt({
          allowBrowserRender,
          browserRenderBudget,
        })
      ) {
        const rendered = await tryBrowserRenderedPage({
          url: finalUrl,
          originalUrl: url,
          domain,
          source,
        });

        if (rendered && isRenderedPageBetter(rendered, firstPage)) {
          return rendered;
        }

        return {
          ...firstPage,
          browser_render_attempted: true,
          browser_rendered: false,
        };
      }

      return {
        ...firstPage,
        browser_render_attempted: false,
        browser_rendered: false,
        browser_render_skipped: true,
        browser_render_skip_reason: getBrowserRenderSkipReason({
          allowBrowserRender,
          browserRenderBudget,
        }),
      };
    }

    return firstPage;
  } catch (error) {
    firstPage = {
      url,
      original_url: url,
      source,
      status_code: 0,
      fetch_error: error?.message || "Fetch failed.",
      title: "",
      meta_description: "",
      h1: "",
      h1_count: 0,
      h2s: [],
      h3s: [],
      word_count: 0,
      internal_links: [],
      external_links: [],
      is_important_page: isImportantPage(url),
      is_utility_page: isUtilityUrl(url),
      likely_client_rendered: false,
      is_scanner_blocked: false,
      scanner_block_reason: "",
      indexability: "unknown",
      indexability_reasons: ["The page could not be fetched."],
      response_size_bytes: 0,
      html_truncated: false,
      browser_render_attempted: false,
      browser_rendered: false,
    };

    if (
      reserveBrowserRenderAttempt({
        allowBrowserRender,
        browserRenderBudget,
      })
    ) {
      const rendered = await tryBrowserRenderedPage({
        url,
        originalUrl: url,
        domain,
        source,
      });

      if (rendered && isRenderedPageBetter(rendered, firstPage)) {
        return rendered;
      }

      return {
        ...firstPage,
        browser_render_attempted: true,
        browser_rendered: false,
      };
    }

    return {
      ...firstPage,
      browser_render_skipped: true,
      browser_render_skip_reason: getBrowserRenderSkipReason({
        allowBrowserRender,
        browserRenderBudget,
      }),
    };
  }
}

function reserveBrowserRenderAttempt({
  allowBrowserRender,
  browserRenderBudget,
}) {
  if (!BROWSERLESS_TOKEN) return false;
  if (BROWSER_RENDER_MODE === "off") return false;
  if (!allowBrowserRender) return false;

  if (!browserRenderBudget) return true;

  if (browserRenderBudget.used >= browserRenderBudget.max) {
    return false;
  }

  browserRenderBudget.used += 1;

  return true;
}

function getBrowserRenderSkipReason({
  allowBrowserRender,
  browserRenderBudget,
}) {
  if (!BROWSERLESS_TOKEN) {
    return "Browser rendering is not configured.";
  }

  if (BROWSER_RENDER_MODE === "off") {
    return "Browser rendering is turned off by BROWSER_RENDER_MODE.";
  }

  if (!allowBrowserRender) {
    return "Browser rendering is reserved for the start page and manual competitor URLs.";
  }

  if (
    browserRenderBudget &&
    browserRenderBudget.used >= browserRenderBudget.max
  ) {
    return "Browser rendering monthly-unit protection stopped this request because the scan reached its render-attempt limit.";
  }

  return "Browser rendering was skipped.";
}

async function tryBrowserRenderedPage({ url, originalUrl, domain, source }) {
  if (!BROWSERLESS_TOKEN) return null;

  try {
    const rendered = await fetchRenderedHtmlWithBrowser(url);

    if (!rendered?.html) return null;

    return extractPageData({
      url: rendered.finalUrl || url,
      originalUrl,
      status: rendered.status || 200,
      contentType: "text/html; rendered=browserless",
      html: rendered.html,
      domain,
      source,
      fetchError: "",
      browserRendered: true,
      browserRenderAttempted: true,
    });
  } catch {
    return null;
  }
}

async function fetchRenderedHtmlWithBrowser(url) {
  const endpoint = appendTokenToBrowserlessUrl(BROWSERLESS_CONTENT_ENDPOINT);

  const response = await fetchWithTimeout(
    endpoint,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
      },
      body: JSON.stringify({
        url,
        gotoOptions: {
          waitUntil: "networkidle2",
          timeout: BROWSER_RENDER_TIMEOUT_MS,
        },
        waitForTimeout: 2500,
      }),
    },
    BROWSER_RENDER_TIMEOUT_MS + 5000
  );

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `Browser rendering failed with status ${response.status}: ${clampText(
        text,
        300
      )}`
    );
  }

  return {
    html: text,
    finalUrl: url,
    status: 200,
  };
}

function appendTokenToBrowserlessUrl(endpoint) {
  const url = new URL(endpoint);

  if (!url.searchParams.get("token")) {
    url.searchParams.set("token", BROWSERLESS_TOKEN);
  }

  return url.toString();
}

function shouldRetryWithBrowser(page) {
  if (!page) return false;

  const status = Number(page.status_code || 0);

  if (page.is_scanner_blocked) return true;

  if (status === 403 || status === 429 || status === 503 || status === 0) {
    return true;
  }

  if (BROWSER_RENDER_MODE === "js_fallback") {
    if (
      status >= 200 &&
      status < 300 &&
      Number(page.word_count || 0) < 30 &&
      Number(page.script_tag_count || 0) >= 10
    ) {
      return true;
    }
  }

  return false;
}

function isRenderedPageBetter(rendered, firstPage) {
  if (!rendered) return false;

  if (rendered.is_scanner_blocked && !firstPage?.is_scanner_blocked) {
    return false;
  }

  if (!rendered.is_scanner_blocked && firstPage?.is_scanner_blocked) {
    return true;
  }

  const renderedWords = Number(rendered.word_count || 0);
  const firstWords = Number(firstPage?.word_count || 0);

  if (renderedWords >= Math.max(80, firstWords + 50)) return true;

  if (
    rendered.status_code >= 200 &&
    rendered.status_code < 300 &&
    firstPage?.status_code >= 400
  ) {
    return true;
  }

  return false;
}

/* -------------------------------------------------------------------------- */
/* Extraction                                                                  */
/* -------------------------------------------------------------------------- */

function extractPageData({
  url,
  originalUrl,
  status,
  contentType,
  html,
  domain,
  source,
  fetchError,
  browserRendered = false,
  browserRenderAttempted = false,
}) {
  const rawHtml = String(html || "");
  const lowerHtml = rawHtml.toLowerCase();
  const visibleText = extractVisibleText(rawHtml);
  const words = tokenizeWords(visibleText);

  const titleTags = extractTitleTags(rawHtml);
  const title = titleTags[0] || "";
  const metaDescriptions = extractMetaNameContents(rawHtml, "description");
  const metaDescription = metaDescriptions[0] || "";

  const h1s = extractHeadingTags(rawHtml, "h1");
  const h2s = extractHeadingTags(rawHtml, "h2");
  const h3s = extractHeadingTags(rawHtml, "h3");

  const links = extractLinks(rawHtml, url);
  const internalLinks = links.filter((link) => isSameRegistrableSite(link, url));
  const externalLinks = links.filter(
    (link) => !isSameRegistrableSite(link, url)
  );

  const images = extractImages(rawHtml);
  const schemaTypes = extractSchemaTypes(rawHtml);
  const canonical = extractCanonical(rawHtml, url);
  const robotsMeta = extractRobotsMeta(rawHtml);
  const indexability = buildIndexability({
    status,
    robotsMeta,
    canonical,
    url,
  });

  const responseSizeBytes = approximateBytes(rawHtml);
  const scriptTagCount = countMatches(lowerHtml, /<script\b/gi);
  const textToHtmlRatio =
    responseSizeBytes > 0
      ? Number(((visibleText.length / responseSizeBytes) * 100).toFixed(2))
      : 0;

  const viewportPresent = /<meta[^>]+name=["']viewport["'][^>]*>/i.test(
    rawHtml
  );

  const charsetPresent =
    /<meta[^>]+charset=/i.test(rawHtml) ||
    /<meta[^>]+http-equiv=["']content-type["']/i.test(rawHtml);

  const socialMeta = detectSocialMeta(rawHtml);
  const hreflangs = extractHreflangs(rawHtml);

  const important = isImportantPage(url);
  const utility = isUtilityUrl(url);

  const antiBot = detectAntiBotBlock({
    status,
    title,
    visibleText,
    html: rawHtml,
  });

  const likelyClientRendered =
    status >= 200 &&
    status < 300 &&
    words.length < 80 &&
    scriptTagCount >= 20 &&
    internalLinks.length > 0 &&
    !antiBot.blocked;

  const trustSignals = detectTrustSignals(visibleText);
  const ctaPhrases = detectCtaPhrases(visibleText);
  const faqQuestions = detectFaqQuestions(rawHtml, visibleText);

  return {
    url,
    original_url: originalUrl,
    source,
    status_code: status,
    fetch_error: fetchError || "",
    content_type: contentType || "",

    title,
    title_length: title.length,
    title_count: titleTags.length,

    meta_description: metaDescription,
    meta_description_length: metaDescription.length,
    meta_description_count: metaDescriptions.length,

    h1: h1s[0] || "",
    h1_count: h1s.length,
    h2s,
    h2_count: h2s.length,
    h3s,
    h3_count: h3s.length,

    word_count: words.length,
    visible_text_sample: clampText(visibleText, 1000),

    internal_links: unique(internalLinks).slice(0, 500),
    internal_link_count: unique(internalLinks).length,
    external_links: unique(externalLinks).slice(0, 200),
    external_link_count: unique(externalLinks).length,

    image_count: images.length,
    images_missing_alt_count: images.filter((img) => !img.alt).length,

    has_schema: schemaTypes.length > 0,
    schema_types: schemaTypes,

    has_faq: faqQuestions.length > 0,
    faq_questions: faqQuestions,

    trust_signals: trustSignals,
    cta_phrases: ctaPhrases,

    canonical_url: canonical.url,
    canonical_status: canonical.status,
    canonical_issue: canonical.issue,

    robots_meta: robotsMeta,
    indexability: antiBot.blocked ? "unknown" : indexability.status,
    indexability_reasons: antiBot.blocked
      ? ["The scanner received a protection or rate-limit page."]
      : indexability.reasons,

    viewport_present: viewportPresent,
    charset_present: charsetPresent,

    open_graph_present: socialMeta.open_graph_present,
    twitter_card_present: socialMeta.twitter_card_present,

    hreflangs,

    response_size_bytes: responseSizeBytes,
    html_truncated: responseSizeBytes >= MAX_HTML_BYTES,
    script_tag_count: scriptTagCount,
    text_to_html_ratio: textToHtmlRatio,

    is_important_page: antiBot.blocked ? false : important,
    is_utility_page: utility,
    likely_client_rendered: likelyClientRendered,

    is_scanner_blocked: antiBot.blocked,
    scanner_block_reason: antiBot.reason,

    browser_render_attempted: browserRenderAttempted,
    browser_rendered: browserRendered,
  };
}

function detectAntiBotBlock({ status, title, visibleText, html }) {
  const lowerTitle = String(title || "").toLowerCase();
  const lowerText = String(visibleText || "").toLowerCase();
  const lowerHtml = String(html || "").toLowerCase();

  const statusLooksBlocked =
    Number(status) === 403 || Number(status) === 429 || Number(status) === 503;

  const phrases = [
    "just a moment",
    "checking your browser",
    "check your browser",
    "enable javascript",
    "please enable javascript",
    "cloudflare",
    "attention required",
    "access denied",
    "rate limit",
    "too many requests",
    "request blocked",
    "bot detection",
    "security check",
    "verify you are human",
    "are you human",
    "captcha",
    "datadome",
    "akamai",
    "perimeterx",
    "imperva",
  ];

  const matchedPhrase = phrases.find(
    (phrase) =>
      lowerTitle.includes(phrase) ||
      lowerText.includes(phrase) ||
      lowerHtml.includes(phrase)
  );

  if (statusLooksBlocked && matchedPhrase) {
    return {
      blocked: true,
      reason: `HTTP ${status} with protection phrase "${matchedPhrase}".`,
    };
  }

  if (statusLooksBlocked && lowerText.length < 800) {
    return {
      blocked: true,
      reason: `HTTP ${status} with very little readable page content.`,
    };
  }

  if (matchedPhrase && tokenizeWords(visibleText).length < 80) {
    return {
      blocked: true,
      reason: `Protection phrase "${matchedPhrase}" appeared instead of normal page content.`,
    };
  }

  return {
    blocked: false,
    reason: "",
  };
}

/* -------------------------------------------------------------------------- */
/* Competitors                                                                 */
/* -------------------------------------------------------------------------- */

async function analyzeCompetitors({ competitorUrls, config, userPages }) {
  const urls = normalizeUrlList(competitorUrls).slice(
    0,
    config.maxCompetitorSnapshots
  );

  const competitorResults = urls.map((url) => ({
    name: friendlyNameFromDomain(getDomain(url)),
    website_url: normalizeStartUrl(url),
    url: normalizeStartUrl(url),
    domain: getDomain(url),
    source: "manual",
    keyword: "",
    title: "",
    snippet: "",
    position: 99,
    query: "",
  }));

  const competitorBrowserRenderBudget = {
    used: 0,
    max: Math.min(MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN, urls.length),
  };

  const snapshots = await Promise.all(
    competitorResults.map(async (competitor) => {
      const page = await fetchAndExtractPage({
        url: competitor.url,
        domain: competitor.domain,
        source: "competitor",
        timeoutMs: config.timeoutMs,

        // Manual competitor URLs may use Browserless, but only if blocked.
        allowBrowserRender: true,
        browserRenderBudget: competitorBrowserRenderBudget,
      });

      return {
        competitor_name: competitor.name,
        competitor_domain: competitor.domain,
        competitor_url: competitor.url,
        status_code: page.status_code,
        fetch_error: page.fetch_error || "",
        title: page.title || "",
        h1: page.h1 || "",
        h2s: page.h2s || [],
        word_count: page.word_count || 0,
        has_faq: Boolean(page.has_faq),
        faq_questions: page.faq_questions || [],
        has_schema: Boolean(page.has_schema),
        schema_types: page.schema_types || [],
        trust_signals: page.trust_signals || [],
        cta_phrases: page.cta_phrases || [],
        visible_text_sample: page.visible_text_sample || "",
        is_scanner_blocked: Boolean(page.is_scanner_blocked),
        scanner_block_reason: page.scanner_block_reason || "",
        browser_rendered: Boolean(page.browser_rendered),
        browser_render_attempted: Boolean(page.browser_render_attempted),
        browser_render_skipped: Boolean(page.browser_render_skipped),
        browser_render_skip_reason: page.browser_render_skip_reason || "",
      };
    })
  );

  const comparison = buildCompetitorComparison({
    userPages,
    competitorSnapshots: snapshots,
  });

  return {
    competitor_results: competitorResults,
    competitor_page_snapshots: snapshots,
    competitor_comparison: comparison,
    browser_render_attempts_used: competitorBrowserRenderBudget.used,
    browser_render_attempts_max: competitorBrowserRenderBudget.max,
  };
}

function buildCompetitorComparison({ userPages, competitorSnapshots }) {
  const userImportant = (userPages || []).filter(
    (page) =>
      page.is_important_page &&
      !page.is_utility_page &&
      !page.is_scanner_blocked
  );

  const readableCompetitors = (competitorSnapshots || []).filter(
    (item) =>
      item.status_code >= 200 &&
      item.status_code < 300 &&
      item.word_count > 50 &&
      !item.is_scanner_blocked
  );

  if (userImportant.length === 0 || readableCompetitors.length === 0) {
    return null;
  }

  const userWords = userImportant.map((page) => page.word_count || 0);
  const competitorWords = readableCompetitors.map(
    (page) => page.word_count || 0
  );

  const userText = userImportant
    .map((page) => page.visible_text_sample || "")
    .join(" ")
    .toLowerCase();

  const topicGaps = extractCompetitorTopicGaps({
    userText,
    competitors: readableCompetitors,
  });

  const competitorsWithFaq = readableCompetitors.filter(
    (item) => item.has_faq || item.faq_questions?.length > 0
  ).length;

  const yourPagesWithFaq = userImportant.filter((page) => page.has_faq).length;

  const schemaTypes = unique(
    readableCompetitors.flatMap((item) => item.schema_types || [])
  );

  const yourSchemaTypes = unique(
    userImportant.flatMap((page) => page.schema_types || [])
  );

  const schemaGaps = schemaTypes.filter(
    (type) => !yourSchemaTypes.includes(type)
  );

  return {
    competitors_compared: readableCompetitors.map((item) => ({
      name: item.competitor_name,
      domain: item.competitor_domain,
      url: item.competitor_url,
      word_count: item.word_count,
    })),

    content_depth: {
      your_median_words: median(userWords),
      competitor_median_words: median(competitorWords),
    },

    faq_coverage: {
      your_pages_with_faq: yourPagesWithFaq,
      competitors_with_faq: competitorsWithFaq,
      competitor_faq_examples: readableCompetitors
        .flatMap((item) => item.faq_questions || [])
        .slice(0, 8),
    },

    topic_gaps: topicGaps,
    schema_gaps: schemaGaps.slice(0, 8),
    trust_signal_gaps: [],
  };
}

function extractCompetitorTopicGaps({ userText, competitors }) {
  const phrases = [];

  for (const competitor of competitors) {
    for (const heading of competitor.h2s || []) {
      const phrase = cleanString(heading);

      if (
        phrase.length >= 4 &&
        phrase.length <= 80 &&
        !userText.includes(phrase.toLowerCase())
      ) {
        phrases.push({
          topic: phrase,
          competitor: competitor.competitor_name,
        });
      }
    }
  }

  const grouped = new Map();

  for (const item of phrases) {
    const key = item.topic.toLowerCase();

    if (!grouped.has(key)) {
      grouped.set(key, {
        topic: item.topic,
        competitors: [],
      });
    }

    grouped.get(key).competitors.push(item.competitor);
  }

  return Array.from(grouped.values())
    .sort((a, b) => b.competitors.length - a.competitors.length)
    .slice(0, 8);
}

/* -------------------------------------------------------------------------- */
/* Findings                                                                    */
/* -------------------------------------------------------------------------- */

function buildFindings({
  pages,
  technicalAuditSummary,
  competitorComparison,
  competitorSnapshots,
}) {
  const fixes = [];

  addScannerBlockedFindings(fixes, pages);
  addBrokenPageFindings(fixes, pages);
  addContentFindings(fixes, pages);
  addScreamingFrogLiteFindings(fixes, pages);
  addClientRenderingFindings(fixes, pages);
  addCompetitorFindings(fixes, competitorComparison, competitorSnapshots);

  return dedupeFindings(fixes).sort(compareFindings);
}

function addScannerBlockedFindings(fixes, pages) {
  const blockedPages = (pages || []).filter((page) => page.is_scanner_blocked);

  if (blockedPages.length === 0) return;

  const startPageBlocked =
    blockedPages.length === 1 ||
    blockedPages.some((page) => page.source === "start");

  fixes.push(
    makeFinding({
      id: "scanner_blocked",
      category: "scanner_blocked",
      customerCategory: "Scan limited",
      priority: "high",
      title: startPageBlocked
        ? "Website protection blocked the scan"
        : "Some pages blocked the scanner",
      explanation: startPageBlocked
        ? "The website showed a protection, browser-check, or rate-limit page instead of the real page content. This means the scan could not properly review the page."
        : "Some pages showed a protection, browser-check, or rate-limit page instead of normal page content.",
      why:
        "This does not automatically mean the website is broken for visitors. It means the scanner could not see enough real content to give a reliable SEO review for those pages.",
      affectedPages: blockedPages.map((page) => cleanPath(page.url)),
      details: {
        affected_count: blockedPages.length,
        browser_rendering_enabled: Boolean(BROWSERLESS_TOKEN),
        browser_render_mode: BROWSER_RENDER_MODE,
        examples: blockedPages.slice(0, 8).map((page) => ({
          url: page.url,
          path: cleanPath(page.url),
          readable_label: readablePageLabel(page.url),
          status_code: page.status_code,
          title: page.title,
          word_count: page.word_count,
          scanner_block_reason: page.scanner_block_reason,
          browser_render_attempted: page.browser_render_attempted,
          browser_rendered: page.browser_rendered,
          browser_render_skipped: page.browser_render_skipped,
          browser_render_skip_reason: page.browser_render_skip_reason || "",
        })),
      },
      difficulty: "developer",
      status: "needs_developer",
    })
  );
}

function addBrokenPageFindings(fixes, pages) {
  const brokenPages = pages.filter((page) => {
    const status = Number(page.status_code || 0);

    if (page.is_scanner_blocked) return false;

    return status === 0 || status >= 400 || page.fetch_error;
  });

  if (brokenPages.length === 0) return;

  const examplePages = brokenPages.slice(0, 10).map((page) => ({
    url: page.url,
    path: cleanPath(page.url),
    readable_label: readablePageLabel(page.url),
    status_code: page.status_code,
    fetch_error: page.fetch_error || "",
    title: page.title || "",
  }));

  const firstPath = cleanPath(brokenPages[0]?.url || "");
  const languageName = languageNameFromPath(firstPath);
  const languageText = languageName ? `${languageName} ` : "";

  fixes.push(
    makeFinding({
      id: "broken_pages",
      category: "broken_page",
      customerCategory: "Broken pages",
      priority: "high",
      title:
        brokenPages.length === 1
          ? `One ${languageText}page may not be loading correctly`
          : `Some ${languageText}pages may not be loading correctly`,
      explanation:
        brokenPages.length === 1
          ? `The scanner found one ${languageText.toLowerCase()}page that returned an error during the scan. This may be an old link, an unavailable page, or a page that blocks server-side checks.`
          : `The scanner found ${brokenPages.length} ${languageText.toLowerCase()}pages that returned errors during the scan. These may be old links, unavailable pages, or pages that block server-side checks.`,
      why:
        "If these URLs are linked from your site, visitors may land on pages that do not work. If they are old or unimportant URLs, they can usually be cleaned up or ignored after review.",
      affectedPages: brokenPages.map((page) => cleanPath(page.url)),
      details: {
        affected_count: brokenPages.length,
        examples: examplePages,
      },
      difficulty: "developer",
      status: "needs_developer",
    })
  );
}

function addContentFindings(fixes, pages) {
  const importantPages = pages.filter(
    (page) =>
      page.is_important_page &&
      !page.is_utility_page &&
      !page.is_scanner_blocked &&
      page.status_code >= 200 &&
      page.status_code < 300
  );

  const missingH1 = importantPages.filter(
    (page) => !page.h1 || page.h1_count === 0
  );

  if (missingH1.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_h1",
        category: "page_heading",
        customerCategory: "Page content",
        priority: "medium",
        title: "Add a clear main heading",
        explanation: "Some important pages may not have a clear main heading.",
        why:
          "A clear main heading helps visitors and search engines understand what the page is about.",
        affectedPages: missingH1.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  const thinPages = importantPages.filter(
    (page) => page.word_count > 0 && page.word_count < 250
  );

  if (thinPages.length > 0) {
    fixes.push(
      makeFinding({
        id: "thin_content",
        category: "thin_content",
        customerCategory: "Page content",
        priority: "medium",
        title: "Add more helpful content to this page",
        explanation:
          "Some important pages may not have enough useful content for visitors.",
        why:
          "Helpful page content can improve trust, answer customer questions, and make the page more useful.",
        affectedPages: thinPages.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  const noTrust = importantPages.filter(
    (page) => (page.trust_signals || []).length === 0
  );

  if (noTrust.length > 0) {
    fixes.push(
      makeFinding({
        id: "trust_signal_gap",
        category: "trust_signal_gap",
        customerCategory: "Trust signals",
        priority: "medium",
        title: "Add more trust signals to important pages",
        explanation:
          "Some important pages may not show enough proof that visitors can trust the business.",
        why:
          "Reviews, credentials, locations, guarantees, and real proof points can help visitors feel more confident.",
        affectedPages: noTrust.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  const noFaq = importantPages.filter((page) => !page.has_faq);

  if (noFaq.length > 0) {
    fixes.push(
      makeFinding({
        id: "faq_gap",
        category: "faq_gap",
        customerCategory: "Page content",
        priority: "low",
        title: "Add answers to common customer questions",
        explanation:
          "Some important pages do not appear to answer common customer questions.",
        why:
          "FAQs can help visitors make decisions and can make pages more complete.",
        affectedPages: noFaq.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  const lowInternalLinks = importantPages.filter(
    (page) =>
      Number(page.internal_link_count || 0) <
      MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE
  );

  if (lowInternalLinks.length > 0) {
    fixes.push(
      makeFinding({
        id: "low_internal_links",
        category: "internal_link",
        customerCategory: "Technical SEO",
        priority: "low",
        title: "Add more helpful internal links",
        explanation:
          "Some important pages have very few links to other useful pages on the same website.",
        why:
          "Internal links help visitors continue their journey and help search engines discover related pages.",
        affectedPages: lowInternalLinks.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }
}

function addScreamingFrogLiteFindings(fixes, pages) {
  const successfulPages = pages.filter(
    (page) =>
      page.status_code >= 200 &&
      page.status_code < 300 &&
      !page.is_scanner_blocked
  );

  const missingTitles = successfulPages.filter((page) => !page.title);
  const duplicateTitles = groupDuplicateValues(successfulPages, "title");
  const missingDescriptions = successfulPages.filter(
    (page) => !page.meta_description
  );
  const multipleDescriptions = successfulPages.filter(
    (page) => Number(page.meta_description_count || 0) > 1
  );
  const multipleH1s = successfulPages.filter(
    (page) => Number(page.h1_count || 0) > 1
  );
  const missingCanonicals = successfulPages.filter(
    (page) => !page.canonical_url
  );
  const canonicalIssues = successfulPages.filter((page) => page.canonical_issue);
  const nonIndexable = successfulPages.filter(
    (page) => page.indexability === "non_indexable"
  );
  const missingViewport = successfulPages.filter(
    (page) => !page.viewport_present
  );
  const missingSocial = successfulPages.filter(
    (page) => !page.open_graph_present
  );
  const imageAlt = successfulPages.filter(
    (page) => Number(page.images_missing_alt_count || 0) > 0
  );
  const heavyPages = successfulPages.filter(
    (page) =>
      Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
      Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT ||
      Number(page.text_to_html_ratio || 0) < LOW_TEXT_TO_HTML_RATIO
  );

  if (missingTitles.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_titles",
        category: "meta_title",
        customerCategory: "Search appearance",
        priority: "high",
        title: "Add missing search titles",
        explanation:
          "Some pages are missing a clear page title for search results.",
        why: "Search titles help people and search engines understand the page.",
        affectedPages: missingTitles.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (duplicateTitles.length > 0) {
    fixes.push(
      makeFinding({
        id: "duplicate_search_titles",
        category: "duplicate_search_titles",
        customerCategory: "Search appearance",
        priority: "medium",
        title: "Review duplicate search titles",
        explanation: "Some pages appear to use the same search title.",
        why:
          "Unique search titles help each page stand out for its own topic.",
        affectedPages: duplicateTitles.flatMap((group) =>
          group.pages.map((page) => cleanPath(page.url))
        ),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (missingDescriptions.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_meta_descriptions",
        category: "meta_description",
        customerCategory: "Search appearance",
        priority: "medium",
        title: "Add helpful search descriptions",
        explanation:
          "Some pages are missing a short description for search results.",
        why:
          "Descriptions can help people understand why they should click your page.",
        affectedPages: missingDescriptions.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (multipleDescriptions.length > 0) {
    fixes.push(
      makeFinding({
        id: "multiple_meta_descriptions",
        category: "duplicate_search_descriptions",
        customerCategory: "Search appearance",
        priority: "low",
        title: "Use one search description per page",
        explanation:
          "Some pages appear to have more than one search description tag.",
        why:
          "Multiple descriptions can make search snippets less predictable.",
        affectedPages: multipleDescriptions.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (multipleH1s.length > 0) {
    fixes.push(
      makeFinding({
        id: "multiple_h1s",
        category: "page_heading",
        customerCategory: "Page content",
        priority: "low",
        title: "Review pages with multiple main headings",
        explanation: "Some pages appear to have more than one main heading.",
        why: "One clear main heading can make the page easier to understand.",
        affectedPages: multipleH1s.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (missingCanonicals.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_canonicals",
        category: "canonical",
        customerCategory: "Technical SEO",
        priority: "low",
        title: "Add preferred-page settings",
        explanation: "Some pages do not show a preferred page address.",
        why:
          "Preferred-page settings help search engines know which version of a page should be treated as the main one.",
        affectedPages: missingCanonicals.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (canonicalIssues.length > 0) {
    fixes.push(
      makeFinding({
        id: "canonical_issues",
        category: "canonical",
        customerCategory: "Technical SEO",
        priority: "medium",
        title: "Review preferred-page settings",
        explanation:
          "Some pages have preferred-page settings that may need review.",
        why:
          "Incorrect preferred-page settings can confuse search engines about which page should rank.",
        affectedPages: canonicalIssues.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (nonIndexable.length > 0) {
    fixes.push(
      makeFinding({
        id: "non_indexable_pages",
        category: "indexability",
        customerCategory: "Technical SEO",
        priority: "high",
        title: "Review pages that may not be visible to search engines",
        explanation:
          "Some pages may be telling search engines not to show them in results.",
        why: "Important pages should usually be available to search engines.",
        affectedPages: nonIndexable.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (missingViewport.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_viewport",
        category: "mobile_setup",
        customerCategory: "Technical SEO",
        priority: "medium",
        title: "Review mobile setup",
        explanation: "Some pages may be missing a mobile viewport setting.",
        why:
          "Mobile setup helps pages display correctly on phones and tablets.",
        affectedPages: missingViewport.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (missingSocial.length > 0) {
    fixes.push(
      makeFinding({
        id: "missing_social_metadata",
        category: "social_metadata",
        customerCategory: "Technical SEO",
        priority: "low",
        title: "Review social sharing previews",
        explanation:
          "Some pages may not define how they appear when shared on social platforms.",
        why:
          "Good sharing previews can make links look more trustworthy and clickable.",
        affectedPages: missingSocial.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }

  if (imageAlt.length > 0) {
    fixes.push(
      makeFinding({
        id: "image_alt_text",
        category: "image_alt_text",
        customerCategory: "Website setup",
        priority: "low",
        title: "Add descriptive text to important images",
        explanation: "Some images may be missing descriptive alt text.",
        why:
          "Image descriptions help accessibility and can help search engines understand image content.",
        affectedPages: imageAlt.map((page) => cleanPath(page.url)),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (heavyPages.length > 0) {
    fixes.push(
      makeFinding({
        id: "heavy_pages",
        category: "performance_hint",
        customerCategory: "Technical SEO",
        priority: "medium",
        title: "Some pages look heavy or script-heavy",
        explanation:
          "Some pages have very large HTML, many scripts, or a low amount of visible text compared with the page code.",
        why:
          "Heavy pages can be harder for visitors and search engines to process.",
        affectedPages: heavyPages.map((page) => cleanPath(page.url)),
        difficulty: "developer",
        status: "needs_developer",
      })
    );
  }
}

function addClientRenderingFindings(fixes, pages) {
  const flagged = unique(
    (pages || [])
      .filter((page) => page.likely_client_rendered && !page.is_scanner_blocked)
      .map((page) => cleanPath(page.url))
  );

  if (flagged.length === 0) return;

  fixes.push(
    makeFinding({
      id: "client_rendered_pages",
      category: "js_rendering",
      customerCategory: "Website setup",
      priority: "medium",
      title: "Some page content may depend heavily on JavaScript",
      explanation:
        "Some pages looked light when checked from the server, which can happen when important content loads later in the browser.",
      why:
        "If important text loads only after scripts run, search engines and accessibility tools may not always see the full page clearly.",
      affectedPages: flagged,
      difficulty: "developer",
      status: "needs_developer",
      details: {
        affected_count: flagged.length,
        examples: flagged.slice(0, 8).map((path) => ({
          url: path,
          path,
          readable_label: readablePageLabel(path),
        })),
      },
    })
  );
}

function addCompetitorFindings(fixes, competitorComparison, competitorSnapshots) {
  const readableCompetitors = (competitorSnapshots || []).filter(
    (item) =>
      item.status_code >= 200 &&
      item.status_code < 300 &&
      item.word_count > 50 &&
      !item.is_scanner_blocked
  );

  const blockedCompetitors = (competitorSnapshots || []).filter(
    (item) => item.is_scanner_blocked
  );

  if (blockedCompetitors.length > 0 && readableCompetitors.length === 0) {
    fixes.push(
      makeFinding({
        id: "competitor_pages_blocked",
        category: "scanner_blocked",
        customerCategory: "Competitor opportunities",
        priority: "medium",
        title: "Competitor pages could not be fully checked",
        explanation:
          "The competitor pages showed protection or browser-check pages, so competitor insights are limited.",
        why:
          "Competitor analysis needs readable competitor content. If competitors block scans, the report can only show limited comparison.",
        affectedPages: blockedCompetitors.map((item) => item.competitor_url),
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (readableCompetitors.length > 0) {
    fixes.push(
      makeFinding({
        id: "competitor_pages_reviewed",
        category: "competitor_gap",
        customerCategory: "Competitor opportunities",
        priority: "medium",
        title: "Review competitor pages for content opportunities",
        explanation:
          "We found competitor pages from the manual URLs and reviewed what those pages include.",
        why:
          "Competitor pages can reveal useful content sections, FAQs, and proof points worth considering.",
        affectedPages: ["/"],
        difficulty: "moderate",
        status: "needs_approval",
      })
    );
  }

  if (!competitorComparison) return;

  const topicGaps = competitorComparison.topic_gaps || [];

  if (topicGaps.length > 0) {
    fixes.push(
      makeFinding({
        id: "competitor_topic_gaps",
        category: "competitor_gap",
        customerCategory: "Competitor opportunities",
        priority: "medium",
        title: "Competitor pages cover topics your pages don’t mention",
        explanation: `Competitor pages include sections such as ${topicGaps
          .slice(0, 3)
          .map((gap) => `“${gap.topic}”`)
          .join(", ")} that we could not find on your important pages.`,
        why:
          "Relevant missing topics can be opportunities to make your pages more complete.",
        affectedPages: ["/"],
        difficulty: "moderate",
        status: "needs_approval",
        details: {
          topic_gaps: topicGaps,
        },
      })
    );
  }

  const depth = competitorComparison.content_depth || {};

  if (
    depth.competitor_median_words > 0 &&
    depth.your_median_words > 0 &&
    depth.competitor_median_words >= depth.your_median_words * 1.5
  ) {
    fixes.push(
      makeFinding({
        id: "competitor_content_depth_gap",
        category: "competitor_gap",
        customerCategory: "Competitor opportunities",
        priority: "medium",
        title: "Competitor pages appear more detailed",
        explanation:
          "The competitor pages we could read appear to include more content than your important pages.",
        why:
          "More complete pages can answer more customer questions and provide stronger context.",
        affectedPages: ["/"],
        difficulty: "moderate",
        status: "needs_approval",
        details: {
          content_depth: depth,
        },
      })
    );
  }

  const faq = competitorComparison.faq_coverage || {};

  if (
    Number(faq.competitors_with_faq || 0) > 0 &&
    Number(faq.your_pages_with_faq || 0) === 0
  ) {
    fixes.push(
      makeFinding({
        id: "competitor_faq_gap",
        category: "faq_gap",
        customerCategory: "Competitor opportunities",
        priority: "low",
        title: "Competitors answer customer questions",
        explanation:
          "Some competitor pages include question-and-answer content that your important pages may not have.",
        why:
          "FAQs can help visitors make decisions and can make pages more useful.",
        affectedPages: ["/"],
        difficulty: "moderate",
        status: "needs_approval",
        details: {
          faq_coverage: faq,
        },
      })
    );
  }
}

function makeFinding({
  id,
  category,
  customerCategory,
  priority,
  title,
  explanation,
  why,
  affectedPages,
  details = {},
  difficulty = "moderate",
  status = "needs_approval",
}) {
  return {
    id,
    fix_id: id,

    type: "site_level",
    page_url: affectedPages?.[0] || "/",

    category,
    customer_category: customerCategory,

    issue_title: title,
    title,

    plain_english_explanation: explanation,
    plain_english_summary: explanation,

    why_it_matters: why,

    current_value: "",
    recommended_value: "Review this recommendation.",
    ai_recommendation: "Review this recommendation.",

    priority,
    difficulty,
    status,

    can_auto_fix: false,
    requires_approval: status === "needs_approval",
    requires_developer: status === "needs_developer",

    affected_pages: unique(affectedPages || ["/"]).slice(0, 150),
    details,

    confidence_score: 90,

    what_to_do: defaultSteps(category, difficulty),
    what_to_do_steps: defaultSteps(category, difficulty),
    fix_steps: defaultSteps(category, difficulty),

    who_can_do_this: difficulty === "developer" ? "your_web_person" : "you",
    estimated_time:
      difficulty === "developer"
        ? "a task for your web person"
        : "about 30–60 minutes",
    time_estimate:
      difficulty === "developer"
        ? "a task for your web person"
        : "about 30–60 minutes",
  };
}

function defaultSteps(category, difficulty) {
  if (category === "scanner_blocked") {
    if (BROWSERLESS_TOKEN) {
      return [
        "Ask your web person to confirm whether this page blocks automated checks.",
        "Review whether the site security settings are intentionally blocking SEO tools.",
        "Try scanning again later or whitelist the scanner if appropriate.",
      ];
    }

    return [
      "Add BROWSERLESS_TOKEN in Base44 backend secrets if you want browser-rendered scans.",
      "Ask your web person to review whether the site blocks automated SEO checks.",
      "Try scanning again later or whitelist the scanner if appropriate.",
    ];
  }

  if (difficulty === "developer") {
    return [
      "Share this finding with your web person.",
      "Ask them to review the affected page or template.",
      "Scan the page again after the update.",
    ];
  }

  if (category === "thin_content" || category === "faq_gap") {
    return [
      "Review the affected page.",
      "Add helpful details, proof points, and common questions.",
      "Make sure the page has a clear next step for visitors.",
    ];
  }

  return [
    "Review the affected page.",
    "Update the page based on the recommendation.",
    "Scan the page again after publishing.",
  ];
}

function dedupeFindings(fixes) {
  const seen = new Set();
  const output = [];

  for (const fix of fixes || []) {
    const key = fix.id || fix.fix_id || fix.issue_title;

    if (!key || seen.has(key)) continue;

    seen.add(key);
    output.push(fix);
  }

  return output;
}

function compareFindings(a, b) {
  const priorityOrder = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };

  return (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
}

/* -------------------------------------------------------------------------- */
/* Summaries                                                                   */
/* -------------------------------------------------------------------------- */

function buildTechnicalAuditSummary(pages) {
  const safePages = Array.isArray(pages) ? pages : [];
  const readable = safePages.filter((page) => !page.is_scanner_blocked);
  const successful = readable.filter(
    (page) => page.status_code >= 200 && page.status_code < 300
  );
  const important = successful.filter(
    (page) => page.is_important_page && !page.is_utility_page
  );

  return {
    pages_checked: safePages.length,
    readable_pages_checked: readable.length,
    scanner_blocked_pages: safePages.filter((page) => page.is_scanner_blocked)
      .length,
    important_pages_checked: important.length,

    indexable_pages: successful.filter(
      (page) => page.indexability === "indexable"
    ).length,
    non_indexable_pages: successful.filter(
      (page) => page.indexability === "non_indexable"
    ).length,

    missing_title_count: successful.filter((page) => !page.title).length,
    missing_meta_description_count: successful.filter(
      (page) => !page.meta_description
    ).length,
    missing_h1_count: important.filter((page) => !page.h1).length,
    multiple_h1_count: important.filter(
      (page) => Number(page.h1_count || 0) > 1
    ).length,

    missing_canonical_count: successful.filter((page) => !page.canonical_url)
      .length,
    canonical_issue_count: successful.filter((page) => page.canonical_issue)
      .length,

    missing_viewport_count: successful.filter((page) => !page.viewport_present)
      .length,
    missing_schema_count: important.filter((page) => !page.has_schema).length,

    heavy_page_count: successful.filter(
      (page) =>
        Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
        Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT ||
        Number(page.text_to_html_ratio || 0) < LOW_TEXT_TO_HTML_RATIO
    ).length,

    average_word_count: Math.round(
      average(successful.map((page) => Number(page.word_count || 0)))
    ),
  };
}

function buildScanSummary({
  pages,
  fixes,
  technicalAuditSummary,
  competitorSnapshots,
  crawlWarnings,
  healthScore,
}) {
  const positives = buildPositiveFindings(pages);
  const blockedPages = (pages || []).filter((page) => page.is_scanner_blocked);
  const scanLimited = blockedPages.length > 0 && pages.length <= 2;
  const summaryParts = [];

  if (scanLimited) {
    summaryParts.push(
      "The scan was limited because the website showed a protection, browser-check, or rate-limit page instead of normal content."
    );
  } else if (positives.length > 0) {
    summaryParts.push(`The scan found a working SEO foundation. ${positives[0]}`);
  } else {
    summaryParts.push(
      "The scan completed and found several practical website improvements."
    );
  }

  if (fixes.length > 0) {
    summaryParts.push(`The main priorities are ${describeFixTypes(fixes)}.`);
  } else {
    summaryParts.push("No major recommendations were returned from the scanner.");
  }

  if (competitorSnapshots.length > 0) {
    summaryParts.push(
      `The scan also reviewed ${competitorSnapshots.length} competitor page${
        competitorSnapshots.length === 1 ? "" : "s"
      }.`
    );
  }

  if (
    Number(technicalAuditSummary.non_indexable_pages || 0) +
      Number(technicalAuditSummary.canonical_issue_count || 0) +
      Number(technicalAuditSummary.multiple_h1_count || 0) +
      Number(technicalAuditSummary.heavy_page_count || 0) >
    0
  ) {
    summaryParts.push(
      "The technical audit also found setup items worth reviewing."
    );
  }

  if (crawlWarnings.length > 0) {
    summaryParts.push(
      "Some checks were limited, so recommendations are based on the pages the scanner could access."
    );
  }

  return {
    score: healthScore,
    status_label: scanLimited
      ? "Scan limited"
      : healthScore >= 85
        ? "Great shape"
        : healthScore >= 70
          ? "Good start"
          : healthScore >= 45
            ? "Needs attention"
            : "Needs urgent attention",
    plain_english_summary: summaryParts.join(" "),
    pages_scanned: pages.length,
    pages_failed: pages.filter((page) => {
      const status = Number(page.status_code || 0);
      return status === 0 || status >= 400 || page.fetch_error;
    }).length,
    scanner_blocked_pages: blockedPages.length,
    high_priority_count: fixes.filter((fix) =>
      ["critical", "high"].includes(fix.priority)
    ).length,
    competitor_gap_count: fixes.filter(
      (fix) => fix.category === "competitor_gap"
    ).length,
    technical_issue_count: fixes.filter(
      (fix) => fix.customer_category === "Technical SEO"
    ).length,
    positive_findings: positives.join(" "),
  };
}

function buildPositiveFindings(pages) {
  const positives = [];
  const successful = (pages || []).filter(
    (page) =>
      page.status_code >= 200 &&
      page.status_code < 300 &&
      !page.is_scanner_blocked
  );

  if (successful.length > 0) {
    positives.push("The scanner was able to read your pages.");
  }

  if (successful.some((page) => page.title && page.meta_description)) {
    positives.push("Your site has basic search title and description setup.");
  }

  if (successful.some((page) => (page.cta_phrases || []).length > 0)) {
    positives.push("Your site gives visitors ways to take the next step.");
  }

  if (successful.some((page) => (page.trust_signals || []).length > 0)) {
    positives.push("Your site already includes some trust signals.");
  }

  if (successful.some((page) => page.has_schema)) {
    positives.push("Your site includes some structured business information.");
  }

  return positives.slice(0, 5);
}

function describeFixTypes(fixes) {
  const labels = [];

  if (fixes.some((fix) => fix.category === "scanner_blocked")) {
    labels.push("scan access");
  }

  if (
    fixes.some(
      (fix) => fix.category === "thin_content" || fix.category === "page_heading"
    )
  ) {
    labels.push("stronger page content");
  }

  if (
    fixes.some(
      (fix) => fix.category === "trust_signal_gap" || fix.category === "schema"
    )
  ) {
    labels.push("trust and structured information");
  }

  if (
    fixes.some(
      (fix) =>
        fix.category === "performance_hint" || fix.category === "js_rendering"
    )
  ) {
    labels.push("page setup and performance cleanup");
  }

  if (fixes.some((fix) => fix.category === "competitor_gap")) {
    labels.push("competitor opportunities");
  }

  if (fixes.some((fix) => fix.customer_category === "Technical SEO")) {
    labels.push("technical SEO opportunities");
  }

  if (labels.length === 0) return "a few website cleanup items";
  if (labels.length === 1) return labels[0];

  return `${labels.slice(0, -1).join(", ")}, and ${
    labels[labels.length - 1]
  }`;
}

function calculateHealthScore({ fixes, pages }) {
  const blockedPages = (pages || []).filter((page) => page.is_scanner_blocked);
  const readablePages = (pages || []).filter((page) => !page.is_scanner_blocked);

  if (blockedPages.length > 0 && readablePages.length === 0) {
    return 40;
  }

  if (blockedPages.length > 0 && readablePages.length <= 1) {
    return 50;
  }

  let score = 100;

  for (const fix of fixes || []) {
    if (fix.category === "scanner_blocked") score -= 35;
    else if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

function buildClientRenderingSummary(pages) {
  const checked = (pages || []).filter(
    (page) =>
      page.status_code >= 200 &&
      page.status_code < 300 &&
      !page.is_scanner_blocked
  );

  const flaggedPaths = unique(
    checked
      .filter((page) => page.likely_client_rendered)
      .map((page) => cleanPath(page.url))
  );

  return {
    detected: flaggedPaths.length > 0,
    flagged_pages: flaggedPaths,
    checked_pages: checked.length,
    fraction: checked.length
      ? Number((flaggedPaths.length / checked.length).toFixed(2))
      : 0,
  };
}

/* -------------------------------------------------------------------------- */
/* Robots and sitemap                                                          */
/* -------------------------------------------------------------------------- */

async function fetchRobotsRules(websiteUrl, timeoutMs) {
  const origin = new URL(websiteUrl).origin;
  const robotsUrl = `${origin}/robots.txt`;

  try {
    const response = await fetchWithTimeout(
      robotsUrl,
      {
        method: "GET",
        headers: {
          "User-Agent": USER_AGENT,
          Accept: "text/plain,*/*",
        },
      },
      timeoutMs
    );

    if (!response.ok) {
      return {
        available: false,
        groups: [],
        sitemaps: [],
      };
    }

    const text = await response.text();

    return parseRobotsTxt(text);
  } catch {
    return {
      available: false,
      groups: [],
      sitemaps: [],
    };
  }
}

function parseRobotsTxt(text) {
  const lines = String(text || "").split(/\r?\n/);
  const groups = [];
  const sitemaps = [];

  let currentAgents = [];
  let currentRules = [];

  function flush() {
    if (currentAgents.length > 0) {
      groups.push({
        agents: currentAgents,
        rules: currentRules,
      });
    }

    currentAgents = [];
    currentRules = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.split("#")[0].trim();

    if (!line) continue;

    const [rawKey, ...rest] = line.split(":");
    const key = String(rawKey || "").trim().toLowerCase();
    const value = rest.join(":").trim();

    if (key === "sitemap" && value) {
      sitemaps.push(value);
      continue;
    }

    if (key === "user-agent") {
      if (currentRules.length > 0) flush();

      currentAgents.push(value.toLowerCase());
      continue;
    }

    if (key === "allow" || key === "disallow") {
      currentRules.push({
        type: key,
        path: value,
      });
    }
  }

  flush();

  return {
    available: true,
    groups,
    sitemaps: unique(sitemaps),
  };
}

function robotsAllows(robots, url) {
  if (!robots?.available || !Array.isArray(robots.groups)) return true;

  const path = new URL(url).pathname || "/";
  const relevantRules = [];

  for (const group of robots.groups) {
    const applies = (group.agents || []).some(
      (agent) =>
        agent === "*" ||
        agent.includes("seo-autopilot") ||
        agent.includes("seo") ||
        USER_AGENT.toLowerCase().includes(agent)
    );

    if (applies) {
      relevantRules.push(...(group.rules || []));
    }
  }

  if (relevantRules.length === 0) return true;

  let bestRule = null;

  for (const rule of relevantRules) {
    if (rule.type === "disallow" && !rule.path) continue;

    if (robotsPathMatches(rule.path, path)) {
      if (!bestRule || String(rule.path).length > String(bestRule.path).length) {
        bestRule = rule;
      }
    }
  }

  if (!bestRule) return true;

  return bestRule.type === "allow";
}

function robotsPathMatches(pattern, path) {
  if (!pattern) return false;

  const escaped = String(pattern)
    .replace(/[.+?^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*");

  const regex = new RegExp(`^${escaped}`);

  return regex.test(path);
}

async function discoverSitemapUrls({
  websiteUrl,
  robots,
  timeoutMs,
  maxUrls,
  startPathPrefix,
}) {
  const origin = new URL(websiteUrl).origin;
  const sitemapQueue = unique([
    ...(robots?.sitemaps || []),
    `${origin}/sitemap.xml`,
    `${origin}/sitemap_index.xml`,
  ]);

  const seenSitemaps = new Set();
  const pageUrls = [];

  while (
    sitemapQueue.length > 0 &&
    seenSitemaps.size < 20 &&
    pageUrls.length < maxUrls
  ) {
    const sitemapUrl = sitemapQueue.shift();

    if (!sitemapUrl || seenSitemaps.has(sitemapUrl)) continue;

    seenSitemaps.add(sitemapUrl);

    try {
      const response = await fetchWithTimeout(
        sitemapUrl,
        {
          method: "GET",
          headers: {
            "User-Agent": USER_AGENT,
            Accept: "application/xml,text/xml,*/*",
          },
        },
        timeoutMs
      );

      if (!response.ok) continue;

      const text = await response.text();
      const locs = Array.from(text.matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi))
        .map((match) => decodeHtml(match[1]).trim())
        .filter(Boolean);

      for (const loc of locs) {
        const normalized = normalizeCrawlUrl(loc, websiteUrl);

        if (!normalized) continue;
        if (!isSameRegistrableSite(normalized, websiteUrl)) continue;

        if (isSitemapUrl(normalized)) {
          if (!seenSitemaps.has(normalized) && sitemapQueue.length < 50) {
            sitemapQueue.push(normalized);
          }
          continue;
        }

        if (
          !isUtilityUrl(normalized) &&
          matchesStartPathPrefix(normalized, startPathPrefix)
        ) {
          pageUrls.push(normalized);
        }

        if (pageUrls.length >= maxUrls) break;
      }
    } catch {
      // Ignore sitemap errors.
    }
  }

  return stableSortUrls(unique(pageUrls)).slice(0, maxUrls);
}

/* -------------------------------------------------------------------------- */
/* HTML helpers                                                                */
/* -------------------------------------------------------------------------- */

function extractTitleTags(html) {
  return Array.from(
    String(html || "").matchAll(/<title[^>]*>([\s\S]*?)<\/title>/gi)
  )
    .map((match) => cleanString(stripTags(match[1])))
    .filter(Boolean);
}

function extractMetaNameContents(html, name) {
  const output = [];
  const regex = /<meta\b[^>]*>/gi;
  const tags = String(html || "").match(regex) || [];

  for (const tag of tags) {
    const tagName = getAttribute(tag, "name") || getAttribute(tag, "property");

    if (String(tagName || "").toLowerCase() === String(name).toLowerCase()) {
      const content = cleanString(getAttribute(tag, "content"));
      if (content) output.push(content);
    }
  }

  return output;
}

function extractHeadingTags(html, heading) {
  const regex = new RegExp(
    `<${heading}\\b[^>]*>([\\s\\S]*?)<\\/${heading}>`,
    "gi"
  );

  return Array.from(String(html || "").matchAll(regex))
    .map((match) => cleanString(stripTags(match[1])))
    .filter(Boolean)
    .slice(0, 40);
}

function extractVisibleText(html) {
  const stripped = String(html || "")
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript\b[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]+>/g, " ");

  return decodeHtml(stripped).replace(/\s+/g, " ").trim();
}

function extractLinks(html, baseUrl) {
  const links = [];
  const regex = /<a\b[^>]*href=["']?([^"'\s>]+)["']?[^>]*>/gi;

  for (const match of String(html || "").matchAll(regex)) {
    const href = decodeHtml(match[1]);
    const normalized = normalizeCrawlUrl(href, baseUrl);

    if (normalized) links.push(normalized);
  }

  return unique(links);
}

function extractImages(html) {
  const images = [];
  const regex = /<img\b[^>]*>/gi;
  const tags = String(html || "").match(regex) || [];

  for (const tag of tags) {
    images.push({
      src: getAttribute(tag, "src") || "",
      alt: cleanString(getAttribute(tag, "alt") || ""),
    });
  }

  return images;
}

function extractSchemaTypes(html) {
  const output = [];
  const scripts = Array.from(
    String(html || "").matchAll(
      /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi
    )
  );

  for (const script of scripts) {
    const text = script[1];

    for (const match of text.matchAll(/"@type"\s*:\s*"([^"]+)"/gi)) {
      output.push(match[1]);
    }
  }

  return unique(output).slice(0, 30);
}

function extractCanonical(html, pageUrl) {
  const links =
    String(html || "").match(
      /<link\b[^>]*rel=["'][^"']*canonical[^"']*["'][^>]*>/gi
    ) || [];

  if (links.length === 0) {
    return {
      url: "",
      status: "missing",
      issue: "",
    };
  }

  const href = getAttribute(links[0], "href") || "";
  const canonicalUrl = normalizeCrawlUrl(href, pageUrl) || href;

  if (!canonicalUrl) {
    return {
      url: "",
      status: "invalid",
      issue: "Canonical tag is present but empty.",
    };
  }

  return {
    url: canonicalUrl,
    status:
      normalizeComparableUrl(canonicalUrl) === normalizeComparableUrl(pageUrl)
        ? "self_referencing"
        : "points_elsewhere",
    issue: isSameRegistrableSite(canonicalUrl, pageUrl)
      ? ""
      : "Canonical points to a different domain.",
  };
}

function extractRobotsMeta(html) {
  const values = [
    ...extractMetaNameContents(html, "robots"),
    ...extractMetaNameContents(html, "googlebot"),
  ];

  return values.join(", ").toLowerCase();
}

function buildIndexability({ status, robotsMeta, canonical, url }) {
  const reasons = [];

  if (status < 200 || status >= 300) {
    reasons.push(`HTTP status ${status}`);
  }

  if (robotsMeta.includes("noindex")) {
    reasons.push("Meta robots contains noindex.");
  }

  if (canonical.issue) {
    reasons.push(canonical.issue);
  }

  const nonIndexable = reasons.length > 0;

  return {
    status: nonIndexable ? "non_indexable" : "indexable",
    reasons,
  };
}

function detectSocialMeta(html) {
  return {
    open_graph_present: /<meta\b[^>]*(property|name)=["']og:/i.test(html),
    twitter_card_present: /<meta\b[^>]*(property|name)=["']twitter:/i.test(
      html
    ),
  };
}

function extractHreflangs(html) {
  const tags =
    String(html || "").match(
      /<link\b[^>]*rel=["'][^"']*alternate[^"']*["'][^>]*>/gi
    ) || [];

  return tags
    .map((tag) => ({
      hreflang: getAttribute(tag, "hreflang") || "",
      href: getAttribute(tag, "href") || "",
    }))
    .filter((item) => item.hreflang || item.href)
    .slice(0, 50);
}

function detectTrustSignals(text) {
  const lower = String(text || "").toLowerCase();
  const signals = [];

  const checks = [
    ["reviews", ["review", "reviews", "testimonial", "testimonials", "avis"]],
    ["awards", ["award", "awards", "certified", "certification"]],
    ["experience", ["years of experience", "since 19", "since 20"]],
    ["guarantee", ["guarantee", "warranty"]],
    ["location", ["address", "located", "visit us"]],
  ];

  for (const [label, terms] of checks) {
    if (terms.some((term) => lower.includes(term))) {
      signals.push(label);
    }
  }

  return unique(signals);
}

function detectCtaPhrases(text) {
  const lower = String(text || "").toLowerCase();
  const phrases = [
    "book now",
    "contact us",
    "get started",
    "request a quote",
    "call now",
    "schedule",
    "buy now",
    "reserve",
    "learn more",
    "sign up",
    "réserver",
    "voir",
    "découvrir",
    "join",
    "visit",
    "shop",
  ];

  return phrases.filter((phrase) => lower.includes(phrase));
}

function detectFaqQuestions(html, text) {
  const headings = [
    ...extractHeadingTags(html, "h2"),
    ...extractHeadingTags(html, "h3"),
  ];

  const questionHeadings = headings.filter((heading) => heading.includes("?"));

  const textQuestions = Array.from(
    String(text || "").matchAll(/([^.!?]{8,120}\?)/g)
  )
    .map((match) => cleanString(match[1]))
    .filter(Boolean);

  return unique([...questionHeadings, ...textQuestions]).slice(0, 12);
}

function getAttribute(tag, attr) {
  const regex = new RegExp(`${attr}\\s*=\\s*["']([^"']*)["']`, "i");
  const match = String(tag || "").match(regex);

  return match ? decodeHtml(match[1]) : "";
}

function stripTags(input) {
  return decodeHtml(String(input || "").replace(/<[^>]+>/g, " "));
}

/* -------------------------------------------------------------------------- */
/* URL helpers                                                                 */
/* -------------------------------------------------------------------------- */

function normalizeScanMode(value) {
  const mode = String(value || "quick").toLowerCase();

  return SCAN_MODES[mode] ? mode : "quick";
}

function normalizeStartUrl(input) {
  const raw = String(input || "").trim();

  if (!raw) return "";

  const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

  const parsed = new URL(withProtocol);

  parsed.hash = "";

  if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
    parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  }

  return parsed.toString();
}

function normalizeCrawlUrl(candidate, baseUrl) {
  try {
    const raw = String(candidate || "").trim();

    if (!raw) return "";
    if (raw.startsWith("#")) return "";
    if (/^(mailto|tel|sms|javascript):/i.test(raw)) return "";

    const parsed = new URL(raw, baseUrl);

    if (!["http:", "https:"].includes(parsed.protocol)) return "";

    parsed.hash = "";
    parsed.search = "";
    parsed.hostname = parsed.hostname.toLowerCase();

    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    }

    return parsed.toString();
  } catch {
    return "";
  }
}

function canonicalQueueKey(url) {
  try {
    const parsed = new URL(url);

    parsed.hash = "";
    parsed.search = "";
    parsed.hostname = parsed.hostname.toLowerCase();

    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    }

    return `${parsed.protocol}//${parsed.hostname}${parsed.pathname}`.toLowerCase();
  } catch {
    return String(url || "").toLowerCase();
  }
}

function normalizeComparableUrl(url) {
  try {
    const parsed = new URL(url);

    parsed.hash = "";
    parsed.search = "";
    parsed.hostname = parsed.hostname.toLowerCase();

    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    }

    return parsed.toString().toLowerCase();
  } catch {
    return String(url || "").toLowerCase();
  }
}

function getDomain(url) {
  try {
    return new URL(normalizeStartUrl(url)).hostname.replace(/^www\./i, "");
  } catch {
    return "";
  }
}

function isSameRegistrableSite(a, b) {
  try {
    return getDomain(a) === getDomain(b);
  } catch {
    return false;
  }
}

function getStartPathPrefix(startUrl) {
  try {
    const path = new URL(startUrl).pathname.toLowerCase();
    const match = path.match(/^\/([a-z]{2})(\/|$)/i);

    if (!match) return "";

    const language = match[1].toLowerCase();

    if (!LANGUAGE_PATHS.includes(language)) return "";

    return `/${language}`;
  } catch {
    return "";
  }
}

function matchesStartPathPrefix(candidateUrl, startPathPrefix) {
  if (!startPathPrefix) return true;

  try {
    const path = new URL(candidateUrl).pathname.toLowerCase();

    return path === startPathPrefix || path.startsWith(`${startPathPrefix}/`);
  } catch {
    return false;
  }
}

function isSitemapUrl(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();

    return path.endsWith(".xml") || path.includes("sitemap");
  } catch {
    return false;
  }
}

function isUtilityUrl(url) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase();

    const utilityPatterns = [
      /\.(jpg|jpeg|png|gif|webp|svg|ico|xml|pdf|zip|mp4|mp3|css|js|woff|woff2|ttf)$/i,

      /\/wp-admin/i,
      /\/wp-json/i,

      /\/cart/i,
      /\/checkout/i,
      /\/login/i,
      /\/logout/i,
      /\/account/i,

      /\/privacy/i,
      /\/terms/i,
      /\/cookie/i,
      /\/cookies/i,
      /\/cgu/i,
      /\/mentions-legales/i,
      /\/legal/i,

      /backup/i,
      /\/home-\d+$/i,
      /\/old($|\/|-)/i,
      /\/draft($|\/|-)/i,
      /\/staging($|\/|-)/i,
      /\/test($|\/|-)/i,
      /\/preview($|\/|-)/i,
    ];

    return utilityPatterns.some((pattern) => pattern.test(path));
  } catch {
    return true;
  }
}

function isImportantPage(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();

    if (path === "/" || path === "") return true;

    const languageRoot = path.match(/^\/([a-z]{2})\/?$/i);

    if (
      languageRoot &&
      LANGUAGE_PATHS.includes(languageRoot[1].toLowerCase())
    ) {
      return true;
    }

    return /\/(service|services|product|products|activity|activities|booking|experience|experiences|tour|tours|things-to-do|electricite|energie|wine|wines|shop|about|contact|location|locations|listing|annonce|reservation|category|categories|guide|guides|collection|visit|club|story)/i.test(
      path
    );
  } catch {
    return false;
  }
}

function scoreUrlPriority(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();

    if (path === "/" || path === "") return 100;
    if (isImportantPage(url)) return 80;
    if (path.split("/").filter(Boolean).length <= 2) return 60;

    return 20;
  } catch {
    return 0;
  }
}

function urlDepth(url) {
  try {
    return new URL(url).pathname.split("/").filter(Boolean).length;
  } catch {
    return 99;
  }
}

function stableSortUrls(urls) {
  return unique(urls || []).sort((a, b) => {
    const priorityDiff = scoreUrlPriority(b) - scoreUrlPriority(a);

    if (priorityDiff !== 0) return priorityDiff;

    const depthDiff = urlDepth(a) - urlDepth(b);

    if (depthDiff !== 0) return depthDiff;

    return String(a).localeCompare(String(b));
  });
}

function sortQueue(queue) {
  queue.sort((a, b) => {
    const priorityDiff = b.priority - a.priority;

    if (priorityDiff !== 0) return priorityDiff;

    const depthDiff = a.depth - b.depth;

    if (depthDiff !== 0) return depthDiff;

    return String(a.url).localeCompare(String(b.url));
  });
}

function cleanPath(input) {
  try {
    const parsed = new URL(String(input || ""), "https://example.com");
    const path = parsed.pathname || "/";

    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    const value = String(input || "/").split("?")[0].split("#")[0];

    if (!value || value === "/") return "/";

    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

function normalizeUrlList(value) {
  if (!Array.isArray(value)) return [];

  return unique(
    value
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .map((item) => {
        try {
          return normalizeStartUrl(item);
        } catch {
          return "";
        }
      })
      .filter(Boolean)
  );
}

function languageNameFromPath(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const match = path.match(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i);

  if (!match) return "";

  const map = {
    en: "English",
    fr: "French",
    es: "Spanish",
    de: "German",
    it: "Italian",
    pt: "Portuguese",
    nl: "Dutch",
  };

  return map[match[1].toLowerCase()] || "";
}

function readablePageLabel(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const languageName = languageNameFromPath(path);

  const withoutLanguage = path
    .replace(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");

  if (!withoutLanguage) {
    return languageName ? `${languageName} homepage` : "Homepage";
  }

  const parts = withoutLanguage.split("/").filter(Boolean);

  if (parts[0] === "category" && parts[1]) {
    const label = humanizeUrlSlug(parts.slice(1).join(" / "));

    return languageName
      ? `${languageName} category page: ${label}`
      : `Category page: ${label}`;
  }

  if (parts[0] === "listing" && parts[1]) {
    const label = humanizeUrlSlug(parts.slice(1).join(" / "));

    return languageName
      ? `${languageName} listing page: ${label}`
      : `Listing page: ${label}`;
  }

  if (parts[0] === "annonce" && parts[1]) {
    const label = humanizeUrlSlug(parts[1]);

    return languageName
      ? `${languageName} activity page: ${label}`
      : `Activity page: ${label}`;
  }

  if (parts[0] === "wine" && parts[1]) {
    return `Wine page: ${humanizeUrlSlug(parts.slice(1).join(" / "))}`;
  }

  const label = humanizeUrlSlug(parts.join(" / "));

  return languageName ? `${languageName} page: ${label}` : label;
}

function humanizeUrlSlug(value) {
  return String(value || "")
    .replace(/-/g, " ")
    .replace(/_/g, " ")
    .replace(/\s*\/\s*/g, " / ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

async function fetchWithTimeout(url, options = {}, timeoutMs, redirectCount = 0) {
  await assertSafePublicUrl(url);
  await assertSafeBodyUrls(options.body);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, redirect: "manual", signal: controller.signal });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location") || "";
      if (!location) return response;
      if (redirectCount >= 5) throw new Error("Too many redirects while checking this website.");
      const nextUrl = new URL(location, url).toString();
      await assertSafePublicUrl(nextUrl);
      const nextOptions = response.status === 303 ? { ...options, method: "GET", body: undefined } : options;
      return await fetchWithTimeout(nextUrl, nextOptions, timeoutMs, redirectCount + 1);
    }
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

async function assertSafeBodyUrls(body) {
  if (!body || typeof body !== "string" || !body.includes('"url"')) return;
  try {
    const payload = JSON.parse(body);
    if (payload?.url) await assertSafePublicUrl(payload.url);
  } catch {
    return;
  }
}

async function assertSafePublicUrl(input) {
  const parsed = new URL(String(input || ""));
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("Only http and https website URLs can be scanned.");
  const hostname = parsed.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (!hostname || hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local") || hostname.endsWith(".internal")) throw new Error("This website address is not allowed for scanning.");
  if (isIpAddress(hostname)) {
    if (!isPublicIpAddress(hostname)) throw new Error("Private or local network addresses cannot be scanned.");
    return true;
  }
  const resolvedIps = await resolvePublicDns(hostname);
  if (resolvedIps.length === 0) throw new Error("Could not verify that this website resolves to a public address.");
  if (resolvedIps.some((ip) => !isPublicIpAddress(ip))) throw new Error("This website resolves to a private or local network address.");
  return true;
}

function isIpAddress(value) { return isIpv4Address(value) || String(value || "").includes(":"); }
function isIpv4Address(value) { const parts = String(value || "").split("."); return parts.length === 4 && parts.every((part) => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255); }
function isPublicIpAddress(ip) {
  const value = String(ip || "").toLowerCase();
  if (isIpv4Address(value)) {
    const [a, b] = value.split(".").map(Number);
    if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
    if (a === 100 && b >= 64 && b <= 127) return false;
    if (a === 169 && b === 254) return false;
    if (a === 172 && b >= 16 && b <= 31) return false;
    if (a === 192 && (b === 0 || b === 168)) return false;
    if (a === 198 && (b === 18 || b === 19)) return false;
    return value !== "255.255.255.255";
  }
  if (value === "::" || value === "::1" || value.startsWith("fe80:") || value.startsWith("fc") || value.startsWith("fd") || value.startsWith("ff") || value.startsWith("2001:db8")) return false;
  if (value.startsWith("::ffff:")) return isPublicIpAddress(value.slice(7));
  return value.includes(":");
}

async function resolvePublicDns(hostname) {
  const cache = (globalThis as any).__safeDnsCache || new Map();
  (globalThis as any).__safeDnsCache = cache;
  if (cache.has(hostname)) return cache.get(hostname);
  const results = [];
  for (const type of ["A", "AAAA"]) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const endpoint = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(hostname)}&type=${type}`;
      const response = await fetch(endpoint, { headers: { Accept: "application/dns-json" }, signal: controller.signal });
      clearTimeout(timeout);
      const payload = await response.json().catch(() => ({}));
      for (const answer of payload.Answer || []) if (answer?.data && isIpAddress(String(answer.data))) results.push(String(answer.data));
    } catch {}
  }
  const uniqueResults = unique(results);
  cache.set(hostname, uniqueResults);
  return uniqueResults;
}

async function readLimitedText(response, maxBytes) {
  const text = await response.text();
  return approximateBytes(text) <= maxBytes ? text : text.slice(0, maxBytes);
}
function approximateBytes(text) { return new TextEncoder().encode(String(text || "")).length; }
function tokenizeWords(text) { return String(text || "").split(/\s+/).map((word) => word.trim()).filter((word) => /[a-zA-ZÀ-ÿ0-9]/.test(word)); }
function cleanString(value) { return decodeHtml(String(value || "").replace(/\s+/g, " ").trim()); }
function clampText(value, max) { const text = cleanString(value); return text.length <= max ? text : text.slice(0, Math.max(0, max - 1)).trim(); }
function decodeHtml(value) { return String(value || "").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&mdash;/g, "—").replace(/&#039;/g, "'").replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;/g, " "); }
function countMatches(text, regex) { return Array.from(String(text || "").matchAll(regex)).length; }
function unique(values) { return Array.from(new Set((values || []).filter(Boolean))); }
function average(values) { const nums = (values || []).map(Number).filter((num) => Number.isFinite(num)); return nums.length ? nums.reduce((sum, value) => sum + value, 0) / nums.length : 0; }
function median(values) { const nums = (values || []).map(Number).filter((num) => Number.isFinite(num)).sort((a, b) => a - b); if (nums.length === 0) return 0; const mid = Math.floor(nums.length / 2); return nums.length % 2 ? nums[mid] : Math.round((nums[mid - 1] + nums[mid]) / 2); }
function groupDuplicateValues(pages, field) { const groups = new Map(); for (const page of pages || []) { const value = cleanString(page[field]); if (!value) continue; const key = value.toLowerCase(); if (!groups.has(key)) groups.set(key, { value, pages: [] }); groups.get(key).pages.push(page); } return Array.from(groups.values()).filter((group) => group.pages.length > 1); }
function friendlyNameFromDomain(domain) { const base = String(domain || "").replace(/^www\./i, "").split(".")[0].replace(/[-_]+/g, " "); return base.charAt(0).toUpperCase() + base.slice(1); }
function pushUniqueWarning(warnings, warning) { if (warning && !warnings.includes(warning)) warnings.push(warning); }