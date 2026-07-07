import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") || "";
const GEMINI_MODEL = Deno.env.get("GEMINI_MODEL") || "gemini-3.1-flash-lite";
const GEMINI_BASE_URL = Deno.env.get("GEMINI_BASE_URL") || "https://generativelanguage.googleapis.com/v1beta/models";
const GEMINI_AI_TIMEOUT_MS = Number(Deno.env.get("GEMINI_AI_TIMEOUT_MS") || 60000);
const BASE44_AI_TIMEOUT_MS = Number(Deno.env.get("BASE44_AI_TIMEOUT_MS") || 25000);
const AI_PROVIDER_ORDER = Deno.env.get("AI_PROVIDER_ORDER") || "gemini_first";
const MAX_AI_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 36);
const MAX_PROMPT_PAGES = Number(Deno.env.get("MAX_PROMPT_PAGES") || 36);

const SCORING_MODEL = "fixlist_business_intent_v4_route_boundaries_meta_gate";

const CATEGORY_MAP = {
  broken_page: "404_error",
  page_heading: "thin_content",
  placeholder_text: "web_dev",
  faq_gap: "thin_content",
  cta_gap: "thin_content",
  trust_signal_gap: "schema",
  image_alt_text: "image_alt_text",
  duplicate_search_titles: "duplicate_content",
  duplicate_search_descriptions: "duplicate_content",
  duplicate_description: "duplicate_content",
  mobile_setup: "mobile_setup",
  performance_hint: "performance_hint",
  social_metadata: "social_metadata",
  indexability: "indexability",
};

const LOW_VALUE_SEGMENT_PATTERNS = [
  "/actualites/",
  "/news/",
  "/blog/",
  "/archive/",
  "/archives/",
  "/tag/",
  "/tags/",
  "/author/",
  "/feed/",
  "/rss/",
  "/page/",
];

const LOW_VALUE_QUERY_PATTERNS = ["?page=", "&page=", "?p=", "&p=", "?tag=", "&tag="];

const INTERNAL_ROUTE_PATTERNS = [
  "/admin",
  "/developer",
  "/assistant",
  "/billing",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/dashboard",
  "/issues",
  "/reports",
  "/crawl-status",
  "/metadata",
  "/canonicals",
  "/redirects",
  "/js-rendering",
  "/competitors",
];

const TRUST_PAGE_PATTERNS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales"];

const SEVERE_RULES = new Set([
  "broken_page",
  "404_error",
  "410_error",
  "server_error",
  "redirect_loop",
  "blocked_by_robots",
  "blocked_page",
  "noindex",
  "canonical_missing",
  "canonical_to_other_domain",
  "internal_route_indexable",
  "duplicate_route_casing",
  "indexability",
]);

const STRUCTURAL_RULES = new Set([
  "broken_page",
  "404_error",
  "410_error",
  "server_error",
  "redirect_loop",
  "canonical_missing",
  "canonical_to_other_domain",
  "mobile_setup",
  "performance_hint",
  "js_rendering",
  "client_rendering",
  "internal_link",
  "duplicate_route_casing",
  "free_base44_subdomain",
]);

const SEMANTIC_RULES = new Set([
  "schema",
  "social_metadata",
  "structured_data",
  "product_schema",
  "localbusiness_schema",
  "breadcrumb_schema",
]);

const CONTENT_TRUST_RULES = new Set([
  "trust_signal_gap",
  "missing_trust_pages",
  "faq_gap",
  "cta_gap",
  "thin_content",
  "thin_repetitive_public_snapshots",
  "author",
  "reviewer",
  "methodology",
  "content_quality",
]);

const METADATA_RULES = new Set([
  "missing_meta_description",
  "long_meta_description",
  "short_meta_description",
  "missing_title",
  "long_title",
  "short_title",
  "duplicate_title",
  "duplicate_meta_description",
  "duplicate_content",
]);

const VERTICAL_PROFILES = {
  insurance_finance: {
    label: "insurance / finance lead generation",
    keywords: ["assurance", "insurance", "pret", "prêt", "credit", "crédit", "loan", "mortgage", "finance", "banque", "bank", "taux", "emprunteur", "mutuelle", "devis", "simulation", "comparateur", "compare"],
    moneyPatterns: ["/devis", "/quote", "/simulation", "/simulateur", "/calcul", "/calculator", "/comparateur", "/compare", "/tarif", "/contact", "/souscription"],
  },
  travel_booking: {
    label: "booking / experiences marketplace",
    keywords: ["booking", "reservation", "réservation", "activity", "activities", "activite", "activité", "event", "tour", "destination", "billet", "ticket", "travel", "voyage", "stage", "pilotage", "pass"],
    moneyPatterns: ["/booking", "/reservation", "/activity", "/activities", "/activite", "/activité", "/event", "/tour", "/destination", "/billet", "/ticket", "/stage", "/pilotage", "/pass", "/show"],
  },
  ecommerce: {
    label: "ecommerce / product catalog",
    keywords: ["product", "produit", "shop", "boutique", "cart", "panier", "checkout", "price", "prix", "sku", "collection", "category"],
    moneyPatterns: ["/products/", "/product/", "/produit/", "/collections/", "/collection/", "/category/", "/categorie/", "/shop", "/boutique", "/cart", "/checkout"],
  },
  saas_app: {
    label: "SaaS or web app",
    keywords: ["dashboard", "login", "register", "app", "billing", "admin", "workspace", "account", "subscription", "developer"],
    moneyPatterns: ["/pricing", "/register", "/signup", "/demo", "/contact", "/features", "/use-cases"],
  },
  local_service: {
    label: "local service business",
    keywords: ["service", "services", "contact", "appointment", "rendez-vous", "near me", "local", "agency", "agence", "location", "adresse", "phone"],
    moneyPatterns: ["/services", "/service", "/contact", "/appointment", "/rendez-vous", "/devis", "/quote", "/location", "/agence"],
  },
  content_publisher: {
    label: "content / blog-heavy site",
    keywords: ["blog", "news", "article", "guide", "resources", "insights", "author"],
    moneyPatterns: ["/newsletter", "/subscribe", "/contact", "/resources", "/guide"],
  },
  general: {
    label: "general website",
    keywords: [],
    moneyPatterns: ["/contact", "/services", "/products", "/pricing"],
  },
};

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ success: false, error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const websiteUrl = body.website_url || body.normalized_url || body.url || "";
    const pages = pickFirstNonEmptyArray([body.crawled_pages, body.pages, body.scanned_pages, body.crawl_pages]);
    const rawFixes = pickFirstNonEmptyArray([body.raw_fixes, body.grouped_findings, body.raw_findings, body.findings, body.fixes, body.recommendations, body.issues]);

    const siteFingerprint = buildSiteFingerprint({ body, pages, websiteUrl });
    const syntheticFixes = buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint });
    const canonicalFixes = prepareFixes([...rawFixes, ...syntheticFixes], siteFingerprint, body);
    const aiFixes = canonicalFixes.slice(0, MAX_AI_FIXES);
    const fallbackPlan = buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint });

    if (!websiteUrl || canonicalFixes.length === 0) {
      return Response.json({
        success: true,
        ai_provider: "scanner_fallback",
        ai_review_warning: !websiteUrl ? "AI review ran, but website_url was missing. Scanner recommendations are shown." : "AI review ran, but no scanner recommendations were provided.",
        ...fallbackPlan,
      });
    }

    const prompt = buildPrompt({ body, websiteUrl, pages, canonicalFixes: aiFixes, fallbackPlan, siteFingerprint });
    const aiErrors = [];
    const providers = AI_PROVIDER_ORDER === "base44_first" ? ["base44", "gemini"] : ["gemini", "base44"];

    for (const provider of providers) {
      if (provider === "gemini") {
        if (!GEMINI_API_KEY) {
          aiErrors.push("GEMINI_API_KEY is not configured.");
          continue;
        }
        try {
          const geminiResponse = await callGeminiAiReview({ prompt, schema: responseSchema() });
          const merged = mergeAiIntoFallback({ aiResponse: geminiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint });
          return Response.json({ success: true, ai_provider: "gemini", ai_review_warning: aiErrors.join(" "), ...merged });
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
            base44.integrations.Core.InvokeLLM({ prompt, response_json_schema: responseSchema() }),
            BASE44_AI_TIMEOUT_MS,
            "Base44 AI review"
          );
          const aiResponse = unwrapAiResponse(rawBase44Response);
          const merged = mergeAiIntoFallback({ aiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint });
          return Response.json({ success: true, ai_provider: "base44_invokellm", ai_review_warning: aiErrors.join(" "), ...merged });
        } catch (error) {
          aiErrors.push(`Base44 AI failed: ${error?.message || "Unknown Base44 AI error."}`);
        }
      }
    }

    return Response.json({ success: true, ai_provider: "scanner_fallback", ai_review_warning: aiErrors.join(" ") || "AI review failed, so scanner recommendations are shown.", ...fallbackPlan });
  } catch (error) {
    console.error("aiReviewScan failed", error);
    return Response.json({ success: false, error: "aiReviewScan failed. Please try again." }, { status: 500 });
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
      headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.1, maxOutputTokens: 7000, responseMimeType: "application/json", responseSchema: schema },
      }),
    }),
    GEMINI_AI_TIMEOUT_MS,
    "Gemini AI review"
  );

  const text = await response.text();
  if (!response.ok) throw new Error(`Gemini returned status ${response.status}: ${clampText(text, 600)}`);
  const payload = JSON.parse(text);
  const modelText = (payload?.candidates?.[0]?.content?.parts || []).map((part) => part?.text || "").filter(Boolean).join("\n").trim();
  if (!modelText) throw new Error("Gemini response did not include output text.");
  return parseJsonObject(modelText);
}

function parseJsonObject(value) {
  const raw = String(value || "").trim();
  if (!raw) return {};
  const cleaned = raw.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/```$/i, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const firstBrace = cleaned.indexOf("{");
    const lastBrace = cleaned.lastIndexOf("}");
    if (firstBrace >= 0 && lastBrace > firstBrace) return JSON.parse(cleaned.slice(firstBrace, lastBrace + 1));
    throw new Error("AI returned text that could not be parsed as JSON.");
  }
}

function unwrapAiResponse(response) {
  if (!response) return {};
  if (typeof response === "string") return parseJsonObject(response);
  if (response?.data?.data) return response.data.data;
  if (response?.data?.result) return response.data.result;
  if (response?.data) return response.data;
  if (response?.result?.data) return response.result.data;
  if (response?.result) return response.result;
  return response;
}

/* -------------------------------------------------------------------------- */
/* Fingerprint and strategic findings                                           */
/* -------------------------------------------------------------------------- */

function buildSiteFingerprint({ body, pages, websiteUrl }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const pageText = safePages.slice(0, 160).map((page) => [page?.url, page?.final_url, page?.title, page?.h1, page?.meta_description, page?.page_template_family, page?.estimated_page_intent].join(" ")).join(" ").toLowerCase();
  const combinedText = [websiteUrl, body?.business_name, body?.business_type, body?.cms_name, body?.cms_platform, pageText].join(" ").toLowerCase();

  const verticalScores = Object.entries(VERTICAL_PROFILES).map(([key, profile]) => ({
    key,
    label: profile.label,
    score: profile.keywords.reduce((total, keyword) => total + countIncludes(combinedText, keyword), 0),
  })).sort((a, b) => b.score - a.score);
  const vertical = verticalScores[0]?.score > 0 ? verticalScores[0].key : "general";
  const confidence = verticalScores[0]?.score > 0 ? Math.min(0.95, 0.45 + verticalScores[0].score / Math.max(10, verticalScores[0].score + (verticalScores[1]?.score || 0))) : 0.35;

  const pagesFound = Number(body?.pages_found || safePages.length || 0);
  const pagesCrawled = Number(body?.pages_crawled || safePages.length || 0);
  const sizeBasis = Math.max(pagesFound, pagesCrawled, safePages.length);
  const hostname = safeHostname(websiteUrl);
  const freeBase44Subdomain = hostname.endsWith(".base44.app");
  const internalRouteCount = safePages.filter((page) => isInternalAppRoute(page?.url || page?.final_url)).length;
  const routeBoundaryRisk = internalRouteCount >= 4 ? "high" : internalRouteCount > 0 ? "medium" : "low";

  return {
    vertical,
    vertical_label: VERTICAL_PROFILES[vertical]?.label || "general website",
    vertical_confidence: Number(confidence.toFixed(2)),
    business_model: detectBusinessModel(combinedText, vertical),
    size_band: sizeBasis >= 1000 ? "enterprise" : sizeBasis >= 150 ? "mid_market" : sizeBasis >= 30 ? "smb" : "micro",
    pages_found: pagesFound,
    pages_crawled: pagesCrawled,
    localization: detectLocalization(safePages, websiteUrl),
    render_mode: detectRenderMode(body, safePages),
    regulatory_sensitivity: ["insurance_finance"].includes(vertical) ? "regulated" : "standard",
    likely_money_page_patterns: VERTICAL_PROFILES[vertical]?.moneyPatterns || VERTICAL_PROFILES.general.moneyPatterns,
    low_value_page_patterns: LOW_VALUE_SEGMENT_PATTERNS,
    internal_route_count: internalRouteCount,
    route_boundary_risk: routeBoundaryRisk,
    free_base44_subdomain: freeBase44Subdomain,
    scoring_model: SCORING_MODEL,
  };
}

function detectBusinessModel(text, vertical) {
  if (hasAny(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"])) return "quote_or_comparison_lead_gen";
  if (hasAny(text, ["booking", "reservation", "réservation", "availability", "calendar", "book now", "ticket", "stage", "pass"])) return "booking_or_reservation";
  if (hasAny(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart"])) return "catalog_or_ecommerce";
  if (hasAny(text, ["login", "dashboard", "subscription", "billing", "admin"])) return "saas_or_member_app";
  if (vertical === "insurance_finance") return "regulated_lead_generation";
  if (vertical === "travel_booking") return "booking_or_reservation";
  if (vertical === "ecommerce") return "catalog_or_ecommerce";
  if (hasAny(text, ["contact", "rendez-vous", "appointment", "agence", "location"])) return "local_lead_generation";
  return "content_or_general_business";
}

function detectLocalization(pages, websiteUrl) {
  const text = [websiteUrl, ...pages.slice(0, 80).map((page) => page?.url || page?.final_url || "")].join(" ").toLowerCase();
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

function buildStrategicFindings({ pages, websiteUrl, siteFingerprint }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const fixes = [];
  const hostname = safeHostname(websiteUrl);

  if (hostname.endsWith(".base44.app")) {
    fixes.push(makeSyntheticFix({
      rule: "free_base44_subdomain",
      category: "indexability",
      priority: "high",
      title: "Move production SEO to a custom domain",
      explanation: "The site is on a free Base44 subdomain. That can be crawled, but it is not the strongest production SEO or trust setup for an SEO product.",
      why: "A custom domain improves brand trust, shareability, Search Console ownership, and company-specific search signals.",
      recommendation: "Connect a branded custom domain before treating this as the long-term production SEO home.",
      affectedPages: ["/"],
      difficulty: "developer",
    }));
  }

  const internalPages = safePages.filter((page) => isInternalAppRoute(page?.url || page?.final_url) && pageIsIndexable(page));
  if (internalPages.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "internal_route_indexable",
      category: "indexability",
      priority: "critical",
      title: "Keep internal app routes out of search",
      explanation: "FixList found app-like routes such as login, admin, billing, dashboard, reports, or reset-password in the crawlable page set.",
      why: "These pages are usually not useful landing pages. Letting them appear in search can dilute the site, confuse prospects, and expose the product structure.",
      recommendation: "Require authentication for private areas or apply noindex to internal/auth routes. Keep only true marketing/help pages indexable.",
      affectedPages: internalPages.map((page) => cleanPath(page?.url || page?.final_url || "/")).slice(0, 50),
      difficulty: "developer",
    }));
  }

  const duplicateCasing = findDuplicateCasingRoutes(safePages);
  if (duplicateCasing.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "duplicate_route_casing",
      category: "duplicate_content",
      priority: "high",
      title: "Consolidate duplicate URL casing",
      explanation: "The crawl found URL variants that differ mainly by capitalization, such as /Dashboard and /dashboard.",
      why: "Duplicate route casing creates canonical ambiguity, splits signals, and makes analytics harder to trust.",
      recommendation: "Choose one canonical URL, update internal links to that version, and redirect or noindex the duplicate casing variant.",
      affectedPages: duplicateCasing.slice(0, 50),
      difficulty: "developer",
    }));
  }

  const paths = safePages.map((page) => cleanPath(page?.url || page?.final_url || "").toLowerCase());
  const hasTrustPage = TRUST_PAGE_PATTERNS.some((pattern) => paths.some((path) => path.startsWith(pattern)));
  const isTrustSensitive = siteFingerprint.regulatory_sensitivity === "regulated" || siteFingerprint.vertical === "saas_app" || siteFingerprint.free_base44_subdomain;
  if (!hasTrustPage && safePages.length >= 4 && isTrustSensitive) {
    fixes.push(makeSyntheticFix({
      rule: "missing_trust_pages",
      category: "schema",
      priority: siteFingerprint.regulatory_sensitivity === "regulated" ? "high" : "medium",
      title: "Add public trust pages",
      explanation: "FixList did not see obvious public About, Contact, Privacy, Terms, or Security pages in the crawl sample.",
      why: "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.",
      recommendation: "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.",
      affectedPages: ["/"],
      difficulty: "moderate",
    }));
  }

  const repeatedThin = findRepeatedSnapshotGroups(safePages);
  if (repeatedThin.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "thin_repetitive_public_snapshots",
      category: "thin_content",
      priority: "high",
      title: "Reduce thin repetitive public snapshots",
      explanation: "Several public routes appear to return very similar titles, headings, or short descriptions.",
      why: "A technically crawlable page is not always a useful indexable page. Thin repeated snapshots can dilute a product site and make it look unfinished.",
      recommendation: "Keep internal app pages private/noindex and add richer, route-specific content only to pages that are meant to rank or convert.",
      affectedPages: repeatedThin.slice(0, 50),
      difficulty: "moderate",
    }));
  }

  return fixes;
}

function makeSyntheticFix({ rule, category, priority, title, explanation, why, recommendation, affectedPages, difficulty }) {
  const page = affectedPages?.[0] || "/";
  const id = stableId(`synthetic|${rule}|${page}|${title}`);
  return {
    id,
    fix_id: id,
    type: "site_level",
    rule,
    category,
    customer_category: friendlyCategory(category),
    issue_title: title,
    title,
    plain_english_explanation: explanation,
    plain_english_summary: explanation,
    why_it_matters: why,
    current_value: "Detected from crawl and route patterns.",
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    priority,
    difficulty,
    status: difficulty === "developer" ? "needs_developer" : "needs_approval",
    can_auto_fix: false,
    requires_approval: difficulty !== "developer",
    requires_developer: difficulty === "developer",
    affected_pages: affectedPages || [page],
    page_url: page,
    confidence_score: 92,
    what_to_do: defaultSteps({ category, difficulty, recommendedValue: recommendation }),
    what_to_do_steps: defaultSteps({ category, difficulty, recommendedValue: recommendation }),
    fix_steps: defaultSteps({ category, difficulty, recommendedValue: recommendation }),
    who_can_do_this: defaultOwner(difficulty),
    estimated_time: defaultTime(difficulty),
    time_estimate: defaultTime(difficulty),
    source: "fixlist_strategy_layer",
  };
}

/* -------------------------------------------------------------------------- */
/* Scoring and grouping                                                         */
/* -------------------------------------------------------------------------- */

function prepareFixes(rawFixes, siteFingerprint, body) {
  const normalized = dedupeByFixId((Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) => normalizeFix(fix, index)));
  const scored = normalized.map((fix) => scoreFixForSite(fix, siteFingerprint, body));
  return groupRepeatedIssues(groupTemplateIssues(scored)).sort(compareFixes).slice(0, 90);
}

function scoreFixForSite(fix, siteFingerprint, body) {
  const pageUrl = cleanPath(fix?.page_url || fix?.affected_pages?.[0] || "/") || "/";
  const pageValue = scorePageValue(pageUrl, siteFingerprint, body);
  const pageType = classifyPageType(pageUrl, pageValue, siteFingerprint, fix);
  const defectClass = classifyDefectClass(fix, pageType, pageValue, siteFingerprint);
  const evidenceConfidence = scoreEvidenceConfidence(fix);
  const reachScore = scoreReach(fix);
  const siteFitScore = scoreSiteFit(fix, pageValue, siteFingerprint, defectClass);
  const businessImpactScore = scoreBusinessImpact(fix, pageValue, siteFingerprint, defectClass);
  const metadataIssue = isMetadataIssue(fix);
  const metaRewriteAllowed = shouldAllowMetaRewrite({ fix, pageType, pageValue, defectClass });
  const cosmetic = isCosmeticIssue(fix);
  const severe = isSevereIssue(fix);
  const imageAlt = isImageAltIssue(fix);

  let priority = normalizePriority(fix.priority);
  let issueTitle = fix.issue_title;
  let why = fix.why_it_matters;
  let recommendedValue = fix.recommended_value;

  if (imageAlt) {
    issueTitle = issueTitle.toLowerCase().includes("image") ? issueTitle : "Add useful image descriptions";
    why = why || "Image alt text helps accessibility and can help search engines understand important images, but it should not be treated like page metadata.";
    recommendedValue = recommendedValue || "Add short, specific alt text to meaningful images. Decorative images can stay empty.";
  }

  if (metadataIssue && !metaRewriteAllowed && !severe) {
    priority = pageType === "article_or_archive" || pageType === "support_guide_or_qa" ? "medium" : "low";
    why = "This is a metadata cleanup item, but FixList found a more important page-type, crawl/index, trust, schema, or template signal first. Handle this as a later batch unless it is on a true money page.";
    recommendedValue = "Do not rewrite this page one by one yet. Fix higher-impact page or template issues first, then batch metadata cleanup.";
  }

  if (pageValue.classification === "internal_or_auth_route") {
    priority = severe || metadataIssue ? "high" : priority;
    if (defectClass === "crawl_index") priority = "critical";
  } else if (pageValue.classification === "low_value" && cosmetic && !severe) {
    priority = "low";
    issueTitle = issueTitle.toLowerCase().includes("archive") ? issueTitle : `Low-priority archive cleanup: ${issueTitle}`;
    why = "This is on a news, blog, tag, pagination, or archive-style page. It should not outrank core service, quote, calculator, product, booking, or contact pages.";
    recommendedValue = "Review these lower-value pages later as a batch, after important business pages are fixed.";
  } else if (pageValue.classification === "low_value" && severe) {
    priority = priority === "critical" || priority === "high" ? "medium" : priority;
    why = "This is a real technical issue, but it is on a lower-priority archive-style page. Fix it after core business pages unless users actively reach this URL.";
  } else if (pageValue.classification === "support_content" && cosmetic && !severe) {
    priority = priority === "critical" || priority === "high" ? "medium" : priority;
    why = "This support page can help search visibility, but it should be handled as a content/template cleanup after main conversion pages.";
  } else if (pageValue.classification === "money_page" && priority === "low") {
    priority = "medium";
  }

  if (siteFingerprint.regulatory_sensitivity === "regulated" && isTrustOrEntityIssue(fix)) priority = priority === "low" ? "medium" : priority;

  const overallPriorityScore = Math.round(evidenceConfidence * 0.2 + siteFitScore * 0.24 + businessImpactScore * 0.42 + reachScore * 0.14);

  return {
    ...fix,
    priority,
    issue_title: issueTitle,
    title: issueTitle,
    why_it_matters: why,
    recommended_value: recommendedValue,
    ai_recommendation: recommendedValue,
    page_url: pageUrl,
    page_type: pageType,
    page_template_family: getTemplateFamily(pageUrl),
    page_value_score: pageValue.score,
    page_value_label: pageValue.label,
    primary_defect_class: defectClass,
    meta_rewrite_allowed: metaRewriteAllowed,
    meta_regeneration_gate: metadataIssue ? (metaRewriteAllowed ? "allowed_metadata_is_primary_gap" : "blocked_metadata_not_primary_gap") : "not_metadata",
    business_importance: pageValue.classification,
    evidence_confidence: evidenceConfidence,
    site_fit_score: siteFitScore,
    business_impact_score: businessImpactScore,
    reach_score: reachScore,
    overall_priority_score: Math.max(0, Math.min(100, overallPriorityScore)),
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

  if (path === "/" || path.endsWith("/index.html")) { score += 35; reasons.push("homepage or section landing page"); }
  if (requested && (path === requested || path === `${requested}/` || path === `${requested}/index.html`)) { score += 35; reasons.push("scanned section landing page"); }
  if (isInternalAppRoute(path)) { score += 32; reasons.push("internal/app route boundary"); }
  for (const pattern of moneyPatterns) {
    if (path.includes(pattern)) { score += 18; reasons.push(`matches ${pattern}`); break; }
  }
  if (hasAny(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "pricing", "demo", "signup"])) { score += 25; reasons.push("conversion or lead page"); }
  if (family === "guide" || family === "qa" || family === "legal_info") { score += siteFingerprint.vertical === "insurance_finance" ? 8 : 5; reasons.push("supporting guide/Q&A/legal content"); }
  if (isLowValuePage(path)) { score -= 45; reasons.push("news/blog/tag/archive/pagination pattern"); }

  const clamped = Math.max(0, Math.min(100, score));
  const classification = isInternalAppRoute(path)
    ? "internal_or_auth_route"
    : clamped >= 70
      ? "money_page"
      : clamped <= 30
        ? "low_value"
        : ["guide", "qa", "legal_info"].includes(family)
          ? "support_content"
          : "standard";
  return {
    score: clamped,
    classification,
    label: classification === "internal_or_auth_route" ? "Internal/auth/app route" : classification === "money_page" ? "Important business page" : classification === "low_value" ? "Lower-priority archive/tag page" : classification === "support_content" ? "Supporting guide/Q&A page" : "Standard page",
    reasons,
  };
}

function scoreEvidenceConfidence(fix) {
  let score = typeof fix?.confidence_score === "number" ? fix.confidence_score : 72;
  if (fix?.source === "screaming_frog_lite" || fix?.source === "fixlist_strategy_layer") score += 10;
  if (fix?.current_value) score += 5;
  if (Array.isArray(fix?.affected_pages) && fix.affected_pages.length > 1) score += 5;
  if (!fix?.page_url && (!fix?.affected_pages || fix.affected_pages.length === 0)) score -= 15;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreReach(fix) {
  const count = Array.isArray(fix?.affected_pages) ? fix.affected_pages.length : 1;
  return Math.max(5, Math.min(100, count * 12));
}

function scoreSiteFit(fix, pageValue, siteFingerprint, defectClass = "metadata") {
  let score = 45 + pageValue.score * 0.45;
  const value = `${fix?.category || ""} ${fix?.rule || ""} ${fix?.issue_title || ""}`.toLowerCase();
  if (siteFingerprint.vertical === "insurance_finance" && hasAny(value, ["schema", "trust", "duplicate", "title", "meta", "404", "index", "privacy", "legal"])) score += 15;
  if (siteFingerprint.vertical === "ecommerce" && hasAny(value, ["schema", "product", "canonical", "duplicate", "index", "blocked", "404"])) score += 15;
  if (siteFingerprint.vertical === "travel_booking" && hasAny(value, ["schema", "internal", "index", "canonical", "thin", "404", "booking", "ticket"])) score += 15;
  if (siteFingerprint.vertical === "saas_app" && hasAny(value, ["internal", "auth", "login", "dashboard", "canonical", "duplicate", "noindex"])) score += 20;
  if (siteFingerprint.regulatory_sensitivity === "regulated" && isTrustOrEntityIssue(fix)) score += 18;
  if (["structural", "crawl_index", "semantic_schema", "content_trust", "security_trust"].includes(defectClass)) score += 12;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreBusinessImpact(fix, pageValue, siteFingerprint, defectClass = "metadata") {
  let score = pageValue.score;
  if (isSevereIssue(fix)) score += 25;
  if (isCosmeticIssue(fix)) score -= pageValue.classification === "low_value" ? 25 : pageValue.classification === "support_content" ? 12 : 5;
  if (pageValue.classification === "internal_or_auth_route" && defectClass === "crawl_index") score += 35;
  if (siteFingerprint.free_base44_subdomain && String(fix?.rule || "").includes("free_base44")) score += 30;
  if (siteFingerprint.business_model?.includes("quote") && hasAny(fix.page_url, ["devis", "quote", "simulation", "comparateur"])) score += 18;
  if (siteFingerprint.business_model?.includes("booking") && hasAny(fix.page_url, ["booking", "reservation", "activity", "event", "ticket", "stage", "pass"])) score += 18;
  if (["structural", "crawl_index", "security_trust"].includes(defectClass)) score += 18;
  if (defectClass === "semantic_schema" && pageValue.classification === "money_page") score += 15;
  if (defectClass === "content_trust" && (siteFingerprint.regulatory_sensitivity === "regulated" || siteFingerprint.free_base44_subdomain)) score += 18;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function groupRepeatedIssues(fixes) {
  const keep = [];
  const groups = new Map();
  for (const fix of fixes || []) {
    const severeGroup = isRepeatedSevereCandidate(fix) && normalizeAffectedPages(fix, fix.page_url).length >= 3;
    if (!severeGroup) {
      keep.push(fix);
      continue;
    }
    const family = fix.page_template_family || getTemplateFamily(fix.page_url);
    const key = `severe|${fix.rule || fix.category}|${family}|${statusBucket(fix)}`;
    const existing = groups.get(key) || {
      ...fix,
      id: stableId(`repeated_${key}`),
      fix_id: stableId(`repeated_${key}`),
      page_url: "",
      issue_title: repeatedSevereTitle(fix, family),
      title: repeatedSevereTitle(fix, family),
      plain_english_explanation: "Several similar pages are failing or blocked in the same way. Treat this as one template, access, or crawlability problem instead of many separate tasks.",
      plain_english_summary: "Several similar pages are failing or blocked in the same way. Treat this as one template, access, or crawlability problem instead of many separate tasks.",
      why_it_matters: "Repeated blocked or failed pages can hide products, listings, bookings, or important content from search engines and users. Grouping keeps the FixList practical.",
      recommended_value: "Check whether the affected page template, firewall, bot protection, redirects, or server rules are blocking the crawler. Fix the shared cause, then rescan.",
      ai_recommendation: "Check whether the affected page template, firewall, bot protection, redirects, or server rules are blocking the crawler. Fix the shared cause, then rescan.",
      affected_pages: [],
      page_count: 0,
      priority: fix.business_importance === "low_value" ? "medium" : "high",
      difficulty: "developer",
      who_can_do_this: "your_web_person",
      estimated_time: "about 1–2 hours",
      time_estimate: "about 1–2 hours",
      primary_defect_class: "structural",
      meta_rewrite_allowed: false,
      meta_regeneration_gate: "not_metadata",
      overall_priority_score: Math.max(72, Number(fix.overall_priority_score || 0)),
      what_to_do: ["Send the grouped affected URLs to your web person.", "Check whether bot protection, redirects, firewall rules, or a shared template are causing the failures.", "Fix the shared cause instead of editing every page one by one.", "Run FixList again to confirm the pages load."],
      what_to_do_steps: ["Send the grouped affected URLs to your web person.", "Check whether bot protection, redirects, firewall rules, or a shared template are causing the failures.", "Fix the shared cause instead of editing every page one by one.", "Run FixList again to confirm the pages load."],
    };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...normalizeAffectedPages(fix, fix.page_url)])).slice(0, 150);
    existing.page_count = existing.affected_pages.length;
    existing.reach_score = scoreReach(existing);
    groups.set(key, existing);
  }
  return [...keep, ...groups.values()];
}

function groupTemplateIssues(fixes) {
  const keep = [];
  const groups = new Map();
  for (const fix of fixes || []) {
    const family = fix.page_template_family || getTemplateFamily(fix.page_url);
    const shouldGroupLowValue = fix.business_importance === "low_value" && fix.priority === "low" && isCosmeticIssue(fix);
    const shouldGroupSupport = ["guide", "qa", "legal_info"].includes(family) && fix.business_importance === "support_content" && isCosmeticIssue(fix) && !isSevereIssue(fix);
    const shouldGroupBlockedMeta = fix.meta_regeneration_gate === "blocked_metadata_not_primary_gap" && !isSevereIssue(fix) && fix.business_importance !== "money_page";
    if (!shouldGroupLowValue && !shouldGroupSupport && !shouldGroupBlockedMeta) {
      keep.push(fix);
      continue;
    }
    const groupFamily = shouldGroupSupport ? family : shouldGroupLowValue ? "archive" : fix.page_type || "metadata_later";
    const key = `${groupFamily}|${fix.rule || fix.category || "cleanup"}`;
    const title = shouldGroupSupport ? supportGroupTitle(fix, family) : shouldGroupLowValue ? archiveGroupTitle(fix) : deferredMetaGroupTitle(fix, groupFamily);
    const existing = groups.get(key) || {
      ...fix,
      id: stableId(`template_group_${key}`),
      fix_id: stableId(`template_group_${key}`),
      page_url: "",
      issue_title: title,
      title,
      plain_english_explanation: shouldGroupSupport ? "Several guide or Q&A pages have the same SEO cleanup issue. Treat this as a template/content cleanup instead of separate one-off tasks." : shouldGroupLowValue ? "Several news, blog, tag, pagination, or archive pages have the same lower-priority cleanup issue." : "Several pages have metadata cleanup opportunities, but metadata is not the first bottleneck for this page type.",
      plain_english_summary: shouldGroupSupport ? "Several guide or Q&A pages have the same SEO cleanup issue. Treat this as a template/content cleanup instead of separate one-off tasks." : shouldGroupLowValue ? "Several news, blog, tag, pagination, or archive pages have the same lower-priority cleanup issue." : "Several pages have metadata cleanup opportunities, but metadata is not the first bottleneck for this page type.",
      why_it_matters: shouldGroupSupport ? "These pages can support search visibility, but they should not crowd out calculator, comparison, quote, product, booking, or main landing pages." : shouldGroupLowValue ? "These pages matter less than the pages that drive leads, sales, bookings, or quote requests. Grouping keeps FixList focused on business impact first." : "Fix structural, schema, trust, crawl, route, or conversion-page issues first, then polish titles and descriptions as a batch.",
      recommended_value: shouldGroupSupport ? "Fix one guide/Q&A pattern, then apply the same rule across the affected pages." : shouldGroupLowValue ? "Review these pages later as a batch, after important business pages are fixed." : "Keep these metadata changes as a later batch unless the page is a true money page.",
      ai_recommendation: shouldGroupSupport ? "Fix one guide/Q&A pattern, then apply the same rule across the affected pages." : shouldGroupLowValue ? "Review these pages later as a batch, after important business pages are fixed." : "Keep these metadata changes as a later batch unless the page is a true money page.",
      priority: shouldGroupSupport ? "medium" : "low",
      difficulty: "easy",
      business_importance: shouldGroupSupport ? "support_content_group" : shouldGroupLowValue ? "low_value_group" : "deferred_metadata_group",
      primary_defect_class: shouldGroupBlockedMeta ? "metadata_deferred" : fix.primary_defect_class,
      meta_rewrite_allowed: false,
      meta_regeneration_gate: shouldGroupBlockedMeta ? "blocked_grouped_for_later" : fix.meta_regeneration_gate,
      affected_pages: [],
      page_value_score: shouldGroupSupport ? 45 : shouldGroupLowValue ? 10 : 30,
      page_value_label: shouldGroupSupport ? "Grouped guide/Q&A content pages" : shouldGroupLowValue ? "Grouped lower-priority archive pages" : "Grouped deferred metadata pages",
      evidence_confidence: 90,
      site_fit_score: shouldGroupSupport ? 55 : shouldGroupLowValue ? 20 : 30,
      business_impact_score: shouldGroupSupport ? 45 : shouldGroupLowValue ? 15 : 25,
      reach_score: 60,
      overall_priority_score: shouldGroupSupport ? 58 : shouldGroupLowValue ? 25 : 32,
      what_to_do: ["Fix important business pages first.", "Pick one affected page as the example.", "Apply the same template or batch rule to the rest.", "Run FixList again after publishing."],
      what_to_do_steps: ["Fix important business pages first.", "Pick one affected page as the example.", "Apply the same template or batch rule to the rest.", "Run FixList again after publishing."],
    };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...normalizeAffectedPages(fix, fix.page_url || "/")])).slice(0, 120);
    existing.page_count = existing.affected_pages.length;
    existing.reach_score = scoreReach(existing);
    groups.set(key, existing);
  }
  return [...keep, ...groups.values()];
}

/* -------------------------------------------------------------------------- */
/* Normalization and page classification                                        */
/* -------------------------------------------------------------------------- */

function normalizeFix(fix, index) {
  const rawCategory = String(fix?.category || fix?.type || "web_dev");
  const category = CATEGORY_MAP[rawCategory] || rawCategory || "web_dev";
  const pageUrl = cleanPath(fix?.page_url || fix?.url || fix?.affected_pages?.[0] || "/") || "/";
  const affectedPages = normalizeAffectedPages(fix, pageUrl);
  const status = normalizeStatus(fix?.status || (fix?.requires_developer ? "needs_developer" : fix?.requires_approval ? "needs_approval" : fix?.can_auto_fix ? "auto_fixed" : "needs_approval"));
  const difficulty = normalizeDifficulty(fix?.difficulty, status);
  const title = cleanString(fix?.issue_title || fix?.title || fix?.headline || defaultTitle(category)) || defaultTitle(category);
  const explanation = cleanString(fix?.plain_english_explanation || fix?.plain_english_summary || fix?.explanation || fix?.summary || fix?.description) || "This recommendation was found during the website scan.";
  const why = cleanString(fix?.why_it_matters || fix?.why || fix?.reason) || "Improving this can help visitors and search engines understand the website more clearly.";
  const recommendedValue = stringifyValue(fix?.recommended_value || fix?.recommendation || fix?.suggested_fix || fix?.ai_recommendation || fix?.recommended_action) || "Review this recommendation.";
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
    who_can_do_this: fix?.who_can_do_this === "you" || fix?.who_can_do_this === "your_web_person" ? fix.who_can_do_this : defaultOwner(difficulty),
    estimated_time: cleanString(fix?.estimated_time || fix?.time_estimate) || defaultTime(difficulty),
    time_estimate: cleanString(fix?.time_estimate || fix?.estimated_time) || defaultTime(difficulty),
    source: fix?.source || "scanner",
  };
}

function getTemplateFamily(url) {
  const path = cleanPath(url).toLowerCase();
  if (isLowValuePage(path)) return "archive";
  if (isInternalAppRoute(path)) return "internal_app";
  if (path.includes("questions-reponses") || path.includes("faq")) return "qa";
  if (path.includes("/loi-") || path.includes("/legal") || path.includes("privacy") || path.includes("terms")) return "legal_info";
  if (path.includes("/le-guide") || path.includes("/guide")) return "guide";
  if (hasAny(path, ["simulation", "simulateur", "calcul", "comparateur", "devis", "quote", "pricing", "demo"])) return "conversion";
  if (hasAny(path, ["/collections/", "/category/", "/categorie/", "/c/", "/listing", "/show", "/pass", "/ticket"])) return "category_listing";
  if (hasAny(path, ["/products/", "/product/", "/produit/", "/p/"])) return "product_detail";
  if (path.includes("contact")) return "contact";
  return "standard";
}

function classifyPageType(url, pageValue, siteFingerprint, fix) {
  const path = cleanPath(url).toLowerCase();
  const family = getTemplateFamily(path);
  const value = `${path} ${fix?.category || ""} ${fix?.rule || ""} ${fix?.issue_title || ""}`.toLowerCase();
  if (path === "/" || path.endsWith("/index.html")) return "landing_page";
  if (family === "internal_app") return "internal_auth_or_app_route";
  if (family === "conversion") return "comparison_tool_or_calculator";
  if (family === "category_listing") return "category_or_listing";
  if (family === "product_detail") return "product_detail";
  if (family === "contact") return "contact_or_lead_page";
  if (family === "archive") return "article_or_archive";
  if (["guide", "qa", "legal_info"].includes(family)) return "support_guide_or_qa";
  if (hasAny(value, ["booking", "reservation", "checkout", "cart", "panier"])) return "booking_or_checkout_flow";
  if (hasAny(value, ["agency", "agence", "location", "adresse", "map", "localbusiness"])) return "location_page";
  if (pageValue.classification === "money_page") return "landing_page";
  if (siteFingerprint.vertical === "ecommerce" && hasAny(path, ["shop", "boutique", "collection"])) return "category_or_listing";
  return "standard_page";
}

function classifyDefectClass(fix, pageType, pageValue, siteFingerprint) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""} ${fix?.current_value || ""}`.toLowerCase();
  if (isImageAltIssue(fix)) return "image_accessibility";
  if (matchesAnyRule(value, new Set(["internal_route_indexable", "duplicate_route_casing", "blocked_by_robots", "noindex", "indexability", "faceted_url", "pagination"]))) return "crawl_index";
  if (matchesAnyRule(value, STRUCTURAL_RULES) || isSevereIssue(fix)) return "structural";
  if (matchesAnyRule(value, SEMANTIC_RULES)) return "semantic_schema";
  if (matchesAnyRule(value, CONTENT_TRUST_RULES) || (siteFingerprint.regulatory_sensitivity === "regulated" && pageValue.classification === "money_page" && hasAny(value, ["trust", "author", "review", "method", "thin", "privacy", "terms"]))) return "content_trust";
  if (isMetadataIssue(fix)) return "metadata";
  if (["category_or_listing", "booking_or_checkout_flow"].includes(pageType) && hasAny(value, ["duplicate", "pagination", "filter", "facet"])) return "crawl_index";
  return "content_or_template";
}

function shouldAllowMetaRewrite({ fix, pageType, pageValue, defectClass }) {
  if (!isMetadataIssue(fix)) return false;
  if (isImageAltIssue(fix)) return false;
  if (["structural", "crawl_index", "semantic_schema", "content_trust", "security_trust", "image_accessibility"].includes(defectClass)) return false;
  if (pageValue.classification === "low_value" || pageValue.classification === "internal_or_auth_route") return false;
  if (["article_or_archive", "support_guide_or_qa", "internal_auth_or_app_route"].includes(pageType)) return false;
  if (["comparison_tool_or_calculator", "contact_or_lead_page", "landing_page", "product_detail", "category_or_listing", "location_page"].includes(pageType)) return true;
  return pageValue.classification === "money_page";
}

function isMetadataIssue(fix) {
  if (isImageAltIssue(fix)) return false;
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""}`.toLowerCase();
  return hasAny(value, ["meta", "title", "description", "duplicate_search", "duplicate title", "duplicate description", "search field"]);
}

function isImageAltIssue(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""} ${fix?.current_value || ""}`.toLowerCase();
  return hasAny(value, ["image_alt_text", "image alt", "alt text", "missing alt", "image description", "missing image descriptions"]);
}

function isCosmeticIssue(fix) {
  if (isImageAltIssue(fix)) return true;
  const value = `${fix?.rule || ""} ${fix?.category || ""}`.toLowerCase();
  for (const rule of METADATA_RULES) if (value.includes(rule) || value.includes(rule.replace(/_/g, " "))) return true;
  if (value.includes("thin_content")) return true;
  return false;
}

function isSevereIssue(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.current_value || ""} ${fix?.issue_title || ""}`.toLowerCase();
  for (const rule of SEVERE_RULES) if (value.includes(rule) || value.includes(rule.replace(/_/g, " "))) return true;
  return ["404", "410", "429", "500", "503", "blocked", "forbidden", "timeout"].some((code) => value.includes(code));
}

function isRepeatedSevereCandidate(fix) {
  const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.current_value || ""} ${fix?.issue_title || ""}`.toLowerCase();
  return isSevereIssue(fix) && hasAny(value, ["404", "410", "429", "500", "503", "blocked", "not loading", "failed", "forbidden", "timeout"]);
}

/* -------------------------------------------------------------------------- */
/* Plan building                                                               */
/* -------------------------------------------------------------------------- */

function buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint }) {
  const score = typeof body?.health_score === "number" ? body.health_score : typeof body?.scan_summary?.score === "number" ? body.scan_summary.score : calculateFallbackScore(canonicalFixes);
  const positiveFindings = buildPositiveFindings({ pages, siteFingerprint });
  const topRecommendedActions = buildTopActions(canonicalFixes);
  const healthReport = buildFallbackHealthReport({ body, pages, fixes: canonicalFixes, score, positiveFindings, siteFingerprint });
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
    ignored_low_value_pages: canonicalFixes.filter((fix) => String(fix.business_importance || "").includes("low_value")).slice(0, 10),
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
  const routeBoundaryText = siteFingerprint?.route_boundary_risk === "high" ? " FixList also found a high route-boundary risk, meaning internal/app pages may be exposed to crawlers." : "";
  const topConcerns = safeFixes.slice(0, 4).map((fix) => ({ title: fix.issue_title, plain_english_explanation: fix.plain_english_explanation, why_it_matters: fix.why_it_matters, affected_area: Array.isArray(fix.affected_pages) && fix.affected_pages.length > 1 ? `${fix.affected_pages.length} pages` : fix.affected_pages?.[0] || "Website" }));
  const quickWins = safeFixes.filter((fix) => fix.difficulty !== "developer").slice(0, 4).map((fix) => ({ title: fix.issue_title, action: Array.isArray(fix.what_to_do) && fix.what_to_do.length > 0 ? fix.what_to_do[0] : "Review and update this item.", expected_benefit: fix.why_it_matters }));
  const biggerProjects = safeFixes.filter((fix) => fix.difficulty === "developer").slice(0, 4).map((fix) => ({ title: fix.issue_title, who_should_handle: "Your web person", why: fix.why_it_matters }));
  const limitations = [];
  if (Array.isArray(body?.crawl_warnings)) limitations.push(...body.crawl_warnings.slice(0, 3));
  if (siteFingerprint?.vertical_confidence < 0.55) limitations.push("The site type was not fully clear, so FixList used a conservative priority model.");
  return {
    health_score: score,
    health_grade: grade,
    overall_explanation: [
      `Your website health is ${grade.toLowerCase()} with a score of ${score}/100.`,
      `FixList recognized this as ${verticalLabel} and prioritized pages that are most likely to drive leads, sales, bookings, quotes, trust, or safe indexation.`,
      safePages.length > 0 ? `The scanner reviewed ${safePages.length} pages.` : "",
      highPriorityCount > 0 ? `There ${highPriorityCount === 1 ? "is" : "are"} ${highPriorityCount} high-priority item${highPriorityCount === 1 ? "" : "s"} to look at first.` : "There are no major emergency issues from this scan, but there are still useful improvements to make.",
      routeBoundaryText,
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
  const websiteHealthReport = plan.website_health_report || buildFallbackHealthReport({ body: plan, pages, fixes: cleanedFixes, score, positiveFindings: plan.positive_findings || [], siteFingerprint: plan.site_fingerprint || {} });
  const topRecommendedActions = Array.isArray(plan.top_recommended_actions) && plan.top_recommended_actions.length > 0 ? fillTopActions(plan.top_recommended_actions, cleanedFixes) : buildTopActions(cleanedFixes);
  const recommendedActions = Array.isArray(plan.recommended_actions) && plan.recommended_actions.length > 0 ? plan.recommended_actions : topRecommendedActions.map((action) => {
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
      pages_failed: pages.filter((page) => { const status = Number(page?.status_code || 0); return status >= 400 || status === 0 || page?.fetch_error; }).length,
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
  for (const rewrite of aiResponse?.fix_rewrites || []) if (rewrite?.fix_id && validIds.has(rewrite.fix_id)) rewrites.set(rewrite.fix_id, rewrite);
  const cleanedFixes = canonicalFixes.map((fix) => {
    const rewrite = rewrites.get(fix.id);
    if (!rewrite) return fix;
    const steps = Array.isArray(rewrite.what_to_do) && rewrite.what_to_do.length > 0 ? rewrite.what_to_do.slice(0, 5).map((step) => String(step).trim()).filter(Boolean) : fix.what_to_do;
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
      who_can_do_this: rewrite.who_can_do_this === "you" || rewrite.who_can_do_this === "your_web_person" ? rewrite.who_can_do_this : fix.who_can_do_this,
      estimated_time: cleanString(rewrite.estimated_time) || fix.estimated_time,
      time_estimate: cleanString(rewrite.estimated_time) || fix.time_estimate,
      ai_recommendation: steps.length > 0 ? steps.join(" ") : fix.ai_recommendation,
    };
  }).sort(compareFixes);
  const aiTopActions = Array.isArray(aiResponse?.top_recommended_actions) ? aiResponse.top_recommended_actions.map((action) => hydrateTopAction(action, cleanedFixes)).filter((action) => action.title) : [];
  const topRecommendedActions = fillTopActions(aiTopActions, cleanedFixes);
  const positives = Array.isArray(aiResponse?.positive_findings) && aiResponse.positive_findings.length > 0 ? aiResponse.positive_findings.slice(0, 5).map((item) => String(item)) : fallbackPlan.positive_findings;
  const healthReport = normalizeAiHealthReport({ aiReport: aiResponse?.website_health_report, fallbackReport: fallbackPlan.website_health_report, score: fallbackPlan.health_score, fixes: cleanedFixes, pages, body, positives, siteFingerprint });
  return makeFrontendCompatible({ ...fallbackPlan, plain_english_summary: cleanString(aiResponse?.plain_english_summary) || healthReport.overall_explanation || fallbackPlan.plain_english_summary, website_health_report: healthReport, health_explanation: healthReport.overall_explanation, customer_summary: healthReport.overall_explanation, top_recommended_actions: topRecommendedActions, cleaned_fixes: cleanedFixes, raw_fixes: cleanedFixes, fixes: cleanedFixes, findings: cleanedFixes, recommendations: cleanedFixes, competitor_insights: [], positive_findings: positives, ai_rewrites_applied: rewrites.size, crawled_pages: pages, pages, site_fingerprint: siteFingerprint });
}

function buildTopActions(fixes) {
  return fillTopActions([], fixes);
}

function fillTopActions(actions, fixes) {
  const output = [];
  const seen = new Set();
  for (const action of actions || []) {
    const id = action.fix_id || action.id || action.title;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    output.push(action);
  }
  for (const fix of fixes || []) {
    const id = fix.fix_id || fix.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    output.push(fixToAction(fix));
    if (output.length >= 5) break;
  }
  return output.slice(0, 5);
}

function hydrateTopAction(action, fixes) {
  const fix = fixes.find((item) => item.id === action?.fix_id || item.fix_id === action?.fix_id);
  if (!fix) return { fix_id: action?.fix_id || "", title: cleanString(action?.title) || "Recommended action", reason: cleanString(action?.reason) || "Review this recommendation.", priority: ["high", "medium", "low"].includes(action?.priority) ? action.priority : "medium", affected_pages: [], what_to_do_steps: [], who_can_do_this: "You", time_estimate: "" };
  return { ...fixToAction(fix), title: cleanString(action?.title) || fix.issue_title, reason: cleanString(action?.reason) || fix.why_it_matters, plain_english_summary: fix.plain_english_explanation, why_it_matters: cleanString(action?.reason) || fix.why_it_matters, priority: ["high", "medium", "low"].includes(action?.priority) ? action.priority : fix.priority === "critical" || fix.priority === "high" ? "high" : fix.priority === "low" ? "low" : "medium" };
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
  return `You are the AI planning layer for FixList.

The deterministic scanner already found evidence. Rewrite and explain recommendations in plain English, while preserving exact fix_id values.

Core instruction: Create a site-aware SEO plan. Do not treat every SEO issue equally. Prioritize by evidence confidence, site-fit, business impact, affected-page reach, route intent, and whether the page should actually be indexable.

Hard rules:
1. Do not invent findings, URLs, rankings, traffic, leads, revenue, or fixes.
2. Do not say anything has already been fixed or published.
3. Only rewrite findings using exact fix_id values provided.
4. what_to_do must contain 2 to 5 short action steps.
5. who_can_do_this must be either "you" or "your_web_person".
6. Use plain English for a non-technical business owner.
7. Focus top actions on pages that drive leads, sales, bookings, quotes, product discovery, trust, or safe indexation.
8. News, blog, tag, feed, pagination, and old archive pages must not dominate top priorities.
9. Internal/auth/app routes such as admin, billing, login, reset-password, dashboard, reports, and developer pages should usually be private or noindex. Prioritize route-boundary issues above metadata polishing.
10. Duplicate route casing such as /Dashboard vs /dashboard is a canonical/indexation issue, not a cosmetic issue.
11. A technically crawlable page is not automatically strategically useful to index.
12. Metadata rewriting is gated. Only recommend title/meta-description rewrites when metadata is the primary gap for that page type.
13. Image alt text is not metadata. Treat it as accessibility/image context, not as page title/description cleanup.
14. Group repeated blocked, 404, 410, 429, 500, or template failures. Do not create dozens of identical product/page tasks.
15. For regulated, finance, insurance, health, SaaS, or trust-sensitive sites, prioritize trust pages, clarity, route boundaries, indexability, canonicalization, and key conversion pages.
16. Always return up to 5 top_recommended_actions when enough findings exist.

Site fingerprint:
${JSON.stringify(siteFingerprint, null, 2)}

Business:
${JSON.stringify({ business_name: body?.business_name || "", business_type: body?.business_type || "", city: body?.city || "", country: body?.country || "", language: body?.language || "", website_url: websiteUrl, scan_mode: body?.scan_mode || "", important_keywords: body?.important_keywords || [], business_priority_instruction: body?.business_priority_instruction || null }, null, 2)}

Scan totals:
${JSON.stringify({ pages_scanned: Array.isArray(pages) ? pages.length : 0, health_score: fallbackPlan.health_score, pages_found: body?.pages_found || 0, pages_crawled: body?.pages_crawled || 0, queued_remaining: body?.queued_remaining || 0, crawl_scope: body?.crawl_scope || null }, null, 2)}

Technical audit summary:
${JSON.stringify(body?.technical_audit_summary || null, null, 2)}

Prioritized scanner findings with evidence, page-type, defect-class, route intent, and meta-gate scores:
${JSON.stringify(canonicalFixes.map(compactFixForPrompt), null, 2)}

Representative page profile:
${JSON.stringify(buildPageProfile(pages), null, 2)}

Fallback website health report:
${JSON.stringify(fallbackPlan.website_health_report || {}, null, 2)}

Return valid JSON only.`;
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
          top_concerns: { type: "array", items: { type: "object", properties: { title: { type: "string" }, plain_english_explanation: { type: "string" }, why_it_matters: { type: "string" }, affected_area: { type: "string" } }, required: ["title", "plain_english_explanation"] } },
          quick_wins: { type: "array", items: { type: "object", properties: { title: { type: "string" }, action: { type: "string" }, expected_benefit: { type: "string" } }, required: ["title", "action"] } },
          bigger_projects: { type: "array", items: { type: "object", properties: { title: { type: "string" }, who_should_handle: { type: "string" }, why: { type: "string" } }, required: ["title", "who_should_handle"] } },
          competitor_takeaways: { type: "array", items: { type: "string" } },
          limitations: { type: "array", items: { type: "string" } },
          next_best_step: { type: "string" },
        },
        required: ["health_score", "health_grade", "overall_explanation", "what_is_working", "top_concerns", "quick_wins", "bigger_projects", "competitor_takeaways", "limitations", "next_best_step"],
      },
      top_recommended_actions: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, title: { type: "string" }, reason: { type: "string" }, priority: { type: "string", enum: ["high", "medium", "low"] } }, required: ["title", "reason", "priority"] } },
      fix_rewrites: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, issue_title: { type: "string" }, plain_english_explanation: { type: "string" }, why_it_matters: { type: "string" }, what_to_do: { type: "array", items: { type: "string" } }, who_can_do_this: { type: "string", enum: ["you", "your_web_person"] }, estimated_time: { type: "string" } }, required: ["fix_id", "issue_title", "plain_english_explanation", "why_it_matters", "what_to_do", "who_can_do_this", "estimated_time"] } },
      competitor_insights: { type: "array", items: { type: "object", properties: {} } },
      positive_findings: { type: "array", items: { type: "string" } },
    },
    required: ["plain_english_summary", "website_health_report", "top_recommended_actions", "fix_rewrites", "competitor_insights", "positive_findings"],
  };
}

/* -------------------------------------------------------------------------- */
/* Output helpers                                                              */
/* -------------------------------------------------------------------------- */

function compactFixForPrompt(fix) {
  return { fix_id: fix.fix_id || fix.id, rule: fix.rule, category: fix.category, title: fix.issue_title, priority: fix.priority, page_url: fix.page_url, affected_pages: fix.affected_pages?.slice(0, 8) || [], why_it_matters: fix.why_it_matters, recommended_value: fix.recommended_value, page_type: fix.page_type, page_template_family: fix.page_template_family, primary_defect_class: fix.primary_defect_class, meta_rewrite_allowed: fix.meta_rewrite_allowed, meta_regeneration_gate: fix.meta_regeneration_gate, page_value_score: fix.page_value_score, page_value_label: fix.page_value_label, business_importance: fix.business_importance, evidence_confidence: fix.evidence_confidence, site_fit_score: fix.site_fit_score, business_impact_score: fix.business_impact_score, reach_score: fix.reach_score, overall_priority_score: fix.overall_priority_score };
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
    page_template_family: page?.page_template_family || "",
    estimated_page_intent: page?.estimated_page_intent || "",
  }));
}

function buildPositiveFindings({ pages, siteFingerprint }) {
  const positives = [];
  if (Array.isArray(pages) && pages.length > 0) positives.push(`The scan reviewed ${pages.length} representative pages.`);
  if (siteFingerprint?.vertical && siteFingerprint.vertical !== "general") positives.push(`FixList identified the site as ${siteFingerprint.vertical_label}.`);
  if (siteFingerprint?.likely_money_page_patterns?.length > 0) positives.push("The review can prioritize likely money pages over low-value archives.");
  if (siteFingerprint?.route_boundary_risk === "low") positives.push("The scan did not find an obvious high-risk internal route exposure pattern.");
  return positives.slice(0, 5);
}

function buildGroupedPageRecommendations(fixes) {
  return (fixes || []).filter((fix) => String(fix.business_importance || "").includes("group") || (Array.isArray(fix.affected_pages) && fix.affected_pages.length > 3)).slice(0, 10).map((fix) => ({ title: fix.issue_title, priority: fix.priority, affected_pages: fix.affected_pages || [], page_count: fix.affected_pages?.length || 0, recommendation: fix.recommended_value }));
}

function fixToAction(fix) {
  return { fix_id: fix.fix_id || fix.id, title: fix.issue_title, reason: fix.why_it_matters, priority: fix.priority === "critical" || fix.priority === "high" ? "high" : fix.priority === "low" ? "low" : "medium", plain_english_summary: fix.plain_english_explanation, why_it_matters: fix.why_it_matters, what_to_do_steps: fix.what_to_do_steps || fix.what_to_do || [], who_can_do_this: fix.who_can_do_this === "your_web_person" ? "Your web person" : "You", time_estimate: fix.time_estimate || fix.estimated_time || "", affected_pages: fix.affected_pages || [], page_url: fix.page_url || "" };
}

function normalizeHealthCards(value, fallback, limit) {
  if (!Array.isArray(value) || value.length === 0) return fallback || [];
  return value.slice(0, limit).map((item) => typeof item === "string" ? { title: item, plain_english_explanation: "", why_it_matters: "" } : { title: cleanString(item?.title) || cleanString(item?.headline) || "", plain_english_explanation: cleanString(item?.plain_english_explanation) || cleanString(item?.explanation) || cleanString(item?.action) || "", why_it_matters: cleanString(item?.why_it_matters) || cleanString(item?.why) || cleanString(item?.expected_benefit) || "", affected_area: cleanString(item?.affected_area) || cleanString(item?.who_should_handle) || "" }).filter((item) => item.title);
}

function cleanStringArray(value, limit) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, limit).map((item) => cleanString(item)).filter(Boolean);
}

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value;
  return [];
}

function normalizeAffectedPages(fix, fallbackPage) {
  const rawPages = Array.isArray(fix?.affected_pages) ? fix.affected_pages : Array.isArray(fix?.pages) ? fix.pages : fix?.page_url ? [fix.page_url] : [fallbackPage];
  return Array.from(new Set(rawPages.map((item) => cleanPath(item)).filter(Boolean))).slice(0, 150);
}

function normalizeSteps(fix) {
  for (const value of [fix?.what_to_do, fix?.what_to_do_steps, fix?.fix_steps, fix?.steps]) {
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

function defaultTitle(category) {
  const titles = { "404_error": "Fix pages that are not loading", duplicate_content: "Review duplicate or repeated pages", meta_description: "Improve search descriptions", meta_title: "Improve search titles", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", web_dev: "Review website setup", mobile_setup: "Review mobile setup", performance_hint: "Review page speed", social_metadata: "Review social sharing details", indexability: "Review indexability settings", image_alt_text: "Add useful image descriptions" };
  return titles[category] || "Review this recommendation";
}

function friendlyCategory(category) {
  const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" };
  return map[category] || "Website improvement";
}

function defaultSteps({ category, difficulty, recommendedValue }) {
  if (difficulty === "developer") return ["Send this item to your web person.", "Ask them to review the affected URL or template.", "Apply the safest fix and publish it.", "Run FixList again to confirm it is resolved."];
  if (["meta_title", "meta_description", "duplicate_content"].includes(category)) return ["Open the affected page in your website editor.", recommendedValue, "Save and publish the change.", "Run FixList again after publishing."];
  if (category === "image_alt_text") return ["Open the affected page or image library.", "Add short, specific alt text to meaningful images.", "Leave decorative images empty if they do not add meaning.", "Save and rescan after publishing."];
  return ["Review the affected page.", recommendedValue, "Check the page again after publishing."];
}

function defaultOwner(difficulty) { return difficulty === "developer" ? "your_web_person" : "you"; }
function defaultTime(difficulty) { return difficulty === "developer" ? "about 1–2 hours" : difficulty === "easy" ? "about 10–15 minutes" : "about 30–60 minutes"; }
function normalizeStatus(value) { const status = String(value || "").toLowerCase(); return ["needs_approval", "auto_fixed", "needs_developer", "open"].includes(status) ? status : "needs_approval"; }
function normalizeDifficulty(value, status) { const difficulty = String(value || "").toLowerCase(); if (["easy", "moderate", "developer"].includes(difficulty)) return difficulty; return status === "needs_developer" ? "developer" : "moderate"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); return ["critical", "high", "medium", "low"].includes(priority) ? priority : "medium"; }
function calculateFallbackScore(fixes) { const safeFixes = Array.isArray(fixes) ? fixes : []; const penalty = safeFixes.reduce((total, fix) => total + (fix.priority === "critical" ? 15 : fix.priority === "high" ? 10 : fix.priority === "medium" ? 5 : 2), 0); return Math.max(20, Math.min(95, 92 - penalty)); }
function scoreToGrade(score) { if (score >= 90) return "Excellent"; if (score >= 75) return "Good"; if (score >= 55) return "Fair"; return "Needs work"; }

function isLowValuePage(url) {
  const path = cleanPath(url).toLowerCase();
  if (/\/(20\d{2})([-/](janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december))?(\/|$)/i.test(path)) return true;
  if (/\/(20\d{2})[-/]?\d{1,2}(\/|$)/i.test(path)) return true;
  if (LOW_VALUE_SEGMENT_PATTERNS.some((pattern) => path.includes(pattern))) return true;
  return LOW_VALUE_QUERY_PATTERNS.some((pattern) => path.includes(pattern));
}

function isInternalAppRoute(url) {
  const path = cleanPath(url).toLowerCase().replace(/\/$/, "");
  return INTERNAL_ROUTE_PATTERNS.some((pattern) => path === pattern || path.startsWith(`${pattern}/`));
}

function pageIsIndexable(page) {
  const robots = String(page?.robots || page?.robots_meta || "").toLowerCase();
  return page?.indexable !== false && !robots.includes("noindex") && Number(page?.status_code || 200) < 400;
}

function findDuplicateCasingRoutes(pages) {
  const buckets = new Map();
  for (const page of pages || []) {
    const path = cleanPath(page?.url || page?.final_url || "");
    if (!path) continue;
    const lower = path.toLowerCase();
    const existing = buckets.get(lower) || new Set();
    existing.add(path);
    buckets.set(lower, existing);
  }
  const output = [];
  for (const variants of buckets.values()) if (variants.size > 1) output.push(...variants);
  return Array.from(new Set(output));
}

function findRepeatedSnapshotGroups(pages) {
  const buckets = new Map();
  for (const page of pages || []) {
    const path = cleanPath(page?.url || page?.final_url || "");
    if (!path || isInternalAppRoute(path)) continue;
    const title = normalizeSnapshotText(page?.title || page?.h1 || page?.meta_description || "");
    const description = normalizeSnapshotText(page?.meta_description || page?.description || "");
    const key = `${title}|${description}`;
    if (key.length < 18) continue;
    const existing = buckets.get(key) || [];
    existing.push(path);
    buckets.set(key, existing);
  }
  for (const pagesForKey of buckets.values()) if (pagesForKey.length >= 4) return pagesForKey;
  return [];
}

function normalizeSnapshotText(value) { return String(value || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 140); }
function matchesAnyRule(value, rules) { const haystack = String(value || "").toLowerCase(); for (const rule of rules || []) { const raw = String(rule || "").toLowerCase(); if (haystack.includes(raw) || haystack.includes(raw.replace(/_/g, " "))) return true; } return false; }
function isTrustOrEntityIssue(fix) { const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""}`.toLowerCase(); return hasAny(value, ["trust", "schema", "organization", "localbusiness", "legal", "review", "address", "phone", "contact", "entity", "privacy", "terms", "security"]); }
function archiveGroupTitle(fix) { const value = `${fix?.rule || ""} ${fix?.category || ""}`.toLowerCase(); if (value.includes("description")) return "Batch low-priority archive descriptions"; if (value.includes("title")) return "Batch low-priority archive titles"; if (value.includes("duplicate")) return "Batch low-priority duplicate archive fields"; if (value.includes("alt")) return "Batch low-priority archive image alt text"; return "Batch low-priority archive cleanup"; }
function supportGroupTitle(fix, family) { const value = `${fix?.rule || ""} ${fix?.category || ""}`.toLowerCase(); const label = family === "qa" ? "Q&A" : family === "legal_info" ? "legal/guide" : "guide"; if (value.includes("description")) return `Batch ${label} page descriptions`; if (value.includes("title")) return `Batch ${label} page titles`; if (value.includes("duplicate")) return `Batch duplicate ${label} search fields`; if (value.includes("alt")) return `Batch ${label} image alt text`; return `Batch ${label} page cleanup`; }
function deferredMetaGroupTitle(fix, family) { const value = `${fix?.rule || ""} ${fix?.category || ""}`.toLowerCase(); const label = String(family || "page").replace(/_/g, " "); if (value.includes("description")) return `Defer ${label} meta descriptions`; if (value.includes("title")) return `Defer ${label} search titles`; if (value.includes("duplicate")) return `Defer duplicate ${label} search fields`; return `Defer ${label} metadata cleanup`; }
function repeatedSevereTitle(fix, family) { const value = `${fix?.rule || ""} ${fix?.current_value || ""} ${fix?.issue_title || ""}`.toLowerCase(); if (value.includes("429")) return `Group blocked/rate-limited ${family} pages`; if (value.includes("404") || value.includes("410")) return `Group missing ${family} pages`; if (value.includes("500") || value.includes("503")) return `Group server errors on ${family} pages`; return `Group repeated page loading problems`; }
function statusBucket(fix) { const value = `${fix?.current_value || ""} ${fix?.issue_title || ""}`.toLowerCase(); for (const code of ["429", "404", "410", "500", "503"]) if (value.includes(code)) return code; if (value.includes("blocked")) return "blocked"; return "failed"; }
function hasAny(text, values) { const haystack = String(text || "").toLowerCase(); return values.some((value) => haystack.includes(String(value).toLowerCase())); }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { if (/^https?:\/\//i.test(raw)) return new URL(raw).pathname || "/"; } catch {} return raw.startsWith("/") ? raw : `/${raw}`; }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function stringifyValue(value) { if (typeof value === "string") return value.trim(); if (value == null) return ""; try { return JSON.stringify(value).slice(0, 700); } catch { return String(value); } }
function clampText(value, max) { const text = String(value || "").trim(); return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
async function withTimeout(promise, timeoutMs, label) { return await Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs))]); }
