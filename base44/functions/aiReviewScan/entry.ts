import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const CATEGORY_MAP: Record<string, string> = {
  broken_page: "404_error",
  page_heading: "thin_content",
  placeholder_text: "web_dev",
  faq_gap: "thin_content",
  cta_gap: "thin_content",
  trust_signal_gap: "schema",
  image_alt_text: "web_dev",
  duplicate_search_titles: "duplicate_content",
  duplicate_search_descriptions: "duplicate_content",
  duplicate_description: "duplicate_content",
  competitor_gap: "thin_content",
  mobile_setup: "web_dev",
  performance_hint: "performance",
  social_metadata: "web_dev",
  indexability: "robots_txt",
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

    const websiteUrl = body.website_url || body.normalized_url || "";
    const pages = pickFirstNonEmptyArray([
      body.crawled_pages,
      body.pages,
      body.scanned_pages,
      body.crawl_pages,
    ]);

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

    const fallbackPlan = buildFallbackPlan({
      body,
      pages,
      canonicalFixes,
    });

    if (!websiteUrl) {
      return Response.json({
        success: true,
        ai_review_warning:
          "AI review ran, but website_url was missing. Scanner recommendations are shown.",
        ...fallbackPlan,
      });
    }

    if (canonicalFixes.length === 0) {
      return Response.json({
        success: true,
        ai_review_warning:
          "AI review ran, but no scanner recommendations were provided.",
        ...fallbackPlan,
      });
    }

    if (!base44.integrations?.Core?.InvokeLLM) {
      return Response.json({
        success: true,
        ai_review_warning:
          "AI review is reachable, but InvokeLLM is not available. Scanner recommendations are shown.",
        ...fallbackPlan,
      });
    }

    try {
      const prompt = buildPrompt({
        body,
        websiteUrl,
        pages,
        canonicalFixes,
        fallbackPlan,
      });

      const rawAiResponse = await withTimeout(
        base44.integrations.Core.InvokeLLM({
          prompt,
          response_json_schema: responseSchema(),
        }),
        25000,
        "AI review"
      );

      const aiResponse = unwrapAiResponse(rawAiResponse);

      const merged = mergeAiIntoFallback({
        aiResponse,
        fallbackPlan,
        canonicalFixes,
        pages,
      });

      return Response.json({
        success: true,
        ...merged,
      });
    } catch (error) {
      return Response.json({
        success: true,
        ai_review_warning:
          error?.message ||
          "AI review failed, so scanner recommendations are shown.",
        ...fallbackPlan,
      });
    }
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "runAiReview failed",
        stack: error?.stack || "",
      },
      { status: 500 }
    );
  }
});

/* -------------------------------------------------------------------------- */
/* Core normalization                                                          */
/* -------------------------------------------------------------------------- */

function pickFirstNonEmptyArray(values: unknown[]) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) {
      return value;
    }
  }

  return [];
}

function prepareFixes(rawFixes: any[]) {
  return dedupeByFixId(
    (Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) =>
      normalizeFix(fix, index)
    )
  )
    .sort(compareFixes)
    .slice(0, 40);
}

function normalizeFix(fix: any, index: number) {
  const rawCategory = String(fix?.category || fix?.type || "web_dev");
  const category = CATEGORY_MAP[rawCategory] || rawCategory || "web_dev";

  const pageUrl =
    cleanPath(fix?.page_url || fix?.url || fix?.affected_pages?.[0] || "/") ||
    "/";

  const affectedPages = normalizeAffectedPages(fix, pageUrl);

  const status = normalizeStatus(
    fix?.status ||
      (fix?.requires_developer
        ? "needs_developer"
        : fix?.requires_approval
          ? "needs_approval"
          : fix?.can_auto_fix
            ? "auto_fixed"
            : "needs_approval")
  );

  const difficulty = normalizeDifficulty(fix?.difficulty, status);

  const title =
    cleanString(
      fix?.issue_title || fix?.title || fix?.headline || defaultTitle(category)
    ) || defaultTitle(category);

  const explanation =
    cleanString(
      fix?.plain_english_explanation ||
        fix?.plain_english_summary ||
        fix?.explanation ||
        fix?.summary ||
        fix?.description
    ) || "This recommendation was found during the website scan.";

  const why =
    cleanString(fix?.why_it_matters || fix?.why || fix?.reason) ||
    "Improving this can help visitors and search engines understand the website more clearly.";

  const recommendedValue =
    stringifyValue(
      fix?.recommended_value ||
        fix?.recommendation ||
        fix?.suggested_fix ||
        fix?.ai_recommendation ||
        fix?.recommended_action
    ) || "Review this recommendation.";

  const steps =
    normalizeSteps(fix) ||
    defaultSteps({
      category,
      difficulty,
      recommendedValue,
    });

  const normalized = {
    ...fix,

    id:
      fix?.id ||
      fix?.fix_id ||
      stableId(`${pageUrl}|${category}|${title}|${index}`),

    fix_id:
      fix?.fix_id ||
      fix?.id ||
      stableId(`${pageUrl}|${category}|${title}|${index}`),

    type: fix?.type || "site_level",

    page_url: pageUrl,

    category,
    customer_category:
      cleanString(fix?.customer_category) || friendlyCategory(category),

    issue_title: title,
    title,

    plain_english_explanation: explanation,
    plain_english_summary: explanation,

    why_it_matters: why,

    current_value: stringifyValue(
      fix?.current_value ||
        fix?.current ||
        fix?.technical_detail ||
        fix?.detected_value ||
        ""
    ),

    recommended_value: recommendedValue,
    ai_recommendation: recommendedValue,

    priority: normalizePriority(fix?.priority),
    difficulty,
    status,

    can_auto_fix: status === "auto_fixed" || fix?.can_auto_fix === true,
    requires_approval:
      status === "needs_approval" || fix?.requires_approval === true,
    requires_developer:
      status === "needs_developer" || fix?.requires_developer === true,

    affected_pages: affectedPages,

    details:
      fix?.details && typeof fix.details === "object" ? fix.details : {},

    confidence_score:
      typeof fix?.confidence_score === "number" ? fix.confidence_score : 90,

    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,

    who_can_do_this:
      fix?.who_can_do_this === "you" ||
      fix?.who_can_do_this === "your_web_person"
        ? fix.who_can_do_this
        : defaultOwner(difficulty),

    estimated_time:
      cleanString(fix?.estimated_time || fix?.time_estimate) ||
      defaultTime(difficulty),

    time_estimate:
      cleanString(fix?.time_estimate || fix?.estimated_time) ||
      defaultTime(difficulty),
  };

  normalized.fix_id = normalized.id;

  return normalized;
}

function normalizeAffectedPages(fix: any, fallbackPage: string) {
  const rawPages = Array.isArray(fix?.affected_pages)
    ? fix.affected_pages
    : Array.isArray(fix?.pages)
      ? fix.pages
      : fix?.page_url
        ? [fix.page_url]
        : [fallbackPage];

  return Array.from(
    new Set(rawPages.map((item) => cleanPath(item)).filter(Boolean))
  ).slice(0, 150);
}

function normalizeSteps(fix: any) {
  const possible = [
    fix?.what_to_do,
    fix?.what_to_do_steps,
    fix?.fix_steps,
    fix?.steps,
  ];

  for (const value of possible) {
    if (Array.isArray(value) && value.length > 0) {
      return value.slice(0, 5).map((item) => String(item).trim()).filter(Boolean);
    }
  }

  return null;
}

function dedupeByFixId(fixes: any[]) {
  const seen = new Set<string>();
  const output = [];

  for (const fix of fixes || []) {
    const key = String(fix?.id || fix?.fix_id || "");

    if (!key || seen.has(key)) continue;

    seen.add(key);
    output.push(fix);
  }

  return output;
}

function compareFixes(a: any, b: any) {
  const priorityOrder: Record<string, number> = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };

  const statusOrder: Record<string, number> = {
    needs_approval: 0,
    auto_fixed: 1,
    needs_developer: 2,
    open: 3,
  };

  const priorityDiff =
    (priorityOrder[a?.priority] ?? 9) - (priorityOrder[b?.priority] ?? 9);

  if (priorityDiff !== 0) return priorityDiff;

  const statusDiff =
    (statusOrder[a?.status] ?? 9) - (statusOrder[b?.status] ?? 9);

  if (statusDiff !== 0) return statusDiff;

  return String(a?.issue_title || "").localeCompare(
    String(b?.issue_title || "")
  );
}

/* -------------------------------------------------------------------------- */
/* Fallback plan                                                               */
/* -------------------------------------------------------------------------- */

function buildFallbackPlan({
  body,
  pages,
  canonicalFixes,
}: {
  body: any;
  pages: any[];
  canonicalFixes: any[];
}) {
  const score =
    typeof body?.health_score === "number"
      ? body.health_score
      : typeof body?.scan_summary?.score === "number"
        ? body.scan_summary.score
        : calculateFallbackScore(canonicalFixes);

  const positiveFindings = buildPositiveFindings({
    body,
    pages,
  });

  const competitorInsights = buildCompetitorInsights(body);

  const topRecommendedActions = canonicalFixes.slice(0, 5).map((fix) => ({
    fix_id: fix.id,
    title: fix.issue_title,
    reason: fix.why_it_matters,
    priority:
      fix.priority === "critical" || fix.priority === "high"
        ? "high"
        : fix.priority === "low"
          ? "low"
          : "medium",
  }));

  const summaryParts = [];

  if (positiveFindings.length > 0) {
    summaryParts.push(
      `The scan found a working SEO foundation. ${positiveFindings[0]}`
    );
  } else {
    summaryParts.push(
      "The scan completed and found several practical website improvements."
    );
  }

  if (canonicalFixes.length > 0) {
    summaryParts.push(
      `The main priorities are ${describeFixTypes(canonicalFixes)}.`
    );
  } else {
    summaryParts.push(
      "No major recommendations were returned from the scanner."
    );
  }

  if (Array.isArray(body?.competitor_page_snapshots)) {
    const count = body.competitor_page_snapshots.length;

    if (count > 0) {
      summaryParts.push(
        `The scan also reviewed ${count} competitor page${count === 1 ? "" : "s"}.`
      );
    }
  }

  if (body?.technical_audit_summary) {
    const techCount =
      Number(body?.technical_audit_summary?.non_indexable_pages || 0) +
      Number(body?.technical_audit_summary?.canonical_issue_count || 0) +
      Number(body?.technical_audit_summary?.multiple_h1_count || 0) +
      Number(body?.technical_audit_summary?.heavy_page_count || 0);

    if (techCount > 0) {
      summaryParts.push(
        "The technical audit also found setup items worth reviewing."
      );
    }
  }

  if (Array.isArray(body?.crawl_warnings) && body.crawl_warnings.length > 0) {
    summaryParts.push(
      "Some checks were limited, so recommendations are based on the pages the scanner could access."
    );
  }

  return makeFrontendCompatible({
    plain_english_summary: summaryParts.join(" "),
    top_recommended_actions: topRecommendedActions,
    recommended_actions: [],
    cleaned_fixes: canonicalFixes,
    raw_fixes: canonicalFixes,
    fixes: canonicalFixes,
    findings: canonicalFixes,
    recommendations: canonicalFixes,
    competitor_insights: competitorInsights,
    grouped_page_recommendations: [],
    ignored_low_value_pages: [],
    positive_findings: positiveFindings,
    ai_rewrites_applied: 0,
    crawled_pages: pages,
    pages,
    health_score: score,
    technical_audit_summary: body?.technical_audit_summary || null,
    screaming_frog_lite_enabled: Boolean(body?.screaming_frog_lite_enabled),
    audit_profile: body?.audit_profile || "",
  });
}

function makeFrontendCompatible(plan: any) {
  const cleanedFixes = Array.isArray(plan.cleaned_fixes)
    ? plan.cleaned_fixes
    : [];

  const pages = Array.isArray(plan.crawled_pages)
    ? plan.crawled_pages
    : Array.isArray(plan.pages)
      ? plan.pages
      : [];

  const score =
    typeof plan.health_score === "number"
      ? plan.health_score
      : calculateFallbackScore(cleanedFixes);

  const topRecommendedActions = Array.isArray(plan.top_recommended_actions)
    ? plan.top_recommended_actions
    : [];

  const recommendedActions =
    Array.isArray(plan.recommended_actions) && plan.recommended_actions.length > 0
      ? plan.recommended_actions
      : topRecommendedActions.map((action: any) => {
          const fix = cleanedFixes.find(
            (item: any) => item.id === action.fix_id || item.fix_id === action.fix_id
          );

          return {
            fix_id: action.fix_id || fix?.id || "",
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
        });

  return {
    ...plan,

    health_score: score,

    cleaned_fixes: cleanedFixes,

    raw_fixes: cleanedFixes,
    fixes: cleanedFixes,
    findings: cleanedFixes,
    recommendations: cleanedFixes,

    top_recommended_actions: topRecommendedActions,
    recommended_actions: recommendedActions,

    competitor_insights: Array.isArray(plan.competitor_insights)
      ? plan.competitor_insights
      : [],

    crawled_pages: pages,
    pages,

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

      plain_english_summary:
        plan.plain_english_summary ||
        "The scan completed. Review the recommended improvements below.",

      pages_scanned: pages.length,

      pages_failed: pages.filter((page: any) => {
        const status = Number(page?.status_code || 0);
        return status >= 400 || status === 0 || page?.fetch_error;
      }).length,

      high_priority_count: cleanedFixes.filter((fix: any) =>
        ["critical", "high"].includes(fix.priority)
      ).length,

      competitor_gap_count: cleanedFixes.filter(
        (fix: any) =>
          fix.category === "competitor_gap" ||
          fix.customer_category === "Competitor opportunities"
      ).length,

      technical_issue_count: cleanedFixes.filter(
        (fix: any) => fix.customer_category === "Technical SEO"
      ).length,

      positive_findings: Array.isArray(plan.positive_findings)
        ? plan.positive_findings.join(" ")
        : "",
    },
  };
}

/* -------------------------------------------------------------------------- */
/* AI merge                                                                    */
/* -------------------------------------------------------------------------- */

function unwrapAiResponse(response: any) {
  if (!response) return {};

  if (typeof response === "string") {
    try {
      return JSON.parse(response);
    } catch {
      return {};
    }
  }

  if (response?.data?.data) return response.data.data;
  if (response?.data?.result) return response.data.result;
  if (response?.data) return response.data;
  if (response?.result?.data) return response.result.data;
  if (response?.result) return response.result;

  return response;
}

function mergeAiIntoFallback({
  aiResponse,
  fallbackPlan,
  canonicalFixes,
  pages,
}: {
  aiResponse: any;
  fallbackPlan: any;
  canonicalFixes: any[];
  pages: any[];
}) {
  const validIds = new Set(canonicalFixes.map((fix) => fix.id));
  const rewrites = new Map<string, any>();

  for (const rewrite of aiResponse?.fix_rewrites || []) {
    if (rewrite?.fix_id && validIds.has(rewrite.fix_id)) {
      rewrites.set(rewrite.fix_id, rewrite);
    }
  }

  const cleanedFixes = canonicalFixes.map((fix) => {
    const rewrite = rewrites.get(fix.id);

    if (!rewrite) return fix;

    const steps =
      Array.isArray(rewrite.what_to_do) && rewrite.what_to_do.length > 0
        ? rewrite.what_to_do
            .slice(0, 5)
            .map((step: any) => String(step).trim())
            .filter(Boolean)
        : fix.what_to_do;

    return {
      ...fix,

      issue_title: cleanString(rewrite.issue_title) || fix.issue_title,
      title: cleanString(rewrite.issue_title) || fix.title || fix.issue_title,

      plain_english_explanation:
        cleanString(rewrite.plain_english_explanation) ||
        fix.plain_english_explanation,

      plain_english_summary:
        cleanString(rewrite.plain_english_explanation) ||
        fix.plain_english_summary ||
        fix.plain_english_explanation,

      why_it_matters:
        cleanString(rewrite.why_it_matters) || fix.why_it_matters,

      what_to_do: steps,
      what_to_do_steps: steps,
      fix_steps: steps,

      who_can_do_this:
        rewrite.who_can_do_this === "you" ||
        rewrite.who_can_do_this === "your_web_person"
          ? rewrite.who_can_do_this
          : fix.who_can_do_this,

      estimated_time:
        cleanString(rewrite.estimated_time) || fix.estimated_time,

      time_estimate:
        cleanString(rewrite.estimated_time) || fix.time_estimate,

      ai_recommendation:
        steps.length > 0 ? steps.join(" ") : fix.ai_recommendation,
    };
  });

  const topRecommendedActions =
    Array.isArray(aiResponse?.top_recommended_actions) &&
    aiResponse.top_recommended_actions.length > 0
      ? aiResponse.top_recommended_actions
          .slice(0, 5)
          .map((action: any) => ({
            fix_id: validIds.has(action?.fix_id) ? action.fix_id : "",
            title: cleanString(action?.title) || "",
            reason: cleanString(action?.reason) || "",
            priority: ["high", "medium", "low"].includes(action?.priority)
              ? action.priority
              : "medium",
          }))
          .filter((action: any) => action.title)
      : fallbackPlan.top_recommended_actions;

  const competitorInsights =
    Array.isArray(aiResponse?.competitor_insights) &&
    aiResponse.competitor_insights.length > 0
      ? aiResponse.competitor_insights
          .slice(0, 6)
          .map((insight: any) => ({
            headline: cleanString(insight?.headline) || "",
            title: cleanString(insight?.headline) || "",
            competitor_name: cleanString(insight?.competitor_name) || "",
            competitor_domain:
              cleanString(insight?.competitor_domain) ||
              cleanString(insight?.competitor_name) ||
              "",
            evidence: cleanString(insight?.evidence) || "",
            what_to_add: cleanString(insight?.what_to_add) || "",
            recommended_action: cleanString(insight?.what_to_add) || "",
            target_page: cleanString(insight?.target_page) || "/",
            related_user_page: cleanString(insight?.target_page) || "/",
            gap_type: "competitor_gap",
          }))
          .filter((insight: any) => insight.headline && insight.evidence)
      : fallbackPlan.competitor_insights;

  const positives =
    Array.isArray(aiResponse?.positive_findings) &&
    aiResponse.positive_findings.length > 0
      ? aiResponse.positive_findings.slice(0, 5).map((item: any) => String(item))
      : fallbackPlan.positive_findings;

  return makeFrontendCompatible({
    ...fallbackPlan,

    plain_english_summary:
      cleanString(aiResponse?.plain_english_summary) ||
      fallbackPlan.plain_english_summary,

    top_recommended_actions: topRecommendedActions,
    cleaned_fixes: cleanedFixes,
    raw_fixes: cleanedFixes,
    fixes: cleanedFixes,
    findings: cleanedFixes,
    recommendations: cleanedFixes,

    competitor_insights: competitorInsights,
    positive_findings: positives,

    ai_rewrites_applied: rewrites.size,

    crawled_pages: pages,
    pages,
  });
}

/* -------------------------------------------------------------------------- */
/* Prompt                                                                      */
/* -------------------------------------------------------------------------- */

function buildPrompt({
  body,
  websiteUrl,
  pages,
  canonicalFixes,
  fallbackPlan,
}: {
  body: any;
  websiteUrl: string;
  pages: any[];
  canonicalFixes: any[];
  fallbackPlan: any;
}) {
  return `
You are the AI review layer for SEO Autopilot.

The deterministic scanner has already found the issues. Your job is to rewrite those findings into clear, helpful, non-technical recommendations for a business owner.

Hard rules:
1. Do not add new findings.
2. Do not remove findings.
3. Do not merge findings.
4. Only rewrite findings using the exact fix_id values provided.
5. Do not invent URLs, competitors, page counts, rankings, traffic, leads, or results.
6. Do not say anything has already been fixed or published.
7. Use plain English.
8. Avoid jargon. If jargon is necessary, explain it simply.
9. what_to_do must contain 2 to 5 short action steps.
10. who_can_do_this must be either "you" or "your_web_person".
11. Competitor insights must only use competitor data provided below.

Business:
${JSON.stringify(
  {
    business_name: body?.business_name || "",
    business_type: body?.business_type || "",
    city: body?.city || "",
    website_url: websiteUrl,
    scan_mode: body?.scan_mode || "",
  },
  null,
  2
)}

Crawl warnings:
${JSON.stringify(body?.crawl_warnings || [], null, 2)}

Technical audit summary:
${JSON.stringify(body?.technical_audit_summary || null, null, 2)}

Client rendering:
${JSON.stringify(body?.client_rendering || null, null, 2)}

Scanner findings:
${JSON.stringify(canonicalFixes.map(compactFixForPrompt), null, 2)}

Important page profile:
${JSON.stringify(buildPageProfile(pages), null, 2)}

Competitor comparison:
${JSON.stringify(body?.competitor_comparison || null, null, 2)}

Competitor snapshots:
${JSON.stringify(trimCompetitorSnapshots(body?.competitor_page_snapshots || []), null, 2)}

Fallback positives:
${JSON.stringify(fallbackPlan?.positive_findings || [], null, 2)}

Return valid JSON only.
`;
}

function responseSchema() {
  return {
    type: "object",
    properties: {
      plain_english_summary: {
        type: "string",
      },
      top_recommended_actions: {
        type: "array",
        items: {
          type: "object",
          properties: {
            fix_id: { type: "string" },
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

function compactFixForPrompt(fix: any) {
  return {
    fix_id: fix.id,
    issue_title: fix.issue_title,
    category: fix.category,
    customer_category: fix.customer_category,
    priority: fix.priority,
    status: fix.status,
    difficulty: fix.difficulty,
    current_value: clampText(fix.current_value, 250),
    recommended_value: clampText(fix.recommended_value, 300),
    affected_page_count: Array.isArray(fix.affected_pages)
      ? fix.affected_pages.length
      : 0,
    example_pages: Array.isArray(fix.affected_pages)
      ? fix.affected_pages.slice(0, 8)
      : [],
    details: compactDetails(fix.details || {}),
  };
}

function compactDetails(details: any) {
  const output: any = {};

  if (details?.affected_count !== undefined) {
    output.affected_count = details.affected_count;
  }

  if (details?.technical_term) {
    output.technical_term = details.technical_term;
  }

  if (Array.isArray(details?.examples)) {
    output.examples = details.examples.slice(0, 6);
  }

  if (details?.content_depth) {
    output.content_depth = details.content_depth;
  }

  if (details?.faq_coverage) {
    output.faq_coverage = {
      ...details.faq_coverage,
      competitor_faq_examples: (
        details.faq_coverage.competitor_faq_examples || []
      ).slice(0, 6),
    };
  }

  if (Array.isArray(details?.topic_gaps)) {
    output.topic_gaps = details.topic_gaps.slice(0, 8);
  }

  if (Array.isArray(details?.schema_gaps)) {
    output.schema_gaps = details.schema_gaps.slice(0, 8);
  }

  if (Array.isArray(details?.trust_signal_gaps)) {
    output.trust_signal_gaps = details.trust_signal_gaps.slice(0, 8);
  }

  return output;
}

function buildPageProfile(pages: any[]) {
  return (Array.isArray(pages) ? pages : [])
    .filter((page) => page?.is_important_page && !page?.is_utility_page)
    .slice(0, 20)
    .map((page) => ({
      page: cleanPath(page?.url || "/"),
      status_code: page?.status_code || 0,
      indexability: page?.indexability || "",
      title: clampText(page?.title || "", 100),
      title_length: page?.title_length || 0,
      title_count: page?.title_count || 0,
      meta_description_length: page?.meta_description_length || 0,
      meta_description_count: page?.meta_description_count || 0,
      h1: clampText(page?.h1 || "", 100),
      h1_count: page?.h1_count || 0,
      word_count: page?.word_count || 0,
      internal_link_count: page?.internal_link_count || 0,
      image_count: page?.image_count || 0,
      images_missing_alt_count: page?.images_missing_alt_count || 0,
      has_faq: Boolean(page?.has_faq),
      has_schema: Boolean(page?.has_schema),
      schema_types: Array.isArray(page?.schema_types)
        ? page.schema_types.slice(0, 8)
        : [],
      trust_signal_count: Array.isArray(page?.trust_signals)
        ? page.trust_signals.length
        : 0,
      cta_count: Array.isArray(page?.cta_phrases)
        ? page.cta_phrases.length
        : 0,
      likely_client_rendered: Boolean(page?.likely_client_rendered),
      canonical_status: page?.canonical_status || "",
    }));
}

function trimCompetitorSnapshots(snapshots: any[]) {
  return (Array.isArray(snapshots) ? snapshots : [])
    .filter((item) => Number(item?.status_code || 0) >= 200)
    .slice(0, 5)
    .map((item) => ({
      competitor_name: item?.competitor_name || "",
      competitor_domain: item?.competitor_domain || "",
      keyword: item?.keyword || "",
      serp_position: item?.serp_position || null,
      title: clampText(item?.title || "", 120),
      h1: clampText(item?.h1 || "", 120),
      h2s: Array.isArray(item?.h2s) ? item.h2s.slice(0, 8) : [],
      word_count: item?.word_count || 0,
      has_faq: Boolean(item?.has_faq),
      faq_questions: Array.isArray(item?.faq_questions)
        ? item.faq_questions.slice(0, 6)
        : [],
      has_schema: Boolean(item?.has_schema),
      schema_types: Array.isArray(item?.schema_types)
        ? item.schema_types.slice(0, 8)
        : [],
      trust_signals: Array.isArray(item?.trust_signals)
        ? item.trust_signals.slice(0, 8)
        : [],
      cta_phrases: Array.isArray(item?.cta_phrases)
        ? item.cta_phrases.slice(0, 8)
        : [],
    }));
}

/* -------------------------------------------------------------------------- */
/* Positives / insights                                                        */
/* -------------------------------------------------------------------------- */

function buildPositiveFindings({ body, pages }: { body: any; pages: any[] }) {
  const positives = [];

  const safePages = Array.isArray(pages) ? pages : [];

  if (safePages.filter((page) => page?.is_important_page).length >= 4) {
    positives.push("Your site has several important service or business pages.");
  }

  if (
    safePages.filter(
      (page) =>
        Array.isArray(page?.trust_signals) && page.trust_signals.length > 0
    ).length >= 1
  ) {
    positives.push("Your site already includes some trust signals.");
  }

  if (
    safePages.filter(
      (page) =>
        Array.isArray(page?.cta_phrases) && page.cta_phrases.length > 0
    ).length >= 1
  ) {
    positives.push("Your site gives visitors ways to take the next step.");
  }

  if (safePages.filter((page) => page?.has_faq).length >= 1) {
    positives.push("Your site already answers some customer questions.");
  }

  if (safePages.filter((page) => page?.has_schema).length >= 1) {
    positives.push(
      "Your site includes some structured business information."
    );
  }

  const summary = body?.technical_audit_summary;

  if (summary?.indexable_pages > 0) {
    positives.push(
      `${summary.indexable_pages} page${summary.indexable_pages === 1 ? "" : "s"} appear indexable from the scan.`
    );
  }

  return positives.slice(0, 5);
}

function buildCompetitorInsights(body: any) {
  const comparison = body?.competitor_comparison;

  if (!comparison) return [];

  const insights = [];
  const depth = comparison?.content_depth || {};
  const faq = comparison?.faq_coverage || {};

  if (
    depth?.competitor_median_words > 0 &&
    depth?.your_median_words > 0 &&
    depth.competitor_median_words >= depth.your_median_words * 2
  ) {
    insights.push({
      headline: "Competitor pages go deeper than yours",
      title: "Competitor pages go deeper than yours",
      competitor_name: comparison?.competitors_compared?.[0]?.name || "",
      competitor_domain: comparison?.competitors_compared?.[0]?.domain || "",
      evidence: `Typical competitor page: about ${depth.competitor_median_words} words. Your typical important page: about ${depth.your_median_words} words.`,
      what_to_add:
        "Expand key pages with service details, process steps, pricing context, FAQs, and proof points.",
      recommended_action:
        "Expand key pages with service details, process steps, pricing context, FAQs, and proof points.",
      target_page: "/",
      related_user_page: "/",
      gap_type: "content_depth_gap",
    });
  }

  if (
    Number(faq?.competitors_with_faq || 0) >= 2 &&
    Number(faq?.your_pages_with_faq || 0) === 0
  ) {
    insights.push({
      headline: "Competitors answer customer questions",
      title: "Competitors answer customer questions",
      competitor_name: comparison?.competitors_compared?.[0]?.name || "",
      competitor_domain: comparison?.competitors_compared?.[0]?.domain || "",
      evidence: `${faq.competitors_with_faq} of ${faq.competitors_measured} competitor pages include a question-and-answer section.`,
      what_to_add:
        "Add 4–6 real customer questions and answers to your key service pages.",
      recommended_action:
        "Add 4–6 real customer questions and answers to your key service pages.",
      target_page: "/",
      related_user_page: "/",
      gap_type: "faq_gap",
    });
  }

  for (const gap of (comparison?.topic_gaps || []).slice(0, 3)) {
    insights.push({
      headline: `Competitors cover “${gap.topic}”`,
      title: `Competitors cover “${gap.topic}”`,
      competitor_name: gap?.competitors?.[0] || "",
      competitor_domain: "",
      evidence: `Found on ${gap?.competitors?.length || 1} competitor page${gap?.competitors?.length === 1 ? "" : "s"}.`,
      what_to_add: `Add a “${gap.topic}” section where it genuinely fits your services.`,
      recommended_action: `Add a “${gap.topic}” section where it genuinely fits your services.`,
      target_page: "/",
      related_user_page: "/",
      gap_type: "topic_gap",
    });
  }

  return insights.slice(0, 6);
}

/* -------------------------------------------------------------------------- */
/* Text defaults                                                               */
/* -------------------------------------------------------------------------- */

function describeFixTypes(fixes: any[]) {
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

  if (fixes.some((fix) => fix.category === "robots_txt")) {
    labels.push("search visibility settings");
  }

  if (fixes.some((fix) => fix.category === "js_rendering")) {
    labels.push("how the site loads content");
  }

  if (fixes.some((fix) => fix.category === "web_dev")) {
    labels.push("website setup cleanup");
  }

  if (fixes.some((fix) => fix.category === "thin_content")) {
    labels.push("stronger page content");
  }

  if (fixes.some((fix) => fix.category === "schema")) {
    labels.push("trust and structured information");
  }

  if (fixes.some((fix) => fix.category === "performance")) {
    labels.push("page performance cleanup");
  }

  if (
    fixes.some(
      (fix) =>
        fix.customer_category === "Technical SEO" ||
        fix.customer_category === "Competitor opportunities"
    )
  ) {
    labels.push("technical SEO opportunities");
  }

  if (labels.length === 0) return "a few website cleanup items";
  if (labels.length === 1) return labels[0];

  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

function friendlyCategory(category: string) {
  const map: Record<string, string> = {
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
    indexability: "Technical SEO",
    mobile_setup: "Technical SEO",
    social_metadata: "Technical SEO",
    performance_hint: "Technical SEO",
  };

  return map[category] || "Website improvement";
}

function defaultTitle(category: string) {
  const map: Record<string, string> = {
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
    js_rendering: "Review how the site loads content",
    indexability: "Review whether important pages are indexable",
    mobile_setup: "Review mobile setup",
    social_metadata: "Review social sharing metadata",
    performance_hint: "Review heavy pages",
  };

  return map[category] || "Review this website recommendation";
}

function defaultSteps({
  category,
  difficulty,
  recommendedValue,
}: {
  category: string;
  difficulty: string;
  recommendedValue: string;
}) {
  if (category === "meta_title") {
    return [
      "Review the affected page.",
      "Write one short, specific search title.",
      "Include the main service or page topic.",
    ];
  }

  if (category === "meta_description") {
    return [
      "Review the affected page.",
      "Write one helpful search description.",
      "Explain what the visitor will find on the page.",
    ];
  }

  if (category === "thin_content") {
    return [
      "Review the affected page.",
      "Add more useful service details.",
      "Add common questions, proof points, and a clear next step.",
    ];
  }

  if (category === "canonical" || category === "robots_txt") {
    return [
      "Share this finding with your web person.",
      "Ask them to review the technical setting.",
      "Confirm the page should be visible as its own search result.",
    ];
  }

  if (difficulty === "developer") {
    return [
      "Share this finding with your web person.",
      "Ask them to review the technical detail.",
      "Confirm the fix after it is updated.",
    ];
  }

  return [
    "Review the affected page.",
    recommendedValue || "Update the page based on the recommendation.",
    "Check the page again after publishing.",
  ].filter(Boolean);
}

function defaultOwner(difficulty: string) {
  return difficulty === "developer" ? "your_web_person" : "you";
}

function defaultTime(difficulty: string) {
  if (difficulty === "easy") return "about 10–15 minutes";
  if (difficulty === "moderate") return "about 30–60 minutes";
  return "a task for your web person";
}

/* -------------------------------------------------------------------------- */
/* Validation helpers                                                          */
/* -------------------------------------------------------------------------- */

function normalizePriority(priority: string) {
  return ["critical", "high", "medium", "low"].includes(priority)
    ? priority
    : "medium";
}

function normalizeStatus(status: string) {
  return ["auto_fixed", "needs_approval", "needs_developer", "open"].includes(
    status
  )
    ? status
    : "needs_approval";
}

function normalizeDifficulty(difficulty: string, status: string) {
  if (["easy", "moderate", "developer"].includes(difficulty)) {
    return difficulty;
  }

  if (status === "needs_developer") return "developer";
  if (status === "needs_approval") return "moderate";

  return "easy";
}

/* -------------------------------------------------------------------------- */
/* Utility                                                                     */
/* -------------------------------------------------------------------------- */

function cleanPath(input: any) {
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

function stringifyValue(value: any) {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function cleanString(value: any) {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }

  return "";
}

function clampText(value: any, max: number) {
  const text = String(value || "").trim();

  if (text.length <= max) return text;

  return text.slice(0, Math.max(0, max - 1)).trim();
}

function stableId(input: any) {
  let hash = 0;
  const value = String(input || "");

  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }

  return `finding_${Math.abs(hash)}`;
}

function calculateFallbackScore(fixes: any[]) {
  let score = 100;

  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

function withTimeout(promise: Promise<any>, ms: number, label = "Operation") {
  let timeoutId: number | undefined;

  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        new Error(`${label} timed out after ${Math.round(ms / 1000)} seconds.`)
      );
    }, ms);
  });

  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timeoutId) clearTimeout(timeoutId);
  });
}