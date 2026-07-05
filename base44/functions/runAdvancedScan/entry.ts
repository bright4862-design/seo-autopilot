import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GOOGLE_API_KEY_NAME = "GOOGLE_" + "CUSTOM_SEARCH_API_KEY";
const GOOGLE_CX_NAME = "GOOGLE_" + "CUSTOM_SEARCH_CX";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/1.0; +https://seoautopilot.app/bot)";

const SCAN_LIMITS = {
  quick: {
    maxPages: 50,
    batchSize: 5,
    timeoutMs: 12000,
    useSitemap: false,
    discoverCompetitors: false,
  },
  deep: {
    maxPages: 200,
    batchSize: 4,
    timeoutMs: 18000,
    useSitemap: true,
    discoverCompetitors: true,
  },
};

function priorityScore(url) {
  const path = getPath(url).toLowerCase();

  if (path === "/") return 100;
  if (/service|services|loan|loans|program|programs|product|products/i.test(path)) return 90;
  if (/location|locations|areas-we-serve|city/i.test(path)) return 80;
  if (/about|contact|pricing|book|appointment|apply/i.test(path)) return 70;
  if (/blog|article|news|resources/i.test(path)) return 35;

  return 50;
}

const UTILITY_PATH_RE =
  /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer|tag|category|author)/i;

const IMPORTANT_PAGE_RE =
  /(^\/$)|(home|service|services|product|products|loan|loans|program|programs|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve|fix-and-flip|new-construction|bridge|rental|dscr)/i;

const ASSET_RE =
  /\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff|woff2|ttf|mp4|mp3|mov|avi)$/i;

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

    let discoveredCompetitors = [];
    let createdCompetitors = [];

    const providedCompetitors = await saveProvidedCompetitors({
      base44,
      user,
      project_id,
      competitor_urls,
    });

    createdCompetitors.push(...providedCompetitors);

    if (scanMode === "deep" && limits.discoverCompetitors) {
      try {
        const discovery = await discoverCompetitorsFromSearch({
          base44,
          user,
          project_id,
          website_url: normalizedUrl,
          business_name,
          business_type,
          city,
          important_keywords,
        });

        discoveredCompetitors = discovery.discovered_competitors || [];
        createdCompetitors = discovery.created_competitors || [];

        if (discovery.warnings?.length) {
          crawlWarnings.push(...discovery.warnings);
        }
      } catch (error) {
        crawlWarnings.push(
          `Competitor discovery was skipped: ${error?.message || "Unknown error"}`
        );
      }
    }

    const sitemapUrls =
      scanMode === "deep" && limits.useSitemap
        ? await discoverSitemapUrls(origin, domain, crawlWarnings)
        : [];

    const crawlResult = await crawlWebsite({
      startUrl: normalizedUrl,
      domain,
      sitemapUrls,
      maxPages: limits.maxPages,
      batchSize: limits.batchSize,
      timeoutMs: limits.timeoutMs,
      crawlWarnings,
    });

    const rawFindings = analyzePages({
      pages: crawlResult.pages,
      domain,
      business_name,
      business_type,
      city,
    });

    const groupedFindings = groupFindings(rawFindings);
    const brokenLinks = detectBrokenInternalLinks(crawlResult.pages);
    const healthScore = calculateHealthScore(groupedFindings);

    const siteSummary = buildSiteSummary({
      pages: crawlResult.pages,
      findings: groupedFindings,
      scanMode,
      sitemapUrls,
      discoveredCompetitors,
    });

    return Response.json({
      success: true,
      scan_mode: scanMode,
      website_url,
      normalized_url: normalizedUrl,
      domain,
      pages_crawled: crawlResult.pages.length,
      pages_found: crawlResult.pagesFound,
      health_score: healthScore,
      crawled_pages: crawlResult.pages,
      raw_findings: rawFindings,
      grouped_findings: groupedFindings,
      broken_links: brokenLinks,
      discovered_competitors: discoveredCompetitors,
      created_competitors: createdCompetitors,
      competitor_results: [...createdCompetitors, ...discoveredCompetitors],
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
        failed.push({
          url: "",
          error: "Fetch promise failed",
        });
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
        const links = Array.isArray(page.internal_links) ? page.internal_links : [];

        for (const link of links) {
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
      `Scan limit reached at ${maxPages} pages. A deeper scan may find more pages.`
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

  const path = getPath(url);

  return {
    url: normalizedUrl,
    original_url: originalNormalized || originalUrl,
    final_url: normalizedUrl,
    crawl_source: source,
    status_code: status,
    content_type: contentType,
    redirected: originalNormalized && originalNormalized !== normalizedUrl,
    title,
    meta_description: metaDescription,
    h1,
    h2s: headings.h2s,
    h3s: headings.h3s,
    canonical_url: canonicalUrl,
    robots_meta: robotsMeta,
    word_count: wordCount,
    visible_text_sample: pageText.slice(0, 1500),
    internal_links: Array.from(new Set(internalLinks)).slice(0, 300),
    external_links: Array.from(new Set(externalLinks)).slice(0, 150),
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

function analyzePages({ pages, business_name, business_type, city }) {
  const findings = [];
  const canonicalPages = [];
  const placeholderPages = [];

  for (const page of pages) {
    const path = getPath(page.url);
    const isUtility = page.is_utility_page || isUtilityPath(path);
    const isImportant = page.is_important_page || isImportantPage(path, page.title, page.h1);

    if (page.status_code === 0 || page.status_code >= 400) {
      findings.push(
        finding({
          page,
          category: "broken_page",
          customerCategory: "Broken page",
          title: "This page may not be loading correctly",
          explanation:
            "We could not access this page successfully during the scan.",
          why:
            "Broken pages can frustrate visitors and make it harder for search engines to understand your website.",
          recommendation:
            "Ask your website editor or developer to review this page and fix the link or page setup.",
          current: `Status: ${page.status_code}`,
          priority: "high",
          status: "needs_developer",
          difficulty: "developer",
        })
      );

      continue;
    }

    if (isUtility) continue;

    if (!page.title) {
      findings.push(
        finding({
          page,
          category: "meta_title",
          customerCategory: "Search title",
          title: "Add a clear search title",
          explanation:
            "This page does not appear to have a clear title for search results.",
          why:
            "A clear search title helps people understand what the page is about before they click.",
          recommendation: suggestSearchTitle(page, business_name, business_type, city),
          current: "Not found",
          priority: "high",
          status: "auto_fixed",
          difficulty: "easy",
        })
      );
    } else if ((page.title.length < 20 || page.title.length > 70) && isImportant) {
      findings.push(
        finding({
          page,
          category: "meta_title",
          customerCategory: "Search title",
          title: "Improve this page’s search title",
          explanation:
            "This page has a search title, but it may be too short, too long, or unclear.",
          why:
            "A stronger search title may help people understand why this page is relevant.",
          recommendation: suggestSearchTitle(page, business_name, business_type, city),
          current: page.title,
          priority: "medium",
          status: "auto_fixed",
          difficulty: "easy",
        })
      );
    }

    if (!page.meta_description && isImportant) {
      findings.push(
        finding({
          page,
          category: "meta_description",
          customerCategory: "Search description",
          title: "Add a helpful search description",
          explanation:
            "This important page does not appear to have a clear search description.",
          why:
            "A search description can help people understand what the page offers before they click.",
          recommendation: suggestSearchDescription(page, business_name, business_type, city),
          current: "Not found",
          priority: "medium",
          status: "auto_fixed",
          difficulty: "easy",
        })
      );
    }

    if (!page.h1 && isImportant) {
      findings.push(
        finding({
          page,
          category: "page_heading",
          customerCategory: "Page heading",
          title: "Add a clear main heading",
          explanation:
            "This important page may not have a clear main heading.",
          why:
            "A clear heading helps visitors quickly understand what the page is about.",
          recommendation:
            "Add one clear main heading that describes the service or topic of the page.",
          current: "Not found",
          priority: "medium",
          status: "needs_approval",
          difficulty: "moderate",
        })
      );
    }

    if (!page.canonical_url && isImportant) {
      canonicalPages.push(path);
    }

    if (page.word_count < 300 && isImportant) {
      findings.push(
        finding({
          page,
          category: "thin_content",
          customerCategory: "Page content",
          title: "Add more helpful content to this page",
          explanation:
            "This important page may not have enough helpful content for visitors.",
          why:
            "Helpful pages usually explain the service, benefits, common questions, proof points, and next steps.",
          recommendation:
            "Add clearer service details, benefits, customer questions, proof points, and a stronger next step.",
          current: `${page.word_count} words found`,
          priority: "medium",
          status: "needs_developer",
          difficulty: "moderate",
        })
      );
    }

    if (page.placeholder_text?.length > 0 && isImportant) {
      placeholderPages.push({
        page: path,
        hits: page.placeholder_text,
      });
    }

    if (isImportant && !page.has_faq) {
      findings.push(
        finding({
          page,
          category: "faq_gap",
          customerCategory: "Page content",
          title: "Add answers to common customer questions",
          explanation:
            "This important page does not appear to answer common customer questions.",
          why:
            "Question-and-answer sections can help visitors make decisions and understand your services.",
          recommendation:
            "Add 4–6 common questions and answers that customers usually ask before contacting you.",
          current: "No clear question-and-answer section found",
          priority: "low",
          status: "needs_developer",
          difficulty: "moderate",
        })
      );
    }

    if (isImportant && page.cta_phrases.length === 0) {
      findings.push(
        finding({
          page,
          category: "cta_gap",
          customerCategory: "Page content",
          title: "Add a clearer next step",
          explanation:
            "This page may not clearly tell visitors what to do next.",
          why:
            "A clear next step can help more visitors contact you, book, apply, or request help.",
          recommendation:
            "Add a simple next step such as “Contact us,” “Request a quote,” “Book a call,” or “Apply now.”",
          current: "No strong next step found",
          priority: "medium",
          status: "needs_developer",
          difficulty: "moderate",
        })
      );
    }

    if (isImportant && page.trust_signals.length === 0) {
      findings.push(
        finding({
          page,
          category: "trust_signal_gap",
          customerCategory: "Trust signals",
          title: "Add more trust signals",
          explanation:
            "This important page may not show enough proof that visitors can trust the business.",
          why:
            "Reviews, testimonials, project examples, credentials, and proof points can help visitors feel more confident.",
          recommendation:
            "Add reviews, testimonials, proof numbers, case studies, certifications, or project examples where appropriate.",
          current: "No clear trust signals found",
          priority: "medium",
          status: "needs_developer",
          difficulty: "moderate",
        })
      );
    }

    if (
      isImportant &&
      page.image_count >= 5 &&
      page.images_missing_alt_count / page.image_count > 0.5
    ) {
      findings.push(
        finding({
          page,
          category: "image_alt_text",
          customerCategory: "Images",
          title: "Improve image descriptions",
          explanation:
            "Several images on this page may not have helpful descriptions.",
          why:
            "Image descriptions can help accessibility and give search engines more context.",
          recommendation:
            "Add short, useful descriptions to important images on this page.",
          current: `${page.images_missing_alt_count} of ${page.image_count} images may be missing descriptions`,
          priority: "low",
          status: "needs_developer",
          difficulty: "moderate",
        })
      );
    }
  }

  if (placeholderPages.length > 0) {
    findings.push({
      id: stableId("placeholder-text-group"),
      type: "site_level",
      page_url: placeholderPages[0].page,
      category: "placeholder_text",
      customer_category: "Website setup",
      issue_title: "Important content may not be showing correctly",
      plain_english_explanation:
        "We found placeholder-like text where important business proof or page content may belong.",
      why_it_matters:
        "Important proof points, service details, and trust signals should be easy for search engines and visitors to understand.",
      current_value:
        "Affected pages: " +
        placeholderPages.map((p) => `${p.page} (${p.hits.join(", ")})`).join(" · "),
      recommended_value:
        "Make sure the real text and numbers appear directly in the page content.",
      ai_recommendation:
        "Ask a developer to make sure final text and numbers appear directly in the page content, not only through scripts or placeholders.",
      priority: "high",
      difficulty: "developer",
      status: "needs_developer",
      can_auto_fix: false,
      requires_approval: false,
      requires_developer: true,
      affected_pages: placeholderPages.map((p) => p.page),
      details: {
        technical_term: "placeholder text",
        affected_count: placeholderPages.length,
      },
      confidence_score: 90,
    });
  }

  if (canonicalPages.length >= 2) {
    findings.push({
      id: stableId("preferred-page-settings-group"),
      type: "site_level",
      page_url: canonicalPages[0],
      category: "canonical",
      customer_category: "Website setup",
      issue_title: "Review preferred-page settings across important pages",
      plain_english_explanation:
        "Several important pages may not clearly tell search engines which version of the page is preferred.",
      why_it_matters:
        "Preferred-page settings can help search engines understand the main version of important pages.",
      current_value: `${canonicalPages.length} pages may need review`,
      recommended_value:
        "Ask your website editor or developer to review preferred-page settings for these pages.",
      ai_recommendation:
        "Ask your website editor or SEO cleanup provider to review preferred-page settings across the affected pages.",
      priority: "medium",
      difficulty: "developer",
      status: "needs_developer",
      can_auto_fix: false,
      requires_approval: false,
      requires_developer: true,
      affected_pages: canonicalPages,
      details: {
        technical_term: "canonical",
        affected_count: canonicalPages.length,
      },
      confidence_score: 90,
    });
  }

  findings.push(...detectDuplicateTitles(pages));

  return dedupeFindings(findings);
}

function finding({
  page,
  category,
  customerCategory,
  title,
  explanation,
  why,
  recommendation,
  current = "",
  priority,
  status,
  difficulty,
}) {
  return {
    id: stableId(`${page.url}-${category}-${title}`),
    type: "page_level",
    page_url: getPath(page.url),
    full_url: page.url,
    category,
    customer_category: customerCategory,
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
    confidence_score: 90,
    affected_pages: [],
    details: {},
  };
}

function groupFindings(findings) {
  return dedupeFindings(findings);
}

async function saveProvidedCompetitors({ base44, user, project_id, competitor_urls }) {
  const urls = (competitor_urls || []).map((url) => String(url || "").trim()).filter(Boolean);

  if (!project_id || urls.length === 0) return [];

  try {
    await base44.entities.Competitor.deleteMany({ project_id });
  } catch {}

  return await base44.entities.Competitor.bulkCreate(
    urls.map((url) => {
      let normalizedUrl = url;
      let name = url;

      try {
        normalizedUrl = /^https?:\/\//i.test(url) ? url : `https://${url}`;
        name = new URL(normalizedUrl).hostname.replace(/^www\./, "");
      } catch {}

      return {
        project_id,
        owner_user_id: user.id,
        name,
        website_url: normalizedUrl,
        notes: "Added from Scan Website.",
        service_pages_count: 0,
        title_quality_score: 0,
        meta_coverage_pct: 0,
        content_depth_score: 0,
        faq_usage: false,
        schema_usage: false,
        broken_links_count: 0,
      };
    })
  );
}

function detectDuplicateTitles(pages) {
  const map = new Map();
  const findings = [];

  for (const page of pages) {
    const path = getPath(page.url);

    if (!page.title) continue;
    if (!page.is_important_page) continue;
    if (page.is_utility_page) continue;

    const key = page.title.trim().toLowerCase();

    if (!map.has(key)) map.set(key, []);
    map.get(key).push(path);
  }

  for (const [title, affectedPages] of map.entries()) {
    if (affectedPages.length <= 1) continue;

    findings.push({
      id: stableId(`duplicate-title-${title}`),
      type: "site_level",
      page_url: affectedPages[0],
      category: "duplicate_search_titles",
      customer_category: "Search appearance",
      issue_title: "Several important pages use the same search title",
      plain_english_explanation:
        "Multiple important pages appear to use the same search title.",
      why_it_matters:
        "Unique search titles help visitors and search engines understand the purpose of each page.",
      current_value: title,
      recommended_value: "Prepare a unique search title for each affected page.",
      ai_recommendation:
        "Review the affected pages and prepare unique search titles for each one.",
      priority: "medium",
      difficulty: "easy",
      status: "needs_approval",
      can_auto_fix: false,
      requires_approval: true,
      requires_developer: false,
      affected_pages: affectedPages,
      details: {
        technical_term: "duplicate title",
        affected_count: affectedPages.length,
      },
      confidence_score: 90,
    });
  }

  return findings;
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
      const searchResults = await searchGoogle(keyword, googleApiKey, googleCx);

      for (const item of searchResults) {
        const domain = getDomain(item.url);

        if (!isValidCompetitorDomain(domain, ownDomain)) continue;

        results.push({
          keyword,
          title: item.title,
          url: item.url,
          domain,
          position: item.position,
          snippet: item.snippet,
        });
      }
    } catch (error) {
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
    if (String(keyword || "").trim()) {
      keywords.push(String(keyword).trim());
    }
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

async function discoverSitemapUrls(origin, domain, warnings) {
  const sitemapUrls = [];

  const candidates = [
    `${origin}/sitemap.xml`,
    `${origin}/sitemap_index.xml`,
    `${origin}/wp-sitemap.xml`,
  ];

  for (const sitemapUrl of candidates) {
    try {
      const response = await fetch(sitemapUrl, {
        headers: {
          "user-agent": USER_AGENT,
          accept: "application/xml,text/xml,*/*",
        },
      });

      if (!response.ok) continue;

      const xml = await response.text();
      const urls = extractUrlsFromSitemap(xml).filter((url) =>
        isSameDomain(url, domain)
      );

      sitemapUrls.push(...urls);
    } catch {
      warnings.push(`Could not read sitemap: ${sitemapUrl}`);
    }
  }

  return Array.from(new Set(sitemapUrls)).slice(0, 200);
}

function extractUrlsFromSitemap(xml) {
  const urls = [];
  const re = /<loc>\s*([^<]+)\s*<\/loc>/gi;
  let match;

  while ((match = re.exec(xml)) !== null) {
    urls.push(match[1].trim());
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

  return broken;
}

function buildSiteSummary({
  pages,
  findings,
  scanMode,
  sitemapUrls,
  discoveredCompetitors,
}) {
  const importantPages = pages.filter((p) => p.is_important_page);
  const pagesWithFaq = pages.filter((p) => p.has_faq);
  const pagesWithTrust = pages.filter((p) => p.trust_signals?.length > 0);
  const pagesWithCta = pages.filter((p) => p.cta_phrases?.length > 0);

  const positives = [];

  if (importantPages.length >= 4) {
    positives.push("Your site has several important service or business pages.");
  }

  if (pagesWithTrust.length >= 1) {
    positives.push("Your site includes trust signals such as reviews, proof points, or testimonials.");
  }

  if (pagesWithCta.length >= 1) {
    positives.push("Your site includes calls to action that help visitors take the next step.");
  }

  if (pagesWithFaq.length >= 1) {
    positives.push("Your site answers some customer questions.");
  }

  return {
    positives,
    total_findings: findings.length,
    important_pages_found: importantPages.length,
    pages_with_faq: pagesWithFaq.length,
    pages_with_trust_signals: pagesWithTrust.length,
    pages_with_calls_to_action: pagesWithCta.length,
    scan_mode: scanMode,
    sitemap_urls_found: sitemapUrls.length,
    discovered_competitor_count: discoveredCompetitors.length,
    html_only_scan: true,
    javascript_rendering_used: false,
  };
}

function calculateHealthScore(findings) {
  let score = 100;

  for (const finding of findings) {
    if (finding.priority === "critical" || finding.priority === "high") {
      score -= 8;
    } else if (finding.priority === "medium") {
      score -= 5;
    } else {
      score -= 2;
    }
  }

  return Math.max(0, Math.min(100, score));
}

function normalizeStartUrl(input) {
  let url = String(input || "").trim();

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  return canonicalizeUrl(url);
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
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
      .replace(/<!--[\s\S]*?-->/g, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
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
    h2s: matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi).slice(0, 30),
    h3s: matchAllClean(html, /<h3[^>]*>([\s\S]*?)<\/h3>/gi).slice(0, 40),
  };
}

function extractImages(html) {
  const images = [];
  const re = /<img[^>]*>/gi;
  let match;

  while ((match = re.exec(html)) !== null) {
    const tag = match[0];
    const src = matchFirst(tag, /src=["']([^"']+)["']/i);
    const alt = matchFirst(tag, /alt=["']([^"']*)["']/i);

    images.push({
      src,
      alt: cleanText(alt),
      has_alt: Boolean(cleanText(alt)),
    });
  }

  return images.slice(0, 150);
}

function extractQuestions(text) {
  return text
    .split(/(?<=[?.!])\s+/)
    .map(cleanText)
    .filter((line) => line.endsWith("?"))
    .slice(0, 15);
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
    return clamp([businessName, businessType, city].filter(Boolean).join(" | "), 65);
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
    path.split("/").filter(Boolean).pop()?.replace(/[-_]/g, " ") || "this service";

  return clamp(
    `Learn about ${pageName} from ${name}. See key details, benefits, common questions, and how to get started.`,
    160
  );
}

function clamp(value, max) {
  const text = String(value || "").trim();

  if (text.length <= max) return text;

  return text.slice(0, max - 1).trim();
}

function decodeHtml(input) {
  return String(input || "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function getMetaContent(html, name) {
  return getMetaName(html, name);
}

function getMetaName(html, name) {
  const escaped = escapeRegExp(name);
  return (
    matchFirst(
      html,
      new RegExp(`<meta[^>]+name=["']${escaped}["'][^>]*content=["']([^"']*)["'][^>]*>`, "i")
    ) ||
    matchFirst(
      html,
      new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*name=["']${escaped}["'][^>]*>`, "i")
    )
  );
}

function getMetaProperty(html, property) {
  const escaped = escapeRegExp(property);
  return (
    matchFirst(
      html,
      new RegExp(`<meta[^>]+property=["']${escaped}["'][^>]*content=["']([^"']*)["'][^>]*>`, "i")
    ) ||
    matchFirst(
      html,
      new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*property=["']${escaped}["'][^>]*>`, "i")
    )
  );
}

function escapeRegExp(input) {
  return String(input || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function matchFirst(input, re) {
  const match = input.match(re);
  return match?.[1] || "";
}

function matchAllClean(input, re) {
  const output = [];
  let match;

  while ((match = re.exec(input)) !== null) {
    const value = cleanText(match[1]);
    if (value) output.push(value);
  }

  return output;
}

function matchAllRaw(input, re) {
  const output = [];
  let match;

  while ((match = re.exec(input)) !== null) {
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
      finding.page_url || "",
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

  for (let i = 0; i < input.length; i++) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
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
  return domain
    .replace(/\.(com|net|org|co|io|us)$/i, "")
    .split(/[.-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}