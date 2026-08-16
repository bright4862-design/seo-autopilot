import { createClient } from '@base44/sdk';
import { appParams } from '@/lib/app-params';

const { appId, token, appBaseUrl } = appParams;

const rawBase44 = createClient({
  appId,
  token,
  serverUrl: '',
  requiresAuth: false,
  appBaseUrl
});

const LEGACY_STANDARD_SCAN_FUNCTION = 'runAdvancedScan';
const STANDARD_SCAN_FUNCTION = 'runStandard150Scan';
const STANDARD_SCAN_MODE = 'standard_150';
const RECOMMENDATION_ARRAY_KEYS = ['recommendations', 'cleaned_fixes', 'fixes', 'findings', 'raw_fixes', 'raw_findings', 'grouped_findings', 'issues'];
const PAGE_ARRAY_KEYS = ['pages', 'crawled_pages', 'scanned_pages', 'crawl_pages'];

function parsePossibleJson(value) {
  if (!value || typeof value !== 'string') return null;
  const text = value.trim();
  try { return JSON.parse(text); } catch {}
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    try { return JSON.parse(text.slice(firstBrace, lastBrace + 1)); } catch {}
  }
  return null;
}

function getErrorPayload(error) {
  const candidates = [error?.response?.data, error?.data, error?.body, error?.cause?.response?.data, error?.cause?.data, error?.cause?.body, parsePossibleJson(error?.message)];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === 'object') {
      return { status: error?.response?.status || candidate.status || candidate.status_code || '', statusText: error?.response?.statusText || candidate.statusText || '', ...candidate };
    }
  }
  return { status: error?.response?.status || '', statusText: error?.response?.statusText || '', message: error?.message || '' };
}

function formatFunctionError(error) {
  const payload = getErrorPayload(error);
  const message = payload.error || payload.message || payload.detail || payload.statusText || error?.message || 'Base44 function request failed.';
  const parts = [String(message)];
  if (payload.status) parts.push(`HTTP ${payload.status}`);
  if (payload.version) parts.push(`version: ${payload.version}`);
  if (Array.isArray(payload.received_keys)) parts.push(`received_keys: ${payload.received_keys.join(', ') || 'none'}`);
  if (Array.isArray(payload.resolved_keys)) parts.push(`resolved_keys: ${payload.resolved_keys.join(', ') || 'none'}`);
  return { message: parts.join(' · '), payload };
}

function decorateFunctionError(error) {
  const { message, payload } = formatFunctionError(error);
  if (error instanceof Error) {
    error.message = message;
    error.backend_error = payload;
    return error;
  }
  const wrapped = new Error(message);
  wrapped.backend_error = payload;
  wrapped.cause = error;
  return wrapped;
}

function resolveInvokedFunctionName(functionName) {
  return functionName === LEGACY_STANDARD_SCAN_FUNCTION ? STANDARD_SCAN_FUNCTION : functionName;
}

function sanitizeFunctionPayload(functionName, payload) {
  if (![LEGACY_STANDARD_SCAN_FUNCTION, STANDARD_SCAN_FUNCTION].includes(functionName) || !payload || typeof payload !== 'object') return payload;
  const { max_pages, max_browser_render_attempts, crawl_timeout_ms, enable_screaming_frog_lite, ...cleanPayload } = payload;
  return {
    ...cleanPayload,
    scan_mode: STANDARD_SCAN_MODE,
    canonical_mode: STANDARD_SCAN_MODE,
    respect_robots_txt: true,
    require_python_scanner: true,
    allow_deno_fallback: false,
  };
}

function sanitizeFunctionResponse(functionName, response) {
  if (![LEGACY_STANDARD_SCAN_FUNCTION, STANDARD_SCAN_FUNCTION, 'aiReviewScan'].includes(functionName) || !response || typeof response !== 'object') return response;
  sanitizeResponseContainer(response);
  return response;
}

function sanitizeResponseContainer(value, depth = 0) {
  if (!value || typeof value !== 'object' || depth > 5) return;
  const blockedPageKeys = collectBlockedPageKeys(value);
  const coverage = getCoverageSnapshot(value);
  const keptFixIds = new Set();

  for (const key of RECOMMENDATION_ARRAY_KEYS) {
    if (!Array.isArray(value[key])) continue;
    value[key] = dedupeRecommendations(value[key].map((item) => sanitizeRecommendation(item, blockedPageKeys, coverage)).filter(Boolean));
    for (const item of value[key]) addFixId(keptFixIds, item);
  }

  if (Array.isArray(value.top_recommended_actions)) value.top_recommended_actions = sanitizeActions(value.top_recommended_actions, blockedPageKeys, keptFixIds, coverage);
  if (Array.isArray(value.recommended_actions)) value.recommended_actions = sanitizeActions(value.recommended_actions, blockedPageKeys, keptFixIds, coverage);

  clarifyLowCoverageSummary(value, coverage);

  for (const nestedKey of ['data', 'result', 'body', 'payload']) {
    if (value[nestedKey] && typeof value[nestedKey] === 'object') sanitizeResponseContainer(value[nestedKey], depth + 1);
  }
}

function clarifyLowCoverageSummary(value, coverage = {}) {
  if (!lowEvidenceCoverage(coverage)) return;
  const recommendationCount = RECOMMENDATION_ARRAY_KEYS.reduce((count, key) => count + (Array.isArray(value[key]) ? value[key].length : 0), 0);
  const hasCoverageCard = RECOMMENDATION_ARRAY_KEYS.some((key) => Array.isArray(value[key]) && value[key].some((item) => /limited_crawl_coverage|scan coverage was limited/i.test(`${item?.rule || ''} ${item?.title || ''} ${item?.issue_title || ''}`)));
  if (recommendationCount > 0 && !hasCoverageCard) return;
  const pages = Number(coverage.pages || 0);
  const message = `FixList only checked ${pages} pages in this section, so it did not have enough coverage to make confident SEO recommendations. The pages it did check looked mostly clean. Expand the crawl or confirm the sitemap/internal links for this section, then rerun FixList.`;
  for (const key of ['customer_summary', 'simple_summary', 'health_explanation']) if (typeof value[key] === 'string') value[key] = message;
  if (value.scan_summary && typeof value.scan_summary === 'object') value.scan_summary.plain_english_summary = message;
  if (value.site_summary && typeof value.site_summary === 'object') value.site_summary.plain_english_summary = message;
  if (value.website_health_report && typeof value.website_health_report === 'object') {
    value.website_health_report.overall_explanation = message;
    value.website_health_report.top_concerns = ['Limited crawl coverage.'];
    value.website_health_report.quick_wins = ['Expand the scan coverage before changing page content or trust signals.'];
    value.website_health_report.next_best_step = 'Rerun the scan after confirming sitemap and internal links expose the rest of this section.';
  }
}

function sanitizeRecommendation(item, blockedPageKeys = new Set(), coverage = {}) {
  if (!item || typeof item !== 'object') return item;
  const originalPages = [...firstArray([item.affected_pages, item.pages, item.page_urls]), item.page_url || item.url || ''];
  const affectedPages = cleanPageList(originalPages);
  if (affectedPages.length === 0 && hasArtifactUrl(originalPages)) return null;

  const blockedAccess = isBlockedAccessRecommendation(item);
  let displayPages = affectedPages;
  if (!blockedAccess && blockedPageKeys.size > 0 && affectedPages.length > 0) {
    displayPages = affectedPages.filter((page) => !blockedPageKeys.has(normalizePageKey(page)));
    if (displayPages.length === 0) return null;
  }

  const next = { ...item };
  next.title = cleanFixTitle(next.title || next.issue_title || '');
  next.issue_title = cleanFixTitle(next.issue_title || next.title || '');

  if (!blockedAccess && lowEvidenceCoverage(coverage)) {
    if (isTrustPageRecommendation(next)) return null;
    if (isLowValueMetaRecommendation(next)) return null;
    if (isImageAltIssue(next) && (displayPages.length <= 1 || isOneMissingAlt(next))) return null;
  }

  if (displayPages.length > 0) {
    next.affected_pages = displayPages;
    next.pages = displayPages;
    next.page_urls = displayPages;
    next.page_url = isArtifactUrl(next.page_url) || isBlockedPageKey(next.page_url, blockedPageKeys) ? displayPages[0] : (next.page_url || displayPages[0]);
  }

  if (!blockedAccess && hasBlockedAccessSteps(next)) {
    const steps = fallbackSteps(next);
    next.what_to_do_steps = steps;
    next.what_to_do = steps;
    next.fix_steps = steps;
  }

  if (!blockedAccess && displayPages.length <= 1 && isRepeatedTemplateText(`${next.title} ${next.issue_title} ${next.plain_english_explanation || ''}`)) {
    next.title = singlePageTitle(next);
    next.issue_title = next.title;
    next.plain_english_explanation = cleanSinglePageExplanation(next.plain_english_explanation || next.explanation || 'Review this issue on the affected page.');
  }

  if (isImageAltIssue(next) && isOneMissingAlt(next) && ['critical', 'high'].includes(String(next.priority || '').toLowerCase())) next.priority = 'medium';
  return next;
}

function sanitizeActions(actions, blockedPageKeys = new Set(), keptFixIds = new Set(), coverage = {}) {
  return actions.map((action) => sanitizeAction(action, blockedPageKeys, coverage)).filter((action) => action && (!action.fix_id || keptFixIds.size === 0 || keptFixIds.has(action.fix_id)));
}

function sanitizeAction(action, blockedPageKeys = new Set(), coverage = {}) {
  if (!action || typeof action !== 'object') return action;
  const next = { ...action };
  next.title = cleanFixTitle(next.title || next.issue_title || '');
  next.issue_title = cleanFixTitle(next.issue_title || next.title || '');
  next.affected_pages = cleanPageList(firstArray([next.affected_pages, next.pages, next.page_urls])).filter((page) => !blockedPageKeys.has(normalizePageKey(page)) || isBlockedAccessRecommendation(next));
  if (lowEvidenceCoverage(coverage) && !isBlockedAccessRecommendation(next) && (isTrustPageRecommendation(next) || isLowValueMetaRecommendation(next))) return null;
  return hasArtifactUrl([next.page_url, next.url, ...(next.affected_pages || [])]) && next.affected_pages.length === 0 ? null : next;
}

function collectBlockedPageKeys(value) {
  const blocked = new Set();
  for (const key of PAGE_ARRAY_KEYS) {
    for (const page of Array.isArray(value[key]) ? value[key] : []) {
      if (isBlockedAccessPage(page)) addPageKey(blocked, page?.final_url || page?.url || page?.path || '');
    }
  }
  for (const key of RECOMMENDATION_ARRAY_KEYS) {
    for (const item of Array.isArray(value[key]) ? value[key] : []) {
      if (!isBlockedAccessRecommendation(item)) continue;
      for (const page of cleanPageList([...firstArray([item.affected_pages, item.pages, item.page_urls]), item.page_url || item.url || ''])) addPageKey(blocked, page);
    }
  }
  return blocked;
}

function getCoverageSnapshot(value = {}) {
  const pages = Math.max(numberValue(value.pages_crawled), numberValue(value.pages_scanned), numberValue(value.scan_summary?.pages_crawled), numberValue(value.scan_summary?.pages_scanned), numberValue(value.technical_audit_summary?.pages_crawled), ...PAGE_ARRAY_KEYS.map((key) => Array.isArray(value[key]) ? value[key].length : 0));
  const found = Math.max(numberValue(value.pages_found), numberValue(value.scan_summary?.pages_found), numberValue(value.technical_audit_summary?.pages_found), pages);
  return { pages, found };
}

function lowEvidenceCoverage(coverage = {}) {
  return Number(coverage.pages || 0) > 0 && Number(coverage.pages || 0) < 15;
}

function isBlockedAccessPage(page = {}) {
  const text = `${page?.status_code || ''} ${page?.fetch_error || ''} ${page?.title || ''} ${page?.h1 || ''} ${page?.meta_description || ''}`.toLowerCase();
  return Number(page?.status_code || 0) === 429 || /429|too many requests|rate[- ]?limit|rate limited|verifying your connection|checking your browser/.test(text);
}

function isBlockedAccessRecommendation(item = {}) {
  const text = `${item?.rule || ''} ${item?.category || ''} ${item?.title || ''} ${item?.issue_title || ''} ${item?.current_value || ''} ${item?.plain_english_explanation || ''} ${item?.recommended_value || ''} ${item?.source || ''}`.toLowerCase();
  const status = Number(item?.status_code || item?.current_status_code || item?.http_status || item?.evidence?.status_code || 0);
  return status === 429 || /429|too many requests|rate[- ]?limit|rate limited|blocked_page_429|rate_limited_page|crawler access|scan coverage/.test(text);
}

function cleanPageList(values = []) {
  const seen = new Set();
  const output = [];
  for (const value of values || []) {
    const text = String(value || '').trim();
    if (!text || isArtifactUrl(text)) continue;
    const key = normalizePageKey(text);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(text);
  }
  return output;
}

function dedupeRecommendations(items = []) {
  const seen = new Set();
  const output = [];
  for (const item of items) {
    const key = semanticRecommendationKey(item);
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(item);
  }
  return output;
}

function semanticRecommendationKey(item = {}) {
  const pages = cleanPageList([...firstArray([item.affected_pages, item.pages, item.page_urls]), item.page_url || item.url || '']).map(normalizePageKey).slice(0, 5).join('|');
  const title = cleanFixTitle(item.title || item.issue_title || '').toLowerCase();
  const rule = String(item.rule || '').toLowerCase();
  const category = String(item.category || '').toLowerCase();
  if (isTrustPageRecommendation(item)) return `trust|${rule || category}|${title}`;
  return `${rule}|${category}|${title}|${pages}`;
}

function addPageKey(target, value) { const key = normalizePageKey(value); if (key) target.add(key); }
function addFixId(target, item = {}) { const id = item?.fix_id || item?.id; if (id) target.add(id); }
function isBlockedPageKey(value, blockedPageKeys) { return Boolean(value && blockedPageKeys?.has?.(normalizePageKey(value))); }

function normalizePageKey(value) {
  try {
    const url = new URL(String(value || ''), 'https://fixlist.local');
    return `${url.hostname === 'fixlist.local' ? '' : url.hostname}${url.pathname.replace(/\/$/, '')}${url.search}`.toLowerCase() || '/';
  } catch {
    return String(value || '').replace(/\/$/, '').toLowerCase();
  }
}

function cleanFixTitle(value) {
  return String(value || '')
    .replace(/collection page pages/gi, 'collection pages')
    .replace(/category page pages/gi, 'category pages')
    .replace(/standard page pages/gi, 'standard pages')
    .replace(/product page pages/gi, 'product pages')
    .replace(/contact page pages/gi, 'contact pages')
    .replace(/\s+/g, ' ')
    .trim();
}

function singlePageTitle(item = {}) {
  const category = String(item.category || '').toLowerCase();
  const rule = String(item.rule || '').toLowerCase();
  if (category === 'canonical' || rule.includes('canonical')) return 'Confirm the official version of this page';
  if (category === 'schema' || rule.includes('schema')) return 'Add structured data to this page';
  if (category === 'image_alt_text' || rule.includes('image_alt')) return 'Improve image descriptions on this page';
  if (rule.includes('h1')) return 'Use one clear main heading on this page';
  return cleanFixTitle(item.title || item.issue_title || 'Review this page issue').replace(/^Fix repeated /i, 'Review ');
}

function cleanSinglePageExplanation(value) {
  return String(value || '')
    .replace(/Several similar pages have the same template-level issue\.*/i, 'This issue was found on the affected page. Review the page directly instead of treating it as a sitewide template problem.')
    .replace(/Fix the shared template or pattern instead of creating one task per page\.?/i, 'Review the affected page and confirm whether it is a one-off issue or a reusable template pattern.')
    .trim();
}

function hasBlockedAccessSteps(item = {}) {
  return /429|rate[- ]?limit|verification responses/i.test(firstArray([item.what_to_do_steps, item.what_to_do, item.fix_steps]).join(' '));
}

function fallbackSteps(item = {}) {
  const category = String(item.category || '').toLowerCase();
  const rule = String(item.rule || '').toLowerCase();
  if (category === 'schema' || rule.includes('schema')) return ['Choose the correct schema type for the page.', 'Add it through the CMS, SEO plugin, theme, or developer workflow.', 'Validate structured data after publishing.'];
  if (category === 'canonical' || rule.includes('canonical')) return ['Identify the preferred URL for this page.', 'Add a canonical tag in the HTML head pointing to that URL.', 'Publish the update and run FixList again.'];
  if (isImageAltIssue(item)) return ['Open the affected page or template.', 'Add short, specific alt text to meaningful images.', 'Publish the update and run FixList again.'];
  return ['Review the affected page.', 'Make the recommended update.', 'Publish and run FixList again.'];
}

function isRepeatedTemplateText(value) { return /repeated|template-level|shared template|template issue/i.test(String(value || '')); }
function isTrustPageRecommendation(item = {}) { return /missing_trust_pages|trust pages|public trust|about, contact, privacy|legal, contact/i.test(`${item.rule || ''} ${item.category || ''} ${item.title || ''} ${item.issue_title || ''} ${item.plain_english_explanation || ''}`); }
function isLowValueMetaRecommendation(item = {}) { return /archive|tag page|low value|lower-priority archive/i.test(`${item.page_template_family || ''} ${item.page_type || ''} ${item.business_importance || ''} ${(item.affected_pages || []).join(' ')} ${item.title || ''} ${item.issue_title || ''}`) && /meta|description|title|search appearance/i.test(`${item.category || ''} ${item.rule || ''} ${item.title || ''}`); }
function isImageAltIssue(item = {}) { return /image_alt|image alt|alt text|missing alt|image description/i.test(`${item.rule || ''} ${item.category || ''} ${item.title || ''} ${item.issue_title || ''}`); }
function isOneMissingAlt(item = {}) { return /(^|\D)1\s+images?\s+missing\s+alt/i.test(`${item.current_value || ''} ${item.current || ''} ${item.detected_value || ''}`); }
function hasArtifactUrl(values = []) { return (values || []).some(isArtifactUrl); }

function isArtifactUrl(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  let path = text;
  try { path = new URL(text, 'https://fixlist.local').pathname; } catch {}
  return path.split('/').filter(Boolean).some((segment) => {
    const decoded = safeDecodeURIComponent(segment);
    if (/^(L2|aHR0c|aHR0p|eyJ|PGE|PHN)[A-Za-z0-9+/_-]{10,}={0,2}$/.test(segment)) return true;
    if (/^[A-Za-z0-9+/_-]{24,}={1,2}$/.test(segment)) return true;
    if (/%2f/i.test(segment) && /%3a|%2f/i.test(segment)) return true;
    if (/^https?:/i.test(decoded) || decoded.startsWith('/')) return true;
    return false;
  });
}

function safeDecodeURIComponent(value) { try { return decodeURIComponent(String(value || '')); } catch { return String(value || ''); } }

function firstArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

function numberValue(value) { const number = Number(value || 0); return Number.isFinite(number) ? number : 0; }

if (rawBase44?.functions?.invoke) {
  const originalInvoke = rawBase44.functions.invoke.bind(rawBase44.functions);
  rawBase44.functions.invoke = async (...args) => {
    const [functionName, payload, ...rest] = args;
    const invokedFunctionName = resolveInvokedFunctionName(functionName);
    try {
      const response = await originalInvoke(invokedFunctionName, sanitizeFunctionPayload(functionName, payload), ...rest);
      return sanitizeFunctionResponse(invokedFunctionName, response);
    } catch (error) {
      throw decorateFunctionError(error);
    }
  };
}

export const base44 = rawBase44;
