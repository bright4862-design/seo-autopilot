import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") || "";
const GEMINI_MODEL = Deno.env.get("GEMINI_MODEL") || "gemini-3.1-flash-lite";
const GEMINI_BASE_URL = Deno.env.get("GEMINI_BASE_URL") || "https://generativelanguage.googleapis.com/v1beta/models";
const GEMINI_AI_TIMEOUT_MS = Number(Deno.env.get("GEMINI_AI_TIMEOUT_MS") || 60000);
const BASE44_AI_TIMEOUT_MS = Number(Deno.env.get("BASE44_AI_TIMEOUT_MS") || 25000);
const AI_PROVIDER_ORDER = Deno.env.get("AI_PROVIDER_ORDER") || "gemini_first";
const MAX_AI_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 36);
const MAX_PROMPT_PAGES = Number(Deno.env.get("MAX_PROMPT_PAGES") || 40);
const SCORING_MODEL = "fixlist_archetype_playbooks_v1";

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

const LOW_VALUE_PATTERNS = ["/actualites/", "/news/", "/blog/", "/archive/", "/archives/", "/tag/", "/tags/", "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag="];
const INTERNAL_ROUTE_PATTERNS = ["/admin", "/developer", "/assistant", "/billing", "/login", "/register", "/forgot-password", "/reset-password", "/dashboard", "/issues", "/reports", "/crawl-status", "/metadata", "/canonicals", "/redirects", "/js-rendering", "/competitors", "/account", "/my-account", "/cart", "/checkout"];
const TRUST_PAGE_PATTERNS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv", "/conditions"];

const STRUCTURAL_RULES = new Set(["broken_page", "404_error", "410_error", "server_error", "blocked_page", "blocked_page_429", "redirect_loop", "canonical_missing", "canonical_to_other_domain", "canonical_to_other_url", "mobile_setup", "performance_hint", "js_rendering", "client_rendering", "internal_link", "duplicate_route_casing", "free_base44_subdomain", "route_boundary_candidate_indexable", "internal_route_indexable"]);
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
    moneyPatterns: ["/energie", "/énergie", "/electricite", "/electricite", "/gaz", "/comparateur", "/simulation", "/simulateur", "/devis", "/tarif", "/fournisseur", "/contrat", "/souscription"],
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
    keywords: ["product", "produit", "shop", "boutique", "cart", "panier", "checkout", "price", "prix", "sku", "collection", "category", "marque", "brand", "size", "variant", "shipping", "livraison"],
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

    if (!websiteUrl || canonicalFixes.length === 0) return Response.json({ success: true, ai_provider: "scanner_fallback", ai_review_warning: !websiteUrl ? "AI review ran, but website_url was missing. Scanner recommendations are shown." : "AI review ran, but no scanner recommendations were provided.", ...fallbackPlan });

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
  const response = await withTimeout(fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY }, body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: prompt }] }], generationConfig: { temperature: 0.1, maxOutputTokens: 7000, responseMimeType: "application/json", responseSchema: schema } }) }), GEMINI_AI_TIMEOUT_MS, "Gemini AI review");
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
  const pageText = safePages.slice(0, 180).map((page) => [page?.url, page?.final_url, page?.title, page?.h1, page?.meta_description, page?.page_template_family, page?.estimated_page_intent, (page?.conversion_signals || []).join(" "), (page?.trust_signals || []).join(" ")].join(" ")).join(" ").toLowerCase();
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
  return { primary_archetype: primary, secondary_archetype: secondary, archetype_label: playbook.label, vertical: primary, vertical_label: playbook.label, vertical_confidence: Number(confidence.toFixed(2)), business_model: detectBusinessModel(bodyText, primary), size_band: Math.max(pagesFound, pagesCrawled, safePages.length) >= 1000 ? "enterprise" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 150 ? "mid_market" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 30 ? "smb" : "micro", pages_found: pagesFound, pages_crawled: pagesCrawled, sampled_pages_sent_to_ai: getFirstNumber([body?.scan_coverage?.sampled_pages_sent_to_ai, safePages.length]), localization: detectLocalization(safePages, websiteUrl), render_mode: detectRenderMode(body, safePages), regulatory_sensitivity: ["finance_insurance_lead_gen", "utilities_comparison_lead_gen", "wine_regulated_commerce"].includes(primary) ? "trust_or_regulated" : "standard", likely_money_page_patterns: playbook.moneyPatterns, archetype_priority_pages: playbook.priorityPages, archetype_priority_issues: playbook.priorityIssues, archetype_demotions: playbook.demote, route_boundary_count: routeBoundaryCount, route_boundary_risk: routeBoundaryRisk, free_base44_subdomain: hostname.endsWith(".base44.app"), scoring_model: SCORING_MODEL };
}

function detectBusinessModel(text, archetype) {
  if (hasAny(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"])) return "quote_or_comparison_lead_gen";
  if (hasAny(text, ["booking", "reservation", "réservation", "availability", "calendar", "book now", "ticket", "stage", "pass"])) return "booking_or_reservation";
  if (hasAny(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart"])) return "catalog_or_ecommerce";
  if (hasAny(text, ["login", "dashboard", "subscription", "billing", "admin"])) return "saas_or_member_app";
  if (["finance_insurance_lead_gen", "utilities_comparison_lead_gen"].includes(archetype)) return "regulated_or_trust_lead_generation";
  if (archetype === "booking_experiences_marketplace") return "booking_or_reservation";
  if (["ecommerce_specialty_retail", "wine_regulated_commerce"].includes(archetype)) return "catalog_or_ecommerce";
  if (archetype === "local_service_brochure") return "local_lead_generation";
  return "content_or_general_business";
}

function detectLocalization(pages, websiteUrl) {
  const text = [websiteUrl, ...pages.slice(0, 100).map((page) => page?.url || page?.final_url || "")].join(" ").toLowerCase();
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

function getArchetypePlaybook(key) { return ARCHETYPE_PLAYBOOKS[key] || ARCHETYPE_PLAYBOOKS.general; }

function buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint, playbook }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const fixes = [];
  const hostname = safeHostname(websiteUrl);
  if (hostname.endsWith(".base44.app")) fixes.push(makeSyntheticFix({ rule: "free_base44_subdomain", category: "indexability", priority: "high", title: "Move production SEO to a custom domain", explanation: "The site is on a free Base44 subdomain. That can be crawled, but it is not the strongest production SEO or trust setup.", why: "A custom domain improves brand trust, shareability, Search Console ownership, and company-specific search signals.", recommendation: "Connect a branded custom domain before treating this as the long-term production SEO home.", affectedPages: ["/"], difficulty: "developer", source: "archetype_strategy_layer" }));

  const routePages = safePages.filter((page) => (isRouteBoundaryCandidate(page?.url || page?.final_url) || isInternalAppRoute(page?.url || page?.final_url)) && pageIsIndexable(page));
  if (routePages.length > 0) fixes.push(makeSyntheticFix({ rule: "route_boundary_candidate_indexable", category: "indexability", priority: "critical", title: "Keep checkout, login, account, and app routes out of search", explanation: "FixList found checkout, login, account, dashboard, billing, cart, admin, or app-like routes that appear crawlable and indexable.", why: "These pages are usually not useful SEO landing pages. Letting them appear in search can dilute the site, confuse prospects, or expose private product structure.", recommendation: "Ask your web person to require login, add noindex, or keep these routes out of public search while preserving true public landing, category, product, booking, and help pages.", affectedPages: routePages.map((page) => cleanPath(page?.url || page?.final_url || "/")).slice(0, 80), difficulty: "developer", source: "archetype_route_boundary_layer" }));

  const paths = safePages.map((page) => cleanPath(page?.url || page?.final_url || "").toLowerCase());
  const hasTrustPage = TRUST_PAGE_PATTERNS.some((pattern) => paths.some((path) => path.startsWith(pattern)));
  const trustSensitive = siteFingerprint.regulatory_sensitivity !== "standard" || siteFingerprint.primary_archetype === "saas_app_membership" || siteFingerprint.free_base44_subdomain;
  if (!hasTrustPage && safePages.length >= 4 && trustSensitive) fixes.push(makeSyntheticFix({ rule: "missing_trust_pages", category: "schema", priority: siteFingerprint.regulatory_sensitivity !== "standard" ? "high" : "medium", title: "Add public trust pages", explanation: `For a ${playbook.label} site, visitors and crawlers need clear trust, legal, contact, and ownership signals.`, why: "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.", recommendation: "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.", affectedPages: ["/"], difficulty: "moderate", source: "archetype_trust_layer" }));

  const repeatedThin = findRepeatedSnapshotGroups(safePages);
  if (repeatedThin.length > 0) fixes.push(makeSyntheticFix({ rule: "thin_repetitive_public_snapshots", category: "thin_content", priority: "high", title: "Reduce thin repetitive public snapshots", explanation: "Several public routes appear to return very similar titles, headings, or short descriptions.", why: "A technically crawlable page is not automatically useful to index. Thin repeated snapshots can dilute important business pages.", recommendation: "Keep internal/app pages private or noindex and add richer route-specific content only to pages meant to rank or convert.", affectedPages: repeatedThin.slice(0, 80), difficulty: "moderate", source: "archetype_strategy_layer" }));
  return fixes;
}

function makeSyntheticFix({ rule, category, priority, title, explanation, why, recommendation, affectedPages, difficulty, source }) {
  const page = affectedPages?.[0] || "/";
  const id = stableId(`synthetic|${rule}|${page}|${title}`);
  return { id, fix_id: id, type: "site_level", rule, category, customer_category: friendlyCategory(category), issue_title: title, title, plain_english_explanation: explanation, plain_english_summary: explanation, why_it_matters: why, current_value: "Detected from crawl, route patterns, and archetype playbook.", recommended_value: recommendation, ai_recommendation: recommendation, priority, difficulty, status: difficulty === "developer" ? "needs_developer" : "needs_approval", can_auto_fix: false, requires_approval: difficulty !== "developer", requires_developer: difficulty === "developer", affected_pages: affectedPages || [page], page_url: page, confidence_score: 92, what_to_do: defaultSteps({ category, difficulty, recommendedValue: recommendation }), what_to_do_steps: defaultSteps({ category, difficulty, recommendedValue: recommendation }), fix_steps: defaultSteps({ category, difficulty, recommendedValue: recommendation }), who_can_do_this: defaultOwner(difficulty), estimated_time: defaultTime(difficulty), time_estimate: defaultTime(difficulty), source: source || "archetype_strategy_layer" };
}

function prepareFixes(rawFixes, siteFingerprint, body, playbook) {
  const normalized = dedupeByFixId((Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) => normalizeFix(fix, index)));
  const scored = normalized.map((fix) => scoreFixForSite(fix, siteFingerprint, body, playbook));
  return groupRepeatedIssues(groupTemplateIssues(scored)).sort(compareFixes).slice(0, 90);
}

function normalizeFix(fix, index) {
  const rule = cleanString(fix?.rule || fix?.type || fix?.issue_type || "");
  const category = CATEGORY_MAP[fix?.category] || CATEGORY_MAP[rule] || fix?.category || inferCategory(rule, fix);
  const pageUrl = cleanPath(fix?.page_url || fix?.url || fix?.affected_pages?.[0] || fix?.pages?.[0] || "/");
  const affected = normalizeAffectedPages(fix, pageUrl);
  const id = cleanString(fix?.id || fix?.fix_id || fix?.fingerprint) || stableId(`${rule}|${category}|${pageUrl}|${index}`);
  const difficulty = normalizeDifficulty(fix);
  const developerOwned = needsDeveloperOwner({ ...fix, rule, category, difficulty });
  return { ...fix, id, fix_id: id, rule: rule || category || "review", category, customer_category: fix?.customer_category || friendlyCategory(category), issue_title: cleanString(fix?.issue_title || fix?.title) || defaultTitle(category), title: cleanString(fix?.title || fix?.issue_title) || defaultTitle(category), plain_english_explanation: cleanString(fix?.plain_english_explanation || fix?.explanation || fix?.summary || fix?.description) || "This recommendation was found during the website scan.", plain_english_summary: cleanString(fix?.plain_english_summary || fix?.plain_english_explanation || fix?.explanation) || "", why_it_matters: cleanString(fix?.why_it_matters || fix?.why || fix?.impact) || "Improving this can help visitors and search engines understand the site more clearly.", recommended_value: cleanString(fix?.recommended_value || fix?.recommendation || fix?.ai_recommendation || fix?.suggested_fix) || "Review and improve this item.", ai_recommendation: cleanString(fix?.ai_recommendation || fix?.recommendation || fix?.recommended_value || fix?.suggested_fix) || "Review and improve this item.", page_url: pageUrl, affected_pages: affected, source_pages: Array.isArray(fix?.source_pages) ? fix.source_pages.slice(0, 20) : [], link_text_samples: Array.isArray(fix?.link_text_samples) ? fix.link_text_samples.slice(0, 10) : [], url_confidence: fix?.url_confidence || "", url_suspicion_reasons: Array.isArray(fix?.url_suspicion_reasons) ? fix.url_suspicion_reasons.slice(0, 8) : [], priority: normalizePriority(fix?.priority), difficulty: developerOwned ? "developer" : difficulty, status: developerOwned ? "needs_developer" : fix?.status || (fix?.can_auto_fix ? "auto_fixed" : "needs_approval"), requires_developer: developerOwned || Boolean(fix?.requires_developer), requires_approval: developerOwned ? false : fix?.requires_approval !== false, can_auto_fix: Boolean(fix?.can_auto_fix), what_to_do: normalizeSteps(fix) || defaultSteps({ category, difficulty: developerOwned ? "developer" : difficulty, recommendedValue: fix?.recommended_value || fix?.recommendation }), what_to_do_steps: normalizeSteps(fix) || defaultSteps({ category, difficulty: developerOwned ? "developer" : difficulty, recommendedValue: fix?.recommended_value || fix?.recommendation }), who_can_do_this: developerOwned ? "your_web_person" : normalizeOwner(fix?.who_can_do_this), estimated_time: cleanString(fix?.estimated_time || fix?.time_estimate) || defaultTime(developerOwned ? "developer" : difficulty), time_estimate: cleanString(fix?.time_estimate || fix?.estimated_time) || defaultTime(developerOwned ? "developer" : difficulty), confidence_score: typeof fix?.confidence_score === "number" ? fix.confidence_score : 80 };
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
  const metaRewriteAllowed = metadataIssue && pageValue.classification === "money_page" && !["structural", "crawl_index", "semantic_schema", "content_trust", "route_boundary"].includes(defectClass) && !isImageAltIssue(fix);
  const overall = Math.round(evidenceConfidence * 0.18 + siteFitScore * 0.24 + businessImpactScore * 0.34 + reachScore * 0.14 + pageValue.score * 0.10);
  const priority = overall >= 82 || fix.priority === "critical" ? "critical" : overall >= 68 ? "high" : overall >= 44 ? "medium" : "low";
  const developerOwned = needsDeveloperOwner({ ...fix, primary_defect_class: defectClass });
  return { ...fix, priority: normalizePriority(priority), page_type: pageValue.classification, page_template_family: getTemplateFamily(pageUrl), page_value_score: pageValue.score, page_value_label: pageValue.label, primary_defect_class: defectClass, meta_rewrite_allowed: metaRewriteAllowed, meta_regeneration_gate: metadataIssue ? (metaRewriteAllowed ? "allowed_metadata_is_primary_gap" : "blocked_metadata_not_primary_gap") : "not_metadata", business_importance: pageValue.classification, evidence_confidence: evidenceConfidence, site_fit_score: siteFitScore, business_impact_score: businessImpactScore, reach_score: reachScore, overall_priority_score: Math.max(0, Math.min(100, overall)), site_fingerprint_vertical: siteFingerprint.primary_archetype, archetype_label: siteFingerprint.archetype_label, requires_developer: developerOwned || fix.requires_developer, difficulty: developerOwned ? "developer" : fix.difficulty, status: developerOwned ? "needs_developer" : fix.status, who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this };
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
  if (hasAny(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "pricing", "demo", "signup", "product", "collection", "checkout"])) { score += 22; reasons.push("conversion, commerce, or lead page"); }
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
  const text = `${rule} ${category} ${fix?.issue_title || ""} ${fix?.title || ""}`.toLowerCase();
  if (rule.includes("route_boundary") || rule.includes("internal_route") || hasAny(text, ["login", "account", "checkout", "dashboard", "noindex", "indexability"])) return "crawl_index";
  if (STRUCTURAL_RULES.has(rule) || STRUCTURAL_RULES.has(category) || hasAny(text, ["javascript", "render", "canonical", "redirect", "blocked", "429", "500", "404"])) return "structural";
  if (SEMANTIC_RULES.has(rule) || SEMANTIC_RULES.has(category) || text.includes("schema") || text.includes("structured")) return "semantic_schema";
  if (CONTENT_TRUST_RULES.has(rule) || CONTENT_TRUST_RULES.has(category) || hasAny(text, ["trust", "privacy", "terms", "legal", "about", "contact", "review", "methodology"])) return "content_trust";
  if (isImageAltIssue(fix)) return "image_accessibility";
  if (METADATA_RULES.has(rule) || METADATA_RULES.has(category) || hasAny(text, ["meta", "title", "description"])) return "metadata";
  return "general";
}

function scoreEvidenceConfidence(fix) { let score = typeof fix?.confidence_score === "number" ? fix.confidence_score : 72; if (fix?.source?.includes("scanner") || fix?.source?.includes("screaming") || fix?.source?.includes("strategy")) score += 10; if (fix?.current_value) score += 5; if (Array.isArray(fix?.affected_pages) && fix.affected_pages.length > 1) score += 5; if (fix?.url_confidence === "crawler_artifact") score -= 35; if (!fix?.page_url && (!fix?.affected_pages || fix.affected_pages.length === 0)) score -= 15; return Math.max(0, Math.min(100, Math.round(score))); }
function scoreReach(fix) { const count = Array.isArray(fix?.affected_pages) ? fix.affected_pages.length : 1; return Math.max(5, Math.min(100, count * 12)); }
function scoreSiteFit(fix, pageValue, siteFingerprint, defectClass, playbook) { let score = 45 + pageValue.score * 0.45; const text = `${fix?.category || ""} ${fix?.rule || ""} ${fix?.issue_title || ""} ${fix?.page_url || ""}`.toLowerCase(); if ((playbook.priorityIssues || []).some((item) => hasAny(text, String(item).split(/\s+/)))) score += 18; if (siteFingerprint.regulatory_sensitivity !== "standard" && ["content_trust", "semantic_schema", "crawl_index"].includes(defectClass)) score += 18; if (["structural", "crawl_index", "semantic_schema", "content_trust"].includes(defectClass)) score += 12; if (fix?.url_confidence === "crawler_artifact") score -= 30; return Math.max(0, Math.min(100, Math.round(score))); }
function scoreBusinessImpact(fix, pageValue, siteFingerprint, defectClass) { let score = pageValue.score; if (isSevereIssue(fix)) score += 25; if (isCosmeticIssue(fix)) score -= pageValue.classification === "low_value" ? 25 : pageValue.classification === "support_content" ? 12 : 5; if (pageValue.classification === "internal_or_auth_route" && defectClass === "crawl_index") score += 35; if (["structural", "crawl_index"].includes(defectClass)) score += 18; if (defectClass === "semantic_schema" && pageValue.classification === "money_page") score += 15; if (defectClass === "content_trust" && siteFingerprint.regulatory_sensitivity !== "standard") score += 18; if (fix?.url_confidence === "crawler_artifact") score -= 40; return Math.max(0, Math.min(100, Math.round(score))); }

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
  const safeFixes = Array.isArray(fixes) ? fixes : [];
  const highPriorityCount = safeFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length;
  const grade = scoreToGrade(score);
  const routeBoundaryText = siteFingerprint?.route_boundary_risk === "high" ? " FixList also found a high route-boundary risk, meaning internal, checkout, account, or app pages may be exposed to crawlers." : "";
  const topConcerns = safeFixes.slice(0, 4).map((fix) => ({ title: fix.issue_title, plain_english_explanation: fix.plain_english_explanation, why_it_matters: fix.why_it_matters, affected_area: Array.isArray(fix.affected_pages) && fix.affected_pages.length > 1 ? `${fix.affected_pages.length} pages` : fix.affected_pages?.[0] || "Website" }));
  const quickWins = safeFixes.filter((fix) => fix.difficulty !== "developer").slice(0, 4).map((fix) => ({ title: fix.issue_title, action: Array.isArray(fix.what_to_do) && fix.what_to_do.length > 0 ? fix.what_to_do[0] : "Review and update this item.", expected_benefit: fix.why_it_matters }));
  const biggerProjects = safeFixes.filter((fix) => fix.difficulty === "developer").slice(0, 4).map((fix) => ({ title: fix.issue_title, who_should_handle: "Your web person", why: fix.why_it_matters }));
  const limitations = [];
  if (Array.isArray(body?.crawl_warnings)) limitations.push(...body.crawl_warnings.slice(0, 3));
  if (siteFingerprint?.vertical_confidence < 0.55) limitations.push("The site type was not fully clear, so FixList used a conservative priority model.");
  return { health_score: score, health_grade: grade, overall_explanation: [`Your website health is ${grade.toLowerCase()} with a score of ${score}/100.`, `FixList recognized this as ${siteFingerprint?.archetype_label || "this type of site"} and used the ${playbook.label} playbook to prioritize ${playbook.priorityPages.slice(0, 4).join(", ")}.`, safePages.length > 0 ? `The scanner reviewed ${siteFingerprint?.pages_crawled || safePages.length} pages.` : "", highPriorityCount > 0 ? `There ${highPriorityCount === 1 ? "is" : "are"} ${highPriorityCount} high-priority item${highPriorityCount === 1 ? "" : "s"} to look at first.` : "There are no major emergency issues from this scan, but there are still useful improvements to make.", routeBoundaryText].filter(Boolean).join(" "), what_is_working: positiveFindings.length > 0 ? positiveFindings : ["The scan completed and found pages that can be reviewed."], top_concerns: topConcerns, quick_wins: quickWins, bigger_projects: biggerProjects, competitor_takeaways: [], limitations, next_best_step: safeFixes[0]?.issue_title || "Review the first recommendation and rescan after making changes." };
}

function makeFrontendCompatible(plan) {
  const cleanedFixes = Array.isArray(plan.cleaned_fixes) ? plan.cleaned_fixes : [];
  const pages = Array.isArray(plan.crawled_pages) ? plan.crawled_pages : Array.isArray(plan.pages) ? plan.pages : [];
  const score = typeof plan.health_score === "number" ? plan.health_score : calculateFallbackScore(cleanedFixes);
  const websiteHealthReport = plan.website_health_report || buildFallbackHealthReport({ body: plan, pages, fixes: cleanedFixes, score, positiveFindings: plan.positive_findings || [], siteFingerprint: plan.site_fingerprint || {}, playbook: getArchetypePlaybook(plan.site_fingerprint?.primary_archetype || "general") });
  const topRecommendedActions = Array.isArray(plan.top_recommended_actions) && plan.top_recommended_actions.length > 0 ? fillTopActions(plan.top_recommended_actions, cleanedFixes) : buildTopActions(cleanedFixes);
  const recommendedActions = Array.isArray(plan.recommended_actions) && plan.recommended_actions.length > 0 ? plan.recommended_actions : topRecommendedActions.map((action) => { const fix = cleanedFixes.find((item) => item.id === action.fix_id || item.fix_id === action.fix_id); return { fix_id: action.fix_id || fix?.id || "", title: action.title || fix?.issue_title || "Recommended action", plain_english_summary: fix?.plain_english_explanation || action.reason || "", why_it_matters: fix?.why_it_matters || action.reason || "", what_to_do_steps: action.what_to_do_steps || fix?.what_to_do || [], who_can_do_this: action.who_can_do_this || (fix?.who_can_do_this === "your_web_person" ? "Your web person" : "You"), time_estimate: action.time_estimate || fix?.estimated_time || "", priority: action.priority || fix?.priority || "medium", affected_pages: action.affected_pages || fix?.affected_pages || [] }; });
  return { ...plan, success: true, health_score: score, website_health_report: websiteHealthReport, health_explanation: websiteHealthReport.overall_explanation, customer_summary: websiteHealthReport.overall_explanation, cleaned_fixes: cleanedFixes, raw_fixes: cleanedFixes, fixes: cleanedFixes, findings: cleanedFixes, recommendations: cleanedFixes, top_recommended_actions: topRecommendedActions, recommended_actions: recommendedActions, competitor_insights: [], crawled_pages: pages, pages, scan_summary: { score, status_label: websiteHealthReport.health_grade, plain_english_summary: websiteHealthReport.overall_explanation || plan.plain_english_summary || "The scan completed. Review the recommended improvements below.", pages_scanned: plan.site_fingerprint?.pages_crawled || pages.length, pages_failed: pages.filter((page) => { const status = Number(page?.status_code || 0); return status >= 400 || status === 0 || page?.fetch_error; }).length, high_priority_count: cleanedFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length, technical_issue_count: cleanedFixes.length, site_fingerprint: plan.site_fingerprint || {}, website_health_report: websiteHealthReport } };
}

function mergeAiIntoFallback({ aiResponse, fallbackPlan, canonicalFixes, pages, body, siteFingerprint, playbook }) {
  const validIds = new Set(canonicalFixes.map((fix) => fix.id));
  const rewrites = new Map();
  for (const rewrite of aiResponse?.fix_rewrites || []) if (rewrite?.fix_id && validIds.has(rewrite.fix_id)) rewrites.set(rewrite.fix_id, rewrite);
  const cleanedFixes = canonicalFixes.map((fix) => {
    const rewrite = rewrites.get(fix.id);
    if (!rewrite) return fix;
    const steps = Array.isArray(rewrite.what_to_do) && rewrite.what_to_do.length > 0 ? rewrite.what_to_do.slice(0, 5).map((step) => String(step).trim()).filter(Boolean) : fix.what_to_do;
    const requestedOwner = rewrite.who_can_do_this === "you" || rewrite.who_can_do_this === "your_web_person" ? rewrite.who_can_do_this : fix.who_can_do_this;
    const forcedDeveloper = needsDeveloperOwner({ ...fix, ...rewrite, what_to_do: steps });
    return { ...fix, issue_title: cleanString(rewrite.issue_title) || fix.issue_title, title: cleanString(rewrite.issue_title) || fix.title || fix.issue_title, plain_english_explanation: cleanString(rewrite.plain_english_explanation) || fix.plain_english_explanation, plain_english_summary: cleanString(rewrite.plain_english_explanation) || fix.plain_english_summary || fix.plain_english_explanation, why_it_matters: cleanString(rewrite.why_it_matters) || fix.why_it_matters, what_to_do: steps, what_to_do_steps: steps, fix_steps: steps, who_can_do_this: forcedDeveloper ? "your_web_person" : requestedOwner, difficulty: forcedDeveloper ? "developer" : fix.difficulty, status: forcedDeveloper ? "needs_developer" : fix.status, requires_developer: forcedDeveloper || fix.requires_developer, estimated_time: cleanString(rewrite.estimated_time) || fix.estimated_time, time_estimate: cleanString(rewrite.estimated_time) || fix.time_estimate, ai_recommendation: steps.length > 0 ? steps.join(" ") : fix.ai_recommendation };
  }).sort(compareFixes);
  const aiTopActions = Array.isArray(aiResponse?.top_recommended_actions) ? aiResponse.top_recommended_actions.map((action) => hydrateTopAction(action, cleanedFixes)).filter((action) => action.title) : [];
  const topRecommendedActions = fillTopActions(aiTopActions, cleanedFixes);
  const positives = Array.isArray(aiResponse?.positive_findings) && aiResponse.positive_findings.length > 0 ? aiResponse.positive_findings.slice(0, 5).map((item) => String(item)) : fallbackPlan.positive_findings;
  const healthReport = normalizeAiHealthReport({ aiReport: aiResponse?.website_health_report, fallbackReport: fallbackPlan.website_health_report, score: fallbackPlan.health_score, fixes: cleanedFixes, pages, body, positives, siteFingerprint, playbook });
  return makeFrontendCompatible({ ...fallbackPlan, plain_english_summary: cleanString(aiResponse?.plain_english_summary) || healthReport.overall_explanation || fallbackPlan.plain_english_summary, website_health_report: healthReport, health_explanation: healthReport.overall_explanation, customer_summary: healthReport.overall_explanation, top_recommended_actions: topRecommendedActions, cleaned_fixes: cleanedFixes, raw_fixes: cleanedFixes, fixes: cleanedFixes, findings: cleanedFixes, recommendations: cleanedFixes, competitor_insights: [], positive_findings: positives, ai_rewrites_applied: rewrites.size, crawled_pages: pages, pages, site_fingerprint: siteFingerprint, archetype_playbook: publicPlaybook(playbook) });
}

function buildPrompt({ body, websiteUrl, pages, canonicalFixes, fallbackPlan, siteFingerprint, playbook }) {
  return `You are the AI planning layer for FixList.

The deterministic scanner already found evidence. Rewrite and explain recommendations in plain English, while preserving exact fix_id values.

Core instruction: Create a site-aware SEO plan. Do not treat every SEO issue equally. Prioritize by evidence confidence, site-fit, business impact, affected-page reach, route intent, and whether the page should actually be indexable.

Archetype playbook:
${JSON.stringify(publicPlaybook(playbook), null, 2)}

Use the playbook as priority context only. Do not mention competitor or benchmark sites unless the user supplied competitor URLs. Use it to decide which pages and defects matter most for this business model.

Hard rules:
1. Do not invent findings, URLs, rankings, traffic, leads, revenue, or fixes.
2. Do not say anything has already been fixed or published.
3. Only rewrite findings using exact fix_id values provided.
4. what_to_do must contain 2 to 5 short action steps.
5. who_can_do_this must be either "you" or "your_web_person".
6. Use plain English for a non-technical business owner.
7. Focus top actions on archetype-critical pages: leads, sales, bookings, quotes, product discovery, comparison/simulation, trust, or safe indexation.
8. News, blog, tag, feed, pagination, and old archive pages must not dominate top priorities unless the playbook says content is the core product.
9. Internal/auth/app/checkout/account routes should usually be sampled for route-boundary evidence but private or noindex. Prioritize route-boundary issues above metadata polishing.
10. Duplicate route casing is a canonical/indexation issue, not a cosmetic issue.
11. A technically crawlable page is not automatically strategically useful to index.
12. Metadata rewriting is gated. Only recommend title/meta-description rewrites when metadata is the primary gap for that page type.
13. Image alt text is not metadata. Treat it as accessibility/image context, not as page title/description cleanup.
14. Group repeated blocked, 404, 410, 429, 500, or template failures. Do not create dozens of identical product/page tasks.
15. For regulated, finance, insurance, utilities, wine/alcohol, SaaS, or trust-sensitive sites, prioritize trust pages, clarity, route boundaries, indexability, canonicalization, and key conversion pages.
16. Always return up to 5 top_recommended_actions when enough findings exist.

Site fingerprint:
${JSON.stringify(siteFingerprint, null, 2)}

Business:
${JSON.stringify({ business_name: body?.business_name || "", business_type: body?.business_type || "", city: body?.city || "", country: body?.country || "", language: body?.language || "", website_url: websiteUrl, scan_mode: body?.scan_mode || "", important_keywords: body?.important_keywords || [], business_priority_instruction: body?.business_priority_instruction || null, scan_coverage: body?.scan_coverage || null }, null, 2)}

Scan totals:
${JSON.stringify({ pages_scanned_sample_sent_to_ai: Array.isArray(pages) ? pages.length : 0, health_score: fallbackPlan.health_score, pages_found: siteFingerprint.pages_found || body?.pages_found || 0, pages_crawled: siteFingerprint.pages_crawled || body?.pages_crawled || 0, queued_remaining: body?.queued_remaining || 0, crawl_scope: body?.crawl_scope || null }, null, 2)}

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
  return { type: "object", properties: { plain_english_summary: { type: "string" }, website_health_report: { type: "object", properties: { health_score: { type: "number" }, health_grade: { type: "string" }, overall_explanation: { type: "string" }, what_is_working: { type: "array", items: { type: "string" } }, top_concerns: { type: "array", items: { type: "object", properties: { title: { type: "string" }, plain_english_explanation: { type: "string" }, why_it_matters: { type: "string" }, affected_area: { type: "string" } }, required: ["title", "plain_english_explanation"] } }, quick_wins: { type: "array", items: { type: "object", properties: { title: { type: "string" }, action: { type: "string" }, expected_benefit: { type: "string" } }, required: ["title", "action"] } }, bigger_projects: { type: "array", items: { type: "object", properties: { title: { type: "string" }, who_should_handle: { type: "string" }, why: { type: "string" } }, required: ["title", "who_should_handle"] } }, competitor_takeaways: { type: "array", items: { type: "string" } }, limitations: { type: "array", items: { type: "string" } }, next_best_step: { type: "string" } }, required: ["health_score", "health_grade", "overall_explanation", "what_is_working", "top_concerns", "quick_wins", "bigger_projects", "competitor_takeaways", "limitations", "next_best_step"] }, top_recommended_actions: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, title: { type: "string" }, reason: { type: "string" }, priority: { type: "string", enum: ["high", "medium", "low"] } }, required: ["title", "reason", "priority"] } }, fix_rewrites: { type: "array", items: { type: "object", properties: { fix_id: { type: "string" }, issue_title: { type: "string" }, plain_english_explanation: { type: "string" }, why_it_matters: { type: "string" }, what_to_do: { type: "array", items: { type: "string" } }, who_can_do_this: { type: "string", enum: ["you", "your_web_person"] }, estimated_time: { type: "string" } }, required: ["fix_id", "issue_title", "plain_english_explanation", "why_it_matters", "what_to_do", "who_can_do_this", "estimated_time"] } }, competitor_insights: { type: "array", items: { type: "object", properties: {} } }, positive_findings: { type: "array", items: { type: "string" } } }, required: ["plain_english_summary", "website_health_report", "top_recommended_actions", "fix_rewrites", "competitor_insights", "positive_findings"] };
}

function compactFixForPrompt(fix) { return { fix_id: fix.fix_id || fix.id, rule: fix.rule, category: fix.category, title: fix.issue_title, priority: fix.priority, page_url: fix.page_url, affected_pages: fix.affected_pages?.slice(0, 8) || [], source_pages: fix.source_pages?.slice(0, 5) || [], link_text_samples: fix.link_text_samples?.slice(0, 5) || [], url_confidence: fix.url_confidence || "", url_suspicion_reasons: fix.url_suspicion_reasons || [], why_it_matters: fix.why_it_matters, recommended_value: fix.recommended_value, page_type: fix.page_type, page_template_family: fix.page_template_family, primary_defect_class: fix.primary_defect_class, meta_rewrite_allowed: fix.meta_rewrite_allowed, meta_regeneration_gate: fix.meta_regeneration_gate, page_value_score: fix.page_value_score, page_value_label: fix.page_value_label, business_importance: fix.business_importance, evidence_confidence: fix.evidence_confidence, site_fit_score: fix.site_fit_score, business_impact_score: fix.business_impact_score, reach_score: fix.reach_score, overall_priority_score: fix.overall_priority_score, archetype_label: fix.archetype_label }; }
function buildPageProfile(pages) { const safePages = Array.isArray(pages) ? pages : []; return safePages.slice(0, MAX_PROMPT_PAGES).map((page) => ({ url: cleanPath(page?.url || page?.final_url || ""), title: clampText(page?.title || "", 120), h1: clampText(page?.h1 || "", 100), status_code: Number(page?.status_code || 0), indexable: page?.indexable !== false, word_count: Number(page?.word_count || 0), in_sitemap: Boolean(page?.in_sitemap), discovered_from: Array.isArray(page?.discovered_from) ? page.discovered_from.slice(0, 4) : [], url_confidence: page?.url_confidence || "", page_template_family: page?.page_template_family || "", estimated_page_intent: page?.estimated_page_intent || "", route_boundary_candidate: Boolean(page?.route_boundary_candidate), route_boundary_type: page?.route_boundary_type || "" })); }
function publicPlaybook(playbook) { return { label: playbook.label, priority_pages: playbook.priorityPages, priority_issues: playbook.priorityIssues, demote: playbook.demote, owner_rule: playbook.ownerRule }; }
function buildPositiveFindings({ pages, siteFingerprint }) { const positives = []; if (Array.isArray(pages) && pages.length > 0) positives.push(`The scan reviewed ${siteFingerprint?.pages_crawled || pages.length} pages.`); if (siteFingerprint?.primary_archetype && siteFingerprint.primary_archetype !== "general") positives.push(`FixList identified the site as ${siteFingerprint.archetype_label}.`); if (siteFingerprint?.likely_money_page_patterns?.length > 0) positives.push("The review can prioritize likely money pages over low-value archives."); if (siteFingerprint?.route_boundary_risk === "low") positives.push("The scan did not find an obvious high-risk route-boundary exposure pattern."); return positives.slice(0, 5); }
function buildGroupedPageRecommendations(fixes) { return (fixes || []).filter((fix) => String(fix.business_importance || "").includes("group") || (Array.isArray(fix.affected_pages) && fix.affected_pages.length > 3)).slice(0, 10).map((fix) => ({ title: fix.issue_title, priority: fix.priority, affected_pages: fix.affected_pages || [], page_count: fix.affected_pages?.length || 0, recommendation: fix.recommended_value })); }
function buildTopActions(fixes) { return fillTopActions([], fixes); }
function fillTopActions(actions, fixes) { const output = []; const seen = new Set(); for (const action of actions || []) { const id = action.fix_id || action.id || action.title; if (!id || seen.has(id)) continue; seen.add(id); output.push(action); } for (const fix of fixes || []) { const id = fix.fix_id || fix.id; if (!id || seen.has(id)) continue; seen.add(id); output.push(fixToAction(fix)); if (output.length >= 5) break; } return output.slice(0, 5); }
function hydrateTopAction(action, fixes) { const fix = fixes.find((item) => item.id === action?.fix_id || item.fix_id === action?.fix_id); if (!fix) return { fix_id: action?.fix_id || "", title: cleanString(action?.title) || "Recommended action", reason: cleanString(action?.reason) || "Review this recommendation.", priority: ["high", "medium", "low"].includes(action?.priority) ? action.priority : "medium", affected_pages: [], what_to_do_steps: [], who_can_do_this: "You", time_estimate: "" }; return { ...fixToAction(fix), title: cleanString(action?.title) || fix.issue_title, reason: cleanString(action?.reason) || fix.why_it_matters, plain_english_summary: fix.plain_english_explanation, why_it_matters: cleanString(action?.reason) || fix.why_it_matters, priority: ["high", "medium", "low"].includes(action?.priority) ? action.priority : fix.priority === "critical" || fix.priority === "high" ? "high" : fix.priority === "low" ? "low" : "medium" }; }
function fixToAction(fix) { return { fix_id: fix.fix_id || fix.id, title: fix.issue_title, reason: fix.why_it_matters, priority: fix.priority === "critical" || fix.priority === "high" ? "high" : fix.priority === "low" ? "low" : "medium", plain_english_summary: fix.plain_english_explanation, why_it_matters: fix.why_it_matters, what_to_do_steps: fix.what_to_do_steps || fix.what_to_do || [], who_can_do_this: fix.who_can_do_this === "your_web_person" ? "Your web person" : "You", time_estimate: fix.time_estimate || fix.estimated_time || "", affected_pages: fix.affected_pages || [], page_url: fix.page_url || "" }; }
function normalizeAiHealthReport({ aiReport, fallbackReport, score, fixes, pages, body, positives, siteFingerprint, playbook }) { const fallback = fallbackReport || buildFallbackHealthReport({ body, pages, fixes, score, positiveFindings: positives, siteFingerprint, playbook }); if (!aiReport || typeof aiReport !== "object") return fallback; return { health_score: typeof aiReport.health_score === "number" ? Math.max(0, Math.min(100, Math.round(aiReport.health_score))) : fallback.health_score, health_grade: cleanString(aiReport.health_grade) || fallback.health_grade, overall_explanation: cleanString(aiReport.overall_explanation) || fallback.overall_explanation, what_is_working: cleanStringArray(aiReport.what_is_working, 5).length ? cleanStringArray(aiReport.what_is_working, 5) : fallback.what_is_working, top_concerns: normalizeHealthCards(aiReport.top_concerns, fallback.top_concerns, 4), quick_wins: normalizeHealthCards(aiReport.quick_wins, fallback.quick_wins, 4), bigger_projects: normalizeHealthCards(aiReport.bigger_projects, fallback.bigger_projects, 4), competitor_takeaways: [], limitations: cleanStringArray(aiReport.limitations, 5).length ? cleanStringArray(aiReport.limitations, 5) : fallback.limitations, next_best_step: cleanString(aiReport.next_best_step) || fallback.next_best_step }; }
function normalizeHealthCards(value, fallback, limit) { if (!Array.isArray(value) || value.length === 0) return fallback || []; return value.slice(0, limit).map((item) => typeof item === "string" ? { title: item, plain_english_explanation: "", why_it_matters: "" } : { title: cleanString(item?.title) || cleanString(item?.headline) || "", plain_english_explanation: cleanString(item?.plain_english_explanation) || cleanString(item?.explanation) || cleanString(item?.action) || "", why_it_matters: cleanString(item?.why_it_matters) || cleanString(item?.why) || cleanString(item?.expected_benefit) || "", affected_area: cleanString(item?.affected_area) || cleanString(item?.who_should_handle) || "" }).filter((item) => item.title); }
function cleanStringArray(value, limit) { if (!Array.isArray(value)) return []; return value.slice(0, limit).map((item) => cleanString(item)).filter(Boolean); }

function pickFirstNonEmptyArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function normalizeAffectedPages(fix, fallbackPage) { const rawPages = Array.isArray(fix?.affected_pages) ? fix.affected_pages : Array.isArray(fix?.pages) ? fix.pages : fix?.page_url ? [fix.page_url] : [fallbackPage]; return Array.from(new Set(rawPages.map((item) => cleanPath(item)).filter(Boolean))).slice(0, 150); }
function normalizeSteps(fix) { for (const value of [fix?.what_to_do, fix?.what_to_do_steps, fix?.fix_steps, fix?.steps]) if (Array.isArray(value) && value.length > 0) { const steps = value.slice(0, 5).map((item) => String(item).trim()).filter(Boolean); if (steps.length > 0) return steps; } return null; }
function dedupeByFixId(fixes) { const seen = new Set(); const output = []; for (const fix of fixes || []) { const key = String(fix?.id || fix?.fix_id || ""); if (!key || seen.has(key)) continue; seen.add(key); output.push(fix); } return output; }
function compareFixes(a, b) { const scoreDiff = Number(b?.overall_priority_score || 0) - Number(a?.overall_priority_score || 0); if (scoreDiff !== 0) return scoreDiff; const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }; const priorityDiff = (priorityOrder[a?.priority] ?? 9) - (priorityOrder[b?.priority] ?? 9); if (priorityDiff !== 0) return priorityDiff; return String(a?.issue_title || "").localeCompare(String(b?.issue_title || "")); }
function inferCategory(rule, fix) { const text = `${rule} ${fix?.title || ""} ${fix?.issue_title || ""}`.toLowerCase(); if (text.includes("schema") || text.includes("trust")) return "schema"; if (text.includes("canonical")) return "canonical"; if (text.includes("title")) return "meta_title"; if (text.includes("description") || text.includes("meta")) return "meta_description"; if (text.includes("alt")) return "image_alt_text"; if (text.includes("404") || text.includes("broken") || text.includes("blocked")) return "404_error"; if (text.includes("index") || text.includes("noindex")) return "indexability"; if (text.includes("render") || text.includes("javascript")) return "web_dev"; return "web_dev"; }
function defaultTitle(category) { const titles = { "404_error": "Fix pages that are not loading", duplicate_content: "Review duplicate or repeated pages", meta_description: "Improve search descriptions", meta_title: "Improve search titles", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", web_dev: "Review website setup", mobile_setup: "Review mobile setup", performance_hint: "Review page speed", social_metadata: "Review social sharing details", indexability: "Review indexability settings", image_alt_text: "Add useful image descriptions", canonical: "Review canonical URL setup" }; return titles[category] || "Review this recommendation"; }
function friendlyCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function defaultSteps({ category, difficulty, recommendedValue }) { if (difficulty === "developer") return ["Send this item to your web person.", "Ask them to review the affected URL, template, or route rule.", "Apply the safest fix and publish it.", "Run FixList again to confirm it is resolved."]; if (["meta_title", "meta_description", "duplicate_content"].includes(category)) return ["Open the affected page in your website editor.", recommendedValue || "Update the search title or description so it matches the page.", "Save and publish the change.", "Run FixList again after publishing."]; if (category === "image_alt_text") return ["Open the affected page or product/listing template.", "Add short, useful alt text to meaningful images.", "Leave decorative images empty.", "Publish and rescan."]; return ["Review the affected page.", recommendedValue || "Make the recommended improvement.", "Save and publish the change.", "Run FixList again after publishing."]; }
function defaultOwner(difficulty) { return difficulty === "developer" ? "your_web_person" : "you"; }
function defaultTime(difficulty) { if (difficulty === "developer") return "about 1–2 hours"; if (difficulty === "moderate") return "about 30–60 minutes"; return "about 10–30 minutes"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(priority)) return priority; return "medium"; }
function normalizeDifficulty(fix) { const value = String(fix?.difficulty || "").toLowerCase(); if (value === "developer" || fix?.requires_developer) return "developer"; if (value === "moderate") return "moderate"; return "easy"; }
function normalizeOwner(value) { const owner = String(value || "").toLowerCase(); if (owner.includes("web") || owner.includes("developer") || owner === "your_web_person") return "your_web_person"; return "you"; }
function needsDeveloperOwner(item = {}) { const value = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.reason || ""} ${item.recommendation || ""} ${item.recommended_value || ""} ${firstArray([item.what_to_do_steps, item.what_to_do]).join(" ")} ${item.who_can_do_this || ""} ${item.primary_defect_class || ""}`.toLowerCase(); if (item.requires_developer || item.difficulty === "developer" || item.status === "needs_developer" || value.includes("your_web_person")) return true; return /developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard/.test(value); }
function isMetadataIssue(fix) { const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""}`.toLowerCase(); return !isImageAltIssue(fix) && /meta|title|description|duplicate_content/.test(value); }
function isImageAltIssue(fix) { return /image_alt_text|image alt|alt text|missing alt|image description/i.test(`${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""} ${fix?.issue_title || ""}`); }
function isCosmeticIssue(fix) { const value = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""}`.toLowerCase(); return /meta|title|description|thin_content|duplicate|image_alt|alt text|h1/.test(value) && !isSevereIssue(fix); }
function isSevereIssue(fix) { return /404|410|429|500|503|blocked|server_error|redirect_loop|noindex|canonical|client_rendering|javascript|route_boundary|internal_route|indexability/.test(`${fix?.rule || ""} ${fix?.category || ""} ${fix?.title || ""} ${fix?.current_value || ""}`.toLowerCase()); }
function isRepeatedSevereCandidate(fix) { return isSevereIssue(fix) || ["404_error", "410_error", "server_error", "blocked_page_429", "client_rendering", "route_boundary_candidate_indexable"].includes(fix?.rule); }
function statusBucket(fix) { const value = `${fix?.current_value || ""} ${fix?.rule || ""}`.toLowerCase(); for (const code of ["429", "404", "410", "500", "503"]) if (value.includes(code)) return code; if (value.includes("blocked")) return "blocked"; if (value.includes("render")) return "rendering"; if (value.includes("route")) return "route_boundary"; return fix?.rule || "failed"; }
function repeatedSevereTitle(fix, family) { const bucket = statusBucket(fix); if (bucket === "429" || bucket === "blocked") return `Group blocked ${family} pages`; if (bucket === "404" || bucket === "410") return `Group confirmed missing ${family} pages`; if (bucket === "500" || bucket === "503") return `Group server errors on ${family} pages`; if (bucket === "rendering") return `Fix crawlable HTML for ${family} pages`; if (bucket === "route_boundary") return "Group route-boundary exposure checks"; return "Group repeated page loading problems"; }
function groupTemplateTitle(fix, family) { if (fix.rule?.includes("render")) return `Fix crawlable HTML for ${family} pages`; if (fix.rule?.includes("description")) return `Batch ${family} meta descriptions`; if (fix.rule?.includes("title")) return `Batch ${family} search titles`; if (fix.rule?.includes("alt")) return `Batch ${family} image descriptions`; if (fix.rule?.includes("schema")) return `Add ${family} structured data pattern`; if (fix.rule?.includes("h1")) return `Batch ${family} page headings`; return `Batch ${family} page cleanup`; }
function calculateFallbackScore(fixes) { let score = 92; for (const fix of fixes || []) { if (fix.priority === "critical") score -= 12; else if (fix.priority === "high") score -= 7; else if (fix.priority === "medium") score -= 3; else score -= 1; } return Math.max(20, Math.min(95, Math.round(score))); }
function scoreToGrade(score) { const number = Number(score || 0); if (number >= 90) return "Excellent"; if (number >= 75) return "Good"; if (number >= 55) return "Fair"; return "Needs work"; }
function pageIsIndexable(page) { const robots = String(page?.robots || page?.robots_meta || "").toLowerCase(); const status = Number(page?.status_code || 200); return page?.indexable !== false && status < 400 && !robots.includes("noindex"); }
function isRouteBoundaryCandidate(url) { const path = cleanPath(url).toLowerCase().replace(/\/$/, ""); return ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"].some((pattern) => path === pattern || path.startsWith(`${pattern}/`)); }
function isInternalAppRoute(url) { const path = cleanPath(url).toLowerCase().replace(/\/$/, ""); return INTERNAL_ROUTE_PATTERNS.some((pattern) => path === pattern || path.startsWith(`${pattern}/`)); }
function getTemplateFamily(url) { const path = cleanPath(url).toLowerCase(); if (isRouteBoundaryCandidate(path)) return "route_boundary"; if (isInternalAppRoute(path)) return "internal_app"; if (isLowValuePage(path)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/listing|show|category|categorie|collection|pass|ticket|stage|pilotage/.test(path)) return "category_listing"; if (/product|produit|\/p\//.test(path)) return "product_detail"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(path)) return "legal_info"; return "standard"; }
function isLowValuePage(url) { const path = cleanPath(url).toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; return LOW_VALUE_PATTERNS.some((pattern) => path.includes(pattern)); }
function findRepeatedSnapshotGroups(pages) { const buckets = new Map(); for (const page of pages || []) { const path = cleanPath(page?.final_url || page?.url || ""); if (!path || isInternalAppRoute(path) || isRouteBoundaryCandidate(path)) continue; const key = `${normalizeSnapshotText(page?.title || page?.h1 || "")}|${normalizeSnapshotText(page?.meta_description || "")}`; if (key.length < 18) continue; const existing = buckets.get(key) || []; existing.push(path); buckets.set(key, existing); } for (const urls of buckets.values()) if (urls.length >= 4) return urls; return []; }
function normalizeSnapshotText(value) { return String(value || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 140); }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { if (/^https?:\/\//i.test(raw)) return new URL(raw).pathname || "/"; } catch {} return raw.startsWith("/") ? raw : `/${raw}`; }
function hasAny(text, values) { const haystack = String(text || "").toLowerCase(); return values.some((value) => haystack.includes(String(value).toLowerCase())); }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function firstArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function clampText(value, max) { const text = String(value || "").trim(); return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function withTimeout(promise, timeoutMs, label) { const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs)); return Promise.race([promise, timeout]); }
