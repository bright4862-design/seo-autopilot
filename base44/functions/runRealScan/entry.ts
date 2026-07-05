import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

const UTILITY_WORDS = [
  'cart', 'checkout', 'login', 'signin', 'signup', 'register', 'account', 'search',
  'privacy', 'terms', 'thank-you', 'payment', 'admin', 'wp-admin', 'reset', 'forgot',
  'cookie', 'legal', 'disclaimer', 'tag', 'category', 'author'
];

const PLACEHOLDER_PATTERNS = [
  [/\bgvar\+?\b/i, 'gvar'],
  [/\bundefined\b/i, 'undefined'],
  [/\bnull\b/i, 'null'],
  [/\bNaN\b/i, 'NaN'],
  [/\[object Object\]/i, '[object Object]'],
  [/\{\{[^}]+\}\}/i, '{{ }}'],
  [/lorem ipsum/i, 'lorem ipsum'],
  [/\bplaceholder\b/i, 'placeholder'],
];

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, business_name, business_type, city, project_id, crawl_job_id } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    let baseUrl = website_url;
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
    baseUrl = canonicalizeUrl(baseUrl);
    const urlObj = new URL(baseUrl);
    const domain = urlObj.hostname.replace(/^www\./, '');
    const startPath = getPath(baseUrl);

    const fetchPage = async (url) => {
      try {
        const res = await fetch(url, {
          redirect: 'follow',
          signal: AbortSignal.timeout(12000),
          headers: { 'User-Agent': 'SEO-Autopilot/1.0' }
        });
        const contentType = res.headers.get('content-type') || '';
        const html = contentType.includes('text/html') ? await res.text() : '';
        return { url: canonicalizeUrl(res.url || url), originalUrl: url, status: res.status, html, ok: res.ok };
      } catch (e) {
        return { url, originalUrl: url, status: 0, html: '', ok: false, error: e.message };
      }
    };

    const firstMatch = (html, re) => {
      const m = html.match(re);
      return m ? cleanText(m[1] || '') : '';
    };

    const extractPage = (url, html, status) => {
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
      const pageText = cleanText(
        html
          .replace(/<script[\s\S]*?<\/script>/gi, ' ')
          .replace(/<style[\s\S]*?<\/style>/gi, ' ')
          .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
          .replace(/<!--([\s\S]*?)-->/g, ' ')
          .replace(/<[^>]+>/g, ' ')
      );
      const wordCount = pageText.split(/\s+/).filter(Boolean).length;
      const links = [];
      const linkRe = /<a[^>]+href=["']([^"']+)["']/gi;
      let lm;
      while ((lm = linkRe.exec(html)) !== null) links.push(lm[1]);

      const headings = extractHeadings(html);
      const faqQuestions = extractQuestions(pageText);
      const schemaTypes = detectSchemaTypes(html);
      const images = detectImages(html);
      const placeholderHits = PLACEHOLDER_PATTERNS
        .filter(([re]) => re.test(pageText))
        .map(([, label]) => label);

      return {
        url,
        status,
        title,
        metaDesc,
        h1,
        h2s: headings.h2s,
        h3s: headings.h3s,
        canonical,
        wordCount,
        links,
        text: pageText,
        faq_questions: faqQuestions,
        has_faq: faqQuestions.length >= 2 || /frequently asked questions|faq/i.test(pageText),
        has_schema: schemaTypes.length > 0,
        schema_types: schemaTypes,
        has_phone: /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.test(pageText),
        has_email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(pageText),
        cta_phrases: detectCtas(pageText),
        trust_signals: detectTrustSignals(pageText),
        image_count: images.length,
        images_missing_alt_count: images.filter((image) => !image.has_alt).length,
        placeholder_hits: placeholderHits,
      };
    };

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
          if (canonicalizeUrl(r.originalUrl) === baseUrl) {
            return Response.json({ error: "We couldn't reach that website. Please check the URL and try again." }, { status: 400 });
          }
          crawledPages.push({
            url: r.url,
            status: r.status || 0,
            title: '', metaDesc: '', h1: '', h2s: [], h3s: [], canonical: '', wordCount: 0, links: [], text: '',
            faq_questions: [], has_faq: false, has_schema: false, schema_types: [], has_phone: false, has_email: false,
            cta_phrases: [], trust_signals: [], image_count: 0, images_missing_alt_count: 0, placeholder_hits: []
          });
          continue;
        }
        const page = extractPage(r.url, r.html, r.status);
        crawledPages.push(page);
        for (const href of page.links) {
          try {
            const abs = canonicalizeUrl(new URL(href, baseUrl).href.split('#')[0]);
            const path = getPath(abs);
            if (
              new URL(abs).hostname.replace(/^www\./, '') === domain &&
              !visited.has(abs) &&
              !toVisit.includes(abs) &&
              !isAssetUrl(abs) &&
              !(isUtilityPage(path) && abs !== baseUrl)
            ) {
              toVisit.push(abs);
            }
          } catch {}
        }
      }
    }

    const generateBasicTitle = (page) => {
      const path = getPath(page?.url || baseUrl);
      if (path === '/') {
        return clamp([business_name, business_type, city].filter(Boolean).join(' | ') || `${business_name || domain} | Official Website`, 65);
      }
      const pageName = path.split('/').filter(Boolean).pop()?.replace(/[-_]/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()) || 'Page';
      return clamp([pageName, business_name, city].filter(Boolean).join(' | '), 65);
    };

    const describePage = (p, pageUrl) => {
      const name = business_name || domain;
      let description;
      if (pageUrl === '/') {
        const type = (business_type || 'professional services').toLowerCase();
        description = city
          ? `${name} provides ${type} in ${city}. Learn about services, options, and next steps, then contact the team today.`
          : `${name} provides ${type}. Learn about services, options, and next steps, then contact the team today.`;
      } else {
        const seg = (pageUrl.split('/').filter(Boolean).pop() || '').replace(/[-_]/g, ' ');
        const topic = ((p.h1 || p.title || seg).split('|')[0].trim() || 'this service').toLowerCase();
        description = `Learn about ${topic} from ${name}. See helpful details, benefits, common questions, and the best next step.`;
      }
      return clamp(description, 160);
    };

    const issues = [];
    const preferredPageItems = [];
    const placeholderPages = [];
    const importantPages = crawledPages.filter((p) => isImportantPage(getPath(p.url), p.title, p.h1) && !isUtilityPage(getPath(p.url)));

    for (const p of crawledPages) {
      const pageUrl = getPath(p.url);
      const isUtility = isUtilityPage(pageUrl) && pageUrl !== startPath;
      const important = isImportantPage(pageUrl, p.title, p.h1) && !isUtility;
      const serviceLike = important && /(^\/$)|(service|services|product|products|loan|loans|program|programs|pricing|packages|location|locations|area|areas|repair|installation|treatment|treatments)/i.test(`${pageUrl} ${p.title} ${p.h1}`);

      if (p.status === 404 || p.status === 0) {
        issues.push({
          page_url: pageUrl, category: '404_error', customer_category: 'Broken page',
          issue_title: 'This page may not be loading correctly',
          plain_english_explanation: 'Visitors may be reaching a page that does not work.',
          why_it_matters: 'Broken pages can hurt trust and make it harder for customers to find the right information.',
          ai_recommendation: 'Send this page to the closest working page or restore the missing page.',
          current_value: `Page status: ${p.status || 'not reachable'}`, recommended_value: 'Send visitors to the closest working page',
          priority: 'high', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      if (!isUtility && !p.title) {
        const title = generateBasicTitle(p);
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'Add a clear search title',
          plain_english_explanation: 'This page does not have a clear title for search results.',
          why_it_matters: 'A clear search title helps people understand what the page is about before they click.',
          ai_recommendation: title, current_value: '(empty)', recommended_value: title,
          priority: 'high', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      } else if (!isUtility && p.title && (p.title.length < 20 || p.title.length > 70)) {
        const title = generateBasicTitle(p);
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'Improve this page’s search title',
          plain_english_explanation: 'The current page title may be too short, too long, or unclear.',
          why_it_matters: 'A stronger title can help customers understand the page before they click.',
          ai_recommendation: title, current_value: p.title, recommended_value: title,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!isUtility && important && !p.metaDesc) {
        const desc = describePage(p, pageUrl);
        issues.push({
          page_url: pageUrl, category: 'meta_description', customer_category: 'Search description',
          issue_title: 'Add a helpful search description',
          plain_english_explanation: 'This important page does not have a clear description for search results.',
          why_it_matters: 'A useful description can help more people understand what your page offers.',
          ai_recommendation: desc, current_value: '(empty)', recommended_value: desc,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      } else if (!isUtility && important && p.metaDesc && (p.metaDesc.length < 70 || p.metaDesc.length > 170)) {
        const desc = describePage(p, pageUrl);
        issues.push({
          page_url: pageUrl, category: 'meta_description', customer_category: 'Search description',
          issue_title: 'Improve this page’s search description',
          plain_english_explanation: 'This page has a search description, but it may not be the best length or clarity.',
          why_it_matters: 'A clearer description may help more people choose your page in search results.',
          ai_recommendation: desc, current_value: p.metaDesc, recommended_value: desc,
          priority: 'low', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (important && (!p.h1 || p.h1.length < 8 || p.h1.length > 90)) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Page heading',
          issue_title: 'Improve the main page heading',
          plain_english_explanation: 'This important page may need a clearer main heading.',
          why_it_matters: 'A clear heading helps visitors quickly understand the page.',
          ai_recommendation: 'Add a short, specific heading that explains the service, offer, or next step.',
          current_value: p.h1 || '(empty)', recommended_value: 'A clear heading that describes this page',
          priority: 'medium', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      if (!isUtility && important && !p.canonical && !preferredPageItems.includes(pageUrl)) {
        preferredPageItems.push(pageUrl);
      }

      if (important && p.status === 200 && p.wordCount < 250) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Page content',
          issue_title: 'This important page may need more helpful content',
          plain_english_explanation: 'This page looks important, but it may not give customers enough information to understand the service, location, benefits, or next step.',
          why_it_matters: 'Helpful pages usually explain the offer, answer common questions, and guide visitors toward action.',
          ai_recommendation: 'Add helpful details such as services offered, areas served, common questions, proof points, and a clear next step.',
          current_value: `${p.wordCount} words`, recommended_value: 'More helpful service details, questions, proof, and next steps',
          priority: 'medium', difficulty: 'developer', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }

      if (serviceLike && !p.has_faq) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Customer questions',
          issue_title: 'Add answers to common customer questions',
          plain_english_explanation: 'This important service page does not appear to answer common customer questions.',
          why_it_matters: 'Question-and-answer sections can help visitors make decisions with more confidence.',
          ai_recommendation: 'Add 4–6 common questions customers ask before contacting you.',
          current_value: 'No clear question-and-answer section found', recommended_value: 'Helpful customer questions and answers',
          priority: 'low', difficulty: 'moderate', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }

      if (serviceLike && p.cta_phrases.length === 0) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Next step',
          issue_title: 'Add a clearer next step',
          plain_english_explanation: 'This important service page may not make the next step obvious.',
          why_it_matters: 'Visitors are more likely to contact you when the next step is clear.',
          ai_recommendation: 'Add a clear button or section such as “Get started,” “Request a quote,” “Book a call,” or “Apply now.”',
          current_value: 'No strong next-step phrase found', recommended_value: 'A clear button or next-step section',
          priority: 'medium', difficulty: 'moderate', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }

      if (serviceLike && p.trust_signals.length === 0) {
        issues.push({
          page_url: pageUrl, category: 'schema', customer_category: 'Trust signals',
          issue_title: 'Add more trust signals',
          plain_english_explanation: 'This important service page may not show enough proof that visitors can trust the business.',
          why_it_matters: 'Reviews, testimonials, project examples, certifications, or proof numbers can help visitors feel more confident.',
          ai_recommendation: 'Add reviews, testimonials, proof numbers, project examples, guarantees, or certifications where appropriate.',
          current_value: 'No clear trust signals found', recommended_value: 'Visible proof points, reviews, examples, or credentials',
          priority: 'medium', difficulty: 'moderate', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }

      if (important && p.image_count >= 5 && p.images_missing_alt_count / p.image_count >= 0.5) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Image descriptions',
          issue_title: 'Add helpful descriptions to important images',
          plain_english_explanation: 'Many images on this page may not have helpful descriptions.',
          why_it_matters: 'Image descriptions can help accessibility and give search engines more context about the page.',
          ai_recommendation: 'Add short, useful descriptions to important service, project, product, or team images.',
          current_value: `${p.images_missing_alt_count} of ${p.image_count} images may need descriptions`, recommended_value: 'Helpful descriptions on important images',
          priority: 'low', difficulty: 'moderate', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }

      if (important && p.placeholder_hits.length > 0 && !placeholderPages.some((x) => x.page === pageUrl)) {
        placeholderPages.push({ page: pageUrl, hits: p.placeholder_hits });
      }
    }

    if (placeholderPages.length > 0) {
      issues.push({
        page_url: placeholderPages[0].page, category: 'web_dev', customer_category: 'Website setup',
        issue_title: 'Important content may not be showing correctly',
        plain_english_explanation: 'We found placeholder-like text where final business information may belong.',
        why_it_matters: 'Important proof points, service details, and trust signals should be easy for visitors and search engines to understand.',
        ai_recommendation: 'Ask a developer to make sure the final text and numbers appear directly in the page content. Affected pages: ' + placeholderPages.map((p) => `${p.page} (${p.hits.join(', ')})`).join(' · '),
        current_value: 'Affected pages: ' + placeholderPages.map((p) => `${p.page} (${p.hits.join(', ')})`).join(' · '),
        recommended_value: 'Final text and numbers visible directly in the page content',
        priority: 'high', difficulty: 'developer', group: 'needs_developer',
        can_auto_fix: false, requires_approval: false, requires_developer: true,
      });
    }

    if (preferredPageItems.length > 0) {
      issues.push({
        page_url: preferredPageItems[0], category: 'canonical', customer_category: 'Website Improvement',
        issue_title: 'Review preferred-page settings across important pages',
        plain_english_explanation: 'Several important pages may not clearly tell search engines which version of the page is preferred. This is usually a website setup item, not an emergency.',
        why_it_matters: 'When search engines know the main version of each page, they can show the right page in results.',
        ai_recommendation: 'Ask your developer or SEO cleanup provider to review preferred-page settings for these pages: ' + preferredPageItems.join(' · '),
        current_value: 'Affected pages: ' + preferredPageItems.join(' · '),
        recommended_value: 'Preferred-page settings reviewed for each affected page',
        priority: 'medium', difficulty: 'developer', group: 'needs_developer',
        can_auto_fix: false, requires_approval: false, requires_developer: true,
      });
    }

    const titleGroups = new Map();
    for (const p of importantPages) {
      const title = cleanText(p.title).toLowerCase();
      if (!title) continue;
      if (!titleGroups.has(title)) titleGroups.set(title, []);
      titleGroups.get(title).push(p);
    }
    for (const [title, pages] of titleGroups.entries()) {
      if (pages.length > 1) {
        issues.push({
          page_url: getPath(pages[0].url), category: 'duplicate_content', customer_category: 'Search title',
          issue_title: 'Several important pages use the same search title',
          plain_english_explanation: 'Multiple important pages appear to use the same title in search results.',
          why_it_matters: 'Unique titles help people and search engines understand what each page is about.',
          ai_recommendation: 'Create a unique search title for each affected page: ' + pages.map((p) => getPath(p.url)).join(' · '),
          current_value: title, recommended_value: 'Unique search titles for each important page',
          priority: 'medium', difficulty: 'easy', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }
    }

    const seen = new Set();
    const deduped = issues.filter((issue) => {
      const key = `${issue.page_url}|${issue.category}|${issue.issue_title}`.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    const fixes = deduped.map((issue) => {
      const status = issue.group === 'we_can_fix' ? 'auto_fixed' : issue.group === 'needs_developer' ? 'needs_developer' : 'needs_approval';
      return { ...issue, confidence_score: 90, status };
    });

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
      crawled_pages: crawledPages.map((p) => ({
        url: p.url,
        status_code: p.status || 0,
        title: p.title || '',
        meta_description: p.metaDesc || '',
        h1: p.h1 || '',
        canonical_url: p.canonical || '',
        word_count: p.wordCount || 0,
        indexable: true,
        in_sitemap: false,
        rendered_title: '',
        rendered_meta_description: '',
        rendered_canonical: '',
        js_difference_detected: false
      })),
      fixes,
      summary: {
        we_can_fix: fixes.filter((f) => f.status === 'auto_fixed').length,
        needs_approval: fixes.filter((f) => f.status === 'needs_approval').length,
        needs_developer: fixes.filter((f) => f.requires_developer === true).length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});

function clamp(str, max) {
  const value = cleanText(str);
  if (value.length <= max) return value;
  return value.slice(0, Math.max(0, max - 1)).trimEnd() + '…';
}

function cleanText(str) {
  return String(str || '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function getPath(url) {
  try {
    return new URL(url).pathname || '/';
  } catch {
    return url || '/';
  }
}

function isUtilityPage(path) {
  const cleaned = String(path || '').toLowerCase();
  return UTILITY_WORDS.some((word) => cleaned.includes(word));
}

function isImportantPage(path, title, h1) {
  const combined = `${path || ''} ${title || ''} ${h1 || ''}`;
  return /(^\/$)|(home|service|services|product|products|loan|loans|program|programs|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve|repair|installation|treatment|treatments)/i.test(combined);
}

function extractHeadings(html) {
  return {
    h2s: matchAllClean(html, /<h2[^>]*>([\s\S]*?)<\/h2>/gi).slice(0, 20),
    h3s: matchAllClean(html, /<h3[^>]*>([\s\S]*?)<\/h3>/gi).slice(0, 30),
  };
}

function extractQuestions(text) {
  return cleanText(text)
    .split(/(?<=[?.!])\s+/)
    .map((sentence) => cleanText(sentence))
    .filter((sentence) => sentence.endsWith('?'))
    .slice(0, 20);
}

function detectTrustSignals(text) {
  const lower = String(text || '').toLowerCase();
  const signals = ['reviews', 'reviewed', 'testimonials', 'case study', 'case studies', 'years in business', 'licensed', 'certified', 'award', 'guarantee', 'trusted', 'rated', 'stars', 'projects', 'clients', 'customers', 'funded', 'insured', 'accredited'];
  return signals.filter((signal) => lower.includes(signal));
}

function detectCtas(text) {
  const lower = String(text || '').toLowerCase();
  const ctas = ['contact us', 'call now', 'get started', 'request a quote', 'book now', 'schedule', 'apply now', 'start application', 'learn more', 'get a free', 'free consultation', 'talk to', 'speak with', 'request funding', 'get approved'];
  return ctas.filter((cta) => lower.includes(cta));
}

function detectSchemaTypes(html) {
  const types = [];
  const blocks = matchAllRaw(html, /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi);
  for (const block of blocks) {
    const matches = block.match(/"@type"\s*:\s*"([^"]+)"/gi) || [];
    for (const item of matches) {
      const type = item.replace(/"@type"\s*:\s*"/i, '').replace(/"/g, '');
      if (type) types.push(type);
    }
  }
  if (/schema\.org\/LocalBusiness/i.test(html)) types.push('LocalBusiness');
  if (/schema\.org\/FAQPage/i.test(html)) types.push('FAQPage');
  if (/schema\.org\/Organization/i.test(html)) types.push('Organization');
  return Array.from(new Set(types)).slice(0, 20);
}

function detectImages(html) {
  const images = [];
  const re = /<img[^>]*>/gi;
  let match;
  while ((match = re.exec(html))) {
    const tag = match[0];
    const alt = tag.match(/alt=["']([^"']*)["']/i);
    images.push({ has_alt: Boolean(cleanText(alt?.[1] || '')) });
  }
  return images;
}

function matchAllClean(input, regex) {
  const output = [];
  let match;
  while ((match = regex.exec(input || ''))) output.push(cleanText(match[1] || ''));
  return output.filter(Boolean);
}

function matchAllRaw(input, regex) {
  const output = [];
  let match;
  while ((match = regex.exec(input || ''))) output.push(match[1] || '');
  return output.filter(Boolean);
}

function canonicalizeUrl(input) {
  try {
    const url = new URL(input);
    url.hash = '';
    if (url.pathname !== '/' && url.pathname.endsWith('/')) url.pathname = url.pathname.slice(0, -1);
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'msclkid'].forEach((param) => url.searchParams.delete(param));
    return url.toString();
  } catch {
    return input;
  }
}

function isAssetUrl(input) {
  return /\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|mp4|mp3|avi|mov|css|js|ico|woff|woff2|ttf)$/i.test(input);
}