import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const MAX_PAGES = 50;
const MAX_LINKS_PER_PAGE = 120;
const BATCH_SIZE = 6;
const FETCH_TIMEOUT_MS = 12000;
const USER_AGENT = "SEO-Autopilot/1.0";

const UTILITY_PATH_PATTERNS = [
  /\/cart/i,
  /\/checkout/i,
  /\/login/i,
  /\/signin/i,
  /\/signup/i,
  /\/register/i,
  /\/account/i,
  /\/search/i,
  /\/privacy/i,
  /\/terms/i,
  /\/thank-you/i,
  /\/thankyou/i,
  /\/payment/i,
  /\/admin/i,
  /\/wp-admin/i,
  /\/reset/i,
  /\/forgot/i,
  /\/cookie/i,
  /\/legal/i,
  /\/disclaimer/i,
  /\/tag\//i,
  /\/category\//i,
  /\/author\//i,
];

const IMPORTANT_PAGE_PATTERNS = [
  /^\/$/,
  /service/i,
  /services/i,
  /product/i,
  /products/i,
  /loan/i,
  /loans/i,
  /program/i,
  /programs/i,
  /pricing/i,
  /packages/i,
  /about/i,
  /location/i,
  /locations/i,
  /area/i,
  /areas/i,
  /contact/i,
  /book/i,
  /appointment/i,
  /consultation/i,
  /repair/i,
  /installation/i,
  /menu/i,
  /treatment/i,
  /treatments/i,
];

const PLACEHOLDER_PATTERNS = [
  /\bgvar\+?\b/i,
  /\bundefined\b/i,
  /\bnull\b/i,
  /\bNaN\b/i,
  /\[object Object\]/i,
  /\{\{[^}]+\}\}/i,
  /\blorem ipsum\b/i,
  /\bplaceholder\b/i,
];

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ success: false, error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();

    const websiteUrl = body.website_url || body.url;
    const businessName = body.business_name || "";
    const businessType = body.business_type || "";
    const city = body.city || "";
    const competitors = Array.isArray(body.competitors) ? body.competitors : [];

    if (!websiteUrl) {
      return Response.json(
        { success: false, error: "website_url is required" },
        { status: 400 }
      );
    }

    const normalizedUrl = normalizeStartUrl(websiteUrl);
    const start = new URL(normalizedUrl);
    const domain = start.hostname.replace(/^www\./, "");

    const crawlResult = await crawlSite({
      startUrl: normalizedUrl,
      domain,
      maxPages: MAX_PAGES,
    });

    const rawFindings = analyzePages({
      pages: crawlResult.pages,
      domain,
      businessName,
      businessType,
      city,
    });

    const brokenLinks = detectBrokenInternalLinks(crawlResult.pages);
    const groupedFindings = groupRepeatedFindings(rawFindings);
    const siteSummary = buildSiteSummary(crawlResult.pages, groupedFindings);
    const healthScore = calculateHealthScore(groupedFindings);

    return Response.json({
      success: true,
      website_url: websiteUrl,
      normalized_url: normalizedUrl,
      domain,
      pages_crawled: crawlResult.pages.length,
      pages_found: crawlResult.pagesFound,
      health_score: healthScore,
      crawled_pages: crawlResult.pages,
      raw_findings: rawFindings,
      grouped_findings: groupedFindings,
      broken_links: brokenLinks,
      site_summary: {
        ...siteSummary,
        competitors_provided: competitors.length,
        html_only_scan: true,
        javascript_rendering_used: false,
      },
      crawl_warnings: crawlResult.warnings,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Scan failed",
      },
      { status: 500 }
    );
  }
});

async function crawlSite({
  startUrl,
  domain,
  maxPages,
}: {
  startUrl: string;
  domain: string;
  maxPages: number;
}) {
  const queue: string[] = [canonicalizeUrl(startUrl)];
  const seen = new Set<string>();
  const pages: any[] = [];
  const warnings: string[] = [];

  while (queue.length > 0 && pages.length < maxPages) {
    const batch = queue.splice(0, BATCH_SIZE).filter((url) => !seen.has(url));

    if (batch.length === 0) continue;

    batch.forEach((url) => seen.add(url));

    const results = await Promise.allSettled(
      batch.map((url) => fetchAndParsePage(url, domain))
    );

    for (const result of results) {
      if (result.status !== "fulfilled") {
        warnings.push("A page could not be fetched.");
        continue;
      }

      const page = result.value;
      pages.push(page);

      if (page.status_code >= 200 && page.status_code < 400) {
        const internalLinks = page.internal_links || [];

        for (const link of internalLinks.slice(0, MAX_LINKS_PER_PAGE)) {
          const clean = canonicalizeUrl(link);

          if (
            clean &&
            !seen.has(clean) &&
            isSameDomain(clean, domain) &&
            !isAssetUrl(clean) &&
            !isUtilityPage(clean) &&
            pages.length + queue.length < maxPages * 3
          ) {
            queue.push(clean);
          }
        }
      }
    }
  }

  return {
    pages,
    pagesFound: seen.size + queue.length,
    warnings,
  };
}

async function fetchAndParsePage(url: string, domain: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "User-Agent": USER_AGENT,
        accept:
          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });

    const contentType = response.headers.get("content-type") || "";
    const finalUrl = response.url || url;

    if (!contentType.includes("text/html")) {
      return buildNonHtmlPage(url, finalUrl, response.status, contentType);
    }

    const html = await response.text();
    const extracted = extractPageData(html, finalUrl, domain);

    return {
      url: canonicalizeUrl(finalUrl),
      original_url: url,
      final_url: finalUrl,
      status_code: response.status,
      content_type: contentType,
      redirected: canonicalizeUrl(url) !== canonicalizeUrl(finalUrl),
      ...extracted,
    };
  } catch (error) {
    return {
      url: canonicalizeUrl(url),
      original_url: url,
      final_url: url,
      status_code: 0,
      content_type: "",
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
      has_faq: false,
      faq_questions: [],
      has_schema: false,
      schema_types: [],
      has_phone: false,
      has_email: false,
      cta_phrases: [],
      trust_signals: [],
      placeholder_text: [],
      is_utility_page: isUtilityPage(url),
      is_important_page: isImportantPage(url, "", ""),
      fetch_error: error?.message || "Fetch failed",
    };
  } finally {
    clearTimeout(timeout);
  }
}

function buildNonHtmlPage(
  url: string,
  finalUrl: string,
  status: number,
  contentType: string
) {
  return {
    url: canonicalizeUrl(finalUrl),
    original_url: url,
    final_url: finalUrl,
    status_code: status,
    content_type: contentType,
    redirected: canonicalizeUrl(url) !== canonicalizeUrl(finalUrl),
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
    has_faq: false,
    faq_questions: [],
    has_schema: false,
    schema_types: [],
    has_phone: false,
    has_email: false,
    cta_phrases: [],
    trust_signals: [],
    placeholder_text: [],
    is_utility_page: isUtilityPage(url),
    is_important_page: isImportantPage(url, "", ""),
    fetch_error: "",
  };
}

function extractPageData(html: string, url: string, domain: string) {
  const title = cleanText(matchFirst(html, /<title[^>]*>([\s\S]*?)<\/title>/i));

  const metaDescription = cleanText(
    matchFirst(
      html,
      /<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["'][^>]*>/i
    ) ||
      matchFirst(
        html,
        /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["'][^>]*>/i
      )
  );

  const h1 = cleanText(matchFirst(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i));
  const h2s = matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi).slice(0, 20);
  const h3s = matchAllClean(html, /<h3[^>]*>([\s\S]*?)<\/h3>/gi).slice(0, 30);

  const canonicalUrl =
    matchFirst(
      html,
      /<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["'][^>]*>/i
    ) ||
    matchFirst(
      html,
      /<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["'][^>]*>/i
    ) ||
    "";

  const robotsMeta =
    matchFirst(
      html,
      /<meta[^>]+name=["']robots["'][^>]+content=["']([^"']*)["'][^>]*>/i
    ) ||
    matchFirst(
      html,
      /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']robots["'][^>]*>/i
    ) ||
    "";

  const visibleText = extractVisibleText(html);
  const wordCount = countWords(visibleText);
  const links = extractLinks(html, url);
  const internalLinks = links.filter((link) => isSameDomain(link, domain));
  const externalLinks = links.filter((link) => !isSameDomain(link, domain));
  const images = extractImages(html, url);

  const faqQuestions = extractQuestions(visibleText);
  const schemaTypes = extractSchemaTypes(html);
  const ctaPhrases = extractCtas(visibleText);
  const trustSignals = extractTrustSignals(visibleText);
  const placeholderText = extractPlaceholderText(visibleText);

  return {
    title,
    meta_description: metaDescription,
    h1,
    h2s,
    h3s,
    canonical_url: absolutizeUrl(canonicalUrl, url),
    robots_meta: robotsMeta,
    word_count: wordCount,
    visible_text_sample: visibleText.slice(0, 1500),
    internal_links: Array.from(new Set(internalLinks)).slice(0, 150),
    external_links: Array.from(new Set(externalLinks)).slice(0, 100),
    images,
    has_faq: faqQuestions.length >= 2 || /frequently asked questions|faq/i.test(visibleText),
    faq_questions: faqQuestions.slice(0, 12),
    has_schema: /application\/ld\+json|schema\.org/i.test(html),
    schema_types: schemaTypes,
    has_phone: /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.test(visibleText),
    has_email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(visibleText),
    cta_phrases: ctaPhrases,
    trust_signals: trustSignals,
    placeholder_text: placeholderText,
    is_utility_page: isUtilityPage(url),
    is_important_page: isImportantPage(url, title, h1),
    fetch_error: "",
  };
}

function analyzePages({
  pages,
  domain,
  businessName,
  businessType,
  city,
}: {
  pages: any[];
  domain: string;
  businessName: string;
  businessType: string;
  city: string;
}) {
  const findings: any[] = [];

  for (const page of pages) {
    if (page.status_code === 0 || page.status_code >= 400) {
      findings.push(makeFinding({
        page,
        category: "broken_page",
        customer_category: "Broken page",
        status: "needs_developer",
        priority: "high",
        difficulty: "developer",
        title: "This page may not be loading correctly",
        explanation: "We could not access this page successfully during the scan.",
        why: "Broken pages can frustrate visitors and make it harder for search engines to understand your website.",
        recommended: "Ask your website editor or developer to review this page and fix the link or page setup.",
      }));
      continue;
    }

    if (page.is_utility_page) {
      continue;
    }

    if (!page.title) {
      findings.push(makeFinding({
        page,
        category: "meta_title",
        customer_category: "Search title",
        status: "auto_fixed",
        priority: "high",
        difficulty: "easy",
        title: "Add a clear search title",
        explanation: "This page does not appear to have a clear title for search results.",
        why: "A clear search title helps people understand what the page is about before they click.",
        current: "",
        recommended: suggestSearchTitle(page, businessName, businessType, city),
      }));
    } else if (page.title.length < 20 || page.title.length > 70) {
      findings.push(makeFinding({
        page,
        category: "meta_title",
        customer_category: "Search title",
        status: "auto_fixed",
        priority: "medium",
        difficulty: "easy",
        title: "Improve this page’s search title",
        explanation: "This page has a search title, but it may be too short, too long, or not descriptive enough.",
        why: "A stronger title may help searchers understand why this page is relevant.",
        current: page.title,
        recommended: suggestSearchTitle(page, businessName, businessType, city),
      }));
    }

    if (!page.meta_description && page.is_important_page) {
      findings.push(makeFinding({
        page,
        category: "meta_description",
        customer_category: "Search description",
        status: "auto_fixed",
        priority: "medium",
        difficulty: "easy",
        title: "Add a helpful search description",
        explanation: "This important page does not appear to have a clear search description.",
        why: "A search description can help people understand what the page offers before they click.",
        current: "",
        recommended: suggestSearchDescription(page, businessName, businessType, city),
      }));
    } else if (
      page.meta_description &&
      (page.meta_description.length < 70 || page.meta_description.length > 170) &&
      page.is_important_page
    ) {
      findings.push(makeFinding({
        page,
        category: "meta_description",
        customer_category: "Search description",
        status: "auto_fixed",
        priority: "low",
        difficulty: "easy",
        title: "Improve this page’s search description",
        explanation: "This page has a search description, but it may not be the best length or clarity.",
        why: "A clearer description may help more people choose your page in search results.",
        current: page.meta_description,
        recommended: suggestSearchDescription(page, businessName, businessType, city),
      }));
    }

    if (!page.h1 && page.is_important_page) {
      findings.push(makeFinding({
        page,
        category: "page_heading",
        customer_category: "Page heading",
        status: "needs_approval",
        priority: "medium",
        difficulty: "moderate",
        title: "Add a clear main page heading",
        explanation: "This important page does not appear to have a clear main heading.",
        why: "A clear heading helps visitors and search engines quickly understand the page.",
        current: "",
        recommended: suggestH1(page, businessType, city),
      }));
    }

    if (!page.canonical_url && page.is_important_page) {
      findings.push(makeFinding({
        page,
        category: "canonical",
        customer_category: "Website setup",
        status: "needs_developer",
        priority: "medium",
        difficulty: "developer",
        title: "Review preferred-page settings",
        explanation: "This page may not clearly tell search engines which version of the page is preferred.",
        why: "Preferred-page settings can help search engines understand the main version of important pages.",
        current: "Not found",
        recommended: "Ask your website editor or developer to review preferred-page settings for this page.",
      }));
    }

    if (page.word_count < 300 && page.is_important_page) {
      findings.push(makeFinding({
        page,
        category: "thin_content",
        customer_category: "Page content",
        status: "needs_developer",
        priority: "medium",
        difficulty: "moderate",
        title: "Add more helpful content to this page",
        explanation: "This important page may not have enough helpful content for visitors.",
        why: "Important pages usually perform better when they clearly answer visitor questions and explain the service.",
        current: `${page.word_count} words found`,
        recommended: "Add clearer service details, benefits, questions and answers, proof points, and a stronger call to action.",
      }));
    }

    if (page.placeholder_text.length > 0 && page.is_important_page) {
      findings.push(makeFinding({
        page,
        category: "placeholder_text",
        customer_category: "Website setup",
        status: "needs_developer",
        priority: "high",
        difficulty: "developer",
        title: "Important content may not be showing correctly",
        explanation: "We found placeholder-like text in the page content.",
        why: "Important proof points, numbers, and service details should be clearly visible in the page content.",
        current: page.placeholder_text.join(", "),
        recommended: "Ask a developer to make sure the final text and numbers appear directly in the page content.",
      }));
    }

    if (page.is_important_page && !page.has_faq) {
      findings.push(makeFinding({
        page,
        category: "faq_gap",
        customer_category: "Page content",
        status: "needs_developer",
        priority: "low",
        difficulty: "moderate",
        title: "Consider adding customer questions",
        explanation: "This important page does not appear to answer common customer questions.",
        why: "Question-and-answer sections can help visitors make decisions and may make the page more useful.",
        current: "No clear FAQ section found",
        recommended: "Add 4–6 common questions customers ask before contacting you.",
      }));
    }

    if (page.is_important_page && page.cta_phrases.length === 0) {
      findings.push(makeFinding({
        page,
        category: "cta_gap",
        customer_category: "Page content",
        status: "needs_developer",
        priority: "medium",
        difficulty: "moderate",
        title: "Add a clearer next step",
        explanation: "This page may not have a clear call to action.",
        why: "Visitors are more likely to contact you when the next step is obvious.",
        current: "No strong call to action found",
        recommended: "Add a clear button or section such as “Get started,” “Request a quote,” “Book a call,” or “Apply now.”",
      }));
    }

    if (page.is_important_page && page.trust_signals.length === 0) {
      findings.push(makeFinding({
        page,
        category: "trust_signal_gap",
        customer_category: "Trust signals",
        status: "needs_developer",
        priority: "medium",
        difficulty: "moderate",
        title: "Add more trust signals",
        explanation: "This important page may not show enough proof that visitors can trust the business.",
        why: "Reviews, testimonials, case studies, years in business, certifications, or project examples can help visitors feel more confident.",
        current: "No clear trust signals found",
        recommended: "Add reviews, testimonials, proof numbers, project examples, guarantees, or certifications where appropriate.",
      }));
    }
  }

  const duplicateTitles = findDuplicateValues(pages, "title");
  for (const title of duplicateTitles) {
    const affected = pages.filter((p) => p.title === title).map((p) => p.url);
    if (affected.length > 1 && title) {
      findings.push({
        id: stableId(`duplicate-title-${title}`),
        type: "site_level",
        category: "duplicate_search_titles",
        customer_category: "Search appearance",
        status: "needs_approval",
        priority: "medium",
        difficulty: "easy",
        issue_title: "Several pages use the same search title",
        plain_english_explanation: "Multiple pages appear to use the same search title.",
        why_it_matters: "Unique titles help people and search engines understand what each page is about.",
        current_value: title,
        recommended_value: "Give each important page a unique search title.",
        ai_recommendation: "Review the affected pages and prepare unique search titles for each one.",
        affected_pages: affected,
        can_auto_fix: false,
        requires_approval: true,
        requires_developer: false,
        confidence_score: 90,
      });
    }
  }

  return dedupeFindings(findings);
}

function makeFinding({
  page,
  category,
  customer_category,
  status,
  priority,
  difficulty,
  title,
  explanation,
  why,
  current = "",
  recommended = "",
}: any) {
  return {
    id: stableId(`${page.url}-${category}-${title}`),
    type: "page_level",
    page_url: pathFromUrl(page.url),
    full_url: page.url,
    category,
    customer_category,
    status,
    priority,
    difficulty,
    issue_title: title,
    plain_english_explanation: explanation,
    why_it_matters: why,
    current_value: current,
    recommended_value: recommended,
    ai_recommendation: recommended,
    can_auto_fix: status === "auto_fixed",
    requires_approval: status === "needs_approval",
    requires_developer: status === "needs_developer",
    confidence_score: 90,
  };
}

function groupRepeatedFindings(findings: any[]) {
  const canonicalFindings = findings.filter((f) => f.category === "canonical");
  const others = findings.filter((f) => f.category !== "canonical");

  const grouped: any[] = [...others];

  if (canonicalFindings.length >= 2) {
    grouped.push({
      id: stableId("grouped-canonical-findings"),
      type: "site_level",
      category: "canonical",
      customer_category: "Website setup",
      status: "needs_developer",
      priority: "medium",
      difficulty: "developer",
      issue_title: "Review preferred-page settings across important pages",
      plain_english_explanation:
        "Several important pages may not clearly tell search engines which version of the page is preferred.",
      why_it_matters:
        "Preferred-page settings can help search engines understand the main version of important pages.",
      current_value: `${canonicalFindings.length} pages may need review`,
      recommended_value:
        "Ask your website editor or developer to review preferred-page settings for these pages.",
      ai_recommendation:
        "Have a website editor or developer review the affected pages and add preferred-page settings where appropriate.",
      affected_pages: canonicalFindings.map((f) => f.page_url),
      can_auto_fix: false,
      requires_approval: false,
      requires_developer: true,
      confidence_score: 90,
    });
  } else {
    grouped.push(...canonicalFindings);
  }

  return dedupeFindings(grouped);
}

function detectBrokenInternalLinks(pages: any[]) {
  const statusMap = new Map<string, number>();

  for (const page of pages) {
    statusMap.set(canonicalizeUrl(page.url), page.status_code);
  }

  const broken: any[] = [];

  for (const page of pages) {
    for (const link of page.internal_links || []) {
      const clean = canonicalizeUrl(link);
      const status = statusMap.get(clean);

      if (status !== undefined && status >= 400) {
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

function buildSiteSummary(pages: any[], findings: any[]) {
  const importantPages = pages.filter((p) => p.is_important_page);
  const pagesWithFaq = pages.filter((p) => p.has_faq);
  const pagesWithTrust = pages.filter((p) => p.trust_signals?.length > 0);
  const pagesWithCta = pages.filter((p) => p.cta_phrases?.length > 0);

  const positives: string[] = [];

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
  };
}

function calculateHealthScore(findings: any[]) {
  let score = 100;

  for (const finding of findings) {
    if (finding.priority === "high" || finding.priority === "critical") {
      score -= 8;
    } else if (finding.priority === "medium") {
      score -= 5;
    } else {
      score -= 2;
    }
  }

  return Math.max(0, Math.min(100, score));
}

function normalizeStartUrl(input: string) {
  let url = input.trim();

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  return canonicalizeUrl(url);
}

function canonicalizeUrl(input: string) {
  try {
    const url = new URL(input);
    url.hash = "";

    if (url.pathname !== "/" && url.pathname.endsWith("/")) {
      url.pathname = url.pathname.slice(0, -1);
    }

    const removableParams = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content",
      "fbclid",
      "gclid",
      "msclkid",
    ];

    for (const param of removableParams) {
      url.searchParams.delete(param);
    }

    return url.toString();
  } catch {
    return input;
  }
}

function absolutizeUrl(href: string, base: string) {
  if (!href) return "";

  try {
    return new URL(href, base).toString();
  } catch {
    return "";
  }
}

function isSameDomain(input: string, domain: string) {
  try {
    const url = new URL(input);
    return url.hostname.replace(/^www\./, "") === domain;
  } catch {
    return false;
  }
}

function isAssetUrl(input: string) {
  return /\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|mp4|mp3|avi|mov|css|js|ico|woff|woff2|ttf)$/i.test(
    input
  );
}

function isUtilityPage(input: string) {
  const path = pathFromUrl(input);
  return UTILITY_PATH_PATTERNS.some((pattern) => pattern.test(path));
}

function isImportantPage(input: string, title = "", h1 = "") {
  const path = pathFromUrl(input);
  const combined = `${path} ${title} ${h1}`;
  return IMPORTANT_PAGE_PATTERNS.some((pattern) => pattern.test(combined));
}

function pathFromUrl(input: string) {
  try {
    const url = new URL(input);
    return url.pathname || "/";
  } catch {
    return input || "/";
  }
}

function extractVisibleText(html: string) {
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

function extractLinks(html: string, baseUrl: string) {
  const links: string[] = [];
  const regex = /<a[^>]+href=["']([^"']+)["'][^>]*>/gi;
  let match;

  while ((match = regex.exec(html))) {
    const href = match[1];

    if (!href) continue;
    if (href.startsWith("#")) continue;
    if (/^(mailto:|tel:|sms:|javascript:)/i.test(href)) continue;

    const absolute = absolutizeUrl(href, baseUrl);
    if (absolute && !isAssetUrl(absolute)) {
      links.push(canonicalizeUrl(absolute));
    }
  }

  return Array.from(new Set(links));
}

function extractImages(html: string, baseUrl: string) {
  const images: any[] = [];
  const regex = /<img[^>]*>/gi;
  let match;

  while ((match = regex.exec(html))) {
    const tag = match[0];
    const src = matchFirst(tag, /src=["']([^"']+)["']/i);
    const alt = matchFirst(tag, /alt=["']([^"']*)["']/i);

    images.push({
      src: absolutizeUrl(src, baseUrl),
      alt: cleanText(alt),
      has_alt: Boolean(cleanText(alt)),
    });
  }

  return images.slice(0, 100);
}

function extractQuestions(text: string) {
  const sentences = text
    .split(/(?<=[?.!])\s+/)
    .map((sentence) => cleanText(sentence))
    .filter(Boolean);

  return sentences.filter((sentence) => sentence.endsWith("?")).slice(0, 20);
}

function extractSchemaTypes(html: string) {
  const types: string[] = [];

  const jsonLdBlocks = matchAllRaw(
    html,
    /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi
  );

  for (const block of jsonLdBlocks) {
    const matches = block.match(/"@type"\s*:\s*"([^"]+)"/gi) || [];

    for (const item of matches) {
      const type = item.replace(/"@type"\s*:\s*"/i, "").replace(/"/g, "");
      if (type) types.push(type);
    }
  }

  if (/schema\.org\/LocalBusiness/i.test(html)) types.push("LocalBusiness");
  if (/schema\.org\/FAQPage/i.test(html)) types.push("FAQPage");
  if (/schema\.org\/Organization/i.test(html)) types.push("Organization");

  return Array.from(new Set(types)).slice(0, 20);
}

function extractCtas(text: string) {
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

  return ctas.filter((cta) => text.toLowerCase().includes(cta));
}

function extractTrustSignals(text: string) {
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
  ];

  return signals.filter((signal) => text.toLowerCase().includes(signal));
}

function extractPlaceholderText(text: string) {
  const found: string[] = [];

  for (const pattern of PLACEHOLDER_PATTERNS) {
    const match = text.match(pattern);
    if (match?.[0]) found.push(match[0]);
  }

  return Array.from(new Set(found));
}

function matchFirst(input: string, regex: RegExp) {
  const match = input.match(regex);
  return match?.[1] || "";
}

function matchAllClean(input: string, regex: RegExp) {
  const results: string[] = [];
  let match;

  while ((match = regex.exec(input))) {
    results.push(cleanText(match[1]));
  }

  return results.filter(Boolean);
}

function matchAllRaw(input: string, regex: RegExp) {
  const results: string[] = [];
  let match;

  while ((match = regex.exec(input))) {
    results.push(match[1]);
  }

  return results.filter(Boolean);
}

function cleanText(input: string) {
  return String(input || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function countWords(text: string) {
  return cleanText(text).split(/\s+/).filter(Boolean).length;
}

function findDuplicateValues(items: any[], key: string) {
  const counts = new Map<string, number>();

  for (const item of items) {
    const value = cleanText(item[key]);
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }

  return Array.from(counts.entries())
    .filter(([, count]) => count > 1)
    .map(([value]) => value);
}

function dedupeFindings(findings: any[]) {
  const seen = new Set<string>();
  const output: any[] = [];

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

function stableId(input: string) {
  let hash = 0;

  for (let i = 0; i < input.length; i++) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }

  return `finding_${Math.abs(hash)}`;
}

function suggestSearchTitle(
  page: any,
  businessName: string,
  businessType: string,
  city: string
) {
  const path = pathFromUrl(page.url);

  if (path === "/") {
    return [businessName, businessType, city].filter(Boolean).join(" | ").slice(0, 65);
  }

  const pageName = path
    .split("/")
    .filter(Boolean)
    .pop()
    ?.replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

  return [pageName, businessName, city].filter(Boolean).join(" | ").slice(0, 65);
}

function suggestSearchDescription(
  page: any,
  businessName: string,
  businessType: string,
  city: string
) {
  const path = pathFromUrl(page.url);

  if (path === "/") {
    return `${businessName} helps customers with ${businessType || "professional services"}${city ? ` in ${city}` : ""}. Learn more, review your options, and get in touch today.`.slice(0, 160);
  }

  const pageName =
    path
      .split("/")
      .filter(Boolean)
      .pop()
      ?.replaceAll("-", " ") || "this service";

  return `Learn more about ${pageName} from ${businessName}${city ? ` in ${city}` : ""}. See helpful details, next steps, and how to get started.`.slice(0, 160);
}

function suggestH1(page: any, businessType: string, city: string) {
  const path = pathFromUrl(page.url);

  if (path === "/") {
    return [businessType, city].filter(Boolean).join(" in ") || "Welcome";
  }

  return (
    path
      .split("/")
      .filter(Boolean)
      .pop()
      ?.replaceAll("-", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Service Information"
  );
}