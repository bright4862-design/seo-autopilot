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
