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

    const issues = [];
    for (const p of crawledPages) {
      const pageUrl = p.url === baseUrl ? '/' : (() => { try { return new URL(p.url).pathname; } catch { return p.url; } })();

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

      if (!p.title) {
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
      } else if (p.title.length < 15) {
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

      if (!p.metaDesc) {
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

      if (!p.canonical) {
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
      if (p.status === 200 && p.wordCount < 250 && !utilityRe.test(pageUrl) && importantRe.test(pageUrl + '|' + (p.title || '') + '|' + (p.h1 || ''))) {
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

    // --- calculate_health_score + map to final fixes ---
    let score = 100;
    const finalIssues = issues.map(issue => {
      if (issue.priority === 'high') score -= 8; else if (issue.priority === 'medium') score -= 5; else score -= 2;
      const status = issue.group === 'we_can_fix' ? 'auto_fixed' : issue.group === 'needs_developer' ? 'needs_developer' : 'needs_approval';
      return { ...issue, confidence_score: 90, status };
    });
    score = Math.max(score, 0);

    return Response.json({
      business_name: business_name || null,
      website_url: baseUrl,
      health_score: score,
      pages_crawled: crawledPages.length,
      issues_found: finalIssues.length,
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
      fixes: finalIssues,
      summary: {
        we_can_fix: finalIssues.filter(f => f.status === 'auto_fixed').length,
        needs_approval: finalIssues.filter(f => f.status === 'needs_approval').length,
        needs_developer: finalIssues.filter(f => f.requires_developer === true).length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});