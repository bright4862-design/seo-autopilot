const LEGACY_PAGE_CAPS = Object.freeze({ basic: 25, quick: 40, deep: 85, advanced: 150, standard_150: 150, standard_500: 500 });

// This formats an authenticated record; it never authorizes or submits a cap.
export function pageCapFromRecord(record = {}) {
  if (Number.isInteger(record?.page_cap) && [150, 500].includes(record.page_cap)) return record.page_cap;
  return LEGACY_PAGE_CAPS[String(record?.scan_mode || "").toLowerCase()] || 150;
}

export function confirmedScanPageLimit(record = {}) {
  if (record?.page_cap === 150 || record?.page_cap === 500) return record.page_cap;
  const legacyCap = LEGACY_PAGE_CAPS[String(record?.scan_mode || "").toLowerCase()];
  return Number.isInteger(legacyCap) && legacyCap !== 500 ? legacyCap : null;
}

export function inventoryCoverageLine(record = {}) {
  const checked = Math.max(0, Math.trunc(Number(record.pages_crawled || record.pages_scanned) || 0));
  const found = Math.max(checked, Math.trunc(Number(record.pages_found) || 0));
  const capped = record.inventory_capped === true || record.sitemap_diagnostics?.inventory_capped === true
    || record.sampling_evidence?.inventory_capped === true;
  const number = value => value.toLocaleString("en-US");
  return `We checked ${number(checked)} ${checked === 1 ? "page" : "pages"} out of ${capped ? "at least " : ""}${number(found)} found.`;
}

export function savedReportCoverageNote(record = {}, { checked, found } = {}) {
  if (record.status !== "complete" || record.authority_verified !== true || !Number.isSafeInteger(checked) || checked < 1) {
    return "";
  }
  const pageLimit = confirmedScanPageLimit(record);
  if (record.crawl_stop_reason === "time_limit" && (pageLimit === null || checked < pageLimit)) {
    return "The crawl reached its time limit, so this saved report covers the pages checked.";
  }
  if (Number.isSafeInteger(found) && found > checked) {
    return "This saved report covers only the pages FixList checked.";
  }
  return "";
}

export function optionalChecksNotice(record = {}) {
  if (record.status !== "complete" || record.authority_verified !== true) return "";
  if (record.optional_checks_notice_reason === "site_rate_limited") {
    return "The site limited automated requests, so some follow-up checks could not be verified.";
  }
  if (record.optional_checks_notice_reason === "repeat_requests_avoided") {
    return "FixList skipped some follow-up checks to avoid sending the site repeat requests.";
  }
  return "";
}

// Ranking, diversity and owner suitability are decided by the server. If its
// shortlist cannot be mapped exactly, retain the existing complete list.
export function serverSelectedPriorityCards(cards = [], ids) {
  if (!Array.isArray(ids) || ids.length < 1 || ids.length > 3 || new Set(ids).size !== ids.length) return null;
  const first = [];
  for (const id of ids) {
    if (typeof id !== "string" || !id) return null;
    const matches = cards.filter(card => card.fixId === id || (card.evidence?.mergedFromFixIds || []).includes(id));
    if (matches.length !== 1 || first.includes(matches[0])) return null;
    first.push(matches[0]);
  }
  return { first, remaining: cards.filter(card => !first.includes(card)) };
}
