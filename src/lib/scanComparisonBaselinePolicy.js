const VERSION = "scan_comparison_baseline_policy_v1";
const ID = /^[A-Za-z0-9_-]{1,160}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const STATUS = new Set(["queued", "crawling", "reviewing", "complete", "limited", "failed", "cancelled"]);
const CREATION_KEYS = new Set([
  "owner_user_id", "project_id", "normalized_domain", "requested_origin",
  "scope_type", "requested_path_prefix", "selection_cutoff_at",
]);
const CANDIDATE_KEYS = new Set([
  "scan_id", "owner_user_id", "project_id", "normalized_domain", "requested_origin",
  "scope_type", "requested_path_prefix", "status", "authority_verified", "sealed_at",
]);

function exactKeys(value, expected, field) {
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new TypeError(`${field} must contain only the versioned descriptor fields`);
  }
}

function exactString(value, field, maximum = 2_000) {
  if (typeof value !== "string" || !value || value !== value.trim() || value.length > maximum) {
    throw new TypeError(`${field} must be an exact bounded string`);
  }
  return value;
}

function scanId(value, field) {
  if (typeof value !== "string" || !ID.test(value)) throw new TypeError(`${field} must be an exact scan id`);
  return value;
}

function instant(value, field) {
  const raw = exactString(value, field, 80);
  if (!INSTANT.test(raw)) throw new TypeError(`${field} must be a UTC RFC3339 timestamp`);
  const milliseconds = Date.parse(raw);
  if (!Number.isFinite(milliseconds)) throw new TypeError(`${field} must be a UTC RFC3339 timestamp`);
  const canonical = new Date(milliseconds).toISOString();
  const normalized = raw.includes(".")
    ? `${raw.slice(0, raw.indexOf("."))}.${raw.slice(raw.indexOf(".") + 1, -1).padEnd(3, "0")}Z`
    : `${raw.slice(0, -1)}.000Z`;
  if (canonical !== normalized) throw new TypeError(`${field} must be a real UTC RFC3339 timestamp`);
  return milliseconds;
}

function origin(value, field) {
  const raw = exactString(value, field);
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new TypeError(`${field} must be an HTTP origin`);
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password
      || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new TypeError(`${field} must be an HTTP origin`);
  }
  return parsed.origin;
}

function scope(record, prefix) {
  const normalizedDomain = exactString(record.normalized_domain, `${prefix} normalized_domain`).toLowerCase();
  if (normalizedDomain !== record.normalized_domain) throw new TypeError(`${prefix} normalized_domain must be canonical`);
  const requestedOrigin = origin(record.requested_origin, `${prefix} requested_origin`);
  const scopeType = record.scope_type;
  const path = record.requested_path_prefix;
  if (scopeType === "" && path === "") {
    return { normalizedDomain, requestedOrigin, scopeType, path };
  }
  if (scopeType !== "path_prefix" || typeof path !== "string" || path !== path.trim()
      || !path.startsWith("/") || path.startsWith("//") || /[?#\\]/.test(path)) {
    throw new TypeError(`${prefix} scope must be exact`);
  }
  return { normalizedDomain, requestedOrigin, scopeType, path };
}

function sameScope(left, right) {
  return left.normalizedDomain === right.normalizedDomain
    && left.requestedOrigin === right.requestedOrigin
    && left.scopeType === right.scopeType
    && left.path === right.path;
}

function creationIdentity(current) {
  if (!current || typeof current !== "object" || Array.isArray(current)) {
    throw new TypeError("current scan must be an object");
  }
  exactKeys(current, CREATION_KEYS, "current scan");
  return {
    owner: exactString(current.owner_user_id, "current owner_user_id"),
    project: exactString(current.project_id, "current project_id"),
    scope: scope(current, "current"),
    selectionCutoffAt: instant(current.selection_cutoff_at, "current selection_cutoff_at"),
  };
}

function candidateIdentity(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("candidate must be an object");
  }
  exactKeys(value, CANDIDATE_KEYS, "candidate");
  const status = exactString(value.status, "candidate status", 40);
  if (!STATUS.has(status)) throw new TypeError("candidate status is unsupported");
  if (typeof value.authority_verified !== "boolean") {
    throw new TypeError("candidate authority_verified must be boolean");
  }
  return {
    scanId: scanId(value.scan_id, "candidate scan_id"),
    owner: exactString(value.owner_user_id, "candidate owner_user_id"),
    project: exactString(value.project_id, "candidate project_id"),
    status,
    authorityVerified: value.authority_verified,
    scope: scope(value, "candidate"),
    sealedAt: instant(value.sealed_at, "candidate sealed_at"),
  };
}

/**
 * Select a baseline exactly once for a new scan.
 *
 * ``authority_verified`` is a typed input assertion, not authentication. The
 * serialized integrator must construct candidates from the existing HMAC-
 * verified reader; callers must never pass raw client rows to this policy.
 */
export function selectComparisonBaselineV1({ current, candidates }) {
  if (current && typeof current === "object" && Object.hasOwn(current, "previous_scan_id")) {
    throw new TypeError("current scan already persists previous_scan_id; use the preservation policy");
  }
  const currentIdentity = creationIdentity(current);
  if (!Array.isArray(candidates) || candidates.length > 100) {
    throw new TypeError("candidates must be a bounded array");
  }
  const seen = new Set();
  const eligible = candidates.map(candidateIdentity).filter((item) => {
    if (seen.has(item.scanId)) throw new TypeError("duplicate candidate scan_id");
    seen.add(item.scanId);
    return item.owner === currentIdentity.owner
      && item.project === currentIdentity.project
      && item.status === "complete"
      && item.authorityVerified === true
      && item.sealedAt < currentIdentity.selectionCutoffAt
      && sameScope(item.scope, currentIdentity.scope);
  });
  eligible.sort((left, right) => {
    if (left.sealedAt !== right.sealedAt) return right.sealedAt - left.sealedAt;
    return left.scanId < right.scanId ? -1 : left.scanId > right.scanId ? 1 : 0;
  });
  if (!eligible.length) {
    return {
      version: VERSION,
      state: "none",
      previous_scan_id: "",
      reason: "no_authenticated_same_scope_complete_scan",
    };
  }
  return {
    version: VERSION,
    state: "selected",
    previous_scan_id: eligible[0].scanId,
    reason: "latest_authenticated_same_scope_complete_scan",
  };
}

/** Preserve the exact stored decision. This function never accepts candidates. */
export function preservePersistedComparisonBaselineV1({ current }) {
  if (!current || typeof current !== "object" || Array.isArray(current)
      || !Object.hasOwn(current, "previous_scan_id")) {
    throw new TypeError("persisted previous_scan_id is required");
  }
  const value = current.previous_scan_id;
  if (value === "") {
    return {
      version: VERSION,
      state: "none",
      previous_scan_id: "",
      reason: "persisted_without_previous_scan",
    };
  }
  return {
    version: VERSION,
    state: "preserved",
    previous_scan_id: scanId(value, "previous_scan_id"),
    reason: "persisted_previous_scan_id",
  };
}
