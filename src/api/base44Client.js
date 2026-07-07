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

if (rawBase44?.functions?.invoke) {
  const originalInvoke = rawBase44.functions.invoke.bind(rawBase44.functions);
  rawBase44.functions.invoke = async (...args) => {
    const [functionName, payload, ...rest] = args;
    try {
      return await originalInvoke(functionName, sanitizeFunctionPayload(functionName, payload), ...rest);
    } catch (error) {
      throw decorateFunctionError(error);
    }
  };
}

export const base44 = rawBase44;
