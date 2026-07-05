import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

// Contract:
// - Scanner findings are canonical.
// - AI only rewrites / explains findings keyed by fix_id.
// - This function accepts raw_fixes, grouped_findings, raw_findings, findings, fixes, or recommendations.
// - This prevents recommendations disappearing when the scanner payload naming changes.

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
      normalized_url = "",
      crawled_pages = [],
      pages = [],
      competitor_page_snapshots = [],
      competitor_comparison = null,
      client_rendering = null,
      scan_mode = "quick",
      crawl_warnings = [],
      health_score = null,
    } = body;

    const finalWebsiteUrl = website_url || normalized_url;

    if (!finalWebsiteUrl) {
      return Response.json(
        { success: false, error: "website_url is required" },
        { status: 400 }
      );
    }

    const finalPages =
      Array.isArray(crawled_pages) && crawled_pages.length > 0
        ? crawled_pages
        : Array.isArray(pages)
          ? pages
          : [];

    const rawFixes = pickFirstNonEmptyArray([
      body.raw_fixes,
      body.grouped_findings,
      body.raw_findings,
      body.findings,
      body.fixes,
      body.recommendations,
      body.issues,
    ]);

    const canonicalFixes = prepareFixes(rawFixes);

    const deterministicPlan = buildDeterministicPlan({
      canonicalFixes,
      crawled_pages: finalPages,
      comparison: competitor_comparison,
      client_rendering,
      crawl_warnings,
    });

    let aiResponse = null;

    try {
      const prompt = buildPrompt({
        business_name,
        business_type,
        city,
        website_url: finalWebsiteUrl,
        scan_mode,
        crawl_warnings,
        canonicalFixes,
        siteProfile: buildSiteProfile(finalPages),
        comparison: competitor_comparison,
        snapshots: trimSnapshots(competitor_page_snapshots),
        client_rendering,
        positives: deterministicPlan.positive_findings,
      });

      aiResponse = await withTimeout(
        base44.integrations.Core.InvokeLLM({
          prompt,
          response_json_schema: responseSchema(),
        }),
        25000,
        "AI review"
      );
    } catch {
      const fallback = withFrontendCompatibility({
        merged: deterministicPlan,
        pages: finalPages,
        health_score,
      });

      return Response.json({
        success: true,
        ai_review_warning:
          "AI review was unavailable, so SEO Autopilot used its rule-based review instead.",
        ...fallback,
      });
    }

    const merged = mergeAiIntoPlan({
      aiResponse,
      deterministicPlan,
      canonicalFixes,
    });

    return Response.json({
      success: true,
      ...withFrontendCompatibility({
        merged,
        pages: finalPages,
        health_score,
      }),
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

/* ------------------------- Compatibility output ------------------------ */

function withFrontendCompatibility({ merged, pages, health_score }) {
  const cleanedFixes = Array.isArray(merged.cleaned_fixes)
    ? merged.cleaned_fixes
    : [];

  const competitorInsights = Array.isArray(merged.competitor_insights)
    ? merged.competitor_insights
    : [];

  const topActions = Array.isArray(merged.top_recommended_actions)
    ? merged.top_recommended_actions
    : [];

  const score =
    typeof health_score === "number"
      ? health_score
      : calculateFallbackScore(cleanedFixes);

  return {
    ...merged,

    raw_fixes: cleanedFixes,
    fixes: cleanedFixes,
    findings: cleanedFixes,
    recommendations: cleanedFixes,

    scan_summary: {
      score,
      status_label:
        score >= 80
          ? "Strong"
          : score >= 60
            ? "Good start"
            : score >= 40
              ? "Needs work"
              : "Needs urgent attention",
      plain_english_summary: merged.plain_english_summary,
      pages_scanned: pages.length,
      pages_failed: pages.filter((page) =>
        String(page.status || page.status_code || "").toLowerCase().includes("fail")
      ).length,
      high_priority_count: cleanedFixes.filter((fix) =>
        ["critical", "high"].includes(fix.priority)
      ).length,
      competitor_gap_count: competitorInsights.length,
      positive_findings: (merged.positive_findings || []).join(" "),
    },

    recommended_actions: topActions.map((action) => {
      const fix = cleanedFixes.find((item) => item.id === action.fix_id);

      return {
        fix_id: action.fix_id,
        title: action.title || fix?.issue_title || "Recommended action",
        plain_english_summary:
          fix?.plain_english_explanation || action.reason || "",
        why_it_matters: fix?.why_it_matters || action.reason || "",
        what_to_do_steps: fix?.what_to_do || [],
        who_can_do_this:
          fix?.who_can_do_this === "your_web_person"
            ? "Your web person"
            : "You",
        time_estimate: fix?.estimated_time || "",
        priority: action.priority || fix?.priority || "medium",
        affected_pages: fix?.affected_pages || [],
      };
    }),

    competitor_insights: competitorInsights.map((insight) => ({
      title: insight.headline || insight.title || "Competitor opportunity",
      headline: insight.headline || insight.title || "Competitor opportunity",
      competitor_name: insight.competitor_name || "",
      competitor_domain: insight.competitor_domain || insight.competitor_name || "",
      evidence: insight.evidence || "",
      recommended_action: insight.what_to_add || insight.recommended_action || "",
      what_to_add: insight.what_to_add || insight.recommended_action || "",
      related_user_page: insight.target_page || "/",
      target_page: insight.target_page || "/",
      gap_type: "competitor_gap",
    })),

    pages,
  };
}

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}

/* ------------------------- Canonical fix prep -------------------------- */

function prepareFixes(rawFixes) {
  const safe = Array.isArray(rawFixes) ? rawFixes : [];

  const filtered = safe.filter((fix) => {
    const pageUrl = String(fix.page_url || fix.url || "").toLowerCase();

    const isUtilityPage = UTILITY_PAGE_WORDS.some((word) =>
      pageUrl.includes(word)
    );

    const isBrokenPage =
      fix.category === "404_error" ||
      fix.category === "broken_page" ||
      fix.category === "internal_link" ||
      String(fix.issue_title || fix.title || "").toLowerCase().includes("broken");

    if (isUtilityPage && !isBrokenPage) return false;

    return true;
  });

  return dedupeFixesById(filtered.map(normalizeFix))
    .sort(compareFixes)
    .slice(0, 20);
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

  const difficulty = safeDifficulty(fix.difficulty, safeStatus(status));

  const normalized = {
    page_url: cleanPath(fix.page_url || fix.url || "/"),
    category,
    customer_category:
      fix.customer_category ||
      friendlyCategory(category) ||
      "Website improvement",
    issue_title: fix.issue_title || fix.title || defaultTitle(category),
    plain_english_explanation:
      fix.plain_english_explanation ||
      fix.explanation ||
      fix.description ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      fix.why_it_matters ||
      fix.why ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: stringifyValue(fix.current_value || fix.current || ""),
    recommended_value:
      stringifyValue(
        fix.recommended_value || fix.recommendation || fix.suggested_fix || ""
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
    difficulty,
    status: safeStatus(status),
    can_auto_fix: status === "auto_fixed" || fix.can_auto_fix === true,
    requires_approval:
      status === "needs_approval" || fix.requires_approval === true,
    requires_developer:
      status === "needs_developer" || fix.requires_developer === true,
    affected_pages: Array.isArray(fix.affected_pages)
      ? fix.affected_pages.map(cleanPath).filter(Boolean)
      : [],
    details: fix.details && typeof fix.details === "object" ? fix.details : {},
    confidence_score:
      typeof fix.confidence_score === "number" ? fix.confidence_score : 90,
    what_to_do: Array.isArray(fix.what_to_do)
      ? fix.what_to_do.slice(0, 4).map((step) => String(step))
      : Array.isArray(fix.fix_steps)
        ? fix.fix_steps.slice(0, 4).map((step) => String(step))
        : [],
    who_can_do_this:
      fix.who_can_do_this === "you" || fix.who_can_do_this === "your_web_person"
        ? fix.who_can_do_this
        : defaultOwner(difficulty),
    estimated_time: fix.estimated_time || fix.time_estimate || defaultTime(difficulty),
  };

  normalized.id = fix.id || fix.fix_id || stableId(buildIntentKey(normalized));

  return normalized;
}

function dedupeFixesById(fixes) {
  const seen = new Set();
  const output = [];

  for (const fix of fixes || []) {
    if (seen.has(fix.id)) continue;
    seen.add(fix.id);
    output.push(fix);
  }

  return output;
}

function buildIntentKey(fix) {
  const title = String(fix.issue_title || "").toLowerCase();

  if (fix.category === "canonical") return "site|canonical|preferred-pages";

  if (fix.category === "web_dev" && /placeholder|numbers/i.test(title)) {
    return "site|web_dev|placeholder";
  }

  if (fix.category === "duplicate_content") {
    return `site|duplicate_content|${title}`;
  }

  if (fix.customer_category === "Competitor opportunities") {
    return `site|competitor|${title}`;
  }

  if (fix.affected_pages?.length > 1) {
    return `site|${fix.category}|${title}`;
  }

  return `${fix.page_url}|${fix.category}|${title}`;
}

function compareFixes(a, b) {
  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const statusOrder = {
    needs_approval: 0,
    auto_fixed: 1,
    needs_developer: 2,
    open: 3,
  };

  const priorityDiff =
    (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
  if (priorityDiff !== 0) return priorityDiff;

  const statusDiff = (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
  if (statusDiff !== 0) return statusDiff;

  const titleDiff = String(a.issue_title || "").localeCompare(
    String(b.issue_title || "")
  );
  if (titleDiff !== 0) return titleDiff;

  return String(a.page_url || "").localeCompare(String(b.page_url || ""));
}

/* ------------------------- Deterministic plan -------------------------- */

function buildDeterministicPlan({
  canonicalFixes,
  crawled_pages,
  comparison,
  client_rendering,
  crawl_warnings,
}) {
  const positiveFindings = buildPositiveFindings(crawled_pages);
  const competitorInsights = buildDeterministicInsights(comparison);

  const topActions = canonicalFixes.slice(0, 5).map((fix) => ({
    fix_id: fix.id,
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

  if (canonicalFixes.length > 0) {
    summaryParts.push(
      `The main opportunities are ${describeFixTypes(canonicalFixes)}.`
    );
  } else {
    summaryParts.push(
      "No major issues stood out from the pages we could access."
    );
  }

  if (comparison?.competitors_compared?.length) {
    summaryParts.push(
      `We also compared your pages against ${comparison.competitors_compared.length} competitor page${comparison.competitors_compared.length === 1 ? "" : "s"} found on Google.`
    );
  }

  if (client_rendering?.detected) {
    summaryParts.push(
      "Part of your site loads its content with scripts, so this review is based on what search engines can read first."
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
    cleaned_fixes: canonicalFixes,
    competitor_insights: competitorInsights,
    grouped_page_recommendations: [],
    ignored_low_value_pages: [],
    positive_findings: positiveFindings,
    ai_rewrites_applied: 0,
  };
}

function buildDeterministicInsights(comparison) {
  if (!comparison) return [];

  const insights = [];
  const depth = comparison.content_depth || {};
  const faq = comparison.faq_coverage || {};

  if (
    depth.competitor_median_words > 0 &&
    depth.your_median_words > 0 &&
    depth.competitor_median_words >= depth.your_median_words * 2
  ) {
    insights.push({
      headline: "Competitor pages go much deeper than yours",
      competitor_name: topCompetitorName(comparison),
      evidence: `Typical competitor page: about ${depth.competitor_median_words} words. Typical important page on your site: about ${depth.your_median_words} words.`,
      what_to_add:
        "Expand your key service pages with process steps, pricing context, eligibility or requirements, and proof points.",
      target_page: "/",
    });
  }

  if ((faq.competitors_with_faq || 0) >= 2 && (faq.your_pages_with_faq || 0) === 0) {
    insights.push({
      headline: "Competitors answer customer questions — you don’t yet",
      competitor_name: topCompetitorName(comparison),
      evidence: `${faq.competitors_with_faq} of ${faq.competitors_measured} competitor pages include a question-and-answer section. Example questions they answer: ${(faq.competitor_faq_examples || []).slice(0, 3).join(" ")}`,
      what_to_add:
        "Add 4–6 real customer questions and answers to your key service pages.",
      target_page: "/",
    });
  }

  for (const gap of (comparison.topic_gaps || []).slice(0, 3)) {
    insights.push({
      headline: `Competitors cover “${gap.topic}” — your pages don’t`,
      competitor_name: gap.competitors?.[0] || "",
      evidence: gap.serp_position
        ? `Found on ${gap.competitors.length} competitor page${gap.competitors.length === 1 ? "" : "s"}, including one at position ${gap.serp_position} on Google for “${gap.keyword}”.`
        : `Found on ${gap.competitors.length} competitor page${gap.competitors.length === 1 ? "" : "s"}.`,
      what_to_add: `Add a “${gap.topic}” section where it genuinely fits your services.`,
      target_page: "/",
    });
  }

  if ((comparison.schema_gaps || []).length > 0) {
    insights.push({
      headline: "Competitors use structured business information you may be missing",
      competitor_name: topCompetitorName(comparison),
      evidence: `Missing structured information types found on competitor pages: ${comparison.schema_gaps.slice(0, 5).join(", ")}.`,
      what_to_add:
        "Ask your website platform or developer to add relevant structured business information to key pages.",
      target_page: "/",
    });
  }

  if ((comparison.trust_signal_gaps || []).length >= 3) {
    insights.push({
      headline: "Competitors show more trust proof",
      competitor_name: topCompetitorName(comparison),
      evidence: `Competitor pages mention trust signals such as ${comparison.trust_signal_gaps.slice(0, 4).join(", ")}.`,
      what_to_add:
        "Add real proof points such as reviews, credentials, guarantees, project numbers, or case studies where relevant.",
      target_page: "/",
    });
  }

  return insights.slice(0, 6);
}

function topCompetitorName(comparison) {
  return comparison?.competitors_compared?.[0]?.name || "";
}

/* ------------------------------- Merge --------------------------------- */

function mergeAiIntoPlan({ aiResponse, deterministicPlan, canonicalFixes }) {
  const validIds = new Set(canonicalFixes.map((fix) => fix.id));
  const rewrites = new Map();

  for (const rewrite of aiResponse?.fix_rewrites || []) {
    if (rewrite && validIds.has(rewrite.fix_id)) {
      rewrites.set(rewrite.fix_id, rewrite);
    }
  }

  const cleaned_fixes = canonicalFixes.map((fix) => {
    const rewrite = rewrites.get(fix.id);
    if (!rewrite) return fix;

    const steps =
      Array.isArray(rewrite.what_to_do) && rewrite.what_to_do.length > 0
        ? rewrite.what_to_do.slice(0, 4).map((step) => String(step))
        : fix.what_to_do;

    return {
      ...fix,
      issue_title: safeString(rewrite.issue_title, fix.issue_title),
      plain_english_explanation: safeString(
        rewrite.plain_english_explanation,
        fix.plain_english_explanation
      ),
      why_it_matters: safeString(rewrite.why_it_matters, fix.why_it_matters),
      what_to_do: steps,
      who_can_do_this:
        rewrite.who_can_do_this === "you" ||
        rewrite.who_can_do_this === "your_web_person"
          ? rewrite.who_can_do_this
          : fix.who_can_do_this,
      estimated_time: safeString(rewrite.estimated_time, fix.estimated_time),
      ai_recommendation:
        steps.length > 0 ? steps.join(" ") : fix.ai_recommendation,
    };
  });

  const topActions =
    Array.isArray(aiResponse?.top_recommended_actions) &&
    aiResponse.top_recommended_actions.length > 0
      ? aiResponse.top_recommended_actions
          .slice(0, 5)
          .map((action) => ({
            fix_id: validIds.has(action?.fix_id) ? action.fix_id : "",
            title: safeString(action?.title, ""),
            reason: safeString(action?.reason, ""),
            priority: ["high", "medium", "low"].includes(action?.priority)
              ? action.priority
              : "medium",
          }))
          .filter((action) => action.title)
      : deterministicPlan.top_recommended_actions;

  const insights =
    Array.isArray(aiResponse?.competitor_insights) &&
    aiResponse.competitor_insights.length > 0
      ? aiResponse.competitor_insights
          .slice(0, 6)
          .map((insight) => ({
            headline: safeString(insight?.headline, ""),
            competitor_name: safeString(insight?.competitor_name, ""),
            evidence: safeString(insight?.evidence, ""),
            what_to_add: safeString(insight?.what_to_add, ""),
            target_page: safeString(insight?.target_page, "/"),
          }))
          .filter((insight) => insight.headline && insight.evidence)
      : deterministicPlan.competitor_insights;

  const positives =
    Array.isArray(aiResponse?.positive_findings) &&
    aiResponse.positive_findings.length > 0
      ? aiResponse.positive_findings.slice(0, 5).map((item) => String(item))
      : deterministicPlan.positive_findings;

  return {
    plain_english_summary: safeString(
      aiResponse?.plain_english_summary,
      deterministicPlan.plain_english_summary
    ),
    top_recommended_actions: topActions,
    cleaned_fixes,
    competitor_insights: insights,
    grouped_page_recommendations: [],
    ignored_low_value_pages: [],
    positive_findings: positives,
    ai_rewrites_applied: rewrites.size,
  };
}

/* --------------------------- Prompt building --------------------------- */

function buildSiteProfile(pages) {
  return (Array.isArray(pages) ? pages : [])
    .filter((page) => page.is_important_page && !page.is_utility_page)
    .slice(0, 15)
    .map((page) => ({
      page: cleanPath(page.url || "/"),
      title: String(page.title || "").slice(0, 90),
      h1: String(page.h1 || "").slice(0, 90),
      word_count: page.word_count || 0,
      has_faq: Boolean(page.has_faq),
      trust_signal_count: Array.isArray(page.trust_signals)
        ? page.trust_signals.length
        : 0,
      cta_count: Array.isArray(page.cta_phrases) ? page.cta_phrases.length : 0,
      is_service_like: Boolean(page.is_service_like),
      likely_client_rendered: Boolean(page.likely_client_rendered),
    }));
}

function trimSnapshots(snapshots) {
  return (Array.isArray(snapshots) ? snapshots : [])
    .filter((item) => item.status_code >= 200 && item.status_code < 400)
    .slice(0, 3)
    .map((item) => ({
      competitor_name: item.competitor_name,
      keyword: item.keyword,
      serp_position: item.serp_position,
      title: String(item.title || "").slice(0, 100),
      h1: String(item.h1 || "").slice(0, 100),
      h2s: Array.isArray(item.h2s) ? item.h2s.slice(0, 8) : [],
      word_count: item.word_count || 0,
      has_faq: Boolean(item.has_faq),
      faq_questions: Array.isArray(item.faq_questions)
        ? item.faq_questions.slice(0, 5)
        : [],
      trust_signals: item.trust_signals || [],
      cta_phrases: item.cta_phrases || [],
    }));
}

function compactFixForPrompt(fix) {
  const details = fix.details || {};
  const compactDetails = {};

  if (details.content_depth) compactDetails.content_depth = details.content_depth;

  if (details.faq_coverage) {
    compactDetails.faq_coverage = {
      ...details.faq_coverage,
      competitor_faq_examples: (
        details.faq_coverage.competitor_faq_examples || []
      ).slice(0, 5),
    };
  }

  if (Array.isArray(details.topic_gaps)) {
    compactDetails.topic_gaps = details.topic_gaps.slice(0, 6);
  }

  if (details.schema_gaps) compactDetails.schema_gaps = details.schema_gaps;

  if (details.trust_signal_gaps) {
    compactDetails.trust_signal_gaps = details.trust_signal_gaps;
  }

  if (Array.isArray(details.examples)) {
    compactDetails.examples = details.examples.slice(0, 3);
  }

  if (details.technical_term) {
    compactDetails.technical_term = details.technical_term;
  }

  return {
    fix_id: fix.id,
    issue_title: fix.issue_title,
    category: fix.category,
    customer_category: fix.customer_category,
    priority: fix.priority,
    status: fix.status,
    difficulty: fix.difficulty,
    current_value: clampText(fix.current_value, 200),
    recommended_value: clampText(fix.recommended_value, 240),
    affected_page_count: (fix.affected_pages || []).length,
    example_pages: (fix.affected_pages || []).slice(0, 3),
    details: compactDetails,
  };
}

function buildPrompt({
  business_name,
  business_type,
  city,
  website_url,
  scan_mode,
  crawl_warnings,
  canonicalFixes,
  siteProfile,
  comparison,
  snapshots,
  client_rendering,
  positives,
}) {
  return `
You are the AI explainer inside SEO Autopilot, an SEO tool for non-technical small business owners.

A rule-based scanner has already decided what the findings are. Your job is to make each finding easy to understand and act on — not to change what was found.

Hard rules:
1. The findings list is final. Do not add, remove, merge, or reorder findings. Only return rewrites keyed by the exact fix_id values in the list.
2. Never invent a fix_id.
3. Never claim anything was fixed, changed, or published. Use "prepared", "recommended", "review", "may help", "next step".
4. Never promise rankings or traffic.
5. Competitor facts must come only from the competitor data below. You may say a competitor page "was found at position N on Google for 'keyword'". Never say a competitor outranks this website — this website's own positions were not measured.
6. Plain English only. Translate jargon: meta title -> search title, meta description -> search description, canonical -> preferred-page setting, schema -> structured business information / trust signals, noindex -> hidden from search engines.
7. what_to_do must be 2–4 short imperative steps a busy owner can follow or hand to their web person.
8. who_can_do_this is "you" when the owner can do it in a typical website editor. Use "your_web_person" when it needs code, platform settings, redirects, schema, or rendering changes.
9. estimated_time is a rough human estimate like "about 15 minutes" or "an hour with your web person".
10. competitor_insights: 3–6 items maximum, each grounded in a specific number, section, or question from the competitor data. Fill the evidence field with that specific fact.
11. positive_findings: 3–5 short, factual sentences. Show what the site already does well before the cleanup list.

Business name: ${business_name || "(not provided)"}
Business type: ${business_type || "(not provided)"}
City or service area: ${city || "(not provided)"}
Website: ${website_url}
Scan mode: ${scan_mode}

Crawl warnings:
${JSON.stringify(crawl_warnings || [], null, 2)}

Client-side rendering check:
${JSON.stringify(client_rendering || { detected: false }, null, 2)}

Findings (final — rewrite only, keyed by fix_id):
${JSON.stringify((canonicalFixes || []).map(compactFixForPrompt), null, 2)}

Your site profile (top important pages):
${JSON.stringify(siteProfile || [], null, 2)}

Competitor comparison (deterministic deltas):
${JSON.stringify(comparison || null, null, 2)}

Competitor page snapshots (top 3, trimmed):
${JSON.stringify(snapshots || [], null, 2)}

Suggested positives (keep or improve):
${JSON.stringify(positives || [], null, 2)}

Return JSON only.
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
            fix_id: { type: "string" },
            title: { type: "string" },
            reason: { type: "string" },
            priority: { type: "string", enum: ["high", "medium", "low"] },
          },
          required: ["title", "reason", "priority"],
        },
      },
      fix_rewrites: {
        type: "array",
        items: {
          type: "object",
          properties: {
            fix_id: { type: "string" },
            issue_title: { type: "string" },
            plain_english_explanation: { type: "string" },
            why_it_matters: { type: "string" },
            what_to_do: {
              type: "array",
              items: { type: "string" },
            },
            who_can_do_this: {
              type: "string",
              enum: ["you", "your_web_person"],
            },
            estimated_time: { type: "string" },
          },
          required: [
            "fix_id",
            "issue_title",
            "plain_english_explanation",
            "why_it_matters",
            "what_to_do",
            "who_can_do_this",
            "estimated_time",
          ],
        },
      },
      competitor_insights: {
        type: "array",
        items: {
          type: "object",
          properties: {
            headline: { type: "string" },
            competitor_name: { type: "string" },
            evidence: { type: "string" },
            what_to_add: { type: "string" },
            target_page: { type: "string" },
          },
          required: ["headline", "evidence", "what_to_add"],
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
      "fix_rewrites",
      "competitor_insights",
      "positive_findings",
    ],
  };
}

/* ------------------------------ Positives ------------------------------ */

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

  if (fixes.some((fix) => fix.category === "js_rendering")) {
    labels.push("how the site loads its content");
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
    fixes.some((fix) => fix.customer_category === "Competitor opportunities")
  ) {
    labels.push("competitor content opportunities");
  }

  if (labels.length === 0) return "a few website cleanup items";
  if (labels.length === 1) return labels[0];

  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

/* ------------------------------- Helpers ------------------------------- */

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

function defaultOwner(difficulty) {
  return difficulty === "developer" ? "your_web_person" : "you";
}

function defaultTime(difficulty) {
  if (difficulty === "easy") return "about 10–15 minutes";
  if (difficulty === "moderate") return "about 30–60 minutes";
  return "a task for your web person";
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
    js_rendering: "Website setup",
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
    js_rendering: "Review how the site loads its content",
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

function safeString(value, fallback) {
  if (typeof value === "string" && value.trim()) return value.trim();
  return fallback;
}

function clampText(value, max) {
  const text = String(value || "").trim();
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 1)).trim();
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

function calculateFallbackScore(fixes) {
  let score = 100;

  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
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