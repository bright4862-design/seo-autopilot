import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, business_name, business_type, city, project_id, crawl_job_id } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    let baseUrl = website_url;
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
    const urlObj = new URL(baseUrl);
    const origin = urlObj.origin;
    const domain = urlObj.hostname.replace(/^www\./, '');

    // --- crawler.py: fetch homepage + a few internal pages ---
    const fetchPage = async (url) => {
      try {
        const res = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(12000), headers: { 'User-Agent': 'SEO-Autopilot/1.0' } });
        const html = await res.text();
        return { url, status: res.status, html, ok: res.ok };
      } catch (e) {
        return { url, status: 0, html: '', ok: false, error: e.message };
      }
    };

    const strip = (html) =>
      html.replace(/<script[\s\S]*?<\/script>/gi, '')
          .replace(/<style[\s\S]*?<\/style>/gi, '')
          .replace(/<[^>]+>/g, ' ');
    const text = (html) => strip(html).replace(/\s+/g, ' ').trim();
    const firstMatch = (html, re) => { const m = html.match(re); return m ? (m[1] || '').trim() : ''; };

    const extractPage = (url, html) => {
      const title = firstMatch(html, /<title[^>]*>([\s\S]*?)<\/title>/i);
      const metaDesc =
        firstMatch(html, /<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i) ||
        firstMatch(html, /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["']/i) ||
        '';
      const h1 = firstMatch(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i);
      const canonical =
        firstMatch(html, /<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']*)["']/i) ||
        firstMatch(html, /<link[^>]+href=["']([^"']*)["'][^>]+rel=["']canonical["']/i) ||
        '';
      const wordCount = text(html).split(/\s+/).filter(Boolean).length;
      const links = [];
      const linkRe = /<a[^>]+href=["']([^"']+)["']/gi;
      let lm;
      while ((lm = linkRe.exec(html)) !== null) links.push(lm[1]);
      return { url, title, metaDesc, h1, canonical, wordCount, links };
    };

    // BFS crawl following internal links, up to MAX_PAGES
    const MAX_PAGES = 25;
    const BATCH = 8;
    const visited = new Set();
    const toVisit = [baseUrl];
    const crawledPages = [];

    while (toVisit.length > 0 && visited.size < MAX_PAGES) {
      const batch = [];
      while (toVisit.length > 0 && batch.length < BATCH && visited.size + batch.length < MAX_PAGES) {
        const url = toVisit.shift();
        if (visited.has(url)) continue;
        visited.add(url);
        batch.push(url);
      }
      const results = await Promise.all(batch.map(fetchPage));
      for (const r of results) {
        if (!r.html) {
          if (r.url === baseUrl) {
            return Response.json({ error: "We couldn't reach that website. Please check the URL and try again." }, { status: 400 });
          }
          crawledPages.push({ url: r.url, status: r.status || 0, title: '', metaDesc: '', h1: '', canonical: '', wordCount: 0, links: [] });
          continue;
        }
        const page = extractPage(r.url, r.html);
        page.status = r.status;
        crawledPages.push(page);
        for (const href of page.links) {
          try {
            const abs = new URL(href, baseUrl).href.split('#')[0];
            if (new URL(abs).hostname.replace(/^www\./, '') === domain && !visited.has(abs) && !toVisit.includes(abs) && !/\.(jpg|png|gif|pdf|zip|css|js)$/i.test(abs)) {
              toVisit.push(abs);
            }
          } catch {}
        }
      }
    }

    // --- analyzer.py: deterministic SEO issue detection ---
    const generateBasicTitle = () => {
      if (business_type && city) return `${business_name} | ${business_type} in ${city}`;
      if (business_type) return `${business_name} | ${business_type}`;
      return `${business_name} | Official Website`;
    };

    const generateBasicDescription = () => {
      const name = business_name || 'us';
      const type = (business_type || '').toLowerCase();
      if (business_type && city) return `Visit ${name} for trusted ${type} services in ${city}. Learn more, contact us, or request help today.`;
      if (business_type) return `Visit ${name} for trusted ${type} services. Learn more, contact us, or request help today.`;
      return `Visit ${name} to learn more about our services, contact our team, and get the help you need.`;
    };

    // Utility pages: only flag when broken, never for titles/descriptions/content
    const lowValueRe = /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer)/i;

    const issues = [];
    for (const p of crawledPages) {
      const pageUrl = p.url === baseUrl ? '/' : (() => { try { return new URL(p.url).pathname; } catch { return p.url; } })();
      const isUtility = lowValueRe.test(pageUrl);

      if (p.status === 404 || p.status === 0) {
        issues.push({
          page_url: pageUrl, category: '404_error', customer_category: 'Broken page',
          issue_title: 'This page is broken',
          plain_english_explanation: 'Visitors and search engines may be landing on a page that does not work.',
          why_it_matters: 'Broken pages can hurt trust and make it harder for search engines to understand your website.',
          ai_recommendation: 'Redirect this broken page to the closest working page.',
          current_value: `Status: ${p.status}`, recommended_value: 'Redirect to closest working page',
          priority: 'high', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      if (!isUtility && !p.title) {
        const title = generateBasicTitle();
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'This page needs a search title',
          plain_english_explanation: 'This page does not have a clear title for search engines.',
          why_it_matters: 'The search title helps people and Google understand what the page is about.',
          ai_recommendation: title, current_value: '(empty)', recommended_value: title,
          priority: 'high', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      } else if (!isUtility && p.title && p.title.length < 15) {
        const title = generateBasicTitle();
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'This page has a weak search title',
          plain_english_explanation: 'The current page title is too short or unclear.',
          why_it_matters: 'A better title can help customers understand the page before they click.',
          ai_recommendation: title, current_value: p.title, recommended_value: title,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!isUtility && !p.metaDesc) {
        const desc = generateBasicDescription();
        issues.push({
          page_url: pageUrl, category: 'meta_description', customer_category: 'Search description',
          issue_title: 'This page needs a better search description',
          plain_english_explanation: 'This page does not have a description for search results.',
          why_it_matters: 'A good description can help more people click your website from Google.',
          ai_recommendation: desc, current_value: '(empty)', recommended_value: desc,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!isUtility && !p.canonical) {
        issues.push({
          page_url: pageUrl, category: 'canonical', customer_category: 'Duplicate page signal',
          issue_title: 'Google may be confused by duplicate page versions',
          plain_english_explanation: 'This page does not clearly tell Google which version is the main version.',
          why_it_matters: 'If Google finds multiple versions of the same page, it may not know which one to show.',
          ai_recommendation: 'Set this page as the preferred version of itself.',
          current_value: '(none)', recommended_value: 'Add a canonical tag',
          priority: 'medium', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      const utilityRe = /\/(contact|login|signin|signup|register|cart|checkout|privacy|terms|thank-you|thankyou|booking|account|search|tag|category|admin|wp-admin|dashboard|forgot|reset|cookie|legal|disclaimer)(\/|$)/i;
      const importantRe = /(^\/$)|(home|service|services|product|products|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve)/i;
      if (p.status === 200 && p.wordCount < 250 && !isUtility && !utilityRe.test(pageUrl) && importantRe.test(pageUrl + '|' + (p.title || '') + '|' + (p.h1 || ''))) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Page content',
          issue_title: 'This important page may need more helpful content',
          plain_english_explanation: 'This page looks important, but it may not give customers enough information to understand the service, location, benefits, or next step.',
          why_it_matters: 'Helpful pages usually explain the service, location, benefits, and common questions.',
          ai_recommendation: 'Add helpful details such as services offered, location served, common questions, proof or reviews, and a clear call-to-action.',
          current_value: `${p.wordCount} words`, recommended_value: '250+ words with service details & FAQ',
          priority: 'medium', difficulty: 'developer', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }
    }

    // --- deduplicate by page_url + category + issue_title ---
    const seen = new Set();
    const deduped = issues.filter(i => {
      const key = `${i.page_url}|${i.category}|${i.issue_title}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    const withStatus = deduped.map(issue => {
      const status = issue.group === 'we_can_fix' ? 'auto_fixed' : issue.group === 'needs_developer' ? 'needs_developer' : 'needs_approval';
      return { ...issue, confidence_score: 90, status };
    });

    // --- AI review pass: one LLM call to clean, merge, prioritize and rewrite ---
    let fixes = withStatus;
    let topActions = [];
    let ignoredPages = [];
    let plainSummary = '';
    let groupedRecommendations = [];
    let aiReviewed = false;

    if (withStatus.length > 0) {
      try {
        let competitorData = [];
        if (project_id) {
          try { competitorData = await base44.entities.Competitor.filter({ project_id }); } catch (e) {}
        }
        const pagesForAi = crawledPages.map(p => ({
          url: p.url, status: p.status || 0, title: p.title || '', meta_description: p.metaDesc || '', word_count: p.wordCount || 0,
        }));
        const compForAi = competitorData.map(c => ({
          name: c.name, website_url: c.website_url, service_pages: c.service_pages_count,
          title_quality: c.title_quality_score, description_coverage: c.meta_coverage_pct, content_depth: c.content_depth_score,
        }));

        const aiRes = await base44.integrations.Core.InvokeLLM({
          prompt: `You are an intelligent SEO assistant reviewing raw scan results before showing them to a non-technical small business owner.

Business name: ${business_name || 'Unknown'}
Business type: ${business_type || 'Unknown'}
City: ${city || 'Unknown'}
Website: ${baseUrl}

Crawled pages (JSON): ${JSON.stringify(pagesForAi)}
Raw fixes (JSON): ${JSON.stringify(withStatus.map(f => ({ page_url: f.page_url, category: f.category, customer_category: f.customer_category, issue_title: f.issue_title, plain_english_explanation: f.plain_english_explanation, why_it_matters: f.why_it_matters, ai_recommendation: f.ai_recommendation, current_value: f.current_value, recommended_value: f.recommended_value, priority: f.priority, status: f.status })))}
Competitors (JSON): ${JSON.stringify(compForAi)}

Clean up this fix list:
1. Remove recommendations for low-value utility pages (cart, checkout, login, account, search, legal, privacy, terms, etc.) unless the page is broken. List removed page URLs in ignored_low_value_pages.
2. Merge duplicate or near-duplicate issues for the same page into one fix.
3. Order cleaned_fixes so business-important pages come first (homepage, services, products, about, contact), then by priority.
4. Rewrite issue_title, plain_english_explanation, why_it_matters and ai_recommendation in warm, plain English for a business owner. No technical jargon (never use words like "meta", "canonical", "schema", "crawl", "SEO tag").
5. Improve recommended_value titles and descriptions so they sound natural and specific to this business (use the business name, type and city; titles under 60 characters, descriptions under 155 characters).
6. In grouped_page_recommendations, for each page with 2+ fixes give the page a friendly page_title (e.g. "Wine Club page") and a short list of its recommendations.
7. Give 2-4 top_recommended_actions the owner should do first, and a 2-3 sentence plain_english_summary of the scan.
8. NEVER claim the website was changed, fixed automatically, or that rankings will instantly improve. Use language like "prepared fix", "recommended improvement", "may help", "could improve", "next step".
9. Keep each fix's page_url unchanged, and keep category and status values exactly as they appear in the raw fixes.`,
          response_json_schema: {
            type: 'object',
            properties: {
              cleaned_fixes: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    page_url: { type: 'string' }, category: { type: 'string' }, customer_category: { type: 'string' },
                    issue_title: { type: 'string' }, plain_english_explanation: { type: 'string' }, why_it_matters: { type: 'string' },
                    ai_recommendation: { type: 'string' }, current_value: { type: 'string' }, recommended_value: { type: 'string' },
                    priority: { type: 'string' }, status: { type: 'string' },
                  },
                },
              },
              grouped_page_recommendations: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    page_url: { type: 'string' }, page_title: { type: 'string' },
                    recommendations: { type: 'array', items: { type: 'string' } },
                  },
                },
              },
              top_recommended_actions: { type: 'array', items: { type: 'string' } },
              ignored_low_value_pages: { type: 'array', items: { type: 'string' } },
              plain_english_summary: { type: 'string' },
            },
          },
        });

        const VALID_CATEGORIES = ['meta_title', 'meta_description', '404_error', 'redirect', 'canonical', 'sitemap', 'robots_txt', 'js_rendering', 'internal_link', 'thin_content', 'duplicate_content', 'schema', 'performance', 'web_dev'];
        const VALID_STATUS = ['auto_fixed', 'needs_approval', 'needs_developer'];
        const cleaned = Array.isArray(aiRes?.cleaned_fixes)
          ? aiRes.cleaned_fixes.filter(f => f && f.page_url && f.issue_title && VALID_CATEGORIES.includes(f.category) && VALID_STATUS.includes(f.status))
          : [];

        if (cleaned.length > 0) {
          fixes = cleaned.map(f => ({
            page_url: f.page_url,
            category: f.category,
            customer_category: f.customer_category || '',
            issue_title: f.issue_title,
            plain_english_explanation: f.plain_english_explanation || '',
            why_it_matters: f.why_it_matters || '',
            ai_recommendation: f.ai_recommendation || '',
            current_value: f.current_value || '',
            recommended_value: f.recommended_value || '',
            priority: ['critical', 'high', 'medium', 'low'].includes(f.priority) ? f.priority : 'medium',
            difficulty: f.status === 'needs_developer' ? 'developer' : f.status === 'needs_approval' ? 'moderate' : 'easy',
            status: f.status,
            confidence_score: 85,
            can_auto_fix: f.status === 'auto_fixed',
            requires_approval: f.status === 'needs_approval',
            requires_developer: f.status === 'needs_developer',
          }));
          aiReviewed = true;
          topActions = Array.isArray(aiRes.top_recommended_actions) ? aiRes.top_recommended_actions.filter(a => typeof a === 'string').slice(0, 5) : [];
          ignoredPages = Array.isArray(aiRes.ignored_low_value_pages) ? aiRes.ignored_low_value_pages.filter(a => typeof a === 'string') : [];
          plainSummary = typeof aiRes.plain_english_summary === 'string' ? aiRes.plain_english_summary : '';
          groupedRecommendations = Array.isArray(aiRes.grouped_page_recommendations) ? aiRes.grouped_page_recommendations : [];
        }
      } catch (e) {
        // Fallback: keep deterministic (already utility-filtered and deduplicated) results
      }
    }

    // --- calculate health score from the final fix list ---
    let score = 100;
    for (const f of fixes) {
      if (f.priority === 'critical' || f.priority === 'high') score -= 8;
      else if (f.priority === 'medium') score -= 5;
      else score -= 2;
    }
    score = Math.max(score, 0);

    return Response.json({
      business_name: business_name || null,
      website_url: baseUrl,
      health_score: score,
      pages_crawled: crawledPages.length,
      issues_found: fixes.length,
      ai_reviewed: aiReviewed,
      top_actions: topActions,
      ignored_low_value_pages: ignoredPages,
      plain_english_summary: plainSummary,
      grouped_page_recommendations: groupedRecommendations,
      crawled_pages: crawledPages.map(p => ({
        url: p.url,
        status_code: p.status || 0,
        title: p.title || "",
        meta_description: p.metaDesc || "",
        h1: p.h1 || "",
        canonical_url: p.canonical || "",
        word_count: p.wordCount || 0,
        indexable: true,
        in_sitemap: false,
        rendered_title: "",
        rendered_meta_description: "",
        rendered_canonical: "",
        js_difference_detected: false
      })),
      fixes,
      summary: {
        we_can_fix: fixes.filter(f => f.status === 'auto_fixed').length,
        needs_approval: fixes.filter(f => f.status === 'needs_approval').length,
        needs_developer: fixes.filter(f => f.requires_developer === true).length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});