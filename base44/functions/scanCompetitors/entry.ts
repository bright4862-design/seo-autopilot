import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEO-Autopilot/2.1; +https://seoautopilot.app/bot)";

const MAX_PAGES_PER_COMPETITOR = 20;
const BATCH_SIZE = 4;
const PAGE_TIMEOUT_MS = 12000;
const COMPETITOR_CONCURRENCY = 2;

const SERVICE_WORDS =
  /service|services|product|products|treatment|treatments|location|locations|pricing|appointment|repair|installation|consultation|loan|loans|program|programs|financing|mortgage|lending|bridge|rental|construction|apply/i;

const UTILITY_PATH_RE =
  /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer|tag|category|author|feed|rss|print|share)/i;

const ASSET_RE =
  /\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|woff|woff2|ttf|mp4|mp3|mov|avi|xml|json)$/i;

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

    const {
      project_id,
      business_type = "",
      city = "",
      customer_pages = [],
    } = await req.json();

    if (!project_id) {
      return Response.json(
        { success: false, error: "project_id is required" },
        { status: 400 }
      );
    }

    const competitors = await base44.entities.Competitor.filter({
      project_id,
    });

    if (!competitors || competitors.length === 0) {
      try {
        await base44.entities.CompetitorInsight.deleteMany({ project_id });
      } catch {}

      return Response.json({
        success: true,
        customer: computeMetrics(normalizeCustomerPages(customer_pages), {
          business_type,
          city,
        }),
        competitors: [],
        insights: [],
        warnings: ["No competitors were saved for this project yet."],
      });
    }

    const customer = computeMetrics(normalizeCustomerPages(customer_pages), {
      business_type,
      city,
    });

    const warnings: string[] = [];

    const competitorResults = await mapWithConcurrency(
      competitors,
      COMPETITOR_CONCURRENCY,
      async (competitor: any) => {
        try {
          const normalizedUrl = normalizeUrl(competitor.website_url);
          const pages = await crawlSite(normalizedUrl);
          const metrics = computeMetrics(pages, {
            business_type,
            city,
          });

          const name =
            competitor.name ||
            formatDomainName(getDomain(normalizedUrl)) ||
            competitor.website_url;

          await base44.entities.Competitor.update(competitor.id, {
            name,
            website_url: normalizedUrl,
            service_pages_count: metrics.service_pages_count,
            title_quality_score: metrics.title_quality_score,
            meta_coverage_pct: metrics.meta_coverage_pct,
            content_depth_score: metrics.content_depth_score,
            faq_usage: metrics.faq_usage,
            schema_usage: metrics.schema_usage,
            broken_links_count: metrics.broken_links_count,
          });

          return {
            id: competitor.id,
            name,
            website_url: normalizedUrl,
            ...metrics,
            sample_pages: pages.slice(0, 8).map((page) => ({
              url: page.url,
              title: page.title,
              h1: page.h1,
              word_count: page.wordCount,
              has_faq: page.hasFaq,
              has_schema: page.hasSchema,
              trust_signals: page.trustSignals,
              cta_phrases: page.ctaPhrases,
            })),
          };
        } catch (error) {
          warnings.push(
            `Could not fully scan ${
              competitor.name || competitor.website_url
            }: ${error?.message || "Unknown error"}`
          );

          return {
            id: competitor.id,
            name: competitor.name || competitor.website_url,
            website_url: competitor.website_url,
            pages_crawled: 0,
            service_pages_count: 0,
            title_quality_score: 0,
            meta_coverage_pct: 0,
            content_depth_score: 0,
            faq_usage: false,
            schema_usage: false,
            broken_links_count: 1,
            sample_pages: [],
          };
        }
      }
    );

    const results = competitorResults.filter(Boolean);

    const insights = buildInsights({
      user,
      project_id,
      customer,
      competitors: results,
    });

    try {
      await base44.entities.CompetitorInsight.deleteMany({ project_id });
    } catch {}

    if (insights.length > 0) {
      await base44.entities.CompetitorInsight.bulkCreate(insights);
    }

    return Response.json({
      success: true,
      customer,
      competitors: results,
      insights,
      warnings,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Competitor scan failed",
      },
      { status: 500 }
    );
  }
});

async function crawlSite(websiteUrl: string) {
  const startUrl = normalizeUrl(websiteUrl);
  const domain = getDomain(startUrl);

  if (!startUrl || !domain) return [];

  const visited = new Set<string>();
  const queued = new Set<string>();
  const queue: string[] = [startUrl];
  queued.add(startUrl);

  const pages: any[] = [];

  while (queue.length > 0 && visited.size < MAX_PAGES_PER_COMPETITOR) {
    queue.sort((a, b) => {
      const priorityDiff = priorityScore(b) - priorityScore(a);
      if (priorityDiff !== 0) return priorityDiff;
      return a.localeCompare(b);
    });

    const batch: string[] = [];

    while (
      queue.length > 0 &&
      batch.length < BATCH_SIZE &&
      visited.size + batch.length < MAX_PAGES_PER_COMPETITOR
    ) {
      const url = queue.shift();

      if (!url) continue;
      queued.delete(url);

      if (visited.has(url)) continue;

      visited.add(url);
      batch.push(url);
    }

    const results = await Promise.allSettled(batch.map(fetchPage));

    for (const result of results) {
      if (result.status !== "fulfilled") continue;

      const page = result.value;
      pages.push(page);

      if (page.status !== 200 || !page.html) continue;

      const links = extractLinks(page.html, page.url)
        .filter((url) => getDomain(url) === domain)
        .filter((url) => !visited.has(url))
        .filter((url) => !queued.has(url))
        .filter((url) => !isUtilityUrl(url))
        .filter((url) => !isAssetUrl(url))
        .sort((a, b) => {
          const priorityDiff = priorityScore(b) - priorityScore(a);
          if (priorityDiff !== 0) return priorityDiff;
          return a.localeCompare(b);
        });

      for (const link of links) {
        if (queue.length + visited.size >= MAX_PAGES_PER_COMPETITOR * 3) break;

        queue.push(link);
        queued.add(link);
      }
    }
  }

  return pages.map(extractPageMetrics).sort((a, b) => {
    const priorityDiff = priorityScore(b.url) - priorityScore(a.url);
    if (priorityDiff !== 0) return priorityDiff;
    return a.url.localeCompare(b.url);
  });
}

async function fetchPage(url: string) {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), PAGE_TIMEOUT_MS);

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

    clearTimeout(timeout);

    const contentType = response.headers.get("content-type") || "";

    if (!contentType.toLowerCase().includes("text/html")) {
      return {
        url: response.url || url,
        status: response.status,
        html: "",
      };
    }

    const html = await response.text();

    return {
      url: response.url || url,
      status: response.status,
      html,
    };
  } catch {
    return {
      url,
      status: 0,
      html: "",
    };
  }
}

function extractPageMetrics(page: any) {
  const html = decodeHtml(page.html || "");
  const bodyText = extractVisibleText(html);

  const title = cleanText(matchFirst(html, /<title[^>]*>([\s\S]*?)<\/title>/i));

  const metaDesc = cleanText(
    getMetaContent(html, "description") ||
      getMetaProperty(html, "og:description") ||
      getMetaContent(html, "twitter:description")
  );

  const h1 = cleanText(matchFirst(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i));

  const h2s = matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi).slice(0, 20);

  const wordCount = countWords(bodyText);
  const questions = extractQuestions(bodyText);
  const schemaTypes = detectSchemaTypes(html);
  const trustSignals = detectTrustSignals(bodyText);
  const ctaPhrases = detectCtas(bodyText);

  return {
    url: canonicalizeUrl(page.url),
    status: page.status,
    title,
    metaDesc,
    h1,
    h2s,
    wordCount,
    hasFaq:
      questions.length >= 2 ||
      /faq|frequently asked/i.test(bodyText),
    questionCount: questions.length,
    hasSchema:
      schemaTypes.length > 0 ||
      html.includes("application/ld+json") ||
      html.includes("schema.org"),
    schemaTypes,
    trustSignals,
    ctaPhrases,
    hasTrustSignals: trustSignals.length > 0,
    hasCta: ctaPhrases.length > 0,
    isServicePage:
      SERVICE_WORDS.test(page.url || "") ||
      SERVICE_WORDS.test(title || "") ||
      SERVICE_WORDS.test(h1 || ""),
  };
}

function normalizeCustomerPages(customerPages: any[]) {
  return (Array.isArray(customerPages) ? customerPages : []).map((page) => {
    const trustSignals = Array.isArray(page.trust_signals)
      ? page.trust_signals
      : [];

    const ctaPhrases = Array.isArray(page.cta_phrases)
      ? page.cta_phrases
      : [];

    const schemaTypes = Array.isArray(page.schema_types)
      ? page.schema_types
      : [];

    return {
      url: page.url || "",
      status: page.status_code || page.status || 0,
      title: page.title || "",
      metaDesc: page.meta_description || page.metaDesc || "",
      h1: page.h1 || "",
      h2s: page.h2s || [],
      wordCount: page.word_count || page.wordCount || 0,
      hasFaq: Boolean(page.has_faq || page.hasFaq),
      hasSchema: Boolean(page.has_schema || page.hasSchema),
      schemaTypes,
      trustSignals,
      ctaPhrases,
      hasTrustSignals: trustSignals.length > 0,
      hasCta: ctaPhrases.length > 0,
      isServicePage:
        SERVICE_WORDS.test(page.url || "") ||
        SERVICE_WORDS.test(page.title || "") ||
        SERVICE_WORDS.test(page.h1 || ""),
    };
  });
}

function computeMetrics(pages: any[], context: any = {}) {
  const okPages = pages.filter((page) => page.status >= 200 && page.status < 400);

  const servicePages = okPages.filter(
    (page) =>
      page.isServicePage ||
      SERVICE_WORDS.test(page.url || "") ||
      SERVICE_WORDS.test(page.title || "") ||
      SERVICE_WORDS.test(page.h1 || "")
  );

  const avgTitle = okPages.length
    ? Math.round(
        okPages.reduce(
          (sum, page) => sum + titleScore(page.title, context),
          0
        ) / okPages.length
      )
    : 0;

  const metaPct = okPages.length
    ? Math.round(
        (okPages.filter((page) => page.metaDesc && page.metaDesc.length >= 50)
          .length /
          okPages.length) *
          100
      )
    : 0;

  const avgWords = okPages.length
    ? Math.round(
        okPages.reduce((sum, page) => sum + Number(page.wordCount || 0), 0) /
          okPages.length
      )
    : 0;

  const faqPct = okPages.length
    ? Math.round((okPages.filter((page) => page.hasFaq).length / okPages.length) * 100)
    : 0;

  const trustPct = okPages.length
    ? Math.round(
        (okPages.filter((page) => page.hasTrustSignals).length / okPages.length) *
          100
      )
    : 0;

  const ctaPct = okPages.length
    ? Math.round((okPages.filter((page) => page.hasCta).length / okPages.length) * 100)
    : 0;

  const schemaPct = okPages.length
    ? Math.round(
        (okPages.filter((page) => page.hasSchema).length / okPages.length) * 100
      )
    : 0;

  const contentDepthScore = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        avgWords >= 900
          ? 95
          : avgWords >= 650
            ? 85
            : avgWords >= 450
              ? 75
              : avgWords >= 300
                ? 60
                : avgWords >= 150
                  ? 40
                  : 20
      )
    )
  );

  const broken = pages.filter(
    (page) => page.status === 0 || page.status >= 400
  ).length;

  return {
    pages_crawled: pages.length,
    pages_accessible: okPages.length,
    service_pages_count: servicePages.length,
    title_quality_score: avgTitle,
    meta_coverage_pct: metaPct,
    content_depth_score: contentDepthScore,
    average_word_count: avgWords,
    faq_usage: faqPct >= 20,
    faq_coverage_pct: faqPct,
    schema_usage: schemaPct >= 20,
    schema_coverage_pct: schemaPct,
    trust_signal_coverage_pct: trustPct,
    cta_coverage_pct: ctaPct,
    broken_links_count: broken,
  };
}

function titleScore(title: string, context: any = {}) {
  if (!title) return 0;

  let score = 35;

  const clean = String(title).trim();
  const lower = clean.toLowerCase();
  const businessType = String(context.business_type || "").toLowerCase();
  const city = String(context.city || "").toLowerCase();

  if (clean.length >= 20 && clean.length <= 70) score += 25;
  if (SERVICE_WORDS.test(clean)) score += 20;
  if (businessType && lower.includes(businessType)) score += 10;
  if (city && lower.includes(city)) score += 10;

  return Math.max(0, Math.min(100, score));
}

function buildInsights({ user, project_id, customer, competitors }: any) {
  const insights = [];

  const successfulCompetitors = competitors.filter(
    (item) => item.pages_accessible > 0
  );

  if (successfulCompetitors.length === 0) return [];

  const avg = (key: string) =>
    successfulCompetitors.length
      ? successfulCompetitors.reduce(
          (sum, item) => sum + Number(item[key] || 0),
          0
        ) / successfulCompetitors.length
      : 0;

  const topFor = (key: string) =>
    successfulCompetitors.reduce(
      (best, item) =>
        Number(item[key] || 0) > Number(best?.[key] || -1) ? item : best,
      null
    );

  const addInsight = ({
    metricKey,
    title,
    explanation,
    action,
    impact,
  }: {
    metricKey: string;
    title: string;
    explanation: string;
    action: string;
    impact: "high" | "medium" | "low";
  }) => {
    const top = topFor(metricKey) || successfulCompetitors[0];

    insights.push({
      owner_user_id: user.id,
      project_id,
      competitor_id: top?.id || "",
      competitor_url: top?.website_url || "",
      insight_title: title,
      explanation,
      recommended_action: action,
      impact,
      created_at: new Date().toISOString(),
    });
  };

  if (avg("service_pages_count") >= customer.service_pages_count + 2) {
    addInsight({
      metricKey: "service_pages_count",
      title: "Competitors have more dedicated service pages",
      explanation:
        "Competitor websites appear to have more separate pages for important services or offers.",
      action:
        "Create or improve dedicated pages for your most important services, products, or locations.",
      impact: "high",
    });
  }

  if (avg("title_quality_score") >= customer.title_quality_score + 12) {
    addInsight({
      metricKey: "title_quality_score",
      title: "Competitors use clearer search titles",
      explanation:
        "Competitor pages may explain the service, offer, or location more clearly in their search titles.",
      action:
        "Review your prepared search title recommendations and update your most important pages first.",
      impact: "medium",
    });
  }

  if (avg("meta_coverage_pct") >= customer.meta_coverage_pct + 20) {
    addInsight({
      metricKey: "meta_coverage_pct",
      title: "Competitors have better search descriptions",
      explanation:
        "More competitor pages include helpful search descriptions, which can make listings clearer in Google.",
      action:
        "Review and use prepared search descriptions for your homepage, service pages, and location pages.",
      impact: "medium",
    });
  }

  if (avg("content_depth_score") >= customer.content_depth_score + 15) {
    addInsight({
      metricKey: "content_depth_score",
      title: "Competitors may answer more customer questions",
      explanation:
        "Competitor pages appear to include more helpful information about services, benefits, questions, proof, or next steps.",
      action:
        "Add useful details, FAQs, proof points, reviews, and calls to action to your most important pages.",
      impact: "high",
    });
  }

  if (avg("faq_coverage_pct") >= customer.faq_coverage_pct + 20) {
    addInsight({
      metricKey: "faq_coverage_pct",
      title: "Competitors answer more common questions",
      explanation:
        "Competitor pages appear more likely to include question-and-answer content.",
      action:
        "Add 4–6 practical customer questions and answers to your most important service pages.",
      impact: "medium",
    });
  }

  if (avg("trust_signal_coverage_pct") >= customer.trust_signal_coverage_pct + 20) {
    addInsight({
      metricKey: "trust_signal_coverage_pct",
      title: "Competitors show more trust signals",
      explanation:
        "Competitor pages appear more likely to show reviews, proof points, credentials, testimonials, or project examples.",
      action:
        "Add reviews, proof numbers, testimonials, certifications, or examples where they help customers make a decision.",
      impact: "medium",
    });
  }

  if (avg("cta_coverage_pct") >= customer.cta_coverage_pct + 20) {
    addInsight({
      metricKey: "cta_coverage_pct",
      title: "Competitors use clearer next steps",
      explanation:
        "Competitor pages appear more likely to tell visitors what to do next.",
      action:
        "Add clear next steps such as Contact us, Request a quote, Book a call, Apply now, or Get started.",
      impact: "medium",
    });
  }

  if (customer.broken_links_count >= avg("broken_links_count") + 2) {
    addInsight({
      metricKey: "broken_links_count",
      title: "Your site has more broken pages",
      explanation:
        "Broken pages can frustrate visitors and make your website look less reliable.",
      action:
        "Review broken-page fixes before adding new content.",
      impact: "high",
    });
  }

  return insights.slice(0, 8);
}

async function mapWithConcurrency(items: any[], limit: number, mapper: any) {
  const results = [];
  let index = 0;

  async function worker() {
    while (index < items.length) {
      const currentIndex = index;
      index += 1;
      results[currentIndex] = await mapper(items[currentIndex], currentIndex);
    }
  }

  const workers = Array.from(
    { length: Math.min(limit, items.length) },
    () => worker()
  );

  await Promise.all(workers);

  return results;
}

function extractLinks(html: string, baseUrl: string) {
  const links = [];
  const re = /<a[^>]+href=["']([^"']+)["'][^>]*>/gi;
  let match;

  while ((match = re.exec(html)) !== null) {
    const href = match[1];

    if (!href) continue;
    if (href.startsWith("#")) continue;
    if (/^(mailto:|tel:|sms:|javascript:)/i.test(href)) continue;

    try {
      const absolute = canonicalizeUrl(new URL(href, baseUrl).toString());
      if (absolute) links.push(absolute);
    } catch {}
  }

  return Array.from(new Set(links));
}

function extractVisibleText(html: string) {
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

function getMetaContent(html: string, name: string) {
  return (
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+name=["']${escapeRegExp(name)}["'][^>]*content=["']([^"']*)["'][^>]*>`,
        "i"
      )
    ) ||
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+content=["']([^"']*)["'][^>]*name=["']${escapeRegExp(name)}["'][^>]*>`,
        "i"
      )
    ) ||
    ""
  );
}

function getMetaProperty(html: string, property: string) {
  return (
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+property=["']${escapeRegExp(property)}["'][^>]*content=["']([^"']*)["'][^>]*>`,
        "i"
      )
    ) ||
    matchFirst(
      html,
      new RegExp(
        `<meta[^>]+content=["']([^"']*)["'][^>]*property=["']${escapeRegExp(property)}["'][^>]*>`,
        "i"
      )
    ) ||
    ""
  );
}

function extractQuestions(text: string) {
  return String(text || "")
    .split(/(?<=[?.!])\s+/)
    .map(cleanText)
    .filter((line) => line.endsWith("?"))
    .slice(0, 20);
}

function detectSchemaTypes(html: string) {
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

function detectTrustSignals(text: string) {
  const lower = String(text || "").toLowerCase();

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
  ];

  return signals.filter((signal) => lower.includes(signal));
}

function detectCtas(text: string) {
  const lower = String(text || "").toLowerCase();

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
  ];

  return ctas.filter((cta) => lower.includes(cta));
}

function priorityScore(url: string) {
  const path = getPath(url).toLowerCase();

  if (path === "/") return 100;
  if (SERVICE_WORDS.test(path)) return 90;
  if (/about|contact|pricing|book|appointment|apply/i.test(path)) return 75;
  if (/case-study|case-studies|portfolio|projects/i.test(path)) return 65;
  if (/blog|article|news|resources/i.test(path)) return 35;

  return 50;
}

function normalizeUrl(input: string) {
  let url = String(input || "").trim();

  if (!url) return "";

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  return canonicalizeUrl(url);
}

function canonicalizeUrl(input: string) {
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

function getDomain(input: string) {
  try {
    const value = String(input || "");
    const url = /^https?:\/\//i.test(value) ? value : `https://${value}`;
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return "";
  }
}

function getPath(input: string) {
  try {
    return new URL(input).pathname || "/";
  } catch {
    return input || "/";
  }
}

function isAssetUrl(input: string) {
  return ASSET_RE.test(input);
}

function isUtilityUrl(input: string) {
  return UTILITY_PATH_RE.test(getPath(input));
}

function formatDomainName(domain: string) {
  return String(domain || "")
    .replace(/\.(com|net|org|co|io|us)$/i, "")
    .split(/[.-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function matchFirst(input: string, re: RegExp) {
  const match = String(input || "").match(re);
  return match?.[1] || "";
}

function matchAllClean(input: string, re: RegExp) {
  const output = [];
  let match;

  while ((match = re.exec(String(input || ""))) !== null) {
    const value = cleanText(decodeHtml(match[1]));
    if (value) output.push(value);
  }

  return Array.from(new Set(output));
}

function matchAllRaw(input: string, re: RegExp) {
  const output = [];
  let match;

  while ((match = re.exec(String(input || ""))) !== null) {
    if (match[1]) output.push(match[1]);
  }

  return output;
}

function cleanText(input: string) {
  return String(input || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function decodeHtml(input: string) {
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

function countWords(text: string) {
  const cleaned = cleanText(text);
  if (!cleaned) return 0;

  return cleaned.split(/\s+/).filter(Boolean).length;
}

function escapeRegExp(value: string) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}