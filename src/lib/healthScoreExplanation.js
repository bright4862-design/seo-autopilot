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
const STAGE3_SCORE_CAP_VERSION = "stage3_health_score_caps_v1_verified_root_cause";
const STAGE3_COVERAGE_STATES = new Set(["sufficient", "limited_coverage", "inventory_unproven", "access_limited", "unknown"]);
const ROOT_CAUSE_CEILING_NOTE = "FixList verified that several issues share the same underlying cause, so the score is capped until that cause is fixed.";

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

function validNullableScore(value) {
  return value === null || (Number.isInteger(value) && value >= 0 && value <= 100);
}

function stage3ScoreDecision(value, finalScore) {
  if (value === undefined) return { present: false, value: null };
  const source = plainObject(value);
  if (
    source.version !== STAGE3_SCORE_CAP_VERSION
    || source.state !== "decided"
    || !Number.isInteger(source.base_health_score)
    || source.base_health_score < 0 || source.base_health_score > 100
    || !validNullableScore(source.existing_score_ceiling)
    || !validNullableScore(source.root_cause_score_ceiling)
    || !validNullableScore(source.effective_score_ceiling)
    || !Number.isInteger(source.adjusted_health_score)
    || source.adjusted_health_score < 0 || source.adjusted_health_score > 100
    || source.adjusted_health_score !== finalScore
    || !STAGE3_COVERAGE_STATES.has(source.coverage_state)
    || !Array.isArray(source.applied_root_cause_caps)
    || !Array.isArray(source.ignored_root_cause_caps)
  ) return { present: true, value: null };
  const ceilings = [source.existing_score_ceiling, source.root_cause_score_ceiling].filter((item) => item !== null);
  const expectedEffective = ceilings.length ? Math.min(...ceilings) : null;
  const expectedAdjusted = Math.min(source.base_health_score, expectedEffective ?? source.base_health_score);
  if (source.effective_score_ceiling !== expectedEffective || source.adjusted_health_score !== expectedAdjusted) {
    return { present: true, value: null };
  }
  const legacyScore = Math.min(source.base_health_score, source.existing_score_ceiling ?? source.base_health_score);
  return { present: true, value: { ...source, legacyScore } };
}

export function healthScoreExplanation(record) {
  const source = plainObject(record);
  const score = integer(source.health_score);
  const sealed = plainObject(source.health_score_explanation);
  const stage3 = stage3ScoreDecision(source.stage3_health_score_decision, score);
  if (stage3.present && !stage3.value) return UNAVAILABLE;
  const explanationScore = stage3.value ? stage3.value.legacyScore : score;

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
  if (score === null || integer(sealed.final_score) !== explanationScore) return UNAVAILABLE;

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
    && sealed.applied_ceiling <= explanationScore;
  const rootCauseCeilingApplied = Boolean(
    stage3.value
    && stage3.value.root_cause_score_ceiling !== null
    && stage3.value.effective_score_ceiling === stage3.value.root_cause_score_ceiling
    && (
      stage3.value.existing_score_ceiling === null
      || stage3.value.root_cause_score_ceiling < stage3.value.existing_score_ceiling
    )
  );

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
    ceilingNote: rootCauseCeilingApplied
      ? ROOT_CAUSE_CEILING_NOTE
      : (ceilingApplied ? (CEILING_NOTES[sealed.ceiling_reason] || "") : ""),
    floorNote: sealed.floor_applied === true
      ? "This is the lowest score FixList reports. The list below is what to work through, not a mark out of a hundred."
      : "",
    verificationExcluded: sealed.verification_findings_excluded === true,
  };
}