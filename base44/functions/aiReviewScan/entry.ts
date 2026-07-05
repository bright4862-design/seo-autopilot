import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VALID_CATEGORIES = new Set([
  "meta_title",
  "meta_description",
  "404_error",
  "redirect",
  "canonical",
  "sitemap",
  "robots_txt",
  "js_rendering",
  "internal_link",
  "thin_content",
  "duplicate_content",
  "schema",
  "performance",
  "web_dev",
]);

const CATEGORY_MAP = {
  broken_page: "404_error",
  page_heading: "thin_content",
  placeholder_text: "web_dev",
  faq_gap: "thin_content",
  cta_gap: "thin_content",
  trust_signal_gap: "schema",
  duplicate_search_titles: "duplicate_content",
  image_alt_text: "web_dev",
  competitor_gap: "thin_content",
};

const UTILITY_PAGE_WORDS = [
  "cart",
  "checkout",
  "login",
  "signin",
  "signup",
  "register",
  "account",
  "search",
  "privacy",
  "terms",
  "thank-you",
  "thankyou",
  "payment",
  "admin",
  "wp-admin",
  "reset",
  "forgot",
  "cookie",
  "legal",
  "disclaimer",
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
      business_name = "",
      business_type = "",
      city = "",
      website_url = "",
      crawled_pages = [],
      raw_fixes = [],
      competitor_results = [],
      discovered_competitors = [],
      competitor_page_snapshots = [],
      scan_mode = "quick",
      crawl_warnings = [],
    } = body;

    if (!website_url) {
      return Response.json(
        { success: false, error: "website_url is required" },
        { status: 400 }
      );
    }

    const filteredFixes = prepareInputFixes(raw_fixes);

    const deterministicPlan = buildDeterministicPlan({
      business_name,
      business_type,
      city,
      website_url,
      crawled_pages,
      filteredFixes,
      competitor_results,
      discovered_competitors,
      competitor_page_snapshots,
      scan_mode,
      crawl_warnings,
    });

    let aiResponse = null;

    try {
      const prompt = buildPrompt({
        business_name,
        business_type,
        city,
        website_url,
        crawled_pages: trimPagesForAI(crawled_pages),
        filteredFixes,
        competitor_results,
        discovered_competitors,
        competitor_page_snapshots: trimCompetitorsForAI(
          competitor_page_snapshots
        ),
        scan_mode,
        crawl_warnings,
        deterministicPlan,
      });

      aiResponse = await withTimeout(
        base44.integrations.Core.InvokeLLM({
          prompt,
          response_json_schema: responseSchema(),
        }),
        30000,
        "AI review"
      );
    } catch {
      return Response.json({
        success: true,
        ai_review_warning:
          "AI review was unavailable, so SEO Autopilot used its rule-based review instead.",
        ...deterministicPlan,
      });
    }

    const cleanedFromAI = Array.isArray(aiResponse?.cleaned_fixes)
      ? aiResponse.cleaned_fixes
      : [];

    let cleanedFixes =
      cleanedFromAI.length > 0
        ? preserveStructuredFields(cleanedFromAI, filteredFixes)
        : deterministicPlan.cleaned_fixes;

    cleanedFixes = normalizeCleanedFixes(cleanedFixes);

    if (filteredFixes.length > 0 && cleanedFixes.length === 0) {
      cleanedFixes = deterministicPlan.cleaned_fixes;
    }

    const competitorFixes = buildCompetitorFixes({
      competitor_results,
      discovered_competitors,
      competitor_page_snapshots,
    });

    cleanedFixes = normalizeCleanedFixes([
      ...cleanedFixes,
      ...competitorFixes,
    ]).slice(0, 16);

    return Response.json({
      success: true,
      plain_english_summary:
        aiResponse?.plain_english_summary ||
        deterministicPlan.plain_english_summary,
      top_recommended_actions:
        Array.isArray(aiResponse?.top_recommended_actions) &&
        aiResponse.top_recommended_actions.length > 0
          ? aiResponse.top_recommended_actions.slice(0, 5)
          : deterministicPlan.top_recommended_actions,
      cleaned_fixes: cleanedFixes,
      grouped_page_recommendations:
        Array.isArray(aiResponse?.grouped_page_recommendations)
          ? aiResponse.grouped_page_recommendations
          : [],
      ignored_low_value_pages:
        Array.isArray(aiResponse?.ignored_low_value_pages)
          ? aiResponse.ignored_low_value_pages
          : [],
      positive_findings:
        Array.isArray(aiResponse?.positive_findings) &&
        aiResponse.positive_findings.length > 0
          ? aiResponse.positive_findings.slice(0, 5)
          : deterministicPlan.positive_findings,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "AI review failed",
      },
      { status: 500 }
    );
  }
});

function prepareInputFixes(rawFixes) {
  const safe = Array.isArray(rawFixes) ? rawFixes : [];

  return dedupeFixes(
    safe
      .filter((fix) => {
        const pageUrl = String(fix.page_url || "").toLowerCase();

        const isUtilityPage = UTILITY_PAGE_WORDS.some((word) =>
          pageUrl.includes(word)
        );

        const isBrokenPage =
          fix.category === "404_error" ||
          fix.category === "broken_page" ||
          fix.category === "internal_link" ||
          String(fix.issue_title || "").toLowerCase().includes("broken");

        if (isUtilityPage && !isBrokenPage) return false;

        return true;
      })
      .map(normalizeFix)
  );
}

function normalizeFix(fix) {
  const category = safeCategory(fix.category);
  const status =
    fix.status ||
    (fix.requires_developer
      ? "needs_developer"
      : fix.requires_approval
        ? "needs_approval"
        : fix.can_auto_fix
          ? "auto_fixed"
          : "needs_approval");

  return {
    page_url: cleanPath(fix.page_url || fix.url || "/"),
    category,
    customer_category:
      fix.customer_category ||
      friendlyCategory(category) ||
      "Website improvement",
    issue_title:
      fix.issue_title ||
      fix.title ||
      defaultTitle(category),
    plain_english_explanation:
      fix.plain_english_explanation ||
      fix.explanation ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      fix.why_it_matters ||
      fix.why ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: stringifyValue(fix.current_value || fix.current || ""),
    recommended_value:
      stringifyValue(
        fix.recommended_value ||
          fix.recommendation ||
          fix.suggested_fix ||
          ""
      ) || "Review this recommendation.",
    ai_recommendation:
      stringifyValue(
        fix.ai_recommendation ||
          fix.recommended_value ||
          fix.recommendation ||
          fix.suggested_fix ||
          ""
      ) || "Review this recommendation.",
    priority: safePriority(fix.priority),
    difficulty: safeDifficulty(fix.difficulty, status),
    status: safeStatus(status),
    can_auto_fix: status === "auto_fixed" || fix.can_auto_fix === true,
    requires_approval:
      status === "needs_approval" || fix.requires_approval === true,
    requires_developer:
      status === "needs_developer" || fix.requires_developer === true,
    affected_pages: Array.isArray(fix.affected_pages)
      ? fix.affected_pages.map(cleanPath).filter(Boolean)
      : [],
    details:
      fix.details && typeof fix.details === "object" ? fix.details : {},
    confidence_score:
      typeof fix.confidence_score === "number" ? fix.confidence_score : 90,
  };
}

function buildDeterministicPlan({
  crawled_pages,
  filteredFixes,
  competitor_results,
  discovered_competitors,
  competitor_page_snapshots,
  crawl_warnings,
}) {
  const positiveFindings = buildPositiveFindings(crawled_pages);

  const cleanedFixes = normalizeCleanedFixes(
    cleanAndPrioritizeFixes(filteredFixes)
  );

  const competitorFixes = buildCompetitorFixes({
    competitor_results,
    discovered_competitors,
    competitor_page_snapshots,
  });

  const finalFixes = normalizeCleanedFixes([
    ...cleanedFixes,
    ...competitorFixes,
  ]).slice(0, 16);

  const topActions = finalFixes.slice(0, 5).map((fix) => ({
    title: fix.issue_title,
    reason: fix.why_it_matters,
    priority:
      fix.priority === "critical" || fix.priority === "high"
        ? "high"
        : fix.priority === "medium"
          ? "medium"
          : "low",
  }));

  const summaryParts = [];

  if (positiveFindings.length > 0) {
    summaryParts.push(
      `Your website has a solid SEO foundation. ${positiveFindings[0]}`
    );
  } else {
    summaryParts.push(
      "We reviewed your website and prepared a focused list of recommended improvements."
    );
  }

  if (finalFixes.length > 0) {
    summaryParts.push(
      `The main opportunities are ${describeFixTypes(finalFixes)}.`
    );
  } else {
    summaryParts.push(
      "No major issues stood out from the pages we could access."
    );
  }

  if (crawl_warnings?.length) {
    summaryParts.push(
      "Some parts of the site could not be reviewed automatically, so the recommendations are based on the pages we could access."
    );
  }

  return {
    plain_english_summary: summaryParts.join(" "),
    top_recommended_actions: topActions,
    cleaned_fixes: finalFixes,
    grouped_page_recommendations: [],
    ignored_low_value_pages: [],
    positive_findings: positiveFindings,
  };
}

function cleanAndPrioritizeFixes(fixes) {
  const byIntent = new Map();

  for (const fix of fixes || []) {
    const normalized = normalizeFix(fix);
    const key = buildIntentKey(normalized);

    if (!byIntent.has(key)) {
      byIntent.set(key, normalized);
    } else {
      const existing = byIntent.get(key);

      existing.affected_pages = Array.from(
        new Set([
          ...(existing.affected_pages || []),
          ...(normalized.affected_pages || []),
          normalized.page_url,
        ])
      ).filter(Boolean);

      existing.details = {
        ...(existing.details || {}),
        ...(normalized.details || {}),
      };
    }
  }

  return Array.from(byIntent.values())
    .sort(compareFixes)
    .slice(0, 14);
}

function compareFixes(a, b) {
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

  const priorityDiff =
    (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);

  if (priorityDiff !== 0) return priorityDiff;

  const statusDiff =
    (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);

  if (statusDiff !== 0) return statusDiff;

  const titleDiff = String(a.issue_title || "").localeCompare(
    String(b.issue_title || "")
  );

  if (titleDiff !== 0) return titleDiff;

  return String(a.page_url || "").localeCompare(String(b.page_url || ""));
}

function buildIntentKey(fix) {
  const title = String(fix.issue_title || "").toLowerCase();

  if (fix.category === "canonical") return "site|canonical|preferred-pages";

  if (fix.category === "web_dev" && /placeholder|numbers/i.test(title)) {
    return "site|web_dev|placeholder";
  }

  if (fix.category === "duplicate_content") {
    return "site|duplicate_content|titles";
  }

  if (fix.customer_category === "Competitor opportunities") {
    return "site|competitor|content-opportunities";
  }

  if (fix.affected_pages?.length > 1) {
    return `site|${fix.category}|${title}`;
  }

  return `${fix.page_url}|${fix.category}|${title}`;
}

function buildCompetitorFixes({
  competitor_results,
  discovered_competitors,
  competitor_page_snapshots,
}) {
  const snapshots = Array.isArray(competitor_page_snapshots)
    ? competitor_page_snapshots.filter((item) => item.status_code >= 200)
    : [];

  const competitors = [
    ...(Array.isArray(competitor_results) ? competitor_results : []),
    ...(Array.isArray(discovered_competitors) ? discovered_competitors : []),
  ];

  const unique = [];
  const seen = new Set();

  for (const item of competitors) {
    const url = item.website_url || item.url || "";
    const domain = getDomain(url);

    if (!domain || seen.has(domain)) continue;

    seen.add(domain);

    unique.push({
      name: item.name || formatDomainName(domain),
      website_url: url,
      keyword: item.keyword || "",
      snippet: item.snippet || "",
      position: item.position || null,
    });
  }

  if (unique.length === 0 && snapshots.length === 0) return [];

  const strongestSignals = summarizeCompetitorSignals(snapshots);

  return [
    {
      page_url: "/",
      affected_pages: [],
      category: "thin_content",
      customer_category: "Competitor opportunities",
      priority: "medium",
      status: "needs_developer",
      difficulty: "moderate",
      issue_title: "Review competitor pages for content opportunities",
      plain_english_explanation:
        snapshots.length > 0
          ? `We reviewed ${snapshots.length} competitor page${snapshots.length === 1 ? "" : "s"} from Google results and found useful comparison points.`
          : "We found competitor pages that may be useful to compare against your website.",
      why_it_matters:
        "Competitor pages can show what services, questions, proof points, and page sections customers may expect to see.",
      current_value:
        snapshots.length > 0
          ? `${snapshots.length} competitor page${snapshots.length === 1 ? "" : "s"} reviewed`
          : `${unique.length} competitor page${unique.length === 1 ? "" : "s"} found`,
      recommended_value:
        strongestSignals ||
        "Review competitor pages and look for missing service details, common questions, proof points, and calls to action.",
      ai_recommendation:
        strongestSignals ||
        "Compare your most important pages against these competitor pages. Add useful sections only when they genuinely help customers understand your services.",
      confidence_score: snapshots.length > 0 ? 90 : 80,
      can_auto_fix: false,
      requires_approval: false,
      requires_developer: true,
      details: {
        competitors: unique.slice(0, 8),
        competitor_page_snapshots: snapshots.slice(0, 5),
      },
    },
  ];
}

function summarizeCompetitorSignals(snapshots) {
  if (!snapshots.length) return "";

  const hasFaq = snapshots.some((item) => item.has_faq);
  const hasTrust = snapshots.some(
    (item) => Array.isArray(item.trust_signals) && item.trust_signals.length > 0
  );
  const hasCta = snapshots.some(
    (item) => Array.isArray(item.cta_phrases) && item.cta_phrases.length > 0
  );
  const deepContent = snapshots.some((item) => Number(item.word_count || 0) > 900);

  const suggestions = [];

  if (deepContent) {
    suggestions.push("clearer service details");
  }

  if (hasFaq) {
    suggestions.push("customer questions and answers");
  }

  if (hasTrust) {
    suggestions.push("reviews, proof points, or credibility signals");
  }

  if (hasCta) {
    suggestions.push("stronger next-step buttons or contact prompts");
  }

  if (suggestions.length === 0) {
    return "Review the competitor pages and look for useful sections that would genuinely help your customers.";
  }

  return `Competitor pages commonly include ${joinHumanList(
    suggestions
  )}. Review whether your important pages should add similar helpful sections.`;
}

function preserveStructuredFields(cleanedFixes, sourceFixes) {
  return cleanedFixes.map((fix, index) => {
    const source =
      findMatchingSourceFix(fix, sourceFixes) || sourceFixes[index] || {};

    return {
      ...fix,
      affected_pages: Array.isArray(fix.affected_pages)
        ? fix.affected_pages
        : source.affected_pages || [],
      details: {
        ...(source.details || {}),
        ...(fix.details || {}),
      },
    };
  });
}

function findMatchingSourceFix(fix, sourceFixes) {
  return (
    (sourceFixes || []).find(
      (source) =>
        String(source.page_url || "") === String(fix.page_url || "") &&
        safeCategory(source.category) === safeCategory(fix.category) &&
        String(source.issue_title || "") === String(fix.issue_title || "")
    ) ||
    (sourceFixes || []).find(
      (source) =>
        String(source.page_url || "") === String(fix.page_url || "") &&
        safeCategory(source.category) === safeCategory(fix.category)
    )
  );
}

function normalizeCleanedFixes(fixes) {
  return dedupeFixes((fixes || []).map(normalizeFix))
    .sort(compareFixes)
    .slice(0, 16);
}

function dedupeFixes(fixes) {
  const seen = new Set();
  const output = [];

  for (const fix of fixes || []) {
    const key = buildIntentKey(fix).toLowerCase();

    if (seen.has(key)) continue;

    seen.add(key);
    output.push(fix);
  }

  return output;
}

function buildPositiveFindings(pages) {
  const safePages = Array.isArray(pages) ? pages : [];

  const importantPages = safePages.filter((page) => page.is_important_page);
  const trustPages = safePages.filter(
    (page) => Array.isArray(page.trust_signals) && page.trust_signals.length > 0
  );
  const ctaPages = safePages.filter(
    (page) => Array.isArray(page.cta_phrases) && page.cta_phrases.length > 0
  );
  const faqPages = safePages.filter((page) => page.has_faq);
  const schemaPages = safePages.filter((page) => page.has_schema);

  const positives = [];

  if (importantPages.length >= 4) {
    positives.push("Your site has a strong service-page foundation.");
  }

  if (trustPages.length >= 1) {
    positives.push("Your site already includes strong trust signals.");
  }

  if (ctaPages.length >= 1) {
    positives.push("Your site gives visitors clear ways to take the next step.");
  }

  if (faqPages.length >= 1) {
    positives.push("Your site already answers some customer questions.");
  }

  if (schemaPages.length >= 1) {
    positives.push("Your site includes structured business information.");
  }

  return positives.slice(0, 5);
}

function describeFixTypes(fixes) {
  const labels = [];

  if (fixes.some((fix) => fix.category === "meta_title")) {
    labels.push("clearer search titles");
  }

  if (fixes.some((fix) => fix.category === "meta_description")) {
    labels.push("better search descriptions");
  }

  if (fixes.some((fix) => fix.category === "canonical")) {
    labels.push("preferred-page settings");
  }

  if (fixes.some((fix) => fix.category === "web_dev")) {
    labels.push("website setup cleanup");
  }

  if (fixes.some((fix) => fix.category === "thin_content")) {
    labels.push("stronger page content");
  }

  if (fixes.some((fix) => fix.category === "schema")) {
    labels.push("stronger trust signals");
  }

  if (
    fixes.some(
      (fix) => fix.customer_category === "Competitor opportunities"
    )
  ) {
    labels.push("competitor content opportunities");
  }

  if (labels.length === 0) return "a few website cleanup items";
  if (labels.length === 1) return labels[0];

  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

function trimPagesForAI(pages) {
  return (Array.isArray(pages) ? pages : []).slice(0, 100).map((page) => ({
    url: page.url,
    title: page.title,
    meta_description: page.meta_description,
    h1: page.h1,
    h2s: Array.isArray(page.h2s) ? page.h2s.slice(0, 12) : [],
    h3s: Array.isArray(page.h3s) ? page.h3s.slice(0, 12) : [],
    word_count: page.word_count,
    has_faq: page.has_faq,
    faq_questions: Array.isArray(page.faq_questions)
      ? page.faq_questions.slice(0, 8)
      : [],
    has_schema: page.has_schema,
    schema_types: page.schema_types,
    trust_signals: page.trust_signals,
    cta_phrases: page.cta_phrases,
    is_important_page: page.is_important_page,
    visible_text_sample: String(page.visible_text_sample || "").slice(0, 1000),
  }));
}

function trimCompetitorsForAI(snapshots) {
  return (Array.isArray(snapshots) ? snapshots : []).slice(0, 5).map((item) => ({
    competitor_name: item.competitor_name,
    competitor_domain: item.competitor_domain,
    competitor_url: item.competitor_url,
    keyword: item.keyword,
    serp_position: item.serp_position,
    serp_title: item.serp_title,
    serp_snippet: item.serp_snippet,
    title: item.title,
    meta_description: item.meta_description,
    h1: item.h1,
    h2s: Array.isArray(item.h2s) ? item.h2s.slice(0, 12) : [],
    h3s: Array.isArray(item.h3s) ? item.h3s.slice(0, 12) : [],
    word_count: item.word_count,
    has_faq: item.has_faq,
    faq_questions: Array.isArray(item.faq_questions)
      ? item.faq_questions.slice(0, 10)
      : [],
    has_schema: item.has_schema,
    schema_types: item.schema_types,
    trust_signals: item.trust_signals,
    cta_phrases: item.cta_phrases,
    visible_text_sample: String(item.visible_text_sample || "").slice(0, 1200),
  }));
}

function buildPrompt({
  business_name,
  business_type,
  city,
  website_url,
  crawled_pages,
  filteredFixes,
  competitor_results,
  discovered_competitors,
  competitor_page_snapshots,
  scan_mode,
  crawl_warnings,
  deterministicPlan,
}) {
  return `
You are the AI strategist inside SEO Autopilot.

The user is a small business owner. Explain SEO like a helpful expert, not a technical report.

Your job:
- Review the crawler findings.
- Remove duplicates.
- Group related issues.
- Explain what to do next in plain English.
- Keep the list useful and not overwhelming.
- Preserve important structured data such as affected_pages and details when possible.
- Do not claim changes were made.
- Do not say anything was fixed or published.
- Do not promise rankings.
- Use "prepared", "recommended", "review", "may help", and "next step".
- Avoid technical jargon. If unavoidable, explain it simply.
- Show positives first, then cleanup opportunities.

Important:
The crawler decides what exists. You explain and prioritize it. Do not erase valid findings.

Customer-facing language:
- meta title = search title
- meta description = search description
- canonical = preferred-page setting
- schema = trust signals / structured business information
- issue = recommendation
- developer required = may need help

Grouping rules:
- Preferred-page/canonical findings must be ONE card:
  "Review preferred-page settings across important pages"
  status: "needs_developer"
  priority: "medium"
  difficulty: "developer"

- Placeholder-like text such as gvar, undefined, null, NaN, [object Object], {{ }}, lorem ipsum, or placeholder must be ONE high-priority developer card:
  "Important numbers may not be showing correctly to search engines"

- Search descriptions should be specific to the business and page.

- Competitor opportunities must use the competitor page snapshots. Mention practical content gaps such as:
  service details, FAQs, proof points, trust signals, calls to action, loan terms, process steps, eligibility, timelines, or location/service coverage.
  Do not say the competitor is ranking better unless the data explicitly says that.

Business:
${business_name || ""}

Business type:
${business_type || ""}

City or service area:
${city || ""}

Website:
${website_url || ""}

Scan mode:
${scan_mode || "quick"}

Crawl warnings:
${JSON.stringify(crawl_warnings || [], null, 2)}

Crawled pages:
${JSON.stringify(crawled_pages || [], null, 2)}

Filtered recommendations:
${JSON.stringify(filteredFixes || [], null, 2)}

Competitor results:
${JSON.stringify(competitor_results || [], null, 2)}

Discovered competitors:
${JSON.stringify(discovered_competitors || [], null, 2)}

Competitor page snapshots:
${JSON.stringify(competitor_page_snapshots || [], null, 2)}

Rule-based fallback plan:
${JSON.stringify(deterministicPlan || {}, null, 2)}

Return JSON only. Keep cleaned_fixes to 6–14 items unless there are fewer valid items.
`;
}

function responseSchema() {
  return {
    type: "object",
    properties: {
      plain_english_summary: { type: "string" },
      top_recommended_actions: {
        type: "array",
        items: {
          type: "object",
          properties: {
            title: { type: "string" },
            reason: { type: "string" },
            priority: {
              type: "string",
              enum: ["high", "medium", "low"],
            },
          },
          required: ["title", "reason", "priority"],
        },
      },
      cleaned_fixes: {
        type: "array",
        items: {
          type: "object",
          properties: {
            page_url: { type: "string" },
            category: { type: "string" },
            customer_category: { type: "string" },
            issue_title: { type: "string" },
            plain_english_explanation: { type: "string" },
            why_it_matters: { type: "string" },
            current_value: { type: "string" },
            recommended_value: { type: "string" },
            ai_recommendation: { type: "string" },
            priority: {
              type: "string",
              enum: ["critical", "high", "medium", "low"],
            },
            difficulty: {
              type: "string",
              enum: ["easy", "moderate", "developer"],
            },
            status: {
              type: "string",
              enum: ["auto_fixed", "needs_approval", "needs_developer"],
            },
            can_auto_fix: { type: "boolean" },
            requires_approval: { type: "boolean" },
            requires_developer: { type: "boolean" },
          },
          required: [
            "page_url",
            "category",
            "customer_category",
            "issue_title",
            "plain_english_explanation",
            "why_it_matters",
            "current_value",
            "recommended_value",
            "ai_recommendation",
            "priority",
            "difficulty",
            "status",
            "can_auto_fix",
            "requires_approval",
            "requires_developer",
          ],
        },
      },
      grouped_page_recommendations: {
        type: "array",
        items: {
          type: "object",
          properties: {
            page_url: { type: "string" },
            group_title: { type: "string" },
            summary: { type: "string" },
            recommendations: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  label: { type: "string" },
                  recommendation: { type: "string" },
                },
                required: ["label", "recommendation"],
              },
            },
            priority: {
              type: "string",
              enum: ["high", "medium", "low"],
            },
          },
          required: [
            "page_url",
            "group_title",
            "summary",
            "recommendations",
            "priority",
          ],
        },
      },
      ignored_low_value_pages: {
        type: "array",
        items: {
          type: "object",
          properties: {
            page_url: { type: "string" },
            reason: { type: "string" },
          },
          required: ["page_url", "reason"],
        },
      },
      positive_findings: {
        type: "array",
        items: { type: "string" },
      },
    },
    required: [
      "plain_english_summary",
      "top_recommended_actions",
      "cleaned_fixes",
      "grouped_page_recommendations",
      "ignored_low_value_pages",
      "positive_findings",
    ],
  };
}

function safeCategory(category) {
  const mapped = CATEGORY_MAP[category] || category || "web_dev";
  return VALID_CATEGORIES.has(mapped) ? mapped : "web_dev";
}

function safePriority(priority) {
  return ["critical", "high", "medium", "low"].includes(priority)
    ? priority
    : "medium";
}

function safeStatus(status) {
  return ["auto_fixed", "needs_approval", "needs_developer"].includes(status)
    ? status
    : "needs_approval";
}

function safeDifficulty(difficulty, status) {
  if (["easy", "moderate", "developer"].includes(difficulty)) {
    return difficulty;
  }

  if (status === "needs_developer") return "developer";
  if (status === "needs_approval") return "moderate";
  return "easy";
}

function friendlyCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Website setup",
    schema: "Trust signals",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken pages",
    redirect: "Page redirects",
    internal_link: "Internal links",
    performance: "Website performance",
    web_dev: "Website setup",
    robots_txt: "Search visibility",
  };

  return map[category] || "Website improvement";
}

function defaultTitle(category) {
  const map = {
    meta_title: "Improve search titles",
    meta_description: "Add helpful search descriptions",
    canonical: "Review preferred-page settings",
    thin_content: "Improve important page content",
    duplicate_content: "Review duplicate page content",
    schema: "Add more trust signals",
    "404_error": "Fix pages that may not be loading",
    redirect: "Review page redirects",
    internal_link: "Review internal links",
    performance: "Review website performance",
    web_dev: "Review website setup",
    robots_txt: "Review search visibility settings",
  };

  return map[category] || "Review this website recommendation";
}

function cleanPath(input) {
  try {
    const parsed = new URL(input, "https://example.com");
    const path = parsed.pathname || "/";
    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    const value = String(input || "/").split("?")[0].split("#")[0];
    if (!value || value === "/") return "/";
    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

function stringifyValue(value) {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
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

function formatDomainName(domain) {
  return String(domain || "")
    .replace(/\.(com|net|org|co|io|us)$/i, "")
    .split(/[.-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function joinHumanList(items) {
  const clean = items.filter(Boolean);

  if (clean.length === 0) return "";
  if (clean.length === 1) return clean[0];
  if (clean.length === 2) return `${clean[0]} and ${clean[1]}`;

  return `${clean.slice(0, -1).join(", ")}, and ${clean[clean.length - 1]}`;
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