// The release component that names how a scan without a result is explained.
// It lived in FixList.jsx while the copy did; it moves here with the copy, and
// v2 records that the explanation is now derived from the producer's structured
// reason codes rather than from one status string.
export const FAILURE_STATE_PRESENTATION_VERSION = "failure_state_presentation_v2_structured_limitation_reasons";

/**
 * Why a scan produced no publishable result, in the customer's terms.
 *
 * Every one of these ended the same way on the page -- "This scan finished with
 * limited evidence", then advice to run a fresh scan -- so a site that is
 * rate-limiting the scanner and a site whose sitemap never answered read
 * identically, and the owner of the first was sent round a loop that cannot
 * terminate. The producer has recorded the difference in structured codes the
 * whole time; this module is the reader.
 *
 * The set is closed. A producer state that maps to nothing here lands on
 * `unknown_limited`, which says plainly that FixList cannot explain this one,
 * rather than borrowing the nearest-looking explanation.
 */
export const LIMITATION_KINDS = Object.freeze([
  "access_limited",
  "too_few_usable_pages",
  "deadline_reached",
  "rendering_not_verified",
  "save_failed",
  "worker_stalled",
  "unknown_limited",
]);

const RUNNING_STATUSES = new Set(["queued", "crawling", "reviewing"]);

// Structured codes, read first and preferred over any text. These are the
// values app/coverage_authority.py and app/evidence_quality.py publish.
const ACCESS_LIMITED_STATES = new Set(["access_limited"]);
const TOO_FEW_PAGES_STATES = new Set([
  "no_usable_html",
  "insufficient_discovery",
  "inventory_unproven",
  "limited_coverage",
  // discovery_quality_state keeps its own two labels where they are more
  // specific than the coverage state, so a row carrying only that field still
  // has to resolve. Missing them sent it to unknown_limited.
  "default_route_dominated",
  "single_page_inventory_unproven",
]);
const ACCESS_LIMITED_REASONS = new Set(["access_limited"]);
const TOO_FEW_PAGES_REASONS = new Set([
  "no_usable_html_pages",
  "small_site_inventory_unproven",
  "no_working_inventory_source",
  "inventory_source_truncated",
  "discovered_urls_unaccounted",
  "single_page_inventory_unproven",
  "sitemap_discovery_failed",
  "sitemap_never_fetched",
  "link_frontier_not_exhausted",
  "default_route_dominance",
  "representative_html_pages_below_minimum",
  "retained_pages_below_minimum",
  "coverage_ratio_below_minimum",
]);

// Historical rows carry no structured code at all, only free text a human wrote
// into status_detail or error_code. These patterns exist for those rows and are
// consulted last; nothing matched here is ever displayed, only classified.
const SAVE_FAILED_TEXT = /persist|save.?fail|authority.?write|result.?write/;
const WORKER_STALLED_TEXT = /heartbeat|stalled|orphaned|vanished|no_terminal|progress stopped/;
const ACCESS_LIMITED_TEXT = /429|rate.?limit|challenge|bot.?protection|access.?limit|scanner.?blocked/;
const DEADLINE_TEXT = /deadline|timed?.?out|time limit/;

function cleanText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function codeSet(value) {
  return new Set(
    (Array.isArray(value) ? value : [])
      .map((entry) => cleanText(entry).toLowerCase())
      .filter(Boolean),
  );
}

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function intersects(codes, allowed) {
  for (const code of codes) if (allowed.has(code)) return true;
  return false;
}

/** Free-text failure evidence, lowercased for matching and never for display. */
function failureText(record) {
  return `${cleanText(record.error_code)} ${cleanText(record.status_detail)}`.toLowerCase();
}

function deadlineReached(record) {
  const timing = plainObject(record.crawl_timing);
  return timing.crawl_deadline_reached === true
    || record.scan_deadline_reached === true
    || timing.scan_deadline_reached === true;
}

function renderingUnverified(record) {
  const evidence = plainObject(record.render_evidence);
  const coverage = plainObject(evidence.coverage);
  return cleanText(evidence.evidence_state) === "insufficient_raw_html_evidence"
    || coverage.sufficient === false;
}

/**
 * Which of the closed set explains this record.
 *
 * Order is not arbitrary. A save failure and a stalled worker are terminal
 * infrastructure states that say nothing about the site, so they are settled
 * first. Access limiting comes next because it explains everything downstream
 * of it: a blocked crawl also runs short of pages and also runs out of time,
 * and telling the owner about the symptom would send them to fix the wrong
 * thing. A deadline outranks a thin page count for the same reason -- it is the
 * cause, the page count is what it left behind. Rendering evidence is last of
 * the real reasons because it describes how the pages that did arrive were
 * evaluated, which only matters once pages arrived.
 */
export function durableScanLimitationKind(record) {
  const source = plainObject(record);
  const text = failureText(source);

  if (SAVE_FAILED_TEXT.test(text)) return "save_failed";
  if (WORKER_STALLED_TEXT.test(text)) return "worker_stalled";

  const states = new Set([
    cleanText(source.evidence_quality_state).toLowerCase(),
    cleanText(source.coverage_state).toLowerCase(),
    cleanText(source.discovery_quality_state).toLowerCase(),
  ].filter(Boolean));
  const reasons = new Set([
    ...codeSet(source.evidence_quality_reasons),
    ...codeSet(source.coverage_reasons),
  ]);

  if (intersects(states, ACCESS_LIMITED_STATES) || intersects(reasons, ACCESS_LIMITED_REASONS)) {
    return "access_limited";
  }
  if (ACCESS_LIMITED_TEXT.test(text)) return "access_limited";
  if (deadlineReached(source)) return "deadline_reached";
  if (intersects(states, TOO_FEW_PAGES_STATES) || intersects(reasons, TOO_FEW_PAGES_REASONS)) {
    return "too_few_usable_pages";
  }
  if (renderingUnverified(source)) return "rendering_not_verified";
  if (DEADLINE_TEXT.test(text)) return "deadline_reached";
  return "unknown_limited";
}

/**
 * What happened, whether the saved evidence is worth anything, and what to do.
 *
 * Every string here is written in this file. Nothing is interpolated from
 * status_detail or error_code, which is where exception text, worker
 * identifiers and upstream URLs end up; those fields classify and never
 * publish. The retry advice is tailored per reason and never promises that
 * running the scan again will work, because for most of these it will not.
 */
const COPY = {
  access_limited: {
    title: "The website limited automated access",
    detail: "The website answered FixList with rate limits or a bot challenge before enough pages could be checked, so no complete FixList was published. What did get through is not a fair sample of the site.",
    nextStep: "Ask whoever manages the site's CDN, firewall, or bot protection to allow the scan, then run it again.",
    retryAdvice: "A scan started now would most likely be limited the same way. Wait for the limit to lift, or get the scanner allowed through first.",
  },
  too_few_usable_pages: {
    title: "Too few usable pages to judge the site",
    detail: "FixList found URLs for this site but could only verify a small number of usable HTML pages, and most of what it did reach was default, archive, or internal routes. That is not enough evidence to describe the site as a whole.",
    nextStep: "Check that the sitemap is reachable and lists real pages, and that the main sections are linked from the homepage.",
    retryAdvice: "Running the same scan again will find the same pages. Fix the sitemap or internal linking first, or scan one section directly.",
  },
  deadline_reached: {
    title: "The scan reached its time limit",
    detail: "FixList stopped at its safe time limit before it had verified enough pages to publish a result. The pages it did check are real; there were not enough of them to describe the site.",
    nextStep: "Scan a single section instead of the whole site, so the time budget is spent where you need the answer.",
    retryAdvice: "A whole-site scan is likely to reach the same limit again on a site this size or this slow to respond.",
  },
  rendering_not_verified: {
    title: "Not enough pages could be read to publish a result",
    detail: "Pages responded, but too few of them returned HTML FixList could evaluate, so it cannot tell whether this site's content is present in the page source or added afterwards in the browser. Judging the site on that would be a guess.",
    nextStep: "Ask your web person whether the main content is rendered on the server or in the browser, then scan a section that returns full HTML.",
    retryAdvice: "Repeating the scan will read the same pages the same way, so the outcome would be the same.",
  },
  save_failed: {
    title: "The result could not be saved",
    detail: "Crawling finished, but FixList could not store the verified result, so nothing was published. Anything a browser tab showed mid-run was partial and was never saved.",
    nextStep: "Run the scan again. If saving fails a second time, send support the scan reference below.",
    retryAdvice: "This is a FixList-side fault rather than something about your site, so a new scan is worth trying now.",
  },
  worker_stalled: {
    title: "The scan stopped making progress",
    detail: "The scan stopped reporting progress and FixList closed it rather than publish a partial result. No partial FixList was promoted.",
    nextStep: "Run the scan again. If it stalls a second time, send support the scan reference below.",
    retryAdvice: "This is a FixList-side fault rather than something about your site, so a new scan is worth trying now.",
  },
  unknown_limited: {
    title: "This scan finished without enough evidence",
    detail: "FixList did not collect enough verified evidence to publish a result, and this run did not record a reason specific enough to explain which part fell short.",
    nextStep: "Run the scan again, and send support the scan reference below if the same thing happens.",
    retryAdvice: "Without a recorded reason there is nothing to fix first, so a new scan is the next thing to try.",
  },
  in_progress: {
    title: "This scan is still running",
    detail: "FixList is still working. This page refreshes automatically and will show your saved result as soon as it is ready.",
    nextStep: "Leave this page open, or come back to it from your scan history.",
    retryAdvice: "Starting a second scan of the same site now would compete with this one for the same time budget.",
  },
  cancelled: {
    title: "This scan was cancelled",
    detail: "This scan was stopped before it finished, so nothing was saved.",
    nextStep: "Run a fresh scan when you're ready.",
    retryAdvice: "Nothing about the site stopped this one, so a new scan can start whenever you want.",
  },
  no_results: {
    title: "No results saved for this scan",
    detail: "This scan finished with nothing saved against it, so there is no FixList to show.",
    nextStep: "Run a fresh scan to get an up-to-date FixList.",
    retryAdvice: "Nothing here says the site is at fault, so a new scan is worth running.",
  },
};

export function durableScanStatePresentation(record) {
  const source = plainObject(record);
  const status = cleanText(source.status);

  if (RUNNING_STATUSES.has(status)) return { kind: "in_progress", ...COPY.in_progress };
  if (status === "cancelled") return { kind: "cancelled", ...COPY.cancelled };
  if (status === "limited" || status === "failed") {
    const kind = durableScanLimitationKind(source);
    return { kind, ...COPY[kind] };
  }
  return { kind: "no_results", ...COPY.no_results };
}

/**
 * The scanner's own limitation sentence, published only if it is safe to.
 *
 * This is the one field carrying the concrete numbers -- "reviewed 38 of 3,689
 * discovered pages" -- that answer whether the saved evidence is worth
 * anything, and it is passed through rather than paraphrased, so it needs a
 * gate. The gate rejects; it does not sanitise. A value that trips any of these
 * is withheld whole, because a scrubbed sentence is one the scanner never wrote
 * and the reader has no way to tell it was edited.
 */
export const LIMITATION_MAX_LENGTH = 400;
export const UNSAFE_LIMITATION = Object.freeze([
  /[a-z][a-z0-9+.-]*:\/\/|(?:^|\s)\/\//i, // any URL, credentialed, schemeless or otherwise
  /\b[0-9a-f]{16,}\b/i,       // hex digests, signatures, ids
  /\bey[A-Za-z0-9_-]{8,}\./,  // a JWT
  /Traceback|File "|at [A-Za-z$_][\w.$<>]*\s*\(/,
  /\b\w*(Error|Exception)\b\s*[:(]/,
  /:\d+:\d+\)/,               // a stack frame position
  /\b[\w.-]+@[\w.-]+\.\w+\b/, // an address
  /\bBearer\b|\btoken\b|\bsecret\b|\bapi[_-]?key\b/i,
  /\bworker\b|\bcloud ?run\b|\brevision\b/i,
  /\b[a-z]+-[a-z]+\d\b/i,     // a deployment region, e.g. europe-west1
]);

export function customerSafeLimitationLine(record) {
  const limitation = cleanText(plainObject(record).limitation);
  if (!limitation) return "";
  if (limitation.length > LIMITATION_MAX_LENGTH) return "";
  if (UNSAFE_LIMITATION.some((pattern) => pattern.test(limitation))) return "";
  return limitation;
}
