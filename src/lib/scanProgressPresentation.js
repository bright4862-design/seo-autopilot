export const SCAN_PROGRESS_PRESENTATION_VERSION = "scan_progress_presentation_v1_truthful_denominator";

const ACTIVE_STATES = new Set(["queued", "crawling", "reviewing"]);
const TERMINAL_STATES = new Set(["complete", "failed", "cancelled"]);

function clean(value = "") {
  return String(value || "").trim();
}

function finiteNonNegative(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function firstFinite(...values) {
  for (const value of values) {
    const parsed = finiteNonNegative(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function statusOf(scan = {}) {
  return clean(scan.status || scan.scan_status || scan.state).toLowerCase();
}

function pagesCheckedOf(scan = {}) {
  return firstFinite(
    scan.pages_crawled,
    scan.pages_checked,
    scan.pages_scanned,
    scan.scan_summary?.pages_crawled,
    scan.scan_summary?.pages_scanned,
    scan.technical_audit_summary?.pages_crawled,
  ) ?? 0;
}

function explicitFinalTotal(scan = {}) {
  const locked = scan.progress_total_locked === true
    || scan.progress_total_is_final === true
    || scan.crawl_timing?.progress_total_is_final === true;
  if (!locked) return null;
  return firstFinite(
    scan.progress_total,
    scan.final_page_target,
    scan.crawl_timing?.progress_total,
  );
}

function completedTotal(scan = {}, pagesChecked = 0) {
  if (statusOf(scan) !== "complete") return null;
  return firstFinite(
    scan.pages_crawled,
    scan.pages_checked,
    scan.pages_scanned,
    scan.scan_summary?.pages_crawled,
    scan.scan_summary?.pages_scanned,
    pagesChecked,
  );
}

function phaseLabel(status) {
  if (status === "queued") return "Finding pages…";
  if (status === "crawling") return "Finding and checking pages…";
  if (status === "reviewing") return "Building your FixList…";
  if (status === "complete") return "Scan complete";
  if (status === "failed") return "Scan stopped";
  if (status === "cancelled") return "Scan cancelled";
  return "Checking your website…";
}

/**
 * Build customer-facing scan progress without inventing a denominator.
 *
 * `pages_found`, the Standard 150 cap, queue length, and sitemap inventory are
 * deliberately NOT treated as a progress total. Discovery can continue while
 * crawling, and a site may legitimately finish well below 150 pages.
 *
 * A determinate percentage is emitted only when the backend explicitly marks a
 * total as final/locked, or once the scan itself is complete.
 */
export function scanProgressModel(scan = {}) {
  const status = statusOf(scan);
  const pagesChecked = pagesCheckedOf(scan);
  const explicitTotal = explicitFinalTotal(scan);
  const total = explicitTotal ?? completedTotal(scan, pagesChecked);
  const determinate = total !== null && total > 0;
  const boundedChecked = determinate ? Math.min(pagesChecked, total) : pagesChecked;
  const percent = determinate
    ? Math.max(0, Math.min(100, Math.round((boundedChecked / total) * 100)))
    : null;

  const active = ACTIVE_STATES.has(status);
  const terminal = TERMINAL_STATES.has(status);

  let countLabel = "";
  if (pagesChecked > 0 && determinate && status !== "reviewing") {
    countLabel = `${boundedChecked} of ${total} pages checked`;
  } else if (pagesChecked > 0) {
    countLabel = `${pagesChecked} ${pagesChecked === 1 ? "page" : "pages"} checked`;
  }

  return {
    version: SCAN_PROGRESS_PRESENTATION_VERSION,
    status,
    active,
    terminal,
    phaseLabel: phaseLabel(status),
    pagesChecked,
    totalPages: total,
    determinate,
    percent,
    countLabel,
    // Safe to show only when durable execution is explicitly confirmed by the
    // backend contract. Do not infer this from an active status alone.
    canLeavePage: scan.durable_background_execution === true,
  };
}
