import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") || "";
const GEMINI_MODEL = Deno.env.get("GEMINI_MODEL") || "gemini-3.1-flash-lite";
const GEMINI_BASE_URL =
  Deno.env.get("GEMINI_BASE_URL") ||
  "https://generativelanguage.googleapis.com/v1beta/models";

const BASE44_AI_TIMEOUT_MS = Number(Deno.env.get("BASE44_AI_TIMEOUT_MS") || 25000);
const GEMINI_AI_TIMEOUT_MS = Number(Deno.env.get("GEMINI_AI_TIMEOUT_MS") || 60000);
const AI_PROVIDER_ORDER = Deno.env.get("AI_PROVIDER_ORDER") || "gemini_first";
const MAX_AI_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 30);
const MAX_PROMPT_PAGES = Number(Deno.env.get("MAX_PROMPT_PAGES") || 30);

const CATEGORY_MAP = {
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
  mobile_setup: "mobile_setup",
  performance_hint: "performance_hint",
  social_metadata: "social_metadata",
  indexability: "indexability",
};

const LOW_VALUE_PAGE_PATTERNS = [
  "actualites",
  "news",
  "blog",
  "archive",
  "archives",
  "tag",
  "tags",
  "category",
  "categorie",
  "author",
  "feed",
  "rss",
  "page/",
  "?page=",
  "?p=",
];

const COSMETIC_RULES = new Set([
  "missing_meta_description",
  "long_meta_description",
  "short_meta_description",
  "missing_title",
  "long_title",
  "short_title",
  "duplicate_title",
  "duplicate_meta_description",
  "thin_content",
  "image_alt_text",
]);

const SEVERE_RULES = new Set([
  "broken_page",
  "404_error",
  "server_error",
  "redirect_loop",
  "blocked_by_robots",
  "noindex",
  "canonical_missing",
  "canonical_to_other_domain",
  "indexability",
]);

const VERTICAL_PROFILES = {
  insurance_finance: {
    label: "insurance / finance lead generation",
    keywords: [
      "assurance",
      "insurance",
      "pret",
      "prêt",
      "credit",
      "crédit",
      "loan",
      "mortgage",
      "finance",
      "banque",
      "bank",
      "taux",
      "emprunteur",
      "mutuelle",
      "devis",
      "simulation",
      "comparateur",
      "compare",
    ],
    moneyPatterns: [
      "devis",
      "quote",
      "simulation",
      "simulateur",
      "calcul-assurance",
      "calculator",
      "comparateur",
      "compare",
      "tarif",
      "taux-assurance",
      "contact",
      "souscription",
      "classement-assurances",
      "meilleures-assurances",
    ],
  },
  travel_booking: {
    label: "travel / booking marketplace",
    keywords: [
      "booking",
      "book",
      "reservation",
      "réservation",
      "activity",
      "activities",
      "activite",
      "activité",
      "event",
      "tour",
      "destination",
      "hotel",
      "billet",
      "ticket",
      "travel",
      "voyage",
    ],
    moneyPatterns: [
      "booking",
      "reservation",
      "réservation",
      "activity",
      "activities",
      "activite",
      "activité",
      "event",
      "tour",
      "destination",
      "billet",
      "ticket",
      "calendar",
      "availability",
    ],
  },
  ecommerce: {
    label: "ecommerce / catalog",
    keywords: [
      "product",
      "produit",
      "shop",
      "boutique",
      "cart",
      "panier",
      "checkout",
      "price",
      "prix",
      "sku",
      "collection",
      "category",
    ],
    moneyPatterns: [
      "product",
      "produit",
      "shop",
      "boutique",
      "cart",
      "panier",
      "checkout",
      "price",
      "prix",
      "collection",
      "category",
      "categorie",
    ],
  },
  winery: {
    label: "winery / wine tourism",
    keywords: [
      "wine",
      "vin",
      "vins",
      "winery",
      "vineyard",
      "vignoble",
      "domaine",
      "cave",
      "cellar",
      "tasting",
      "degustation",
      "dégustation",
      "champagne",
      "appellation",
    ],
    moneyPatterns: [
      "wine",
      "vin",
      "boutique",
      "shop",
      "tasting",
      "degustation",
      "dégustation",
      "visit",
      "visite",
      "reservation",
      "contact",
    ],
  },
  local_service: {
    label: "local service business",
    keywords: [
      "service",
      "services",
      "contact",
      "appointment",
      "rendez-vous",
      "near me",
      "local",
      "agency",
      "agence",
      "location",
      "adresse",
    ],
    moneyPatterns: [
      "service",
      "services",
      "contact",
      "appointment",
      "rendez-vous",
      "devis",
      "quote",
      "location",
      "agence",
    ],
  },
  general: {
    label: "general website",
    keywords: [],
    moneyPatterns: ["contact", "service", "product"],
  },
};

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ success: false, error: "Unauthorized" }, { status: 401 });
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

    const siteFingerprint = buildSiteFingerprint({ body, pages, websiteUrl });
    const canonicalFixes = prepareFixes(rawFixes, siteFingerprint, body);
    const aiFixes = canonicalFixes.slice(0, MAX_AI_FIXES);

    const fallbackPlan = buildFallbackPlan({
      body,
      pages,
      canonicalFixes,
      siteFingerprint,
    });

    if (!websiteUrl || canonicalFixes.length === 0) {
      return Response.json({
        success: true,
        ai_provider: "scanner_fallback",
        ai_review_warning: !websiteUrl
          ? "AI review ran, but website_url was missing. Scanner recommendations are shown."
          : "AI review ran, but no scanner recommendations were provided.",
        ...fallbackPlan,
      });
    }

    const prompt = buildPrompt({
      body,
      websiteUrl,
      pages,
      canonicalFixes: aiFixes,
      fallbackPlan,
      siteFingerprint,
    });

    const aiErrors = [];
    const providers =
      AI_PROVIDER_ORDER === "base44_first" ? ["base44", "gemini"] : ["gemini", "base44"];

    for (const provider of providers) {
      if (provider === "gemini") {
        if (!GEMINI_API_KEY) {
          aiErrors.push("GEMINI_API_KEY is not configured.");
          continue;
        }

        try {
          const geminiResponse = await callGeminiAiReview({ prompt, schema: responseSchema() });
          const merged = mergeAiIntoFallback({
            aiResponse: geminiResponse,
            fallbackPlan,
            canonicalFixes,
            pages,
            body,
            siteFingerprint,
          });

          return Response.json({
            success: true,
            ai_provider: "gemini",
            ai_review_warning: aiErrors.length > 0 ? aiErrors.join(" ") : "",
            ...merged,
          });
        } catch (error) {
          aiErrors.push(`Gemini failed: ${error?.message || "Unknown Gemini error."}`);
        }
      }

      if (provider === "base44") {
        if (!base44.integrations?.Core?.InvokeLLM) {
          aiErrors.push("Base44 InvokeLLM is not available.");
          continue;
        }

        try {
          const rawBase44Response = await withTimeout(
            base44.integrations.Core.InvokeLLM({
              prompt,
              response_json_schema: responseSchema(),
            }),
            BASE44_AI_TIMEOUT_MS,
            "Base44 AI review"
          );

          const aiResponse = unwrapAiResponse(rawBase44Response);
          const merged = mergeAiIntoFallback({
            aiResponse,
            fallbackPlan,
            canonicalFixes,
            pages,
            body,
            siteFingerprint,
          });

          return Response.json({
            success: true,
            ai_provider: "base44_invokellm",
            ai_review_warning: aiErrors.length > 0 ? aiErrors.join(" ") : "",
            ...merged,
          });
        } catch (error) {
          aiErrors.push(`Base44 AI failed: ${error?.message || "Unknown Base44 AI error."}`);
        }
      }
    }

    return Response.json({
      success: true,
      ai_provider: "scanner_fallback",
      ai_review_warning:
        aiErrors.join(" ") || "AI review failed, so scanner recommendations are shown.",
      ...fallbackPlan,
    });
  } catch (error) {
    console.error("aiReviewScan failed", error);
    return Response.json(
      { success: false, error: "aiReviewScan failed. Please try again." },
      { status: 500 }
    );
  }
});

/* -------------------------------------------------------------------------- */
/* AI providers                                                                */
/* -------------------------------------------------------------------------- */

async function callGeminiAiReview({ prompt, schema }) {
  const endpoint = `${GEMINI_BASE_URL}/${encodeURIComponent(GEMINI_MODEL)}:generateContent`;
  const response = await withTimeout(
    fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
      },
      body: JSON.stringify({
        contents: [
          {
            role: "user",
            parts: [{ text: prompt }],
          },
        ],
        generationConfig: {
          temperature: 0.12,
          maxOutputTokens: 6000,
          responseMimeType: "application/json",
          responseSchema: schema,
        },
      }),
    }),
    GEMINI_AI_TIMEOUT_MS,
    "Gemini AI review"
  );

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Gemini returned status ${response.status}: ${clampText(text, 600)}`);
  }

  const payload = JSON.parse(text);
  const modelText = extractGeminiText(payload);
  if (!modelText) throw new Error("Gemini response did not include output text.");
  return parseJsonObject(modelText);
}

function extractGeminiText(payload) {
  const parts = payload?.candidates?.[0]?.content?.parts || [];
  return parts.map((part) => part?.text || "").filter(Boolean).join("\n").trim();
}

function parseJsonObject(value) {
  const raw = String(value || "").trim();
  if (!raw) return {};

  const cleaned = raw
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();

  try {
    return JSON.parse(cleaned);
  } catch {
    const firstBrace = cleaned.indexOf("{");
    const lastBrace = cleaned.lastIndexOf("}");
    if (firstBrace >= 0 && lastBrace > firstBrace) {
      return JSON.parse(cleaned.slice(firstBrace, lastBrace + 1));
    }
    throw new Error("AI returned text that could not be parsed as JSON.");
  }
}

function unwrapAiResponse(response) {
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

/* -------------------------------------------------------------------------- */
/* Site fingerprinting and ranking                                             */
/* -------------------------------------------------------------------------- */

function buildSiteFingerprint({ body, pages, websiteUrl }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const pageText = safePages
    .slice(0, 120)
    .map((page) => [page?.url, page?.final_url, page?.title, page?.h1, page?.meta_description].join(" "))
    .join(" ")
    .toLowerCase();

  const combinedText = [
    websiteUrl,
    body?.business_name,
    body?.business_type,
    body?.cms_name,
    body?.cms_platform,
    pageText,
  ]
    .join(" ")
    .toLowerCase();

  const verticalScores = Object.entries(VERTICAL_PROFILES).map(([key, profile]) => {
    const score = profile.keywords.reduce(
      (total, keyword) => total + countIncludes(combinedText, keyword),
      0
    );
    return { key, label: profile.label, score };
  });

  verticalScores.sort((a, b) => b.score - a.score);
  const best = verticalScores[0]?.score > 0 ? verticalScores[0] : VERTICAL_PROFILES.general;
  const vertical = verticalScores[0]?.score > 0 ? verticalScores[0].key : "general";
  const confidence = verticalScores[0]?.score > 0
    ? Math.min(0.95, 0.45 + verticalScores[0].score / Math.max(10, verticalScores[0].score + (verticalScores[1]?.score || 0)))
    : 0.35;

  const pagesFound = Number(body?.pages_found || safePages.length || 0);
  const pagesCrawled = Number(body?.pages_crawled || safePages.length || 0);
  const sizeBasis = Math.max(pagesFound, pagesCrawled, safePages.length);
  const sizeBand = sizeBasis >= 1000 ? "enterprise" : sizeBasis >= 150 ? "mid_market" : sizeBasis >= 30 ? "smb" : "micro";

  const businessModel = detectBusinessModel(combinedText, vertical);
  const localization = detectLocalization(safePages, websiteUrl);
  const renderMode = detectRenderMode(body, safePages);
  const regulatorySensitivity = ["insurance_finance"].includes(vertical) ? "regulated" : "standard";

  return {
    vertical,
    vertical_label: typeof best === "object" && best.label ? best.label : VERTICAL_PROFILES[vertical]?.label || "general website",
    vertical_confidence: Number(confidence.toFixed(2)),
    business_model: businessModel,
    size_band: sizeBand,
    pages_found: pagesFound,
    pages_crawled: pagesCrawled,
    localization,
    render_mode: renderMode,
    regulatory_sensitivity: regulatorySensitivity,
    likely_money_page_patterns: VERTICAL_PROFILES[vertical]?.moneyPatterns || VERTICAL_PROFILES.general.moneyPatterns,
    low_value_page_patterns: LOW_VALUE_PAGE_PATTERNS,
    scoring_model: "evidence_confidence_x_site_fit_x_business_impact_x_reach_v2_template_groups",
  };
}

function detectBusinessModel(text, vertical) {
  if (hasAny(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"])) {
    return "quote_or_comparison_lead_gen";
  }
  if (hasAny(text, ["booking", "reservation", "réservation", "availability", "calendar", "book now"])) {
    return "booking_or_reservation";
  }
  if (hasAny(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart"])) {
    return "catalog_or_ecommerce";
  }
  if (vertical === "insurance_finance") return "regulated_lead_generation";
  if (vertical === "travel_booking") return "booking_or_reservation";
  if (vertical === "winery") return "hybrid_catalog_visit_lead_gen";
  if (hasAny(text, ["contact", "rendez-vous", "appointment", "agence", "location"])) {
    return "local_lead_generation";
  }
  return "content_or_general_business";
}

function detectLocalization(pages, websiteUrl) {
  const text = [websiteUrl, ...pages.slice(0, 80).map((page) => page?.url || page?.final_url || "")]
    .join(" ")
    .toLowerCase();
  const localeHits = (text.match(/\/(fr|en|es|de|it|nl|pt|ca|us|uk)([-_/]|\/)/g) || []).length;
  if (localeHits >= 4) return "multi_language_or_multi_country";
  if (localeHits > 0) return "single_locale_subfolder";
  return "single_language_or_unknown";
}

function detectRenderMode(body, pages) {
  if (body?.browser_rendering?.enabled) return "rendered_browser_checked";
  const suspected = pages.filter((page) => page?.client_rendering_suspected).length;
  if (suspected >= 3) return "js_heavy_suspected";
  return "raw_html_first";
}

function prepareFixes(rawFixes, siteFingerprint, body) {
  const normalized = dedupeByFixId(
    (Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) => normalizeFix(fix, index))
  );

  return groupTemplateIssues(
    normalized.map((fix) => scoreFixForSite(fix, siteFingerprint, body))
  )
    .sort(compareFixes)
    .slice(0, 80);
}

function scoreFixForSite(fix, siteFingerprint, body) {
  const pageUrl = cleanPath(fix?.page_url || fix?.affected_pages?.[0] || "/") || "/";
  const pageValue = scorePageValue(pageUrl, siteFingerprint, body);
  const evidenceConfidence = scoreEvidenceConfidence(fix);
  const reachScore = scoreReach(fix);
  const siteFitScore = scoreSiteFit(fix, pageValue, siteFingerprint);
  const businessImpactScore = scoreBusinessImpact(fix, pageValue, siteFingerprint);
  const lowValuePage = pageValue.classification === "low_value";
  const supportContent = pageValue.classification === "support_content";
  const cosmetic = isCosmeticIssue(fix);
  const severe = isSevereIssue(fix);

  let priority = normalizePriority(fix.priority);
  let issueTitle = fix.issue_title;
  let why = fix.why_it_matters;
  let recommendedValue = fix.recommended_value;
  let difficulty = fix.difficulty;

  if (lowValuePage && cosmetic && !severe) {
    priority = "low";
    issueTitle = issueTitle.toLowerCase().includes("archive")
      ? issueTitle
      : `Low-priority archive cleanup: ${issueTitle}`;
    why =
      "This is on a news, blog, or archive page. It is usually less important than fixing core service, quote, calculator, comparison, guide, or contact pages first.";
    recommendedValue =
      "Review these lower-value pages later as a batch, after the important business pages are cleaned up.";
  } else if (lowValuePage && severe) {
    priority = priority === "critical" || priority === "high" ? "medium" : priority;
    why =
      "This is a real technical problem, but it is on a lower-priority news or archive page. Fix it after core business pages unless users actively reach this URL.";
  } else if (supportContent && cosmetic && !severe) {
    priority = priority === "critical" || priority === "high" ? "medium" : priority;
    why =
      "This guide or Q&A page can support search visibility, but it should be handled as a content-template cleanup after the main calculator, comparison, quote, and landing pages.";
  } else if (pageValue.classification === "money_page" && priority === "low") {
    priority = "medium";
  }

  if (siteFingerprint.regulatory_sensitivity === "regulated" && isTrustOrEntityIssue(fix)) {
    priority = priority === "low" ? "medium" : priority;
  }

  const overallPriorityScore = Math.round(
    evidenceConfidence * 0.25 + siteFitScore * 0.25 + businessImpactScore * 0.35 + reachScore * 0.15
  );

  return {
    ...fix,
    priority,
    issue_title: issueTitle,
    title: issueTitle,
    why_it_matters: why,
    recommended_value: recommendedValue,
    ai_recommendation: recommendedValue,
    difficulty,
    page_url: pageUrl,
    page_template_family: getTemplateFamily(pageUrl),
    page_value_score: pageValue.score,
    page_value_label: pageValue.label,
    business_importance: pageValue.classification,
    evidence_confidence: evidenceConfidence,
    site_fit_score: siteFitScore,
    business_impact_score: businessImpactScore,
    reach_score: reachScore,
    overall_priority_score: overallPriorityScore,
    site_fingerprint_vertical: siteFingerprint.vertical,
  };
}

function scorePageValue(url, siteFingerprint, body) {
  const path = cleanPath(url).toLowerCase();
  const requested = cleanPath(body?.requested_path_prefix || body?.crawl_path_prefix || "").toLowerCase();
  const moneyPatterns = siteFingerprint.likely_money_page_patterns || [];
  const family = getTemplateFamily(path);

  let score = 35;
  const reasons = [];

  if (path === "/" || path.endsWith("/index.html")) {
    score += 35;
    reasons.push("section or homepage landing page");
  }

  if (requested && (path === requested || path === `${requested}/` || path === `${requested}/index.html`)) {
    score += 35;
    reasons.push("scanned section landing page");
  }

  for (const pattern of moneyPatterns) {
    if (path.includes(pattern)) {
      score += 14;
      reasons.push(`matches ${pattern}`);
      break;
    }
  }

  if (hasAny(path, ["contact", "devis", "quote", "simulation", "calcul-assurance", "calculator", "comparateur", "booking", "reservation"])) {
    score += 25;
    reasons.push("conversion or lead page");
  }

  if (family === "guide" || family === "qa" || family === "legal_info") {
    score += siteFingerprint.vertical === "insurance_finance" ? 8 : 5;
    reasons.push("supporting guide or Q&A content");
  }

  if (isLowValuePage(path)) {
    score -= 45;
    reasons.push("news/blog/archive pattern");
  }

  const clamped = Math.max(0, Math.min(100, score));
  const classification = clamped >= 70 ? "money_page" : clamped <= 30 ? "low_value" : family === "guide" || family === "qa" || family === "legal_info" ? "support_content" : "standard";

  return {
    score: clamped,
    classification,
    label:
      classification === "money_page"
        ? "Important business page"
        : classification === "low_value"
          ? "Lower-priority news/archive page"
          : classification === "support_content"
            ? "Supporting guide/Q&A page"
            : "Standard page",
    reasons,
  };
}

function scoreEvidenceConfidence(fix) {
  let score = typeof fix?.confidence_score === "number" ? fix.confidence_score : 70;
  if (fix?.source === "screaming_frog_lite") score += 10;
  if (fix?.current_value) score += 5;
  if (Array.isArray(fix?.affected_pages) && fix.affected_pages.length > 1) score += 5;
  if (!fix?.page_url && (!fix?.affected_pages || fix.affected_pages.length === 0)) score -= 15;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreReach(fix) {
  const count = Array.isArray(fix?.affected_pages) ? fix.affected_pages.length : 1;
  return Math.max(5, Math.min(100, count * 12));
}

function scoreSiteFit(fix, pageValue, siteFingerprint) {
  let score = 45 + pageValue.score * 0.45;
  const category = String(fix?.category || "").toLowerCase();
  const rule = String(fix?.rule || "").toLowerCase();

  if (siteFingerprint.vertical === "insurance_finance" && hasAny(`${category} ${rule}`, ["schema", "trust", "duplicate", "title", "meta", "404", "index"])) {
    score += 15;
  }
  if (siteFingerprint.vertical === "ecommerce" && hasAny(`${category} ${rule}`, ["schema", "product", "canonical", "duplicate", "index"])) {
    score += 15;
  }
  if (siteFingerprint.vertical === "travel_booking" && hasAny(`${category} ${rule}`, ["schema", "internal", "index", "canonical", "thin", "404"])) {
    score += 15;
  }
  if (siteFingerprint.regulatory_sensitivity === "regulated" && isTrustOrEntityIssue(fix)) score += 18;

  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreBusinessImpact(fix, pageValue, siteFingerprint) {
  let score = pageValue.score;
  if (isSevereIssue(fix)) score += 25;
  if (isCosmeticIssue(fix)) score -= pageValue.classification === "low_value" ? 25 : pageValue.classification === "support_content" ? 12 : 5;
  if (siteFingerprint.business_model?.includes("quote") && hasAny(fix.page_url, ["devis", "quote", "simulation", "calcul-assurance", "comparateur"])) score += 18;
  if (siteFingerprint.business_model?.includes("booking") && hasAny(fix.page_url, ["booking", "reservation", "activity", "event"])) score += 18;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function groupTemplateIssues(fixes) {
  const keep = [];
  const groups = new Map();

  for (const fix of fixes) {
    const family = fix.page_template_family || getTemplateFamily(fix.page_url);
    const shouldGroupLowValue =
      fix.business_importance === "low_value" &&
      fix.priority === "low" &&
      isCosmeticIssue(fix);
    const shouldGroupSupport =
      ["guide", "qa", "legal_info"].includes(family) &&
      fix.business_importance === "support_content" &&
      isCosmeticIssue(fix) &&
      !isSevereIssue(fix);

    if (!shouldGroupLowValue && !shouldGroupSupport) {
      keep.push(fix);
      continue;
    }

    const key = `${shouldGroupSupport ? family : "archive"}|${fix.rule || fix.category || "cleanup"}`;
    const title = shouldGroupSupport ? supportGroupTitle(fix, family) : archiveGroupTitle(fix);
    const existing = groups.get(key) || {
      ...fix,
      id: stableId(`template_group_${key}`),
      fix_id: stableId(`template_group_${key}`),
      page_url: "",
      issue_title: title,
      title,
      plain_english_explanation: shouldGroupSupport
        ? "Several guide or Q&A pages have the same SEO cleanup issue. Treat this as a template/content cleanup instead of separate one-off tasks."
        : "Several news, blog, or archive pages have the same lower-priority SEO cleanup issue.",
      plain_english_summary: shouldGroupSupport
        ? "Several guide or Q&A pages have the same SEO cleanup issue. Treat this as a template/content cleanup instead of separate one-off tasks."
        : "Several news, blog, or archive pages have the same lower-priority SEO cleanup issue.",
      why_it_matters: shouldGroupSupport
        ? "These pages can support search visibility, but they should not crowd out the calculator, comparison, quote, and main landing pages. Grouping them keeps the FixList practical."
        : "These pages matter less than the pages that drive leads, sales, bookings, or quote requests. Grouping them keeps the FixList focused on business impact first.",
      recommended_value: shouldGroupSupport
        ? "Fix one guide/Q&A title or description pattern, then apply the same rule across the affected pages."
        : "Review these pages later as a batch, or leave them until important business pages are fixed.",
      ai_recommendation: shouldGroupSupport
        ? "Fix one guide/Q&A title or description pattern, then apply the same rule across the affected pages."
        : "Review these pages later as a batch, or leave them until important business pages are fixed.",
      priority: shouldGroupSupport ? "medium" : "low",
      difficulty: "easy",
      business_importance: shouldGroupSupport ? "support_content_group" : "low_value_group",
      affected_pages: [],
      page_value_score: shouldGroupSupport ? 45 : 10,
      page_value_label: shouldGroupSupport ? "Grouped guide/Q&A content pages" : "Grouped lower-priority archive pages",
      evidence_confidence: 90,
      site_fit_score: shouldGroupSupport ? 55 : 20,
      business_impact_score: shouldGroupSupport ? 45 : 15,
      reach_score: 60,
      overall_priority_score: shouldGroupSupport ? 58 : 25,
      what_to_do: shouldGroupSupport
        ? [
            "Pick one affected guide or Q&A page as the example.",
            "Rewrite the title or description pattern so it is clearer and shorter.",
            "Apply the same rule across the affected template group.",
            "Run FixList again after publishing.",
          ]
        : [
            "Fix your important business pages first.",
            "Review these archive/news pages as a later batch.",
            "Run FixList again if you decide to clean them up.",
          ],
      what_to_do_steps: shouldGroupSupport
        ? [
            "Pick one affected guide or Q&A page as the example.",
            "Rewrite the title or description pattern so it is clearer and shorter.",
            "Apply the same rule across the affected template group.",
            "Run FixList again after publishing.",
          ]
        : [
            "Fix your important business pages first.",
            "Review these archive/news pages as a later batch.",
            "Run FixList again if you decide to clean them up.",
          ],
    };

    existing.affected_pages = Array.from(
      new Set([
        ...existing.affected_pages,
        ...normalizeAffectedPages(fix, fix.page_url || "/"),
      ])
    ).slice(0, 100);
    existing.page_count = existing.affected_pages.length;
    existing.reach_score = scoreReach(existing);
    groups.set(key, existing);
  }

  return [...keep, ...groups.values()].map((fix) => ({
    ...fix,
    overall_priority_score:
      fix.business_importance === "support_content_group"
        ? Math.max(55, Number(fix.overall_priority_score || 0))
        : fix.overall_priority_score,
  }));
}

function archiveGroupTitle(fix) {
  const rule = String(fix?.rule || "").toLowerCase();
  const category = String(fix?.category || "").toLowerCase();
  if (rule.includes("description") || category.includes("description")) return "Batch low-priority news/archive descriptions";
  if (rule.includes("title") || category.includes("title")) return "Batch low-priority news/archive titles";
  if (rule.includes("duplicate") || category.includes("duplicate")) return "Batch low-priority duplicate archive fields";
  if (rule.includes("alt")) return "Batch low-priority archive image alt text";
  return "Batch low-priority news/archive cleanup";
}

function supportGroupTitle(fix, family) {
  const rule = String(fix?.rule || "").toLowerCase();
  const label = family === "qa" ? "Q&A" : family === "legal_info" ? "legal/guide" : "guide";
  if (rule.includes("description")) return `Batch ${label} page descriptions`;
  if (rule.includes("title")) return `Batch ${label} page titles`;
  if (rule.includes("duplicate")) return `Batch duplicate ${label} search fields`;
  if (rule.includes("alt")) return `Batch ${label} image alt text`;
  return `Batch ${label} page cleanup`;
}

function getTemplateFamily(url) {
  const path = cleanPath(url).toLowerCase();
  if (isLowValuePage(path)) return "archive";
  if (path.includes("questions-reponses") || path.includes("faq")) return "qa";
  if (path.includes("/loi-") || path.includes("/loi_") || path.includes("/legal")) return "legal_info";
  if (path.includes("/le-guide") || path.includes("/guide")) return "guide";
  if (hasAny(path, ["simulation", "simulateur", "calcul-assurance", "comparateur", "devis", "quote"])) return "conversion";
  if (path.includes("contact")) return "contact";
  return "standard";
}

/* -------------------------------------------------------------------------- */
/* Normalization                                                               */
/* -------------------------------------------------------------------------- */

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

function normalizeFix(fix, index) {
  const rawCategory = String(fix?.category || fix?.type || "web_dev");
  const category = CATEGORY_MAP[rawCategory] || rawCategory || "web_dev";
  const pageUrl = cleanPath(fix?.page_url || fix?.url || fix?.affected_pages?.[0] || "/") || "/";
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
  const title = cleanString(fix?.issue_title || fix?.title || fix?.headline || defaultTitle(category)) || defaultTitle(category);
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
  const steps = normalizeSteps(fix) || defaultSteps({ category, difficulty, recommendedValue });
  const stable = fix?.id || fix?.fix_id || stableId(`${pageUrl}|${category}|${title}|${index}`);

  return {
    ...fix,
    id: stable,
    fix_id: stable,
    type: fix?.type || "site_level",
    rule: String(fix?.rule || fix?.type || category || ""),
    page_url: pageUrl,
    category,
    customer_category: cleanString(fix?.customer_category) || friendlyCategory(category),
    issue_title: title,
    title,
    plain_english_explanation: explanation,
    plain_english_summary: explanation,
    why_it_matters: why,
    current_value: stringifyValue(fix?.current_value || fix?.current || fix?.technical_detail || fix?.detected_value || ""),
    recommended_value: recommendedValue,
    ai_recommendation: recommendedValue,
    priority: normalizePriority(fix?.priority),
    difficulty,
    status,
    can_auto_fix: status === "auto_fixed" || fix?.can_auto_fix === true,
    requires_approval: status === "needs_approval" || fix?.requires_approval === true,
    requires_developer: status === "needs_developer" || fix?.requires_developer === true,
    affected_pages: affectedPages,
    details: fix?.details && typeof fix.details === "object" ? fix.details : {},
    confidence_score: typeof fix?.confidence_score === "number" ? fix.confidence_score : 80,
    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,
    who_can_do_this:
      fix?.who_can_do_this === "you" || fix?.who_can_do_this === "your_web_person"
        ? fix.who_can_do_this
        : defaultOwner(difficulty),
    estimated_time: cleanString(fix?.estimated_time || fix?.time_estimate) || defaultTime(difficulty),
    time_estimate: cleanString(fix?.time_estimate || fix?.estimated_time) || defaultTime(difficulty),
    source: fix?.source || "scanner",
  };
}

function normalizeAffectedPages(fix, fallbackPage) {
  const rawPages = Array.isArray(fix?.affected_pages)
    ? fix.affected_pages
    : Array.isArray(fix?.pages)
      ? fix.pages
      : fix?.page_url
        ? [fix.page_url]
        : [fallbackPage];
  return Array.from(new Set(rawPages.map((item) => cleanPath(item)).filter(Boolean))).slice(0, 150);
}

function normalizeSteps(fix) {
  const possible = [fix?.what_to_do, fix?.what_to_do_steps, fix?.fix_steps, fix?.steps];
  for (const value of possible) {
    if (Array.isArray(value) && value.length > 0) {
      const steps = value.slice(0, 5).map((item) => String(item).trim()).filter(Boolean);
      if (steps.length > 0) return steps;
    }
  }
  return null;
}

function dedupeByFixId(fixes) {
  const seen = new Set();
  const output = [];
  for (const fix of fixes || []) {
    const key = String(fix?.id || fix?.fix_id || "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(fix);
  }
  return output;
}

function compareFixes(a, b) {
  const scoreDiff = Number(b?.overall_priority_score || 0) - Number(a?.overall_priority_score || 0);
  if (scoreDiff !== 0) return scoreDiff;
  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const priorityDiff = (priorityOrder[a?.priority] ?? 9) - (priorityOrder[b?.priority] ?? 9);
  if (priorityDiff !== 0) return priorityDiff;
  return String(a?.issue_title || "").localeCompare(String(b?.issue_title || ""));
}

/* -------------------------------------------------------------------------- */
/* Plan building                                                               */
/* -------------------------------------------------------------------------- */

function buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint }) {
  const score =
    typeof body?.health_score === "number"
      ? body.health_score
      : typeof body?.scan_summary?.score === "number"
        ? body.scan_summary.score
        : calculateFallbackScore(canonicalFixes);
  const positiveFindings = buildPositiveFindings({ pages, siteFingerprint });
  const topRecommendedActions = canonicalFixes.slice(0, 5).map(fixToAction);
  const healthReport = buildFallbackHealthReport({
    body,
    pages,
    fixes: canonicalFixes,
    score,
    positiveFindings,
    siteFingerprint,
  });

  return makeFrontendCompatible({
    plain_english_summary: healthReport.overall_explanation,
    website_health_report: healthReport,
    health_explanation: healthReport.overall_explanation,
    customer_summary: healthReport.overall_explanation,
    top_recommended_actions: topRecommendedActions,
    recommended_actions: [],
    cleaned_fixes: canonicalFixes,
    raw_fixes: canonicalFixes,
    fixes: canonicalFixes,
    findings: canonicalFixes,
    recommendations: canonicalFixes,
    competitor_insights: [],
    grouped_page_recommendations: buildGroupedPageRecommendations(canonicalFixes),
    ignored_low_value_pages: canonicalFixes.filter((fix) => fix.business_importance === "low_value_group").slice(0, 10),
    positive_findings: positiveFindings,
    ai_rewrites_applied: 0,
    crawled_pages: pages,
    pages,
    health_score: score,
    site_fingerprint: siteFingerprint,
    technical_audit_summary: body?.technical_audit_summary || null,
    screaming_frog_lite_enabled: Boolean(body?.technical_audit_summary?.screaming_frog_lite_enabled || body?.screaming_frog_lite_enabled),
    audit_profile: body?.audit_profile || "",
  });
}

function buildFallbackHealthReport({ body, pages, fixes, score, positiveFindings, siteFingerprint }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const safeFixes = Array.isArray(fixes) ? fixes : [];
  const highPriorityCount = safeFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length;
  const grade = scoreToGrade(score);
  const verticalLabel = siteFingerprint?.vertical_label || "this type of site";
  const topConcerns = safeFixes.slice(0, 4).map((fix) => ({
    title: fix.issue_title,
    plain_english_explanation: fix.plain_english_explanation,
    why_it_matters: fix.why_it_matters,
    affected_area:
      Array.isArray(fix.affected_pages) && fix.affected_pages.length > 1
        ? `${fix.affected_pages.length} pages`
        : fix.affected_pages?.[0] || "Website",
  }));
  const quickWins = safeFixes.filter((fix) => fix.difficulty !== "developer").slice(0, 4).map((fix) => ({
    title: fix.issue_title,
    action: Array.isArray(fix.what_to_do) && fix.what_to_do.length > 0 ? fix.what_to_do[0] : "Review and update this item.",
    expected_benefit: fix.why_it_matters,
  }));
  const biggerProjects = safeFixes.filter((fix) => fix.difficulty === "developer").slice(0, 4).map((fix) => ({
    title: fix.issue_title,
    who_should_handle: "Your web person",
    why: fix.why_it_matters,
  }));
  const limitations = [];
  if (Array.isArray(body?.crawl_warnings)) limitations.push(...body.crawl_warnings.slice(0, 3));
  if (siteFingerprint?.vertical_confidence < 0.55) {
    limitations.push("The site type was not fully clear, so FixList used a conservative priority model.");
  }

  return {
    health_score: score,
    health_grade: grade,
    overall_explanation: [
      `Your website health is ${grade.toLowerCase()} with a score of ${score}/100.`,
      `FixList recognized this as ${verticalLabel} and prioritized pages that are most likely to drive leads, sales, bookings, or quotes.`,
      safePages.length > 0 ? `The scanner reviewed ${safePages.length} pages.` : "",
      highPriorityCount > 0
        ? `There ${highPriorityCount === 1 ? "is" : "are"} ${highPriorityCount} high-priority item${highPriorityCount === 1 ? "" : "s"} to look at first.`
        : "There are no major emergency issues from this scan, but there are still useful improvements to make.",
    ].filter(Boolean).join(" "),
    what_is_working: positiveFindings.length > 0 ? positiveFindings : ["The scan completed and found pages that can be reviewed."],
    top_concerns: topConcerns,
    quick_wins: quickWins,
    bigger_projects: biggerProjects,
    competitor_takeaways: [],
    limitations,
    next_best_step: safeFixes[0]?.issue_title || "Review the first recommendation and rescan after making changes.",
  };
}

function makeFrontendCompatible(plan) {
  const cleanedFixes = Array.isArray(plan.cleaned_fixes) ? plan.cleaned_fixes : [];
  const pages = Array.isArray(plan.crawled_pages) ? plan.crawled_pages : Array.isArray(plan.pages) ? plan.pages : [];
  const score = typeof plan.health_score === "number" ? plan.health_score : calculateFallbackScore(cleanedFixes);
  const websiteHealthReport = plan.website_health_report || buildFallbackHealthReport({
    body: plan,
    pages,
    fixes: cleanedFixes,
    score,
    positiveFindings: plan.positive_findings || [],
    siteFingerprint: plan.site_fingerprint || {},
  });
  const topRecommendedActions = Array.isArray(plan.top_recommended_actions) ? plan.top_recommended_actions : [];
  const recommendedActions = Array.isArray(plan.recommended_actions) && plan.recommended_actions.length > 0
    ? plan.recommended_actions
    : topRecommendedActions.map((action) => {
        const fix = cleanedFixes.find((item) => item.id === action.fix_id || item.fix_id === action.fix_id);
        return {
          fix_id: action.fix_id || fix?.id || "",
          title: action.title || fix?.issue_title || "Recommended action",
          plain_english_summary: fix?.plain_english_explanation || action.reason || "",
          why_it_matters: fix?.why_it_matters || action.reason || "",
          what_to_do_steps: action.what_to_do_steps || fix?.what_to_do || [],
          who_can_do_this: action.who_can_do_this || (fix?.who_can_do_this === "your_web_person" ? "Your web person" : "You"),
          time_estimate: action.time_estimate || fix?.estimated_time || "",
          priority: action.priority || fix?.priority || "medium",
          affected_pages: action.affected_pages || fix?.affected_pages || [],
        };
      });

  return {
    ...plan,
    success: true,
    health_score: score,
    website_health_report: websiteHealthReport,
    health_explanation: websiteHealthReport.overall_explanation,
    customer_summary: websiteHealthReport.overall_explanation,
    cleaned_fixes: cleanedFixes,
    raw_fixes: cleanedFixes,
    fixes: cleanedFixes,
    findings: cleanedFixes,
    recommendations: cleanedFixes,
    top_recommended_actions: topRecommendedActions,
    recommended_actions: recommendedActions,
    competitor_insights: [],
    crawled_pages: pages,
    pages,
    scan_summary: {
      score,
      status_label: websiteHealthReport.health_grade,
      plain_english_summary: websiteHealthReport.overall_explanation || plan.plain_english_summary || "The scan completed. Review the recommended improvements below.",
      pages_scanned: pages.length,
      pages_failed: pages.filter((page) => {
        const status = Number(page?.status_code || 0);
        return status >= 400 || status === 0 || page?.fetch_error;
      }).length,
      high_priority_count: cleanedFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length,
      technical_issue_count: cleanedFixes.length,
      site_fingerprint: plan.site_fingerprint || {},
      website_health_report: websiteHealthReport,
    },
  };
}

function mergeAiIntoFallback({ aiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint }) {
  const validIds = new Set(canonicalFixes.map((fix) => fix.id));
  const rewrites = new Map();

  for (const rewrite of aiResponse?.fix_rewrites || []) {
    if (rewrite?.fix_id && validIds.has(rewrite.fix_id)) rewrites.set(rewrite.fix_id, rewrite);
  }

  const cleanedFixes = canonicalFixes.map((fix) => {
    const rewrite = rewrites.get(fix.id);
    if (!rewrite) return fix;
    const steps = Array.isArray(rewrite.what_to_do) && rewrite.what_to_do.length > 0
      ? rewrite.what_to_do.slice(0, 5).map((step) => String(step).trim()).filter(Boolean)
      : fix.what_to_do;
    return {
      ...fix,
      issue_title: cleanString(rewrite.issue_title) || fix.issue_title,
      title: cleanString(rewrite.issue_title) || fix.title || fix.issue_title,
      plain_english_explanation: cleanString(rewrite.plain_english_explanation) || fix.plain_english_explanation,
      plain_english_summary: cleanString(rewrite.plain_english_explanation) || fix.plain_english_summary || fix.plain_english_explanation,
      why_it_matters: cleanString(rewrite.why_it_matters) || fix.why_it_matters,
      what_to_do: steps,
      what_to_do_steps: steps,
      fix_steps: steps,
      who_can_do_this:
        rewrite.who_can_do_this === "you" || rewrite.who_can_do_this === "your_web_person"
          ? rewrite.who_can_do_this
          : fix.who_can_do_this,
      estimated_time: cleanString(rewrite.estimated_time) || fix.estimated_time,
      time_estimate: cleanString(rewrite.estimated_time) || fix.time_estimate,
      ai_recommendation: steps.length > 0 ? steps.join(" ") : fix.ai_recommendation,
    };
  }).sort(compareFixes);

  const topRecommendedActions = Array.isArray(aiResponse?.top_recommended_actions) && aiResponse.top_recommended_actions.length > 0
    ? aiResponse.top_recommended_actions
        .slice(0, 5)
        .map((action) => hydrateTopAction(action, cleanedFixes))
        .filter((action) => action.title)
    : cleanedFixes.slice(0, 5).map(fixToAction);

  const positives = Array.isArray(aiResponse?.positive_findings) && aiResponse.positive_findings.length > 0
    ? aiResponse.positive_findings.slice(0, 5).map((item) => String(item))
    : fallbackPlan.positive_findings;

  const healthReport = normalizeAiHealthReport({
    aiReport: aiResponse?.website_health_report,
    fallbackReport: fallbackPlan.website_health_report,
    score: fallbackPlan.health_score,
    fixes: cleanedFixes,
    pages,
    body,
    positives,
    siteFingerprint,
  });

  return makeFrontendCompatible({
    ...fallbackPlan,
    plain_english_summary:
      cleanString(aiResponse?.plain_english_summary) || healthReport.overall_explanation || fallbackPlan.plain_english_summary,
    website_health_report: healthReport,
    health_explanation: healthReport.overall_explanation,
    customer_summary: healthReport.overall_explanation,
    top_recommended_actions: topRecommendedActions,
    cleaned_fixes: cleanedFixes,
    raw_fixes: cleanedFixes,
    fixes: cleanedFixes,
    findings: cleanedFixes,
    recommendations: cleanedFixes,
    competitor_insights: [],
    positive_findings: positives,
    ai_rewrites_applied: rewrites.size,
    crawled_pages: pages,
    pages,
    site_fingerprint: siteFingerprint,
  });
}

function hydrateTopAction(action, fixes) {
  const fix = fixes.find((item) => item.id === action?.fix_id || item.fix_id === action?.fix_id);
  if (!fix) {
    return {
      fix_id: "",
      title: cleanString(action?.title) || "Recommended action",
      reason: cleanString(action?.reason) || "Review this recommendation.",
      priority: ["high", "medium", "low"].includes(action?.priority) ? action.priority : "medium",
      affected_pages: [],
      what_to_do_steps: [],
      who_can_do_this: "You",
      time_estimate: "",
    };
  }

  return {
    ...fixToAction(fix),
    title: cleanString(action?.title) || fix.issue_title,
    reason: cleanString(action?.reason) || fix.why_it_matters,
    plain_english_summary: fix.plain_english_explanation,
    why_it_matters: cleanString(action?.reason) || fix.why_it_matters,
    priority: ["high", "medium", "low"].includes(action?.priority)
      ? action.priority
      : fix.priority === "critical" || fix.priority === "high"
        ? "high"
        : fix.priority === "low"
          ? "low"
          : "medium",
  };
}

function normalizeAiHealthReport({ aiReport, fallbackReport, score, fixes, pages, body, positives, siteFingerprint }) {
  const fallback = fallbackReport || buildFallbackHealthReport({ body, pages, fixes, score, positiveFindings: positives, siteFingerprint });
  if (!aiReport || typeof aiReport !== "object") return fallback;
  return {
    health_score: typeof aiReport.health_score === "number" ? Math.max(0, Math.min(100, Math.round(aiReport.health_score))) : fallback.health_score,
    health_grade: cleanString(aiReport.health_grade) || fallback.health_grade,
    overall_explanation: cleanString(aiReport.overall_explanation) || fallback.overall_explanation,
    what_is_working: cleanStringArray(aiReport.what_is_working, 5).length ? cleanStringArray(aiReport.what_is_working, 5) : fallback.what_is_working,
    top_concerns: normalizeHealthCards(aiReport.top_concerns, fallback.top_concerns, 4),
    quick_wins: normalizeHealthCards(aiReport.quick_wins, fallback.quick_wins, 4),
    bigger_projects: normalizeHealthCards(aiReport.bigger_projects, fallback.bigger_projects, 4),
    competitor_takeaways: [],
    limitations: cleanStringArray(aiReport.limitations, 5).length ? cleanStringArray(aiReport.limitations, 5) : fallback.limitations,
    next_best_step: cleanString(aiReport.next_best_step) || fallback.next_best_step,
  };
}

/* -------------------------------------------------------------------------- */
/* Prompt and schema                                                           */
/* -------------------------------------------------------------------------- */

function buildPrompt({ body, websiteUrl, pages, canonicalFixes, fallbackPlan, siteFingerprint }) {
  return `
You are the AI planning layer for FixList.

The deterministic scanner already found the evidence. Your job is to rewrite and explain recommendations in plain English, while preserving the exact fix_id values.

Core instruction:
Create a site-aware SEO plan. Do not treat every SEO issue equally. Prioritize based on:
1. evidence confidence,
2. site-fit,
3. business impact,
4. affected-page reach.

Hard rules:
1. Do not invent new technical findings, URLs, rankings, traffic, leads, or revenue.
2. Do not say anything has already been fixed or published.
3. Only rewrite findings using the exact fix_id values provided.
4. what_to_do must contain 2 to 5 short action steps.
5. who_can_do_this must be either "you" or "your_web_person".
6. Use plain English for a non-technical business owner.
7. Focus top actions on pages that drive leads, sales, bookings, quotes, or trust.
8. News, blog, tag, feed, pagination, and old archive pages should not dominate the top priorities.
9. Guide and Q&A page issues should usually be grouped by template or content family unless the issue affects a true conversion page.
10. For regulated or trust-sensitive sites, prioritize trust, clarity, indexability, and key conversion pages.

Site fingerprint:
${JSON.stringify(siteFingerprint, null, 2)}

Business:
${JSON.stringify(
  {
    business_name: body?.business_name || "",
    business_type: body?.business_type || "",
    city: body?.city || "",
    country: body?.country || "",
    language: body?.language || "",
    website_url: websiteUrl,
    scan_mode: body?.scan_mode || "",
    important_keywords: body?.important_keywords || [],
    business_priority_instruction: body?.business_priority_instruction || null,
  },
  null,
  2
)}

Scan totals:
${JSON.stringify(
  {
    pages_scanned: Array.isArray(pages) ? pages.length : 0,
    health_score: fallbackPlan.health_score,
    pages_found: body?.pages_found || 0,
    pages_crawled: body?.pages_crawled || 0,
    queued_remaining: body?.queued_remaining || 0,
    crawl_scope: body?.crawl_scope || null,
  },
  null,
  2
)}

Technical audit summary:
${JSON.stringify(body?.technical_audit_summary || null, null, 2)}

Prioritized scanner findings with evidence and page-value scores:
${JSON.stringify(canonicalFixes.map(compactFixForPrompt), null, 2)}

Representative page profile:
${JSON.stringify(buildPageProfile(pages), null, 2)}

Fallback website health report:
${JSON.stringify(fallbackPlan.website_health_report || {}, null, 2)}

Return valid JSON only.
`;
}

function responseSchema() {
  return {
    type: "object",
    properties: {
      plain_english_summary: { type: "string" },
      website_health_report: {
        type: "object",
        properties: {
          health_score: { type: "number" },
          health_grade: { type: "string" },
          overall_explanation: { type: "string" },
          what_is_working: { type: "array", items: { type: "string" } },
          top_concerns: {
            type: "array",
            items: {
              type: "object",
              properties: {
                title: { type: "string" },
                plain_english_explanation: { type: "string" },
                why_it_matters: { type: "string" },
                affected_area: { type: "string" },
              },
              required: ["title", "plain_english_explanation"],
            },
          },
          quick_wins: {
            type: "array",
            items: {
              type: "object",
              properties: {
                title: { type: "string" },
                action: { type: "string" },
                expected_benefit: { type: "string" },
              },
              required: ["title", "action"],
            },
          },
          bigger_projects: {
            type: "array",
            items: {
              type: "object",
              properties: {
                title: { type: "string" },
                who_should_handle: { type: "string" },
                why: { type: "string" },
              },
              required: ["title", "who_should_handle"],
            },
          },
          competitor_takeaways: { type: "array", items: { type: "string" } },
          limitations: { type: "array", items: { type: "string" } },
          next_best_step: { type: "string" },
        },
        required: [
          "health_score",
          "health_grade",
          "overall_explanation",
          "what_is_working",
          "top_concerns",
          "quick_wins",
          "bigger_projects",
          "competitor_takeaways",
          "limitations",
          "next_best_step",
        ],
      },
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
            what_to_do: { type: "array", items: { type: "string" } },
            who_can_do_this: { type: "string", enum: ["you", "your_web_person"] },
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
      competitor_insights: { type: "array", items: { type: "object", properties: {} } },
      positive_findings: { type: "array", items: { type: "string" } },
    },
    required: [
      "plain_english_summary",
      "website_health_report",
      "top_recommended_actions",
      "fix_rewrites",
      "competitor_insights",
      "positive_findings",
    ],
  };
}

/* -------------------------------------------------------------------------- */
/* Small helpers                                                               */
/* -------------------------------------------------------------------------- */

function compactFixForPrompt(fix) {
  return {
    fix_id: fix.fix_id || fix.id,
    rule: fix.rule,
    category: fix.category,
    title: fix.issue_title,
    priority: fix.priority,
    page_url: fix.page_url,
    affected_pages: fix.affected_pages?.slice(0, 8) || [],
    why_it_matters: fix.why_it_matters,
    recommended_value: fix.recommended_value,
    page_template_family: fix.page_template_family,
    page_value_score: fix.page_value_score,
    page_value_label: fix.page_value_label,
    business_importance: fix.business_importance,
    evidence_confidence: fix.evidence_confidence,
    site_fit_score: fix.site_fit_score,
    business_impact_score: fix.business_impact_score,
    reach_score: fix.reach_score,
    overall_priority_score: fix.overall_priority_score,
  };
}

function buildPageProfile(pages) {
  const safePages = Array.isArray(pages) ? pages : [];
  return safePages.slice(0, MAX_PROMPT_PAGES).map((page) => ({
    url: cleanPath(page?.url || page?.final_url || ""),
    title: clampText(page?.title || "", 120),
    h1: clampText(page?.h1 || "", 100),
    status_code: Number(page?.status_code || 0),
    indexable: page?.indexable !== false,
    word_count: Number(page?.word_count || 0),
    in_sitemap: Boolean(page?.in_sitemap),
  }));
}

function buildPositiveFindings({ pages, siteFingerprint }) {
  const positives = [];
  if (Array.isArray(pages) && pages.length > 0) positives.push(`The scan reviewed ${pages.length} representative pages.`);
  if (siteFingerprint?.vertical && siteFingerprint.vertical !== "general") positives.push(`FixList identified the site as ${siteFingerprint.vertical_label}.`);
  if (siteFingerprint?.likely_money_page_patterns?.length > 0) positives.push("The review can prioritize likely money pages over low-value archives.");
  return positives.slice(0, 5);
}

function buildGroupedPageRecommendations(fixes) {
  return (fixes || [])
    .filter((fix) => fix.business_importance === "low_value_group" || fix.business_importance === "support_content_group" || (Array.isArray(fix.affected_pages) && fix.affected_pages.length > 3))
    .slice(0, 8)
    .map((fix) => ({
      title: fix.issue_title,
      priority: fix.priority,
      affected_pages: fix.affected_pages || [],
      page_count: fix.affected_pages?.length || 0,
      recommendation: fix.recommended_value,
    }));
}

function fixToAction(fix) {
  return {
    fix_id: fix.fix_id || fix.id,
    title: fix.issue_title,
    reason: fix.why_it_matters,
    priority: fix.priority === "critical" || fix.priority === "high" ? "high" : fix.priority === "low" ? "low" : "medium",
    plain_english_summary: fix.plain_english_explanation,
    why_it_matters: fix.why_it_matters,
    what_to_do_steps: fix.what_to_do_steps || fix.what_to_do || [],
    who_can_do_this: fix.who_can_do_this === "your_web_person" ? "Your web person" : "You",
    time_estimate: fix.time_estimate || fix.estimated_time || "",
    affected_pages: fix.affected_pages || [],
    page_url: fix.page_url || "",
  };
}

function normalizeHealthCards(value, fallback, limit) {
  if (!Array.isArray(value) || value.length === 0) return fallback || [];
  return value.slice(0, limit).map((item) => {
    if (typeof item === "string") return { title: item, plain_english_explanation: "", why_it_matters: "" };
    return {
      title: cleanString(item?.title) || cleanString(item?.headline) || "",
      plain_english_explanation: cleanString(item?.plain_english_explanation) || cleanString(item?.explanation) || cleanString(item?.action) || "",
      why_it_matters: cleanString(item?.why_it_matters) || cleanString(item?.why) || cleanString(item?.expected_benefit) || "",
      affected_area: cleanString(item?.affected_area) || cleanString(item?.who_should_handle) || "",
    };
  }).filter((item) => item.title);
}

function cleanStringArray(value, limit) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, limit).map((item) => cleanString(item)).filter(Boolean);
}

function defaultTitle(category) {
  const titles = {
    "404_error": "Fix pages that are not loading",
    duplicate_content: "Review duplicate search fields",
    meta_description: "Improve search descriptions",
    meta_title: "Improve search titles",
    schema: "Improve trust and structured data",
    thin_content: "Improve thin or unclear pages",
    web_dev: "Review website setup",
    mobile_setup: "Review mobile setup",
    performance_hint: "Review page speed",
    social_metadata: "Review social sharing details",
    indexability: "Review indexability settings",
  };
  return titles[category] || "Review this recommendation";
}

function friendlyCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    duplicate_content: "Search appearance",
    canonical: "Website setup",
    schema: "Trust signals",
    thin_content: "Page content",
    "404_error": "Broken page",
    redirect: "Page redirect",
    internal_link: "Internal links",
    performance: "Website performance",
    web_dev: "Website setup",
    mobile_setup: "Mobile setup",
    performance_hint: "Website performance",
    social_metadata: "Social sharing",
    indexability: "Indexability",
  };
  return map[category] || "Website improvement";
}

function defaultSteps({ category, difficulty, recommendedValue }) {
  if (difficulty === "developer") {
    return [
      "Send this item to your web person.",
      "Ask them to review the affected URL or template.",
      "Apply the safest fix and publish it.",
      "Run FixList again to confirm it is resolved.",
    ];
  }
  if (["meta_title", "meta_description", "duplicate_content"].includes(category)) {
    return [
      "Open the affected page in your website editor.",
      recommendedValue,
      "Save and publish the change.",
      "Run FixList again after publishing.",
    ];
  }
  return [
    "Review the affected page.",
    recommendedValue,
    "Check the page again after publishing.",
  ];
}

function defaultOwner(difficulty) {
  return difficulty === "developer" ? "your_web_person" : "you";
}

function defaultTime(difficulty) {
  return difficulty === "developer" ? "about 1–2 hours" : difficulty === "easy" ? "about 10–15 minutes" : "about 30–60 minutes";
}

function normalizeStatus(value) {
  const status = String(value || "").toLowerCase();
  if (["needs_approval", "auto_fixed", "needs_developer", "open"].includes(status)) return status;
  return "needs_approval";
}

function normalizeDifficulty(value, status) {
  const difficulty = String(value || "").toLowerCase();
  if (["easy", "moderate", "developer"].includes(difficulty)) return difficulty;
  if (status === "needs_developer") return "developer";
  return "moderate";
}

function normalizePriority(value) {
  const priority = String(value || "").toLowerCase();
  if (["critical", "high", "medium", "low"].includes(priority)) return priority;
  return "medium";
}

function calculateFallbackScore(fixes) {
  const safeFixes = Array.isArray(fixes) ? fixes : [];
  const penalty = safeFixes.reduce((total, fix) => {
    if (fix.priority === "critical") return total + 15;
    if (fix.priority === "high") return total + 10;
    if (fix.priority === "medium") return total + 5;
    return total + 2;
  }, 0);
  return Math.max(20, Math.min(95, 92 - penalty));
}

function scoreToGrade(score) {
  if (score >= 90) return "Excellent";
  if (score >= 75) return "Good";
  if (score >= 55) return "Fair";
  return "Needs work";
}

function isLowValuePage(url) {
  const path = cleanPath(url).toLowerCase();
  if (/\/(20\d{2})([-/](janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december))?(\/|$)/i.test(path)) return true;
  if (/\/(20\d{2})[-/]?\d{1,2}(\/|$)/i.test(path)) return true;
  return LOW_VALUE_PAGE_PATTERNS.some((pattern) => path.includes(pattern));
}

function isCosmeticIssue(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""}`.toLowerCase();
  for (const rule of COSMETIC_RULES) {
    if (value.includes(rule) || value.includes(rule.replace(/_/g, " "))) return true;
  }
  return false;
}

function isSevereIssue(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.current_value || ""}`.toLowerCase();
  for (const rule of SEVERE_RULES) {
    if (value.includes(rule) || value.includes(rule.replace(/_/g, " "))) return true;
  }
  return ["404", "410", "500", "503"].some((code) => value.includes(code));
}

function isTrustOrEntityIssue(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""}`.toLowerCase();
  return hasAny(value, ["trust", "schema", "organization", "localbusiness", "legal", "review", "address", "phone", "contact", "entity"]);
}

function hasAny(text, values) {
  const haystack = String(text || "").toLowerCase();
  return values.some((value) => haystack.includes(String(value).toLowerCase()));
}

function countIncludes(text, keyword) {
  const haystack = String(text || "").toLowerCase();
  const needle = String(keyword || "").toLowerCase();
  if (!needle) return 0;
  return haystack.split(needle).length - 1;
}

function cleanPath(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    if (/^https?:\/\//i.test(raw)) {
      const parsed = new URL(raw);
      return parsed.pathname || "/";
    }
  } catch {
    // fall through
  }
  return raw.startsWith("/") ? raw : `/${raw}`;
}

function cleanString(value) {
  if (typeof value === "string" && value.trim()) return value.trim();
  return "";
}

function stringifyValue(value) {
  if (typeof value === "string") return value.trim();
  if (value == null) return "";
  try {
    return JSON.stringify(value).slice(0, 500);
  } catch {
    return String(value);
  }
}

function clampText(value, max) {
  const text = String(value || "").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trim()}…`;
}

function stableId(input) {
  let hash = 0;
  const value = String(input || "");
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return `finding_${Math.abs(hash)}`;
}

async function withTimeout(promise, timeoutMs, label) {
  return await Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs);
    }),
  ]);
}
