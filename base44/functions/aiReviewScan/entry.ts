import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") || "";
const GEMINI_MODEL = Deno.env.get("GEMINI_MODEL") || "gemini-3.1-flash-lite";
const GEMINI_BASE_URL = Deno.env.get("GEMINI_BASE_URL") || "https://generativelanguage.googleapis.com/v1beta/models";
const GEMINI_AI_TIMEOUT_MS = Number(Deno.env.get("GEMINI_AI_TIMEOUT_MS") || 60000);
const BASE44_AI_TIMEOUT_MS = Number(Deno.env.get("BASE44_AI_TIMEOUT_MS") || 25000);
const AI_PROVIDER_ORDER = Deno.env.get("AI_PROVIDER_ORDER") || "gemini_first";
const MAX_AI_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 36);
const MAX_PROMPT_PAGES = Number(Deno.env.get("MAX_PROMPT_PAGES") || 40);
const SCORING_MODEL = "fixlist_archetype_playbooks_v1_blocked_access_groups";

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
  blocked_page: "web_dev",
  blocked_page_429: "web_dev",
  scanner_blocked: "web_dev",
};

const LOW_VALUE_PATTERNS = ["/actualites/", "/news/", "/blog/", "/archive/", "/archives/", "/tag/", "/tags/", "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag="];
const INTERNAL_ROUTE_PATTERNS = ["/admin", "/developer", "/assistant", "/billing", "/login", "/register", "/forgot-password", "/reset-password", "/dashboard", "/issues", "/reports", "/crawl-status", "/metadata", "/canonicals", "/redirects", "/js-rendering", "/competitors", "/account", "/my-account", "/cart", "/checkout"];
const TRUST_PAGE_PATTERNS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv", "/conditions"];
const STRUCTURAL_RULES = new Set(["broken_page", "404_error", "410_error", "server_error", "blocked_page", "blocked_page_429", "scanner_blocked", "rate_limited_page", "commerce_product_access_blocked", "redirect_loop", "canonical_missing", "canonical_to_other_domain", "canonical_to_other_url", "mobile_setup", "performance_hint", "js_rendering", "client_rendering", "internal_link", "duplicate_route_casing", "free_base44_subdomain", "route_boundary_candidate_indexable", "internal_route_indexable"]);
const SEMANTIC_RULES = new Set(["schema", "structured_data", "product_schema", "localbusiness_schema", "breadcrumb_schema", "social_metadata"]);
const CONTENT_TRUST_RULES = new Set(["trust_signal_gap", "missing_trust_pages", "faq_gap", "cta_gap", "thin_content", "thin_repetitive_public_snapshots", "author", "reviewer", "methodology", "content_quality"]);
const METADATA_RULES = new Set(["missing_meta_description", "long_meta_description", "short_meta_description", "missing_title", "long_title", "short_title", "duplicate_title", "duplicate_meta_description", "duplicate_content"]);

const ARCHETYPE_PLAYBOOKS = {
  finance_insurance_lead_gen: {
    label: "finance / insurance / lead generation",
    keywords: ["assurance", "insurance", "pret", "prêt", "credit", "crédit", "loan", "mortgage", "finance", "banque", "bank", "taux", "emprunteur", "mutuelle", "devis", "simulation", "comparateur", "compare", "courtier", "broker"],
    moneyPatterns: ["/devis", "/quote", "/simulation", "/simulateur", "/calcul", "/calculator", "/comparateur", "/compare", "/tarif", "/contact", "/souscription", "/assurance", "/credit", "/pret"],
    priorityPages: ["quote forms", "calculators and simulators", "comparison pages", "eligibility/application pages", "contact/agency pages", "legal/trust pages", "methodology/review pages"],
    priorityIssues: ["indexability", "canonicalization", "trust pages", "schema", "route boundaries", "broken lead paths", "thin or repeated calculator/comparison content"],
    demote: ["old news", "tag archives", "blog pagination", "generic metadata on low-value articles"],
    ownerRule: "Trust, indexability, canonical, schema, route-boundary, and form/lead-flow issues often need your_web_person. Simple copy edits can be you.",
  },
  utilities_comparison_lead_gen: {
    label: "utilities / energy comparison lead generation",
    keywords: ["energie", "énergie", "electricite", "électricité", "gaz", "fournisseur", "edf", "engie", "kwh", "tarif réglementé", "compteur", "comparateur", "devis", "simulation", "contrat"],
    moneyPatterns: ["/energie", "/énergie", "/electricite", "/électricité", "/gaz", "/comparateur", "/simulation", "/simulateur", "/devis", "/tarif", "/fournisseur", "/contrat", "/souscription"],
    priorityPages: ["energy comparison pages", "supplier pages", "tariff pages", "simulators", "quote/subscription flows", "legal/trust pages", "methodology pages"],
    priorityIssues: ["crawl/index coverage", "canonicalization", "structured data", "trust/legal clarity", "form and comparison flow reliability", "thin supplier/tariff pages"],
    demote: ["old tariff news", "tag archives", "pagination", "generic metadata on non-converting guides"],
    ownerRule: "Comparison, tariff, schema, canonical, crawl, and route-boundary issues often need your_web_person. Editorial clarifications can be you.",
  },
  booking_experiences_marketplace: {
    label: "booking / experiences marketplace",
    keywords: ["booking", "reservation", "réservation", "activity", "activities", "activite", "activité", "event", "tour", "destination", "billet", "ticket", "travel", "voyage", "stage", "pilotage", "pass", "atelier", "cadeau"],
    moneyPatterns: ["/booking", "/reservation", "/activity", "/activities", "/activite", "/activité", "/event", "/tour", "/destination", "/billet", "/ticket", "/stage", "/pilotage", "/pass", "/show", "/checkout"],
    priorityPages: ["listing/category pages", "activity/detail pages", "location pages", "booking and checkout paths", "gift/ticket pages", "review/trust pages"],
    priorityIssues: ["JavaScript rendering", "crawlable listing content", "booking route boundaries", "schema", "blocked listings", "duplicate templates", "missing trust signals"],
    demote: ["old editorial posts", "tag archives", "low-value pagination", "one-off metadata on inactive listings"],
    ownerRule: "Rendering, schema, canonical, booking-flow, and template fixes usually need your_web_person.",
  },
  ecommerce_specialty_retail: {
    label: "ecommerce / specialty retail",
    keywords: ["product", "produit", "shop", "boutique", "cart", "panier", "checkout", "price", "prix", "sku", "collection", "category", "marque", "brand", "size", "variant", "shipping", "livraison", "shopify"],
    moneyPatterns: ["/products/", "/product/", "/produit/", "/collections/", "/collection/", "/category/", "/categorie/", "/shop", "/boutique", "/cart", "/checkout", "/marque"],
    priorityPages: ["product pages", "collection/category pages", "brand pages", "cart/checkout route boundaries", "shipping/returns/trust pages"],
    priorityIssues: ["product/category indexability", "product schema", "canonicalization", "blocked product pages", "template image-alt issues", "checkout/account route boundaries"],
    demote: ["old blog posts", "tag archives", "generic metadata on inactive products"],
    ownerRule: "Product schema, canonical, template, cart/checkout, and blocked-product issues usually need your_web_person. Product copy and alt text can often be you.",
  },
  wine_regulated_commerce: {
    label: "wine / regulated commerce",
    keywords: ["wine", "vin", "vins", "champagne", "cave", "caviste", "whisky", "spirits", "alcool", "bottle", "domaine", "chateau", "château", "millésime", "vintage", "degustation", "dégustation"],
    moneyPatterns: ["/vin", "/vins", "/wine", "/champagne", "/whisky", "/spirits", "/product", "/produit", "/collections", "/boutique", "/cart", "/checkout", "/club"],
    priorityPages: ["product/bottle pages", "collection/appellation pages", "producer/domain pages", "club/subscription pages", "age/legal/shipping/trust pages"],
    priorityIssues: ["product schema", "legal/trust pages", "shipping/availability clarity", "canonicalization", "checkout route boundaries", "thin product templates"],
    demote: ["generic blog metadata", "old event/news pages", "tag archives"],
    ownerRule: "Schema, legal/trust, checkout, template, and canonical fixes usually need your_web_person; product descriptions may be you.",
  },
  saas_app_membership: {
    label: "SaaS / app / membership",
    keywords: ["dashboard", "login", "register", "app", "billing", "admin", "workspace", "account", "subscription", "developer", "pricing", "demo", "trial", "api", "report"],
    moneyPatterns: ["/pricing", "/register", "/signup", "/demo", "/contact", "/features", "/use-cases", "/solutions"],
    priorityPages: ["homepage", "pricing", "demo/signup", "features/use cases", "docs/help pages", "public trust/security pages"],
    priorityIssues: ["internal/auth route exposure", "custom domain trust", "duplicate casing", "thin app snapshots", "noindex boundaries", "canonicalization"],
    demote: ["metadata on internal routes", "duplicate app snapshots that should be noindexed", "low-value docs pagination"],
    ownerRule: "Route boundaries, auth, canonical, app rendering, and noindex rules need your_web_person.",
  },
  local_service_brochure: {
    label: "local service / brochure",
    keywords: ["service", "services", "contact", "appointment", "rendez-vous", "near me", "local", "agency", "agence", "location", "adresse", "phone", "heures", "hours"],
    moneyPatterns: ["/services", "/service", "/contact", "/appointment", "/rendez-vous", "/devis", "/quote", "/location", "/agence"],
    priorityPages: ["homepage", "service pages", "location/agency pages", "contact/quote pages", "reviews/trust pages"],
    priorityIssues: ["contact visibility", "local schema", "service-page clarity", "trust pages", "broken contact paths", "mobile usability"],
    demote: ["old blog posts", "archive metadata"],
    ownerRule: "Copy, headings, and simple page improvements can be you; schema, redirects, and technical issues need your_web_person.",
  },
  content_blog: {
    label: "content / blog-heavy site",
    keywords: ["blog", "news", "article", "guide", "resources", "insights", "author", "newsletter", "subscribe"],
    moneyPatterns: ["/newsletter", "/subscribe", "/contact", "/resources", "/guide", "/pricing"],
    priorityPages: ["pillar guides", "category hubs", "newsletter/subscription pages", "author/trust pages", "contact/conversion pages"],
    priorityIssues: ["duplicate/thin content", "author/reviewer trust", "internal linking", "canonicalization", "index bloat", "schema"],
    demote: ["tag pages", "date archives", "pagination", "old low-traffic news unless strategically important"],
    ownerRule: "Editorial changes can be you; indexation, canonical, templates, and schema often need your_web_person.",
  },
  general: {
    label: "general website",
    keywords: [],
    moneyPatterns: ["/contact", "/services", "/products", "/pricing"],
    priorityPages: ["homepage", "contact", "services/products", "pricing/quote", "trust pages"],
    priorityIssues: ["crawlability", "indexability", "trust", "broken pages", "schema", "metadata on key pages"],
    demote: ["archives", "tags", "pagination"],
    ownerRule: "Simple content edits can be you; crawl, schema, redirects, canonicals, and rendering need your_web_person.",
  },
};

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return Response.json({ success: false, error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const websiteUrl = body.website_url || body.normalized_url || body.url || "";
    const pages = pickFirstNonEmptyArray([body.crawled_pages, body.pages, body.scanned_pages, body.crawl_pages]);
    const rawFixes = pickFirstNonEmptyArray([body.raw_fixes, body.grouped_findings, body.raw_findings, body.findings, body.fixes, body.recommendations, body.issues]);
    const siteFingerprint = buildSiteFingerprint({ body, pages, websiteUrl });
    const playbook = getArchetypePlaybook(siteFingerprint.primary_archetype);
    const syntheticFixes = buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint, playbook });
    const canonicalFixes = prepareFixes([...rawFixes, ...syntheticFixes], siteFingerprint, body, playbook);
    const aiFixes = canonicalFixes.slice(0, MAX_AI_FIXES);
    const fallbackPlan = buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint, playbook });

    if (!websiteUrl || canonicalFixes.length === 0) {
      return Response.json({ success: true, ai_provider: "scanner_fallback", ai_review_warning: !websiteUrl ? "AI review ran, but website_url was missing. Scanner recommendations are shown." : "AI review ran, but no scanner recommendations were provided.", ...fallbackPlan });
    }

    const prompt = buildPrompt({ body, websiteUrl, pages, canonicalFixes: aiFixes, fallbackPlan, siteFingerprint, playbook });
    const aiErrors = [];
    const providers = AI_PROVIDER_ORDER === "base44_first" ? ["base44", "gemini"] : ["gemini", "base44"];

    for (const provider of providers) {
      if (provider === "gemini") {
        if (!GEMINI_API_KEY) { aiErrors.push("GEMINI_API_KEY is not configured."); continue; }
        try {
          const geminiResponse = await callGeminiAiReview({ prompt, schema: responseSchema() });
          const merged = mergeAiIntoFallback({ aiResponse: geminiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint, playbook });
          return Response.json({ success: true, ai_provider: "gemini", ai_review_warning: aiErrors.join(" "), ...merged });
        } catch (error) { aiErrors.push(`Gemini failed: ${error?.message || "Unknown Gemini error."}`); }
      }
      if (provider === "base44") {
        if (!base44.integrations?.Core?.InvokeLLM) { aiErrors.push("Base44 InvokeLLM is not available."); continue; }
        try {
          const rawBase44Response = await withTimeout(base44.integrations.Core.InvokeLLM({ prompt, response_json_schema: responseSchema() }), BASE44_AI_TIMEOUT_MS, "Base44 AI review");
          const aiResponse = unwrapAiResponse(rawBase44Response);
          const merged = mergeAiIntoFallback({ aiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint, playbook });
          return Response.json({ success: true, ai_provider: "base44_invokellm", ai_review_warning: aiErrors.join(" "), ...merged });
        } catch (error) { aiErrors.push(`Base44 AI failed: ${error?.message || "Unknown Base44 AI error."}`); }
      }
    }

    return Response.json({ success: true, ai_provider: "scanner_fallback", ai_review_warning: aiErrors.join(" ") || "AI review failed, so scanner recommendations are shown.", ...fallbackPlan });
  } catch (error) {
    console.error("aiReviewScan failed", error);
    return Response.json({ success: false, error: "aiReviewScan failed. Please try again." }, { status: 500 });
  }
});

async function callGeminiAiReview({ prompt, schema }) {
  const endpoint = `${GEMINI_BASE_URL}/${encodeURIComponent(GEMINI_MODEL)}:generateContent`;
  const response = await withTimeout(fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
    body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: prompt }] }], generationConfig: { temperature: 0.1, maxOutputTokens: 7000, responseMimeType: "application/json", responseSchema: schema } }),
  }), GEMINI_AI_TIMEOUT_MS, "Gemini AI review");
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
  try { return JSON.parse(cleaned); } catch {
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
  if (response?.content?.[0]?.text) return parseJsonObject(response.content[0].text);
  if (response?.text) return parseJsonObject(response.text);
  return response;
}

function buildSiteFingerprint({ body, pages, websiteUrl }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const pageText = safePages.slice(0, 180).map((page) => [page?.url, page?.final_url, page?.title, page?.h1, page?.meta_description, page?.page_template_family, page?.estimated_page_intent, page?.status_code, (page?.conversion_signals || []).join(" "), (page?.trust_signals || []).join(" ")].join(" ")).join(" ").toLowerCase();
  const bodyText = [websiteUrl, body?.business_name, body?.business_type, body?.cms_name, body?.cms_platform, body?.scan_mode, JSON.stringify(body?.business_priority_instruction || {}), pageText].join(" ").toLowerCase();
  const scores = Object.entries(ARCHETYPE_PLAYBOOKS).filter(([key]) => key !== "general").map(([key, playbook]) => ({ key, label: playbook.label, score: playbook.keywords.reduce((total, keyword) => total + countIncludes(bodyText, keyword), 0) + playbook.moneyPatterns.reduce((total, pattern) => total + countIncludes(bodyText, pattern), 0) * 1.5 })).sort((a, b) => b.score - a.score);
  const primary = scores[0]?.score > 0 ? scores[0].key : "general";
  const secondary = scores[1]?.score > Math.max(2, scores[0]?.score * 0.55) ? scores[1].key : "";
  const confidence = scores[0]?.score > 0 ? Math.min(0.95, 0.45 + scores[0].score / Math.max(10, scores[0].score + (scores[1]?.score || 0))) : 0.35;
  const pagesFound = getFirstNumber([body?.scan_coverage?.pages_found, body?.pages_found, body?.technical_audit_summary?.pages_found, safePages.length]);
  const pagesCrawled = getFirstNumber([body?.scan_coverage?.pages_crawled, body?.pages_crawled, body?.technical_audit_summary?.pages_crawled, safePages.length]);
  const routeBoundaryCount = safePages.filter((page) => isRouteBoundaryCandidate(page?.url || page?.final_url) || isInternalAppRoute(page?.url || page?.final_url)).length;
  const routeBoundaryRisk = routeBoundaryCount >= 4 ? "high" : routeBoundaryCount > 0 ? "medium" : "low";
  const hostname = safeHostname(websiteUrl);
  const playbook = getArchetypePlaybook(primary);
  const blockedAccessPages = safePages.filter(isBlockedAccessPage).length;
  return {
    primary_archetype: primary,
    secondary_archetype: secondary,
    archetype_label: playbook.label,
    vertical: primary,
    vertical_label: playbook.label,
    vertical_confidence: Number(confidence.toFixed(2)),
    business_model: detectBusinessModel(bodyText, primary),
    size_band: Math.max(pagesFound, pagesCrawled, safePages.length) >= 1000 ? "enterprise" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 150 ? "mid_market" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 30 ? "smb" : "micro",
    pages_found: pagesFound,
    pages_crawled: pagesCrawled,
    sampled_pages_sent_to_ai: getFirstNumber([body?.scan_coverage?.sampled_pages_sent_to_ai, safePages.length]),
    localization: detectLocalization(safePages, websiteUrl),
    render_mode: detectRenderMode(body, safePages),
    regulatory_sensitivity: ["finance_insurance_lead_gen", "utilities_comparison_lead_gen", "wine_regulated_commerce"].includes(primary) ? "trust_or_regulated" : "standard",
    likely_money_page_patterns: playbook.moneyPatterns,
    archetype_priority_pages: playbook.priorityPages,
    archetype_priority_issues: playbook.priorityIssues,
    archetype_demotions: playbook.demote,
    route_boundary_count: routeBoundaryCount,
    route_boundary_risk: routeBoundaryRisk,
    blocked_access_pages: blockedAccessPages,
    free_base44_subdomain: hostname.endsWith(".base44.app"),
    scoring_model: SCORING_MODEL,
  };
}

function detectBusinessModel(text, archetype) {
  if (hasAny(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"])) return "quote_or_comparison_lead_gen";
  if (hasAny(text, ["booking", "reservation", "réservation", "availability", "calendar", "book now", "ticket", "stage", "pass"])) return "booking_or_reservation";
  if (hasAny(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart", "shopify"])) return "catalog_or_ecommerce";
  if (hasAny(text, ["login", "dashboard", "subscription", "billing", "admin"])) return "saas_or_member_app";
  if (["finance_insurance_lead_gen", "utilities_comparison_lead_gen"].includes(archetype)) return "regulated_or_trust_lead_generation";
  if (archetype === "booking_experiences_marketplace") return "booking_or_reservation";
  if (["ecommerce_specialty_retail", "wine_regulated_commerce"].includes(archetype)) return "catalog_or_ecommerce";
  if (archetype === "local_service_brochure") return "local_lead_generation";
  return "content_or_general_business";
}

function detectLocalization(pages, websiteUrl) {
  const text = [websiteUrl, ...pages.slice(0, 100).map((page) => page?.url || page?.final_url || "")].join(" ").toLowerCase();
  const localeHits = (text.match(/\/(fr|en|es|de|it|nl|pt|ca|us|uk)([-_\/]|$)/g) || []).length;
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

function getArchetypePlaybook(key) { return ARCHETYPE_PLAYBOOKS[key] || ARCHETYPE_PLAYBOOKS.general; }

function buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint, playbook }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const fixes = [];
  const hostname = safeHostname(websiteUrl);
  if (hostname.endsWith(".base44.app")) fixes.push(makeSyntheticFix({ rule: "free_base44_subdomain", category: "indexability", priority: "high", title: "Move production SEO to a custom domain", explanation: "The site is on a free Base44 subdomain. That can be crawled, but it is not the strongest production SEO or trust setup.", why: "A custom domain improves brand trust, shareability, Search Console ownership, and company-specific search signals.", recommendation: "Connect a branded custom domain before treating this as the long-term production SEO home.", affectedPages: ["/"], difficulty: "developer", source: "archetype_strategy_layer" }));

  const routePages = safePages.filter((page) => (isRouteBoundaryCandidate(page?.url || page?.final_url) || isInternalAppRoute(page?.url || page?.final_url)) && pageIsIndexable(page));
  if (routePages.length > 0) fixes.push(makeSyntheticFix({ rule: "route_boundary_candidate_indexable", category: "indexability", priority: "critical", title: "Keep checkout, login, account, and app routes out of search", explanation: "FixList found checkout, login, account, dashboard, billing, cart, admin, or app-like routes that appear crawlable and indexable.", why: "These pages are usually not useful SEO landing pages. Letting them appear in search can dilute the site, confuse prospects, or expose private product structure.", recommendation: "Ask your web person to require login, add noindex, or keep these routes out of public search while preserving true public landing, category, product, booking, and help pages.", affectedPages: routePages.map((page) => cleanPath(page?.url || page?.final_url || "/")).slice(0, 80), difficulty: "developer", source: "archetype_route_boundary_layer" }));

  const blockedAccessGroups = buildBlockedAccessFindings(safePages, siteFingerprint, body);
  fixes.push(...blockedAccessGroups);

  const paths = safePages.map((page) => cleanPath(page?.url || page?.final_url || "").toLowerCase());
  const hasTrustPage = TRUST_PAGE_PATTERNS.some((pattern) => paths.some((path) => path.startsWith(pattern)));
  const trustSensitive = siteFingerprint.regulatory_sensitivity !== "standard" || siteFingerprint.primary_archetype === "saas_app_membership" || siteFingerprint.free_base44_subdomain;
  if (!hasTrustPage && safePages.length >= 4 && trustSensitive) fixes.push(makeSyntheticFix({ rule: "missing_trust_pages", category: "schema", priority: siteFingerprint.regulatory_sensitivity !== "standard" ? "high" : "medium", title: "Add public trust pages", explanation: `For a ${playbook.label} site, visitors and crawlers need clear trust, legal, contact, and ownership signals.`, why: "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.", recommendation: "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.", affectedPages: ["/"], difficulty: "moderate", source: "archetype_trust_layer" }));

  const repeatedThin = findRepeatedSnapshotGroups(safePages);
  if (repeatedThin.length > 0) fixes.push(makeSyntheticFix({ rule: "thin_repetitive_public_snapshots", category: "thin_content", priority: "high", title: "Reduce thin repetitive public snapshots", explanation: "Several public routes appear to return very similar titles, headings, or short descriptions.", why: "A technically crawlable page is not automatically useful to index. Thin repeated snapshots can dilute important business pages.", recommendation: "Keep internal/app pages private or noindex and add richer route-specific content only to pages meant to rank or convert.", affectedPages: repeatedThin.slice(0, 80), difficulty: "moderate", source: "archetype_strategy_layer" }));
  return fixes;
}

function buildBlockedAccessFindings(pages, siteFingerprint, body) {
  const blocked = (pages || []).filter(isBlockedAccessPage);
  if (blocked.length === 0) return [];
  const groups = new Map();
  for (const page of blocked) {
    const url = cleanPath(page?.url || page?.final_url || "/");
    const family = getTemplateFamily(url);
    const key = `${blockedAccessScope(url, siteFingerprint, body)}|${family}`;
    const current = groups.get(key) || [];
    current.push(page);
    groups.set(key, current);
  }
  const fixes = [];
  for (const [key, groupPages] of groups.entries()) {
    const [scope, family] = key.split("|");
    const urls = groupPages.map((page) => cleanPath(page?.url || page?.final_url || "/")).slice(0, 150);
    const isCommerceProduct = ["product_page", "collection_page", "category_page"].includes(family) || siteFingerprint.business_model === "catalog_or_ecommerce";
    const title = isCommerceProduct ? "Check product pages blocked by rate limiting" : "Check pages blocked by rate limiting";
    const explanation = isCommerceProduct
      ? "Several product or catalog URLs returned HTTP 429 or a connection-verification page during the scan. This usually means Shopify, a CDN, firewall, or bot-protection layer rate-limited the crawler. Treat it as one technical access issue, not many broken product-page copy tasks."
      : "Several URLs returned HTTP 429 or a connection-verification page during the scan. This usually means the server, CDN, firewall, or bot-protection layer rate-limited the crawler. Verify access before treating these as confirmed broken pages.";
    const why = isCommerceProduct
      ? "If legitimate crawlers cannot load product or collection pages, search engines may miss revenue-driving catalog content. But a 429 is not proof that customers see a broken page, so the next step is verification."
      : "Rate limiting can hide pages from crawlers if configured too aggressively, but it should be verified before being called a broken-page SEO issue.";
    const recommendation = "Ask your web person to check server, CDN, firewall, Shopify app, and bot-protection logs for these URLs. Confirm whether Googlebot and normal users can access them, then adjust rate-limit rules only if legitimate access is blocked.";
    fixes.push(makeSyntheticFix({ rule: isCommerceProduct ? "commerce_product_access_blocked" : "rate_limited_page", category: "web_dev", priority: groupPages.length >= 3 || isCommerceProduct ? "high" : "medium", title, explanation, why, recommendation, affectedPages: urls, difficulty: "developer", source: `blocked_access_group:${scope}:${family}` }));
  }
  return fixes;
}

function makeSyntheticFix({ rule, category, priority, title, explanation, why, recommendation, affectedPages, difficulty, source }) {
  const page = affectedPages?.[0] || "/";
  const id = stableId(`synthetic|${rule}|${page}|${title}`);
  const steps = defaultSteps({ category, rule, difficulty, recommendedValue: recommendation });
  return { id, fix_id: id, type: "site_level", rule, category, customer_category: friendlyCategory(category), issue_title: title, title, plain_english_explanation: explanation, plain_english_summary: explanation, why_it_matters: why, current_value: rule.includes("blocked") || rule.includes("rate_limited") ? "HTTP 429 / connection verification detected by scanner" : "Detected from crawl, route patterns, and archetype playbook.", recommended_value: recommendation, ai_recommendation: recommendation, priority, difficulty, status: difficulty === "developer" ? "needs_developer" : "needs_approval", can_auto_fix: false, requires_approval: difficulty !== "developer", requires_developer: difficulty === "developer", affected_pages: affectedPages || [page], page_url: page, confidence_score: 92, what_to_do: steps, what_to_do_steps: steps, fix_steps: steps, who_can_do_this: defaultOwner(difficulty), estimated_time: defaultTime(difficulty), time_estimate: defaultTime(difficulty), source: source || "archetype_strategy_layer" };
}

function prepareFixes(rawFixes, siteFingerprint, body, playbook) {
  const normalized = dedupeByFixId((Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) => normalizeFix(fix, index)));
  const scored = normalized.map((fix) => scoreFixForSite(fix, siteFingerprint, body, playbook));
  return groupBlockedAccessIssues(groupRepeatedIssues(groupTemplateIssues(scored))).sort(compareFixes).slice(0, 90);
}

function normalizeFix(fix, index) {
  const rule = cleanString(fix?.rule || fix?.type || fix?.issue_type || "");
  const category = CATEGORY_MAP[fix?.category] || CATEGORY_MAP[rule] || fix?.category || inferCategory(rule, fix);
  const pageUrl = cleanPath(fix?.page_url || fix?.url || fix?.affected_pages?.[0] || fix?.pages?.[0] || "/");
  const affected = normalizeAffectedPages(fix, pageUrl);
  const id = cleanString(fix?.id || fix?.fix_id || fix?.fingerprint) || stableId(`${rule}|${category}|${pageUrl}|${index}`);
  const difficulty = normalizeDifficulty(fix);
  const blockedAccess = isBlockedAccessFix(fix);
  const developerOwned = blockedAccess || needsDeveloperOwner({ ...fix, rule, category, difficulty });
  const title = blockedAccess ? "Check pages blocked by rate limiting" : cleanString(fix?.issue_title || fix?.title) || defaultTitle(category);
  const explanation = blockedAccess ? "The scanner saw HTTP 429, rate limiting, bot protection, or a connection-verification page. This is crawler access evidence, not a confirmed broken customer page." : cleanString(fix?.plain_english_explanation || fix?.explanation || fix?.summary || fix?.description) || "This recommendation was found during the website scan.";
  const why = blockedAccess ? "Rate limiting can block legitimate crawlers if configured too aggressively, but it needs verification before being treated as lost rankings or broken product pages." : cleanString(fix?.why_it_matters || fix?.why || fix?.impact) || "Improving this can help visitors and search engines understand the site more clearly.";
  const recommendation = blockedAccess ? "Ask your web person to verify server, CDN, firewall, Shopify app, and bot-protection logs. Confirm Googlebot and normal users can access the affected URLs before changing page content." : cleanString(fix?.recommended_value || fix?.recommendation || fix?.ai_recommendation || fix?.suggested_fix) || "Review and improve this item.";
  const steps = normalizeSteps(fix) || defaultSteps({ category, rule, difficulty: developerOwned ? "developer" : difficulty, recommendedValue: recommendation });
  return { ...fix, id, fix_id: id, rule: rule || category || "review", category, customer_category: blockedAccess ? "Scan coverage" : fix?.customer_category || friendlyCategory(category), issue_title: title, title, plain_english_explanation: explanation, plain_english_summary: cleanString(fix?.plain_english_summary || fix?.plain_english_explanation || fix?.explanation) || explanation, why_it_matters: why, recommended_value: recommendation, ai_recommendation: recommendation, current_value: blockedAccess ? "HTTP 429 / rate-limit / connection verification" : cleanString(fix?.current_value || fix?.current || ""), page_url: pageUrl, affected_pages: affected, source_pages: Array.isArray(fix?.source_pages) ? fix.source_pages.slice(0, 20) : [], link_text_samples: Array.isArray(fix?.link_text_samples) ? fix.link_text_samples.slice(0, 10) : [], url_confidence: fix?.url_confidence || "", url_suspicion_reasons: Array.isArray(fix?.url_suspicion_reasons) ? fix.url_suspicion_reasons.slice(0, 8) : [], priority: normalizePriority(fix?.priority), difficulty: developerOwned ? "developer" : difficulty, status: developerOwned ? "needs_developer" : fix?.status || (fix?.can_auto_fix ? "auto_fixed" : "needs_approval"), requires_developer: developerOwned || Boolean(fix?.requires_developer), requires_approval: developerOwned ? false : fix?.requires_approval !== false, can_auto_fix: Boolean(fix?.can_auto_fix) && !developerOwned, what_to_do: steps, what_to_do_steps: steps, who_can_do_this: developerOwned ? "your_web_person" : normalizeOwner(fix?.who_can_do_this), estimated_time: cleanString(fix?.estimated_time || fix?.time_estimate) || defaultTime(developerOwned ? "developer" : difficulty), time_estimate: cleanString(fix?.time_estimate || fix?.estimated_time) || defaultTime(developerOwned ? "developer" : difficulty), confidence_score: typeof fix?.confidence_score === "number" ? fix.confidence_score : 80, blocked_access_evidence: blockedAccess };
}

function scoreFixForSite(fix, siteFingerprint, body, playbook) {
  const pageUrl = cleanPath(fix?.page_url || fix?.affected_pages?.[0] || "/") || "/";
  const pageValue = scorePageValue(pageUrl, siteFingerprint, body, playbook);
  const defectClass = classifyDefectClass(fix);
  const evidenceConfidence = scoreEvidenceConfidence(fix);
  const reachScore = scoreReach(fix);
  const siteFitScore = scoreSiteFit(fix, pageValue, siteFingerprint, defectClass, playbook);
  const businessImpactScore = scoreBusinessImpact(fix, pageValue, siteFingerprint, defectClass);
  const metadataIssue = isMetadataIssue(fix);
  const blockedAccess = isBlockedAccessFix(fix);
  const metaRewriteAllowed = metadataIssue && !blockedAccess && pageValue.classification === "money_page" && !["structural", "crawl_index", "semantic_schema", "content_trust", "route_boundary"].includes(defectClass) && !isImageAltIssue(fix);
  let overall = Math.round(evidenceConfidence * 0.18 + siteFitScore * 0.24 + businessImpactScore * 0.34 + reachScore * 0.14 + pageValue.score * 0.10);
  if (blockedAccess && fix.affected_pages?.length <= 1 && pageValue.classification !== "money_page") overall = Math.min(overall, 58);
  if (blockedAccess && fix.affected_pages?.length >= 3) overall = Math.max(overall, 72);
  const priority = overall >= 82 || fix.priority === "critical" ? "critical" : overall >= 68 ? "high" : overall >= 44 ? "medium" : "low";
  const developerOwned = blockedAccess || needsDeveloperOwner({ ...fix, primary_defect_class: defectClass });
  return { ...fix, priority: normalizePriority(priority), page_type: blockedAccess ? (pageValue.classification === "money_page" ? "blocked_important_page" : "blocked_standard_page") : pageValue.classification, page_template_family: getTemplateFamily(pageUrl), page_value_score: pageValue.score, page_value_label: blockedAccess ? "Crawler access/rate-limit evidence" : pageValue.label, primary_defect_class: blockedAccess ? "blocked_access" : defectClass, meta_rewrite_allowed: metaRewriteAllowed, meta_regeneration_gate: metadataIssue ? (metaRewriteAllowed ? "allowed_metadata_is_primary_gap" : "blocked_metadata_not_primary_gap") : "not_metadata", business_importance: pageValue.classification, evidence_confidence: evidenceConfidence, site_fit_score: siteFitScore, business_impact_score: businessImpactScore, reach_score: reachScore, overall_priority_score: Math.max(0, Math.min(100, overall)), site_fingerprint_vertical: siteFingerprint.primary_archetype, archetype_label: siteFingerprint.archetype_label, requires_developer: developerOwned || fix.requires_developer, difficulty: developerOwned ? "developer" : fix.difficulty, status: developerOwned ? "needs_developer" : fix.status, who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this };
}

function scorePageValue(url, siteFingerprint, body, playbook) {
  const path = cleanPath(url).toLowerCase();
  const requested = cleanPath(body?.requested_path_prefix || body?.crawl_path_prefix || "").toLowerCase();
  let score = 35;
  const reasons = [];
  if (path === "/" || path.endsWith("/index.html")) { score += 35; reasons.push("homepage or section landing page"); }
  if (requested && (path === requested || path === `${requested}/` || path === `${requested}/index.html`)) { score += 35; reasons.push("scanned section landing page"); }
  if (isRouteBoundaryCandidate(path) || isInternalAppRoute(path)) { score += 32; reasons.push("route-boundary candidate"); }
  for (const pattern of playbook.moneyPatterns || []) if (path.includes(pattern)) { score += 20; reasons.push(`matches archetype pattern ${pattern}`); break; }
  if (hasAny(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "pricing", "demo", "signup", "product", "products", "collection", "collections", "checkout"])) { score += 22; reasons.push("conversion, commerce, or lead page"); }
  const family = getTemplateFamily(path);
  if (["guide", "qa", "legal_info"].includes(family)) { score += siteFingerprint.regulatory_sensitivity !== "standard" ? 10 : 5; reasons.push("supporting guide/Q&A/legal content"); }
  if (isLowValuePage(path)) { score -= 45; reasons.push("news/blog/tag/archive/pagination pattern"); }
  const clamped = Math.max(0, Math.min(100, score));
  const classification = isRouteBoundaryCandidate(path) || isInternalAppRoute(path) ? "internal_or_auth_route" : clamped >= 70 ? "money_page" : clamped <= 30 ? "low_value" : ["guide", "qa", "legal_info"].includes(family) ? "support_content" : "standard";
  return { score: clamped, classification, label: classification === "internal_or_auth_route" ? "Route-boundary candidate" : classification === "money_page" ? "Important business page" : classification === "low_value" ? "Lower-priority archive/tag page" : classification === "support_content" ? "Supporting guide/Q&A/legal page" : "Standard page", reasons };
}

function classifyDefectClass(fix) {
  const rule = String(fix?.rule || "").toLowerCase();
  const category = String(fix?.category || "").toLowerCase();
  const text = `${rule} ${category} ${fix?.issue_title || ""} ${fix?.title || ""} ${fix?.current_value || ""}`.toLowerCase();
  if (isBlockedAccessFix(fix)) return "blocked_access";
  if (rule.includes("route_boundary") || rule.includes("internal_route") || hasAny(text, ["login", "account", "checkout", "dashboard", "noindex", "indexability"])) return "crawl_index";
  if (STRUCTURAL_RULES.has(rule) || STRUCTURAL_RULES.has(category) || hasAny(text, ["javascript", "render", "canonical", "redirect", "blocked", "429", "500", "404"])) return "structural";
  if (SEMANTIC_RULES.has(rule) || SEMANTIC_RULES.has(category) || text.includes("schema") || text.includes("structured")) return "semantic_schema";
  if (CONTENT_TRUST_RULES.has(rule) || CONTENT_TRUST_RULES.has(category) || hasAny(text, ["trust", "privacy", "terms", "legal", "about", "contact", "review", "methodology"])) return "content_trust";
  if (isImageAltIssue(fix)) return "image_accessibility";
  if (METADATA_RULES.has(rule) || METADATA_RULES.has(category) || hasAny(text, ["meta", "title", "description"])) return "metadata";
  return "general";
}

function scoreEvidenceConfidence(fix) { let score = typeof fix?.confidence_score === "number" ? fix.confidence_score : 72; if (fix?.source?.includes("scanner") || fix?.source?.includes("screaming") || fix?.source?.includes("strategy") || fix?.source?.includes("blocked_access")) score += 10; if (fix?.current_value) score += 5; if (Array.isArray(fix?.affected_pages) && fix.affected_pages.length > 1) score += 5; if (fix?.url_confidence === "crawler_artifact") score -= 35; if (isBlockedAccessFix(fix)) score = Math.min(score, 88); if (!fix?.page_url && (!fix?.affected_pages || fix.affected_pages.length === 0)) score -= 15; return Math.max(0, Math.min(100, Math.round(score))); }
function scoreReach(fix) { const count = Array.isArray(fix?.affected_pages) ? fix.affected_pages.length : 1; return Math.max(5, Math.min(100, count * 12)); }
function scoreSiteFit(fix, pageValue, siteFingerprint, defectClass, playbook) { let score = 45 + pageValue.score * 0.45; const text = `${fix?.category || ""} ${fix?.rule || ""} ${fix?.issue_title || ""} ${fix?.page_url || ""}`.toLowerCase(); if ((playbook.priorityIssues || []).some((item) => hasAny(text, String(item).split(/\s+/)))) score += 18; if (siteFingerprint.regulatory_sensitivity !== "standard" && ["content_trust", "semantic_schema", "crawl_index"].includes(defectClass)) score += 18; if (["structural", "crawl_index", "semantic_schema", "content_trust", "blocked_access"].includes(defectClass)) score += 12; if (isBlockedAccessFix(fix) && siteFingerprint.business_model === "catalog_or_ecommerce") score += 15; if (fix?.url_confidence === "crawler_artifact") score -= 30; return Math.max(0, Math.min(100, Math.round(score))); }
function scoreBusinessImpact(fix, pageValue, siteFingerprint, defectClass) { let score = pageValue.score; if (isSevereIssue(fix)) score += 25; if (isCosmeticIssue(fix)) score -= pageValue.classification === "low_value" ? 25 : pageValue.classification === "support_content" ? 12 : 5; if (pageValue.classification === "internal_or_auth_route" && defectClass === "crawl_index") score += 35; if (["structural", "crawl_index", "blocked_access"].includes(defectClass)) score += 18; if (defectClass === "semantic_schema" && pageValue.classification === "money_page") score += 15; if (defectClass === "content_trust" && siteFingerprint.regulatory_sensitivity !== "standard") score += 18; if (isBlockedAccessFix(fix) && Array.isArray(fix.affected_pages) && fix.affected_pages.length >= 3) score += 12; if (fix?.url_confidence === "crawler_artifact") score -= 40; return Math.max(0, Math.min(100, Math.round(score))); }

function groupBlockedAccessIssues(fixes) {
  const keep = [];
  const groups = new Map();
  for (const fix of fixes || []) {
    if (!isBlockedAccessFix(fix)) { keep.push(fix); continue; }
    const affected = normalizeAffectedPages(fix, fix.page_url);
    const family = fix.page_template_family || getTemplateFamily(fix.page_url || affected[0]);
    const shouldGroup = affected.length >= 2 || ["product_page", "collection_page", "category_page"].includes(family) || /product|catalog|shopify|commerce/i.test(`${fix.title} ${fix.issue_title} ${fix.source}`);
    if (!shouldGroup) { keep.push(fix); continue; }
    const key = `blocked_access|${family}|${statusBucket(fix)}`;
    const title = ["product_page", "collection_page", "category_page"].includes(family) ? "Check product/catalog pages blocked by rate limiting" : "Check pages blocked by rate limiting";
    const existing = groups.get(key) || { ...fix, id: stableId(`blocked_${key}`), fix_id: stableId(`blocked_${key}`), page_url: "", issue_title: title, title, plain_english_explanation: "Several similar pages returned HTTP 429, rate limiting, bot protection, or a connection-verification screen. Treat this as one crawler-access problem, not many confirmed broken pages or copy edits.", plain_english_summary: "Several similar pages returned HTTP 429, rate limiting, bot protection, or a connection-verification screen.", why_it_matters: "If legitimate crawlers cannot load important product, collection, listing, booking, or quote pages, they may miss revenue-driving content. A 429 still needs verification before being called a broken customer page.", recommended_value: "Ask your web person to check CDN, firewall, Shopify app, server, and bot-protection logs. Confirm whether Googlebot and normal users can access the affected URLs, then adjust rules only if legitimate access is blocked.", ai_recommendation: "Ask your web person to check CDN, firewall, Shopify app, server, and bot-protection logs. Confirm whether Googlebot and normal users can access the affected URLs, then adjust rules only if legitimate access is blocked.", affected_pages: [], page_count: 0, priority: "high", difficulty: "developer", who_can_do_this: "your_web_person", requires_developer: true, status: "needs_developer", can_auto_fix: false, requires_approval: false, customer_category: "Scan coverage", current_value: "HTTP 429 / connection verification detected by scanner", page_value_label: "Crawler access/rate-limit evidence", primary_defect_class: "blocked_access", meta_rewrite_allowed: false, meta_regeneration_gate: "not_metadata", overall_priority_score: Math.max(72, Number(fix.overall_priority_score || 0)), what_to_do: blockedAccessSteps(), what_to_do_steps: blockedAccessSteps(), fix_steps: blockedAccessSteps(), estimated_time: "about 1–2 hours", time_estimate: "about 1–2 hours" };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...affected])).slice(0, 150);
    existing.page_count = existing.affected_pages.length;
    existing.reach_score = scoreReach(existing);
    groups.set(key, existing);
  }
  return [...keep, ...groups.values()];
}

function groupRepeatedIssues(fixes) {
  const keep = [];
  const groups = new Map();
  for (const fix of fixes || []) {
    const affected = normalizeAffectedPages(fix, fix.page_url);
    const family = fix.page_template_family || getTemplateFamily(fix.page_url);
    const severeGroup = isRepeatedSevereCandidate(fix) && affected.length >= 3;
    if (!severeGroup) { keep.push(fix); continue; }
    const key = `severe|${fix.rule || fix.category}|${family}|${statusBucket(fix)}`;
    const existing = groups.get(key) || { ...fix, id: stableId(`repeated_${key}`), fix_id: stableId(`repeated_${key}`), page_url: "", issue_title: repeatedSevereTitle(fix, family), title: repeatedSevereTitle(fix, family), plain_english_explanation: "Several similar pages are failing or blocked in the same way. Treat this as one template, access, or crawlability problem instead of many separate tasks.", plain_english_summary: "Several similar pages are failing or blocked in the same way. Treat this as one template, access, or crawlability problem instead of many separate tasks.", why_it_matters: "Repeated blocked or failed pages can hide products, listings, bookings, quote paths, or important content from search engines and users.", recommended_value: "Check whether the affected page template, firewall, bot protection, redirects, or server rules are causing these failures. Fix the shared cause, then rescan.", ai_recommendation: "Check whether the affected page template, firewall, bot protection, redirects, or server rules are causing these failures. Fix the shared cause, then rescan.", affected_pages: [], page_count: 0, priority: fix.business_importance === "low_value" ? "medium" : "high", difficulty: "developer", who_can_do_this: "your_web_person", requires_developer: true, status: "needs_developer", estimated_time: "about 1–2 hours", time_estimate: "about 1–2 hours", primary_defect_class: "structural", meta_rewrite_allowed: false, meta_regeneration_gate: "not_metadata", overall_priority_score: Math.max(72, Number(fix.overall_priority_score || 0)), what_to_do: ["Send the grouped affected URLs to your web person.", "Check whether bot protection, redirects, firewall rules, or a shared template are causing the failures.", "Fix the shared cause instead of editing every page one by one.", "Run FixList again to confirm the pages load."], what_to_do_steps: ["Send the grouped affected URLs to your web person.", "Check whether bot protection, redirects, firewall rules, or a shared template are causing the failures.", "Fix the shared cause instead of editing every page one by one.", "Run FixList again to confirm the pages load."] };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...affected])).slice(0, 150);
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
    const affected = normalizeAffectedPages(fix, fix.page_url);
    const shouldGroup = affected.length >= 3 || (fix.business_importance === "low_value" && isCosmeticIssue(fix)) || (["guide", "qa", "legal_info"].includes(family) && isCosmeticIssue(fix)) || (fix.meta_regeneration_gate === "blocked_metadata_not_primary_gap" && !isSevereIssue(fix) && fix.business_importance !== "money_page");
    if (!shouldGroup) { keep.push(fix); continue; }
    const key = `${family}|${fix.rule || fix.category || "cleanup"}|${fix.primary_defect_class || "general"}`;
    const title = groupTemplateTitle(fix, family);
    const existing = groups.get(key) || { ...fix, id: stableId(`template_group_${key}`), fix_id: stableId(`template_group_${key}`), page_url: "", issue_title: title, title, plain_english_explanation: "Several similar pages have the same pattern-level issue. Fix the shared template or batch rule instead of treating every page as a separate task.", plain_english_summary: "Several similar pages have the same pattern-level issue. Fix the shared template or batch rule instead of treating every page as a separate task.", why_it_matters: fix.business_importance === "low_value" ? "These pages matter less than pages that drive leads, sales, bookings, quotes, trust, or safe indexation." : "Template-level issues can affect many important pages at once.", recommended_value: "Fix one representative page or template first, then apply the same rule across the affected group.", ai_recommendation: "Fix one representative page or template first, then apply the same rule across the affected group.", affected_pages: [], page_count: 0, meta_rewrite_allowed: false, meta_regeneration_gate: fix.meta_regeneration_gate === "blocked_metadata_not_primary_gap" ? "blocked_grouped_for_later" : fix.meta_regeneration_gate, overall_priority_score: Math.max(Number(fix.overall_priority_score || 0), fix.business_importance === "money_page" ? 65 : 35), what_to_do: ["Fix important business pages first.", "Pick one affected page as the example.", "Apply the same template or batch rule to the rest.", "Run FixList again after publishing."], what_to_do_steps: ["Fix important business pages first.", "Pick one affected page as the example.", "Apply the same template or batch rule to the rest.", "Run FixList again after publishing."] };
    existing.affected_pages = Array.from(new Set([...existing.affected_pages, ...affected])).slice(0, 150);
    existing.page_count = existing.affected_pages.length;
    existing.reach_score = scoreReach(existing);
    groups.set(key, existing);
  }
  return [...keep, ...groups.values()];
}

function buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint, playbook }) {
  const score = getFirstNumber([body?.health_score, body?.seo_score, body?.scan_summary?.health_score, body?.scan_summary?.score]) || calculateFallbackScore(canonicalFixes);
  const positiveFindings = buildPositiveFindings({ pages, siteFingerprint });
  const topRecommendedActions = buildTopActions(canonicalFixes);
  const healthReport = buildFallbackHealthReport({ body, pages, fixes: canonicalFixes, score, positiveFindings, siteFingerprint, playbook });
  return makeFrontendCompatible({ plain_english_summary: healthReport.overall_explanation, website_health_report: healthReport, health_explanation: healthReport.overall_explanation, customer_summary: healthReport.overall_explanation, top_recommended_actions: topRecommendedActions, recommended_actions: [], cleaned_fixes: canonicalFixes, raw_fixes: canonicalFixes, fixes: canonicalFixes, findings: canonicalFixes, recommendations: canonicalFixes, competitor_insights: [], grouped_page_recommendations: buildGroupedPageRecommendations(canonicalFixes), ignored_low_value_pages: canonicalFixes.filter((fix) => String(fix.business_importance || "").includes("low_value")).slice(0, 10), positive_findings: positiveFindings, ai_rewrites_applied: 0, crawled_pages: pages, pages, health_score: score, site_fingerprint: siteFingerprint, archetype_playbook: publicPlaybook(playbook), technical_audit_summary: body?.technical_audit_summary || null, screaming_frog_lite_enabled: Boolean(body?.technical_audit_summary?.screaming_frog_lite_enabled || body?.screaming_frog_lite_enabled), audit_profile: body?.audit_profile || "" });
}

function buildFallbackHealthReport({ body, pages, fixes, score, positiveFindings, siteFingerprint, playbook }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const pagesCrawled = getFirstNumber([body?.scan_coverage?.pages_crawled, body?.pages_crawled, body?.technical_audit_summary?.pages_crawled, safePages.length]);
  const blockedGroups = fixes.filter(isBlockedAccessFix).length;
  const topConcerns = fixes.slice(0, 5).map((fix) => fix.title || fix.issue_title).filter(Boolean);
  const summary = `FixList recognized this as ${playbook.label} and used the ${playbook.label} playbook. The scanner reviewed ${pagesCrawled} pages${siteFingerprint.pages_found ? ` out of about ${siteFingerprint.pages_found} discovered URLs` : ""}. ${blockedGroups ? "Some URLs returned rate-limit or bot-protection responses, so those are treated as crawler-access checks rather than confirmed broken customer pages. " : ""}Start with the highest-impact items on ${playbook.priorityPages.slice(0, 3).join(", ")}.`;
  return { health_score: score, health_grade: score >= 90 ? "Excellent" : score >= 75 ? "Good" : score >= 55 ? "Fair" : "Needs work", overall_explanation: summary, what_is_working: positiveFindings.slice(0, 5), top_concerns: topConcerns, quick_wins: fixes.filter((fix) => !fix.requires_developer).slice(0, 4).map((fix) => fix.title || fix.issue_title), bigger_projects: fixes.filter((fix) => fix.requires_developer).slice(0, 4).map((fix) => fix.title || fix.issue_title), limitations: ["This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs.", "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages."], next_best_step: topConcerns[0] || "Review the first FixList item." };
}

function mergeAiIntoFallback({ aiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint, playbook }) {
  const safeAi = aiResponse && typeof aiResponse === "object" ? aiResponse : {};
  const aiFixes = pickFirstNonEmptyArray([safeAi.cleaned_fixes, safeAi.recommendations, safeAi.fixes, safeAi.findings]).map((fix) => mergeAiFixWithCanonical(fix, canonicalFixes)).filter(Boolean);
  const finalFixes = aiFixes.length ? preserveBlockedAccessFixes(aiFixes, canonicalFixes) : canonicalFixes;
  const fallbackReport = fallbackPlan.website_health_report || {};
  const report = { ...fallbackReport, ...(safeAi.website_health_report || {}) };
  report.overall_explanation = cleanString(safeAi.customer_summary || safeAi.plain_english_summary || safeAi.summary || report.overall_explanation) || fallbackReport.overall_explanation;
  return makeFrontendCompatible({ ...fallbackPlan, ...safeAi, website_health_report: report, customer_summary: report.overall_explanation, plain_english_summary: report.overall_explanation, health_explanation: report.overall_explanation, cleaned_fixes: finalFixes, raw_fixes: finalFixes, fixes: finalFixes, findings: finalFixes, recommendations: finalFixes, top_recommended_actions: buildTopActions(finalFixes), recommended_actions: buildTopActions(finalFixes), grouped_page_recommendations: buildGroupedPageRecommendations(finalFixes), crawled_pages: pages, pages, site_fingerprint: siteFingerprint, archetype_playbook: publicPlaybook(playbook), health_score: getFirstNumber([safeAi.health_score, safeAi.seo_score, report.health_score, fallbackPlan.health_score]) });
}

function mergeAiFixWithCanonical(aiFix, canonicalFixes) {
  const id = aiFix?.fix_id || aiFix?.id;
  const match = canonicalFixes.find((fix) => fix.fix_id === id || fix.id === id) || null;
  if (!match) return null;
  if (isBlockedAccessFix(match)) return match;
  const title = cleanString(aiFix?.title || aiFix?.issue_title) || match.title;
  const explanation = cleanString(aiFix?.plain_english_explanation || aiFix?.plain_english_summary || aiFix?.explanation) || match.plain_english_explanation;
  const recommendation = cleanString(aiFix?.recommended_value || aiFix?.ai_recommendation || aiFix?.recommendation) || match.recommended_value;
  const developerOwned = needsDeveloperOwner({ ...match, ...aiFix });
  return { ...match, ...aiFix, id: match.id, fix_id: match.fix_id, title, issue_title: title, plain_english_explanation: explanation, plain_english_summary: explanation, recommended_value: recommendation, ai_recommendation: recommendation, why_it_matters: cleanString(aiFix?.why_it_matters || aiFix?.reason) || match.why_it_matters, what_to_do: normalizeSteps(aiFix) || match.what_to_do, what_to_do_steps: normalizeSteps(aiFix) || match.what_to_do_steps, requires_developer: developerOwned || match.requires_developer, difficulty: developerOwned ? "developer" : match.difficulty, status: developerOwned ? "needs_developer" : match.status, who_can_do_this: developerOwned ? "your_web_person" : match.who_can_do_this };
}

function preserveBlockedAccessFixes(aiFixes, canonicalFixes) {
  const output = [...aiFixes];
  const existingIds = new Set(output.map((fix) => fix.fix_id || fix.id));
  for (const fix of canonicalFixes) {
    if (isBlockedAccessFix(fix) && !existingIds.has(fix.fix_id || fix.id)) output.push(fix);
  }
  return output.sort(compareFixes).slice(0, 90);
}

function buildPrompt({ body, websiteUrl, pages, canonicalFixes, fallbackPlan, siteFingerprint, playbook }) {
  const pageSample = (pages || []).slice(0, MAX_PROMPT_PAGES).map((page) => ({ url: page?.url || page?.final_url, status_code: page?.status_code, title: page?.title, h1: page?.h1, template: page?.page_template_family, intent: page?.estimated_page_intent, route_boundary_candidate: page?.route_boundary_candidate, url_confidence: page?.url_confidence })).filter((page) => page.url);
  return `You are FixList, a plain-English SEO advisor. Return only valid JSON matching the schema.

Website: ${websiteUrl}
Business name: ${body?.business_name || ""}
CMS: ${body?.cms_name || body?.cms_platform || "unknown"}
Scan coverage: ${JSON.stringify(body?.scan_coverage || {}, null, 2)}
Site fingerprint: ${JSON.stringify(siteFingerprint, null, 2)}
Archetype playbook: ${JSON.stringify(publicPlaybook(playbook), null, 2)}

Use the playbook as priority context only. Do not mention competitor or benchmark sites unless the user supplied competitor URLs. Use it to decide which pages and defects matter most for this business model.

Hard rules:
- Do not invent findings, URLs, rankings, traffic, leads, revenue, or server causes.
- Rewrite only the supplied fix IDs. Keep exact fix_id values.
- Focus top actions on archetype-critical pages, not low-value archives.
- Demote old news, tags, archives, and pagination unless the site is content-first.
- Internal/auth/app/checkout/account routes are route-boundary evidence and usually belong to the web person.
- HTTP 429, rate-limit, bot protection, Cloudflare, Shopify connection verification, or “Verifying your connection” are crawler-access checks. Do not call them confirmed broken customer pages unless the evidence proves normal users are blocked.
- Repeated blocked product/catalog/listing pages must be one grouped technical access issue owned by your_web_person, not many copy or metadata tasks.
- If a selected scan section finds same-parent-domain sibling vertical URLs, treat them as parent-domain/sibling-scope evidence, not automatically as primary selected-section pages.
- Metadata rewrites are allowed only when metadata is the main gap on an important public page.
- Image alt text is an image/content accessibility issue, not metadata.
- Keep language simple and specific.

Page sample:
${JSON.stringify(pageSample, null, 2)}

Canonical fixes to rewrite:
${JSON.stringify(canonicalFixes, null, 2)}

Fallback plan, for reference:
${JSON.stringify({ summary: fallbackPlan.customer_summary, top_recommended_actions: fallbackPlan.top_recommended_actions?.slice?.(0, 5) || [] }, null, 2)}
`;
}

function responseSchema() {
  return { type: "object", properties: { customer_summary: { type: "string" }, health_score: { type: "number" }, website_health_report: { type: "object", properties: { health_score: { type: "number" }, health_grade: { type: "string" }, overall_explanation: { type: "string" }, what_is_working: { type: "array", items: { type: "string" } }, top_concerns: { type: "array", items: { type: "string" } }, quick_wins: { type: "array", items: { type: "string" } }, bigger_projects: { type: "array", items: { type: "string" } }, limitations: { type: "array", items: { type: "string" } }, next_best_step: { type: "string" } } }, cleaned_fixes: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, title: { type: "string" }, issue_title: { type: "string" }, plain_english_explanation: { type: "string" }, plain_english_summary: { type: "string" }, why_it_matters: { type: "string" }, recommended_value: { type: "string" }, ai_recommendation: { type: "string" }, priority: { type: "string" }, who_can_do_this: { type: "string" }, what_to_do_steps: { type: "array", items: { type: "string" } }, time_estimate: { type: "string" } }, required: ["fix_id"] } }, top_recommended_actions: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, title: { type: "string" }, reason: { type: "string" }, priority: { type: "string" }, who_can_do_this: { type: "string" }, what_to_do_steps: { type: "array", items: { type: "string" } }, time_estimate: { type: "string" } } } } } };
}

function makeFrontendCompatible(payload) {
  const fixes = pickFirstNonEmptyArray([payload.cleaned_fixes, payload.recommendations, payload.fixes, payload.findings]);
  const pages = pickFirstNonEmptyArray([payload.crawled_pages, payload.pages]);
  const health = getFirstNumber([payload.health_score, payload.seo_score, payload.website_health_report?.health_score, payload.scan_summary?.health_score]);
  const summary = cleanString(payload.customer_summary || payload.plain_english_summary || payload.website_health_report?.overall_explanation || payload.summary) || "FixList reviewed the scan and prepared prioritized recommendations.";
  return { ...payload, health_score: health, seo_score: health, customer_summary: summary, plain_english_summary: summary, simple_summary: summary, cleaned_fixes: fixes, raw_fixes: fixes, fixes, findings: fixes, recommendations: fixes, crawled_pages: pages, pages, scanned_pages: pages, scan_summary: { ...(payload.scan_summary || {}), health_score: health, score: health, pages_scanned: payload?.site_fingerprint?.pages_crawled || pages.length, plain_english_summary: summary, site_fingerprint: payload.site_fingerprint || {} }, website_health_report: { health_score: health, score: health, overall_explanation: summary, ...(payload.website_health_report || {}) }, site_fingerprint: payload.site_fingerprint || {}, archetype_playbook: payload.archetype_playbook || {}, scoring_model: SCORING_MODEL };
}

function buildTopActions(fixes) {
  return (fixes || []).slice().sort(compareFixes).slice(0, 5).map((fix) => ({ fix_id: fix.fix_id || fix.id, title: fix.title || fix.issue_title, reason: fix.why_it_matters || fix.plain_english_summary || fix.plain_english_explanation, priority: fix.priority === "critical" ? "high" : fix.priority || "medium", who_can_do_this: fix.who_can_do_this === "your_web_person" || fix.requires_developer ? "Your web person" : "You", what_to_do_steps: firstArray([fix.what_to_do_steps, fix.what_to_do, fix.fix_steps]).slice(0, 5), time_estimate: fix.time_estimate || fix.estimated_time || "" }));
}

function buildGroupedPageRecommendations(fixes) { return (fixes || []).filter((fix) => Array.isArray(fix.affected_pages) && fix.affected_pages.length > 1).map((fix) => ({ title: fix.title || fix.issue_title, rule: fix.rule, category: fix.category, affected_pages: fix.affected_pages, page_count: fix.affected_pages.length, priority: fix.priority })).slice(0, 20); }
function publicPlaybook(playbook) { return { label: playbook.label, priority_pages: playbook.priorityPages, priority_issues: playbook.priorityIssues, demote: playbook.demote, owner_rule: playbook.ownerRule }; }
function buildPositiveFindings({ pages, siteFingerprint }) { const safePages = Array.isArray(pages) ? pages : []; const positives = []; if (safePages.length > 0) positives.push(`FixList scanned ${safePages.length} page sample records.`); if (siteFingerprint.primary_archetype !== "general") positives.push(`FixList detected a ${siteFingerprint.archetype_label} pattern.`); if (safePages.some((page) => page?.title)) positives.push("Some pages expose crawlable titles."); if (safePages.some((page) => page?.canonical || page?.canonical_url)) positives.push("Some pages include canonical URL signals."); return positives.slice(0, 5); }
function calculateFallbackScore(fixes) { let score = 86; for (const fix of fixes || []) { const priority = normalizePriority(fix.priority); if (priority === "critical") score -= 14; else if (priority === "high") score -= 9; else if (priority === "medium") score -= 4; else score -= 1; } return Math.max(20, Math.min(95, score)); }

function isBlockedAccessPage(page = {}) {
  const text = `${page?.status_code || ""} ${page?.fetch_error || ""} ${page?.title || ""} ${page?.h1 || ""} ${page?.meta_description || ""} ${page?.current_value || ""}`.toLowerCase();
  return Number(page?.status_code || 0) === 429 || hasAny(text, ["429", "too many requests", "rate limit", "rate-limit", "rate limited", "bot protection", "cloudflare", "verifying your connection", "just a moment", "checking your browser"]);
}

function isBlockedAccessFix(fix = {}) {
  const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""} ${fix?.issue_title || ""} ${fix?.current_value || ""} ${fix?.fetch_error || ""} ${fix?.recommended_value || ""} ${fix?.plain_english_explanation || ""} ${fix?.source || ""}`.toLowerCase();
  const status = getFirstNumber([fix?.status_code, fix?.current_status_code, fix?.http_status, fix?.evidence?.status_code]);
  return status === 429 || hasAny(text, ["429", "too many requests", "rate limit", "rate-limit", "rate limited", "bot protection", "cloudflare", "verifying your connection", "checking your browser", "connection verification", "blocked product", "blocked_page_429", "rate_limited_page", "commerce_product_access_blocked"]);
}

function blockedAccessSteps() { return ["Send the grouped affected URLs to your web person.", "Check CDN, firewall, Shopify app, server, and bot-protection logs for HTTP 429 or verification responses.", "Confirm whether Googlebot and normal users can load the pages.", "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.", "Run FixList again to confirm the affected pages load."]; }
function blockedAccessScope(url, siteFingerprint, body) { const path = cleanPath(url).toLowerCase(); if (isRouteBoundaryCandidate(path)) return "route_boundary"; if (String(body?.requested_path_prefix || "") && !path.startsWith(cleanPath(body.requested_path_prefix).toLowerCase())) return "outside_selected_scope"; if (siteFingerprint.business_model === "catalog_or_ecommerce" && /product|products|collection|collections|category|shop/.test(path)) return "commerce_catalog"; return "site_access"; }

function normalizeAffectedPages(fix, fallback) { return Array.from(new Set([...(Array.isArray(fix?.affected_pages) ? fix.affected_pages : []), ...(Array.isArray(fix?.pages) ? fix.pages : []), ...(Array.isArray(fix?.page_urls) ? fix.page_urls : []), fallback].filter(Boolean).map((url) => cleanPath(url)))).slice(0, 150); }
function dedupeByFixId(fixes) { const seen = new Set(); const output = []; for (const fix of fixes || []) { const key = fix.fix_id || fix.id || `${fix.rule}|${fix.category}|${fix.page_url}|${(fix.affected_pages || []).join(",")}`; if (seen.has(key)) continue; seen.add(key); output.push(fix); } return output; }
function compareFixes(a, b) { const priorityScore = { critical: 4, high: 3, medium: 2, low: 1 }; return (Number(b.overall_priority_score || 0) + (priorityScore[b.priority] || 0) * 100) - (Number(a.overall_priority_score || 0) + (priorityScore[a.priority] || 0) * 100); }
function statusBucket(fix) { const text = `${fix?.status_code || ""} ${fix?.current_value || ""} ${fix?.title || ""} ${fix?.rule || ""}`.toLowerCase(); if (text.includes("429") || text.includes("rate")) return "429"; if (text.includes("500") || text.includes("503")) return "5xx"; if (text.includes("404")) return "404"; return "blocked"; }
function repeatedSevereTitle(fix, family) { if (isBlockedAccessFix(fix)) return ["product_page", "collection_page", "category_page"].includes(family) ? "Check product/catalog pages blocked by rate limiting" : "Check pages blocked by rate limiting"; if (String(fix?.rule || "").includes("429")) return "Check pages blocked by rate limiting"; if (String(fix?.rule || "").includes("404")) return "Group repeated broken-page checks"; return `Fix repeated ${humanize(family)} page failures`; }
function groupTemplateTitle(fix, family) { const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""}`.toLowerCase(); const label = humanize(family || "template").toLowerCase(); if (text.includes("schema")) return `Add structured data to ${label} templates`; if (text.includes("h1")) return `Fix missing H1 headings on ${label} templates`; if (text.includes("alt")) return `Batch image descriptions on ${label} pages`; if (text.includes("description") || text.includes("meta")) return `Batch search descriptions on ${label} pages`; return `Fix repeated ${label} template issue`; }
function isRepeatedSevereCandidate(fix) { return isBlockedAccessFix(fix) || isSevereIssue(fix) || hasAny(`${fix?.rule || ""} ${fix?.category || ""} ${fix?.current_value || ""}`, ["404", "410", "429", "500", "blocked", "server_error"]); }
function isSevereIssue(fix) { const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""} ${fix?.current_value || ""}`.toLowerCase(); return hasAny(text, ["404", "410", "429", "500", "server", "blocked", "canonical", "redirect", "noindex", "indexability", "javascript", "render"]); }
function isCosmeticIssue(fix) { const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""}`.toLowerCase(); return hasAny(text, ["meta", "title", "description", "alt", "h1", "thin", "duplicate"]); }
function isMetadataIssue(fix) { const rule = String(fix?.rule || "").toLowerCase(); const category = String(fix?.category || "").toLowerCase(); const text = `${rule} ${category} ${fix?.title || ""}`.toLowerCase(); return !isImageAltIssue(fix) && (METADATA_RULES.has(rule) || METADATA_RULES.has(category) || hasAny(text, ["meta title", "meta description", "search title", "search description"])); }
function isImageAltIssue(fix) { return /image_alt_text|image alt|alt text|missing alt|image description/i.test(`${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""} ${fix?.issue_title || ""}`); }
function needsDeveloperOwner(item = {}) { const value = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.reason || ""} ${item.recommendation || ""} ${item.recommended_value || ""} ${firstArray([item.what_to_do_steps, item.what_to_do]).join(" ")} ${item.who_can_do_this || ""} ${item.primary_defect_class || ""}`.toLowerCase(); if (isBlockedAccessFix(item)) return true; if (item.requires_developer || item.difficulty === "developer" || item.status === "needs_developer" || value.includes("your_web_person")) return true; return /developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard|shopify app/.test(value); }
function normalizeDifficulty(fix) { const difficulty = String(fix?.difficulty || fix?.estimated_complexity || "").toLowerCase(); if (difficulty.includes("developer") || difficulty.includes("complex")) return "developer"; if (difficulty.includes("moderate")) return "moderate"; return "easy"; }
function normalizeOwner(value) { const owner = String(value || "").toLowerCase(); if (owner.includes("web") || owner.includes("developer") || owner === "your_web_person") return "your_web_person"; return "you"; }
function defaultOwner(difficulty) { return difficulty === "developer" ? "your_web_person" : "you"; }
function defaultTime(difficulty) { if (difficulty === "developer") return "about 1–2 hours"; if (difficulty === "moderate") return "about 30–60 minutes"; return "about 10–20 minutes"; }
function defaultSteps({ category, rule, difficulty, recommendedValue }) { if (difficulty === "developer" || /429|blocked|rate_limited|commerce_product_access/i.test(String(rule || ""))) return blockedAccessSteps(); if (category === "schema") return ["Choose the correct schema type for the page.", "Add it through the CMS, SEO plugin, theme, or developer workflow.", "Validate structured data after publishing."]; if (category === "canonical") return ["Open the affected page or template.", "Set the canonical URL to the clean official page URL.", "Check duplicate and filtered URLs point to the official version."]; return ["Open the affected page or template.", cleanString(recommendedValue) || "Apply the recommended change.", "Publish the update and run FixList again."]; }
function normalizeSteps(fix) { const steps = firstArray([fix?.what_to_do_steps, fix?.what_to_do, fix?.fix_steps, fix?.steps]); return steps.length ? steps.map(String).filter(Boolean).slice(0, 6) : null; }
function inferCategory(rule, fix) { const text = `${rule} ${fix?.title || ""} ${fix?.issue_title || ""}`.toLowerCase(); if (isBlockedAccessFix(fix) || hasAny(text, ["429", "blocked", "rate limit", "bot protection"])) return "web_dev"; if (text.includes("schema") || text.includes("trust")) return "schema"; if (text.includes("canonical")) return "canonical"; if (text.includes("title")) return "meta_title"; if (text.includes("description") || text.includes("meta")) return "meta_description"; if (text.includes("alt")) return "image_alt_text"; if (text.includes("404") || text.includes("broken")) return "404_error"; if (text.includes("index") || text.includes("noindex")) return "indexability"; if (text.includes("render") || text.includes("javascript")) return "web_dev"; return "web_dev"; }
function defaultTitle(category) { const titles = { meta_title: "Improve search titles", meta_description: "Improve search descriptions", duplicate_content: "Review duplicate or repeated pages", canonical: "Review canonical URL setup", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", "404_error": "Fix pages that are not loading", web_dev: "Review website setup", image_alt_text: "Add useful image descriptions", indexability: "Review indexability settings" }; return titles[category] || "Review this recommendation"; }
function friendlyCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(priority)) return priority; return "medium"; }
function getTemplateFamily(url = "") { const path = cleanPath(url).toLowerCase(); if (isRouteBoundaryCandidate(path)) return "route_boundary"; if (isLowValuePage(path)) return "archive"; if (/checkout|cart|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/\/products?\/|\/p\//.test(path)) return "product_page"; if (/\/collections?\/|\/category\/|\/categorie\/|listing|show|marque|brand/.test(path)) return "collection_page"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog|article/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(path)) return "legal_info"; return "standard"; }
function isLowValuePage(url = "") { const path = cleanPath(url).toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; return LOW_VALUE_PATTERNS.some((pattern) => path.includes(pattern)); }
function isRouteBoundaryCandidate(url = "") { const path = cleanPath(url).toLowerCase(); return ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"].some((pattern) => path.includes(pattern)); }
function isInternalAppRoute(url = "") { const path = cleanPath(url).toLowerCase(); return INTERNAL_ROUTE_PATTERNS.some((pattern) => path.includes(pattern)); }
function pageIsIndexable(page) { const robots = String(page?.robots || page?.robots_meta || "").toLowerCase(); if (robots.includes("noindex")) return false; if (page?.indexable === false) return false; return true; }
function findRepeatedSnapshotGroups(pages) { const seen = new Map(); for (const page of pages || []) { const key = `${String(page?.title || "").trim().toLowerCase()}|${String(page?.h1 || "").trim().toLowerCase()}`; if (!key || key === "|") continue; const list = seen.get(key) || []; list.push(cleanPath(page?.url || page?.final_url || "/")); seen.set(key, list); } return Array.from(seen.values()).find((list) => list.length >= 6) || []; }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const url = new URL(raw); return `${url.pathname || "/"}${url.search || ""}` || "/"; } catch { return raw.startsWith("/") ? raw : `/${raw}`; } }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function hasAny(text, needles) { const haystack = String(text || "").toLowerCase(); return (needles || []).some((needle) => haystack.includes(String(needle || "").toLowerCase())); }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function pickFirstNonEmptyArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function firstArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function clampText(value, max) { const text = String(value || "").trim(); return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`; }
function humanize(value) { return String(value || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim(); }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
async function withTimeout(promise, timeoutMs, label) { let timeoutId; const timeoutPromise = new Promise((_, reject) => { timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs); }); try { return await Promise.race([promise, timeoutPromise]); } finally { clearTimeout(timeoutId); } }
