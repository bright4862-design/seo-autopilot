import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/3.3; +https://seoautopilot.app/bot)";

const MAX_HTML_BYTES = 800000;
const CRAWL_TIME_BUDGET_MS = 95000;
const LARGE_HTML_BYTES = 500000;
const HEAVY_SCRIPT_TAG_COUNT = 50;
const LOW_TEXT_TO_HTML_RATIO = 3;
const MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE = 2;

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

    const scanSummary = buildScanSummary({
      pages: crawlResult.crawled_pages,
      fixes: rawFixes,
      technicalAuditSummary,
      competitorSnapshots: competitorResult.competitor_page_snapshots,
      crawlWarnings: crawlResult.crawl_warnings,
    });

    const healthScore = calculateHealthScore(rawFixes);

    return Response.json({
      success: true,

      website_url: websiteUrl,
      normalized_url: normalizedUrl,
      domain,
      scan_mode: scanMode,

      pages_found: crawlResult.pages_found,
      pages_crawled: crawlResult.pages_crawled,
      queued_remaining: crawlResult.queued_remaining,

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

  const robots = await fetchRobotsRules(websiteUrl, config.timeoutMs);

  function addToQueue(candidateUrl, source = "internal") {
    const normalized = normalizeCrawlUrl(candidateUrl, websiteUrl);

    if (!normalized) return false;
    if (!isSameRegistrableSite(normalized, websiteUrl)) return false;
    if (isUtilityUrl(normalized)) return false;
    if (queued.has(normalized) || crawled.has(normalized)) return false;

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

    queued.add(normalized);
    queue.push({
      url: normalized,
      source,
      priority: source === "start" ? 999 : scoreUrlPriority(normalized),
    });

    queue.sort((a, b) => b.priority - a.priority);

    return true;
  }

  addToQueue(websiteUrl, "start");

  if (config.useSitemap) {
    const sitemapUrls = await discoverSitemapUrls({
      websiteUrl,
      robots,
      timeoutMs: config.timeoutMs,
      maxUrls: config.maxPages * 3,
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
        crawled.add(item.url);

        return await fetchAndExtractPage({
          url: item.url,
          domain,
          source: item.source,
          timeoutMs: config.timeoutMs,
        });
      })
    );

    for (const page of pages) {
      if (crawledPages.length >= config.maxPages) break;

      crawledPages.push(page);

      if (
        page.status_code >= 200 &&
        page.status_code < 300 &&
        !page.fetch_error
      ) {
        for (const link of page.internal_links || []) {
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

  return {
    crawled_pages: crawledPages,
    pages_found: queued.size,
    pages_crawled: crawledPages.length,
    queued_remaining: queue.length,
    crawl_warnings: crawlWarnings,
  };
}

async function fetchAndExtractPage({ url, domain, source, timeoutMs }) {
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
          "Accept-Language": "en-US,en;q=0.9",
          "Cache-Control": "no-cache",
        },
      },
      timeoutMs
    );

    const finalUrl = response.url || url;
    const contentType = response.headers.get("content-type") || "";
    const html = await readLimitedText(response, MAX_HTML_BYTES);

    return extractPageData({
      url: finalUrl,
      originalUrl: url,
      status: response.status,
      contentType,
      html,
      domain,
      source,
      fetchError: "",
    });
  } catch (error) {
    return {
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
      indexability: "unknown",
      indexability_reasons: ["The page could not be fetched."],
      response_size_bytes: 0,
      html_truncated: false,
    };
  }
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
  const internalLinks = links.filter((link) =>
    isSameRegistrableSite(link, url)
  );
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

  const likelyClientRendered =
    status >= 200 &&
    status < 300 &&
    words.length < 80 &&
    scriptTagCount >= 20 &&
    internalLinks.length > 0;

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
    indexability: indexability.status,
    indexability_reasons: indexability.reasons,

    viewport_present: viewportPresent,
    charset_present: charsetPresent,

    open_graph_present: socialMeta.open_graph_present,
    twitter_card_present: socialMeta.twitter_card_present,

    hreflangs,

    response_size_bytes: responseSizeBytes,
    html_truncated: responseSizeBytes >= MAX_HTML_BYTES,
    script_tag_count: scriptTagCount,
    text_to_html_ratio: textToHtmlRatio,

    is_important_page: important,
    is_utility_page: utility,
    likely_client_rendered: likelyClientRendered,
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

  const snapshots = await Promise.all(
    competitorResults.map(async (competitor) => {
      const page = await fetchAndExtractPage({
        url: competitor.url,
        domain: competitor.domain,
        source: "competitor",
        timeoutMs: config.timeoutMs,
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
  };
}

function buildCompetitorComparison({ userPages, competitorSnapshots }) {
  const userImportant = (userPages || []).filter(
    (page) => page.is_important_page && !page.is_utility_page
  );

  const readableCompetitors = (competitorSnapshots || []).filter(
    (item) =>
      item.status_code >= 200 && item.status_code < 300 && item.word_count > 50
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

  addBrokenPageFindings(fixes, pages);
  addContentFindings(fixes, pages);
  addScreamingFrogLiteFindings(fixes, pages);
  addCompetitorFindings(fixes, competitorComparison, competitorSnapshots);

  return dedupeFindings(fixes).sort(compareFindings);
}

function addBrokenPageFindings(fixes, pages) {
  const brokenPages = pages.filter((page) => {
    const status = Number(page.status_code || 0);
    return status === 0 || status >= 400 || page.fetch_error;
  });

  if (brokenPages.length === 0) return;

  fixes.push(
    makeFinding({
      id: "broken_pages",
      category: "broken_page",
      customerCategory: "Broken pages",
      priority: "high",
      title:
        brokenPages.length === 1
          ? "One page may not be loading correctly"
          : "Some pages may not be loading correctly",
      explanation:
        "We found pages that did not load successfully during the scan.",
      why:
        "Broken or blocked pages can stop visitors and search engines from understanding the website.",
      affectedPages: brokenPages.map((page) => cleanPath(page.url)),
      details: {
        affected_count: brokenPages.length,
        examples: brokenPages.slice(0, 8).map((page) => ({
          url: page.url,
          status_code: page.status_code,
          fetch_error: page.fetch_error,
          title: page.title,
        })),
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
          "Some important service pages may not show enough proof that visitors can trust the business.",
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
          "Some important service pages do not appear to answer common customer questions.",
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
    (page) => page.status_code >= 200 && page.status_code < 300
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
        why:
          "Search titles help people and search engines understand the page.",
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
        explanation:
          "Some pages appear to use the same search title.",
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
        explanation:
          "Some pages appear to have more than one main heading.",
        why:
          "One clear main heading can make the page easier to understand.",
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
        explanation:
          "Some pages do not show a preferred page address.",
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
        title: "Review pages that may not be indexable",
        explanation:
          "Some pages may be telling search engines not to show them in results.",
        why:
          "Important pages should usually be available to search engines.",
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
        explanation:
          "Some pages may be missing a mobile viewport setting.",
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
        explanation:
          "Some images may be missing descriptive alt text.",
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
        title: "Some important pages look heavy or script-heavy",
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

function addCompetitorFindings(fixes, competitorComparison, competitorSnapshots) {
  const readableCompetitors = (competitorSnapshots || []).filter(
    (item) =>
      item.status_code >= 200 && item.status_code < 300 && item.word_count > 50
  );

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
  const successful = safePages.filter(
    (page) => page.status_code >= 200 && page.status_code < 300
  );
  const important = successful.filter(
    (page) => page.is_important_page && !page.is_utility_page
  );

  return {
    pages_checked: safePages.length,
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
}) {
  const positives = buildPositiveFindings(pages);
  const summaryParts = [];

  if (positives.length > 0) {
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
    score: calculateHealthScore(fixes),
    status_label: calculateHealthScore(fixes) >= 80 ? "Strong" : "Needs work",
    plain_english_summary: summaryParts.join(" "),
    pages_scanned: pages.length,
    pages_failed: pages.filter((page) => {
      const status = Number(page.status_code || 0);
      return status === 0 || status >= 400 || page.fetch_error;
    }).length,
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
    (page) => page.status_code >= 200 && page.status_code < 300
  );

  if (successful.length > 0) {
    positives.push("The scanner was able to read at least one page.");
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

  if (fixes.some((fix) => fix.category === "performance_hint")) {
    labels.push("page performance cleanup");
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

function calculateHealthScore(fixes) {
  let score = 100;

  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

function buildClientRenderingSummary(pages) {
  const checked = (pages || []).filter(
    (page) => page.status_code >= 200 && page.status_code < 300
  );

  const flagged = checked.filter((page) => page.likely_client_rendered);

  return {
    detected: flagged.length > 0,
    flagged_pages: flagged.map((page) => cleanPath(page.url)),
    checked_pages: checked.length,
    fraction: checked.length
      ? Number((flagged.length / checked.length).toFixed(2))
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

async function discoverSitemapUrls({ websiteUrl, robots, timeoutMs, maxUrls }) {
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

        if (!isUtilityUrl(normalized)) {
          pageUrls.push(normalized);
        }

        if (pageUrls.length >= maxUrls) break;
      }
    } catch {
      // Ignore sitemap errors.
    }
  }

  return unique(pageUrls).slice(0, maxUrls);
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
    twitter_card_present: /<meta\b[^>]*(property|name)=["']twitter:/i.test(html),
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
    ["reviews", ["review", "reviews", "testimonial", "testimonials"]],
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

    const blockedParams = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_content",
      "utm_term",
      "fbclid",
      "gclid",
    ];

    for (const param of blockedParams) {
      parsed.searchParams.delete(param);
    }

    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    }

    return parsed.toString();
  } catch {
    return "";
  }
}

function normalizeComparableUrl(url) {
  try {
    const parsed = new URL(url);

    parsed.hash = "";
    parsed.search = "";

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

    return /\/(service|services|product|products|activity|activities|booking|experience|experiences|tour|tours|things-to-do|electricite|energie|wine|wines|shop|about|contact|location|locations)/i.test(
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

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function readLimitedText(response, maxBytes) {
  const text = await response.text();

  if (approximateBytes(text) <= maxBytes) return text;

  return text.slice(0, maxBytes);
}

function approximateBytes(text) {
  return new TextEncoder().encode(String(text || "")).length;
}

function tokenizeWords(text) {
  return String(text || "")
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => /[a-zA-ZÀ-ÿ0-9]/.test(word));
}

function cleanString(value) {
  return decodeHtml(String(value || "").replace(/\s+/g, " ").trim());
}

function clampText(value, max) {
  const text = cleanString(value);

  if (text.length <= max) return text;

  return text.slice(0, Math.max(0, max - 1)).trim();
}

function decodeHtml(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ");
}

function countMatches(text, regex) {
  return Array.from(String(text || "").matchAll(regex)).length;
}

function unique(values) {
  return Array.from(new Set((values || []).filter(Boolean)));
}

function average(values) {
  const nums = (values || []).map(Number).filter((num) => Number.isFinite(num));

  if (nums.length === 0) return 0;

  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

function median(values) {
  const nums = (values || [])
    .map(Number)
    .filter((num) => Number.isFinite(num))
    .sort((a, b) => a - b);

  if (nums.length === 0) return 0;

  const mid = Math.floor(nums.length / 2);

  if (nums.length % 2) return nums[mid];

  return Math.round((nums[mid - 1] + nums[mid]) / 2);
}

function groupDuplicateValues(pages, field) {
  const groups = new Map();

  for (const page of pages || []) {
    const value = cleanString(page[field]);

    if (!value) continue;

    const key = value.toLowerCase();

    if (!groups.has(key)) {
      groups.set(key, {
        value,
        pages: [],
      });
    }

    groups.get(key).pages.push(page);
  }

  return Array.from(groups.values()).filter((group) => group.pages.length > 1);
}

function friendlyNameFromDomain(domain) {
  const base = String(domain || "")
    .replace(/^www\./i, "")
    .split(".")[0]
    .replace(/[-_]+/g, " ");

  return base.charAt(0).toUpperCase() + base.slice(1);
}

function pushUniqueWarning(warnings, warning) {
  if (!warnings.includes(warning)) {
    warnings.push(warning);
  }
}