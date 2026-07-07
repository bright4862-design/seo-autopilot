import { createClient } from '@base44/sdk';
import { appParams } from '@/lib/app-params';

const { appId, token, functionsVersion, appBaseUrl } = appParams;

// Create a client with authentication required
const rawBase44 = createClient({
  appId,
  token,
  functionsVersion,
  serverUrl: '',
  requiresAuth: false,
  appBaseUrl
});

const RECOMMENDATION_ARRAY_KEYS = [
  'recommendations',
  'cleaned_fixes',
  'fixes',
  'findings',
  'raw_fixes',
  'raw_findings',
  'grouped_findings',
  'issues',
];

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
  const candidates = [
    error?.response?.data,
    error?.data,
    error?.body,
    error?.cause?.response?.data,
    error?.cause?.data,
    error?.cause?.body,
    parsePossibleJson(error?.message),
  ];

  for (const candidate of candidates) {
    if (candidate && typeof candidate === 'object') {
      return {
        status: error?.response?.status || candidate.status || candidate.status_code || '',
        statusText: error?.response?.statusText || candidate.statusText || '',
        ...candidate,
      };
    }
  }

  return {
    status: error?.response?.status || '',
    statusText: error?.response?.statusText || '',
    message: error?.message || '',
  };
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

function sanitizeFunctionPayload(functionName, payload) {
  if (functionName !== 'runAdvancedScan' || !payload || typeof payload !== 'object') return payload;
  const { max_pages, max_browser_render_attempts, crawl_timeout_ms, ...cleanPayload } = payload;
  return cleanPayload;
}

function sanitizeFunctionResponse(functionName, response) {
  if (!['runAdvancedScan', 'aiReviewScan'].includes(functionName) || !response || typeof response !== 'object') return response;
  sanitizeResponseContainer(response);
  return response;
}

function sanitizeResponseContainer(value, depth = 0) {
  if (!value || typeof value !== 'object' || depth > 5) return;

  for (const key of RECOMMENDATION_ARRAY_KEYS) {
    if (Array.isArray(value[key])) value[key] = sanitizeRecommendationArray(value[key]);
  }

  if (Array.isArray(value.top_recommended_actions)) value.top_recommended_actions = value.top_recommended_actions.map(sanitizeAction).filter(Boolean);
  if (Array.isArray(value.recommended_actions)) value.recommended_actions = value.recommended_actions.map(sanitizeAction).filter(Boolean);

  for (const nestedKey of ['data', 'result', 'body', 'payload']) {
    if (value[nestedKey] && typeof value[nestedKey] === 'object') sanitizeResponseContainer(value[nestedKey], depth + 1);
  }
}

function sanitizeRecommendationArray(items) {
  return items.map(sanitizeRecommendation).filter(Boolean);
}

function sanitizeRecommendation(item) {
  if (!item || typeof item !== 'object') return item;
  const affectedPages = cleanPageList([...(firstArray([item.affected_pages, item.pages, item.page_urls]) || []), item.page_url || item.url || '']);
  const artifactOnly = affectedPages.length === 0 && hasArtifactUrl([item.page_url, item.url, ...(firstArray([item.affected_pages, item.pages, item.page_urls]) || [])]);
  if (artifactOnly) return null;

  const next = { ...item };
  next.title = cleanFixTitle(next.title || next.issue_title || '');
  next.issue_title = cleanFixTitle(next.issue_title || next.title || '');

  if (affectedPages.length > 0) {
    next.affected_pages = affectedPages;
    next.pages = affectedPages;
    next.page_urls = affectedPages;
    next.page_url = isArtifactUrl(next.page_url) ? affectedPages[0] : (next.page_url || affectedPages[0]);
  }

  if (affectedPages.length <= 1 && isRepeatedTemplateText(`${next.title} ${next.issue_title} ${next.plain_english_explanation || ''}`)) {
    next.title = singlePageTitle(next);
    next.issue_title = next.title;
    next.plain_english_explanation = cleanSinglePageExplanation(next.plain_english_explanation || next.explanation || 'Review this issue on the affected page.');
  }

  if (isImageAltIssue(next) && isOneMissingAlt(next) && ['critical', 'high'].includes(String(next.priority || '').toLowerCase())) {
    next.priority = 'medium';
  }

  return next;
}

function sanitizeAction(action) {
  if (!action || typeof action !== 'object') return action;
  const next = { ...action };
  next.title = cleanFixTitle(next.title || next.issue_title || '');
  next.issue_title = cleanFixTitle(next.issue_title || next.title || '');
  next.affected_pages = cleanPageList(firstArray([next.affected_pages, next.pages, next.page_urls]));
  return hasArtifactUrl([next.page_url, next.url, ...(next.affected_pages || [])]) && next.affected_pages.length === 0 ? null : next;
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

function isRepeatedTemplateText(value) {
  return /repeated|template-level|shared template|template issue/i.test(String(value || ''));
}

function isImageAltIssue(item = {}) {
  return /image_alt|image alt|alt text|image description/i.test(`${item.rule || ''} ${item.category || ''} ${item.title || ''} ${item.issue_title || ''}`);
}

function isOneMissingAlt(item = {}) {
  return /(^|\D)1\s+images?\s+missing\s+alt/i.test(`${item.current_value || ''} ${item.current || ''} ${item.detected_value || ''}`);
}

function hasArtifactUrl(values = []) {
  return (values || []).some(isArtifactUrl);
}

function isArtifactUrl(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  let path = text;
  try { path = new URL(text, 'https://fixlist.local').pathname; } catch {}
  return /(^|\/)(aHR0cHM6|aHR0cDov|L2[a-zA-Z0-9+/=_-]{12,}|[A-Za-z0-9+/=_-]{36,}={0,2})(\/|$)/.test(path)
    || /\/[A-Za-z0-9+/_=-]{32,}={0,2}(\/|$)/.test(path)
    || /\/L2[A-Za-z0-9+/_=-]{10,}={0,2}(\/|$)/.test(path);
}

function firstArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

if (rawBase44?.functions?.invoke) {
  const originalInvoke = rawBase44.functions.invoke.bind(rawBase44.functions);
  rawBase44.functions.invoke = async (...args) => {
    const [functionName, payload, ...rest] = args;
    try {
      const response = await originalInvoke(functionName, sanitizeFunctionPayload(functionName, payload), ...rest);
      return sanitizeFunctionResponse(functionName, response);
    } catch (error) {
      throw decorateFunctionError(error);
    }
  };
}

export const base44 = rawBase44;
