--- "/mnt/data/Pasted text(14).txt"	2026-07-05 14:28:33.254477154 +0000
+++ /mnt/data/advanced_scan_screaming_frog_lite.js	2026-07-05 14:32:25.995114629 +0000
@@ -9,6 +9,15 @@
 const CRAWL_TIME_BUDGET_MS = 95000;
 const MAX_HTML_BYTES = 800000;
 
+// Native "Screaming Frog Lite" checks. These do not replace a full JS-rendered
+// desktop crawl, but they add the high-value technical SEO checks most clients
+// expect from an advanced crawler.
+const SCREAMING_FROG_LITE_DEFAULT = true;
+const LARGE_HTML_BYTES = 500000;
+const HEAVY_SCRIPT_TAG_COUNT = 50;
+const LOW_TEXT_TO_HTML_RATIO = 3;
+const MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE = 2;
+
 const SCAN_LIMITS = {
   basic: {
     maxPages: 25,
@@ -37,6 +46,15 @@
     maxCompetitorSnapshots: 5,
     maxKeywords: 5,
   },
+  advanced: {
+    maxPages: 350,
+    concurrency: 12,
+    timeoutMs: 18000,
+    useSitemap: true,
+    discoverCompetitors: true,
+    maxCompetitorSnapshots: 7,
+    maxKeywords: 6,
+  },
 };
 
 const UTILITY_PATH_RE =
@@ -130,10 +148,12 @@
       crawl_job_id = "",
       important_keywords = [],
       competitor_urls = [],
+      enable_screaming_frog_lite = SCREAMING_FROG_LITE_DEFAULT,
     } = body;
 
     const scanMode = SCAN_LIMITS[body.scan_mode] ? body.scan_mode : "quick";
     const limits = SCAN_LIMITS[scanMode];
+    const screamingFrogLiteEnabled = enable_screaming_frog_lite !== false;
 
     if (!website_url) {
       return Response.json(
@@ -189,6 +209,7 @@
 
     const brokenLinks = detectBrokenInternalLinks(crawlResult.pages);
     const clientRendering = detectClientRendering(crawlResult.pages);
+    const technicalAuditSummary = buildTechnicalAuditSummary(crawlResult.pages);
 
     const competitorComparison = buildCompetitorComparison({
       pages: crawlResult.pages,
@@ -204,6 +225,7 @@
       business_name,
       business_type,
       city,
+      screamingFrogLiteEnabled,
     });
 
     const groupedFindings = groupAndPrioritizeFindings(rawFindings);
@@ -221,6 +243,7 @@
       robots,
       clientRendering,
       competitorComparison,
+      technicalAuditSummary,
     });
 
     const scanSummary = {
@@ -246,6 +269,9 @@
           fix.category === "competitor_gap" ||
           fix.customer_category === "Competitor opportunities"
       ).length,
+      technical_issue_count: groupedFindings.filter(
+        (fix) => fix.customer_category === "Technical SEO"
+      ).length,
       positive_findings: siteSummary.positives.join(" "),
     };
 
@@ -285,6 +311,9 @@
       competitor_comparison: competitorComparison,
 
       client_rendering: clientRendering,
+      technical_audit_summary: technicalAuditSummary,
+      screaming_frog_lite_enabled: screamingFrogLiteEnabled,
+      audit_profile: screamingFrogLiteEnabled ? "screaming_frog_lite" : "standard",
 
       competitor_urls,
       crawl_job_id,
@@ -652,17 +681,21 @@
   const originalNormalized = canonicalizeUrl(originalUrl);
   const decodedHtml = decodeHtml(html);
 
-  const title = cleanText(
-    matchFirst(decodedHtml, /<title[^>]*>([\s\S]*?)<\/title>/i)
-  );
+  const titleMatches = matchAllClean(decodedHtml, /<title[^>]*>([\s\S]*?)<\/title>/gi);
+  const title = cleanText(titleMatches[0] || "");
+  const titleCount = titleMatches.length;
 
   const metaDescription = cleanText(
     getMetaContent(decodedHtml, "description") ||
       getMetaProperty(decodedHtml, "og:description") ||
       getMetaName(decodedHtml, "twitter:description")
   );
+  const metaDescriptionCount = countMetaNameTags(decodedHtml, "description");
 
-  const h1 = cleanText(matchFirst(decodedHtml, /<h1[^>]*>([\s\S]*?)<\/h1>/i));
+  const h1s = matchAllClean(decodedHtml, /<h1[^>]*>([\s\S]*?)<\/h1>/gi)
+    .filter((h) => !HEADING_JUNK_RE.test(h))
+    .slice(0, 20);
+  const h1 = cleanText(h1s[0] || "");
 
   const canonicalRaw =
     matchFirst(
@@ -696,6 +729,22 @@
   const placeholder = detectPlaceholderText(pageText);
   const path = getPath(normalizedUrl || url);
   const scriptTagCount = (html.match(/<script/gi) || []).length;
+  const responseSizeBytes = new TextEncoder().encode(String(html || "")).length;
+  const textToHtmlRatio = Math.round(
+    (String(pageText || "").length / Math.max(String(html || "").length, 1)) * 1000
+  ) / 10;
+  const socialMeta = detectSocialMeta(decodedHtml);
+  const hreflangs = extractHreflangs(decodedHtml, url);
+  const canonicalDiagnostics = buildCanonicalDiagnostics({
+    pageUrl: normalizedUrl || url,
+    canonicalUrl,
+    domain,
+  });
+  const indexability = buildIndexability({
+    status,
+    robotsMeta,
+    canonicalDiagnostics,
+  });
 
   return {
     url: normalizedUrl,
@@ -707,17 +756,34 @@
     redirected: Boolean(originalNormalized && originalNormalized !== normalizedUrl),
 
     title,
+    title_length: title.length,
+    title_count: titleCount,
     meta_description: metaDescription,
+    meta_description_length: metaDescription.length,
+    meta_description_count: metaDescriptionCount,
     h1,
+    h1s,
+    h1_count: h1s.length,
     h2s: headings.h2s,
+    h2_count: headings.h2s.length,
     h3s: headings.h3s,
+    h3_count: headings.h3s.length,
 
     canonical_url: canonicalUrl,
     robots_meta: robotsMeta,
     noindex: /noindex/i.test(robotsMeta),
     nofollow: /nofollow/i.test(robotsMeta),
+    indexability: indexability.status,
+    indexability_reasons: indexability.reasons,
+    canonical_status: canonicalDiagnostics.status,
+    canonical_issue: canonicalDiagnostics.issue,
+    canonical_is_self_reference: canonicalDiagnostics.isSelfReference,
+    canonical_points_off_domain: canonicalDiagnostics.pointsOffDomain,
 
     word_count: wordCount,
+    response_size_bytes: responseSizeBytes,
+    html_truncated: String(html || "").length >= MAX_HTML_BYTES,
+    text_to_html_ratio: textToHtmlRatio,
     visible_text_sample: pageText.slice(0, 2500),
 
     internal_links: stableSortUrls(Array.from(new Set(internalLinks))).slice(
@@ -728,6 +794,8 @@
       0,
       200
     ),
+    internal_link_count: Array.from(new Set(internalLinks)).length,
+    external_link_count: Array.from(new Set(externalLinks)).length,
 
     images,
     image_count: images.length,
@@ -743,6 +811,13 @@
       /application\/ld\+json|schema\.org/i.test(decodedHtml),
     schema_types: schemaTypes,
 
+    viewport_present: Boolean(getMetaContent(decodedHtml, "viewport")),
+    charset_present: /<meta[^>]+charset=["']?[^"'>\s]+/i.test(decodedHtml),
+    open_graph_present: socialMeta.open_graph,
+    twitter_card_present: socialMeta.twitter_card,
+    hreflang_count: hreflangs.length,
+    hreflangs,
+
     has_phone: /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.test(pageText),
     has_email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(pageText),
 
@@ -785,21 +860,40 @@
     redirected: false,
 
     title: "",
+    title_length: 0,
+    title_count: 0,
     meta_description: "",
+    meta_description_length: 0,
+    meta_description_count: 0,
     h1: "",
+    h1s: [],
+    h1_count: 0,
     h2s: [],
+    h2_count: 0,
     h3s: [],
+    h3_count: 0,
 
     canonical_url: "",
     robots_meta: "",
     noindex: false,
     nofollow: false,
+    indexability: "not_indexable",
+    indexability_reasons: error ? [error] : ["Page was not successfully fetched"],
+    canonical_status: "missing",
+    canonical_issue: "No canonical tag was found",
+    canonical_is_self_reference: false,
+    canonical_points_off_domain: false,
 
     word_count: 0,
+    response_size_bytes: 0,
+    html_truncated: false,
+    text_to_html_ratio: 0,
     visible_text_sample: "",
 
     internal_links: [],
     external_links: [],
+    internal_link_count: 0,
+    external_link_count: 0,
 
     images: [],
     image_count: 0,
@@ -811,6 +905,13 @@
     has_schema: false,
     schema_types: [],
 
+    viewport_present: false,
+    charset_present: false,
+    open_graph_present: false,
+    twitter_card_present: false,
+    hreflang_count: 0,
+    hreflangs: [],
+
     has_phone: false,
     has_email: false,
 
@@ -1081,6 +1182,7 @@
   business_name,
   business_type,
   city,
+  screamingFrogLiteEnabled = true,
 }) {
   const findings = [];
 
@@ -1586,6 +1688,10 @@
     })
   );
 
+  if (screamingFrogLiteEnabled) {
+    findings.push(...detectScreamingFrogLiteFindings(pages));
+  }
+
   findings.push(...detectDuplicateTitles(pages));
   findings.push(...detectDuplicateDescriptions(pages));
 
@@ -1953,6 +2059,403 @@
   return findings;
 }
 
+function detectScreamingFrogLiteFindings(pages) {
+  const findings = [];
+
+  const importantPages = (pages || []).filter(
+    (page) =>
+      page.is_important_page &&
+      !page.is_utility_page &&
+      page.status_code >= 200 &&
+      page.status_code < 400
+  );
+
+  const multipleTitlePages = importantPages.filter((page) => page.title_count > 1);
+  const multipleMetaDescriptionPages = importantPages.filter(
+    (page) => page.meta_description_count > 1
+  );
+  const longDescriptionPages = importantPages.filter(
+    (page) => page.meta_description && page.meta_description.length > 165
+  );
+  const multipleH1Pages = importantPages.filter((page) => page.h1_count > 1);
+  const canonicalIssuePages = importantPages.filter(
+    (page) =>
+      page.canonical_points_off_domain ||
+      page.canonical_status === "invalid" ||
+      page.canonical_status === "canonicalized"
+  );
+  const missingViewportPages = importantPages.filter(
+    (page) => !page.viewport_present
+  );
+  const missingSchemaPages = importantPages.filter(
+    (page) => page.is_service_like && !page.has_schema
+  );
+  const heavyPages = importantPages.filter(
+    (page) =>
+      Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
+      Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT ||
+      (Number(page.text_to_html_ratio || 0) > 0 &&
+        Number(page.text_to_html_ratio || 0) < LOW_TEXT_TO_HTML_RATIO)
+  );
+  const lowInternalLinkPages = importantPages.filter(
+    (page) => getPath(page.url) !== "/" &&
+      Number(page.internal_link_count || 0) < MIN_INTERNAL_LINKS_ON_IMPORTANT_PAGE
+  );
+  const missingSocialPages = importantPages.filter(
+    (page) => !page.open_graph_present
+  );
+  const nonIndexableImportantPages = importantPages.filter(
+    (page) => page.indexability !== "indexable" && !page.noindex
+  );
+
+  if (multipleTitlePages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-multiple-title-tags",
+        category: "meta_title",
+        customer_category: "Technical SEO",
+        title: "Some pages have more than one search title tag",
+        explanation:
+          "We found important pages with multiple title tags in the page code.",
+        why:
+          "Multiple title tags can make the search result title less predictable.",
+        recommendation:
+          "Keep one title tag per page and remove duplicate title tags from the template or page builder.",
+        current: `${multipleTitlePages.length} page${multipleTitlePages.length === 1 ? "" : "s"} affected`,
+        priority: "medium",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: multipleTitlePages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: multipleTitlePages.length,
+          examples: multipleTitlePages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            title_count: page.title_count,
+            title: page.title,
+          })),
+        },
+      })
+    );
+  }
+
+  if (multipleMetaDescriptionPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-multiple-meta-descriptions",
+        category: "meta_description",
+        customer_category: "Technical SEO",
+        title: "Some pages have more than one search description tag",
+        explanation:
+          "We found important pages with multiple meta description tags in the page code.",
+        why:
+          "Multiple descriptions can make search snippets inconsistent or confusing.",
+        recommendation:
+          "Keep one meta description tag per page and remove duplicate description tags from the page template.",
+        current: `${multipleMetaDescriptionPages.length} page${multipleMetaDescriptionPages.length === 1 ? "" : "s"} affected`,
+        priority: "medium",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: multipleMetaDescriptionPages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: multipleMetaDescriptionPages.length,
+          examples: multipleMetaDescriptionPages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            meta_description_count: page.meta_description_count,
+            meta_description: page.meta_description,
+          })),
+        },
+      })
+    );
+  }
+
+  if (longDescriptionPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-long-meta-descriptions",
+        category: "meta_description",
+        customer_category: "Search appearance",
+        title: "Shorten long search descriptions",
+        explanation:
+          "Some important pages have search descriptions that are likely too long to display cleanly.",
+        why:
+          "Shorter descriptions are easier to scan and are less likely to be cut off in search results.",
+        recommendation:
+          "Rewrite each affected search description so it clearly explains the page in about 140–160 characters.",
+        current: `${longDescriptionPages.length} page${longDescriptionPages.length === 1 ? "" : "s"} affected`,
+        priority: "low",
+        status: "auto_fixed",
+        difficulty: "easy",
+        affected_pages: longDescriptionPages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: longDescriptionPages.length,
+          examples: longDescriptionPages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            length: page.meta_description_length,
+            current_description: page.meta_description,
+            suggested_max_length: 160,
+          })),
+        },
+      })
+    );
+  }
+
+  if (multipleH1Pages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-multiple-main-headings",
+        category: "page_heading",
+        customer_category: "Technical SEO",
+        title: "Some pages have multiple main headings",
+        explanation:
+          "We found important pages with more than one H1 heading.",
+        why:
+          "A single clear main heading helps visitors and search engines understand the page focus.",
+        recommendation:
+          "Keep one clear H1 per page and change extra H1s to H2 or H3 headings where appropriate.",
+        current: `${multipleH1Pages.length} page${multipleH1Pages.length === 1 ? "" : "s"} affected`,
+        priority: "medium",
+        status: "needs_approval",
+        difficulty: "moderate",
+        affected_pages: multipleH1Pages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: multipleH1Pages.length,
+          examples: multipleH1Pages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            h1_count: page.h1_count,
+            h1s: page.h1s,
+          })),
+        },
+      })
+    );
+  }
+
+  if (canonicalIssuePages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-canonical-issues",
+        category: "canonical",
+        customer_category: "Technical SEO",
+        title: "Review canonical settings on important pages",
+        explanation:
+          "Some important pages point their preferred-page tag to another URL or to a URL that may not be valid.",
+        why:
+          "Canonical tags tell search engines which URL should be treated as the main version of a page.",
+        recommendation:
+          "Confirm that each important page has a self-referencing canonical URL unless you intentionally want another page indexed instead.",
+        current: `${canonicalIssuePages.length} page${canonicalIssuePages.length === 1 ? "" : "s"} affected`,
+        priority: "high",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: canonicalIssuePages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: canonicalIssuePages.length,
+          examples: canonicalIssuePages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            canonical_url: page.canonical_url,
+            canonical_status: page.canonical_status,
+            canonical_issue: page.canonical_issue,
+          })),
+        },
+      })
+    );
+  }
+
+  if (nonIndexableImportantPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-non-indexable-important-pages",
+        category: "indexability",
+        customer_category: "Technical SEO",
+        title: "Some important pages may not be indexable",
+        explanation:
+          "We found important pages that may be hard for search engines to include as standalone results.",
+        why:
+          "Important service, location, and conversion pages usually need to be indexable.",
+        recommendation:
+          "Review the technical reasons and make sure important pages return a successful status and are not canonicalized away by mistake.",
+        current: `${nonIndexableImportantPages.length} page${nonIndexableImportantPages.length === 1 ? "" : "s"} affected`,
+        priority: "high",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: nonIndexableImportantPages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: nonIndexableImportantPages.length,
+          examples: nonIndexableImportantPages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            status_code: page.status_code,
+            indexability: page.indexability,
+            reasons: page.indexability_reasons,
+          })),
+        },
+      })
+    );
+  }
+
+  if (missingViewportPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-missing-viewport",
+        category: "mobile_setup",
+        customer_category: "Technical SEO",
+        title: "Add mobile viewport settings",
+        explanation:
+          "Some important pages are missing a viewport meta tag.",
+        why:
+          "Viewport settings help pages display correctly on mobile devices.",
+        recommendation:
+          "Add a standard viewport tag to the site template, such as width=device-width and initial-scale=1.",
+        current: `${missingViewportPages.length} page${missingViewportPages.length === 1 ? "" : "s"} affected`,
+        priority: "medium",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: missingViewportPages.map((page) => getPath(page.url)),
+        details: { affected_count: missingViewportPages.length },
+      })
+    );
+  }
+
+  if (missingSchemaPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-missing-service-schema",
+        category: "schema",
+        customer_category: "Technical SEO",
+        title: "Add structured information to key service pages",
+        explanation:
+          "Some key service-style pages do not appear to include structured data.",
+        why:
+          "Structured data can help search engines understand services, business details, breadcrumbs, FAQs, and reviews.",
+        recommendation:
+          "Add appropriate schema such as LocalBusiness, Service, FAQPage, BreadcrumbList, Review, or AggregateRating where it genuinely fits.",
+        current: `${missingSchemaPages.length} page${missingSchemaPages.length === 1 ? "" : "s"} affected`,
+        priority: "low",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: missingSchemaPages.map((page) => getPath(page.url)),
+        details: { affected_count: missingSchemaPages.length },
+      })
+    );
+  }
+
+  if (heavyPages.length > 0) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-heavy-pages",
+        category: "performance_hint",
+        customer_category: "Technical SEO",
+        title: "Some important pages look heavy or script-heavy",
+        explanation:
+          "Some pages have very large HTML, many scripts, or a low amount of visible text compared with the page code.",
+        why:
+          "Heavy pages can load slower and make it harder for crawlers to quickly understand the main content.",
+        recommendation:
+          "Review scripts, page-builder output, unused app embeds, oversized templates, and content loaded only by JavaScript.",
+        current: `${heavyPages.length} page${heavyPages.length === 1 ? "" : "s"} affected`,
+        priority: "medium",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: heavyPages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: heavyPages.length,
+          examples: heavyPages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            response_size_bytes: page.response_size_bytes,
+            script_tag_count: page.script_tag_count,
+            text_to_html_ratio: page.text_to_html_ratio,
+          })),
+        },
+      })
+    );
+  }
+
+  if (lowInternalLinkPages.length > 0 && lowInternalLinkPages.length <= 30) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-low-internal-links",
+        category: "internal_link",
+        customer_category: "Technical SEO",
+        title: "Add more internal links to important pages",
+        explanation:
+          "Some important pages have very few internal links pointing visitors onward to related pages.",
+        why:
+          "Internal links help visitors find related services and help search engines understand page relationships.",
+        recommendation:
+          "Add relevant links to related services, location pages, FAQs, case studies, contact pages, or conversion pages.",
+        current: `${lowInternalLinkPages.length} page${lowInternalLinkPages.length === 1 ? "" : "s"} affected`,
+        priority: "low",
+        status: "needs_approval",
+        difficulty: "moderate",
+        affected_pages: lowInternalLinkPages.map((page) => getPath(page.url)),
+        details: {
+          affected_count: lowInternalLinkPages.length,
+          examples: lowInternalLinkPages.slice(0, 12).map((page) => ({
+            page: getPath(page.url),
+            internal_link_count: page.internal_link_count,
+          })),
+        },
+      })
+    );
+  }
+
+  if (missingSocialPages.length > 0 && missingSocialPages.length <= 30) {
+    findings.push(
+      groupedFinding({
+        id: "sf-lite-missing-open-graph",
+        category: "social_metadata",
+        customer_category: "Technical SEO",
+        title: "Add social preview information to important pages",
+        explanation:
+          "Some important pages are missing Open Graph metadata for link previews.",
+        why:
+          "Social preview information helps pages look clearer when shared in messaging apps and social platforms.",
+        recommendation:
+          "Add Open Graph title, description, URL, and image tags to important page templates.",
+        current: `${missingSocialPages.length} page${missingSocialPages.length === 1 ? "" : "s"} affected`,
+        priority: "low",
+        status: "needs_developer",
+        difficulty: "developer",
+        affected_pages: missingSocialPages.map((page) => getPath(page.url)),
+        details: { affected_count: missingSocialPages.length },
+      })
+    );
+  }
+
+  return findings;
+}
+
+function buildTechnicalAuditSummary(pages) {
+  const safePages = pages || [];
+  const importantPages = safePages.filter(
+    (page) => page.is_important_page && !page.is_utility_page
+  );
+
+  return {
+    pages_checked: safePages.length,
+    important_pages_checked: importantPages.length,
+    indexable_pages: safePages.filter((page) => page.indexability === "indexable").length,
+    non_indexable_pages: safePages.filter((page) => page.indexability !== "indexable").length,
+    missing_title_count: safePages.filter((page) => !page.title).length,
+    missing_meta_description_count: safePages.filter((page) => !page.meta_description).length,
+    missing_h1_count: safePages.filter((page) => !page.h1).length,
+    multiple_h1_count: safePages.filter((page) => Number(page.h1_count || 0) > 1).length,
+    missing_canonical_count: safePages.filter((page) => !page.canonical_url).length,
+    canonical_issue_count: safePages.filter(
+      (page) => page.canonical_status === "invalid" || page.canonical_points_off_domain
+    ).length,
+    missing_viewport_count: safePages.filter((page) => !page.viewport_present).length,
+    missing_schema_count: importantPages.filter((page) => !page.has_schema).length,
+    heavy_page_count: safePages.filter(
+      (page) =>
+        Number(page.response_size_bytes || 0) >= LARGE_HTML_BYTES ||
+        Number(page.script_tag_count || 0) >= HEAVY_SCRIPT_TAG_COUNT
+    ).length,
+    average_word_count: Math.round(
+      safePages.reduce((sum, page) => sum + Number(page.word_count || 0), 0) /
+        Math.max(safePages.length, 1)
+    ),
+  };
+}
+
 /* ------------------------ SerpAPI competitor discovery ------------------------- */
 
 async function discoverCompetitorsFromSerpApi({
@@ -2656,6 +3159,7 @@
   robots,
   clientRendering,
   competitorComparison,
+  technicalAuditSummary,
 }) {
   const importantPages = pages.filter((p) => p.is_important_page);
   const pagesWithFaq = pages.filter((p) => p.has_faq);
@@ -2736,6 +3240,7 @@
     competitors_found: discoveredCompetitors.length,
     competitor_snapshots_read: competitorPageSnapshots.length,
     client_rendering: clientRendering,
+    technical_audit_summary: technicalAuditSummary || buildTechnicalAuditSummary(pages),
   };
 }
 
@@ -3136,6 +3641,126 @@
   );
 }
 
+function countMetaNameTags(html, name) {
+  const escaped = escapeRegExp(name);
+  const re = new RegExp(
+    `<meta[^>]+(?:name|property)=["']${escaped}["'][^>]*>`,
+    "gi"
+  );
+
+  return (String(html || "").match(re) || []).length;
+}
+
+function detectSocialMeta(html) {
+  return {
+    open_graph: /<meta[^>]+property=["']og:/i.test(String(html || "")),
+    twitter_card: /<meta[^>]+name=["']twitter:/i.test(String(html || "")),
+  };
+}
+
+function extractHreflangs(html, baseUrl) {
+  const output = [];
+  const re = /<link\b[^>]*rel=["'][^"']*alternate[^"']*["'][^>]*>/gi;
+
+  let match;
+
+  while ((match = re.exec(String(html || ""))) !== null) {
+    const tag = match[0];
+    const hreflang = matchFirst(tag, /\bhreflang=["']([^"']+)["']/i);
+    const href = matchFirst(tag, /\bhref=["']([^"']+)["']/i);
+
+    if (!hreflang || !href) continue;
+
+    output.push({
+      hreflang: hreflang.toLowerCase(),
+      href: absolutizeUrl(href, baseUrl),
+    });
+  }
+
+  return output.slice(0, 50);
+}
+
+function buildCanonicalDiagnostics({ pageUrl, canonicalUrl, domain }) {
+  const page = canonicalizeUrl(pageUrl);
+  const canonical = canonicalizeUrl(canonicalUrl);
+
+  if (!canonicalUrl) {
+    return {
+      status: "missing",
+      issue: "No canonical tag was found",
+      isSelfReference: false,
+      pointsOffDomain: false,
+    };
+  }
+
+  if (!canonical) {
+    return {
+      status: "invalid",
+      issue: "Canonical URL could not be read",
+      isSelfReference: false,
+      pointsOffDomain: false,
+    };
+  }
+
+  const canonicalDomain = getDomain(canonical);
+  const pointsOffDomain = Boolean(domain && canonicalDomain && canonicalDomain !== domain);
+  const isSelfReference = Boolean(page && canonical && page === canonical);
+
+  if (pointsOffDomain) {
+    return {
+      status: "off_domain",
+      issue: "Canonical URL points to a different domain",
+      isSelfReference,
+      pointsOffDomain,
+    };
+  }
+
+  if (!isSelfReference) {
+    return {
+      status: "canonicalized",
+      issue: "Canonical URL points to a different page",
+      isSelfReference,
+      pointsOffDomain,
+    };
+  }
+
+  return {
+    status: "self_reference",
+    issue: "",
+    isSelfReference,
+    pointsOffDomain,
+  };
+}
+
+function buildIndexability({ status, robotsMeta, canonicalDiagnostics }) {
+  const reasons = [];
+
+  if (status < 200 || status >= 300) {
+    reasons.push(`HTTP status ${status}`);
+  }
+
+  if (/noindex/i.test(robotsMeta || "")) {
+    reasons.push("Meta robots noindex");
+  }
+
+  if (canonicalDiagnostics?.status === "canonicalized") {
+    reasons.push("Canonical points to another URL");
+  }
+
+  if (canonicalDiagnostics?.status === "off_domain") {
+    reasons.push("Canonical points to another domain");
+  }
+
+  if (canonicalDiagnostics?.status === "invalid") {
+    reasons.push("Canonical URL is invalid");
+  }
+
+  return {
+    status: reasons.length === 0 ? "indexable" : "not_indexable",
+    reasons,
+  };
+}
+
 function getMetaContent(html, name) {
   return getMetaName(html, name);
 }
