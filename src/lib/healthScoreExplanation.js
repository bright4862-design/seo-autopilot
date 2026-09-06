export const HEALTH_SCORE_EXPLANATION_VERSION = "health_score_explanation_v1";

/**
 * The persisted score breakdown, read back for display.
 *
 * FixList showed a number and a grade and nothing else, and the number is the
 * first thing an owner argues with -- particularly a low one on a site whose
 * only real findings are image descriptions. The scanner has always recorded
 * exactly where every point went; it never left the scanner.
 *
 * This reader's job is narrow on purpose: show what was persisted, and refuse
 * anything that does not add up. It derives nothing. A browser that can
 * recompute the score can also disagree with it, and then the page is arguing
 * with itself in front of the customer -- so a breakdown that contradicts the
 * stored score is withheld whole rather than shown next to it.
 */

// The scanner's own customer-facing area names. An allowlist rather than a
// passthrough: these strings are rendered verbatim, so this is what stops a
// bucket key or a diagnostic string reaching the page through a field nobody
// is watching.
const KNOWN_CATEGORIES = new Set([
  "Search visibility",
  "Site navigation",
  "Search appearance",
  "Page content",
  "Website setup",
]);

/**
 * What a ceiling means, in the customer's terms.
 *
 * Each of these describes what the scan could see, not how good the site is.
 * That distinction is the whole point of showing them: a low score from a
 * blocked crawl is a statement about access, and reads as a verdict on the
 * business unless it says otherwise.
 */
const CEILING_NOTES = Object.freeze({
  sample_size: "This scan checked a sample of the site, so the pages we checked set the highest score it can report.",
  blocked_access: "The site limited automated access during this scan, so the score is capped — a scan that sees less finds less.",
  incomplete_evidence: "This scan could not gather enough evidence to rate the site fully, so the score is capped.",
  no_pages_crawled: "No pages were checked in this scan, so the score is capped.",
});

const MAX_VISIBLE_DEDUCTIONS = 4;

const UNAVAILABLE = Object.freeze({
  available: false,
  legacy: false,
  legacyNote: "",
  finalScore: null,
  totalDeduction: 0,
  deductions: [],
  remainingDeduction: 0,
  ceilingNote: "",
  floorNote: "",
  verificationExcluded: false,
});

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function integer(value) {
  return Number.isInteger(value) ? value : null;
}

export function healthScoreExplanation(record) {
  const source = plainObject(record);
  const score = integer(source.health_score);
  const sealed = plainObject(source.health_score_explanation);

  if (!sealed.version) {
    // Two different silences, and they read differently on the page: a scan
    // that predates the breakdown, and one that was never scored at all. A
    // current row may intentionally persist an empty explanation object; field
    // presence distinguishes that from a genuinely legacy record.
    const legacy = source.health_score_explanation === undefined;
    return score === null || !legacy ? UNAVAILABLE : {
      ...UNAVAILABLE,
      legacy: true,
      legacyNote: "This older result does not include a score breakdown.",
    };
  }
  if (sealed.version !== HEALTH_SCORE_EXPLANATION_VERSION) return UNAVAILABLE;
  if (score === null || integer(sealed.final_score) !== score) return UNAVAILABLE;

  const rows = Array.isArray(sealed.deductions) ? sealed.deductions : [];
  const deductions = rows
    .filter((row) => KNOWN_CATEGORIES.has(plainObject(row).category) && integer(plainObject(row).points) > 0)
    .map((row) => ({ category: row.category, points: row.points }));
  const total = integer(sealed.total_deduction);
  // Refused whole rather than shortened: a row dropped for an unrecognised
  // category leaves a breakdown that is missing points, and a breakdown with
  // missing points is not a breakdown.
  if (total === null || deductions.length !== rows.length) return UNAVAILABLE;
  if (deductions.reduce((sum, row) => sum + row.points, 0) !== total) return UNAVAILABLE;

  const visible = deductions.slice(0, MAX_VISIBLE_DEDUCTIONS);
  const ceilingApplied = integer(sealed.applied_ceiling) !== null
    && sealed.applied_ceiling < 100
    && sealed.applied_ceiling <= score;

  return {
    available: true,
    legacy: false,
    legacyNote: "",
    finalScore: score,
    totalDeduction: total,
    deductions: visible,
    // The points below the fold are still accounted for, so the column adds up
    // whether or not a reader opens the rest.
    remainingDeduction: total - visible.reduce((sum, row) => sum + row.points, 0),
    ceilingNote: ceilingApplied ? (CEILING_NOTES[sealed.ceiling_reason] || "") : "",
    floorNote: sealed.floor_applied === true
      ? "This is the lowest score FixList reports. The list below is what to work through, not a mark out of a hundred."
      : "",
    verificationExcluded: sealed.verification_findings_excluded === true,
  };
}