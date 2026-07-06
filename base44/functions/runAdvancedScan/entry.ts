import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runAdvancedScan_v8_reliable_debug_no_robots_block";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const USER_AGENT =
  "Mozilla/5.0 (compatible; SEOAutopilotBot/1.0; +https://base44.app)";

const BROWSERLESS_TOKEN = Deno.env.get("BROWSERLESS_TOKEN") || "";
const BROWSERLESS_CONTENT_ENDPOINT =
  Deno.env.get("BROWSERLESS_CONTENT_ENDPOINT") ||
  "https://production-sfo.browserless.io/content";

const BROWSER_RENDER_MODE = String(
  Deno.env.get("BROWSER_RENDER_MODE") || "blocked_only"
).toLowerCase();

const BROWSER_RENDER_TIMEOUT_MS = Number(
  Deno.env.get("BROWSER_RENDER_TIMEOUT_MS") || 30000
);

const ENV_MAX_BROWSER_RENDER_ATTEMPTS = Math.max(
  0,
  Number(Deno.env.get("MAX_BROWSER_RENDER_ATTEMPTS_PER_SCAN") || 1)
);

const FETCH_TIMEOUT_MS = 12000;
const SITEMAP_FETCH_TIMEOUT_MS = 8000;

const MODE_LIMITS: Record<
  string,
  {
    max_pages: number;
    max_competitors: number;
    crawl_timeout_ms: number;
    concurrency: number;
    use_sitemap: boolean;
  }
> = {
  basic: {
    max_pages: 25,
    max_competitors: 0,
    crawl_timeout_ms: 35000,
    concurrency: 3,
    use_sitemap: false,
  },
  quick: {
    max_pages: 40,
    max_competitors: 1,
    crawl_timeout_ms: 45000,
    concurrency: 3,
    use_sitemap: true,
  },
  deep: {
    max_pages: 85,
    max_competitors: 2,
    crawl_timeout_ms: 75000,
    concurrency: 4,
    use_sitemap: true,
  },
  advanced: {
    max_pages: 150,
    max_competitors: 3,
    crawl_timeout_ms: 90000,
    concurrency: 5,
    use_sitemap: true,
  },
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: CORS_HEADERS,
    });
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);

    if (!user) {
      return jsonResponse(
        {
          success: false,
          error: "Unauthorized",
        },
        401
      );
    }

    const body = await safeReadJson(req);
    const budget = resolveBudget(body);

    const websiteUrl = normalizeWebsiteUrl(body.website_url || body.url || "");

    if (!websiteUrl) {
      return jsonResponse(
        {
          success: false,
          error: "Missing or invalid website_url.",
        },
        400
      );
    }

    const deadlineAt = Date.now() + budget.crawl_timeout_ms - 3000;

    const crawlResult = await crawlWebsite({
      startUrl: websiteUrl,
      body,
      budget,
      deadlineAt,
    });

    const screamingFrogLite = runScreamingFrogLiteAudit({
      pages: crawlResult.pages,
      startUrl: websiteUrl,
    });

    const coverageFindings = buildCoverageFindings({
      pages: crawlResult.pages,
      startUrl: websiteUrl,
      crawlResult,
    });

    const followupFindings = buildFollowupScanFindings({
      followups: crawlResult.recommended_followup_scans,
      startUrl: websiteUrl,
    });

    const allRawFindings = [
      ...coverageFindings,
      ...followupFindings,
      ...screamingFrogLite.raw_findings,
    ];

    const groupedFindings = groupFindings(allRawFindings);

    let competitorResult = {
      competitor_results: [] as any[],
      competitor_opportunities: [] as any[],
      browser_render_attempts_used: 0,
      browser_render_attempts_max: 0,
      skipped: false,
      reason: "",
    };

    if (Date.now() < deadlineAt - 12000 && budget.max_competitors > 0) {
      competitorResult = await analyzeCompetitors({
        body,
        ownPages: crawlResult.pages,
        budget,
        deadlineAt,
      });
    } else {
      competitorResult.skipped = true;
      competitorResult.reason =
        "Competitor checks were skipped to keep the main scan reliable.";
    }

    const healthScore = calculateHealthScore({
      pages: crawlResult.pages,
      findings: groupedFindings,
      technicalSummary: screamingFrogLite.technical_audit_summary,
      startUrl: websiteUrl,
    });

    const scanSummary = buildScanSummary({
      websiteUrl,
      body,
      healthScore,
      pages: crawlResult.pages,
      findings: groupedFindings,
      technicalSummary: screamingFrogLite.technical_audit_summary,
      crawlResult,
    });

    const crawlWarnings = [
      ...crawlResult.warnings,
      ...buildFriendlyWarnings({
        pages: crawlResult.pages,
        crawlResult,
      }),
    ];

    return jsonResponse({
      success: true,
      version: VERSION,

      website_url: websiteUrl,
      business_name: body.business_name || "",
      scan_mode: budget.scan_mode,

      max_pages_requested: body.max_pages || null,
      max_pages_effective: budget.max_pages,
      max_competitors_effective: budget.max_competitors,

      pages_found: crawlResult.pages_found,
      pages_crawled: crawlResult.pages.length,
      queued_remaining: crawlResult.queued_remaining,

      health_score: healthScore,
      seo_score: healthScore,

      scan_summary: scanSummary,
      site_summary: scanSummary,

      important_page_patterns: crawlResult.important_page_patterns,
      deprioritized_page_patterns: crawlResult.deprioritized_page_patterns,
      recommended_followup_scans: crawlResult.recommended_followup_scans,
      sitemap_priority_summary: crawlResult.sitemap_priority_summary,

      technical_audit_summary: screamingFrogLite.technical_audit_summary,
      screaming_frog_lite: {
        enabled: true,
        audit_profile: "screaming_frog_lite",
        raw_findings_count: screamingFrogLite.raw_findings.length,
        grouped_findings_count: groupedFindings.length,
      },

      browser_rendering: {
        enabled: Boolean(BROWSERLESS_TOKEN),
        provider: BROWSERLESS_TOKEN ? "browserless" : "",
        mode: BROWSER_RENDER_MODE,
        max_attempts_per_scan: budget.max_browser_render_attempts,
        crawl_attempts_used: crawlResult.browser_render_attempts_used,
        competitor_attempts_used:
          competitorResult.browser_render_attempts_used || 0,
        crawl_attempts_max: crawlResult.browser_render_attempts_max,
        competitor_attempts_max:
          competitorResult.browser_render_attempts_max || 0,
        usage_policy:
          "Browser rendering is used only when a starting page, start variant, or selected high-priority page needs a rendered check.",
      },

      crawl_scope: crawlResult.crawl_scope,
      crawl_warnings: crawlWarnings,

      competitor_results: competitorResult.competitor_results,
      competitor_opportunities: competitorResult.competitor_opportunities,
      discovered_competitors: competitorResult.competitor_results,
      competitor_result: competitorResult,

      raw_findings: allRawFindings,
      grouped_findings: groupedFindings,
      raw_fixes: groupedFindings,

      fixes: groupedFindings,
      findings: groupedFindings,
      recommendations: groupedFindings,
      issues: groupedFindings,

      crawled_pages: crawlResult.pages,
      pages: crawlResult.pages,
      scanned_pages: crawlResult.pages,
      crawl_pages: crawlResult.pages,

      debug: {
        version: VERSION,
        budget,
        screaming_frog_lite_enabled: true,
        audit_profile: "screaming_frog_lite",
        sitemap_entries_found: crawlResult.sitemap_entries_found,
        importance_strategy: crawlResult.sitemap_priority_summary,
        skipped_junk_urls_count: crawlResult.skipped_junk_urls_count,
        skipped_outside_prefix_count: crawlResult.skipped_outside_prefix_count,
        start_url_candidates: crawlResult.start_url_candidates,
        fetch_error_class_counts: countFetchErrorClasses(crawlResult.pages),
        robots_policy:
          "robots.txt is used to discover sitemap URLs only. Disallow rules are not enforced in this version.",
        request_received_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    return jsonResponse(
      {
        success: false,
        version: VERSION,
        error: getErrorMessage(error),
      },
      500
    );
  }
});

/* -------------------------------------------------------------------------- */
/* Request helpers                                                             */
/* -------------------------------------------------------------------------- */

async function safeReadJson(req: Request) {
  try {
    return await req.json();
  } catch {
    return {};
  }
}

function jsonResponse(data: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}

function resolveBudget(body: any) {
  const requestedMode = String(body.scan_mode || "deep").toLowerCase();
  const scanMode = MODE_LIMITS[requestedMode] ? requestedMode : "deep";
  const defaults = MODE_LIMITS[scanMode];

  const requestedMaxPages = Number(body.max_pages || 0);
  const requestedMaxCompetitors = Number(body.max_competitors || 0);
  const requestedTimeout = Number(body.crawl_timeout_ms || 0);

  const requestedBrowserAttempts =
    body.max_browser_render_attempts !== undefined
      ? Number(body.max_browser_render_attempts)
      : ENV_MAX_BROWSER_RENDER_ATTEMPTS;

  return {
    scan_mode: scanMode,

    max_pages:
      requestedMaxPages > 0
        ? Math.max(1, Math.min(defaults.max_pages, requestedMaxPages))
        : defaults.max_pages,

    max_competitors:
      requestedMaxCompetitors > 0
        ? Math.max(
            0,
            Math.min(defaults.max_competitors, requestedMaxCompetitors)
          )
        : defaults.max_competitors,

    max_browser_render_attempts: Math.max(
      0,
      Math.min(3, requestedBrowserAttempts)
    ),

    crawl_timeout_ms:
      requestedTimeout > 0
        ? Math.max(
            20000,
            Math.min(defaults.crawl_timeout_ms, requestedTimeout)
          )
        : defaults.crawl_timeout_ms,

    concurrency: defaults.concurrency,
    use_sitemap: defaults.use_sitemap,
  };
}

/* -------------------------------------------------------------------------- */
/* Crawler                                                                     */
/* -------------------------------------------------------------------------- */

async function crawlWebsite({
  startUrl,
  body,
  budget,
  deadlineAt,
}: {
  startUrl: string;
  body: any;
  budget: any;
  deadlineAt: number;
}) {
  const start = new URL(startUrl);
  const origin = start.origin;
  const baseDomain = getBaseDomain(start.hostname);

  const requestedPathPrefix = normalizeRequestedPathPrefix(
    body.crawl_path_prefix || body.start_path_prefix || ""
  );

  const crawlPathPrefix =
    requestedPathPrefix || detectLanguagePrefix(start.pathname);

  const browserRenderBudget = {
    used: 0,
    max: budget.max_browser_render_attempts,
  };

  const renderTemplateDecisionCache = new Map<string, boolean>();

  const warnings: string[] = [];

  const skippedStats = {
    junk_urls: 0,
    outside_prefix: 0,
  };

  const startUrlCandidates = buildStartUrlCandidates(startUrl);

  const sitemapEntries = budget.use_sitemap
    ? await discoverSitemapEntries({
        origin,
        pathPrefix: crawlPathPrefix,
        deadlineAt,
        maxUrls: budget.max_pages * 5,
        skippedStats,
      })
    : [];

  const sitemapEntryMap = new Map<string, any>();

  for (const entry of sitemapEntries) {
    sitemapEntryMap.set(cleanUrl(entry.url), entry);
  }

  const importanceProfile = buildImportanceProfile({
    startUrl,
    sitemapEntries,
    pathPrefix: crawlPathPrefix,
  });

  const queue: Array<{
    url: string;
    source: string;
    in_sitemap: boolean;
    importance_score: number;
    importance_reasons: string[];
  }> = [];

  const discovered = new Set<string>();
  const fetched = new Set<string>();
  const relatedSubdomains = new Map<string, any>();

  function addToQueue(url: string, source: string, inSitemap = false) {
    const cleaned = cleanUrl(url);

    if (!cleaned) return;
    if (discovered.has(cleaned)) return;

    const crawlCheck = shouldCrawlUrl({
      url: cleaned,
      origin,
      pathPrefix: crawlPathPrefix,
    });

    if (!crawlCheck.ok) {
      if (crawlCheck.reason === "junk") skippedStats.junk_urls += 1;
      if (crawlCheck.reason === "outside_prefix") {
        skippedStats.outside_prefix += 1;
      }
      return;
    }

    const sitemapEntry = sitemapEntryMap.get(cleaned) || null;

    const score = scoreUrlImportance({
      url: cleaned,
      source,
      startUrl,
      pathPrefix: crawlPathPrefix,
      profile: importanceProfile,
      sitemapEntry,
    });

    discovered.add(cleaned);

    insertSortedByImportance(queue, {
      url: cleaned,
      source,
      in_sitemap: inSitemap || Boolean(sitemapEntry),
      importance_score: score.score,
      importance_reasons: score.reasons,
    });
  }

  for (const candidate of startUrlCandidates) {
    addToQueue(
      candidate,
      cleanUrl(candidate) === cleanUrl(startUrl) ? "start" : "start_variant",
      sitemapEntryMap.has(cleanUrl(candidate))
    );
  }

  for (const entry of sitemapEntries) {
    addToQueue(entry.url, "sitemap", true);
    if (queue.length >= budget.max_pages * 4) break;
  }

  const pages: any[] = [];
  let consecutiveBlockedInternal = 0;
  let stoppedForRateLimit = false;

  while (
    queue.length > 0 &&
    pages.length < budget.max_pages &&
    Date.now() < deadlineAt
  ) {
    const batch: Array<{
      url: string;
      source: string;
      in_sitemap: boolean;
      importance_score: number;
      importance_reasons: string[];
    }> = [];

    while (
      batch.length < budget.concurrency &&
      queue.length > 0 &&
      pages.length + batch.length < budget.max_pages
    ) {
      const next = queue.shift();

      if (!next) break;

      const cleaned = cleanUrl(next.url);

      if (!cleaned || fetched.has(cleaned)) continue;

      fetched.add(cleaned);
      batch.push(next);
    }

    if (batch.length === 0) break;

    const batchResults = await Promise.all(
      batch.map((item) =>
        fetchAndExtractPage({
          url: item.url,
          source: item.source,
          origin,
          inSitemap: item.in_sitemap,
          importanceScore: item.importance_score,
          importanceReasons: item.importance_reasons,
          allowBrowserRender: shouldAllowBrowserRenderForQueueItem({
            item,
            renderTemplateDecisionCache,
          }),
          allowBlockedBrowserRender:
            item.source === "start" || item.source === "start_variant",
          browserRenderBudget,
          deadlineAt,
        })
      )
    );

    for (const page of batchResults) {
      if (
        crawlPathPrefix &&
        page.final_url &&
        !isInsidePathPrefix(page.final_url, crawlPathPrefix)
      ) {
        skippedStats.outside_prefix += 1;
        continue;
      }

      pages.push(page);

      collectRelatedSubdomains({
        page,
        startHost: start.hostname,
        baseDomain,
        relatedSubdomains,
      });

      const isInternalBlocked =
        page.source !== "start" &&
        page.source !== "start_variant" &&
        page.is_scanner_blocked === true;

      if (isInternalBlocked) {
        consecutiveBlockedInternal += 1;
      } else if (page.status_code > 0) {
        consecutiveBlockedInternal = 0;
      }

      const readablePages = pages.filter(
        (item) =>
          item.status_code >= 200 &&
          item.status_code < 300 &&
          !item.is_scanner_blocked &&
          Number(item.word_count || 0) > 50
      ).length;

      const blockedInternalPages = pages.filter(
        (item) =>
          item.source !== "start" &&
          item.source !== "start_variant" &&
          item.is_scanner_blocked
      ).length;

      const minReadablePagesBeforeEarlyStop =
        budget.scan_mode === "advanced"
          ? 80
          : budget.scan_mode === "deep"
            ? 45
            : 20;

      const nearDeadline = Date.now() > deadlineAt - 12000;

      const blockedRatio = blockedInternalPages / Math.max(1, pages.length);

      const enoughUsefulPagesBeforeStopping =
        readablePages >= minReadablePagesBeforeEarlyStop || nearDeadline;

      if (
        enoughUsefulPagesBeforeStopping &&
        blockedInternalPages >= 25 &&
        blockedRatio > 0.45
      ) {
        stoppedForRateLimit = true;
        break;
      }

      if (enoughUsefulPagesBeforeStopping && consecutiveBlockedInternal >= 20) {
        stoppedForRateLimit = true;
        break;
      }

      if (
        page.status_code >= 200 &&
        page.status_code < 300 &&
        !page.is_scanner_blocked
      ) {
        for (const link of page.internal_links || []) {
          if (pages.length + queue.length >= budget.max_pages * 4) break;

          addToQueue(
            link,
            page.source === "start" || page.source === "start_variant"
              ? "homepage_link"
              : "internal",
            sitemapEntryMap.has(cleanUrl(link))
          );
        }
      }
    }

    if (stoppedForRateLimit) break;
  }

  if (Date.now() >= deadlineAt) {
    warnings.push(
      "The scan returned a partial result before the function timeout limit."
    );
  }

  if (stoppedForRateLimit) {
    warnings.push(
      "Some internal pages could not be checked because the website appeared to limit crawler requests. The Fix List is based on the pages that were readable."
    );
  }

  if (crawlPathPrefix) {
    warnings.push(
      `The scan was locked to ${crawlPathPrefix} pages so unrelated sections were ignored.`
    );
  }

  if (skippedStats.junk_urls > 0) {
    warnings.push(
      `${skippedStats.junk_urls} low-value encoded or tracking-style URLs were skipped so the scan could focus on useful pages.`
    );
  }

  const recommendedFollowups = buildRecommendedFollowupScans({
    relatedSubdomains,
    startUrl,
    baseDomain,
  });

  return {
    pages,
    pages_found: discovered.size,
    queued_remaining: queue.length,
    warnings,
    browser_render_attempts_used: browserRenderBudget.used,
    browser_render_attempts_max: browserRenderBudget.max,
    crawl_scope: {
      locked_to_start_language: Boolean(crawlPathPrefix),
      start_path_prefix: crawlPathPrefix || "",
      origin,
      topic_dossier_prefix: importanceProfile.topic_dossier_prefix || "",
    },
    sitemap_entries_found: sitemapEntries.length,
    important_page_patterns: importanceProfile.important_page_patterns,
    deprioritized_page_patterns: importanceProfile.deprioritized_page_patterns,
    recommended_followup_scans: recommendedFollowups,
    skipped_junk_urls_count: skippedStats.junk_urls,
    skipped_outside_prefix_count: skippedStats.outside_prefix,
    start_url_candidates: startUrlCandidates,
    sitemap_priority_summary: {
      strategy:
        "The scanner reads sitemap URLs first, learns common URL folders, tries cleaner start URL variants, boosts likely landing pages, demotes listing/archive/news/filter/encoded pages, and keeps the scan focused inside the requested folder or language path.",
      topic_dossier_prefix: importanceProfile.topic_dossier_prefix || "",
      sitemap_entries_found: sitemapEntries.length,
      important_page_patterns: importanceProfile.important_page_patterns,
      deprioritized_page_patterns: importanceProfile.deprioritized_page_patterns,
      max_pages_enforced: budget.max_pages,
      related_subdomains_found: recommendedFollowups.length,
      skipped_junk_urls_count: skippedStats.junk_urls,
      skipped_outside_prefix_count: skippedStats.outside_prefix,
      start_url_candidates: startUrlCandidates,
    },
  };
}

function shouldAllowBrowserRenderForQueueItem({
  item,
  renderTemplateDecisionCache,
}: {
  item: {
    url: string;
    source: string;
    importance_score: number;
  };
  renderTemplateDecisionCache: Map<string, boolean>;
}) {
  if (item.source === "start" || item.source === "start_variant") {
    return true;
  }

  if (BROWSER_RENDER_MODE !== "auto") {
    return false;
  }

  const template = makeUrlTemplate(item.url);

  if (template && renderTemplateDecisionCache.has(template)) {
    return Boolean(renderTemplateDecisionCache.get(template));
  }

  const decision = item.importance_score >= 150;

  if (template) {
    renderTemplateDecisionCache.set(template, decision);
  }

  return decision;
}

function insertSortedByImportance(queue: Array<any>, item: any) {
  let low = 0;
  let high = queue.length;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);

    if (Number(queue[middle]?.importance_score || 0) < item.importance_score) {
      high = middle;
    } else {
      low = middle + 1;
    }
  }

  queue.splice(low, 0, item);
}

async function fetchAndExtractPage({
  url,
  source,
  origin,
  inSitemap,
  importanceScore,
  importanceReasons,
  allowBrowserRender,
  allowBlockedBrowserRender,
  browserRenderBudget,
  deadlineAt,
}: {
  url: string;
  source: string;
  origin: string;
  inSitemap: boolean;
  importanceScore: number;
  importanceReasons: string[];
  allowBrowserRender: boolean;
  allowBlockedBrowserRender: boolean;
  browserRenderBudget: { used: number; max: number };
  deadlineAt: number;
}) {
  let html = "";
  let statusCode = 0;
  let finalUrl = url;
  let fetchError = "";
  let fetchErrorClass = "";
  let fetchedByBrowser = false;

  const fetchResult = await fetchHtmlWithRetry(url);

  html = fetchResult.html;
  statusCode = fetchResult.status_code;
  finalUrl = fetchResult.final_url || url;
  fetchError = fetchResult.fetch_error;
  fetchErrorClass = fetchResult.fetch_error_class;

  let page = extractPageFromHtml({
    url,
    finalUrl,
    html,
    statusCode,
    source,
    origin,
    inSitemap,
    fetchError,
    fetchErrorClass,
    fetchedByBrowser,
    importanceScore,
    importanceReasons,
  });

  const shouldTryRender =
    Date.now() < deadlineAt - 8000 &&
    allowBrowserRender &&
    shouldRetryWithBrowser(page, allowBlockedBrowserRender) &&
    browserRenderBudget.used < browserRenderBudget.max;

  if (shouldTryRender) {
    try {
      browserRenderBudget.used += 1;

      const rendered = await fetchWithBrowserless(url);

      if (rendered.html) {
        fetchedByBrowser = true;
        html = rendered.html;
        statusCode = rendered.status_code || statusCode || 0;
        finalUrl = rendered.final_url || finalUrl || url;
        fetchError = "";
        fetchErrorClass = "";

        page = extractPageFromHtml({
          url,
          finalUrl,
          html,
          statusCode,
          source,
          origin,
          inSitemap,
          fetchError: "",
          fetchErrorClass: "",
          fetchedByBrowser,
          importanceScore,
          importanceReasons,
        });
      }
    } catch (error) {
      page.browser_render_error = getErrorMessage(error);
    }
  }

  return page;
}

async function fetchHtmlWithRetry(url: string) {
  let html = "";
  let statusCode = 0;
  let finalUrl = url;
  let contentType = "";
  let fetchError = "";
  let fetchErrorClass = "";

  try {
    const response = await fetchWithTimeout(url, FETCH_TIMEOUT_MS);
    statusCode = response.status;
    finalUrl = response.url || url;
    contentType = response.headers.get("content-type") || "";
    fetchErrorClass = classifyFetchError(new Error(`HTTP ${statusCode}`), statusCode);

    if (shouldRetryFetch(fetchErrorClass)) {
      await sleep(jitterDelay());

      const retryResponse = await fetchWithTimeout(url, FETCH_TIMEOUT_MS);
      statusCode = retryResponse.status;
      finalUrl = retryResponse.url || finalUrl;
      contentType = retryResponse.headers.get("content-type") || "";
      fetchErrorClass = classifyFetchError(
        new Error(`HTTP ${statusCode}`),
        statusCode
      );

      html = /text\/html|application\/xhtml/i.test(contentType)
        ? await retryResponse.text()
        : "";
    } else {
      html = /text\/html|application\/xhtml/i.test(contentType)
        ? await response.text()
        : "";
    }

    if (!fetchErrorClass || fetchErrorClass === "other") {
      fetchErrorClass = "";
    }
  } catch (error) {
    fetchError = getErrorMessage(error);
    fetchErrorClass = classifyFetchError(error);

    if (shouldRetryFetch(fetchErrorClass)) {
      try {
        await sleep(jitterDelay());

        const retryResponse = await fetchWithTimeout(url, FETCH_TIMEOUT_MS);
        statusCode = retryResponse.status;
        finalUrl = retryResponse.url || url;
        contentType = retryResponse.headers.get("content-type") || "";
        html = /text\/html|application\/xhtml/i.test(contentType)
          ? await retryResponse.text()
          : "";
        fetchError = "";
        fetchErrorClass = classifyFetchError(
          new Error(`HTTP ${statusCode}`),
          statusCode
        );

        if (!fetchErrorClass || fetchErrorClass === "other") {
          fetchErrorClass = "";
        }
      } catch (retryError) {
        fetchError = getErrorMessage(retryError);
        fetchErrorClass = classifyFetchError(retryError);
      }
    }
  }

  return {
    html,
    status_code: statusCode,
    final_url: finalUrl,
    fetch_error: fetchError,
    fetch_error_class: fetchErrorClass,
  };
}

async function fetchWithTimeout(url: string, timeoutMs: number) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      method: "GET",
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "User-Agent": USER_AGENT,
        Accept:
          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
      },
    });
  } finally {
    clearTimeout(timeout);
  }
}

function classifyFetchError(error: unknown, statusCode = 0) {
  const message = getErrorMessage(error).toLowerCase();

  if ([403, 429, 503].includes(Number(statusCode || 0))) {
    return "blocked";
  }

  if (statusCode >= 500) {
    return "http_5xx";
  }

  if (message.includes("abort") || message.includes("timeout")) {
    return "timeout";
  }

  if (
    message.includes("dns") ||
    message.includes("name not resolved") ||
    message.includes("enotfound")
  ) {
    return "dns";
  }

  if (
    message.includes("tls") ||
    message.includes("ssl") ||
    message.includes("certificate")
  ) {
    return "tls";
  }

  if (!message || message === "http 0" || message === "http 200") {
    return "";
  }

  return "other";
}

function shouldRetryFetch(errorClass: string) {
  return ["timeout", "http_5xx", "other"].includes(errorClass);
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jitterDelay() {
  return 250 + Math.floor(Math.random() * 500);
}

function shouldRetryWithBrowser(page: any, allowBlockedBrowserRender: boolean) {
  if (!BROWSERLESS_TOKEN) return false;

  const renderNeed =
    Number(page.word_count || 0) < 80 && Number(page.script_count || 0) >= 15;

  if (
    allowBlockedBrowserRender &&
    (page.is_scanner_blocked ||
      [0, 403, 429, 503].includes(Number(page.status_code || 0)))
  ) {
    return true;
  }

  if (BROWSER_RENDER_MODE === "js_fallback" || BROWSER_RENDER_MODE === "auto") {
    return renderNeed;
  }

  return false;
}

async function fetchWithBrowserless(url: string) {
  const endpoint = new URL(BROWSERLESS_CONTENT_ENDPOINT);

  if (BROWSERLESS_TOKEN && !endpoint.searchParams.has("token")) {
    endpoint.searchParams.set("token", BROWSERLESS_TOKEN);
  }

  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    BROWSER_RENDER_TIMEOUT_MS
  );

  try {
    const response = await fetch(endpoint.toString(), {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url,
        waitForTimeout: 1000,
        viewport: {
          width: 1366,
          height: 900,
        },
        gotoOptions: {
          waitUntil: "networkidle2",
          timeout: BROWSER_RENDER_TIMEOUT_MS,
        },
        userAgent: USER_AGENT,
      }),
    });

    const html = await response.text();

    const finalUrl =
      response.headers.get("x-response-url") ||
      response.headers.get("browserless-final-url") ||
      response.headers.get("location") ||
      url;

    if (!response.ok) {
      throw new Error(
        `Browserless failed with status ${response.status}: ${html.slice(
          0,
          200
        )}`
      );
    }

    if (!html || html.trim().length < 50) {
      throw new Error("Browserless returned empty HTML.");
    }

    const visibleText = stripHtmlToText(html);
    const title = extractTitle(html);

    const renderedLooksBlocked = detectBlocked({
      html: "",
      text: visibleText,
      title,
      statusCode: response.status,
    });

    if (renderedLooksBlocked) {
      throw new Error("Browserless render still appears blocked.");
    }

    return {
      html,
      status_code: response.status || 200,
      final_url: finalUrl,
    };
  } finally {
    clearTimeout(timeout);
  }
}

/* -------------------------------------------------------------------------- */
/* Sitemap + importance scoring                                                */
/* -------------------------------------------------------------------------- */

async function discoverSitemapEntries({
  origin,
  pathPrefix,
  deadlineAt,
  maxUrls,
  skippedStats,
}: {
  origin: string;
  pathPrefix: string;
  deadlineAt: number;
  maxUrls: number;
  skippedStats: { junk_urls: number; outside_prefix: number };
}) {
  const sitemapCandidates = new Set<string>();

  sitemapCandidates.add(`${origin}/sitemap.xml`);
  sitemapCandidates.add(`${origin}/sitemap_index.xml`);

  try {
    const robots = await fetchText(
      `${origin}/robots.txt`,
      SITEMAP_FETCH_TIMEOUT_MS
    );

    for (const line of robots.split(/\r?\n/)) {
      const match = line.match(/^sitemap:\s*(.+)$/i);

      if (match?.[1]) {
        sitemapCandidates.add(match[1].trim());
      }
    }
  } catch {
    // robots.txt is optional. In this version, robots.txt is only used to find sitemaps.
  }

  const pageEntries = new Map<string, any>();
  const sitemapQueue = [...sitemapCandidates].slice(0, 10);
  const visitedSitemaps = new Set<string>();

  while (
    sitemapQueue.length > 0 &&
    pageEntries.size < maxUrls &&
    Date.now() < deadlineAt - 5000
  ) {
    const sitemapUrl = sitemapQueue.shift();

    if (!sitemapUrl || visitedSitemaps.has(sitemapUrl)) continue;

    visitedSitemaps.add(sitemapUrl);

    try {
      const xml = await fetchText(sitemapUrl, SITEMAP_FETCH_TIMEOUT_MS);

      const childSitemaps = parseSitemapIndexLocs(xml);

      for (const child of childSitemaps) {
        if (sitemapQueue.length >= 35) break;

        const cleanedChild = cleanUrl(child);

        if (cleanedChild && /\.xml(\?|$)/i.test(cleanedChild)) {
          sitemapQueue.push(cleanedChild);
        }
      }

      const entries = parseSitemapUrlEntries(xml);

      for (const entry of entries) {
        if (pageEntries.size >= maxUrls) break;

        const cleaned = cleanUrl(entry.url);

        if (!cleaned) continue;

        if (/\.xml(\?|$)/i.test(cleaned)) {
          if (sitemapQueue.length < 35) {
            sitemapQueue.push(cleaned);
          }
          continue;
        }

        const crawlCheck = shouldCrawlUrl({
          url: cleaned,
          origin,
          pathPrefix,
        });

        if (!crawlCheck.ok) {
          if (crawlCheck.reason === "junk") skippedStats.junk_urls += 1;
          if (crawlCheck.reason === "outside_prefix") {
            skippedStats.outside_prefix += 1;
          }
          continue;
        }

        pageEntries.set(cleaned, {
          ...entry,
          url: cleaned,
          source_sitemap: sitemapUrl,
        });
      }
    } catch {
      // Ignore sitemap fetch failures.
    }
  }

  return [...pageEntries.values()].slice(0, maxUrls);
}

function parseSitemapIndexLocs(xml: string) {
  const sitemapBlocks = [
    ...String(xml || "").matchAll(/<sitemap\b[^>]*>([\s\S]*?)<\/sitemap>/gi),
  ];

  return sitemapBlocks
    .map((block) => extractXmlTag(block[1], "loc"))
    .filter(Boolean);
}

function parseSitemapUrlEntries(xml: string) {
  const urlBlocks = [
    ...String(xml || "").matchAll(/<url\b[^>]*>([\s\S]*?)<\/url>/gi),
  ];

  if (urlBlocks.length > 0) {
    return urlBlocks
      .map((block) => {
        const content = block[1] || "";

        return {
          url: extractXmlTag(content, "loc"),
          lastmod: extractXmlTag(content, "lastmod"),
          priority: Number(extractXmlTag(content, "priority") || 0),
        };
      })
      .filter((entry) => entry.url);
  }

  return parseLocTags(xml).map((url) => ({
    url,
    lastmod: "",
    priority: 0,
  }));
}

function extractXmlTag(xml: string, tag: string) {
  const regex = new RegExp(`<${tag}\\b[^>]*>\\s*([^<]+)\\s*</${tag}>`, "i");
  const match = String(xml || "").match(regex);

  return decodeHtmlEntities(match?.[1] || "").trim();
}

function buildImportanceProfile({
  startUrl,
  sitemapEntries,
  pathPrefix,
}: {
  startUrl: string;
  sitemapEntries: any[];
  pathPrefix: string;
}) {
  const start = new URL(startUrl);
  const topicDossierPrefix = detectTopicDossierPrefix(
    start.pathname,
    pathPrefix
  );

  const folderStats = new Map<string, any>();

  for (const entry of sitemapEntries) {
    const folder = getPrimaryFolder(entry.url, pathPrefix);

    if (!folder) continue;

    if (!folderStats.has(folder)) {
      folderStats.set(folder, {
        folder,
        count: 0,
        average_depth_total: 0,
        demoted: isDemotedFolder(folder),
      });
    }

    const stat = folderStats.get(folder);
    stat.count += 1;
    stat.average_depth_total += getUrlDepth(entry.url);
  }

  const importantFolders = [...folderStats.values()]
    .map((stat) => ({
      ...stat,
      average_depth: stat.average_depth_total / Math.max(1, stat.count),
    }))
    .filter((stat) => {
      if (stat.demoted) return false;
      if (stat.count < 2) return false;
      if (stat.average_depth > 5.5) return false;
      return true;
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((stat) => stat.folder);

  const demotedFolders = [...folderStats.values()]
    .filter((stat) => stat.demoted)
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((stat) => stat.folder);

  const importantPagePatterns = unique([
    ...(topicDossierPrefix ? [topicDossierPrefix] : []),
    ...importantFolders,
  ]);

  const deprioritizedPagePatterns = unique([
    ...demotedFolders,
    "/listing/",
    "/show",
    "/actualite/",
    "/actualité/",
    "/blog/",
    "/news/",
    "/tag/",
    "/author/",
    "/search",
    "/page/",
    "encoded-url",
  ]);

  return {
    topic_dossier_prefix: topicDossierPrefix,
    important_folders: importantFolders,
    demoted_folders: demotedFolders,
    important_page_patterns: importantPagePatterns,
    deprioritized_page_patterns: deprioritizedPagePatterns,
  };
}

function scoreUrlImportance({
  url,
  source,
  startUrl,
  pathPrefix,
  profile,
  sitemapEntry,
}: {
  url: string;
  source: string;
  startUrl: string;
  pathPrefix: string;
  profile: any;
  sitemapEntry: any;
}) {
  let score = 0;
  const reasons: string[] = [];

  const cleanedUrl = cleanUrl(url);
  const cleanedStart = cleanUrl(startUrl);

  if (cleanedUrl === cleanedStart) {
    score += 10000;
    reasons.push("starting page");
  }

  if (source === "start") {
    score += 900;
    reasons.push("scan start");
  }

  if (source === "start_variant") {
    score += 880;
    reasons.push("cleaner start URL variant");
  }

  if (source === "homepage_link") {
    score += 180;
    reasons.push("linked from starting page");
  }

  if (source === "sitemap") {
    score += 90;
    reasons.push("found in sitemap");
  }

  if (source === "internal") {
    score += 25;
    reasons.push("found from internal link");
  }

  if (sitemapEntry) {
    score += 60;
    reasons.push("listed in sitemap");

    const sitemapPriority = Number(sitemapEntry.priority || 0);

    if (sitemapPriority > 0) {
      score += Math.round(sitemapPriority * 60);
      reasons.push(`sitemap priority ${sitemapPriority}`);
    }

    const recencyBoost = getLastmodRecencyBoost(sitemapEntry.lastmod);

    if (recencyBoost > 0) {
      score += recencyBoost;
      reasons.push("recent sitemap update");
    }
  }

  const depth = getUrlDepth(url);

  if (depth <= 1) {
    score += 120;
    reasons.push("short high-level URL");
  } else if (depth <= 3) {
    score += 60;
    reasons.push("clean landing-page depth");
  } else if (depth >= 6) {
    score -= 80;
    reasons.push("deep URL");
  }

  const folder = getPrimaryFolder(url, pathPrefix);

  if (folder && profile.important_folders.includes(folder)) {
    score += 130;
    reasons.push(`common important site folder: ${folder}`);
  }

  const topicPrefix = profile.topic_dossier_prefix;

  if (topicPrefix) {
    const path = normalizePath(new URL(url).pathname);

    if (path === topicPrefix || path.startsWith(`${topicPrefix}/`)) {
      score += 300;
      reasons.push(`inside starting topic folder ${topicPrefix}`);
    } else {
      score -= 280;
      reasons.push(`outside starting topic folder ${topicPrefix}`);
    }
  }

  const lowValuePenalty = getLowValueUrlPenalty(url, topicPrefix);

  if (lowValuePenalty.penalty > 0) {
    score -= lowValuePenalty.penalty;
    reasons.push(lowValuePenalty.reason);
  }

  if (looksLikeLandingPage(url)) {
    score += 70;
    reasons.push("looks like a landing page");
  }

  if (looksLikeListingDetail(url)) {
    score -= 240;
    reasons.push("looks like a listing/detail page");
  }

  if (looksLikeFilterOrPagination(url)) {
    score -= 180;
    reasons.push("looks like filtered or paginated page");
  }

  if (isLikelyEncodedOrJunkUrl(new URL(url).pathname)) {
    score -= 500;
    reasons.push("encoded or low-value URL");
  }

  if (pathPrefix && normalizePath(new URL(url).pathname) === pathPrefix) {
    score += 120;
    reasons.push("starting path prefix page");
  }

  return {
    score,
    reasons,
  };
}

function detectTopicDossierPrefix(pathname: string, pathPrefix: string) {
  const path = normalizePath(pathname);

  if (!path || path === "/") return "";

  if (pathPrefix && path === pathPrefix) {
    return pathPrefix;
  }

  if (pathPrefix && path.startsWith(`${pathPrefix}/`)) {
    return pathPrefix;
  }

  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) return "";

  const first = parts[0];

  if (!first || isDemotedSegment(first)) return "";

  return `/${first}`;
}

function getPrimaryFolder(url: string, pathPrefix: string) {
  try {
    const pathname = normalizePath(new URL(url).pathname);
    let path = pathname;

    if (pathPrefix && path.startsWith(pathPrefix)) {
      path = path.slice(pathPrefix.length) || "/";
    }

    const first = path.split("/").filter(Boolean)[0];

    if (first) return `/${first}/`;

    if (pathPrefix) return pathPrefix;

    return "";
  } catch {
    return "";
  }
}

function getUrlDepth(url: string) {
  try {
    return new URL(url).pathname.split("/").filter(Boolean).length;
  } catch {
    return 99;
  }
}

function getLastmodRecencyBoost(lastmod: string) {
  if (!lastmod) return 0;

  const time = new Date(lastmod).getTime();

  if (!Number.isFinite(time)) return 0;

  const ageDays = (Date.now() - time) / 86400000;

  if (ageDays <= 30) return 45;
  if (ageDays <= 180) return 30;
  if (ageDays <= 365) return 15;
  return 0;
}

function isDemotedFolder(folder: string) {
  const value = String(folder || "").toLowerCase();

  return [
    "/listing/",
    "/actualite/",
    "/actualité/",
    "/blog/",
    "/news/",
    "/tag/",
    "/author/",
    "/search/",
    "/page/",
    "/archive/",
    "/archives/",
    "/press/",
    "/presse/",
  ].some((part) => value.includes(part));
}

function isDemotedSegment(segment: string) {
  const value = String(segment || "").toLowerCase();

  return [
    "listing",
    "actualite",
    "actualité",
    "blog",
    "news",
    "tag",
    "author",
    "search",
    "page",
    "archive",
    "archives",
    "press",
    "presse",
  ].includes(value);
}

function getLowValueUrlPenalty(url: string, topicPrefix: string) {
  const parsed = new URL(url);
  const path = parsed.pathname.toLowerCase();

  const insideTopic =
    topicPrefix && (path === topicPrefix || path.startsWith(`${topicPrefix}/`));

  const newsLike =
    path.includes("/actualite/") ||
    path.includes("/actualité/") ||
    path.includes("/blog/") ||
    path.includes("/news/") ||
    path.includes("/archive/") ||
    path.includes("/archives/");

  if (newsLike) {
    return {
      penalty: insideTopic ? 90 : 230,
      reason: insideTopic
        ? "article/news page inside topic folder"
        : "article/news/archive page outside main topic",
    };
  }

  if (
    path.includes("/tag/") ||
    path.includes("/author/") ||
    path.includes("/search")
  ) {
    return {
      penalty: 220,
      reason: "tag, author, or search URL",
    };
  }

  return {
    penalty: 0,
    reason: "",
  };
}

function looksLikeLandingPage(url: string) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);

    if (parts.length <= 2) return true;

    const last = parts[parts.length - 1] || "";

    if (
      ["category", "categories", "place", "places", "activity", "activities"].some(
        (word) => parts.includes(word)
      )
    ) {
      return parts.length <= 4;
    }

    return !/\d{4}|\d{5,}/.test(last) && parts.length <= 4;
  } catch {
    return false;
  }
}

function looksLikeListingDetail(url: string) {
  try {
    const path = new URL(url).pathname.toLowerCase();

    if (path.includes("/listing/") && path.endsWith("/show")) return true;
    if (path.includes("/listing/")) return true;
    if (path.includes("/annonce/")) return true;
    if (path.includes("/item/")) return true;

    return false;
  } catch {
    return false;
  }
}

function looksLikeFilterOrPagination(url: string) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase();

    if (path.includes("/page/")) return true;
    if (path.includes("/filter/")) return true;
    if (parsed.searchParams.toString()) return true;

    return false;
  } catch {
    return false;
  }
}

/* -------------------------------------------------------------------------- */
/* HTML extraction                                                             */
/* -------------------------------------------------------------------------- */

function extractPageFromHtml({
  url,
  finalUrl,
  html,
  statusCode,
  source,
  origin,
  inSitemap,
  fetchError,
  fetchErrorClass,
  fetchedByBrowser,
  importanceScore,
  importanceReasons,
}: {
  url: string;
  finalUrl: string;
  html: string;
  statusCode: number;
  source: string;
  origin: string;
  inSitemap: boolean;
  fetchError: string;
  fetchErrorClass: string;
  fetchedByBrowser: boolean;
  importanceScore: number;
  importanceReasons: string[];
}) {
  const title = extractTitle(html);
  const metaDescription = extractMeta(html, "description");
  const robotsMeta = extractMeta(html, "robots");
  const viewport = extractMeta(html, "viewport");
  const canonicalUrl = extractCanonical(html, finalUrl);
  const h1s = extractAllH1(html);
  const text = stripHtmlToText(html);
  const wordCount = text ? text.split(/\s+/).filter(Boolean).length : 0;

  const scriptCount = countMatches(html, /<script\b/gi);
  const stylesheetCount = countMatches(html, /<link[^>]+rel=["']?stylesheet/gi);
  const imageCount = countMatches(html, /<img\b/gi);
  const missingAltImageCount = countImagesMissingAlt(html);
  const schemaCount = countMatches(
    html,
    /<script[^>]+type=["']application\/ld\+json["']/gi
  );
  const ogCount = countMatches(html, /<meta[^>]+property=["']og:/gi);

  const isScannerBlocked = detectBlocked({
    html,
    text,
    statusCode,
    title,
  });

  const internalLinks = extractInternalLinks(html, finalUrl, origin);
  const externalLinks = extractExternalLinks(html, finalUrl, origin);

  return {
    url: cleanUrl(url),
    final_url: cleanUrl(finalUrl || url),
    original_url: cleanUrl(url),
    source,
    status_code: statusCode,
    fetch_error: fetchError,
    fetch_error_class: fetchErrorClass || "",

    title,
    meta_description: metaDescription,
    h1: h1s[0] || "",
    h1s,
    h1_count: h1s.length,
    canonical_url: canonicalUrl,
    robots_meta: robotsMeta,
    viewport,

    word_count: wordCount,
    text_length: text.length,
    html_size: html.length,
    script_count: scriptCount,
    stylesheet_count: stylesheetCount,
    image_count: imageCount,
    missing_alt_image_count: missingAltImageCount,
    schema_count: schemaCount,
    open_graph_tag_count: ogCount,

    internal_links: internalLinks,
    internal_link_count: internalLinks.length,
    external_links: externalLinks,
    external_link_count: externalLinks.length,

    indexable: !/noindex/i.test(robotsMeta || ""),
    in_sitemap: inSitemap,
    is_scanner_blocked: isScannerBlocked,
    fetched_by_browser_render: fetchedByBrowser,

    importance_score: importanceScore,
    importance_reasons: importanceReasons,

    client_rendering_suspected:
      !isScannerBlocked && wordCount < 100 && scriptCount >= 15,

    template: makeUrlTemplate(url),
    extracted_at: new Date().toISOString(),
  };
}

function detectBlocked({
  html,
  text,
  statusCode,
  title,
}: {
  html: string;
  text: string;
  statusCode: number;
  title: string;
}) {
  if ([403, 429, 503].includes(Number(statusCode || 0))) return true;

  const visibleHaystack = `${title || ""} ${text || ""}`
    .toLowerCase()
    .slice(0, 6000);

  const challengePhrases = [
    "just a moment",
    "checking your browser",
    "enable javascript",
    "verify you are human",
    "captcha",
    "access denied",
    "are you a robot",
    "too many requests",
    "rate limit",
    "request blocked",
  ];

  if (challengePhrases.some((phrase) => visibleHaystack.includes(phrase))) {
    return true;
  }

  const vendorWords = [
    "cloudflare",
    "datadome",
    "akamai",
    "perimeterx",
    "imperva",
    "sucuri",
  ];

  const vendorChallengePhrases = [
    "just a moment",
    "checking your browser",
    "verify you are human",
    "captcha",
    "access denied",
    "are you a robot",
    "bot detection",
  ];

  const hasVendorWord = vendorWords.some((word) =>
    visibleHaystack.includes(word)
  );

  const hasVendorChallenge = vendorChallengePhrases.some((phrase) =>
    visibleHaystack.includes(phrase)
  );

  return hasVendorWord && hasVendorChallenge;
}

function stripHtmlToText(html: string) {
  if (!html) return "";

  return decodeHtmlEntities(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
      .replace(/<!--[\s\S]*?-->/g, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
  );
}

function extractTitle(html: string) {
  const match = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return decodeHtmlEntities((match?.[1] || "").replace(/\s+/g, " ").trim());
}

function extractMeta(html: string, name: string) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  const regexes = [
    new RegExp(
      `<meta[^>]+name=["']${escaped}["'][^>]+content=["']([^"']*)["'][^>]*>`,
      "i"
    ),
    new RegExp(
      `<meta[^>]+content=["']([^"']*)["'][^>]+name=["']${escaped}["'][^>]*>`,
      "i"
    ),
  ];

  for (const regex of regexes) {
    const match = html.match(regex);

    if (match?.[1]) {
      return decodeHtmlEntities(match[1].trim());
    }
  }

  return "";
}

function extractCanonical(html: string, baseUrl: string) {
  const match = html.match(
    /<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["'][^>]*>/i
  );

  if (!match?.[1]) return "";

  try {
    return cleanUrl(new URL(match[1], baseUrl).toString());
  } catch {
    return match[1];
  }
}

function extractAllH1(html: string) {
  const matches = [...html.matchAll(/<h1[^>]*>([\s\S]*?)<\/h1>/gi)];

  return matches
    .map((match) =>
      decodeHtmlEntities(
        String(match[1] || "")
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ")
          .trim()
      )
    )
    .filter(Boolean);
}

function extractInternalLinks(html: string, baseUrl: string, origin: string) {
  const links = extractLinks(html, baseUrl);

  return unique(
    links.filter((link) => {
      try {
        return new URL(link).origin === origin;
      } catch {
        return false;
      }
    })
  );
}

function extractExternalLinks(html: string, baseUrl: string, origin: string) {
  const links = extractLinks(html, baseUrl);

  return unique(
    links.filter((link) => {
      try {
        return new URL(link).origin !== origin;
      } catch {
        return false;
      }
    })
  );
}

function extractLinks(html: string, baseUrl: string) {
  const output: string[] = [];
  const matches = html.matchAll(/<a[^>]+href=["']([^"']+)["'][^>]*>/gi);

  for (const match of matches) {
    const href = match[1];

    if (!href) continue;
    if (/^(mailto:|tel:|javascript:|#)/i.test(href)) continue;

    try {
      output.push(cleanUrl(new URL(href, baseUrl).toString()));
    } catch {
      // Ignore invalid URLs.
    }
  }

  return output.filter(Boolean);
}

function countMatches(value: string, regex: RegExp) {
  return [...String(value || "").matchAll(regex)].length;
}

function countImagesMissingAlt(html: string) {
  const images = [...String(html || "").matchAll(/<img\b[^>]*>/gi)];

  return images.filter((match) => {
    const tag = match[0];
    return !/\salt\s*=\s*["'][^"']+["']/i.test(tag);
  }).length;
}

function decodeHtmlEntities(value: string) {
  return String(value || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
}

/* -------------------------------------------------------------------------- */
/* URL filtering                                                               */
/* -------------------------------------------------------------------------- */

function normalizeWebsiteUrl(value: string) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  try {
    const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const url = new URL(withProtocol);

    url.hash = "";

    return url.toString();
  } catch {
    return "";
  }
}

function cleanUrl(value: string) {
  try {
    const url = new URL(String(value || ""));

    url.hash = "";

    const removableParams = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content",
      "fbclid",
      "gclid",
      "msclkid",
    ];

    for (const param of removableParams) {
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

function normalizePath(pathname: string) {
  const path = String(pathname || "/");

  if (!path || path === "/") return "/";

  return path.endsWith("/") ? path.slice(0, -1) : path;
}

function normalizeRequestedPathPrefix(value: string) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  const cleaned = raw.startsWith("/") ? raw : `/${raw}`;

  const withoutTrailingSlash =
    cleaned !== "/" && cleaned.endsWith("/")
      ? cleaned.slice(0, -1)
      : cleaned;

  if (withoutTrailingSlash === "/") return "";

  return withoutTrailingSlash;
}

function detectLanguagePrefix(pathname: string) {
  const parts = String(pathname || "/")
    .split("/")
    .filter(Boolean);

  const first = parts[0] || "";

  if (/^[a-z]{2}(-[a-z]{2})?$/i.test(first)) {
    return `/${first}`;
  }

  return "";
}

function shouldCrawlUrl({
  url,
  origin,
  pathPrefix,
}: {
  url: string;
  origin: string;
  pathPrefix: string;
}) {
  try {
    const parsed = new URL(url);

    if (parsed.origin !== origin) {
      return { ok: false, reason: "external" };
    }

    if (!/^https?:$/i.test(parsed.protocol)) {
      return { ok: false, reason: "protocol" };
    }

    if (pathPrefix) {
      const path = normalizePath(parsed.pathname);

      if (path !== pathPrefix && !path.startsWith(`${pathPrefix}/`)) {
        return { ok: false, reason: "outside_prefix" };
      }
    }

    if (isProbablyAsset(parsed.pathname)) {
      return { ok: false, reason: "asset" };
    }

    if (isUtilityUrl(parsed.pathname)) {
      return { ok: false, reason: "utility" };
    }

    if (isLikelyEncodedOrJunkUrl(parsed.pathname)) {
      return { ok: false, reason: "junk" };
    }

    return { ok: true, reason: "" };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}

function isProbablyAsset(pathname: string) {
  return /\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|rar|7z|css|js|mjs|woff|woff2|ttf|eot|mp4|mp3|avi|mov|xml)$/i.test(
    pathname
  );
}

function isUtilityUrl(pathname: string) {
  const path = String(pathname || "").toLowerCase();

  const segments = path
    .split("/")
    .filter(Boolean)
    .map((segment) => segment.trim());

  if (segments.length === 0) return false;

  const first = segments[0] || "";

  if (first === "wp-admin" || first === "wp-json") return true;

  const blockedWholeSegments = new Set([
    "cart",
    "checkout",
    "login",
    "logout",
    "account",
    "my-account",
    "privacy",
    "terms",
    "cookie",
    "cookies",
    "legal",
    "cgu",
    "search",
    "tag",
    "author",
    "feed",
    "preview",
    "staging",
    "test",
    "backup",
  ]);

  if (segments.some((segment) => blockedWholeSegments.has(segment))) {
    return true;
  }

  if (segments.some((segment) => /^home-\d+$/.test(segment))) {
    return true;
  }

  return false;
}

function isLikelyEncodedOrJunkUrl(pathname: string) {
  const parts = String(pathname || "")
    .split("/")
    .filter(Boolean)
    .map((part) => safeDecodeURIComponent(part));

  for (const part of parts) {
    const cleaned = part.trim();

    if (!cleaned) continue;

    const base64ish =
      cleaned.length >= 18 &&
      /^[A-Za-z0-9+/=_-]+$/.test(cleaned) &&
      /[A-Z]/.test(cleaned) &&
      /[a-z]/.test(cleaned) &&
      !cleaned.includes("-");

    if (!base64ish) continue;

    try {
      const normalized = cleaned.replace(/-/g, "+").replace(/_/g, "/");
      const decoded = atob(normalized);

      if (
        /^https?:\/\//i.test(decoded) ||
        decoded.startsWith("/") ||
        decoded.includes(".html") ||
        decoded.includes("/actualites/") ||
        decoded.includes("/actualité/") ||
        decoded.includes("/assurance-") ||
        decoded.includes("/rachat-") ||
        decoded.includes("/vigilance-") ||
        decoded.includes("/partenaires")
      ) {
        return true;
      }
    } catch {
      if (cleaned.length >= 28) return true;
    }
  }

  return false;
}

function safeDecodeURIComponent(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isInsidePathPrefix(value: string, prefix: string) {
  try {
    const parsed = new URL(value);
    const path = normalizePath(parsed.pathname);

    return path === prefix || path.startsWith(`${prefix}/`);
  } catch {
    return false;
  }
}

function buildStartUrlCandidates(startUrl: string) {
  const output = new Set<string>();
  const cleanedStart = cleanUrl(startUrl);

  if (cleanedStart) output.add(cleanedStart);

  try {
    const parsed = new URL(startUrl);
    const originalPath = parsed.pathname;

    if (/\/index\.html?$/i.test(originalPath)) {
      parsed.pathname = originalPath.replace(/\/index\.html?$/i, "/");
      output.add(cleanUrl(parsed.toString()));
    }

    if (!originalPath.endsWith("/") && !/\.[a-z0-9]+$/i.test(originalPath)) {
      parsed.pathname = `${originalPath}/`;
      output.add(cleanUrl(parsed.toString()));
    }

    if (originalPath === "/" || originalPath === "") {
      output.add(cleanUrl(parsed.origin + "/"));
    }
  } catch {
    // Ignore invalid variants.
  }

  return [...output].filter(Boolean).slice(0, 3);
}

function makeUrlTemplate(url: string) {
  try {
    const parsed = new URL(url);
    const segments = parsed.pathname.split("/").filter(Boolean);

    const templated = segments.map((segment, index) => {
      if (index < 2) return segment;

      if (isDynamicUrlSegment(segment)) return "*";

      return segment;
    });

    return `/${templated.join("/")}`;
  } catch {
    return "";
  }
}

function isDynamicUrlSegment(segment: string) {
  const value = String(segment || "");

  if (/^\d+$/.test(value)) return true;
  if (/^[0-9a-f]{8,}-[0-9a-f-]{8,}$/i.test(value)) return true;
  if (value.length > 45) return true;

  return false;
}

/* -------------------------------------------------------------------------- */
/* Sitemap helpers                                                             */
/* -------------------------------------------------------------------------- */

async function fetchText(url: string, timeoutMs: number) {
  const response = await fetchWithTimeout(url, timeoutMs);

  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }

  return await response.text();
}

function parseLocTags(xml: string) {
  const matches = [...String(xml || "").matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi)];

  return matches
    .map((match) => decodeHtmlEntities(match[1] || "").trim())
    .filter(Boolean);
}

/* -------------------------------------------------------------------------- */
/* Related subdomains                                                          */
/* -------------------------------------------------------------------------- */

function collectRelatedSubdomains({
  page,
  startHost,
  baseDomain,
  relatedSubdomains,
}: {
  page: any;
  startHost: string;
  baseDomain: string;
  relatedSubdomains: Map<string, any>;
}) {
  const externalLinks = Array.isArray(page.external_links)
    ? page.external_links
    : [];

  for (const link of externalLinks) {
    try {
      const parsed = new URL(link);
      const host = parsed.hostname.replace(/^www\./i, "");
      const normalizedStartHost = startHost.replace(/^www\./i, "");

      if (host === normalizedStartHost) continue;
      if (getBaseDomain(host) !== baseDomain) continue;

      if (!relatedSubdomains.has(host)) {
        relatedSubdomains.set(host, {
          host,
          url: `${parsed.protocol}//${parsed.host}/`,
          seen_on_pages: [],
          count: 0,
        });
      }

      const item = relatedSubdomains.get(host);
      item.count += 1;

      if (item.seen_on_pages.length < 5) {
        item.seen_on_pages.push(page.url);
      }
    } catch {
      // Ignore invalid URLs.
    }
  }
}

function buildRecommendedFollowupScans({
  relatedSubdomains,
  startUrl,
  baseDomain,
}: {
  relatedSubdomains: Map<string, any>;
  startUrl: string;
  baseDomain: string;
}) {
  const startHost = new URL(startUrl).hostname.replace(/^www\./i, "");

  return [...relatedSubdomains.values()]
    .filter((item) => item.host !== startHost)
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((item) => ({
      type: "related_subdomain",
      url: item.url,
      host: item.host,
      base_domain: baseDomain,
      reason:
        "This related subdomain was linked from the scanned website. It was not crawled in this scan so the 150-page limit stays focused.",
      seen_link_count: item.count,
      seen_on_pages: item.seen_on_pages,
      recommended_action:
        "Consider running a separate scan for this subdomain if it is important to the business.",
    }));
}

function getBaseDomain(hostname: string) {
  const host = String(hostname || "")
    .toLowerCase()
    .replace(/^www\./, "");

  const parts = host.split(".").filter(Boolean);

  if (parts.length <= 2) return host;

  const secondLevelTlds = ["co.uk", "com.au", "com.br", "com.mx", "co.nz"];
  const lastTwo = parts.slice(-2).join(".");
  const lastThree = parts.slice(-3).join(".");

  if (secondLevelTlds.includes(lastTwo) && parts.length >= 3) {
    return lastThree;
  }

  return lastTwo;
}

/* -------------------------------------------------------------------------- */
/* Screaming Frog Lite audit                                                   */
/* -------------------------------------------------------------------------- */

function runScreamingFrogLiteAudit({
  pages,
  startUrl,
}: {
  pages: any[];
  startUrl: string;
}) {
  const rawFindings: any[] = [];
  const readablePages = pages.filter(isReadablePage);
  const indexablePages = readablePages.filter((page) => page.indexable !== false);

  for (const page of pages) {
    if (Number(page.status_code || 0) >= 400) {
      rawFindings.push(
        makeFinding({
          rule: "broken_page",
          category: "404_error",
          customer_category: "Broken page",
          priority: "high",
          difficulty: "developer",
          page,
          title: "Fix pages that are not loading",
          explanation:
            "This page returned an error status, so visitors and search engines may not be able to use it.",
          recommendation:
            "Restore the page, update the link, or redirect it to the closest useful page.",
        })
      );
    }
  }

  for (const page of readablePages) {
    if (!page.title) {
      rawFindings.push(
        makeFinding({
          rule: "missing_title",
          category: "meta_title",
          customer_category: "Search appearance",
          priority: "high",
          difficulty: "easy",
          page,
          title: "Add a search title",
          explanation:
            "This page is missing a title tag, which can hurt how it appears in search results.",
          recommendation:
            "Add a clear title that describes the page and includes the main topic.",
        })
      );
    } else if (page.title.length > 65) {
      rawFindings.push(
        makeFinding({
          rule: "long_title",
          category: "meta_title",
          customer_category: "Search appearance",
          priority: "medium",
          difficulty: "easy",
          page,
          title: "Shorten long search titles",
          explanation: "Long titles can be cut off in search results.",
          recommendation:
            "Rewrite the title so the most important words appear near the beginning.",
        })
      );
    } else if (page.title.length < 15) {
      rawFindings.push(
        makeFinding({
          rule: "short_title",
          category: "meta_title",
          customer_category: "Search appearance",
          priority: "medium",
          difficulty: "easy",
          page,
          title: "Make short search titles more descriptive",
          explanation:
            "Very short titles may not give searchers enough context.",
          recommendation:
            "Add a more descriptive title that explains what the page is about.",
        })
      );
    }

    if (!page.meta_description) {
      rawFindings.push(
        makeFinding({
          rule: "missing_meta_description",
          category: "meta_description",
          customer_category: "Search appearance",
          priority: "medium",
          difficulty: "easy",
          page,
          title: "Add a helpful search description",
          explanation:
            "This page is missing a meta description, so Google may choose its own snippet.",
          recommendation:
            "Write a short description that explains the page and encourages the right visitors to click.",
        })
      );
    } else if (page.meta_description.length > 170) {
      rawFindings.push(
        makeFinding({
          rule: "long_meta_description",
          category: "meta_description",
          customer_category: "Search appearance",
          priority: "low",
          difficulty: "easy",
          page,
          title: "Shorten long search descriptions",
          explanation:
            "Long meta descriptions may be cut off in search results.",
          recommendation:
            "Rewrite the description to focus on the main benefit in one or two sentences.",
        })
      );
    }

    if (!page.h1) {
      rawFindings.push(
        makeFinding({
          rule: "missing_h1",
          category: "thin_content",
          customer_category: "Page content",
          priority: "medium",
          difficulty: "easy",
          page,
          title: "Add a clear main heading",
          explanation:
            "This page does not appear to have a clear H1 heading.",
          recommendation:
            "Add one main heading that clearly describes the page topic.",
        })
      );
    }

    if (Number(page.h1_count || 0) > 1) {
      rawFindings.push(
        makeFinding({
          rule: "multiple_h1",
          category: "thin_content",
          customer_category: "Page content",
          priority: "low",
          difficulty: "easy",
          page,
          title: "Review pages with multiple main headings",
          explanation:
            "Multiple H1 headings can make the page structure less clear.",
          recommendation:
            "Keep one main H1 and use H2/H3 headings for sections.",
        })
      );
    }

    if (Number(page.word_count || 0) > 0 && Number(page.word_count || 0) < 200) {
      rawFindings.push(
        makeFinding({
          rule: "thin_content",
          category: "thin_content",
          customer_category: "Page content",
          priority: "medium",
          difficulty: "easy",
          page,
          title: "Improve thin pages",
          explanation:
            "This page has very little readable content, so it may not fully answer what visitors are looking for.",
          recommendation:
            "Add useful information, FAQs, examples, services, pricing details, or next steps where relevant.",
        })
      );
    }

    if (!page.canonical_url) {
      rawFindings.push(
        makeFinding({
          rule: "missing_canonical",
          category: "canonical",
          customer_category: "Website setup",
          priority: "low",
          difficulty: "developer",
          page,
          title: "Review canonical settings",
          explanation:
            "This page does not show a canonical URL in the HTML.",
          recommendation:
            "Add or confirm the preferred version of this page in your CMS or SEO plugin.",
        })
      );
    }

    if (page.indexable === false) {
      rawFindings.push(
        makeFinding({
          rule: "noindex",
          category: "canonical",
          customer_category: "Website setup",
          priority: "high",
          difficulty: "developer",
          page,
          title: "Review pages marked noindex",
          explanation:
            "This page appears to tell search engines not to index it.",
          recommendation:
            "If this page should appear in Google, remove the noindex setting.",
        })
      );
    }

    if (!page.viewport) {
      rawFindings.push(
        makeFinding({
          rule: "missing_viewport",
          category: "performance",
          customer_category: "Mobile experience",
          priority: "medium",
          difficulty: "developer",
          page,
          title: "Add mobile viewport settings",
          explanation:
            "This page may not be set up correctly for mobile screens.",
          recommendation: "Add a viewport meta tag in the site template or theme.",
        })
      );
    }

    if (Number(page.schema_count || 0) === 0) {
      rawFindings.push(
        makeFinding({
          rule: "missing_schema",
          category: "schema",
          customer_category: "Trust signals",
          priority: "low",
          difficulty: "moderate",
          page,
          title: "Add structured data where useful",
          explanation:
            "This page does not appear to include structured data.",
          recommendation:
            "Add relevant schema such as Organization, LocalBusiness, Product, Article, FAQ, or Breadcrumb schema where appropriate.",
        })
      );
    }

    if (Number(page.open_graph_tag_count || 0) === 0) {
      rawFindings.push(
        makeFinding({
          rule: "missing_open_graph",
          category: "web_dev",
          customer_category: "Social sharing",
          priority: "low",
          difficulty: "easy",
          page,
          title: "Improve social sharing metadata",
          explanation: "This page may not have social sharing tags.",
          recommendation:
            "Add Open Graph title, description, and image fields in the CMS or SEO plugin.",
        })
      );
    }

    if (Number(page.missing_alt_image_count || 0) > 0) {
      rawFindings.push(
        makeFinding({
          rule: "image_alt_text",
          category: "web_dev",
          customer_category: "Images",
          priority: "low",
          difficulty: "easy",
          page,
          title: "Add missing image descriptions",
          explanation:
            "Some images on this page appear to be missing alt text.",
          recommendation: "Add short, useful alt text to important images.",
          current_value: `${page.missing_alt_image_count} images missing alt text`,
        })
      );
    }

    if (
      Number(page.html_size || 0) > 800000 ||
      Number(page.script_count || 0) > 70
    ) {
      rawFindings.push(
        makeFinding({
          rule: "heavy_page",
          category: "performance",
          customer_category: "Website performance",
          priority: "medium",
          difficulty: "developer",
          page,
          title: "Review heavy pages",
          explanation:
            "This page appears large or script-heavy, which can slow down visitors and crawling.",
          recommendation:
            "Compress images, reduce unused scripts, and review third-party apps or plugins.",
        })
      );
    }

    if (page.client_rendering_suspected) {
      rawFindings.push(
        makeFinding({
          rule: "client_rendering",
          category: "js_rendering",
          customer_category: "Website setup",
          priority: "medium",
          difficulty: "developer",
          page,
          title: "Review JavaScript-rendered content",
          explanation:
            "This page may rely heavily on JavaScript before important content appears.",
          recommendation:
            "Make sure the main content, title, links, and headings are available in the initial HTML where possible.",
        })
      );
    }

    if (
      page.final_url !== page.url &&
      cleanUrl(page.final_url) &&
      cleanUrl(page.url)
    ) {
      rawFindings.push(
        makeFinding({
          rule: "redirect",
          category: "redirect",
          customer_category: "Page redirect",
          priority: "low",
          difficulty: "developer",
          page,
          title: "Review redirected pages",
          explanation: "This page redirects to another URL.",
          recommendation:
            "Update internal links so they point directly to the final URL.",
          current_value: page.url,
          recommended_value: page.final_url,
        })
      );
    }
  }

  const duplicateTitleGroups = findDuplicateTitles(indexablePages);
  const duplicateMetaDescriptionGroups = findDuplicateFieldGroups(
    indexablePages,
    "meta_description"
  );
  const duplicateH1Groups = findDuplicateFieldGroups(indexablePages, "h1");

  for (const group of duplicateTitleGroups) {
    rawFindings.push({
      rule: "duplicate_title",
      category: "duplicate_content",
      customer_category: "Search appearance",
      priority: "medium",
      difficulty: "easy",
      issue_title: "Review duplicate search titles",
      title: "Review duplicate search titles",
      plain_english_explanation:
        "Multiple pages use the same search title, which can make it harder for Google to understand which page is most relevant.",
      why_it_matters:
        "Unique titles help each important page stand out in search results.",
      recommendation:
        "Rewrite the titles so each page has a unique, specific search title.",
      recommended_value:
        "Give each affected page a unique title based on the page topic.",
      affected_pages: group.pages,
      page_url: group.pages[0],
      current_value: group.title,
      fingerprint: fnv1a(`duplicate_title|${group.title}`),
      confidence_score: 95,
      source: "screaming_frog_lite",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
    });
  }

  for (const group of duplicateMetaDescriptionGroups) {
    rawFindings.push({
      rule: "duplicate_meta_description",
      category: "duplicate_content",
      customer_category: "Search appearance",
      priority: "low",
      difficulty: "easy",
      issue_title: "Review duplicate search descriptions",
      title: "Review duplicate search descriptions",
      plain_english_explanation:
        "Multiple pages use the same search description, which can make search results less helpful.",
      why_it_matters:
        "Unique descriptions help each important page explain its own value in search results.",
      recommendation:
        "Rewrite the descriptions so each affected page has a unique, helpful summary.",
      recommended_value:
        "Give each affected page a unique description based on the page topic.",
      affected_pages: group.pages,
      page_url: group.pages[0],
      current_value: group.value,
      fingerprint: fnv1a(`duplicate_meta_description|${group.value}`),
      confidence_score: 95,
      source: "screaming_frog_lite",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
    });
  }

  for (const group of duplicateH1Groups) {
    rawFindings.push({
      rule: "duplicate_h1",
      category: "thin_content",
      customer_category: "Page content",
      priority: "low",
      difficulty: "easy",
      issue_title: "Review duplicate main headings",
      title: "Review duplicate main headings",
      plain_english_explanation:
        "Multiple pages use the same main heading, which can make pages feel repetitive or unclear.",
      why_it_matters:
        "Unique headings help visitors and search engines understand what each page is about.",
      recommendation:
        "Update the main heading on each affected page so it clearly matches that page topic.",
      recommended_value:
        "Give each affected page a unique H1 based on its specific topic.",
      affected_pages: group.pages,
      page_url: group.pages[0],
      current_value: group.value,
      fingerprint: fnv1a(`duplicate_h1|${group.value}`),
      confidence_score: 95,
      source: "screaming_frog_lite",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
    });
  }

  const orphanPages = findOrphanSitemapPages(pages);

  if (orphanPages.length > 0) {
    rawFindings.push({
      rule: "orphan_page",
      category: "internal_link",
      customer_category: "Internal links",
      priority: "low",
      difficulty: "easy",
      issue_title: "Pages not linked from your website",
      title: "Pages not linked from your website",
      plain_english_explanation:
        "Some pages were found in the sitemap but were not linked from the pages the scanner checked.",
      why_it_matters:
        "Important pages should be linked from your website so visitors and search engines can discover them naturally.",
      recommendation:
        "Add internal links to important orphan pages from relevant service pages, menus, footer links, or related content.",
      recommended_value:
        "Link to important sitemap pages from relevant pages on your website.",
      affected_pages: orphanPages.map((page) => page.url),
      page_url: orphanPages[0]?.url || startUrl,
      fingerprint: fnv1a("orphan_page|sitemap"),
      confidence_score: 95,
      source: "screaming_frog_lite",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
    });
  }

  const scannerBlockedPages = pages.filter((page) => page.is_scanner_blocked);
  const missingMetaDescriptionCount = rawFindings.filter(
    (item) => item.rule === "missing_meta_description"
  ).length;
  const heavyPageCount = rawFindings.filter(
    (item) => item.rule === "heavy_page"
  ).length;

  const averageWordCount = Math.round(
    readablePages.reduce(
      (sum, page) => sum + Number(page.word_count || 0),
      0
    ) / Math.max(1, readablePages.length)
  );

  return {
    raw_findings: rawFindings,
    technical_audit_summary: {
      audit_profile: "screaming_frog_lite",
      screaming_frog_lite_enabled: true,
      pages_checked: pages.length,
      readable_pages_checked: readablePages.length,
      scanner_blocked_pages: scannerBlockedPages.length,
      important_pages_checked: readablePages.length,
      indexable_pages: indexablePages.length,
      missing_meta_description_count: missingMetaDescriptionCount,
      heavy_page_count: heavyPageCount,
      average_word_count: averageWordCount,
      checks_completed: [
        "status_codes",
        "titles",
        "meta_descriptions",
        "h1_headings",
        "canonicals",
        "indexability",
        "mobile_viewport",
        "schema",
        "open_graph",
        "image_alt_text",
        "thin_content",
        "redirects",
        "heavy_pages",
        "client_rendering",
        "duplicate_titles",
        "duplicate_meta_descriptions",
        "duplicate_h1_headings",
        "orphan_sitemap_pages",
      ],
    },
  };
}

function isReadablePage(page: any) {
  return (
    Number(page.status_code || 0) >= 200 &&
    Number(page.status_code || 0) < 300 &&
    page.is_scanner_blocked !== true &&
    Number(page.word_count || 0) > 20
  );
}

function makeFinding({
  rule,
  category,
  customer_category,
  priority,
  difficulty,
  page,
  title,
  explanation,
  recommendation,
  current_value = "",
  recommended_value = "",
}: {
  rule: string;
  category: string;
  customer_category: string;
  priority: string;
  difficulty: string;
  page: any;
  title: string;
  explanation: string;
  recommendation: string;
  current_value?: string;
  recommended_value?: string;
}) {
  return {
    rule,
    category,
    customer_category,
    priority,
    difficulty,
    issue_title: title,
    title,
    plain_english_explanation: explanation,
    why_it_matters:
      "Fixing this can improve how visitors and search engines understand the page.",
    recommendation,
    suggested_fix: recommendation,
    ai_recommendation: recommendation,
    recommended_value: recommended_value || recommendation,
    current_value,
    page_url: page.url,
    affected_pages: [page.url],
    fingerprint: fnv1a(`${rule}|${cleanUrl(page.url)}`),
    confidence_score: getFindingConfidence(rule),
    source: "screaming_frog_lite",
    requires_approval: difficulty !== "developer",
    requires_developer: difficulty === "developer",
    can_auto_fix: false,
    details: {
      final_url: page.final_url,
      status_code: page.status_code,
      word_count: page.word_count,
      title: page.title,
      meta_description: page.meta_description,
      h1: page.h1,
      importance_score: page.importance_score,
      importance_reasons: page.importance_reasons,
      fetch_error_class: page.fetch_error_class,
    },
  };
}

function getFindingConfidence(rule: string) {
  const deterministicRules = [
    "broken_page",
    "missing_title",
    "long_title",
    "short_title",
    "missing_meta_description",
    "long_meta_description",
    "missing_h1",
    "multiple_h1",
    "missing_canonical",
    "noindex",
    "missing_viewport",
    "missing_schema",
    "missing_open_graph",
    "image_alt_text",
    "redirect",
    "duplicate_title",
    "duplicate_meta_description",
    "duplicate_h1",
    "orphan_page",
  ];

  const heuristicRules = [
    "thin_content",
    "heavy_page",
    "client_rendering",
    "scanner_blocked_start_page",
    "internal_pages_crawl_limited",
  ];

  if (deterministicRules.includes(rule)) return 95;
  if (heuristicRules.includes(rule)) return 80;

  return 85;
}

function groupFindings(findings: any[]) {
  const groups = new Map<string, any>();
  const templateCounts = buildTemplateCounts(findings);

  for (const finding of findings) {
    const rule = finding.rule || finding.category || "unknown";
    const title = finding.issue_title || finding.title || "Review this item";
    const key = `${rule}:${title}`;

    if (!groups.has(key)) {
      const {
        details,
        current_value,
        recommended_value,
        page_url,
        affected_pages,
        ...safeFinding
      } = finding;

      groups.set(key, {
        ...safeFinding,
        rule,
        issue_title: title,
        title,
        type: "site_level",
        affected_pages: [],
        affected_count: 0,
        samples: [],
        fingerprint: fnv1a(`${rule}|${title}`),
        template: "",
        template_reach: 0,
      });
    }

    const group = groups.get(key);

    const pages = Array.isArray(finding.affected_pages)
      ? finding.affected_pages
      : finding.page_url
        ? [finding.page_url]
        : [];

    group.affected_pages = unique([...group.affected_pages, ...pages]);
    group.affected_count = group.affected_pages.length;
    group.page_url = group.affected_pages[0] || finding.page_url || "/";

    const sampleUrl = finding.page_url || pages[0] || "";

    if (sampleUrl && group.samples.length < 3) {
      group.samples.push({
        url: sampleUrl,
        current_value: finding.current_value || "",
      });
    }

    const template = sampleUrl ? makeUrlTemplate(sampleUrl) : "";

    if (template && !group.template) {
      group.template = template;
      group.template_reach = templateCounts.get(template) || 1;
    }
  }

  return [...groups.values()].sort((a, b) => {
    const priorityDiff = priorityWeight(b.priority) - priorityWeight(a.priority);

    if (priorityDiff !== 0) return priorityDiff;

    return Number(b.template_reach || 0) - Number(a.template_reach || 0);
  });
}

function buildTemplateCounts(findings: any[]) {
  const counts = new Map<string, number>();

  for (const finding of findings) {
    const pages = Array.isArray(finding.affected_pages)
      ? finding.affected_pages
      : finding.page_url
        ? [finding.page_url]
        : [];

    for (const page of pages) {
      const template = makeUrlTemplate(page);

      if (!template) continue;

      counts.set(template, (counts.get(template) || 0) + 1);
    }
  }

  return counts;
}

function findDuplicateTitles(pages: any[]) {
  const map = new Map<string, string[]>();

  for (const page of pages) {
    const title = String(page.title || "").trim().toLowerCase();

    if (!title) continue;

    if (!map.has(title)) map.set(title, []);
    map.get(title)?.push(page.url);
  }

  return [...map.entries()]
    .filter(([, urls]) => urls.length > 1)
    .map(([title, urls]) => ({
      title,
      pages: urls,
    }));
}

function findDuplicateFieldGroups(pages: any[], fieldName: string) {
  const map = new Map<string, string[]>();

  for (const page of pages) {
    const value = String(page[fieldName] || "").trim().toLowerCase();

    if (!value) continue;

    if (!map.has(value)) map.set(value, []);
    map.get(value)?.push(page.url);
  }

  return [...map.entries()]
    .filter(([, urls]) => urls.length > 1)
    .map(([value, urls]) => ({
      value,
      pages: urls,
    }));
}

function findOrphanSitemapPages(pages: any[]) {
  const linkedUrls = new Set<string>();

  for (const page of pages) {
    for (const link of page.internal_links || []) {
      linkedUrls.add(cleanUrl(link));
    }
  }

  return pages.filter((page) => {
    if (!page.in_sitemap) return false;
    if (!isReadablePage(page)) return false;
    if (page.source === "start" || page.source === "start_variant") {
      return false;
    }

    return !linkedUrls.has(cleanUrl(page.url));
  });
}

/* -------------------------------------------------------------------------- */
/* Scan coverage + follow-up findings                                          */
/* -------------------------------------------------------------------------- */

function buildCoverageFindings({
  pages,
  startUrl,
  crawlResult,
}: {
  pages: any[];
  startUrl: string;
  crawlResult: any;
}) {
  const findings: any[] = [];
  const startPage =
    pages.find((page) => cleanUrl(page.url) === cleanUrl(startUrl)) || pages[0];

  const blockedPages = pages.filter((page) => page.is_scanner_blocked);
  const internalBlockedPages = pages.filter(
    (page) =>
      page.source !== "start" &&
      page.source !== "start_variant" &&
      page.is_scanner_blocked
  );
  const readablePages = pages.filter(isReadablePage);

  if (startPage?.is_scanner_blocked || readablePages.length === 0) {
    findings.push({
      rule: "scanner_blocked_start_page",
      category: "scanner_blocked",
      customer_category: "Scan coverage",
      priority: "high",
      difficulty: "developer",
      issue_title: "Website protection blocked the scan",
      title: "Website protection blocked the scan",
      plain_english_explanation:
        "The scanner could not read the real content on the starting page.",
      why_it_matters:
        "If search engines or SEO tools cannot access the content, the site may need technical review.",
      recommendation:
        "Check firewall, bot protection, CDN, or security plugin settings. Allow trusted crawlers where appropriate.",
      recommended_value:
        "Allow the scanner and search engines to access the real HTML content.",
      page_url: startPage?.url || startUrl,
      affected_pages: blockedPages.map((page) => page.url),
      affected_count: blockedPages.length,
      fingerprint: fnv1a(
        `scanner_blocked_start_page|${cleanUrl(startPage?.url || startUrl)}`
      ),
      confidence_score: 80,
      source: "crawler",
      requires_approval: false,
      requires_developer: true,
      can_auto_fix: false,
    });

    return findings;
  }

  if (internalBlockedPages.length > 0) {
    findings.push({
      rule: "internal_pages_crawl_limited",
      category: "scanner_blocked",
      customer_category: "Scan coverage",
      priority: internalBlockedPages.length > 20 ? "medium" : "low",
      difficulty: "developer",
      issue_title: "Some internal pages could not be checked",
      title: "Some internal pages could not be checked",
      plain_english_explanation:
        "The scanner read the main website content, but some internal pages started limiting crawler requests.",
      why_it_matters:
        "The Fix List is still useful, but a few pages may need to be checked later or manually.",
      recommendation:
        "Use the current Fix List first. If this happens often, reduce crawler speed or review firewall and rate-limit settings.",
      recommended_value:
        "Treat this as a scan coverage note, not a major SEO failure.",
      page_url: internalBlockedPages[0]?.url || startUrl,
      affected_pages: internalBlockedPages.map((page) => page.url),
      affected_count: internalBlockedPages.length,
      fingerprint: fnv1a("internal_pages_crawl_limited|site"),
      confidence_score: 80,
      source: "crawler",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
      details: {
        readable_pages: readablePages.length,
        blocked_internal_pages: internalBlockedPages.length,
        queued_remaining: crawlResult.queued_remaining || 0,
      },
    });
  }

  return findings;
}

function buildFollowupScanFindings({
  followups,
  startUrl,
}: {
  followups: any[];
  startUrl: string;
}) {
  if (!Array.isArray(followups) || followups.length === 0) return [];

  return [
    {
      rule: "related_subdomains_found",
      category: "web_dev",
      customer_category: "Scan planning",
      priority: "low",
      difficulty: "easy",
      issue_title: "Related website sections may need separate scans",
      title: "Related website sections may need separate scans",
      plain_english_explanation:
        "The scanner found related subdomains linked from this website. They were not crawled in this scan so the 150-page limit stays focused.",
      why_it_matters:
        "Large websites often split important content across subdomains. These can be scanned separately if they matter to the business.",
      recommendation:
        "Review the suggested follow-up scan list and run a separate scan only for the sections that are important.",
      recommended_value: followups.map((item) => item.url).join(", "),
      page_url: startUrl,
      affected_pages: followups.map((item) => item.url),
      affected_count: followups.length,
      fingerprint: fnv1a("related_subdomains_found|site"),
      confidence_score: 85,
      source: "crawler",
      requires_approval: true,
      requires_developer: false,
      can_auto_fix: false,
      details: {
        recommended_followup_scans: followups,
      },
    },
  ];
}

function buildFriendlyWarnings({
  pages,
}: {
  pages: any[];
  crawlResult: any;
}) {
  const warnings: string[] = [];
  const readablePages = pages.filter(isReadablePage);
  const internalBlockedPages = pages.filter(
    (page) =>
      page.source !== "start" &&
      page.source !== "start_variant" &&
      page.is_scanner_blocked
  );

  if (internalBlockedPages.length > 0 && readablePages.length > 0) {
    warnings.push(
      "Some internal pages could not be checked because the site began limiting crawler requests."
    );
  }

  return unique(warnings);
}

/* -------------------------------------------------------------------------- */
/* Competitor checks                                                           */
/* -------------------------------------------------------------------------- */

async function analyzeCompetitors({
  body,
  ownPages,
  budget,
  deadlineAt,
}: {
  body: any;
  ownPages: any[];
  budget: any;
  deadlineAt: number;
}) {
  const competitorUrls = Array.isArray(body.competitor_urls)
    ? body.competitor_urls
        .map((url: string) => normalizeWebsiteUrl(url))
        .filter(Boolean)
        .slice(0, budget.max_competitors)
    : [];

  const browserRenderBudget = {
    used: 0,
    max: budget.max_browser_render_attempts,
  };

  const competitorResults: any[] = [];

  for (const competitorUrl of competitorUrls) {
    if (Date.now() > deadlineAt - 10000) break;

    try {
      const parsed = new URL(competitorUrl);

      const page = await fetchAndExtractPage({
        url: competitorUrl,
        source: "manual_competitor",
        origin: parsed.origin,
        inSitemap: false,
        importanceScore: 0,
        importanceReasons: ["manual competitor URL"],
        allowBrowserRender: true,
        allowBlockedBrowserRender: true,
        browserRenderBudget,
        deadlineAt,
      });

      competitorResults.push({
        url: competitorUrl,
        final_url: page.final_url,
        status_code: page.status_code,
        title: page.title,
        meta_description: page.meta_description,
        h1: page.h1,
        word_count: page.word_count,
        schema_count: page.schema_count,
        internal_link_count: page.internal_link_count,
        is_scanner_blocked: page.is_scanner_blocked,
        fetch_error_class: page.fetch_error_class,
      });
    } catch (error) {
      competitorResults.push({
        url: competitorUrl,
        error: getErrorMessage(error),
      });
    }
  }

  const ownAverageWordCount = averageWordCount(ownPages.filter(isReadablePage));
  const competitorAverageWordCount = averageWordCount(
    competitorResults.filter((item) => !item.is_scanner_blocked)
  );

  const opportunities: any[] = [];

  if (
    competitorAverageWordCount > 0 &&
    ownAverageWordCount > 0 &&
    competitorAverageWordCount > ownAverageWordCount + 300
  ) {
    opportunities.push({
      category: "thin_content",
      customer_category: "Competitor opportunity",
      priority: "medium",
      difficulty: "easy",
      issue_title: "Competitors may have more complete content",
      plain_english_explanation:
        "The competitor pages checked appear to have more readable content on average.",
      why_it_matters:
        "More complete pages can answer more customer questions and create more ranking opportunities.",
      recommendation:
        "Expand important pages with FAQs, service details, benefits, examples, pricing notes, and internal links.",
      current_value: `Your average: ${ownAverageWordCount} words`,
      recommended_value: `Competitor average: ${competitorAverageWordCount} words`,
      affected_pages: ownPages.slice(0, 5).map((page) => page.url),
      fingerprint: fnv1a("competitor_word_count|site"),
      confidence_score: 70,
      source: "competitor_comparison",
    });
  }

  return {
    competitor_results: competitorResults,
    competitor_opportunities: opportunities,
    browser_render_attempts_used: browserRenderBudget.used,
    browser_render_attempts_max: browserRenderBudget.max,
    skipped: false,
    reason: "",
  };
}

function averageWordCount(pages: any[]) {
  if (!Array.isArray(pages) || pages.length === 0) return 0;

  return Math.round(
    pages.reduce((sum, page) => sum + Number(page.word_count || 0), 0) /
      pages.length
  );
}

/* -------------------------------------------------------------------------- */
/* Score + summary                                                             */
/* -------------------------------------------------------------------------- */

function calculateHealthScore({
  pages,
  findings,
  technicalSummary,
  startUrl,
}: {
  pages: any[];
  findings: any[];
  technicalSummary: any;
  startUrl: string;
}) {
  const startPage =
    pages.find((page) => cleanUrl(page.url) === cleanUrl(startUrl)) || pages[0];

  const readablePages = pages.filter(isReadablePage);
  const blockedInternalPages = pages.filter(
    (page) =>
      page.source !== "start" &&
      page.source !== "start_variant" &&
      page.is_scanner_blocked
  );

  if (!startPage || startPage.is_scanner_blocked || readablePages.length === 0) {
    return 35;
  }

  if (pages.length <= 2 && readablePages.length <= 1) {
    return 40;
  }

  let score = 94;

  for (const finding of findings) {
    if (finding.rule === "internal_pages_crawl_limited") continue;
    if (finding.rule === "related_subdomains_found") continue;

    const baseDeduction =
      finding.priority === "critical"
        ? 8
        : finding.priority === "high"
          ? 5
          : finding.priority === "medium"
            ? 3
            : 1;

    const affectedCount = Number(finding.affected_count || 1);
    const impactMultiplier = Math.min(
      1.5,
      0.5 + affectedCount / Math.max(1, readablePages.length)
    );

    score -= baseDeduction * impactMultiplier;
  }

  const blockedRatio =
    blockedInternalPages.length / Math.max(1, pages.length);

  if (blockedInternalPages.length > 0 && readablePages.length >= 10) {
    score -= Math.min(8, Math.round(blockedRatio * 10));
  }

  if (Number(technicalSummary.average_word_count || 0) >= 700) {
    score += 3;
  }

  return Math.max(45, Math.min(100, Math.round(score)));
}

function buildScanSummary({
  websiteUrl,
  body,
  healthScore,
  pages,
  findings,
  technicalSummary,
  crawlResult,
}: {
  websiteUrl: string;
  body: any;
  healthScore: number;
  pages: any[];
  findings: any[];
  technicalSummary: any;
  crawlResult: any;
}) {
  const readablePages = pages.filter(isReadablePage);
  const highPriorityCount = findings.filter(
    (finding) => finding.priority === "high" || finding.priority === "critical"
  ).length;

  const positives: string[] = [];

  if (readablePages.length > 0) {
    positives.push(
      `The scanner successfully reviewed ${readablePages.length} readable pages.`
    );
  }

  if (Number(technicalSummary.average_word_count || 0) >= 500) {
    positives.push(
      "The readable pages have a healthy amount of content on average."
    );
  }

  if (highPriorityCount === 0) {
    positives.push(
      "No critical site-wide SEO issue was found in the readable pages."
    );
  }

  return {
    website_url: websiteUrl,
    business_name: body.business_name || "",
    health_score: healthScore,
    pages_checked: pages.length,
    readable_pages_checked: readablePages.length,
    recommendations_count: findings.length,
    high_priority_count: highPriorityCount,
    positives,
    plain_english_summary:
      `The scan reviewed ${pages.length} pages and found ${findings.length} grouped recommendations. ` +
      `Screaming Frog Lite checks were completed for titles, descriptions, headings, canonicals, indexability, mobile setup, schema, image alt text, performance signals, redirects, duplicate titles, duplicate descriptions, duplicate H1 headings, and orphan sitemap pages.`,
    coverage: {
      pages_found: crawlResult.pages_found,
      pages_crawled: pages.length,
      queued_remaining: crawlResult.queued_remaining,
    },
    scan_focus: {
      max_pages_enforced: crawlResult.sitemap_priority_summary?.max_pages_enforced,
      topic_dossier_prefix:
        crawlResult.sitemap_priority_summary?.topic_dossier_prefix || "",
      important_page_patterns: crawlResult.important_page_patterns,
      deprioritized_page_patterns: crawlResult.deprioritized_page_patterns,
      recommended_followup_scans: crawlResult.recommended_followup_scans,
      skipped_junk_urls_count: crawlResult.skipped_junk_urls_count || 0,
      skipped_outside_prefix_count:
        crawlResult.skipped_outside_prefix_count || 0,
      start_url_candidates: crawlResult.start_url_candidates || [],
      explanation:
        "The scanner prioritized sitemap and internal URLs that looked like important landing pages, tried cleaner start URL variants, bypassed robots.txt crawl restrictions, and deprioritized listing, archive, news, tag, search, encoded, and very deep pages where appropriate.",
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Small helpers                                                               */
/* -------------------------------------------------------------------------- */

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function priorityWeight(priority: string) {
  const map: Record<string, number> = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };

  return map[String(priority || "medium")] || 2;
}

function fnv1a(value: string) {
  let hash = 0x811c9dc5;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }

  return `fp_${(hash >>> 0).toString(16)}`;
}

function countFetchErrorClasses(pages: any[]) {
  const counts: Record<string, number> = {};

  for (const page of pages) {
    const key = page.fetch_error_class || "none";
    counts[key] = (counts[key] || 0) + 1;
  }

  return counts;
}