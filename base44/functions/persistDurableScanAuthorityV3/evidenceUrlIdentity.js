/**
 * One URL identity, shared with Python.
 *
 * Python decides a repair's partitions and this runtime re-verifies them. If the
 * two disagree about whether "/a?b=1&c=2" and "/a?c=2&b=1" are the same URL, a
 * payload Python considers valid fails these invariants -- or worse, passes them
 * while describing a different set of pages.
 *
 * Mirrors scanner-api/app/repair_coverage.py. Both are asserted against
 * tests/fixtures/evidence-url-identity.json, which neither side owns.
 */

// Parameters that identify a visitor or a campaign, never a page.
const TRACKING_PARAMETERS = new Set([
  "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
  "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "mc_cid", "mc_eid",
  "ref", "referrer", "source",
]);

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizedPath(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  let path;
  if (raw.includes("//")) {
    try {
      path = new URL(raw).pathname;
    } catch {
      path = raw.split("?")[0].split("#")[0];
    }
  } else {
    path = raw.split("?")[0].split("#")[0];
  }
  path = safeDecode(path) || "/";
  if (!path.startsWith("/")) path = `/${path}`;
  // Case folded: a host filesystem is not the identity of a page.
  return (path.replace(/\/+$/, "") || "/").toLowerCase();
}

/** Path-only identity, which is what a template family is defined over. */
export function templateFamilyKey(value) {
  return normalizedPath(value);
}

function rawQuery(value) {
  const raw = String(value || "");
  if (raw.includes("//")) {
    try {
      return new URL(raw).search.replace(/^\?/, "");
    } catch {
      /* fall through to the string form below */
    }
  }
  const index = raw.indexOf("?");
  return index === -1 ? "" : raw.slice(index + 1).split("#")[0];
}

function canonicalQuery(value) {
  const query = rawQuery(value);
  if (!query) return "";
  const pairs = [];
  for (const part of query.split("&")) {
    if (!part) continue;
    const index = part.indexOf("=");
    const key = safeDecode(index === -1 ? part : part.slice(0, index));
    const val = index === -1 ? "" : safeDecode(part.slice(index + 1));
    // Duplicate keys are both kept: dropping one would merge two pages a server
    // may well render differently.
    if (!TRACKING_PARAMETERS.has(key.toLowerCase())) pairs.push([key, val]);
  }
  if (pairs.length === 0) return "";
  pairs.sort((left, right) => (
    left[0] < right[0] ? -1 : left[0] > right[0] ? 1
      : left[1] < right[1] ? -1 : left[1] > right[1] ? 1 : 0
  ));
  return pairs
    .map(([key, val]) => `${encodeURIComponent(key)}=${encodeURIComponent(val)}`)
    .join("&");
}

/** Path plus canonical query: the identity of one piece of page evidence. */
export function evidenceUrlKey(value) {
  const path = normalizedPath(value);
  if (!path) return "";
  const query = canonicalQuery(value);
  return query ? `${path}?${query}` : path;
}

export const PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION = "evidence_url_identity_v2_published_route";

const OBSERVED_URL_FORBIDDEN = /[\u0000-\u0020\u007f-\u009f\\]/;
const OBSERVED_ABSOLUTE_URL = /^(https?):\/\/([^/?#]+)([\s\S]*)$/i;

function publishedOrigin(scheme, authority) {
  if (authority.includes("@") || authority.includes("%")) return "";
  const ipv6 = authority.startsWith("[");
  const parts = ipv6
    ? authority.match(/^\[([^\]]+)\](?::([0-9]+))?$/)
    : authority.match(/^([^:\[\]]+)(?::([0-9]+))?$/);
  if (!parts) return "";
  scheme = scheme.toLowerCase();
  let port = "";
  if (parts[2] !== undefined) {
    const number = Number(parts[2]);
    if (!Number.isInteger(number) || number > 65535) return "";
    if (number !== (scheme === "https" ? 443 : 80)) port = `:${number}`;
  }
  try {
    // The URL parser sees only the origin: it may normalize IDN/IPv6, but must
    // never rewrite the observed path, dot segments, escapes or query.
    const host = new URL(`${scheme}://${ipv6 ? `[${parts[1]}]` : parts[1]}/`).hostname;
    if (!ipv6) {
      // Validate the UTS-46 host without URL's non-canonical IPv4 coercions.
      // A dummy nonnumeric suffix keeps numeric inputs in domain parsing mode.
      const domain = new URL(`https://${parts[1]}.invalid/`).hostname.slice(0, -8);
      const labels = domain.replace(/\.$/, "").split(".");
      if (domain.replace(/\.$/, "").length > 253 || labels.some((label) => (
        label.length > 63 || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label)
      ))) return "";
      if (host !== domain) return "";
      const last = labels.at(-1);
      if (/^(?:[0-9]+|0x[0-9a-f]*)$/.test(last)) {
        if (domain.endsWith(".") || labels.length !== 4 || labels.some((label) => (
          !/^(?:0|[1-9][0-9]{0,2})$/.test(label) || Number(label) > 255
        ))) return "";
      }
    }
    return `${scheme}://${host}${port}`;
  } catch {
    return "";
  }
}

/** Exact observed HTTP(S) route, with only origin/fragment normalization. */
export function publishedEvidenceUrlKey(value, { scanOrigin = "" } = {}) {
  if (typeof value !== "string" || !value || OBSERVED_URL_FORBIDDEN.test(value)) return "";
  const raw = value.split("#", 1)[0];
  const absolute = raw.match(OBSERVED_ABSOLUTE_URL);
  let origin;
  let route;
  if (absolute) {
    origin = publishedOrigin(absolute[1], absolute[2]);
    route = absolute[3];
  } else if (raw.startsWith("/") && !raw.startsWith("//")) {
    if (typeof scanOrigin !== "string" || OBSERVED_URL_FORBIDDEN.test(scanOrigin)) return "";
    const base = scanOrigin.match(OBSERVED_ABSOLUTE_URL);
    if (!base) return "";
    origin = publishedOrigin(base[1], base[2]);
    route = raw;
  } else {
    return "";
  }
  return origin ? origin + (route.startsWith("/") ? route : `/${route}`) : "";
}
