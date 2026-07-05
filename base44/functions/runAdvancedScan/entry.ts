import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GOOGLE_API_KEY_NAME = "GOOGLE_" + "CUSTOM_SEARCH_API_KEY";
const GOOGLE_CX_NAME = "GOOGLE_" + "CUSTOM_SEARCH_CX";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/2.0; +https://seoautopilot.app/bot)";

const SCAN_LIMITS = {
  quick: {
    maxPages: 75,
    batchSize: 6,
    timeoutMs: 12000,
    useSitemap: true,
    discoverCompetitors: false,
    checkBrokenLinks: true,
  },
  deep: {
    maxPages: 500,
    batchSize: 6,
    timeoutMs: 18000,
    useSitemap: true,
    discoverCompetitors: true,
    checkBrokenLinks: true,
  },
};

const UTILITY_PATH_RE =
  /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer|tag|category|author|feed|rss|print|share)/i;

const IMPORTANT_PAGE_RE =
  /(^\/$)|(home|service|services|product|products|loan|loans|program|programs|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve|fix-and-flip|new-construction|bridge|rental|dscr|apply|application|menu|treatment|repair|installation|financing|mortgage|lending|case-study|case-studies)/i;

const ASSET_RE =
  /\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff|woff2|ttf|mp4|mp3|mov|avi|xml|json)$/i;

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
      important_keywords = [],
      competitor_urls = [],
    } = body;

    const scanMode = body.scan_mode === "deep" ? "deep" : "quick";
    const limits = SCAN_LIMITS[scanMode];

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

    const robots = await readRobotsTxt(origin, crawlWarnings);

    let discoveredCompetitors = [];
    let createdCompetitors = [];

    const providedCompetitors = await saveProvidedCompetitors({
      base44,
      user,
      project_id,
      competitor_urls,
    });

    if (providedCompetitors.length > 0) {
      createdCompetitors.push(...providedCompetitors);
    }

    if (scanMode === "deep" && limits.discoverCompetitors) {
      try {
        const discovery = await withTimeout(
          discoverCompetitorsFromSearch({
            base44,
            user,
            project_id,
            website_url: normalizedUrl,
            business_name,
            business_type,
            city,
            important_keywords,
          }),
          12000,
          "Competitor discovery"
        );

        discoveredCompetitors = discovery.discovered_competitors || [];

        if (discovery.created_competitors?.length) {
          createdCompetitors.push(...discovery.created_competitors);
        }

        if (discovery.warnings?.length) {
          crawlWarnings.push(...discovery.warnings);
        }
      } catch (error) {
        crawlWarnings.push(
          `Competitor discovery was skipped: ${
            error?.message || "Unknown error"
          }`
        );
      }
    }

    const sitemapUrls =
      limits.useSitemap
        ? await discoverSitemapUrls(origin, domain, robots, crawlWarnings)
        : [];

    const crawlResult = await crawlWebsite({
      startUrl: normalizedUrl,
      domain,
      sitemapUrls,
      robots,
      maxPages: limits.maxPages,
      batchSize: limits.batchSize,
      timeoutMs: limits.timeoutMs,
      crawlWarnings,
    });

    const brokenLinks = limits.checkBrokenLinks
      ? detectBrokenInternalLinks(crawlResult.pages)
      : [];

    const rawFindings = analyzePages({
      pages: crawlResult.pages,
      brokenLinks,
      domain,
      business_name,
      business_type,
      city,
    });

    const groupedFindings = groupAndPrioritizeFindings(rawFindings);
    const healthScore = calculateHealthScore(groupedFindings);

    const competitorResults = mergeCompetitorResults({
      own_url: normalizedUrl,
      manual: providedCompetitors,
      discovered: discoveredCompetitors,
    });

    const siteSummary = buildSiteSummary({
      pages: crawlResult.pages,
      rawFindings,
      groupedFindings,
      scanMode,
      sitemapUrls,
      discoveredCompetitors,
      brokenLinks,
      robots,
    });

    return Response.json({
      success: true,
      scan_mode: scanMode,
      website_url,
      normalized_url: normalizedUrl,
      domain,
      pages_crawled: crawlResult.pages.length,
      pages_found: crawlResult.pagesFound,
      queued_remaining: crawlResult.queuedRemaining,
      health_score: healthScore,
      crawled_pages: crawlResult.pages,
      raw_findings: rawFindings,
      grouped_findings: groupedFindings,
      broken_links: brokenLinks,
      discovered_competitors: discoveredCompetitors,
      created_competitors: createdCompetitors,
      competitor_results: competitorResults,
      competitor_urls,
      crawl_job_id,
      site_summary: siteSummary,
      crawl_warnings: crawlWarnings,
      html_only_scan: true,
      javascript_rendering_used: false,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Advanced scan failed",
      },
      { status: 500 }
    );
  }
});

async function crawlWebsite({
  startUrl,
  domain,
  sitemapUrls = [],
  robots,
  maxPages,
  batchSize,
  timeoutMs,
  crawlWarnings,
}) {
  const queue = [];
  const seen = new Set();
  const queued = new Set();
  const failed = [];
  const pages = [];

  const addToQueue = (url, source = "link") => {
    const clean = canonicalizeUrl(url);

    if (!clean) return false;
    if (seen.has(clean)) return false;
    if (queued.has(clean)) return false;
    if (!isSameDomain(clean, domain)) return false;
    if (isAssetUrl(clean)) return false;
    if (isUtilityUrl(clean)) return false;
    if (isBlockedByRobots(clean, robots)) return false;

    queued.add(clean);

    queue.push({
      url: clean,
      source,
      priority: priorityScore(clean),
    });

    queue.sort((a, b) => b.priority - a.priority);

    return true;
  };

  addToQueue(startUrl, "start");

  for (const url of sitemapUrls || []) {
    addToQueue(url, "sitemap");
  }

  while (queue.length > 0 && pages.length < maxPages) {
    const batchItems = queue.splice(0, batchSize);

    for (const item of batchItems) {
      queued.delete(item.url);
    }

    const results = await Promise.allSettled(
      batchItems.map((item) =>
        fetchAndExtractPage(item.url, domain, timeoutMs, item.source)
      )
    );

    for (const result of results) {
      if (pages.length >= maxPages) break;

      if (result.status !== "fulfilled") {
        failed.push({ url: "", error: "Fetch promise failed" });
        continue;
      }

      const page = result.value;
      const pageUrl = canonicalizeUrl(page.url || page.final_url || page.original_url);

      if (!pageUrl) continue;
      if (seen.has(pageUrl)) continue;

      seen.add(pageUrl);
      pages.push(page);

      if (page.fetch_error) {
        failed.push({
          url: pageUrl,
          error: page.fetch_error,
        });
      }

      if (page.status_code >= 200 && page.status_code < 400) {
        for (const link of page.internal_links || []) {
          addToQueue(link, "internal");
        }
      }
    }
  }

  if (failed.length > 0) {
    crawlWarnings.push(
      `${failed.length} page${failed.length === 1 ? "" : "s"} could not be fully read.`
    );
  }

  if (pages.length >= maxPages) {
    crawlWarnings.push(
      `Scan limit reached at ${maxPages} pages. A larger scan may find more pages.`
    );
  }

  return {
    pages,
    pagesFound: pages.length + queue.length,
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

    const html = await response.text();

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

  const title = cleanText(
    decodeHtml(matchFirst(html, /<title[^>]*>([\s\S]*?)<\/title>/i))
  );

  const metaDescription = cleanText(
    decodeHtml(
      getMetaContent(html, "description") ||
        getMetaProperty(html, "og:description") ||
        getMetaName(html, "twitter:description")
    )
  );

  const h1 = cleanText(
    decodeHtml(matchFirst(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i))
  );

  const canonicalRaw =
    matchFirst(
      html,
      /<link[^>]+rel=["'][^"']*canonical[^"']*["'][^>]*href=["']([^"']+)["'][^>]*>/i
    ) ||
    matchFirst(
      html,
      /<link[^>]+href=["']([^"']+)["'][^>]*rel=["'][^"']*canonical[^"']*["'][^>]*>/i
    ) ||
    "";

  const canonicalUrl = absolutizeUrl(canonicalRaw, url);

  const robotsMeta =
    getMetaContent(html, "robots") ||
    getMetaContent(html, "googlebot") ||
    "";

  const pageText = extractVisibleText(html);
  const wordCount = countWords(pageText);

  const headings = extractHeadings(html);
  const links = extractLinks(html, url);

  const internalLinks = links.filter((link) => isSameDomain(link, domain));
  const externalLinks = links.filter((link) => !isSameDomain(link, domain));
  const images = extractImages(html, url);
  const faqQuestions = extractQuestions(pageText);
  const schemaTypes = detectSchemaTypes(html);
  const trustSignals = detectTrustSignals(pageText);
  const ctaPhrases = detectCtas(pageText);
  const placeholderText = detectPlaceholderText(pageText);
  const path = getPath(normalizedUrl || url);

  return {
    url: normalizedUrl,
    original_url: originalNormalized || originalUrl,
    final_url: normalizedUrl,
    crawl_source: source,
    status_code: status,
    content_type: contentType,
    redirected: Boolean(originalNormalized && originalNormalized !== normalizedUrl),
    title,
    meta_description: metaDescription,
    h1,
    h2s: headings.h2s,
    h3s: headings.h3s,
    canonical_url: canonicalUrl,
    robots_meta: robotsMeta,
    noindex: /noindex/i.test(robotsMeta),
    nofollow: /nofollow/i.test(robotsMeta),
    word_count: wordCount,
    visible_text_sample: pageText.slice(0, 2000),
    internal_links: Array.from(new Set(internalLinks)).slice(0, 500),
    external_links: Array.from(new Set(externalLinks)).slice(0, 200),
    images,
    image_count: images.length,
    images_missing_alt_count: images.filter((img) => !img.has_alt).length,
    has_faq:
      faqQuestions.length >= 2 ||
      /frequently asked questions|faqs|\bfaq\b/i.test(pageText),
    faq_questions: faqQuestions,
    has_schema:
      schemaTypes.length > 0 ||
      /application\/ld\+json|schema\.org/i.test(html),
    schema_types: schemaTypes,
    has_phone: /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.test(pageText),
    has_email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(pageText),
    cta_phrases: ctaPhrases,
    trust_signals: trustSignals,
    placeholder_text: placeholderText,
    is_utility_page: isUtilityPath(path),
    is_important_page: isImportantPage(path, title, h1),
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
    meta_description: "",
    h1: "",
    h2s: [],
    h3s: [],
    canonical_url: "",
    robots_meta: "",
    noindex: false,
    nofollow: false,
    word_count: 0,
    visible_text_sample: "",
    internal_links: [],
    external_links: [],
    images: [],
    image_count: 0,
    images_missing_alt_count: 0,
    has_faq: false,
    faq_questions: [],
    has_schema: false,
    schema_types: [],
    has_phone: false,
    has_email: false,
    cta_phrases: [],
    trust_signals: [],
    placeholder_text: [],
    is_utility_page: isUtilityPath(path),
    is_important_page: isImportantPage(path, "", ""),
    fetch_error: error,
  };
}

function analyzePages({
  pages,
  brokenLinks,
  business_name,
  business_type,
  city,
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

    if (!page.h1) {
      missingHeadingPages.push(page);
    }

    if (page.noindex) {
      noindexPages.push(page);
    }

    if (!page.canonical_url) {
      canonicalPages.push(page);
    }

    if (page.word_count < 300) {
      thinPages.push(page);
    }

    if (page.placeholder_text?.length > 0) {
      placeholderPages.push({
        page: path,
        hits: page.placeholder_text,
      });
    }

    if (!page.has_faq) {
      faqGapPages.push(page);
    }

    if (!page.cta_phrases || page.cta_phrases.length === 0) {
      ctaGapPages.push(page);
    }

    if (!page.trust_signals || page.trust_signals.length === 0) {
      trustGapPages.push(page);
    }

    if (
      page.image_count >= 5 &&
      page.images_missing_alt_count > 0 &&
      page.images_missing_alt_count / page.image_count > 0.5
    ) {
      imageAltPages.push(page);
    }
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
    const examples = weakTitlePages.slice(0, 10);

    findings.push(
      groupedFinding({
        id: "weak-search-titles",
        category: "meta_title",
        customer_category: "Search appearance",
        title:
          weakTitlePages.length === 1
            ? "Improve this page’s search title"
            : "Improve search titles on important pages",
        explanation:
          "Some important pages may need clearer search titles.",
        why:
          "Clear search titles help people understand what each page is about before they click.",
        recommendation:
          examples.length === 1
            ? suggestSearchTitle(
                examples[0],
                business_name,
                business_type,
                city
              )
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
    const examples = missingDescriptionPages.slice(0, 10);

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
        explanation:
          "Some important pages may not have a clear main heading.",
        why:
          "A clear heading helps visitors quickly understand what a page is about.",
        recommendation:
          "Add one clear main heading to each affected page.",
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
          examples: thinPages.slice(0, 10).map((p) => ({
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
        title: "Important numbers may not be showing correctly to search engines",
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
          examples: placeholderPages.slice(0, 10),
          technical_term: "placeholder text",
        },
      })
    );
  }

  if (faqGapPages.length > 0 && faqGapPages.length <= 20) {
    findings.push(
      groupedFinding({
        id: "faq-gaps",
        category: "faq_gap",
        customer_category: "Page content",
        title: "Add answers to common customer questions",
        explanation:
          "Some important pages do not appear to answer common customer questions.",
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

  if (ctaGapPages.length > 0 && ctaGapPages.length <= 20) {
    findings.push(
      groupedFinding({
        id: "cta-gaps",
        category: "cta_gap",
        customer_category: "Page content",
        title: "Add clearer next steps on important pages",
        explanation:
          "Some important pages may not clearly tell visitors what to do next.",
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

  if (trustGapPages.length > 0 && trustGapPages.length <= 20) {
    findings.push(
      groupedFinding({
        id: "trust-signal-gaps",
        category: "trust_signal_gap",
        customer_category: "Trust signals",
        title: "Add more trust signals to important pages",
        explanation:
          "Some important pages may not show enough proof that visitors can trust the business.",
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
          examples: imageAltPages.slice(0, 10).map((p) => ({
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
          examples: brokenLinks.slice(0, 20),
        },
      })
    );
  }

  findings.push(...detectDuplicateTitles(pages));
  findings.push(...detectDuplicateDescriptions(pages));

  return dedupeFindings(findings);
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
    affected_pages: Array.from(new Set(affected_pages || [])).slice(0, 100),
    details,
    confidence_score: 90,
  };
}

function groupAndPrioritizeFindings(findings) {
  const priorityOrder = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };

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

      return aStatus - bStatus;
    })
    .slice(0, 25);
}

function detectDuplicateTitles(pages) {
  const map = new Map();
  const findings = [];

  for (const page of pages) {
    if (!page.title) continue;
    if (!page.is_important_page) continue;
    if (page.is_utility_page) continue;

    const key = page.title.trim().toLowerCase();

    if (!map.has(key)) map.set(key, []);
    map.get(key).push(getPath(page.url));
  }

  for (const [title, affectedPages] of map.entries()) {
    if (affectedPages.length <= 1) continue;

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
        affected_pages: affectedPages,
        details: {
          affected_count: affectedPages.length,
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

  for (const page of pages) {
    if (!page.meta_description) continue;
    if (!page.is_important_page) continue;
    if (page.is_utility_page) continue;

    const key = page.meta_description.trim().toLowerCase();

    if (!map.has(key)) map.set(key, []);
    map.get(key).push(getPath(page.url));
  }

  for (const [description, affectedPages] of map.entries()) {
    if (affectedPages.length <= 1) continue;

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
        affected_pages: affectedPages,
        details: {
          affected_count: affectedPages.length,
          technical_term: "duplicate meta description",
        },
      })
    );
  }

  return findings;
}

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
      return {
        found: false,
        disallow: [],
        sitemaps: [],
      };
    }

    const text = await response.text();
    return parseRobotsTxt(text);
  } catch {
    warnings.push("Could not read robots.txt.");
    return {
      found: false,
      disallow: [],
      sitemaps: [],
    };
  }
}

function parseRobotsTxt(text) {
  const lines = String(text || "").split(/\r?\n/);
  const disallow = [];
  const sitemaps = [];

  for (const rawLine of lines) {
    const line = rawLine.split("#")[0].trim();

    if (!line) continue;

    const [keyRaw, ...valueParts] = line.split(":");
    const key = String(keyRaw || "").trim().toLowerCase();
    const value = valueParts.join(":").trim();

    if (key === "disallow" && value && value !== "/") {
      disallow.push(value);
    }

    if (key === "sitemap" && value) {
      sitemaps.push(value);
    }
  }

  return {
    found: true,
    disallow,
    sitemaps,
  };
}

function isBlockedByRobots(url, robots) {
  if (!robots?.disallow?.length) return false;

  const path = getPath(url);

  return robots.disallow.some((rule) => {
    if (!rule || rule === "/") return false;
    return path.startsWith(rule);
  });
}

async function discoverSitemapUrls(origin, domain, robots, warnings) {
  const sitemapUrls = [];

  const candidates = [
    ...(robots?.sitemaps || []),
    `${origin}/sitemap.xml`,
    `${origin}/sitemap_index.xml`,
    `${origin}/wp-sitemap.xml`,
    `${origin}/page-sitemap.xml`,
  ];

  for (const sitemapUrl of Array.from(new Set(candidates))) {
    try {
      const urls = await readSitemap(sitemapUrl, domain, warnings, 0);
      sitemapUrls.push(...urls);
    } catch {
      warnings.push(`Could not read sitemap: ${sitemapUrl}`);
    }
  }

  return Array.from(new Set(sitemapUrls)).slice(0, 1000);
}

async function readSitemap(sitemapUrl, domain, warnings, depth) {
  if (depth > 2) return [];

  const response = await withTimeout(
    fetch(sitemapUrl, {
      headers: {
        "user-agent": USER_AGENT,
        accept: "application/xml,text/xml,*/*",
      },
    }),
    7000,
    "Sitemap fetch"
  );

  if (!response.ok) return [];

  const xml = await response.text();
  const urls = extractUrlsFromSitemap(xml);

  const sitemapChildren = urls.filter((url) => /sitemap/i.test(url));
  const pageUrls = urls.filter(
    (url) =>
      isSameDomain(url, domain) &&
      !isAssetUrl(url) &&
      !/sitemap/i.test(url)
  );

  for (const child of sitemapChildren.slice(0, 20)) {
    try {
      const childUrls = await readSitemap(child, domain, warnings, depth + 1);
      pageUrls.push(...childUrls);
    } catch {
      warnings.push(`Could not read nested sitemap: ${child}`);
    }
  }

  return pageUrls;
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

function detectBrokenInternalLinks(pages) {
  const statusMap = new Map();

  for (const page of pages) {
    statusMap.set(canonicalizeUrl(page.url), page.status_code);
  }

  const broken = [];

  for (const page of pages) {
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

  for (const item of items) {
    const key = `${item.source_page}|${item.broken_link}|${item.status_code}`;

    if (seen.has(key)) continue;

    seen.add(key);
    output.push(item);
  }

  return output;
}

async function discoverCompetitorsFromSearch({
  base44,
  user,
  project_id,
  website_url,
  business_name,
  business_type,
  city,
  important_keywords,
}) {
  const warnings = [];
  const googleApiKey = getOptionalSecret(GOOGLE_API_KEY_NAME);
  const googleCx = getOptionalSecret(GOOGLE_CX_NAME);

  if (!googleApiKey || !googleCx) {
    return {
      discovered_competitors: [],
      created_competitors: [],
      warnings: [
        "Automatic competitor discovery is not configured. Add GOOGLE_CUSTOM_SEARCH_API_KEY and GOOGLE_CUSTOM_SEARCH_CX.",
      ],
    };
  }

  const ownDomain = getDomain(website_url);

  const keywords = buildCompetitorKeywords({
    business_name,
    business_type,
    city,
    important_keywords,
  }).slice(0, 5);

  const results = [];

  for (const keyword of keywords) {
    try {
      const searchResults = await withTimeout(
        searchGoogle(keyword, googleApiKey, googleCx),
        5000,
        "Google search"
      );

      for (const item of searchResults) {
        const domain = getDomain(item.url);

        if (!isValidCompetitorDomain(domain, ownDomain)) continue;

        results.push({
          source: "google_custom_search",
          keyword,
          title: item.title,
          url: normalizeCompetitorUrl(item.url),
          domain,
          position: item.position,
          snippet: item.snippet,
        });
      }
    } catch {
      warnings.push(`Search failed for "${keyword}".`);
    }
  }

  const discovered = dedupeCompetitors(results).slice(0, 5);
  let createdCompetitors = [];

  if (project_id && discovered.length > 0) {
    const existing = await base44.entities.Competitor.filter({ project_id });
    const existingDomains = new Set(
      (existing || []).map((item) => getDomain(item.website_url))
    );

    const toCreate = discovered.filter(
      (item) => !existingDomains.has(item.domain)
    );

    if (toCreate.length > 0) {
      createdCompetitors = await base44.entities.Competitor.bulkCreate(
        toCreate.map((item) => ({
          project_id,
          owner_user_id: user.id,
          name: formatDomainName(item.domain),
          website_url: item.url,
          notes: `Automatically found from search results for "${item.keyword}".`,
          service_pages_count: 0,
          title_quality_score: 0,
          meta_coverage_pct: 0,
          content_depth_score: 0,
          faq_usage: false,
          schema_usage: false,
          broken_links_count: 0,
        }))
      );
    }
  }

  return {
    discovered_competitors: discovered,
    created_competitors: createdCompetitors,
    warnings,
  };
}

async function saveProvidedCompetitors({
  base44,
  user,
  project_id,
  competitor_urls,
}) {
  const urls = (competitor_urls || [])
    .map((url) => String(url || "").trim())
    .filter(Boolean);

  if (!project_id || urls.length === 0) return [];

  const existing = await base44.entities.Competitor.filter({ project_id });
  const existingDomains = new Set(
    (existing || []).map((item) => getDomain(item.website_url))
  );

  const toCreate = [];

  for (const rawUrl of urls) {
    const normalized = normalizeUrl(rawUrl);
    const domain = getDomain(normalized);

    if (!domain || existingDomains.has(domain)) continue;

    toCreate.push({
      project_id,
      owner_user_id: user.id,
      name: formatDomainName(domain),
      website_url: normalized,
      notes: "Added from Scan Website.",
      service_pages_count: 0,
      title_quality_score: 0,
      meta_coverage_pct: 0,
      content_depth_score: 0,
      faq_usage: false,
      schema_usage: false,
      broken_links_count: 0,
    });
  }

  if (toCreate.length === 0) return [];

  return await base44.entities.Competitor.bulkCreate(toCreate);
}

async function searchGoogle(keyword, googleApiKey, googleCx) {
  const url = new URL("https://www.googleapis.com/customsearch/v1");
  url.searchParams.set("key", googleApiKey);
  url.searchParams.set("cx", googleCx);
  url.searchParams.set("q", keyword);
  url.searchParams.set("num", "5");

  const response = await fetch(url.toString(), {
    headers: {
      accept: "application/json",
      "user-agent": USER_AGENT,
    },
  });

  if (!response.ok) {
    throw new Error(`Google search failed: ${response.status}`);
  }

  const data = await response.json();
  const items = Array.isArray(data.items) ? data.items : [];

  return items.map((item, index) => ({
    title: item.title || "",
    url: item.link || "",
    snippet: item.snippet || "",
    position: index + 1,
  }));
}

function buildCompetitorKeywords({
  business_name,
  business_type,
  city,
  important_keywords,
}) {
  const keywords = [];

  for (const keyword of important_keywords || []) {
    const clean = String(keyword || "").trim();

    if (clean) keywords.push(clean);
  }

  const type = String(business_type || "").trim();
  const place = String(city || "").trim();

  if (type && place) keywords.push(`${type} ${place}`);
  if (type) keywords.push(`${type} near me`);
  if (type && place) keywords.push(`best ${type} ${place}`);

  if (/loan|lender|mortgage|financ/i.test(type)) {
    if (place) {
      keywords.push(`fix and flip loans ${place}`);
      keywords.push(`bridge loans ${place}`);
      keywords.push(`hard money lender ${place}`);
      keywords.push(`new construction loans ${place}`);
    } else {
      keywords.push("fix and flip loans");
      keywords.push("bridge loans");
      keywords.push("hard money lender");
      keywords.push("new construction loans");
    }
  }

  if (business_name && type) keywords.push(`${type} companies`);

  return Array.from(new Set(keywords)).filter(Boolean);
}

function mergeCompetitorResults({ own_url, manual, discovered }) {
  const ownDomain = getDomain(own_url);
  const map = new Map();

  for (const item of [...(manual || []), ...(discovered || [])]) {
    const website_url = item.website_url || item.url || "";
    const domain = item.domain || getDomain(website_url);

    if (!isValidCompetitorDomain(domain, ownDomain)) continue;

    if (!map.has(domain)) {
      map.set(domain, {
        name: item.name || formatDomainName(domain),
        website_url,
        url: website_url,
        domain,
        source: item.source || "manual",
        keyword: item.keyword || "",
        title: item.title || "",
        snippet: item.snippet || "",
        position: item.position || null,
      });
    }
  }

  return Array.from(map.values()).slice(0, 8);
}

function dedupeCompetitors(results) {
  const map = new Map();

  for (const result of results) {
    if (!result.domain) continue;

    const existing = map.get(result.domain);

    if (!existing) {
      map.set(result.domain, {
        ...result,
        appearances: 1,
        best_position: result.position || 99,
      });
    } else {
      existing.appearances += 1;
      existing.best_position = Math.min(
        existing.best_position,
        result.position || 99
      );
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    if (b.appearances !== a.appearances) return b.appearances - a.appearances;
    return a.best_position - b.best_position;
  });
}

function isValidCompetitorDomain(domain, ownDomain) {
  if (!domain) return false;
  if (domain === ownDomain) return false;
  if (domain.endsWith(`.${ownDomain}`)) return false;

  return !EXCLUDED_COMPETITOR_DOMAINS.some(
    (blocked) => domain === blocked || domain.endsWith(`.${blocked}`)
  );
}

function buildSiteSummary({
  pages,
  rawFindings,
  groupedFindings,
  scanMode,
  sitemapUrls,
  discoveredCompetitors,
  brokenLinks,
  robots,
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

  return {
    positives,
    raw_findings_count: rawFindings.length,
    total_findings: groupedFindings.length,
    important_pages_found: importantPages.length,
    pages_with_faq: pagesWithFaq.length,
    pages_with_trust_signals: pagesWithTrust.length,
    pages_with_calls_to_action: pagesWithCta.length,
    pages_with_schema: pagesWithSchema.length,
    noindex_pages: noindexPages.length,
    scan_mode: scanMode,
    sitemap_urls_found: sitemapUrls.length,
    robots_txt_found: Boolean(robots?.found),
    discovered_competitor_count: discoveredCompetitors.length,
    broken_links_count: brokenLinks.length,
    html_only_scan: true,
    javascript_rendering_used: false,
  };
}

function calculateHealthScore(findings) {
  let score = 94;

  for (const finding of findings) {
    if (finding.priority === "critical") {
      score -= 9;
    } else if (finding.priority === "high") {
      score -= 6;
    } else if (finding.priority === "medium") {
      score -= 4;
    } else {
      score -= 1;
    }
  }

  return Math.max(45, Math.min(100, score));
}

function priorityScore(url) {
  const path = getPath(url).toLowerCase();

  if (path === "/") return 100;
  if (/service|services|loan|loans|program|programs|product|products/i.test(path)) return 95;
  if (/location|locations|areas-we-serve|city/i.test(path)) return 85;
  if (/about|contact|pricing|book|appointment|apply/i.test(path)) return 75;
  if (/case-study|case-studies|portfolio|projects/i.test(path)) return 65;
  if (/blog|article|news|resources/i.test(path)) return 35;

  return 50;
}

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
    const url = /^https?:\/\//i.test(input) ? input : `https://${input}`;
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
  return ASSET_RE.test(input);
}

function isUtilityUrl(input) {
  return isUtilityPath(getPath(input));
}

function isUtilityPath(path) {
  return UTILITY_PATH_RE.test(path);
}

function isImportantPage(path, title = "", h1 = "") {
  return IMPORTANT_PAGE_RE.test(`${path}|${title}|${h1}`);
}

function extractVisibleText(html) {
  return cleanText(
    decodeHtml(
      html
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

  while ((match = re.exec(html)) !== null) {
    const href = match[1];

    if (!href) continue;
    if (href.startsWith("#")) continue;
    if (/^(mailto:|tel:|sms:|javascript:)/i.test(href)) continue;

    const absolute = absolutizeUrl(href, baseUrl);

    if (absolute && !isAssetUrl(absolute)) {
      links.push(absolute);
    }
  }

  return Array.from(new Set(links));
}

function extractHeadings(html) {
  return {
    h2s: matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi).slice(0, 50),
    h3s: matchAllClean(html, /<h3[^>]*>([\s\S]*?)<\/h3>/gi).slice(0, 80),
  };
}

function extractImages(html, baseUrl = "") {
  const images = [];
  const re = /<img[^>]*>/gi;
  let match;

  while ((match = re.exec(html)) !== null) {
    const tag = match[0];

    const src =
      matchFirst(tag, /src=["']([^"']+)["']/i) ||
      matchFirst(tag, /data-src=["']([^"']+)["']/i) ||
      matchFirst(tag, /data-lazy-src=["']([^"']+)["']/i) ||
      "";

    const alt = cleanText(
      decodeHtml(matchFirst(tag, /alt=["']([^"']*)["']/i))
    );

    images.push({
      src: src ? absolutizeUrl(src, baseUrl) : "",
      alt,
      has_alt: Boolean(alt),
    });
  }

  return images.slice(0, 200);
}

function extractQuestions(text) {
  return text
    .split(/(?<=[?.!])\s+/)
    .map(cleanText)
    .filter((line) => line.endsWith("?"))
    .slice(0, 30);
}

function detectSchemaTypes(html) {
  const types = [];

  const jsonLdBlocks = matchAllRaw(
    html,
    /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi
  );

  for (const block of jsonLdBlocks) {
    const matches = block.match(/"@type"\s*:\s*"([^"]+)"/gi) || [];

    for (const item of matches) {
      const type = item
        .replace(/"@type"\s*:\s*"/i, "")
        .replace(/"/g, "")
        .trim();

      if (type) types.push(type);
    }
  }

  if (/schema\.org\/LocalBusiness/i.test(html)) types.push("LocalBusiness");
  if (/schema\.org\/FAQPage/i.test(html)) types.push("FAQPage");
  if (/schema\.org\/Organization/i.test(html)) types.push("Organization");
  if (/schema\.org\/Product/i.test(html)) types.push("Product");
  if (/schema\.org\/Service/i.test(html)) types.push("Service");
  if (/schema\.org\/Review/i.test(html)) types.push("Review");

  return Array.from(new Set(types));
}

function detectTrustSignals(text) {
  const lower = text.toLowerCase();

  const signals = [
    "reviews",
    "testimonials",
    "case study",
    "case studies",
    "years in business",
    "licensed",
    "certified",
    "award",
    "guarantee",
    "trusted",
    "rated",
    "stars",
    "projects",
    "clients",
    "customers",
    "funded",
    "insured",
    "google reviews",
    "bbb",
    "five star",
    "5-star",
    "verified",
    "accredited",
    "in-house",
  ];

  return signals.filter((signal) => lower.includes(signal));
}

function detectCtas(text) {
  const lower = text.toLowerCase();

  const ctas = [
    "contact us",
    "call now",
    "get started",
    "request a quote",
    "book now",
    "schedule",
    "apply now",
    "start application",
    "learn more",
    "get a free",
    "free consultation",
    "talk to",
    "speak with",
    "request funding",
    "apply online",
    "get approved",
  ];

  return ctas.filter((cta) => lower.includes(cta));
}

function detectPlaceholderText(text) {
  const patterns = [
    [/\bgvar\+?\b/i, "gvar"],
    [/\bundefined\b/i, "undefined"],
    [/\bnull\b/i, "null"],
    [/\bNaN\b/i, "NaN"],
    [/\[object Object\]/i, "[object Object]"],
    [/\{\{[^}]*\}\}/i, "{{ }}"],
    [/lorem ipsum/i, "lorem ipsum"],
    [/\bplaceholder\b/i, "placeholder"],
  ];

  return patterns.filter(([re]) => re.test(text)).map(([, label]) => label);
}

function suggestSearchTitle(page, businessName, businessType, city) {
  const path = getPath(page.url);

  if (path === "/") {
    return clamp(
      [businessName, businessType, city].filter(Boolean).join(" | "),
      65
    );
  }

  const pageName =
    path
      .split("/")
      .filter(Boolean)
      .pop()
      ?.replace(/[-_]/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase()) || "Page";

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

  return output;
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
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function countWords(text) {
  const cleaned = cleanText(text);
  if (!cleaned) return 0;

  return cleaned.split(/\s+/).filter(Boolean).length;
}

function dedupeFindings(findings) {
  const seen = new Set();
  const output = [];

  for (const finding of findings) {
    const key = [
      finding.type || "",
      finding.category || "",
      finding.issue_title || "",
      JSON.stringify(finding.affected_pages || []),
    ]
      .join("|")
      .toLowerCase();

    if (seen.has(key)) continue;

    seen.add(key);
    output.push(finding);
  }

  return output;
}

function stableId(input) {
  let hash = 0;

  for (let i = 0; i < String(input).length; i++) {
    hash = (hash << 5) - hash + String(input).charCodeAt(i);
    hash |= 0;
  }

  return `finding_${Math.abs(hash)}`;
}

function getOptionalSecret(name) {
  try {
    return Deno.env.get(name) || "";
  } catch {
    return "";
  }
}

function formatDomainName(domain) {
  return String(domain || "")
    .replace(/\.(com|net|org|co|io|us)$/i, "")
    .split(/[.-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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