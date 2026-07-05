import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

const SERVICE_WORDS = /service|product|treatment|location|pricing|appointment|repair|installation|consultation/i;

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { project_id, business_type, city, customer_pages } = await req.json();
    if (!project_id) return Response.json({ error: 'project_id is required' }, { status: 400 });

    const competitors = await base44.entities.Competitor.filter({ project_id });
    if (competitors.length === 0) {
      return Response.json({ competitors: [], insights: [] });
    }

    const strip = (html) =>
      html.replace(/<script[\s\S]*?<\/script>/gi, '')
          .replace(/<style[\s\S]*?<\/style>/gi, '')
          .replace(/<[^>]+>/g, ' ');
    const text = (html) => strip(html).replace(/\s+/g, ' ').trim();
    const firstMatch = (html, re) => { const m = html.match(re); return m ? (m[1] || '').trim() : ''; };

    const fetchPage = async (url) => {
      try {
        const res = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(10000), headers: { 'User-Agent': 'SEO-Autopilot/1.0' } });
        const html = await res.text();
        return { url, status: res.status, html };
      } catch {
        return { url, status: 0, html: '' };
      }
    };

    const crawlSite = async (websiteUrl) => {
      let baseUrl = websiteUrl;
      if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
      const domain = new URL(baseUrl).hostname.replace(/^www\./, '');
      const MAX_PAGES = 10;
      const visited = new Set();
      const toVisit = [baseUrl];
      const pages = [];
      while (toVisit.length > 0 && visited.size < MAX_PAGES) {
        const batch = [];
        while (toVisit.length > 0 && batch.length < 5 && visited.size + batch.length < MAX_PAGES) {
          const url = toVisit.shift();
          if (visited.has(url)) continue;
          visited.add(url);
          batch.push(url);
        }
        const results = await Promise.all(batch.map(fetchPage));
        for (const r of results) {
          const html = r.html || '';
          const bodyText = text(html);
          pages.push({
            url: r.url,
            status: r.status,
            title: firstMatch(html, /<title[^>]*>([\s\S]*?)<\/title>/i),
            metaDesc:
              firstMatch(html, /<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i) ||
              firstMatch(html, /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["']/i) || '',
            h1: firstMatch(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i),
            wordCount: bodyText.split(/\s+/).filter(Boolean).length,
            hasFaq: /faq|frequently asked/i.test(bodyText) || (bodyText.match(/\?/g) || []).length >= 5,
            hasSchema: html.includes('application/ld+json') || html.includes('schema.org'),
          });
          const linkRe = /<a[^>]+href=["']([^"']+)["']/gi;
          let lm;
          while ((lm = linkRe.exec(html)) !== null) {
            try {
              const abs = new URL(lm[1], baseUrl).href.split('#')[0];
              if (new URL(abs).hostname.replace(/^www\./, '') === domain && !visited.has(abs) && !toVisit.includes(abs) && !/\.(jpg|png|gif|pdf|zip|css|js)$/i.test(abs)) {
                toVisit.push(abs);
              }
            } catch {}
          }
        }
      }
      return pages;
    };

    const titleScore = (title) => {
      if (!title) return 0;
      let s = 40;
      if (title.length >= 20 && title.length <= 70) s += 20;
      if (SERVICE_WORDS.test(title) || (business_type && title.toLowerCase().includes(String(business_type).toLowerCase()))) s += 20;
      if (city && title.toLowerCase().includes(String(city).toLowerCase())) s += 20;
      return s;
    };

    const computeMetrics = (pages) => {
      const okPages = pages.filter(p => p.status === 200);
      const servicePages = okPages.filter(p =>
        SERVICE_WORDS.test(p.url) || SERVICE_WORDS.test(p.title || '') || SERVICE_WORDS.test(p.h1 || '')
      ).length;
      const avgTitle = okPages.length ? Math.round(okPages.reduce((s, p) => s + titleScore(p.title), 0) / okPages.length) : 0;
      const metaPct = okPages.length ? Math.round((okPages.filter(p => p.metaDesc).length / okPages.length) * 100) : 0;
      const avgWords = okPages.length ? okPages.reduce((s, p) => s + (p.wordCount || 0), 0) / okPages.length : 0;
      const depth = avgWords <= 150 ? 30 : avgWords <= 300 ? 60 : 90;
      const broken = pages.filter(p => p.status === 404 || p.status === 0).length;
      return {
        pages_crawled: pages.length,
        service_pages_count: servicePages,
        title_quality_score: avgTitle,
        meta_coverage_pct: metaPct,
        content_depth_score: depth,
        faq_usage: pages.some(p => p.hasFaq),
        schema_usage: pages.some(p => p.hasSchema),
        broken_links_count: broken,
      };
    };

    // Crawl competitors sequentially (each crawls its pages in parallel batches)
    const results = [];
    for (const comp of competitors) {
      const pages = await crawlSite(comp.website_url);
      const metrics = computeMetrics(pages);
      const name = comp.name || (() => { try { return new URL(/^https?:\/\//i.test(comp.website_url) ? comp.website_url : 'https://' + comp.website_url).hostname.replace(/^www\./, ''); } catch { return comp.website_url; } })();
      await base44.entities.Competitor.update(comp.id, {
        name,
        service_pages_count: metrics.service_pages_count,
        title_quality_score: metrics.title_quality_score,
        meta_coverage_pct: metrics.meta_coverage_pct,
        content_depth_score: metrics.content_depth_score,
        faq_usage: metrics.faq_usage,
        schema_usage: metrics.schema_usage,
        broken_links_count: metrics.broken_links_count,
      });
      results.push({ id: comp.id, name, website_url: comp.website_url, ...metrics });
    }

    // Customer metrics from the customer's own crawl data
    const custPages = (customer_pages || []).map(p => ({
      url: p.url, status: p.status_code, title: p.title || '', metaDesc: p.meta_description || '',
      h1: p.h1 || '', wordCount: p.word_count || 0, hasFaq: false, hasSchema: false,
    }));
    const customer = computeMetrics(custPages);

    const avg = (key) => results.length ? results.reduce((s, r) => s + (r[key] || 0), 0) / results.length : 0;
    const topFor = (key) => results.reduce((best, r) => (r[key] > (best?.[key] ?? -1) ? r : best), null);

    const insights = [];
    const addInsight = (key, title, explanation, action, impact) => {
      const top = topFor(key) || results[0];
      insights.push({
        owner_user_id: user.id,
        project_id,
        competitor_id: top?.id || '',
        competitor_url: top?.website_url || '',
        insight_title: title,
        explanation,
        recommended_action: action,
        impact,
        created_at: new Date().toISOString(),
      });
    };

    if (avg('service_pages_count') > customer.service_pages_count) {
      addInsight('service_pages_count',
        'Competitors have more dedicated service pages',
        'Your competitors appear to have separate pages for important services, while your website may mention those services more generally.',
        'Create or improve dedicated pages for your most important services.',
        'high');
    }
    if (avg('title_quality_score') > customer.title_quality_score) {
      addInsight('title_quality_score',
        'Competitors use clearer search titles',
        "Your competitors' page titles may do a better job explaining the service and location.",
        'Review your prepared title recommendations and update the most important pages first.',
        'medium');
    }
    if (avg('meta_coverage_pct') > customer.meta_coverage_pct) {
      addInsight('meta_coverage_pct',
        'Competitors have better search descriptions',
        'More of their pages include search descriptions, which can make listings clearer in Google.',
        'Review and use the prepared search descriptions for your important pages.',
        'medium');
    }
    if (avg('content_depth_score') > customer.content_depth_score) {
      addInsight('content_depth_score',
        'Competitors may answer more customer questions',
        'Their pages appear to contain more helpful information about services, locations, or next steps.',
        'Add useful details, FAQs, proof, reviews, and calls to action to your important pages.',
        'high');
    }
    if (customer.broken_links_count > avg('broken_links_count')) {
      addInsight('broken_links_count',
        'Your site has more broken pages',
        'Broken pages can frustrate visitors and make your website look less reliable.',
        'Review broken-page fixes before adding new content.',
        'high');
    }

    try { await base44.entities.CompetitorInsight.deleteMany({ project_id }); } catch {}
    if (insights.length > 0) {
      await base44.entities.CompetitorInsight.bulkCreate(insights);
    }

    return Response.json({ customer, competitors: results, insights });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});