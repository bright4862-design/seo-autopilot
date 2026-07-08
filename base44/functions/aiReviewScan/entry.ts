import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const AI_REVIEW_VERSION = "aiReviewScan_v2_scanner_evidence_fixes";
const SCORING_MODEL = "fixlist_archetype_playbooks_v2_scanner_evidence_fixes";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const MAX_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 36);
const MAX_PAGES_RETURNED = Number(Deno.env.get("MAX_REVIEW_PAGES_RETURNED") || 80);

const LOW_VALUE_PATTERNS = ["/actualites/", "/news/", "/blog/", "/archive/", "/archives/", "/tag/", "/tags/", "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag="];
const INTERNAL_ROUTE_PATTERNS = ["/admin", "/developer", "/assistant", "/billing", "/login", "/register", "/forgot-password", "/reset-password", "/dashboard", "/issues", "/reports", "/crawl-status", "/metadata", "/canonicals", "/redirects", "/js-rendering", "/competitors", "/account", "/my-account", "/cart", "/checkout"];
const TRUST_PAGE_PATTERNS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv", "/conditions"];

const CATEGORY_MAP = {
  broken_page: "404_error",
  "404_error": "404_error",
  "410_error": "404_error",
  server_error: "web_dev",
  blocked_page: "web_dev",
  blocked_page_429: "web_dev",
  scanner_blocked: "web_dev",
  rate_limited_page: "web_dev",
  canonical_missing: "canonical",
  canonical_to_other_domain: "canonical",
  canonical_to_other_url: "canonical",
  duplicate_route_casing: "canonical",
  route_boundary_candidate_indexable: "indexability",
  internal_route_indexable: "indexability",
  missing_trust_pages: "schema",
  trust_signal_gap: "schema",
  schema: "schema",
  structured_data: "schema",
  image_alt_text: "image_alt_text",
  missing_meta_description: "meta_description",
  missing_title: "meta_title",
  duplicate_title: "duplicate_content",
  duplicate_meta_description: "duplicate_content",
};

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
    keywords: ["product", "produit", "shop", "boutique", "cart", "panier", "checkout", "price", "prix", "sku", "collection", "category", "marque", "brand", "variant", "shipping", "livraison", "shopify"],
    moneyPatterns: ["/products/", "/product/", "/produit/", "/collections/", "/collection/", "/category/", "/categorie/", "/shop", "/boutique", "/cart", "/checkout", "/marque"],
    priorityPages: ["product pages", "collection/category pages", "brand pages", "cart/checkout route boundaries", "shipping/returns/trust pages"],
    priorityIssues: ["product/category indexability", "product schema", "canonicalization", "blocked product pages", "template image-alt issues", "checkout/account route boundaries"],
    demote: ["old blog posts", "tag archives", "generic metadata on inactive products"],
    ownerRule: "Product schema, canonical, template, cart/checkout, and blocked-product issues usually need your_web_person. Product copy and alt text can often be you.",
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
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, error: "Unauthorized" }, 401);

    const rawBody = await req.json().catch(() => ({}));
    const body = unwrapScanPayload(rawBody);
    const websiteUrl = cleanString(body.website_url || body.normalized_url || body.url || body.technical_audit_summary?.website_url || "");
    const pages = pickFirstNonEmptyArray([body.crawled_pages, body.pages, body.scanned_pages, body.crawl_pages, body.technical_audit_summary?.pages]);
    const rawFixes = collectArrays([body.raw_fixes, body.grouped_findings, body.raw_findings, body.findings, body.fixes, body.recommendations, body.issues]);

    const siteFingerprint = buildSiteFingerprint({ body, pages, websiteUrl });
    const playbook = getArchetypePlaybook(siteFingerprint.primary_archetype);
    const evidenceFixes = buildScannerEvidenceFindings({ body, pages, websiteUrl, siteFingerprint });
    const strategicFixes = buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint, playbook });
    const canonicalFixes = prepareFixes([...rawFixes, ...evidenceFixes, ...strategicFixes], siteFingerprint, body, playbook);
    const fallbackPlan = buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint, playbook, websiteUrl });

    const warning = !websiteUrl
      ? "AI review ran, but website_url was missing. Scanner recommendations are shown."
      : canonicalFixes.length === 0
        ? "AI review ran, but no scanner recommendations were provided."
        : "";

    return jsonResponse({
      success: true,
      ai_provider: "scanner_fallback",
      ai_review_version: AI_REVIEW_VERSION,
      ai_review_warning: warning,
      ...fallbackPlan,
    });
  } catch (error) {
    console.error("aiReviewScan failed", error);
    return jsonResponse({ success: false, error: "aiReviewScan failed. Please try again." }, 500);
  }
});

function unwrapScanPayload(value) {
  let current = value || {};
  for (let i = 0; i < 5; i += 1) {
    if (typeof current === "string") current = parseJsonObject(current);
    if (looksLikeScanPayload(current)) return current;
    if (looksLikeScanPayload(current?.data)) { current = current.data; continue; }
    if (looksLikeScanPayload(current?.data?.data)) { current = current.data.data; continue; }
    if (looksLikeScanPayload(current?.payload)) { current = current.payload; continue; }
    if (looksLikeScanPayload(current?.body)) { current = current.body; continue; }
    if (looksLikeScanPayload(current?.result)) { current = current.result; continue; }
    break;
  }
  return current && typeof current === "object" ? current : {};
}

function looksLikeScanPayload(value) {
  if (!value || typeof value !== "object") return false;
  if (value.ai_provider && !value.scanner_version && !value.pages_crawled) return false;
  return Boolean(value.website_url || value.normalized_url || value.scanner_version || value.pages_crawled || value.pages_found || Array.isArray(value.pages) || Array.isArray(value.crawled_pages) || Array.isArray(value.verified_failed_pages));
}

function buildScannerEvidenceFindings({ body, pages, siteFingerprint }) {
  const evidencePages = dedupePages([
    ...collectArrays([body.verified_failed_pages, body.technical_audit_summary?.verified_failed_pages, body.url_evidence_summary?.verified_failed_pages]),
    ...(Array.isArray(pages) ? pages.filter((page) => isFailedPage(page) || isBlockedAccessPage(page)) : []),
  ]);
  const fixes = [];
  const failedByBucket = new Map();
  for (const page of evidencePages) {
    const bucket = statusBucketFromPage(page);
    if (!failedByBucket.has(bucket)) failedByBucket.set(bucket, []);
    failedByBucket.get(bucket).push(page);
  }

  for (const [bucket, group] of failedByBucket.entries()) {
    if (bucket === "429") {
      fixes.push(makeSyntheticFix({
        rule: "rate_limited_page",
        category: "web_dev",
        priority: group.length >= 3 ? "high" : "medium",
        title: group.length >= 3 ? "Check pages blocked by rate limiting" : "Verify crawler access for a rate-limited page",
        explanation: "The scanner saw HTTP 429, bot protection, or a connection-verification response. This is crawler-access evidence, not proof that customers see a broken page.",
        why: "If legitimate crawlers cannot access important pages, search engines may miss them. The fix should be verified in server, CDN, firewall, or bot-protection logs before changing page content.",
        recommendation: "Ask your web person to check server, CDN, firewall, and bot-protection logs for these URLs. Confirm whether Googlebot and normal users can access them, then adjust rate-limit rules only if legitimate access is blocked.",
        affectedPages: group.map(pageEvidenceUrl).filter(Boolean),
        difficulty: "developer",
        source: "scanner_verified_failed_pages:429",
        extra: evidenceExtra(group),
      }));
      continue;
    }

    const isServer = bucket === "5xx";
    const title = isServer ? "Fix server errors found during the crawl" : "Fix confirmed broken URLs found during the crawl";
    const explanation = isServer
      ? "The scanner found URLs that returned server errors during the crawl. These are technical availability problems, not copywriting tasks."
      : "The scanner found URLs that returned 404 or 410 during the crawl and included source evidence such as internal links, sitemap discovery, or linked failed URLs.";
    const why = isServer
      ? "Server errors can prevent search engines and users from reaching important pages and can waste crawl budget."
      : "Broken internal links and confirmed failed URLs waste crawl budget and can send users or search engines into dead ends, especially when they are discovered from important pages.";
    const recommendation = isServer
      ? "Ask your web person to inspect the failing URLs, server logs, and routing rules, then restore the page or redirect to the closest relevant live page."
      : "Ask your web person to either restore the missing URL, update the internal link that points to it, or add a 301 redirect to the closest relevant live page. Do not treat this as a meta title or content rewrite.";
    fixes.push(makeSyntheticFix({
      rule: isServer ? "server_error" : bucket === "410" ? "410_error" : "broken_page",
      category: isServer ? "web_dev" : "404_error",
      priority: importantFailedPages(group, siteFingerprint) ? "high" : "medium",
      title,
      explanation,
      why,
      recommendation,
      affectedPages: group.map(pageEvidenceUrl).filter(Boolean),
      difficulty: "developer",
      source: `scanner_verified_failed_pages:${bucket}`,
      extra: evidenceExtra(group),
    }));
  }

  const suspiciousArtifacts = collectArrays([body.suspicious_url_artifacts, body.technical_audit_summary?.suspicious_url_artifacts]).filter(Boolean);
  if (suspiciousArtifacts.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "suspicious_url_artifacts",
      category: "web_dev",
      priority: "low",
      title: "Review suspicious crawler URL artifacts separately from real broken pages",
      explanation: "The scanner saw URL-like artifacts that may come from encoded scripts, assets, or parser noise. They should not be mixed into the confirmed broken-page list without source evidence.",
      why: "Separating suspicious artifacts from confirmed URLs prevents FixList from telling customers to repair pages that may never exist as real routes.",
      recommendation: "Use the evidence list to confirm whether each artifact is a real internal link before adding redirects or content work.",
      affectedPages: suspiciousArtifacts.map((item) => cleanPath(item?.url || item?.path || item)).slice(0, 80),
      difficulty: "developer",
      source: "scanner_suspicious_url_artifacts",
    }));
  }
  return fixes;
}

function buildStrategicFindings({ body, pages, websiteUrl, siteFingerprint, playbook }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const fixes = [];
  const hostname = safeHostname(websiteUrl);

  if (hostname.endsWith(".base44.app")) {
    fixes.push(makeSyntheticFix({
      rule: "free_base44_subdomain",
      category: "indexability",
      priority: "high",
      title: "Move production SEO to a custom domain",
      explanation: "The site is on a free Base44 subdomain. That can be crawled, but it is not the strongest production SEO or trust setup.",
      why: "A custom domain improves brand trust, shareability, Search Console ownership, and company-specific search signals.",
      recommendation: "Connect a branded custom domain before treating this as the long-term production SEO home.",
      affectedPages: ["/"],
      difficulty: "developer",
      source: "archetype_strategy_layer",
    }));
  }

  const routePages = safePages.filter((page) => (isRouteBoundaryCandidate(page?.url || page?.final_url) || isInternalAppRoute(page?.url || page?.final_url)) && pageIsIndexable(page));
  if (routePages.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "route_boundary_candidate_indexable",
      category: "indexability",
      priority: "critical",
      title: "Keep checkout, login, account, and app routes out of search",
      explanation: "FixList found checkout, login, account, dashboard, billing, cart, admin, or app-like routes that appear crawlable and indexable.",
      why: "These pages are usually not useful SEO landing pages. Letting them appear in search can dilute the site, confuse prospects, or expose private product structure.",
      recommendation: "Ask your web person to require login, add noindex, or keep these routes out of public search while preserving true public landing, category, product, booking, and help pages.",
      affectedPages: routePages.map((page) => cleanPath(page?.url || page?.final_url || "/")).slice(0, 80),
      difficulty: "developer",
      source: "archetype_route_boundary_layer",
    }));
  }

  const hasTrustPage = TRUST_PAGE_PATTERNS.some((pattern) => safePages.some((page) => cleanPath(page?.url || page?.final_url || "").toLowerCase().startsWith(pattern)));
  const trustSensitive = siteFingerprint.regulatory_sensitivity !== "standard" || siteFingerprint.primary_archetype === "saas_app_membership" || siteFingerprint.free_base44_subdomain;
  if (!hasTrustPage && safePages.length >= 4 && trustSensitive) {
    fixes.push(makeSyntheticFix({
      rule: "missing_trust_pages",
      category: "schema",
      priority: siteFingerprint.regulatory_sensitivity !== "standard" ? "high" : "medium",
      title: "Add public trust pages",
      explanation: `For a ${playbook.label} site, visitors and crawlers need clear trust, legal, contact, and ownership signals.`,
      why: "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.",
      recommendation: "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.",
      affectedPages: ["/"],
      difficulty: "moderate",
      source: "archetype_trust_layer",
    }));
  }

  const duplicateCasing = collectArrays([body.duplicate_casing_routes, body.technical_audit_summary?.duplicate_casing_routes]);
  if (duplicateCasing.length > 0) {
    fixes.push(makeSyntheticFix({
      rule: "duplicate_route_casing",
      category: "canonical",
      priority: "medium",
      title: "Normalize duplicate URL casing",
      explanation: "The scanner found route variants that differ only by capitalization. These can split signals or create duplicate crawl paths.",
      why: "Consistent casing keeps canonical signals cleaner and avoids duplicate routing edge cases.",
      recommendation: "Ask your web person to canonicalize casing, redirect non-preferred casing, and make internal links use the preferred lowercase route.",
      affectedPages: duplicateCasing.map((item) => cleanPath(item?.url || item?.path || item)).slice(0, 80),
      difficulty: "developer",
      source: "scanner_duplicate_casing_routes",
    }));
  }

  return fixes;
}

function buildSiteFingerprint({ body, pages, websiteUrl }) {
  const safePages = Array.isArray(pages) ? pages : [];
  const pageText = safePages.slice(0, 180).map((page) => [page?.url, page?.final_url, page?.title, page?.h1, page?.meta_description, page?.page_template_family, page?.estimated_page_intent, page?.status_code, (page?.schema_types || []).join(" ")].join(" ")).join(" ").toLowerCase();
  const bodyText = [websiteUrl, body?.business_name, body?.business_type, body?.cms_name, body?.cms_platform, body?.scan_mode, JSON.stringify(body?.business_priority_instruction || {}), pageText].join(" ").toLowerCase();
  const scores = Object.entries(ARCHETYPE_PLAYBOOKS).filter(([key]) => key !== "general").map(([key, playbook]) => ({
    key,
    score: playbook.keywords.reduce((total, keyword) => total + countIncludes(bodyText, keyword), 0) + playbook.moneyPatterns.reduce((total, pattern) => total + countIncludes(bodyText, pattern), 0) * 1.5,
  })).sort((a, b) => b.score - a.score);
  const primary = scores[0]?.score > 0 ? scores[0].key : "general";
  const secondary = scores[1]?.score > Math.max(2, scores[0]?.score * 0.55) ? scores[1].key : "";
  const confidence = scores[0]?.score > 0 ? Math.min(0.95, 0.45 + scores[0].score / Math.max(10, scores[0].score + (scores[1]?.score || 0))) : 0.35;
  const pagesFound = getFirstNumber([body?.scan_coverage?.pages_found, body?.pages_found, body?.technical_audit_summary?.pages_found, safePages.length]);
  const pagesCrawled = getFirstNumber([body?.scan_coverage?.pages_crawled, body?.pages_crawled, body?.technical_audit_summary?.pages_crawled, safePages.length]);
  const playbook = getArchetypePlaybook(primary);
  const hostname = safeHostname(websiteUrl);
  const routeBoundaryCount = safePages.filter((page) => isRouteBoundaryCandidate(page?.url || page?.final_url) || isInternalAppRoute(page?.url || page?.final_url)).length;
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
    render_mode: body?.browser_rendering?.enabled ? "rendered_browser_checked" : safePages.filter((page) => page?.client_rendering_suspected).length >= 3 ? "js_heavy_suspected" : "raw_html_first",
    regulatory_sensitivity: ["finance_insurance_lead_gen", "utilities_comparison_lead_gen"].includes(primary) ? "trust_or_regulated" : "standard",
    likely_money_page_patterns: playbook.moneyPatterns,
    archetype_priority_pages: playbook.priorityPages,
    archetype_priority_issues: playbook.priorityIssues,
    archetype_demotions: playbook.demote,
    route_boundary_count: routeBoundaryCount,
    route_boundary_risk: routeBoundaryCount >= 4 ? "high" : routeBoundaryCount > 0 ? "medium" : "low",
    blocked_access_pages: blockedAccessPages,
    free_base44_subdomain: hostname.endsWith(".base44.app"),
    scoring_model: SCORING_MODEL,
  };
}

function prepareFixes(rawFixes, siteFingerprint, body, playbook) {
  const normalized = dedupeByFixId((Array.isArray(rawFixes) ? rawFixes : []).map((fix, index) => normalizeFix(fix, index)));
  return normalized.map((fix) => scoreFixForSite(fix, siteFingerprint, body, playbook)).sort(compareFixes).slice(0, MAX_FIXES);
}

function normalizeFix(fix, index) {
  const rule = cleanString(fix?.rule || fix?.type || fix?.issue_type || "review");
  const category = CATEGORY_MAP[fix?.category] || CATEGORY_MAP[rule] || fix?.category || inferCategory(rule, fix);
  const pageUrl = cleanPath(fix?.page_url || fix?.url || fix?.final_url || fix?.affected_pages?.[0] || fix?.pages?.[0] || "/");
  const affected = normalizeAffectedPages(fix, pageUrl);
  const difficulty = normalizeDifficulty(fix);
  const developerOwned = needsDeveloperOwner({ ...fix, rule, category, difficulty });
  const title = cleanString(fix?.issue_title || fix?.title) || defaultTitle(category, rule);
  const explanation = cleanString(fix?.plain_english_explanation || fix?.explanation || fix?.summary || fix?.description) || "This recommendation was found during the website scan.";
  const why = cleanString(fix?.why_it_matters || fix?.why || fix?.impact) || "Improving this helps visitors and search engines understand and access the site more clearly.";
  const recommendation = cleanString(fix?.recommended_value || fix?.recommendation || fix?.ai_recommendation || fix?.suggested_fix) || "Review and improve this item.";
  const id = cleanString(fix?.id || fix?.fix_id || fix?.fingerprint) || stableId(`${rule}|${category}|${pageUrl}|${index}|${affected.join(",")}`);
  const steps = normalizeSteps(fix) || defaultSteps({ category, rule, difficulty: developerOwned ? "developer" : difficulty, recommendedValue: recommendation });
  return {
    ...fix,
    id,
    fix_id: id,
    rule,
    category,
    customer_category: fix?.customer_category || friendlyCategory(category),
    issue_title: title,
    title,
    plain_english_explanation: explanation,
    plain_english_summary: cleanString(fix?.plain_english_summary || fix?.plain_english_explanation || fix?.explanation) || explanation,
    why_it_matters: why,
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    current_value: cleanString(fix?.current_value || fix?.current || fix?.status_code ? `HTTP ${fix.status_code}` : ""),
    page_url: pageUrl,
    affected_pages: affected,
    source_pages: Array.isArray(fix?.source_pages) ? fix.source_pages.slice(0, 20) : [],
    link_text_samples: Array.isArray(fix?.link_text_samples) ? fix.link_text_samples.slice(0, 10) : [],
    url_confidence: fix?.url_confidence || "",
    url_suspicion_reasons: Array.isArray(fix?.url_suspicion_reasons) ? fix.url_suspicion_reasons.slice(0, 8) : [],
    priority: normalizePriority(fix?.priority),
    difficulty: developerOwned ? "developer" : difficulty,
    status: developerOwned ? "needs_developer" : fix?.status || (fix?.can_auto_fix ? "auto_fixed" : "needs_approval"),
    requires_developer: developerOwned || Boolean(fix?.requires_developer),
    requires_approval: developerOwned ? false : fix?.requires_approval !== false,
    can_auto_fix: Boolean(fix?.can_auto_fix) && !developerOwned,
    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,
    who_can_do_this: developerOwned ? "your_web_person" : normalizeOwner(fix?.who_can_do_this),
    estimated_time: cleanString(fix?.estimated_time || fix?.time_estimate) || defaultTime(developerOwned ? "developer" : difficulty),
    time_estimate: cleanString(fix?.time_estimate || fix?.estimated_time) || defaultTime(developerOwned ? "developer" : difficulty),
    confidence_score: typeof fix?.confidence_score === "number" ? fix.confidence_score : 88,
  };
}

function scoreFixForSite(fix, siteFingerprint, body, playbook) {
  const pageUrl = cleanPath(fix?.page_url || fix?.affected_pages?.[0] || "/") || "/";
  const pageValue = scorePageValue(pageUrl, siteFingerprint, body, playbook);
  const defectClass = classifyDefectClass(fix);
  const evidenceConfidence = scoreEvidenceConfidence(fix);
  const reachScore = Math.max(5, Math.min(100, (fix?.affected_pages?.length || 1) * 12));
  const structuralBoost = ["structural", "crawl_index", "blocked_access"].includes(defectClass) ? 18 : 0;
  const trustBoost = siteFingerprint.regulatory_sensitivity !== "standard" && ["content_trust", "semantic_schema", "crawl_index"].includes(defectClass) ? 15 : 0;
  let overall = Math.round(evidenceConfidence * 0.22 + pageValue.score * 0.26 + reachScore * 0.14 + structuralBoost + trustBoost + 24);
  if (fix?.url_confidence === "crawler_artifact") overall = Math.min(overall, 44);
  overall = Math.max(0, Math.min(100, overall));
  const priority = fix.priority === "critical" ? "critical" : overall >= 82 ? "critical" : overall >= 68 ? "high" : overall >= 44 ? "medium" : "low";
  const developerOwned = needsDeveloperOwner({ ...fix, primary_defect_class: defectClass });
  return {
    ...fix,
    priority,
    page_type: pageValue.classification,
    page_template_family: fix.page_template_family || getTemplateFamily(pageUrl),
    page_value_score: pageValue.score,
    page_value_label: pageValue.label,
    primary_defect_class: defectClass,
    meta_rewrite_allowed: false,
    meta_regeneration_gate: "not_metadata_primary_gap",
    business_importance: pageValue.classification,
    evidence_confidence: evidenceConfidence,
    reach_score: reachScore,
    overall_priority_score: overall,
    site_fingerprint_vertical: siteFingerprint.primary_archetype,
    archetype_label: siteFingerprint.archetype_label,
    requires_developer: developerOwned || fix.requires_developer,
    difficulty: developerOwned ? "developer" : fix.difficulty,
    status: developerOwned ? "needs_developer" : fix.status,
    who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this,
  };
}

function buildFallbackPlan({ body, pages, canonicalFixes, siteFingerprint, playbook, websiteUrl }) {
  const healthScore = computeHealthScore(canonicalFixes, siteFingerprint);
  const summary = `FixList recognized this as ${playbook.label} and used the ${playbook.label} playbook. The scanner reviewed ${siteFingerprint.pages_crawled} pages${siteFingerprint.pages_found ? ` out of about ${siteFingerprint.pages_found} discovered URLs` : ""}. Start with the highest-impact items on ${playbook.priorityPages.slice(0, 3).join(", ")}.`;
  const working = [];
  if (siteFingerprint.primary_archetype !== "general") working.push(`FixList detected a ${playbook.label} pattern.`);
  const topConcerns = canonicalFixes.slice(0, 3).map((fix) => fix.issue_title || fix.title).filter(Boolean);
  const quickWins = canonicalFixes.filter((fix) => fix.difficulty !== "developer").slice(0, 3).map((fix) => fix.issue_title || fix.title).filter(Boolean);
  const biggerProjects = canonicalFixes.filter((fix) => fix.difficulty === "developer" || fix.requires_developer).slice(0, 3).map((fix) => fix.issue_title || fix.title).filter(Boolean);
  const report = {
    health_score: healthScore,
    score: healthScore,
    overall_explanation: summary,
    health_grade: healthScore >= 90 ? "Excellent" : healthScore >= 80 ? "Good" : healthScore >= 65 ? "Needs work" : "Poor",
    what_is_working: working,
    top_concerns: topConcerns,
    quick_wins: quickWins,
    bigger_projects: biggerProjects,
    limitations: [
      "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs.",
      "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages.",
    ],
    next_best_step: canonicalFixes[0]?.issue_title || "Review the first FixList item.",
  };
  return {
    plain_english_summary: summary,
    website_health_report: report,
    health_explanation: summary,
    customer_summary: summary,
    top_recommended_actions: canonicalFixes.slice(0, 5),
    recommended_actions: canonicalFixes,
    cleaned_fixes: canonicalFixes,
    raw_fixes: canonicalFixes,
    fixes: canonicalFixes,
    findings: canonicalFixes,
    recommendations: canonicalFixes,
    competitor_insights: [],
    grouped_page_recommendations: groupPageRecommendations(canonicalFixes),
    ignored_low_value_pages: (pages || []).filter((page) => isLowValuePage(page?.url || page?.final_url)).slice(0, 30).map((page) => cleanPath(page?.url || page?.final_url || "")),
    positive_findings: working,
    ai_rewrites_applied: 0,
    crawled_pages: (pages || []).slice(0, MAX_PAGES_RETURNED),
    pages: (pages || []).slice(0, MAX_PAGES_RETURNED),
    health_score: healthScore,
    site_fingerprint: siteFingerprint,
    archetype_playbook: { label: playbook.label, priority_pages: playbook.priorityPages, priority_issues: playbook.priorityIssues, demote: playbook.demote, owner_rule: playbook.ownerRule },
    technical_audit_summary: body.technical_audit_summary || null,
    screaming_frog_lite_enabled: Boolean(body.screaming_frog_lite_enabled),
    audit_profile: cleanString(body.scanner_profile || body.audit_profile || ""),
    scanner_version: body.scanner_version || body.version || "",
    advanced_scan_backend: body.advanced_scan_backend || body.technical_audit_summary?.advanced_scan_backend || "",
    deno_fallback_used: Boolean(body.deno_fallback_used || body.technical_audit_summary?.deno_fallback_used),
    website_url: websiteUrl,
    seo_score: healthScore,
    simple_summary: summary,
    scanned_pages: (pages || []).slice(0, MAX_PAGES_RETURNED),
    scan_summary: { health_score: healthScore, score: healthScore, pages_scanned: siteFingerprint.pages_crawled, plain_english_summary: summary, site_fingerprint: siteFingerprint },
    scoring_model: SCORING_MODEL,
  };
}

function makeSyntheticFix({ rule, category, priority, title, explanation, why, recommendation, affectedPages, difficulty, source, extra = {} }) {
  const cleanAffected = Array.from(new Set((affectedPages || ["/"]).map((url) => cleanPath(url)).filter(Boolean))).slice(0, 150);
  const page = cleanAffected[0] || "/";
  const id = stableId(`synthetic|${rule}|${page}|${title}|${cleanAffected.join(",")}`);
  const steps = defaultSteps({ category, rule, difficulty, recommendedValue: recommendation });
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
    current_value: extra.current_value || (rule.includes("broken") || rule.includes("404") || rule.includes("410") ? "Confirmed failed URL evidence from scanner" : "Detected from crawl evidence and site patterns."),
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    priority,
    difficulty,
    status: difficulty === "developer" ? "needs_developer" : "needs_approval",
    can_auto_fix: false,
    requires_approval: difficulty !== "developer",
    requires_developer: difficulty === "developer",
    affected_pages: cleanAffected,
    page_url: page,
    confidence_score: extra.confidence_score || 92,
    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,
    who_can_do_this: defaultOwner(difficulty),
    estimated_time: defaultTime(difficulty),
    time_estimate: defaultTime(difficulty),
    source,
    ...extra,
  };
}

function evidenceExtra(group) {
  return {
    status_codes: Array.from(new Set(group.map((page) => Number(page?.status_code || page?.status || 0)).filter(Boolean))),
    source_pages: Array.from(new Set(group.flatMap((page) => Array.isArray(page?.source_pages) ? page.source_pages : []))).slice(0, 30),
    link_text_samples: Array.from(new Set(group.flatMap((page) => Array.isArray(page?.link_text_samples) ? page.link_text_samples : []))).slice(0, 12),
    url_confidence: group.some((page) => page?.url_confidence === "linked_but_failed") ? "linked_but_failed" : group[0]?.url_confidence || "scanner_evidence",
    current_value: group.map((page) => `${cleanPath(pageEvidenceUrl(page))}: HTTP ${page?.status_code || page?.status || "failed"}`).slice(0, 8).join("; "),
  };
}

function computeHealthScore(fixes, siteFingerprint) {
  let score = 92;
  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 12;
    else if (fix.priority === "high") score -= 8;
    else if (fix.priority === "medium") score -= 4;
    else score -= 1;
  }
  if (siteFingerprint.pages_crawled === 0) score = Math.min(score, 86);
  return Math.max(35, Math.min(98, score));
}

function scorePageValue(url, siteFingerprint, body, playbook) {
  const path = cleanPath(url).toLowerCase();
  const requested = cleanPath(body?.requested_path_prefix || body?.crawl_path_prefix || body?.path_prefix || "").toLowerCase();
  let score = 35;
  if (path === "/" || path.endsWith("/index.html")) score += 35;
  if (requested && (path === requested || path === `${requested}/` || path === `${requested}/index.html`)) score += 35;
  if (isRouteBoundaryCandidate(path) || isInternalAppRoute(path)) score += 32;
  for (const pattern of playbook.moneyPatterns || []) if (path.includes(pattern)) { score += 20; break; }
  if (hasAny(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "pricing", "demo", "signup", "product", "products", "collection", "collections", "checkout"])) score += 22;
  if (isLowValuePage(path)) score -= 45;
  const clamped = Math.max(0, Math.min(100, score));
  const classification = isRouteBoundaryCandidate(path) || isInternalAppRoute(path) ? "internal_or_auth_route" : clamped >= 70 ? "money_page" : clamped <= 30 ? "low_value" : "standard";
  return { score: clamped, classification, label: classification === "internal_or_auth_route" ? "Route-boundary candidate" : classification === "money_page" ? "Important business page" : classification === "low_value" ? "Lower-priority archive/tag page" : "Standard page" };
}

function classifyDefectClass(fix) {
  const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""} ${fix?.title || ""} ${fix?.current_value || ""}`.toLowerCase();
  if (hasAny(text, ["429", "blocked", "rate limit", "bot protection", "connection verification"])) return "blocked_access";
  if (hasAny(text, ["route_boundary", "internal_route", "login", "account", "checkout", "dashboard", "noindex", "indexability"])) return "crawl_index";
  if (hasAny(text, ["javascript", "render", "canonical", "redirect", "500", "503", "404", "410", "server_error", "broken_page"])) return "structural";
  if (hasAny(text, ["schema", "structured"])) return "semantic_schema";
  if (hasAny(text, ["trust", "privacy", "terms", "legal", "about", "contact", "review", "methodology"])) return "content_trust";
  if (hasAny(text, ["meta", "title", "description"])) return "metadata";
  return "general";
}

function scoreEvidenceConfidence(fix) {
  let score = typeof fix?.confidence_score === "number" ? fix.confidence_score : 72;
  if (String(fix?.source || "").includes("scanner")) score += 10;
  if (fix?.current_value) score += 5;
  if (Array.isArray(fix?.affected_pages) && fix.affected_pages.length > 1) score += 5;
  if (fix?.url_confidence === "crawler_artifact") score -= 35;
  if (!fix?.page_url && (!fix?.affected_pages || fix.affected_pages.length === 0)) score -= 15;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function defaultSteps({ category, rule, difficulty, recommendedValue }) {
  if (difficulty === "developer" || /429|blocked|rate_limited|server_error|404|410|broken|canonical|redirect|route_boundary|indexability/i.test(String(rule || category || ""))) {
    if (/429|blocked|rate_limited/i.test(String(rule || ""))) return ["Send the grouped affected URLs to your web person.", "Check CDN, firewall, server, and bot-protection logs for HTTP 429 or verification responses.", "Confirm whether Googlebot and normal users can load the pages.", "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.", "Run FixList again to confirm the affected pages load."];
    if (/404|410|broken/i.test(String(rule || category || ""))) return ["Send the affected URLs and source-page evidence to your web person.", "Decide whether each URL should be restored, redirected, or removed from internal links.", "Update the source links or add 301 redirects to the closest relevant live page.", "Run FixList again to confirm the URLs no longer fail."];
    return ["Send this recommendation to your web person.", "Update the routing, canonical, schema, indexability, or template configuration.", "Publish the change and rerun FixList to verify it."];
  }
  if (category === "schema") return ["Choose the correct schema or trust-page update.", "Add it through the CMS, SEO plugin, theme, or developer workflow.", "Validate after publishing."];
  return ["Open the affected page or template.", cleanString(recommendedValue) || "Apply the recommended change.", "Publish the update and run FixList again."];
}

function inferCategory(rule, fix) {
  const text = `${rule} ${fix?.title || ""} ${fix?.issue_title || ""}`.toLowerCase();
  if (hasAny(text, ["429", "blocked", "rate limit", "bot protection", "server", "500", "503"])) return "web_dev";
  if (text.includes("schema") || text.includes("trust")) return "schema";
  if (text.includes("canonical")) return "canonical";
  if (text.includes("title")) return "meta_title";
  if (text.includes("description") || text.includes("meta")) return "meta_description";
  if (text.includes("alt")) return "image_alt_text";
  if (text.includes("404") || text.includes("410") || text.includes("broken")) return "404_error";
  if (text.includes("index") || text.includes("noindex")) return "indexability";
  return "web_dev";
}

function defaultTitle(category, rule = "") {
  if (/404|410|broken/i.test(`${category} ${rule}`)) return "Fix confirmed broken URLs";
  const titles = { meta_title: "Improve search titles", meta_description: "Improve search descriptions", duplicate_content: "Review duplicate or repeated pages", canonical: "Review canonical URL setup", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", "404_error": "Fix pages that are not loading", web_dev: "Review website setup", image_alt_text: "Add useful image descriptions", indexability: "Review indexability settings" };
  return titles[category] || "Review this recommendation";
}
function friendlyCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(priority)) return priority; return "medium"; }
function normalizeDifficulty(fix) { const difficulty = String(fix?.difficulty || fix?.estimated_complexity || "").toLowerCase(); if (difficulty.includes("developer") || difficulty.includes("complex")) return "developer"; if (difficulty.includes("moderate")) return "moderate"; return "easy"; }
function normalizeOwner(value) { const owner = String(value || "").toLowerCase(); if (owner.includes("web") || owner.includes("developer") || owner === "your_web_person") return "your_web_person"; return "you"; }
function defaultOwner(difficulty) { return difficulty === "developer" ? "your_web_person" : "you"; }
function defaultTime(difficulty) { if (difficulty === "developer") return "about 1–2 hours"; if (difficulty === "moderate") return "about 30–60 minutes"; return "about 10–20 minutes"; }
function normalizeSteps(fix) { const steps = pickFirstNonEmptyArray([fix?.what_to_do_steps, fix?.what_to_do, fix?.fix_steps, fix?.steps]); return steps.length ? steps.map(String).filter(Boolean).slice(0, 6) : null; }
function needsDeveloperOwner(item = {}) { const value = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.reason || ""} ${item.recommendation || ""} ${item.recommended_value || ""} ${pickFirstNonEmptyArray([item.what_to_do_steps, item.what_to_do]).join(" ")} ${item.who_can_do_this || ""} ${item.primary_defect_class || ""}`.toLowerCase(); if (item.requires_developer || item.difficulty === "developer" || item.status === "needs_developer" || value.includes("your_web_person")) return true; return /developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|404|410|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard|routing/.test(value); }
function detectBusinessModel(text, archetype) { if (hasAny(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"])) return "quote_or_comparison_lead_gen"; if (hasAny(text, ["booking", "reservation", "réservation", "availability", "calendar", "book now", "ticket", "stage", "pass"])) return "booking_or_reservation"; if (hasAny(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart", "shopify"])) return "catalog_or_ecommerce"; if (hasAny(text, ["login", "dashboard", "subscription", "billing", "admin"])) return "saas_or_member_app"; if (["finance_insurance_lead_gen", "utilities_comparison_lead_gen"].includes(archetype)) return "regulated_or_trust_lead_generation"; if (archetype === "booking_experiences_marketplace") return "booking_or_reservation"; if (archetype === "ecommerce_specialty_retail") return "catalog_or_ecommerce"; return "content_or_general_business"; }
function detectLocalization(pages, websiteUrl) { const text = [websiteUrl, ...pages.slice(0, 100).map((page) => page?.url || page?.final_url || "")].join(" ").toLowerCase(); const hits = (text.match(/\/(fr|en|es|de|it|nl|pt|ca|us|uk)([-_\/]|$)/g) || []).length; if (hits >= 4) return "multi_language_or_multi_country"; if (hits > 0) return "single_locale_subfolder"; return "single_language_or_unknown"; }
function getArchetypePlaybook(key) { return ARCHETYPE_PLAYBOOKS[key] || ARCHETYPE_PLAYBOOKS.general; }
function isFailedPage(page) { const status = Number(page?.status_code || page?.status || 0); if (status >= 400 && status !== 429) return true; const error = String(page?.fetch_error || page?.error || "").toLowerCase(); return hasAny(error, ["404", "410", "500", "503", "not found", "server error"]); }
function isBlockedAccessPage(page) { const status = Number(page?.status_code || page?.status || 0); const text = `${page?.fetch_error || ""} ${page?.title || ""} ${page?.content_type || ""}`.toLowerCase(); return status === 429 || hasAny(text, ["rate limit", "too many requests", "connection verification", "bot protection", "access denied", "cloudflare"]); }
function statusBucketFromPage(page) { const status = Number(page?.status_code || page?.status || 0); if (status === 429 || isBlockedAccessPage(page)) return "429"; if (status >= 500) return "5xx"; if (status === 410) return "410"; return "404"; }
function importantFailedPages(group, siteFingerprint) { return group.some((page) => { const url = pageEvidenceUrl(page); const path = cleanPath(url).toLowerCase(); return page?.url_confidence === "linked_but_failed" || page?.url_confidence === "confirmed_sitemap_and_linked" || siteFingerprint.likely_money_page_patterns.some((pattern) => path.includes(pattern)) || !isLowValuePage(path); }); }
function pageEvidenceUrl(page) { return page?.url || page?.final_url || page?.path || page?.page_url || "/"; }
function pageIsIndexable(page) { const robots = String(page?.robots || page?.robots_meta || "").toLowerCase(); if (robots.includes("noindex")) return false; if (page?.indexable === false) return false; return true; }
function getTemplateFamily(url = "") { const path = cleanPath(url).toLowerCase(); if (isRouteBoundaryCandidate(path)) return "route_boundary"; if (isLowValuePage(path)) return "archive"; if (/checkout|cart|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/\/products?\/|\/p\//.test(path)) return "product_page"; if (/\/collections?\/|\/category\/|\/categorie\/|listing|show|marque|brand/.test(path)) return "collection_page"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz|pret|credit/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog|article/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(path)) return "legal_info"; return "standard"; }
function isLowValuePage(url = "") { const path = cleanPath(url).toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; return LOW_VALUE_PATTERNS.some((pattern) => path.includes(pattern)); }
function isRouteBoundaryCandidate(url = "") { const path = cleanPath(url).toLowerCase(); return ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"].some((pattern) => path.includes(pattern)); }
function isInternalAppRoute(url = "") { const path = cleanPath(url).toLowerCase(); return INTERNAL_ROUTE_PATTERNS.some((pattern) => path.includes(pattern)); }
function normalizeAffectedPages(fix, fallback) { return Array.from(new Set([...(Array.isArray(fix?.affected_pages) ? fix.affected_pages : []), ...(Array.isArray(fix?.pages) ? fix.pages : []), ...(Array.isArray(fix?.page_urls) ? fix.page_urls : []), fallback].filter(Boolean).map((url) => cleanPath(url)))).slice(0, 150); }
function dedupeByFixId(fixes) { const seen = new Set(); const output = []; for (const fix of fixes || []) { const key = fix.fix_id || fix.id || `${fix.rule}|${fix.category}|${fix.page_url}|${(fix.affected_pages || []).join(",")}`; if (seen.has(key)) continue; seen.add(key); output.push(fix); } return output; }
function dedupePages(pages) { const seen = new Set(); const output = []; for (const page of pages || []) { const key = cleanPath(pageEvidenceUrl(page)); if (!key || seen.has(key)) continue; seen.add(key); output.push(page); } return output; }
function compareFixes(a, b) { const priorityScore = { critical: 4, high: 3, medium: 2, low: 1 }; return (Number(b.overall_priority_score || 0) + (priorityScore[b.priority] || 0) * 100) - (Number(a.overall_priority_score || 0) + (priorityScore[a.priority] || 0) * 100); }
function groupPageRecommendations(fixes) { const groups = new Map(); for (const fix of fixes || []) { const family = fix.page_template_family || "site"; const list = groups.get(family) || []; list.push(fix); groups.set(family, list); } return Array.from(groups.entries()).map(([template_family, items]) => ({ template_family, count: items.length, top_recommendations: items.slice(0, 5) })).slice(0, 12); }
function collectArrays(values) { const output = []; for (const value of values || []) { if (Array.isArray(value)) output.push(...value); } return output; }
function pickFirstNonEmptyArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function parseJsonObject(value) { try { return JSON.parse(String(value || "{}")); } catch { return {}; } }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const url = new URL(raw); return `${url.pathname || "/"}${url.search || ""}` || "/"; } catch { return raw.startsWith("/") ? raw : `/${raw}`; } }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function hasAny(text, needles) { const haystack = String(text || "").toLowerCase(); return (needles || []).some((needle) => haystack.includes(String(needle || "").toLowerCase())); }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function jsonResponse(payload, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }); }
