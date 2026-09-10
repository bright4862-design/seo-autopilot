import { normalizeCustomerIdentity } from "./customerBrowserCache.js";

export const SITE_OWNERSHIP_POLICY_VERSION = "site_ownership_policy_v3_owner_robots_override";

export const OWNERSHIP_UNANSWERED = "";
export const OWNERSHIP_OWNER_MANAGED = "owner_or_manager";
export const OWNERSHIP_NOT_MANAGED = "not_owner";

export const SITE_OWNERSHIP_ANSWERS = Object.freeze([
  OWNERSHIP_OWNER_MANAGED,
  OWNERSHIP_NOT_MANAGED,
]);

export const SITE_OWNER_ATTESTATION_FIELD = "site_owner_attestation";
export const OWNERSHIP_QUESTION = "Do you own or manage this website?";

export const OWNERSHIP_ANSWER_LABELS = Object.freeze({
  [OWNERSHIP_OWNER_MANAGED]: "Yes — I can change this site's settings",
  [OWNERSHIP_NOT_MANAGED]: "No — I'm checking someone else's site",
});

export function normalizeOwnershipAnswer(value) {
  const answer = typeof value === "string" ? value.trim() : "";
  return SITE_OWNERSHIP_ANSWERS.includes(answer) ? answer : OWNERSHIP_UNANSWERED;
}

export function isOwnerManaged(value) {
  return normalizeOwnershipAnswer(value) === OWNERSHIP_OWNER_MANAGED;
}

const OWNERSHIP_KEY_PREFIX = "seo_autopilot:customer:site-ownership";

export function siteOwnershipStorageKey(websiteUrl) {
  const domain = normalizeCustomerIdentity({ website_url: websiteUrl }).normalized_domain;
  return domain ? `${OWNERSHIP_KEY_PREFIX}:${domain}` : "";
}

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
 * Resolve the ownership state that was actually applied to a saved scan.
 * New scans use the immutable ScanRun policy fields first. The legacy
 * site_ownership_answer fallback keeps pre-policy scans readable.
 */
export function scanRunOwnership(record) {
  const source = record && typeof record === "object" ? record : {};
  if (source.owner_attested_robots_override === true) return OWNERSHIP_OWNER_MANAGED;
  if (
    Object.prototype.hasOwnProperty.call(source, "owner_attested_robots_override")
    && source.owner_attested_robots_override === false
  ) return OWNERSHIP_NOT_MANAGED;
  return normalizeOwnershipAnswer(source.site_ownership_answer);
}

export function resolveScanOwnership(record, browserAnswer) {
  return scanRunOwnership(record) || normalizeOwnershipAnswer(browserAnswer);
}

export function projectAttestationUpdate(project, value) {
  const answer = normalizeOwnershipAnswer(value);
  if (!answer) return null;
  const source = project && typeof project === "object" ? project : {};
  if (normalizeOwnershipAnswer(source[SITE_OWNER_ATTESTATION_FIELD]) === answer) return null;
  return { [SITE_OWNER_ATTESTATION_FIELD]: answer };
}

export function ownershipOnSiteChange({ hadNoSite, pendingAnswer, storedAnswer } = {}) {
  const pending = normalizeOwnershipAnswer(pendingAnswer);
  const stored = normalizeOwnershipAnswer(storedAnswer);
  if (hadNoSite && pending && !stored) return { carry: true, answer: pending };
  return { carry: false, answer: stored };
}

/**
 * Browser intent only. The server still derives the applied policy from the
 * owned BusinessProject before it creates or dispatches a ScanRun, so these
 * fields cannot grant an override by themselves.
 */
export function ownerManagedRobotsPolicy(value) {
  const answer = normalizeOwnershipAnswer(value);
  const owner = answer === OWNERSHIP_OWNER_MANAGED;
  return Object.freeze({
    respect_robots_txt: !owner,
    owner_attested_robots_override: owner,
    owner_managed_site: owner,
    robots_policy: owner ? "owner_managed" : "public_crawler",
    site_ownership_answer: answer,
    site_ownership_policy_version: SITE_OWNERSHIP_POLICY_VERSION,
  });
}

export function policyObeysRobots(policy) {
  const source = policy && typeof policy === "object" ? policy : {};
  return source.respect_robots_txt === true && source.owner_attested_robots_override === false;
}

export function submissionObeysRobots(value) {
  return policyObeysRobots(ownerManagedRobotsPolicy(value));
}

export const ROBOTS_OBEYED_COPY = Object.freeze({
  help: "FixList will respect robots.txt and the site's other access controls.",
  spec: "Scan depth: up to 150 pages · respects robots.txt · read-only",
});

export const ROBOTS_OVERRIDE_COPY = Object.freeze({
  help: "Because you own or manage this site, FixList can ignore robots.txt for this scan. This does not bypass logins, firewalls, bot challenges, or rate limits.",
  spec: "Scan depth: up to 150 pages · owner robots override · read-only",
});

export function helpTextForPolicy(policy) {
  return policyObeysRobots(policy) ? ROBOTS_OBEYED_COPY.help : ROBOTS_OVERRIDE_COPY.help;
}

export function ownershipHelpText(value) {
  return helpTextForPolicy(ownerManagedRobotsPolicy(value));
}

export function scanSpecForOwnership(value) {
  return submissionObeysRobots(value) ? ROBOTS_OBEYED_COPY.spec : ROBOTS_OVERRIDE_COPY.spec;
}
