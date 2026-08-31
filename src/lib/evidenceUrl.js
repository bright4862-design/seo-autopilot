/**
 * One contract for showing an affected page to a customer.
 *
 * The 35-site production audit found evidence URLs rendered as plain text and
 * the site root shown as a bare "/", which tells a customer nothing about which
 * page is affected. Cards, modals and exports each formatted URLs their own
 * way, so a page could read differently in three places in one report.
 *
 * Nothing here invents evidence. A path is resolved against the origin the scan
 * actually ran on, and when no trustworthy origin is available the path is shown
 * as-is rather than resolved against whatever host happens to be serving the
 * app -- a relative path must never appear to belong to getfixlist.com.
 */

const HTTP_URL = /^https?:\/\//i;
// The only schemes a customer report may turn into a link. An allowlist on the
// parsed protocol is the single guard: `new URL("javascript:...", origin)`
// parses as an absolute javascript: URL rather than resolving against the
// origin, so checking what came out is what actually decides safety. A second
// pattern-matching guard in front of this only made the real one untestable.
const LINKABLE_PROTOCOLS = new Set(["http:", "https:"]);

const clean = (value) => (typeof value === "string" ? value.trim() : "");

/** True when a value is already an absolute http(s) URL. */
export function isAbsoluteHttpUrl(value) {
  return HTTP_URL.test(clean(value));
}

/**
 * The absolute URL for a page, or "" when one cannot honestly be produced.
 *
 * An unsafe scheme returns "" rather than a link: a report is a document a
 * customer clicks through, so a `javascript:` payload smuggled into evidence
 * must not survive as an anchor href.
 */
export function resolveEvidenceUrl(page, siteOrigin) {
  const raw = clean(page);
  if (!raw) return "";
  const origin = clean(siteOrigin);
  // A relative path with no trustworthy origin has no honest absolute form.
  if (!isAbsoluteHttpUrl(raw) && !isAbsoluteHttpUrl(origin)) return "";
  try {
    const resolved = new URL(raw, isAbsoluteHttpUrl(origin) ? origin : undefined);
    return LINKABLE_PROTOCOLS.has(resolved.protocol) ? resolved.toString() : "";
  } catch {
    return "";
  }
}

/** The path a page occupies, for display beneath its label. */
export function evidencePath(page) {
  const raw = clean(page);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return `${url.pathname}${url.search}` || "/";
  } catch {
    return raw.split("#")[0] || "";
  }
}

/**
 * What the customer reads for this page.
 *
 * The root is named, not punctuated: "Homepage · /" says which page it is and
 * still shows the path it lives at. Everything else reads as its own path,
 * which is what someone editing the site actually recognises.
 */
export function evidenceDisplayLabel(page) {
  const path = evidencePath(page);
  if (!path || path === "/") return "Homepage · /";
  return path;
}

/** An accessible name that says what opening the link will do. */
export function evidenceLinkName(page) {
  return `Open affected page: ${evidenceDisplayLabel(page)}`;
}

/**
 * Everything a surface needs to render one page consistently.
 *
 * `href` is empty whenever the page must not be clickable, so a caller renders
 * a link only when the contract says one is safe.
 */
export function evidenceLink(page, siteOrigin) {
  const href = resolveEvidenceUrl(page, siteOrigin);
  return {
    href,
    label: evidenceDisplayLabel(href || page),
    path: evidencePath(href || page),
    title: href || clean(page),
    linkName: evidenceLinkName(href || page),
    isLinkable: Boolean(href),
  };
}
