const MAX_REDIRECT_EVIDENCE_SAMPLES = 20;
const MAX_REDIRECT_HOPS = 12;
const MAX_REPAIR_OBSERVATION_SAMPLES = 20;
const SENSITIVE_QUERY_KEYS = new Set([
  "access_token", "api_key", "apikey", "auth", "authorization", "bearer",
  "cookie", "jwt", "key", "password", "passwd", "refresh_token", "secret",
  "session", "session_id", "sessionid", "sig", "signature", "token",
]);

function hasOwn(value, key) {
  return Boolean(value && Object.prototype.hasOwnProperty.call(value, key));
}

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function text(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function nullableText(value, limit) {
  if (value === null) return null;
  if (typeof value !== "string") return null;
  return value.trim().slice(0, limit);
}

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nonNegativeInteger(value) {
  const parsed = finiteNumber(value);
  return parsed === null ? null : Math.max(0, Math.trunc(parsed));
}

function httpStatus(value) {
  const parsed = nonNegativeInteger(value);
  return parsed !== null && parsed >= 100 && parsed <= 599 ? parsed : null;
}

function redactSensitiveText(value, limit) {
  const raw = nullableText(value, limit);
  if (raw === null) return null;
  return raw
    .replace(/\b(Bearer)\s+[A-Za-z0-9._~+\/-]+=*/gi, "$1 [redacted]")
    .replace(/\b(authorization|access[_-]?token|refresh[_-]?token|api[_-]?key|password|passwd|secret|session(?:_id)?|jwt|signature|sig|token)=([^\s&;]+)/gi, "$1=[redacted]");
}

export function sanitizeEvidenceUrl(value) {
  const raw = text(value, 2_000);
  if (!raw) return "";
  const withoutCredentials = raw.replace(/^(https?:\/\/)[^/@\s]+@/i, "$1");
  const hashIndex = withoutCredentials.indexOf("#");
  const beforeHash = hashIndex >= 0 ? withoutCredentials.slice(0, hashIndex) : withoutCredentials;
  const hash = hashIndex >= 0 ? withoutCredentials.slice(hashIndex) : "";
  const queryIndex = beforeHash.indexOf("?");
  if (queryIndex < 0) return withoutCredentials.slice(0, 2_000);
  const base = beforeHash.slice(0, queryIndex);
  const query = beforeHash.slice(queryIndex + 1).split("&").map((part) => {
    const equals = part.indexOf("=");
    const rawKey = equals >= 0 ? part.slice(0, equals) : part;
    let decodedKey = rawKey;
    try { decodedKey = decodeURIComponent(rawKey.replace(/\+/g, " ")); } catch {}
    if (!SENSITIVE_QUERY_KEYS.has(String(decodedKey || "").trim().toLowerCase())) return part;
    return equals >= 0 ? `${rawKey}=[redacted]` : rawKey;
  }).join("&");
  return `${base}?${query}${hash}`.slice(0, 2_000);
}

function sanitizeRedirectHop(value) {
  const source = plainObject(value);
  const result = {};
  if (hasOwn(source, "url")) result.url = sanitizeEvidenceUrl(source.url);
  if (hasOwn(source, "status")) result.status = httpStatus(source.status);
  if (hasOwn(source, "location")) result.location = sanitizeEvidenceUrl(source.location);
  return result;
}

export function sanitizeRedirectEvidence(value) {
  const source = plainObject(value);
  if (Object.keys(source).length === 0) return {};
  const result = {};
  if (hasOwn(source, "requested_url")) result.requested_url = sanitizeEvidenceUrl(source.requested_url);
  if (hasOwn(source, "redirect_chain")) {
    result.redirect_chain = (Array.isArray(source.redirect_chain) ? source.redirect_chain : [])
      .slice(0, MAX_REDIRECT_HOPS)
      .map(sanitizeRedirectHop);
  }
  if (hasOwn(source, "final_url")) result.final_url = sanitizeEvidenceUrl(source.final_url);
  if (hasOwn(source, "final_status")) result.final_status = httpStatus(source.final_status);
  if (hasOwn(source, "final_content_type")) result.final_content_type = nullableText(source.final_content_type, 200);
  if (hasOwn(source, "body_bytes")) result.body_bytes = nonNegativeInteger(source.body_bytes);
  if (hasOwn(source, "html_parse_ok")) result.html_parse_ok = typeof source.html_parse_ok === "boolean" ? source.html_parse_ok : null;
  if (hasOwn(source, "fetch_error")) result.fetch_error = redactSensitiveText(source.fetch_error, 500);
  if (hasOwn(source, "robots_status")) result.robots_status = nullableText(source.robots_status, 160);
  if (hasOwn(source, "canonical_url")) result.canonical_url = sanitizeEvidenceUrl(source.canonical_url);
  if (hasOwn(source, "noindex")) result.noindex = typeof source.noindex === "boolean" ? source.noindex : null;
  if (hasOwn(source, "classification")) result.classification = nullableText(source.classification, 120);
  return result;
}

function sanitizeObservation(value) {
  const source = plainObject(value);
  const result = {};
  for (const key of ["page_url", "canonical_url", "image_url", "source_page", "current_href", "observed_target", "sitemap_file", "original_loc"]) {
    if (hasOwn(source, key)) result[key] = sanitizeEvidenceUrl(source[key]);
  }
  for (const [key, limit] of Object.entries({
    title: 500,
    h1: 500,
    excerpt: 500,
    alt_text: 500,
    meta_description: 1_000,
    meta_description_state: 80,
    decorative_state: 80,
    issue_type: 100,
    intended_market: 160,
    alt_state: 80,
    link_text: 500,
  })) {
    if (hasOwn(source, key)) result[key] = nullableText(source[key], limit);
  }
  if (hasOwn(source, "h1_count")) result.h1_count = nonNegativeInteger(source.h1_count);
  if (hasOwn(source, "status")) result.status = httpStatus(source.status);
  return result;
}

export function sanitizeReportRawFindingEvidence(value) {
  const raw = plainObject(value);
  const result = {};
  if (hasOwn(raw, "redirect_outcome")) result.redirect_outcome = text(raw.redirect_outcome, 120);
  if (hasOwn(raw, "redirect_fetch_evidence")) {
    result.redirect_fetch_evidence = sanitizeRedirectEvidence(raw.redirect_fetch_evidence);
  }
  if (hasOwn(raw, "redirect_fetch_evidence_samples")) {
    result.redirect_fetch_evidence_samples = (Array.isArray(raw.redirect_fetch_evidence_samples) ? raw.redirect_fetch_evidence_samples : [])
      .slice(0, MAX_REDIRECT_EVIDENCE_SAMPLES)
      .map(sanitizeRedirectEvidence);
  }
  if (hasOwn(raw, "redirect_observed_count")) result.redirect_observed_count = nonNegativeInteger(raw.redirect_observed_count);
  if (hasOwn(raw, "redirect_evidence_truncated")) result.redirect_evidence_truncated = raw.redirect_evidence_truncated === true;
  if (hasOwn(raw, "non_scoring")) result.non_scoring = raw.non_scoring === true;
  if (hasOwn(raw, "score_impact")) result.score_impact = finiteNumber(raw.score_impact);
  if (hasOwn(raw, "repair_observation_samples")) {
    result.repair_observation_samples = (Array.isArray(raw.repair_observation_samples) ? raw.repair_observation_samples : [])
      .slice(0, MAX_REPAIR_OBSERVATION_SAMPLES)
      .map(sanitizeObservation);
  }
  if (hasOwn(raw, "repair_observation_count")) result.repair_observation_count = nonNegativeInteger(raw.repair_observation_count);
  return result;
}

export function sanitizeScanCoverage(value) {
  const source = plainObject(value);
  const result = {};
  for (const key of [
    "urls_attempted",
    "usable_html_pages",
    "verified_http_failures",
    "access_unverified_pages",
    "non_html_resources",
    "unique_retained_destinations",
  ]) {
    if (!hasOwn(source, key)) continue;
    const parsed = nonNegativeInteger(source[key]);
    if (parsed !== null) result[key] = parsed;
  }
  return result;
}
