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
export const SITE_OWNERSHIP_POLICY_VERSION = "site_ownership_policy_v2_owner_attestation_enum";

export const OWNERSHIP_UNANSWERED = "";
export const OWNERSHIP_OWNER_MANAGED = "owner_or_manager";
export const OWNERSHIP_NOT_MANAGED = "not_owner";

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

/** Normalizes any stored or submitted value onto the closed set. */
export function normalizeOwnershipAnswer(value) {
  const answer = typeof value === "string" ? value.trim() : "";
  return SITE_OWNERSHIP_ANSWERS.includes(answer) ? answer : OWNERSHIP_UNANSWERED;
}

/**
 * Whether this answer means the customer can act on the site's own settings.
 * @param {unknown} value A stored or in-flight ownership answer.
 * @returns {boolean} True only for an explicit owner-or-manager answer.
 */
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
/**
 * The browser store, or null when it is absent or throws on access.
 * @returns {Storage|null}
 */
function storage() {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

/**
 * Reads the stored answer for a site.
 * @param {string} websiteUrl Any URL or host for the site.
 * @returns {string} The stored answer, or the unanswered value when there is
 *   none, the host cannot be resolved, or storage is unavailable.
 */
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
 * What to do with the answer when the form's site changes.
 *
 * The form asks the question whether or not a URL has been typed yet, and an
 * answer given before the URL has nowhere to live: `writeSiteOwnership` needs a
 * host to build a key, so it stores nothing and reports false. Reading storage
 * for the newly typed site then returns nothing and clears the selection the
 * customer just made -- they answered, and the answer vanished as they finished
 * the field they were asked to fill in.
 *
 * A stored answer for the new site still wins. It was given while looking at
 * that site; the pending one was given before the site was known.
 *
 * @param {{hadNoSite: boolean, pendingAnswer: string, storedAnswer: string}} state
 * @returns {{carry: boolean, answer: string}} `carry` means persist `answer`
 *   under the new site's key and keep the current selection.
 */
export function ownershipOnSiteChange({ hadNoSite, pendingAnswer, storedAnswer } = {}) {
  const pending = normalizeOwnershipAnswer(pendingAnswer);
  const stored = normalizeOwnershipAnswer(storedAnswer);
  if (hadNoSite && pending && !stored) return { carry: true, answer: pending };
  return { carry: false, answer: stored };
}

/**
 * The robots policy fields a Standard 150 submission carries for this answer.
 *
 * The scanner API pairs two fields and rejects them when they disagree:
 * `owner_attested_robots_override` must be true exactly when
 * `respect_robots_txt` is false, or admission returns 400 "A robots.txt
 * override requires explicit owner attestation." Both are sent explicitly so
 * the pair is visible here rather than resting on a server-side default.
 *
 * This asks for no override. A checkbox in a browser is not an attestation:
 * the server may only honour one that is backed by durable, owned state, and
 * `BusinessProject.site_owner_attestation` does not exist in main yet. Until it
 * does, the honest thing for the frontend to send is the answer plus a refusal
 * to act on it -- so the customer's declaration is recorded and carried, and
 * the crawl obeys robots.txt exactly as it does today.
 *
 * When that durable field lands, the change is here and in ROBOTS_OBEYED_COPY
 * together; the test suite fails if one moves without the other.
 */
export function ownerManagedRobotsPolicy(value) {
  const owner = isOwnerManaged(value);
  return Object.freeze({
    respect_robots_txt: true,
    owner_attested_robots_override: false,
    owner_managed_site: owner,
    robots_policy: owner ? "owner_managed" : "public_crawler",
    site_ownership_answer: normalizeOwnershipAnswer(value),
    site_ownership_policy_version: SITE_OWNERSHIP_POLICY_VERSION,
  });
}

/**
 * Whether a submission built from this answer still obeys robots.txt, and the
 * customer-facing sentences that are only true while it does.
 *
 * These sentences are derived from the policy rather than written beside it. A
 * scan that overrides robots.txt while the form still promises it "does not
 * change how the site is scanned" is a lie told to the person who trusted us
 * enough to say they own the site, and it is the kind of lie that survives a
 * refactor because nobody remembers the copy is downstream of a boolean.
 */
/**
 * Whether a submission built from this policy plainly obeys robots.txt.
 * @param {{respect_robots_txt?: boolean, owner_attested_robots_override?: boolean}} policy
 * @returns {boolean} True only when robots.txt is respected and no override is
 *   attested; anything else is not a scan we may describe as obeying it.
 */
export function policyObeysRobots(policy) {
  const source = policy && typeof policy === "object" ? policy : {};
  return source.respect_robots_txt === true && source.owner_attested_robots_override === false;
}

/**
 * Whether the submission this answer produces obeys robots.txt.
 * @param {unknown} value An ownership answer.
 * @returns {boolean}
 */
export function submissionObeysRobots(value) {
  return policyObeysRobots(ownerManagedRobotsPolicy(value));
}

export const ROBOTS_OBEYED_COPY = Object.freeze({
  help: "This only changes the advice FixList gives you if the scan is blocked. It does not change how the site is scanned.",
  spec: "Scan depth: up to 150 pages · respects robots.txt · read-only",
});

/**
 * Takes the policy rather than the answer, so the withholding branch can be
 * exercised before any policy in this file reaches it. A guard whose false case
 * is unreachable is a guard that asserts nothing.
 */
export function helpTextForPolicy(policy) {
  return policyObeysRobots(policy) ? ROBOTS_OBEYED_COPY.help : "";
}

/**
 * The help line shown under the ownership question for this answer.
 * @param {unknown} value An ownership answer.
 * @returns {string} The help text, or "" when the resulting scan would no
 *   longer obey robots.txt and the sentence would be untrue.
 */
export function ownershipHelpText(value) {
  return helpTextForPolicy(ownerManagedRobotsPolicy(value));
}
