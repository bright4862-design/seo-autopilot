import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, max_pages } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    const MAX_PAGES = Math.min(Math.max(Number(max_pages) || 50, 1), 50);
    const CRAWL_BATCH_SIZE = 6;
    const LINK_CHECK_BATCH_SIZE = 10;
    const USER_AGENT = 'SEO-Autopilot/1.0';
    const FETCH_TIMEOUT_MS = 12000;
    const LINK_TIMEOUT_MS = 7000;
    const MAX_HTML_BYTES = 1800000;

    const normalizeHostname = (hostname) => String(hostname || '').toLowerCase().replace(/^www\./, '');
    const assetRe = /\.(jpg|jpeg|png|gif|webp|svg|ico|css|js|mjs|pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|7z|gz|mp3|mp4|mov|avi|wmv|webm|woff|woff2|ttf|eot)(\?|$)/i;
    const utilityPageRe = /(^|\/)(cart|basket|checkout|login|log-in|signin|sign-in|signup|sign-up|register|account|my-account|search|privacy|privacy-policy|terms|terms-of-service|conditions|thank-you|thankyou|payment|payments|admin|wp-admin|wp-login|reset|forgot|password|cookie|cookies|legal|disclaimer|sitemap|feed|rss|tag|tags|category|author|wishlist)(\/|$)/i;
    const importantPageRe = /(^\/$|home|service|services|product|products|solution|solutions|about|location|locations|contact|book|booking|appointment|pricing|price|packages|service-area|areas-we-serve|reviews|testimonials|case-stud|portfolio|work|menu|shop|store|team|faq|faqs)/i;
    const placeholderPatterns = [
      { label: 'gvar', re: /\bgvar\b/i },
      { label: 'undefined', re: /\bundefined\b/i },
      { label: 'null', re: /\bnull\b/i },
      { label: 'NaN', re: /\bNaN\b/ },
      { label: '[object Object]', re: /\[object Object\]/i },
      { label: '{{ placeholder }}', re: /\{\{\s*[^}]+\s*\}\}/ },
      { label: '${ placeholder }', re: /\$\{\s*[^}]+\s*\}/ },
      { label: 'lorem ipsum', re: /lorem ipsum/i },
      { label: 'placeholder', re: /\bplaceholder\b/i },
      { label: 'todo/tbd', re: /\b(todo|tbd|coming soon)\b/i },
      { label: 'template token', re: /%%[^%]{2,80}%%|\[\[[^\]]{2,80}\]\]/ },
    ];

    const decodeHtml = (value) => String(value || '')
      .replace(/&amp;/gi, '&')
      .replace(/&quot;/gi, '"')
      .replace(/&#39;|&apos;/gi, "'")
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/&nbsp;/gi, ' ');

    const stripTags = (html) => decodeHtml(String(html || '')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
      .replace(/<!--([\s\S]*?)-->/g, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim());

    const getAttr = (tag, attr) => {
      const re = new RegExp(attr + "\\s*=\\s*([\"'])([\\s\\S]*?)\\1", 'i');
      const match = String(tag || '').match(re);
      return match ? decodeHtml(match[2].trim()) : '';
    };

    const firstMatch = (html, re) => {
      const match = String(html || '').match(re);
      return match ? stripTags(match[1] || '') : '';
    };

    const normalizeUrl = (rawUrl, baseUrl) => {
      try {
        if (!rawUrl) return null;
        const trimmed = String(rawUrl).trim();
        if (!trimmed || /^#/.test(trimmed) || /^(mailto|tel|sms|javascript|data|blob):/i.test(trimmed)) return null;
        const withProtocol = baseUrl ? trimmed : (/^https?:\/\//i.test(trimmed) ? trimmed : 'https://' + trimmed);
        const url = new URL(withProtocol, baseUrl || undefined);
        if (!/^https?:$/i.test(url.protocol)) return null;
        url.hash = '';
        url.hostname = url.hostname.toLowerCase();
        const paramsToRemove = [];
        url.searchParams.forEach((_, key) => {
          if (/^(utm_|fbclid|gclid|msclkid|mc_cid|mc_eid|igshid|ref$)/i.test(key)) paramsToRemove.push(key);
        });
        paramsToRemove.forEach((key) => url.searchParams.delete(key));
        url.searchParams.sort();
        let href = url.href;
        if (url.pathname !== '/' && href.endsWith('/')) href = href.slice(0, -1);
        return href;
      } catch (_error) {
        return null;
      }
    };

    const startUrl = normalizeUrl(website_url, null);
    if (!startUrl) return Response.json({ error: 'Please enter a valid website URL.' }, { status: 400 });

    const start = new URL(startUrl);
    const domain = normalizeHostname(start.hostname);
    const origin = start.origin;
    const crawlWarnings = [];

    const isSameDomain = (url) => {
      try { return normalizeHostname(new URL(url).hostname) === domain; } catch (_error) { return false; }
    };

    const isLowValueUrl = (url) => {
      try {
        const parsed = new URL(url);
        const path = parsed.pathname.toLowerCase();
        return assetRe.test(parsed.href) || utilityPageRe.test(path);
      } catch (_error) {
        return true;
      }
    };

    const pathOf = (url) => {
      try {
        const parsed = new URL(url);
        return parsed.pathname === '/' ? '/' : parsed.pathname.replace(/\/$/, '');
      } catch (_error) {
        return url;
      }
    };

    const fetchPage = async (url) => {
      try {
        const res = await fetch(url, {
          redirect: 'follow',
          signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
          headers: { 'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' },
        });
        const finalUrl = normalizeUrl(res.url || url, null) || url;
        const contentType = res.headers.get('content-type') || '';
        if (!/text\/html|application\/xhtml\+xml/i.test(contentType)) {
          return { url, finalUrl, status: res.status, ok: res.ok, html: '', contentType, skipped: 'non_html' };
        }
        const html = (await res.text()).slice(0, MAX_HTML_BYTES);
        return { url, finalUrl, status: res.status, ok: res.ok, html, contentType, skipped: '' };
      } catch (error) {
        return { url, finalUrl: url, status: 0, ok: false, html: '', contentType: '', skipped: '', error: error.message || 'Fetch failed' };
      }
    };

    const extractLinks = (html, pageUrl) => {
      const links = [];
      const linkTagRe = /<a\b[^>]*>([\s\S]*?)<\/a>/gi;
      let match;
      while ((match = linkTagRe.exec(html)) !== null) {
        const tag = match[0];
        const href = getAttr(tag, 'href');
        const normalized = normalizeUrl(href, pageUrl);
        if (!normalized) continue;
        links.push({
          href: normalized,
          raw_href: href,
          anchor_text: stripTags(match[1]).slice(0, 120),
          rel: getAttr(tag, 'rel'),
          internal: isSameDomain(normalized),
        });
      }
      return links;
    };

    const extractJsonLd = (html) => {
      const items = [];
      const scriptRe = /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
      let match;
      while ((match = scriptRe.exec(html)) !== null) {
        const raw = decodeHtml(match[1] || '').trim();
        if (!raw) continue;
        try {
          const parsed = JSON.parse(raw);
          items.push(...(Array.isArray(parsed) ? parsed : [parsed]));
        } catch (_error) {
          items.push({ parse_error: true, raw_preview: raw.slice(0, 220) });
        }
      }
      return items;
    };

    const flattenSchemaTypes = (items) => {
      const types = [];
      const visit = (value) => {
        if (!value || typeof value !== 'object') return;
        if (value['@type']) types.push(...(Array.isArray(value['@type']) ? value['@type'].map(String) : [String(value['@type'])]));
        if (Array.isArray(value['@graph'])) value['@graph'].forEach(visit);
      };
      items.forEach(visit);
      return [...new Set(types)];
    };

    const extractHeadings = (html, level) => {
      const re = new RegExp(`<h${level}\\b[^>]*>([\\s\\S]*?)<\\/h${level}>`, 'gi');
      const headings = [];
      let match;
      while ((match = re.exec(html)) !== null) {
        const value = stripTags(match[1]);
        if (value) headings.push(value);
      }
      return headings.slice(0, 20);
    };

    const extractMeta = (html, desiredName) => {
      const metaRe = /<meta\b[^>]*>/gi;
      let match;
      while ((match = metaRe.exec(html)) !== null) {
        const tag = match[0];
        const name = (getAttr(tag, 'name') || getAttr(tag, 'property')).toLowerCase();
        if (name === desiredName) return getAttr(tag, 'content');
      }
      return '';
    };

    const extractCanonical = (html, pageUrl) => {
      const linkRe = /<link\b[^>]*>/gi;
      let match;
      while ((match = linkRe.exec(html)) !== null) {
        const tag = match[0];
        if ((getAttr(tag, 'rel') || '').toLowerCase().split(/\s+/).includes('canonical')) return normalizeUrl(getAttr(tag, 'href'), pageUrl) || getAttr(tag, 'href');
      }
      return '';
    };

    const extractPage = (fetchResult) => {
      const html = fetchResult.html || '';
      const pageUrl = fetchResult.finalUrl || fetchResult.url;
      const bodyText = stripTags(html);
      const words = bodyText.match(/[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)?/g) || [];
      const links = extractLinks(html, pageUrl);
      const jsonLd = extractJsonLd(html);
      const schemaTypes = flattenSchemaTypes(jsonLd);
      const h1s = extractHeadings(html, 1);
      const h2s = extractHeadings(html, 2);
      const h3s = extractHeadings(html, 3);
      const imageTags = html.match(/<img\b[^>]*>/gi) || [];
      const ctaMatches = bodyText.match(/\b(contact us|call now|get a quote|request a quote|book now|schedule|make an appointment|buy now|shop now|start today|learn more|sign up|subscribe|get started)\b/gi) || [];
      const trustMatches = bodyText.match(/\b(review|reviews|testimonial|testimonials|licensed|insured|certified|award|awards|guarantee|years of experience|trusted|case study|case studies|portfolio|clients|customer rating|stars)\b/gi) || [];
      const phoneMatches = bodyText.match(/(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}/g) || [];
      const emailMatches = bodyText.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [];
      const socialLinks = links.filter((link) => /facebook\.com|instagram\.com|linkedin\.com|youtube\.com|tiktok\.com|x\.com|twitter\.com/i.test(link.href)).map((link) => link.href);
      const placeholderHits = placeholderPatterns.filter((item) => item.re.test(bodyText)).map((item) => item.label);
      const title = firstMatch(html, /<title\b[^>]*>([\s\S]*?)<\/title>/i);
      const metaDescription = extractMeta(html, 'description') || extractMeta(html, 'og:description');
      const robots = extractMeta(html, 'robots');
      const isUtilityPage = isLowValueUrl(pageUrl);
      const importantHaystack = `${pathOf(pageUrl)} ${title} ${h1s[0] || ''}`;

      return {
        url: pageUrl,
        requested_url: fetchResult.url,
        status_code: fetchResult.status || 0,
        content_type: fetchResult.contentType || '',
        title,
        title_length: title.length,
        meta_description: metaDescription,
        meta_description_length: metaDescription.length,
        h1: h1s[0] || '',
        h1_count: h1s.length,
        h1s,
        h2s,
        h3s,
        canonical_url: extractCanonical(html, pageUrl),
        robots,
        word_count: words.length,
        internal_links_count: links.filter((link) => link.internal).length,
        external_links_count: links.filter((link) => !link.internal).length,
        links,
        images_total: imageTags.length,
        images_missing_alt: imageTags.filter((tag) => !getAttr(tag, 'alt')).length,
        forms_count: (html.match(/<form\b/gi) || []).length,
        schema_types: schemaTypes,
        json_ld_count: jsonLd.length,
        has_faq: schemaTypes.some((type) => /FAQPage/i.test(type)) || (bodyText.match(/\?/g) || []).length >= 2,
        faq_question_count: (bodyText.match(/\?/g) || []).length,
        has_cta: ctaMatches.length > 0,
        cta_count: ctaMatches.length,
        has_trust_signals: trustMatches.length > 0,
        trust_signal_count: trustMatches.length,
        phone_count: phoneMatches.length,
        email_count: emailMatches.length,
        has_address_hint: /\b(street|st\.|avenue|ave\.|road|rd\.|boulevard|blvd\.|suite|unit|postcode|postal code|zip code)\b/i.test(bodyText),
        social_links: [...new Set(socialLinks)].slice(0, 10),
        placeholder_hits: placeholderHits,
        is_utility_page: isUtilityPage,
        is_important_page: importantPageRe.test(importantHaystack) && !isUtilityPage,
        text_preview: bodyText.slice(0, 700),
        indexable: !/noindex/i.test(robots),
        in_sitemap: false,
        rendered_title: '',
        rendered_meta_description: '',
        rendered_canonical: '',
        js_difference_detected: false,
      };
    };

    const rawFindings = [];
    const addFinding = (type, severity, pageUrl, evidence, details = {}) => rawFindings.push({ type, severity, page_url: pageUrl, evidence, ...details });

    const visited = new Set();
    const queued = new Set([startUrl]);
    const queue = [startUrl];
    const crawledPages = [];

    while (queue.length > 0 && visited.size < MAX_PAGES) {
      const batch = [];
      while (queue.length > 0 && batch.length < CRAWL_BATCH_SIZE && visited.size + batch.length < MAX_PAGES) {
        const nextUrl = queue.shift();
        queued.delete(nextUrl);
        if (!nextUrl || visited.has(nextUrl) || !isSameDomain(nextUrl) || isLowValueUrl(nextUrl)) continue;
        visited.add(nextUrl);
        batch.push(nextUrl);
      }
      if (batch.length === 0) break;

      const results = await Promise.all(batch.map(fetchPage));
      for (const result of results) {
        if (result.error) crawlWarnings.push({ type: 'fetch_failed', url: result.url, message: result.error });
        if (result.skipped === 'non_html') crawlWarnings.push({ type: 'non_html_skipped', url: result.url, content_type: result.contentType });

        if (!result.html) {
          crawledPages.push({ url: result.finalUrl || result.url, requested_url: result.url, status_code: result.status || 0, content_type: result.contentType || '', title: '', title_length: 0, meta_description: '', meta_description_length: 0, h1: '', h1_count: 0, h1s: [], h2s: [], h3s: [], canonical_url: '', robots: '', word_count: 0, internal_links_count: 0, external_links_count: 0, links: [], images_total: 0, images_missing_alt: 0, forms_count: 0, schema_types: [], json_ld_count: 0, has_faq: false, faq_question_count: 0, has_cta: false, cta_count: 0, has_trust_signals: false, trust_signal_count: 0, phone_count: 0, email_count: 0, has_address_hint: false, social_links: [], placeholder_hits: [], is_utility_page: isLowValueUrl(result.finalUrl || result.url), is_important_page: false, text_preview: '', indexable: false, in_sitemap: false, rendered_title: '', rendered_meta_description: '', rendered_canonical: '', js_difference_detected: false });
          continue;
        }

        const page = extractPage(result);
        crawledPages.push(page);

        for (const link of page.links) {
          if (!link.internal || isLowValueUrl(link.href)) continue;
          if (!visited.has(link.href) && !queued.has(link.href) && queue.length + visited.size < MAX_PAGES * 3) {
            queued.add(link.href);
            queue.push(link.href);
          }
        }
      }
    }

    if (crawledPages.length === 0 || crawledPages[0].status_code === 0) {
      return Response.json({ error: "We couldn't reach that website. Please check the URL and try again." }, { status: 400 });
    }

    const analysisPages = crawledPages.filter((page) => page.status_code >= 200 && page.status_code < 400 && !page.is_utility_page);
    const importantPages = analysisPages.filter((page) => page.is_important_page);

    for (const page of analysisPages) {
      if (!page.title) addFinding('missing_title', 'high', page.url, 'No <title> tag found.', { category: 'seo', current_value: '' });
      else if (page.title_length < 20) addFinding('weak_title_short', 'medium', page.url, `Title is ${page.title_length} characters.`, { category: 'seo', current_value: page.title });
      else if (page.title_length > 65) addFinding('weak_title_long', 'low', page.url, `Title is ${page.title_length} characters.`, { category: 'seo', current_value: page.title });
      else if (/^(home|welcome|untitled|new page|index)$/i.test(page.title.trim())) addFinding('generic_title', 'medium', page.url, `Generic title: ${page.title}`, { category: 'seo', current_value: page.title });

      if (!page.meta_description) addFinding('missing_meta_description', 'medium', page.url, 'No meta description found.', { category: 'seo', current_value: '' });
      else if (page.meta_description_length < 50) addFinding('weak_meta_description_short', 'low', page.url, `Description is ${page.meta_description_length} characters.`, { category: 'seo', current_value: page.meta_description });
      else if (page.meta_description_length > 170) addFinding('weak_meta_description_long', 'low', page.url, `Description is ${page.meta_description_length} characters.`, { category: 'seo', current_value: page.meta_description });

      if (page.h1_count === 0) addFinding('missing_h1', 'medium', page.url, 'No H1 heading found.', { category: 'content' });
      if (page.h1_count > 1) addFinding('multiple_h1', 'low', page.url, `${page.h1_count} H1 headings found.`, { category: 'content', current_value: page.h1s.join(' | ') });
      if (page.placeholder_hits.length > 0) addFinding('placeholder_or_dynamic_text', 'high', page.url, `Found placeholder-like text: ${page.placeholder_hits.join(', ')}`, { category: 'technical', current_value: page.placeholder_hits.join(', ') });
      if (!page.canonical_url && page.is_important_page) addFinding('missing_canonical', 'low', page.url, 'Important page has no canonical URL.', { category: 'technical' });
      if (page.images_total > 0 && page.images_missing_alt / page.images_total >= 0.5) addFinding('many_images_missing_alt', 'low', page.url, `${page.images_missing_alt} of ${page.images_total} images are missing alt text.`, { category: 'accessibility' });
      if (page.is_important_page && page.word_count < 250) addFinding('thin_important_page', 'medium', page.url, `Important page has ${page.word_count} words.`, { category: 'content', current_value: String(page.word_count) });
      if (page.is_important_page && !page.has_cta) addFinding('missing_clear_cta', 'low', page.url, 'Important page does not appear to include a clear call to action.', { category: 'conversion' });
      if (page.is_important_page && !page.has_trust_signals) addFinding('missing_trust_signals', 'low', page.url, 'Important page does not appear to include reviews, proof, credentials, or similar trust signals.', { category: 'trust' });
      if ((/contact|location|about/i.test(pathOf(page.url) + ' ' + page.title) || page.url === origin || page.url === startUrl) && page.phone_count === 0 && page.email_count === 0 && page.forms_count === 0) {
        addFinding('missing_contact_path', 'medium', page.url, 'Important business page does not show a phone number, email address, or form in HTML.', { category: 'trust' });
      }
    }

    const titleMap = new Map();
    const descMap = new Map();
    for (const page of analysisPages) {
      if (page.title) titleMap.set(page.title.toLowerCase(), [...(titleMap.get(page.title.toLowerCase()) || []), page.url]);
      if (page.meta_description) descMap.set(page.meta_description.toLowerCase(), [...(descMap.get(page.meta_description.toLowerCase()) || []), page.url]);
    }
    for (const [title, pages] of titleMap.entries()) if (pages.length >= 3) addFinding('duplicate_titles', 'medium', pages[0], `Same title appears on ${pages.length} pages.`, { category: 'seo', pages, current_value: title });
    for (const [description, pages] of descMap.entries()) if (pages.length >= 3) addFinding('duplicate_meta_descriptions', 'low', pages[0], `Same description appears on ${pages.length} pages.`, { category: 'seo', pages, current_value: description.slice(0, 180) });

    const internalLinkSources = [];
    for (const page of crawledPages) for (const link of page.links || []) if (link.internal) internalLinkSources.push({ source_url: page.url, target_url: link.href, anchor_text: link.anchor_text || '' });
    const uniqueInternalTargets = [...new Set(internalLinkSources.map((link) => link.target_url))].filter((url) => !assetRe.test(url)).slice(0, 120);
    const checkedStatuses = new Map();
    const checkLink = async (url) => {
      try {
        const res = await fetch(url, { method: 'HEAD', redirect: 'follow', signal: AbortSignal.timeout(LINK_TIMEOUT_MS), headers: { 'User-Agent': USER_AGENT } });
        if (res.status === 405 || res.status === 403) {
          const getRes = await fetch(url, { method: 'GET', redirect: 'follow', signal: AbortSignal.timeout(LINK_TIMEOUT_MS), headers: { 'User-Agent': USER_AGENT, 'Accept': 'text/html,*/*;q=0.8' } });
          return { url, status: getRes.status, ok: getRes.ok };
        }
        return { url, status: res.status, ok: res.ok };
      } catch (error) {
        return { url, status: 0, ok: false, error: error.message || 'Link check failed' };
      }
    };
    for (let index = 0; index < uniqueInternalTargets.length; index += LINK_CHECK_BATCH_SIZE) {
      const results = await Promise.all(uniqueInternalTargets.slice(index, index + LINK_CHECK_BATCH_SIZE).map(checkLink));
      for (const result of results) checkedStatuses.set(result.url, result);
    }

    const brokenLinks = [];
    for (const link of internalLinkSources) {
      const result = checkedStatuses.get(link.target_url);
      if (result && (!result.ok || result.status >= 400)) brokenLinks.push({ ...link, status_code: result.status || 0, error: result.error || '' });
    }
    const dedupedBrokenLinks = brokenLinks.filter((link, index, list) => index === list.findIndex((item) => item.source_url === link.source_url && item.target_url === link.target_url));
    for (const link of dedupedBrokenLinks.slice(0, 30)) addFinding('broken_internal_link', link.status_code === 404 ? 'high' : 'medium', link.source_url, `Internal link returns status ${link.status_code}.`, { category: 'technical', target_url: link.target_url, status_code: link.status_code });

    const groupedMap = new Map();
    const severityRank = { critical: 4, high: 3, medium: 2, low: 1 };
    for (const finding of rawFindings) {
      const existing = groupedMap.get(finding.type) || { type: finding.type, category: finding.category || 'general', severity: finding.severity, pages_count: 0, pages: [], evidence_examples: [] };
      if (!existing.pages.includes(finding.page_url)) existing.pages.push(finding.page_url);
      if (existing.evidence_examples.length < 5) existing.evidence_examples.push(finding.evidence);
      existing.pages_count = existing.pages.length;
      if ((severityRank[finding.severity] || 0) > (severityRank[existing.severity] || 0)) existing.severity = finding.severity;
      groupedMap.set(finding.type, existing);
    }
    const groupedFindings = [...groupedMap.values()].sort((a, b) => (severityRank[b.severity] || 0) - (severityRank[a.severity] || 0) || b.pages_count - a.pages_count);

    let healthScore = 100;
    for (const finding of rawFindings) {
      if (finding.severity === 'critical') healthScore -= 10;
      else if (finding.severity === 'high') healthScore -= 7;
      else if (finding.severity === 'medium') healthScore -= 4;
      else healthScore -= 1.5;
    }
    healthScore = Math.max(0, Math.round(healthScore));

    const pagesWithSchema = analysisPages.filter((page) => page.schema_types.length > 0);
    const siteSummary = {
      total_pages_crawled: crawledPages.length,
      crawl_limit: MAX_PAGES,
      important_pages_detected: importantPages.map((page) => ({ url: page.url, title: page.title, word_count: page.word_count })).slice(0, 20),
      utility_pages_skipped_or_deprioritized: crawledPages.filter((page) => page.is_utility_page).length,
      title_coverage_pct: analysisPages.length ? Math.round((analysisPages.filter((page) => Boolean(page.title)).length / analysisPages.length) * 100) : 0,
      description_coverage_pct: analysisPages.length ? Math.round((analysisPages.filter((page) => Boolean(page.meta_description)).length / analysisPages.length) * 100) : 0,
      pages_with_schema: pagesWithSchema.length,
      schema_types_found: [...new Set(pagesWithSchema.flatMap((page) => page.schema_types))],
      pages_with_faq: analysisPages.filter((page) => page.has_faq).length,
      pages_with_cta: analysisPages.filter((page) => page.has_cta).length,
      pages_with_trust_signals: analysisPages.filter((page) => page.has_trust_signals).length,
      pages_with_forms: analysisPages.filter((page) => page.forms_count > 0).length,
      broken_internal_links: dedupedBrokenLinks.length,
      placeholder_pages: analysisPages.filter((page) => page.placeholder_hits.length > 0).map((page) => ({ url: page.url, hits: page.placeholder_hits })),
      average_word_count: analysisPages.length ? Math.round(analysisPages.reduce((sum, page) => sum + page.word_count, 0) / analysisPages.length) : 0,
      html_only_scan: true,
      javascript_rendering_used: false,
    };

    return Response.json({
      success: true,
      website_url,
      normalized_url: startUrl,
      domain,
      pages_crawled: crawledPages.length,
      pages_found: new Set([...visited, ...queue, ...uniqueInternalTargets]).size,
      health_score: healthScore,
      crawled_pages: crawledPages.map((page) => {
        const { links, ...rest } = page;
        return { ...rest, internal_link_samples: (links || []).filter((link) => link.internal).slice(0, 20), external_link_samples: (links || []).filter((link) => !link.internal).slice(0, 10) };
      }),
      raw_findings: rawFindings,
      grouped_findings: groupedFindings,
      broken_links: dedupedBrokenLinks,
      site_summary: siteSummary,
      crawl_warnings: crawlWarnings,
    });
  } catch (error) {
    return Response.json({ success: false, error: error.message || 'Advanced scan failed' }, { status: 500 });
  }
});