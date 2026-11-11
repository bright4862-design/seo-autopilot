const LEGACY_PAGE_CAPS = Object.freeze({ basic: 25, quick: 40, deep: 85, advanced: 150, standard_150: 150, standard_500: 500 });

// This formats an authenticated record; it never authorizes or submits a cap.
export function pageCapFromRecord(record = {}) {
  if (Number.isInteger(record?.page_cap) && [150, 500].includes(record.page_cap)) return record.page_cap;
  return LEGACY_PAGE_CAPS[String(record?.scan_mode || "").toLowerCase()] || 150;
}

export function inventoryCoverageLine(record = {}) {
  const checked = Math.max(0, Math.trunc(Number(record.pages_crawled || record.pages_scanned) || 0));
  const found = Math.max(checked, Math.trunc(Number(record.pages_found) || 0));
  const capped = record.inventory_capped === true || record.sitemap_diagnostics?.inventory_capped === true
    || record.sampling_evidence?.inventory_capped === true;
  const number = value => value.toLocaleString("en-US");
  return `We checked ${number(checked)} ${checked === 1 ? "page" : "pages"} out of ${capped ? "at least " : ""}${number(found)} found.`;
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
