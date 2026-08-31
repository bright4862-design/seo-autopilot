// Release acceptance gates for the Standard 150 matrix.
//
// Nine sites in the focused matrix and fifty in the full one, each judged on
// four gates, is more than anyone reliably eyeballs. These evaluate one scan
// bundle -- the persisted ScanRun, its FixList and its FixItems -- and say
// exactly which gate failed and why.
//
// The thresholds and vocabularies are read from the scanner's own source
// rather than restated here. A second copy of "what counts as an asset" would
// drift from the filter that actually runs, and the acceptance gate would then
// be measuring something the product does not do.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), "utf8");

/** Every suffix the scanner's artifact filter treats as non-HTML. */
export function assetSuffixes() {
  const source = read("scanner-api/app/artifact_filter.py");
  const block = source.match(/_NON_HTML_RESOURCE_SUFFIXES = \(([\s\S]*?)\)/);
  if (!block) throw new Error("artifact_filter.py no longer declares _NON_HTML_RESOURCE_SUFFIXES");
  const suffixes = [...block[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  if (suffixes.length === 0) throw new Error("artifact filter suffix list is empty");
  return suffixes;
}

/** The affected-page count at which a card is authoritative for its pages. */
export function groupCardMinAffected() {
  const source = read("scanner-api/app/repair_dedup.py");
  const match = source.match(/GROUP_CARD_MIN_AFFECTED = (\d+)/);
  if (!match) throw new Error("repair_dedup.py no longer declares GROUP_CARD_MIN_AFFECTED");
  return Number(match[1]);
}

/** The release identity this checkout freezes. */
export function expectedFingerprint() {
  return String(JSON.parse(read("data/beta-crawler-revision.json")).fingerprint || "");
}

const text = (value) => (typeof value === "string" ? value.trim() : "");
const lower = (value) => text(value).toLowerCase();
const pagesOf = (fix) => (Array.isArray(fix?.affected_pages) ? fix.affected_pages.map(text).filter(Boolean) : []);

/** A URL whose path ends in a non-HTML suffix is an asset, not a page. */
export function isAssetUrl(url, suffixes = assetSuffixes()) {
  const raw = text(url);
  if (!raw) return false;
  let pathname = raw;
  try {
    pathname = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).pathname;
  } catch {
    // A value that will not parse cannot be shown to be a page either; fall
    // back to matching the raw string so a malformed asset URL is still caught.
  }
  const lowered = pathname.toLowerCase().replace(/\/+$/, "");
  return suffixes.some((suffix) => lowered.endsWith(suffix));
}

/**
 * A scan whose evidence was materially limited by the site, not by the
 * scanner. These are reported, but excluded from classification accuracy: a
 * site that blocked the crawl cannot fairly count against the classifier.
 */
export function isAccessLimited(scanRun) {
  const status = lower(scanRun?.status);
  if (status === "limited") return true;
  const confidence = lower(scanRun?.review_confidence_state);
  const quality = lower(scanRun?.evidence_quality_state);
  return confidence.includes("blocked") || quality === "blocked" || quality === "blocking";
}

function infrastructureGate({ scanRun, fixList, fixItems }, fingerprint) {
  const failures = [];
  const status = lower(scanRun?.status);
  const crawled = Number(scanRun?.pages_crawled);

  if (!text(scanRun?.id)) failures.push("ScanRun has no id");
  if (!text(scanRun?.fix_list_id)) failures.push("ScanRun carries no fix_list_id");
  if (!text(fixList?.id)) failures.push("FixList has no id");
  if (text(fixList?.id) && text(scanRun?.fix_list_id) && text(fixList.id) !== text(scanRun.fix_list_id)) {
    failures.push(`ScanRun points at FixList ${text(scanRun.fix_list_id)} but the bundle carries ${text(fixList.id)}`);
  }
  if (!Number.isFinite(crawled) || crawled <= 0) failures.push("pages_crawled is not a positive number");
  else if (crawled > 150) failures.push(`pages_crawled ${crawled} exceeds the Standard 150 cap`);

  // A fallback presented as an authoritative result is a release blocker in its
  // own right, so each of the four markers is checked rather than inferred.
  if (scanRun?.deno_fallback_used === true) failures.push("Deno fallback was used");
  if (scanRun?.python_review_fallback_used === true) failures.push("Python review fallback was used");
  if (text(scanRun?.advanced_scan_backend) !== "python_scanner_api") {
    failures.push(`advanced_scan_backend is ${text(scanRun?.advanced_scan_backend) || "(unset)"}`);
  }
  if (text(scanRun?.ai_review_backend) !== "python_review_api") {
    failures.push(`ai_review_backend is ${text(scanRun?.ai_review_backend) || "(unset)"}`);
  }

  const runFingerprint = text(scanRun?.beta_revision_fingerprint);
  if (runFingerprint !== fingerprint) {
    failures.push(`fingerprint ${runFingerprint || "(absent)"} is not the frozen ${fingerprint}`);
  }

  if (status !== "complete" && status !== "limited") failures.push(`status is ${status || "(unset)"}`);
  if (status === "complete") {
    if (!/^[0-9a-f]{64}$/.test(lower(scanRun?.authority_proof))) failures.push("no valid authority proof was persisted");
    if (!text(scanRun?.authority_sealed_at)) failures.push("authority_sealed_at is empty");
    if (!Array.isArray(fixItems)) failures.push("no FixItems were persisted");
  }
  return { pass: failures.length === 0, failures };
}

function classificationGate({ scanRun }, expected) {
  const failures = [];
  const limited = isAccessLimited(scanRun);
  const actual = text(scanRun?.primary_archetype || scanRun?.archetype || scanRun?.site_archetype);
  const wanted = text(expected?.archetype);

  if (!text(scanRun?.archetype_classifier_version)) failures.push("no archetype classifier version was recorded");
  if (limited) {
    // Excluded from accuracy, but it still has to say so rather than assert a
    // confident archetype it could not have earned.
    return { pass: failures.length === 0, failures, excluded: true, reason: "access-limited" };
  }
  if (wanted) {
    if (!actual) failures.push(`expected archetype ${wanted} but none was recorded`);
    else if (actual.toLowerCase() !== wanted.toLowerCase()) failures.push(`archetype ${actual} is not the expected ${wanted}`);
  }
  return { pass: failures.length === 0, failures, excluded: false };
}

function evidenceGate({ fixItems }, suffixes, minAffected) {
  const failures = [];
  const items = Array.isArray(fixItems) ? fixItems : [];

  for (const fix of items) {
    const id = text(fix?.fix_id) || "(unnamed fix)";
    const pages = pagesOf(fix);
    const primary = text(fix?.page_url);

    if (primary && isAssetUrl(primary, suffixes)) failures.push(`${id} is anchored on an asset URL: ${primary}`);
    const assetPages = pages.filter((page) => isAssetUrl(page, suffixes));
    if (assetPages.length > 0) failures.push(`${id} names ${assetPages.length} asset URL(s), e.g. ${assetPages[0]}`);
    if (pages.length === 0 && !primary) failures.push(`${id} names no affected page at all`);

    // A stated count that does not match the URLs shown is the shape a
    // customer cannot verify, and the shape a truncated list produces.
    const declared = Number(fix?.page_count ?? fix?.affected_page_count);
    if (Number.isFinite(declared) && pages.length > 0 && fix?.affected_pages_complete !== false && declared !== pages.length) {
      failures.push(`${id} claims ${declared} affected pages but lists ${pages.length}`);
    }
  }

  // The duplicate-card regression: a page-scope row for a rule that a grouped
  // card of the same rule already covers.
  const covered = new Map();
  for (const fix of items) {
    const rule = text(fix?.rule);
    const pages = pagesOf(fix);
    if (!rule || pages.length < minAffected) continue;
    if (!covered.has(rule)) covered.set(rule, new Set());
    for (const page of pages) covered.get(rule).add(page);
  }
  for (const fix of items) {
    const rule = text(fix?.rule);
    const pages = pagesOf(fix);
    if (!rule || pages.length === 0 || pages.length >= minAffected) continue;
    const group = covered.get(rule);
    if (group && pages.every((page) => group.has(page))) {
      failures.push(`${text(fix?.fix_id) || "(unnamed fix)"} repeats rule ${rule} for pages a grouped card already covers`);
    }
  }
  return { pass: failures.length === 0, failures };
}

function authorityGate({ scanRun }, fingerprint) {
  const failures = [];
  const eligible = scanRun?.release_gate_eligible === true;
  const status = lower(scanRun?.status);
  const limited = isAccessLimited(scanRun);
  const fingerprintMatches = text(scanRun?.beta_revision_fingerprint) === fingerprint;

  if (eligible && !fingerprintMatches) failures.push("release_gate_eligible is true under a fingerprint that does not match the freeze");
  if (eligible && status !== "complete") failures.push(`release_gate_eligible is true on a ${status || "(unset)"} scan`);
  if (eligible && limited) failures.push("an access-limited scan claims release-gate eligibility");
  if (eligible && scanRun?.score_is_provisional === true) failures.push("a provisional score claims release-gate eligibility");
  if (eligible && scanRun?.evidence_quality_blocking === true) failures.push("evidence quality is blocking but the scan claims eligibility");
  if (limited && scanRun?.score_is_provisional !== true) failures.push("an access-limited scan does not mark its score provisional");
  return { pass: failures.length === 0, failures };
}

/** Judge one scan bundle against all four release gates. */
export function evaluateScan(bundle, options = {}) {
  const fingerprint = options.fingerprint || expectedFingerprint();
  const suffixes = options.assetSuffixes || assetSuffixes();
  const minAffected = options.groupCardMinAffected || groupCardMinAffected();

  const gates = {
    infrastructure: infrastructureGate(bundle, fingerprint),
    classification: classificationGate(bundle, options.expected),
    evidence: evidenceGate(bundle, suffixes, minAffected),
    authority: authorityGate(bundle, fingerprint),
  };
  return {
    site: text(options.site) || text(bundle?.scanRun?.website_url) || "(unnamed site)",
    accessLimited: isAccessLimited(bundle?.scanRun),
    gates,
    pass: Object.values(gates).every((gate) => gate.pass),
  };
}

/**
 * Roll the matrix up the way the release gates are actually stated:
 * infrastructure success and classification accuracy are separate numbers, and
 * blocked sites are listed rather than folded into either.
 */
export function summarizeMatrix(results) {
  const total = results.length;
  const infrastructurePassed = results.filter((r) => r.gates.infrastructure.pass).length;
  const conclusive = results.filter((r) => !r.gates.classification.excluded);
  const classificationPassed = conclusive.filter((r) => r.gates.classification.pass).length;
  const assetFindings = results.filter((r) => r.gates.evidence.failures.some((f) => f.includes("asset URL"))).length;
  const duplicateCards = results.filter((r) => r.gates.evidence.failures.some((f) => f.includes("grouped card already covers"))).length;
  const fallbackAuthoritative = results.filter((r) =>
    r.gates.infrastructure.failures.some((f) => f.includes("fallback")) && r.gates.authority.pass === false,
  ).length;

  const infrastructureRate = total === 0 ? 0 : infrastructurePassed / total;
  const classificationRate = conclusive.length === 0 ? 0 : classificationPassed / conclusive.length;
  return {
    total,
    infrastructurePassed,
    infrastructureRate,
    conclusive: conclusive.length,
    classificationPassed,
    classificationRate,
    blocked: results.filter((r) => r.accessLimited).map((r) => r.site),
    assetFindings,
    duplicateCards,
    fallbackAuthoritative,
    // The beta gates, as stated in the release plan.
    betaGatesMet:
      infrastructureRate >= 0.9
      && classificationRate >= 0.85
      && assetFindings === 0
      && duplicateCards === 0
      && fallbackAuthoritative === 0,
  };
}

export function formatReport(results, summary) {
  const lines = [];
  for (const result of results) {
    lines.push(`${result.pass ? "PASS" : "FAIL"}  ${result.site}${result.accessLimited ? "  [access-limited]" : ""}`);
    for (const [name, gate] of Object.entries(result.gates)) {
      for (const failure of gate.failures) lines.push(`        ${name}: ${failure}`);
    }
  }
  lines.push("");
  lines.push(`infrastructure: ${summary.infrastructurePassed}/${summary.total} (${(summary.infrastructureRate * 100).toFixed(1)}%, gate 90%)`);
  lines.push(`classification: ${summary.classificationPassed}/${summary.conclusive} conclusive (${(summary.classificationRate * 100).toFixed(1)}%, gate 85%)`);
  lines.push(`asset findings: ${summary.assetFindings}   duplicate cards: ${summary.duplicateCards}   fallback-as-authoritative: ${summary.fallbackAuthoritative}`);
  if (summary.blocked.length > 0) lines.push(`blocked / inconclusive (excluded from accuracy): ${summary.blocked.join(", ")}`);
  lines.push(summary.betaGatesMet ? "BETA GATES MET" : "BETA GATES NOT MET");
  return lines.join("\n");
}

// CLI: one JSON file holding either a bundle or an array of {site, expected, ...bundle}.
if (import.meta.url === `file://${process.argv[1]}`) {
  const target = process.argv[2];
  if (!target) {
    console.error("usage: node scripts/acceptance-gates.mjs <matrix.json>");
    process.exit(2);
  }
  const payload = JSON.parse(fs.readFileSync(target, "utf8"));
  const entries = Array.isArray(payload) ? payload : [payload];
  const results = entries.map((entry) => evaluateScan(entry, { site: entry.site, expected: entry.expected }));
  const summary = summarizeMatrix(results);
  console.log(formatReport(results, summary));
  process.exit(summary.betaGatesMet && results.every((r) => r.pass) ? 0 : 1);
}
