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
      const pageText = text(html);
      const wordCount = pageText.split(/\s+/).filter(Boolean).length;
      const placeholderPatterns = [
        [/\bgvar\b/i, 'gvar'], [/\bundefined\b/, 'undefined'], [/\bnull\b/, 'null'], [/\bNaN\b/, 'NaN'],
        [/\[object Object\]/, '[object Object]'], [/\{\{[^}]*\}\}/, '{{ }}'],
        [/lorem ipsum/i, 'lorem ipsum'], [/\bplaceholder\b/i, 'placeholder'],
      ];
      const placeholderHits = placeholderPatterns.filter(([re]) => re.test(pageText)).map(([, label]) => label);
      const links = [];
      const linkRe = /<a[^>]+href=["']([^"']+)["']/gi;
      let lm;
      while ((lm = linkRe.exec(html)) !== null) links.push(lm[1]);
      return { url, title, metaDesc, h1, canonical, wordCount, links, placeholderHits };
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

    const describePage = (p, pageUrl) => {
      const name = business_name || domain;
      if (pageUrl === '/') {
        const type = (business_type || 'services').toLowerCase();
        if (city) return `${name} provides ${type} in ${city}. Learn more, get answers to common questions, or contact our team today.`;
        return `${name} provides ${type}. Learn more, get answers to common questions, or contact our team today.`;
      }
      const seg = (pageUrl.split('/').filter(Boolean).pop() || '').replace(/[-_]/g, ' ');
      const topic = ((p.h1 || p.title || seg).split('|')[0].trim() || 'this service').toLowerCase();
      return `Learn about ${topic} from ${name} — what's included, key benefits, and how to get started.`;
    };

    // Utility pages: only flag when broken, never for titles/descriptions/content
    const lowValueRe = /(cart|checkout|login|signin|signup|register|account|search|privacy|terms|thank-?you|payment|admin|wp-admin|reset|forgot|cookie|legal|disclaimer)/i;

    const issues = [];
    const canonicalPages = [];
    const placeholderPages = [];
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
        const desc = describePage(p, pageUrl);
        issues.push({
          page_url: pageUrl, category: 'meta_description', customer_category: 'Search description',
          issue_title: "Improve this page's search description",
          plain_english_explanation: 'This page does not have a description for search results.',
          why_it_matters: 'A good description can help more people click your website from Google.',
          ai_recommendation: desc, current_value: '(empty)', recommended_value: desc,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!isUtility && !p.canonical && !canonicalPages.includes(pageUrl)) {
        canonicalPages.push(pageUrl);
      }

      if (!isUtility && p.status === 200 && (p.placeholderHits || []).length > 0 && !placeholderPages.some(x => x.page === pageUrl)) {
        placeholderPages.push({ page: pageUrl, hits: p.placeholderHits });
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

    // One grouped item for placeholder-like text found in accessible content
    if (placeholderPages.length > 0) {
      issues.push({
        page_url: placeholderPages[0].page, category: 'web_dev', customer_category: 'Page content',
        issue_title: 'Important numbers may not be showing correctly to search engines',
        plain_english_explanation: 'We found placeholder-like text where important business proof or page content may belong. Visitors may see the page normally, but the accessible page content may not clearly show the final information.',
        why_it_matters: 'Important proof points, service details, and trust signals should be easy for search engines and visitors to understand.',
        ai_recommendation: 'Ask a developer to make sure the real text and numbers appear directly in the page content, not only through scripts or placeholders.',
        current_value: 'Affected pages: ' + placeholderPages.map(p => `${p.page} (found: ${p.hits.join(', ')})`).join(' · '),
        recommended_value: 'Real text and numbers visible directly in the page content',
        priority: 'high', difficulty: 'developer', group: 'needs_developer',
        can_auto_fix: false, requires_approval: false, requires_developer: true,
      });
    }

    // One grouped item for preferred-page (canonical) settings instead of one card per page
    if (canonicalPages.length > 0) {
      issues.push({
        page_url: canonicalPages[0], category: 'canonical', customer_category: 'Duplicate-page settings',
        issue_title: 'Review preferred-page settings across important pages',
        plain_english_explanation: 'Several important pages may not clearly tell search engines which version of the page is preferred. This is usually a website setup item, not an emergency.',
        why_it_matters: 'When search engines know the main version of each page, they can show the right page in results.',
        ai_recommendation: 'Ask your developer or SEO cleanup provider to add preferred-page settings to the affected pages.',
        current_value: 'Affected pages: ' + canonicalPages.join(' · '),
        recommended_value: 'Preferred-page settings on each affected page (technical detail: canonical tags)',
        priority: 'medium', difficulty: 'developer', group: 'needs_developer',
        can_auto_fix: false, requires_approval: false, requires_developer: true,
      });
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

    // AI review happens as a second step via the aiReviewScan function, called by the app
    const fixes = withStatus;

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