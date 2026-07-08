import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const AI_REVIEW_VERSION = "aiReviewScan_v5_python_review_first";
const PYTHON_REVIEW_VERSION = "python_review_v1_archetype_templates";
const DENO_FALLBACK_PROFILE = "deno_review_safety_fallback_v5";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const REVIEW_TIMEOUT_MS = Number(Deno.env.get("PYTHON_REVIEW_TIMEOUT_MS") || 120000);
const MAX_FIXES = Number(Deno.env.get("MAX_AI_FIXES") || 36);
const MAX_PAGES_RETURNED = Number(Deno.env.get("MAX_REVIEW_PAGES_RETURNED") || 80);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, error: "Unauthorized" }, 401);

    const rawBody = await req.json().catch(() => ({}));
    const pythonAttempt = await tryPythonReview(rawBody);

    if (pythonAttempt.ok) {
      return jsonResponse({
        ...pythonAttempt.result,
        success: true,
        ai_review_version: pythonAttempt.result.ai_review_version || PYTHON_REVIEW_VERSION,
        review_version: pythonAttempt.result.review_version || PYTHON_REVIEW_VERSION,
        base44_ai_review_version: AI_REVIEW_VERSION,
        ai_review_backend: "python_review_api",
        python_review_fallback_used: false,
        python_review_api_url_configured: true,
      });
    }

    const fallback = buildDenoSafetyFallback(rawBody, pythonAttempt.reason, pythonAttempt.configured);
    return jsonResponse(fallback);
  } catch (error) {
    console.error("aiReviewScan failed", error);
    return jsonResponse({ success: false, error: "aiReviewScan failed. Please try again." }, 500);
  }
});

async function tryPythonReview(rawBody) {
  const scannerUrl = String(
    Deno.env.get("SCANNER_API_URL") ||
    Deno.env.get("PYTHON_SCANNER_API_URL") ||
    Deno.env.get("PYTHON_SCANNER_URL") ||
    Deno.env.get("SCANNER_URL") ||
    Deno.env.get("cloud_api") ||
    Deno.env.get("CLOUD_API") ||
    ""
  ).replace(/\/+$/, "");
  const scannerKey = String(Deno.env.get("SCANNER_API_KEY") || Deno.env.get("PYTHON_SCANNER_API_KEY") || "");

  if (!scannerUrl) return { ok: false, configured: false, reason: "SCANNER_API_URL/cloud_api is not configured." };
  if (!scannerKey) return { ok: false, configured: true, reason: "SCANNER_API_KEY is not configured." };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REVIEW_TIMEOUT_MS);
  try {
    const response = await fetch(`${scannerUrl}/review`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-scanner-key": scannerKey,
      },
      body: JSON.stringify({ scan: rawBody }),
      signal: controller.signal,
    });

    const text = await response.text();
    let result = {};
    try {
      result = text ? JSON.parse(text) : {};
    } catch {
      return { ok: false, configured: true, reason: `Python review returned non-JSON response (${response.status}).` };
    }

    if (!response.ok || result?.success === false) {
      return { ok: false, configured: true, reason: result?.error || result?.detail || `Python review failed with HTTP ${response.status}.` };
    }

    const reviewVersion = result?.ai_review_version || result?.review_version || "";
    if (reviewVersion !== PYTHON_REVIEW_VERSION) {
      return { ok: false, configured: true, reason: `Python review version mismatch: ${reviewVersion || "missing"}.` };
    }

    return { ok: true, configured: true, result };
  } catch (error) {
    const reason = error?.name === "AbortError" ? "Python review timed out." : `Python review request failed: ${error?.message || String(error)}`;
    return { ok: false, configured: true, reason };
  } finally {
    clearTimeout(timeout);
  }
}

function buildDenoSafetyFallback(rawBody, reason, configured) {
  const body = unwrapScanPayload(rawBody);
  const websiteUrl = cleanString(body.website_url || body.normalized_url || body.url || body.technical_audit_summary?.website_url || "");
  const pages = pickFirstNonEmptyArray([body.crawled_pages, body.pages, body.scanned_pages, body.crawl_pages, body.technical_audit_summary?.pages]);
  const fingerprint = buildSiteFingerprint(body, pages, websiteUrl);
  const fixes = buildFallbackFixes(body, pages, fingerprint).slice(0, MAX_FIXES);
  const healthScore = computeHealthScore(fixes, pages);
  const summary = `FixList used the local safety fallback because Python review was unavailable. It recognized this as ${fingerprint.archetype_label}. The scanner reviewed ${fingerprint.pages_crawled} pages${fingerprint.pages_found ? ` out of about ${fingerprint.pages_found} discovered URLs` : ""}.`;
  const warning = `Python review fallback used: ${reason || "unknown reason"}`;
  const report = {
    health_score: healthScore,
    score: healthScore,
    overall_explanation: summary,
    health_grade: healthScore >= 90 ? "Excellent" : healthScore >= 80 ? "Good" : healthScore >= 65 ? "Needs work" : "Poor",
    what_is_working: fingerprint.primary_archetype !== "general" ? [`FixList detected a ${fingerprint.archetype_label} pattern.`] : [],
    top_concerns: fixes.slice(0, 3).map((fix) => fix.title),
    quick_wins: fixes.filter((fix) => fix.who_can_do_this !== "your_web_person").slice(0, 3).map((fix) => fix.title),
    bigger_projects: fixes.filter((fix) => fix.who_can_do_this === "your_web_person").slice(0, 3).map((fix) => fix.title),
    limitations: [
      "This fallback is deterministic and uses scanner evidence only.",
      "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages.",
    ],
    next_best_step: fixes[0]?.title || "Review the first FixList item.",
  };

  return {
    success: true,
    ai_provider: "deno_safety_fallback",
    ai_review_version: AI_REVIEW_VERSION,
    review_version: AI_REVIEW_VERSION,
    base44_ai_review_version: AI_REVIEW_VERSION,
    ai_review_backend: "deno_safety_fallback",
    ai_review_warning: warning,
    python_review_fallback_used: true,
    python_review_api_url_configured: Boolean(configured),
    python_review_fallback_reason: reason || "unknown reason",
    deno_fallback_profile: DENO_FALLBACK_PROFILE,
    plain_english_summary: summary,
    website_health_report: report,
    health_explanation: summary,
    customer_summary: summary,
    top_recommended_actions: fixes.slice(0, 5),
    recommended_actions: fixes,
    cleaned_fixes: fixes,
    raw_fixes: fixes,
    fixes,
    findings: fixes,
    recommendations: fixes,
    competitor_insights: [],
    grouped_page_recommendations: groupByTemplate(fixes),
    ignored_low_value_pages: pages.filter((page) => isLowValuePage(page.url || page.final_url || page.path)).slice(0, 30).map((page) => cleanPath(page.url || page.final_url || page.path)),
    positive_findings: fingerprint.primary_archetype !== "general" ? [`FixList detected a ${fingerprint.archetype_label} pattern.`] : [],
    ai_rewrites_applied: 0,
    crawled_pages: pages.slice(0, MAX_PAGES_RETURNED),
    pages: pages.slice(0, MAX_PAGES_RETURNED),
    health_score: healthScore,
    seo_score: healthScore,
    site_fingerprint: fingerprint,
    archetype_playbook: {
      label: fingerprint.archetype_label,
      priority_pages: fingerprint.archetype_priority_pages,
      priority_issues: fingerprint.archetype_priority_issues,
      demote: fingerprint.archetype_demotions,
      owner_rule: "Technical, template, canonical, schema, routing, and repeated batch issues usually need your_web_person.",
    },
    technical_audit_summary: body.technical_audit_summary || null,
    screaming_frog_lite_enabled: Boolean(body.screaming_frog_lite_enabled),
    audit_profile: cleanString(body.scanner_profile || body.audit_profile || ""),
    scanner_version: body.scanner_version || body.version || "",
    advanced_scan_backend: body.advanced_scan_backend || body.technical_audit_summary?.advanced_scan_backend || "",
    deno_fallback_used: Boolean(body.deno_fallback_used || body.technical_audit_summary?.deno_fallback_used),
    website_url: websiteUrl,
    simple_summary: summary,
    scanned_pages: pages.slice(0, MAX_PAGES_RETURNED),
    scan_summary: {
      health_score: healthScore,
      score: healthScore,
      pages_scanned: fingerprint.pages_crawled,
      plain_english_summary: summary,
      site_fingerprint: fingerprint,
    },
    scoring_model: "deno_safety_fallback_v5",
  };
}

function buildFallbackFixes(body, pages, fingerprint) {
  const fixes = [];
  const verifiedFailed = dedupePages([
    ...collectArrays([body.verified_failed_pages, body.technical_audit_summary?.verified_failed_pages, body.url_evidence_summary?.verified_failed_pages]),
    ...pages.filter((page) => isFailedPage(page)),
  ]);
  const blocked = dedupePages(pages.filter((page) => isBlockedAccessPage(page)));

  if (verifiedFailed.length > 0) {
    fixes.push(makeFix({
      rule: "broken_page",
      category: "404_error",
      priority: "high",
      title: "Fix confirmed broken URLs found during the crawl",
      explanation: "The scanner found URLs that returned 404, 410, or server errors during the crawl.",
      why: "Broken internal links and failed URLs waste crawl budget and can send users or search engines into dead ends.",
      recommendation: "Ask your web person to restore the missing URL, update the internal link, or add a 301 redirect to the closest relevant live page.",
      affectedPages: verifiedFailed.map(pageEvidenceUrl),
      difficulty: "developer",
      source: "deno_fallback_verified_failed_pages",
      extra: evidenceExtra(verifiedFailed),
    }));
  }

  if (blocked.length > 0) {
    fixes.push(makeFix({
      rule: "rate_limited_page",
      category: "web_dev",
      priority: blocked.length >= 3 ? "high" : "medium",
      title: "Verify crawler access for blocked or rate-limited pages",
      explanation: "The scanner saw HTTP 429, bot protection, or connection-verification evidence.",
      why: "If legitimate crawlers cannot access important pages, search engines may miss them.",
      recommendation: "Ask your web person to check CDN, firewall, bot-protection, and server logs before changing page content.",
      affectedPages: blocked.map(pageEvidenceUrl),
      difficulty: "developer",
      source: "deno_fallback_blocked_access_pages",
      extra: evidenceExtra(blocked),
    }));
  }

  const buckets = new Map();
  for (const page of pages || []) {
    const url = page.url || page.final_url || page.path || "";
    if (!url) continue;
    const family = page.page_template_family || getTemplateFamily(url);
    if (!cleanString(page.canonical || page.canonical_url)) addBucket(buckets, "canonical_missing", "canonical", family, page, "Add canonical URLs across templates", "The page does not expose a canonical URL.", "Canonical URLs help search engines consolidate duplicate and near-duplicate pages.", "Ask your web person to add self-referencing canonicals to the shared template or affected pages.", "developer");
    const h1Count = Number(page.h1_count || 0);
    if (h1Count === 0) addBucket(buckets, "missing_h1", "thin_content", family, page, "Fix missing H1 headings on templates", "The page has no main H1 heading.", "A clear H1 helps users and search engines understand the page topic.", "Add one clear H1 to the affected template or page.", "moderate");
    if (h1Count > 1) addBucket(buckets, "multiple_h1", "thin_content", family, page, "Use one main page heading", "The page has more than one H1 heading.", "Multiple H1s can make the page structure less clear.", "Keep one H1 as the main page heading and make the rest H2/H3 headings.", "easy");
    const missingAlt = Number(page.image_missing_alt_count || page.missing_alt_image_count || 0);
    if (missingAlt > 0) addBucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", `${missingAlt} images missing alt text`, "Repeated image-alt gaps are usually a shared template or CMS pattern.", "Fix one representative page/template first, then roll out the same rule across the affected group.", missingAlt >= 8 ? "developer" : "easy");
    if (!cleanString(page.meta_description)) addBucket(buckets, "missing_meta_description", "meta_description", family, page, "Batch meta descriptions on templates", "The page is missing a meta description.", "Search descriptions can improve how pages appear in search results.", "Add a short description that explains the page and why someone should click.", "easy");
  }

  for (const bucket of buckets.values()) {
    const affected = Array.from(new Set(bucket.pages.map(pageEvidenceUrl).map(cleanPath))).filter(Boolean);
    const grouped = affected.length > 1;
    fixes.push(makeFix({
      rule: bucket.rule,
      category: bucket.category,
      priority: bucket.category === "canonical" ? "critical" : affected.length >= 8 ? "high" : "medium",
      title: grouped ? bucket.title.replace("templates", `${familyLabel(bucket.family)} templates`) : bucket.title.replace("templates", "the affected page"),
      explanation: grouped ? "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page." : bucket.explanation,
      why: grouped ? "Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns." : bucket.why,
      recommendation: bucket.recommendation,
      affectedPages: affected,
      difficulty: affected.length >= 5 ? "developer" : bucket.difficulty,
      source: `deno_fallback_page_pattern:${bucket.rule}:${bucket.family}`,
      extra: { current_value: bucket.currentValue, page_template_family: bucket.family },
    }));
  }

  return fixes.map((fix) => scoreFix(fix, fingerprint, body)).sort(compareFixes);
}

function makeFix({ rule, category, priority, title, explanation, why, recommendation, affectedPages, difficulty, source, extra = {} }) {
  const cleanAffected = Array.from(new Set((affectedPages || ["/"]).map(cleanPath).filter(Boolean))).slice(0, 150);
  const page = cleanAffected[0] || "/";
  const developerOwned = difficulty === "developer" || cleanAffected.length >= 5 || /canonical|redirect|server|schema|template|404|410|429|blocked|indexability|route/i.test(`${rule} ${category} ${title}`);
  const id = stableId(`fallback|${rule}|${page}|${title}|${cleanAffected.join(",")}`);
  const steps = defaultSteps({ category, rule, difficulty: developerOwned ? "developer" : difficulty, recommendedValue: recommendation });
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
    current_value: extra.current_value || "Detected from crawl evidence and site patterns.",
    recommended_value: recommendation,
    ai_recommendation: recommendation,
    priority,
    difficulty: developerOwned ? "developer" : difficulty,
    status: developerOwned ? "needs_developer" : "needs_approval",
    can_auto_fix: false,
    requires_approval: !developerOwned,
    requires_developer: developerOwned,
    affected_pages: cleanAffected,
    page_url: page,
    confidence_score: 88,
    what_to_do: steps,
    what_to_do_steps: steps,
    fix_steps: steps,
    who_can_do_this: developerOwned ? "your_web_person" : "you",
    estimated_time: developerOwned ? "about 1–2 hours" : "about 10–20 minutes",
    time_estimate: developerOwned ? "about 1–2 hours" : "about 10–20 minutes",
    source,
    ...extra,
  };
}

function scoreFix(fix, fingerprint, body) {
  const pageUrl = cleanPath(fix.page_url || fix.affected_pages?.[0] || "/");
  const pageValue = scorePageValue(pageUrl, fingerprint, body);
  const defectClass = classifyDefectClass(fix);
  const evidenceConfidence = Number(fix.confidence_score || 80);
  const reachScore = Math.max(5, Math.min(100, (fix.affected_pages?.length || 1) * 10));
  let overall = Math.round(evidenceConfidence * 0.24 + pageValue.score * 0.27 + reachScore * 0.15 + (["structural", "crawl_index", "blocked_access"].includes(defectClass) ? 18 : 0) + 22);
  overall = Math.max(0, Math.min(100, overall));
  const priority = fix.priority === "critical" ? "critical" : overall >= 82 ? "critical" : overall >= 68 ? "high" : overall >= 44 ? "medium" : "low";
  const developerOwned = fix.requires_developer || fix.difficulty === "developer" || (["structural", "crawl_index", "blocked_access", "semantic_schema"].includes(defectClass) && (fix.affected_pages?.length || 0) >= 2);
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
    site_fingerprint_vertical: fingerprint.primary_archetype,
    archetype_label: fingerprint.archetype_label,
    requires_developer: developerOwned,
    difficulty: developerOwned ? "developer" : fix.difficulty,
    status: developerOwned ? "needs_developer" : fix.status,
    who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this,
  };
}

function buildSiteFingerprint(body, pages, websiteUrl) {
  const safePages = Array.isArray(pages) ? pages : [];
  const text = [websiteUrl, body.business_name, body.business_type, body.cms_name, body.cms_platform, ...safePages.slice(0, 220).flatMap((page) => [page.url, page.final_url, page.path, page.title, page.h1, page.meta_description, page.page_template_family, page.estimated_page_intent, ...(Array.isArray(page.schema_types) ? page.schema_types : [])])].join(" ").toLowerCase();
  const pathText = safePages.slice(0, 220).map((page) => cleanPath(page.url || page.final_url || page.path || "").toLowerCase()).join(" ");
  let primary = "general";
  let label = "general website";
  let priorityPages = ["homepage", "contact", "services/products", "pricing/quote", "trust pages"];
  let priorityIssues = ["crawlability", "indexability", "trust", "broken pages", "schema", "metadata on key pages"];
  let demote = ["archives", "tags", "pagination"];
  let moneyPatterns = ["/contact", "/services", "/products", "/pricing"];

  if (hasAny(`${text} ${pathText}`, ["centerstreetlending", "center street lending", "fix-and-flip", "fix and flip", "hard money", "bridge loan", "private lending", "lending", "/loans", "/loan", "/apply-now", "/request-a-payoff", "/document-exchange"])) {
    primary = "finance_insurance_lead_gen";
    label = "finance / insurance / lead generation";
    priorityPages = ["loan program pages", "application pages", "quote/contact forms", "calculator or rate pages", "location pages"];
    priorityIssues = ["indexability", "canonicalization", "trust pages", "schema", "broken lead paths", "form/application flow reliability"];
    demote = ["old news", "tag archives", "blog pagination", "generic metadata on low-value articles"];
    moneyPatterns = ["/loan", "/loans", "/loan-overview", "/apply", "/apply-now", "/request-a-payoff", "/document-exchange", "/locations", "/fix-and-flip", "/contact"];
  } else if (hasAny(`${text} ${pathText}`, ["funbooker", "/annonce/", "/voir", "activité", "activite", "cadeau", "coffret", "loisir", "reservation", "réservation", "booking", "ticket", "stage", "atelier"])) {
    primary = "booking_experiences_marketplace";
    label = "booking / experiences marketplace";
    priorityPages = ["listing/category pages", "activity/detail pages", "location pages", "booking and checkout paths", "gift/ticket pages"];
    priorityIssues = ["JavaScript rendering", "crawlable listing content", "booking route boundaries", "schema", "blocked listings", "duplicate templates"];
    demote = ["old editorial posts", "tag archives", "low-value pagination", "one-off metadata on inactive listings"];
    moneyPatterns = ["/booking", "/reservation", "/activity", "/activite", "/activité", "/annonce", "/voir", "/cadeau", "/coffret", "/loisir", "/ticket"];
  } else if (hasAny(`${text} ${pathText}`, ["product", "produit", "shop", "boutique", "cart", "panier", "checkout", "price", "sku", "collection", "category", "brand", "shopify"])) {
    primary = "ecommerce_specialty_retail";
    label = "ecommerce / specialty retail";
    priorityPages = ["product pages", "collection/category pages", "brand pages", "cart/checkout route boundaries", "shipping/returns/trust pages"];
    priorityIssues = ["product/category indexability", "product schema", "canonicalization", "blocked product pages", "template image-alt issues"];
    demote = ["old blog posts", "tag archives", "generic metadata on inactive products"];
    moneyPatterns = ["/products/", "/product/", "/produit/", "/collections/", "/collection/", "/category/", "/categorie/", "/shop", "/checkout"];
  } else if (hasAny(`${text} ${pathText}`, ["blog", "news", "article", "guide", "resources", "insights", "newsletter", "subscribe"])) {
    primary = "content_blog";
    label = "content / blog-heavy site";
    priorityPages = ["pillar guides", "category hubs", "newsletter/subscription pages", "author/trust pages", "contact/conversion pages"];
    priorityIssues = ["duplicate/thin content", "author/reviewer trust", "internal linking", "canonicalization", "index bloat", "schema"];
  }

  const pagesFound = getFirstNumber([body?.scan_coverage?.pages_found, body?.pages_found, body?.technical_audit_summary?.pages_found, safePages.length]);
  const pagesCrawled = getFirstNumber([body?.scan_coverage?.pages_crawled, body?.pages_crawled, body?.technical_audit_summary?.pages_crawled, safePages.length]);
  const routeBoundaryCount = safePages.filter((page) => isRouteBoundaryCandidate(page.url || page.final_url || page.path) || isInternalAppRoute(page.url || page.final_url || page.path)).length;
  const blockedAccessPages = safePages.filter(isBlockedAccessPage).length;
  const hostname = safeHostname(websiteUrl);

  return {
    primary_archetype: primary,
    secondary_archetype: "",
    archetype_label: label,
    vertical: primary,
    vertical_label: label,
    vertical_confidence: primary === "general" ? 0.35 : 0.9,
    business_model: primary === "booking_experiences_marketplace" ? "booking_or_reservation" : primary === "finance_insurance_lead_gen" ? "regulated_or_trust_lead_generation" : primary === "ecommerce_specialty_retail" ? "catalog_or_ecommerce" : "content_or_general_business",
    size_band: Math.max(pagesFound, pagesCrawled, safePages.length) >= 1000 ? "enterprise" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 150 ? "mid_market" : Math.max(pagesFound, pagesCrawled, safePages.length) >= 30 ? "smb" : "micro",
    pages_found: pagesFound,
    pages_crawled: pagesCrawled,
    sampled_pages_sent_to_ai: safePages.length,
    localization: detectLocalization(safePages, websiteUrl),
    render_mode: safePages.filter((page) => page.client_rendering_suspected).length >= 3 ? "js_heavy_suspected" : "raw_html_first",
    regulatory_sensitivity: primary === "finance_insurance_lead_gen" ? "trust_or_regulated" : "standard",
    likely_money_page_patterns: moneyPatterns,
    archetype_priority_pages: priorityPages,
    archetype_priority_issues: priorityIssues,
    archetype_demotions: demote,
    route_boundary_count: routeBoundaryCount,
    route_boundary_risk: routeBoundaryCount >= 4 ? "high" : routeBoundaryCount > 0 ? "medium" : "low",
    blocked_access_pages: blockedAccessPages,
    free_base44_subdomain: hostname.endsWith(".base44.app"),
    scoring_model: "deno_safety_fallback_v5",
  };
}

function addBucket(buckets, rule, category, family, page, title, explanation, why, recommendation, difficulty) {
  const key = `${rule}|${family}`;
  if (!buckets.has(key)) buckets.set(key, { rule, category, family, pages: [], title, explanation, why, recommendation, difficulty, currentValue: explanation });
  buckets.get(key).pages.push(page);
}

function unwrapScanPayload(value) {
  let current = value || {};
  for (let i = 0; i < 5; i += 1) {
    if (typeof current === "string") current = parseJsonObject(current);
    if (looksLikeScanPayload(current)) return current;
    if (looksLikeScanPayload(current?.scan)) { current = current.scan; continue; }
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
function isFailedPage(page) { const status = Number(page?.status_code || page?.status || 0); if (status >= 400 && status !== 429) return true; const error = String(page?.fetch_error || page?.error || "").toLowerCase(); return hasAny(error, ["404", "410", "500", "503", "not found", "server error"]); }
function isBlockedAccessPage(page) { const status = Number(page?.status_code || page?.status || 0); const text = `${page?.fetch_error || ""} ${page?.title || ""} ${page?.content_type || ""}`.toLowerCase(); return status === 429 || hasAny(text, ["rate limit", "too many requests", "connection verification", "bot protection", "access denied", "cloudflare"]); }
function pageEvidenceUrl(page) { return page?.url || page?.final_url || page?.path || page?.page_url || "/"; }
function evidenceExtra(group) { return { status_codes: Array.from(new Set(group.map((page) => Number(page?.status_code || page?.status || 0)).filter(Boolean))), source_pages: Array.from(new Set(group.flatMap((page) => Array.isArray(page?.source_pages) ? page.source_pages : []))).slice(0, 30), link_text_samples: Array.from(new Set(group.flatMap((page) => Array.isArray(page?.link_text_samples) ? page.link_text_samples : []))).slice(0, 12), url_confidence: group.some((page) => page?.url_confidence === "linked_but_failed") ? "linked_but_failed" : group[0]?.url_confidence || "scanner_evidence", current_value: group.map((page) => `${cleanPath(pageEvidenceUrl(page))}: HTTP ${page?.status_code || page?.status || "failed"}`).slice(0, 8).join("; ") }; }
function computeHealthScore(fixes, pages) { let score = 92; for (const fix of fixes || []) { if (fix.priority === "critical") score -= 12; else if (fix.priority === "high") score -= 8; else if (fix.priority === "medium") score -= 4; else score -= 1; } if (!pages || pages.length === 0) score = Math.min(score, 86); return Math.max(35, Math.min(98, score)); }
function scorePageValue(url, fingerprint, body) { const path = cleanPath(url).toLowerCase(); let score = 35; if (path === "/" || path.endsWith("/index.html")) score += 35; if ((fingerprint.likely_money_page_patterns || []).some((pattern) => path.includes(pattern))) score += 24; if (hasAny(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "annonce", "voir", "cadeau", "coffret", "loisir", "pricing", "demo", "signup", "product", "products", "collection", "collections", "checkout", "loan", "loans", "apply", "payoff", "document-exchange", "locations", "fix-and-flip"])) score += 24; if (isRouteBoundaryCandidate(path) || isInternalAppRoute(path)) score += 32; if (isLowValuePage(path)) score -= 35; const clamped = Math.max(0, Math.min(100, score)); const classification = isRouteBoundaryCandidate(path) || isInternalAppRoute(path) ? "internal_or_auth_route" : clamped >= 70 ? "money_page" : clamped <= 30 ? "low_value" : "standard"; return { score: clamped, classification, label: classification === "internal_or_auth_route" ? "Route-boundary candidate" : classification === "money_page" ? "Important business page" : classification === "low_value" ? "Lower-priority archive/tag page" : "Standard page" }; }
function classifyDefectClass(fix) { const text = `${fix?.rule || ""} ${fix?.category || ""} ${fix?.issue_title || ""} ${fix?.title || ""} ${fix?.current_value || ""}`.toLowerCase(); if (hasAny(text, ["429", "blocked", "rate limit", "bot protection", "connection verification"])) return "blocked_access"; if (hasAny(text, ["route_boundary", "internal_route", "login", "account", "checkout", "dashboard", "noindex", "indexability"])) return "crawl_index"; if (hasAny(text, ["javascript", "render", "canonical", "redirect", "500", "503", "404", "410", "server_error", "broken_page", "template", "shared pattern", "similar pages"])) return "structural"; if (hasAny(text, ["schema", "structured"])) return "semantic_schema"; if (hasAny(text, ["trust", "privacy", "terms", "legal", "about", "contact", "review", "methodology"])) return "content_trust"; if (hasAny(text, ["meta", "title", "description", "image_alt_text", "alt text"])) return "metadata"; return "general"; }
function defaultSteps({ category, rule, difficulty, recommendedValue }) { if (difficulty === "developer" || /429|blocked|rate_limited|server_error|404|410|broken|canonical|redirect|route_boundary|indexability|template/i.test(String(rule || category || ""))) { if (/429|blocked|rate_limited/i.test(String(rule || ""))) return ["Send the grouped affected URLs to your web person.", "Check CDN, firewall, server, and bot-protection logs for HTTP 429 or verification responses.", "Confirm whether Googlebot and normal users can load the pages.", "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.", "Run FixList again to confirm the affected pages load."]; if (/404|410|broken/i.test(String(rule || category || ""))) return ["Send the affected URLs and source-page evidence to your web person.", "Decide whether each URL should be restored, redirected, or removed from internal links.", "Update the source links or add 301 redirects to the closest relevant live page.", "Run FixList again to confirm the URLs no longer fail."]; return ["Send this recommendation to your web person.", "Update the routing, canonical, schema, indexability, or shared template configuration.", "Publish the change and rerun FixList to verify it."]; } if (category === "image_alt_text") return ["Open the affected page or template.", "Add short, specific alt text to meaningful images.", "Publish the update and run FixList again."]; return ["Open the affected page or template.", cleanString(recommendedValue) || "Apply the recommended change.", "Publish the update and run FixList again."]; }
function friendlyCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function getTemplateFamily(url = "") { const path = cleanPath(url).toLowerCase(); if (/\/annonce\/.*\/voir/.test(path) || /\/annonce\//.test(path)) return "activity_detail"; if (/\/loans?\/|\/loan-overview|\/apply-now|\/request-a-payoff|\/document-exchange|\/locations\//.test(path)) return "conversion"; if (isRouteBoundaryCandidate(path)) return "route_boundary"; if (/checkout|cart|booking|reservation|ticket_order|gift_voucher|cadeau|coffret/.test(path)) return "booking_or_checkout"; if (/\/products?\/|\/p\//.test(path)) return "product_page"; if (/\/collections?\/|\/category\/|\/categorie\/|listing|show|marque|brand/.test(path)) return "collection_page"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz|pret|credit/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog|article/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv|dmca|ccpa/.test(path)) return "legal_info"; return "standard"; }
function familyLabel(family) { const map = { activity_detail: "activity/detail", booking_or_checkout: "booking", conversion: "conversion", contact: "contact", guide: "guide", legal_info: "legal info", product_page: "product", collection_page: "collection", route_boundary: "route-boundary", standard: "standard" }; return map[family] || family || "standard"; }
function isLowValuePage(url = "") { const path = cleanPath(url).toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; return ["/actualites/", "/news/", "/archive/", "/archives/", "/tag/", "/tags/", "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag="].some((pattern) => path.includes(pattern)); }
function isRouteBoundaryCandidate(url = "") { const path = cleanPath(url).toLowerCase(); return ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"].some((pattern) => path.includes(pattern)); }
function isInternalAppRoute(url = "") { const path = cleanPath(url).toLowerCase(); return ["/admin", "/developer", "/assistant", "/billing", "/login", "/register", "/forgot-password", "/reset-password", "/dashboard", "/issues", "/reports", "/crawl-status", "/metadata", "/canonicals", "/redirects", "/js-rendering", "/competitors", "/account", "/my-account", "/cart", "/checkout"].some((pattern) => path.includes(pattern)); }
function groupByTemplate(fixes) { const groups = new Map(); for (const fix of fixes || []) { const family = fix.page_template_family || "site"; const list = groups.get(family) || []; list.push(fix); groups.set(family, list); } return Array.from(groups.entries()).map(([template_family, items]) => ({ template_family, count: items.length, top_recommendations: items.slice(0, 5) })).slice(0, 12); }
function collectArrays(values) { const output = []; for (const value of values || []) { if (Array.isArray(value)) output.push(...value); } return output; }
function pickFirstNonEmptyArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function dedupePages(pages) { const seen = new Set(); const output = []; for (const page of pages || []) { const key = cleanPath(pageEvidenceUrl(page)); if (!key || seen.has(key)) continue; seen.add(key); output.push(page); } return output; }
function compareFixes(a, b) { const priorityScore = { critical: 4, high: 3, medium: 2, low: 1 }; return (Number(b.overall_priority_score || 0) + (priorityScore[b.priority] || 0) * 100) - (Number(a.overall_priority_score || 0) + (priorityScore[a.priority] || 0) * 100); }
function parseJsonObject(value) { try { return JSON.parse(String(value || "{}")); } catch { return {}; } }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function cleanPath(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const url = new URL(raw); return `${url.pathname || "/"}${url.search || ""}` || "/"; } catch { return raw.startsWith("/") ? raw : `/${raw}`; } }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function hasAny(text, needles) { const haystack = String(text || "").toLowerCase(); return (needles || []).some((needle) => haystack.includes(String(needle || "").toLowerCase())); }
function detectLocalization(pages, websiteUrl) { const text = [websiteUrl, ...pages.slice(0, 100).map((page) => page?.url || page?.final_url || "")].join(" ").toLowerCase(); const hits = (text.match(/\/(fr|en|es|de|it|nl|pt|ca|us|uk)([-_\/]|$)/g) || []).length; if (hits >= 4) return "multi_language_or_multi_country"; if (hits > 0) return "single_locale_subfolder"; return "single_language_or_unknown"; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function jsonResponse(payload, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }); }
