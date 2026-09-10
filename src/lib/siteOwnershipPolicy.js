import { normalizeCustomerIdentity } from "./customerBrowserCache.js";

/**
 * Whether the customer can change the site they are scanning, and what that
 * changes for them.
 *
 * Two customers see the same blocked scan and need opposite advice. Someone
 * scanning their own site can go and allow FixList through their firewall;
 * someone checking a competitor, a client's site before a pitch, or a site they
 * have no login for cannot, and telling them to "allow FixList in your bot
 * protection" sends them to a settings page they will never reach. FixList
 * cannot infer which one is reading -- nothing in a crawl distinguishes an
 * owner from an onlooker -- so it asks once, before the scan, and remembers.
 */
export const SITE_OWNERSHIP_POLICY_VERSION = "site_ownership_policy_v1_owner_managed_robots";

export const OWNERSHIP_UNANSWERED = "";
export const OWNERSHIP_OWNER_MANAGED = "owner_managed";
export const OWNERSHIP_NOT_MANAGED = "not_managed";

/** The closed set of stored answers. Anything else reads as unanswered. */
export const SITE_OWNERSHIP_ANSWERS = Object.freeze([
  OWNERSHIP_OWNER_MANAGED,
  OWNERSHIP_NOT_MANAGED,
]);

export const OWNERSHIP_QUESTION = "Do you own or manage this website?";

/**
 * Written in terms of what the answer lets FixList do for them, not in terms of
 * legal ownership. "Manage" is the operative word: an agency running a client's
 * site can act on a firewall block, and a company's legal owner may not be able
 * to.
 */
export const OWNERSHIP_ANSWER_LABELS = Object.freeze({
  [OWNERSHIP_OWNER_MANAGED]: "Yes — I can change this site's settings",
  [OWNERSHIP_NOT_MANAGED]: "No — I'm checking someone else's site",
});

export const OWNERSHIP_HELP_TEXT =
  "This only changes the advice FixList gives you if the scan is blocked. It does not change how the site is scanned.";

/** Normalizes any stored or submitted value onto the closed set. */
export function normalizeOwnershipAnswer(value) {
  const answer = typeof value === "string" ? value.trim() : "";
  return SITE_OWNERSHIP_ANSWERS.includes(answer) ? answer : OWNERSHIP_UNANSWERED;
}

export function isOwnerManaged(value) {
  return normalizeOwnershipAnswer(value) === OWNERSHIP_OWNER_MANAGED;
}

const OWNERSHIP_KEY_PREFIX = "seo_autopilot:customer:site-ownership";

/**
 * One key per website, under the existing customer-scoped prefix so the answer
 * is cleared with the rest of a customer's local state at a customer boundary.
 *
 * Keyed on the site rather than the project. A project in this app is a
 * website, and the question is asked before submission -- before
 * `ensureScanProject` has resolved an id -- so a project-scoped key would be
 * written under one name and read back under another on the next visit, which
 * reads to the customer as the answer not sticking.
 */
export function siteOwnershipStorageKey(websiteUrl) {
  const domain = normalizeCustomerIdentity({ website_url: websiteUrl }).normalized_domain;
  return domain ? `${OWNERSHIP_KEY_PREFIX}:${domain}` : "";
}

/**
 * Browser storage is optional here, never load-bearing.
 *
 * Private windows, cleared site data and storage-blocking settings all make
 * these throw or come back empty. An unanswered question is a normal state that
 * the form and the failure copy both handle, so every path returns the
 * unanswered value rather than propagating a storage fault into the scan.
 */
function storage() {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export function readSiteOwnership(websiteUrl) {
  const key = siteOwnershipStorageKey(websiteUrl);
  if (!key) return OWNERSHIP_UNANSWERED;
  const store = storage();
  if (!store) return OWNERSHIP_UNANSWERED;
  try {
    return normalizeOwnershipAnswer(store.getItem(key));
  } catch {
    return OWNERSHIP_UNANSWERED;
  }
}

/**
 * Stores an answer, and reports whether it was stored.
 *
 * Clearing on the unanswered value rather than writing an empty string keeps a
 * "no answer" indistinguishable from "never asked", so a customer who changes
 * their mind is asked again instead of being held to a blank.
 */
export function writeSiteOwnership(websiteUrl, value) {
  const key = siteOwnershipStorageKey(websiteUrl);
  if (!key) return false;
  const store = storage();
  if (!store) return false;
  const answer = normalizeOwnershipAnswer(value);
  try {
    if (answer === OWNERSHIP_UNANSWERED) store.removeItem(key);
    else store.setItem(key, answer);
    return true;
  } catch {
    return false;
  }
}

/**
 * The robots policy fields a Standard 150 submission carries for this answer.
 *
 * `respect_robots_txt` is `true` for both answers, and that is deliberate. The
 * scanner API rejects any Standard 150 submission whose `respect_robots_txt` is
 * not exactly `true` -- HTTP 400, "Standard scans must respect robots.txt", on
 * both the admission and the dispatch path -- so sending `false` for an owner
 * would not widen the crawl, it would fail the scan outright for exactly the
 * customers who told us they can fix things.
 *
 * Declaring ownership records who is able to act on a block. It does not change
 * what the crawler obeys, and nothing here should ever be used to make it.
 */
export function ownerManagedRobotsPolicy(value) {
  const owner = isOwnerManaged(value);
  return Object.freeze({
    respect_robots_txt: true,
    owner_managed_site: owner,
    robots_policy: owner ? "owner_managed" : "public_crawler",
    site_ownership_answer: normalizeOwnershipAnswer(value),
    site_ownership_policy_version: SITE_OWNERSHIP_POLICY_VERSION,
  });
}
