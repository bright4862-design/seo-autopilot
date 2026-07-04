import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, business_name, business_type, city } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    let baseUrl = website_url;
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
    const urlObj = new URL(baseUrl);
    const origin = urlObj.origin;

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

    const home = await fetchPage(baseUrl);
    if (!home.html) {
      return Response.json({ error: "We couldn't reach that website. Please check the URL and try again." }, { status: 400 });
    }
    const homePage = extractPage(baseUrl, home.html);

    const internalLinks = new Set();
    for (const href of homePage.links) {
      try {
        const abs = new URL(href, baseUrl).href;
        if (abs.startsWith(origin) && !abs.includes('#') && !/\.(jpg|png|gif|pdf|zip)$/i.test(abs)) internalLinks.add(abs);
      } catch {}
    }
    const pagesToCrawl = Array.from(internalLinks).slice(0, 4);
    const otherPages = (await Promise.all(pagesToCrawl.map(fetchPage)))
      .filter(p => p.html)
      .map(p => ({ ...extractPage(p.url, p.html), status: p.status }));

    const crawledPages = [homePage, ...otherPages];

    // --- analyzer.py: detect real SEO issues ---
    const detected = [];
    const push = (p, fields) => detected.push({ page_url: p.url === baseUrl ? '/' : new URL(p.url).pathname, ...fields });

    for (const p of crawledPages) {
      if (!p.title) push(p, { category: 'meta_title', priority: 'high', issue_title: 'Missing page title', current_value: '(empty)', recommended_value: 'A clear 30–60 character title', detail: 'This page has no <title> tag.' });
      else if (p.title.length < 10 || p.title.length > 65) push(p, { category: 'meta_title', priority: 'medium', issue_title: 'Page title length is not ideal', current_value: p.title, recommended_value: 'A clear 30–60 character title', detail: `Title is ${p.title.length} characters.` });

      if (!p.metaDesc) push(p, { category: 'meta_description', priority: 'medium', issue_title: 'Missing meta description', current_value: '(empty)', recommended_value: 'A 150–160 character summary', detail: 'This page has no meta description.' });
      else if (p.metaDesc.length > 160) push(p, { category: 'meta_description', priority: 'low', issue_title: 'Meta description is too long', current_value: p.metaDesc, recommended_value: 'Shorten to under 160 characters', detail: `Description is ${p.metaDesc.length} characters.` });

      if (!p.h1) push(p, { category: 'meta_title', priority: 'medium', issue_title: 'Missing main heading (H1)', current_value: '(none)', recommended_value: 'A descriptive H1 heading', detail: 'This page has no H1.' });

      if (p.wordCount < 300) push(p, { category: 'thin_content', priority: 'high', issue_title: 'Very little content on this page', current_value: `${p.wordCount} words`, recommended_value: '300+ words with service details & FAQ', detail: 'This page has thin content.' });

      if (!p.canonical) push(p, { category: 'canonical', priority: 'medium', issue_title: 'No canonical tag', current_value: '(none)', recommended_value: 'Add a canonical tag', detail: 'This page has no canonical tag.' });

      if (p.status === 404) push(p, { category: '404_error', priority: 'high', issue_title: 'Broken page returning an error', current_value: '404 error', recommended_value: 'Fix or redirect the page', detail: 'This page returned a 404.' });
    }

    // --- ai_recommendations.py: generate plain-English fixes + grouping ---
    let fixes = [];
    if (detected.length > 0) {
      try {
        const llmRes = await base44.asServiceRole.integrations.Core.InvokeLLM({
          prompt:
            'You are an SEO advisor for non-technical small business owners. For each detected SEO issue, write a plain-English explanation, why it matters, an AI recommendation, and assign it to exactly ONE group: "we_can_fix" (simple, auto-fixable now), "needs_approval" (a fix is prepared, owner just approves), or "needs_developer" (requires a developer).\n\n' +
            `Business: ${business_name || 'This business'}\nType: ${business_type || 'N/A'}\nCity: ${city || 'N/A'}\n\n` +
            'Detected issues (the "issue_index" in your output must match the order below):\n' +
            JSON.stringify(detected, null, 2) +
            '\n\nReturn a JSON object with a "fixes" array. Each item: issue_index (number), plain_english_explanation (string), why_it_matters (string), ai_recommendation (string), group (one of we_can_fix|needs_approval|needs_developer), impact (high|medium|low).',
          response_json_schema: {
            type: 'object',
            properties: {
              fixes: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    issue_index: { type: 'number' },
                    plain_english_explanation: { type: 'string' },
                    why_it_matters: { type: 'string' },
                    ai_recommendation: { type: 'string' },
                    group: { type: 'string', enum: ['we_can_fix', 'needs_approval', 'needs_developer'] },
                    impact: { type: 'string', enum: ['high', 'medium', 'low'] },
                  },
                  required: ['issue_index', 'plain_english_explanation', 'why_it_matters', 'ai_recommendation', 'group', 'impact'],
                },
              },
            },
            required: ['fixes'],
          },
        });
        fixes = llmRes.fixes || [];
      } catch (e) {
        console.error('LLM recommendations failed', e.message);
      }
    }

    // --- calculate_health_score + assemble fixes ---
    let score = 100;
    const finalIssues = detected.map((d, i) => {
      const fix = fixes.find(f => f.issue_index === i) || {};
      const group = fix.group || 'needs_approval';
      const impact = fix.impact || d.priority;
      if (impact === 'high') score -= 8; else if (impact === 'medium') score -= 5; else score -= 2;
      const status = group === 'we_can_fix' ? 'auto_fixed' : group === 'needs_developer' ? 'needs_developer' : 'needs_approval';
      return {
        page_url: d.page_url,
        category: d.category,
        priority: d.priority,
        issue_title: d.issue_title,
        plain_english_explanation: fix.plain_english_explanation || d.detail,
        why_it_matters: fix.why_it_matters || '',
        current_value: d.current_value,
        recommended_value: d.recommended_value,
        ai_recommendation: fix.ai_recommendation || '',
        confidence_score: 85,
        can_auto_fix: group === 'we_can_fix',
        requires_approval: group === 'needs_approval',
        requires_developer: group === 'needs_developer',
        status,
      };
    });
    score = Math.max(score, 0);

    return Response.json({
      business_name: business_name || null,
      website_url: baseUrl,
      health_score: score,
      pages_crawled: crawledPages.length,
      issues_found: finalIssues.length,
      fixes: finalIssues,
      summary: {
        we_can_fix: finalIssues.filter(f => f.status === 'auto_fixed').length,
        needs_approval: finalIssues.filter(f => f.status === 'needs_approval').length,
        needs_developer: finalIssues.filter(f => f.status === 'needs_developer').length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});