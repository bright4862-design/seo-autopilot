export const CUSTOMER_LOCAL_STORAGE_KEYS = Object.freeze([
  "active_project_id",
  "seo_autopilot:last_scan",
  "seo_autopilot:scan_history",
  "SEO_AUTOPILOT_LAST_SCAN",
  "SEO_AUTOPILOT_SCAN_HISTORY",
  "seo_autopilot:active_scan_url",
  "seo_autopilot:active_scan_started_at",
  "seo_autopilot:active_scan_id",
  "seo_autopilot:scan_debug",
  "seo_autopilot:done_fixes",
  "seo_autopilot:gsc_connection",
  "seo_autopilot:gsc_oauth_state",
  "seo_autopilot:restore_pointer",
  "seo_autopilot:grok_conversation",
  "seo_autopilot:pending_request",
]);

export const CUSTOMER_LOCAL_STORAGE_PREFIXES = Object.freeze([
  "seo_autopilot:scan:",
  "seo_autopilot:customer:",
]);

export const CUSTOMER_SESSION_STORAGE_KEYS = Object.freeze([
  "seo_autopilot_pending_analytics",
  "seo_autopilot:active_request",
  "seo_autopilot:pending_callbacks",
]);

export const CUSTOMER_CACHE_VERSION = 2;
export const CUSTOMER_BOUNDARY_EVENT = "seo-autopilot-customer-boundary";
const CUSTOMER_SCOPE_PREFIX = "seo_autopilot:customer";
const AUTH_OWNER_MARKER_KEY = `${CUSTOMER_SCOPE_PREFIX}:auth-owner`;
const ACTIVE_PROJECT_KIND = "active-project";

function normalizedPart(value) {
  return String(value || "").trim();
}

function normalizedDomain(value) {
  const raw = normalizedPart(value).toLowerCase();
  if (!raw) return "";
  try {
    const url = new URL(raw.includes("://") ? raw : `https://${raw}`);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return raw.replace(/^www\./, "").replace(/\/$/, "");
  }
}

export function customerCacheScope({ ownerId, projectId } = {}) {
  const owner = normalizedPart(ownerId);
  const project = normalizedPart(projectId);
  if (!owner || !project) return "";
  return `${encodeURIComponent(owner)}:${encodeURIComponent(project)}`;
}

export function customerCacheKey(kind, identity = {}) {
  const scope = customerCacheScope(identity);
  const safeKind = normalizedPart(kind);
  if (!scope || !safeKind) return "";
  return `${CUSTOMER_SCOPE_PREFIX}:${scope}:${safeKind}`;
}

function customerOwnerKey(kind, ownerId) {
  const owner = normalizedPart(ownerId);
  const safeKind = normalizedPart(kind);
  if (!owner || !safeKind) return "";
  return `${CUSTOMER_SCOPE_PREFIX}:${encodeURIComponent(owner)}:owner:${safeKind}`;
}

export function normalizeCustomerIdentity(identity = {}) {
  return {
    owner_id: normalizedPart(identity.owner_id ?? identity.ownerId ?? identity.owner_user_id),
    project_id: normalizedPart(identity.project_id ?? identity.projectId),
    request_id: normalizedPart(identity.request_id ?? identity.requestId),
    scan_id: normalizedPart(identity.scan_id ?? identity.scanId ?? identity.scan_run_id),
    normalized_domain: normalizedDomain(
      identity.normalized_domain ?? identity.normalizedDomain ?? identity.website_url,
    ),
    canonical_mode: normalizedPart(
      identity.canonical_mode ?? identity.canonicalMode ?? identity.scan_mode,
    ),
    release_identity: normalizedPart(
      identity.release_identity ?? identity.releaseIdentity ?? identity.beta_revision_fingerprint,
    ),
  };
}

export function customerIdentityMatches(candidate, expected, { requireExactScan = true } = {}) {
  const actual = normalizeCustomerIdentity(candidate);
  const wanted = normalizeCustomerIdentity(expected);
  const required = [
    "owner_id",
    "project_id",
    "request_id",
    "normalized_domain",
    "canonical_mode",
    "release_identity",
  ];
  if (requireExactScan) required.push("scan_id");
  return required.every((field) => Boolean(wanted[field]) && actual[field] === wanted[field]);
}

function removeKeys(storage, keys, prefixes = []) {
  if (!storage) return;

  const matchingKeys = [];
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && prefixes.some((prefix) => key.startsWith(prefix))) matchingKeys.push(key);
    }
  } catch {
    // Browser privacy settings can block enumeration. Explicit keys are still attempted below.
  }

  for (const key of [...keys, ...matchingKeys]) {
    try {
      storage.removeItem(key);
    } catch {
      // Cache cleanup must never prevent the Base44 session from being revoked.
    }
  }
}

export function signalCustomerBoundary(reason, detail = {}, browserWindow = globalThis.window) {
  if (!browserWindow?.dispatchEvent) return;
  try {
    const EventType = browserWindow.CustomEvent || globalThis.CustomEvent;
    const event = typeof EventType === "function"
      ? new EventType(CUSTOMER_BOUNDARY_EVENT, { detail: { reason, ...detail } })
      : new Event(CUSTOMER_BOUNDARY_EVENT);
    browserWindow.dispatchEvent(event);
  } catch {
    // Boundary signalling is best-effort; storage cleanup is still authoritative.
  }
}

export function isCustomerAuthBoundaryError(error) {
  const status = Number(
    error?.status
    ?? error?.response?.status
    ?? error?.data?.status
    ?? error?.response?.data?.status,
  );
  return status === 401 || status === 403;
}

export function clearCustomerAuthBoundary(error, browserWindow = globalThis.window) {
  if (!isCustomerAuthBoundaryError(error)) return false;
  clearCustomerBrowserCaches(browserWindow, "auth_expired");
  return true;
}

export function clearCustomerBrowserCaches(browserWindow = globalThis.window, reason = "session_cleared") {
  if (!browserWindow) return;

  try {
    removeKeys(
      browserWindow.localStorage,
      CUSTOMER_LOCAL_STORAGE_KEYS,
      CUSTOMER_LOCAL_STORAGE_PREFIXES,
    );
  } catch {
    // Accessing localStorage itself can throw when browser storage is disabled.
  }

  try {
    removeKeys(browserWindow.sessionStorage, CUSTOMER_SESSION_STORAGE_KEYS);
  } catch {
    // Session cache cleanup is best-effort for the same reason.
  }
  signalCustomerBoundary(reason, {}, browserWindow);
}


export function clearLegacyCustomerCaches(browserWindow = globalThis.window) {
  if (!browserWindow) return;
  try {
    removeKeys(browserWindow.localStorage, CUSTOMER_LOCAL_STORAGE_KEYS, ["seo_autopilot:scan:"]);
  } catch {
    // Legacy cleanup is best effort; active code never reads these keys.
  }
}

export function synchronizeAuthenticatedOwner(ownerId, browserWindow = globalThis.window) {
  const owner = normalizedPart(ownerId);
  if (!owner || !browserWindow?.localStorage) return false;
  let previous = "";
  try {
    previous = normalizedPart(browserWindow.localStorage.getItem(AUTH_OWNER_MARKER_KEY));
  } catch {
    return false;
  }
  if (previous !== owner) clearCustomerBrowserCaches(browserWindow, previous ? "account_switch" : "auth_session_start");
  clearLegacyCustomerCaches(browserWindow);
  try {
    browserWindow.localStorage.setItem(AUTH_OWNER_MARKER_KEY, owner);
    return true;
  } catch {
    return false;
  }
}

export function readCustomerActiveProject(ownerId, browserWindow = globalThis.window) {
  const owner = normalizedPart(ownerId);
  const key = customerOwnerKey(ACTIVE_PROJECT_KIND, owner);
  if (!key || !browserWindow?.localStorage) return "";
  try {
    // A global pointer can belong to another account, so it is never read.
    browserWindow.localStorage.removeItem("active_project_id");
    const raw = browserWindow.localStorage.getItem(key);
    if (!raw) return "";
    const envelope = JSON.parse(raw);
    if (
      envelope?.cache_version !== CUSTOMER_CACHE_VERSION
      || normalizedPart(envelope.owner_id) !== owner
      || !normalizedPart(envelope.project_id)
    ) {
      browserWindow.localStorage.removeItem(key);
      return "";
    }
    return normalizedPart(envelope.project_id);
  } catch {
    try { browserWindow.localStorage.removeItem(key); } catch { /* best effort */ }
    return "";
  }
}

export function writeCustomerActiveProject(ownerId, projectId, browserWindow = globalThis.window) {
  const owner = normalizedPart(ownerId);
  const project = normalizedPart(projectId);
  const key = customerOwnerKey(ACTIVE_PROJECT_KIND, owner);
  if (!key || !project || !browserWindow?.localStorage) return false;
  const previousProject = readCustomerActiveProject(owner, browserWindow);
  if (previousProject && previousProject !== project) {
    clearCustomerProjectCaches({ ownerId: owner, projectId: previousProject }, browserWindow, false);
  }
  try {
    browserWindow.localStorage.removeItem("active_project_id");
    browserWindow.localStorage.setItem(key, JSON.stringify({
      cache_version: CUSTOMER_CACHE_VERSION,
      owner_id: owner,
      project_id: project,
    }));
    removeKeys(browserWindow.sessionStorage, CUSTOMER_SESSION_STORAGE_KEYS);
    if (previousProject !== project) {
      signalCustomerBoundary("project_switch", { owner_id: owner, project_id: project }, browserWindow);
    }
    return true;
  } catch {
    return false;
  }
}

export function writeCustomerCache(kind, value, identity, browserWindow = globalThis.window) {
  const key = customerCacheKey(kind, identity);
  const normalizedIdentity = normalizeCustomerIdentity(identity);
  if (!key || !browserWindow?.localStorage) return false;
  if (!normalizedIdentity.owner_id || !normalizedIdentity.project_id) return false;
  try {
    browserWindow.localStorage.setItem(key, JSON.stringify({
      cache_version: CUSTOMER_CACHE_VERSION,
      identity: normalizedIdentity,
      value,
    }));
    return true;
  } catch {
    return false;
  }
}

export function readCustomerCache(
  kind,
  expectedIdentity,
  browserWindow = globalThis.window,
  { requireExactScan = true } = {},
) {
  const key = customerCacheKey(kind, expectedIdentity);
  if (!key || !browserWindow?.localStorage) return null;
  try {
    const raw = browserWindow.localStorage.getItem(key);
    if (!raw) return null;
    const envelope = JSON.parse(raw);
    if (envelope?.cache_version !== CUSTOMER_CACHE_VERSION) {
      browserWindow.localStorage.removeItem(key);
      return null;
    }
    if (!customerIdentityMatches(envelope.identity, expectedIdentity, { requireExactScan })) {
      browserWindow.localStorage.removeItem(key);
      return null;
    }
    return envelope.value ?? null;
  } catch {
    try { browserWindow.localStorage.removeItem(key); } catch { /* best effort */ }
    return null;
  }
}

export function clearCustomerProjectCaches(
  identity,
  browserWindow = globalThis.window,
  shouldSignal = true,
) {
  const scope = customerCacheScope(identity);
  if (!scope || !browserWindow?.localStorage) return;
  removeKeys(browserWindow.localStorage, [], [`${CUSTOMER_SCOPE_PREFIX}:${scope}:`]);
  try {
    removeKeys(browserWindow.sessionStorage, CUSTOMER_SESSION_STORAGE_KEYS);
  } catch {
    // Best effort when storage access is restricted.
  }
  if (shouldSignal) signalCustomerBoundary("project_cache_cleared", normalizeCustomerIdentity(identity), browserWindow);
}

export function createResponseGuard(identity) {
  const snapshot = normalizeCustomerIdentity(identity);
  let active = true;
  return Object.freeze({
    identity: snapshot,
    cancel() { active = false; },
    accepts(responseIdentity, currentIdentity = snapshot) {
      return active
        && customerIdentityMatches(responseIdentity, snapshot)
        && customerIdentityMatches(currentIdentity, snapshot);
    },
  });
}
