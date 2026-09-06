"""A record of how the health score was reached, safe to show a customer.

`compute_health_score_breakdown()` has always known exactly where every point
went -- which area cost what, which ceilings bound the result -- and none of it
left the scanner. The page showed a number and a grade, and the number is the
first thing an owner argues with.

This module is a *record* of that score, not a second opinion about it. It
recomputes nothing. `final_score` is copied from the breakdown and moved only by
`apply_score_ceiling`, so a page can never show a breakdown that adds up to a
different number than the score printed above it.

Two things deliberately do not appear. `action_penalties` is keyed by rule
identity, which is internal vocabulary and would name findings the customer copy
has already translated; and the bucket keys themselves are the scorer's own
names, not areas an owner recognises.
"""

from __future__ import annotations

from typing import Any

HEALTH_SCORE_EXPLANATION_VERSION = "health_score_explanation_v1"

# The scorer's buckets in the vocabulary the rest of the customer surface
# already uses (src/lib/fixVocabulary.js CATEGORY_LABELS). A bucket absent from
# this map is not published: an unnamed area is one this build cannot describe,
# and printing its key is how classifier vocabulary reaches the page.
CUSTOMER_BUCKET_LABELS = {
    "search_visibility": "Search visibility",
    "site_structure": "Site navigation",
    "search_appearance": "Search appearance",
    "page_content": "Page content",
    "technical_quality": "Website setup",
}

# Why a ceiling bound the score, from a closed set. The reason is published, so
# an arbitrary string here is how a diagnostic message reaches the page through
# a field nobody was watching.
CEILING_REASONS = frozenset({
    "sample_size",
    "blocked_access",
    "incomplete_evidence",
    "no_pages_crawled",
    "other",
})

MAX_DEDUCTION_ROWS = len(CUSTOMER_BUCKET_LABELS)
STARTING_SCORE = 100


def _int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _customer_deductions(bucket_penalties: dict[str, Any], total: int) -> list[dict[str, Any]]:
    """Whole-number deductions that sum to exactly `total`.

    Bucket penalties are floats and the customer sees whole numbers. Rounding
    each row independently produces a column that does not add up to its own
    stated total, which is the first thing an owner checks. Largest-remainder
    apportionment keeps every row within a point of its true value and makes the
    column add up.
    """
    named = [
        (CUSTOMER_BUCKET_LABELS[bucket], float(penalty))
        for bucket, penalty in (bucket_penalties or {}).items()
        if bucket in CUSTOMER_BUCKET_LABELS and float(penalty or 0) > 0
    ]
    if not named or total <= 0:
        return []

    weight = sum(penalty for _, penalty in named)
    if weight <= 0:
        return []

    shares = [(label, penalty * total / weight) for label, penalty in named]
    rows = [{"category": label, "points": int(share)} for label, share in shares]
    remainder = total - sum(row["points"] for row in rows)
    # Hand the leftover points to the largest fractional parts, biggest first.
    order = sorted(
        range(len(shares)),
        key=lambda index: (shares[index][1] - int(shares[index][1]), shares[index][1]),
        reverse=True,
    )
    for index in order[:max(0, remainder)]:
        rows[index]["points"] += 1

    rows = [row for row in rows if row["points"] > 0]
    rows.sort(key=lambda row: (-row["points"], row["category"]))
    return rows[:MAX_DEDUCTION_ROWS]


def build_health_score_explanation(
    breakdown: dict[str, Any] | None,
    *,
    verification_findings_excluded: bool = False,
) -> dict[str, Any] | None:
    """Serialize a breakdown into the bounded customer-safe record, or None.

    None rather than a placeholder: an explanation of a score that does not
    exist is the same kind of overstatement as claiming coverage the crawl never
    had. A record with no explanation says so on the page.
    """
    if not isinstance(breakdown, dict):
        return None
    score = breakdown.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None

    final_score = _int(score)
    total_penalty = float(breakdown.get("total_penalty") or 0)
    # The deduction total is what the deductions add up to, never `100 - score`:
    # the floor and the ceilings move the score without deducting anything, and
    # attributing their effect to a bucket would blame the site for the limits
    # of the scan.
    total_deduction = max(0, min(STARTING_SCORE, _int(total_penalty)))
    deductions = _customer_deductions(breakdown.get("bucket_penalties") or {}, total_deduction)
    total_deduction = sum(row["points"] for row in deductions)

    coverage_ceiling = max(0, min(STARTING_SCORE, _int(breakdown.get("coverage_ceiling") or STARTING_SCORE)))
    # The scorer reports which limit actually bound the number, if any. Deriving
    # it here from the coverage ceiling alone would miss the blocked-access and
    # incomplete-evidence ceilings, which are the two a customer most needs to
    # see: they are the cases where a low score is about the scan, not the site.
    applied = _int(breakdown.get("applied_ceiling") or STARTING_SCORE)
    reason = str(breakdown.get("ceiling_reason") or "")
    ceiling_bound = 0 < applied < STARTING_SCORE and reason in CEILING_REASONS

    return {
        "version": HEALTH_SCORE_EXPLANATION_VERSION,
        "starting_score": STARTING_SCORE,
        "final_score": final_score,
        "total_deduction": total_deduction,
        "deductions": deductions,
        "coverage_ceiling": coverage_ceiling,
        "applied_ceiling": applied if ceiling_bound else STARTING_SCORE,
        "ceiling_reason": reason if ceiling_bound else "",
        # The floor is a calibration decision, not a finding. Declaring it is
        # what stops `100 - total_deduction` reading as broken arithmetic.
        "floor_applied": STARTING_SCORE - total_deduction < final_score and not ceiling_bound,
        "verification_findings_excluded": bool(verification_findings_excluded),
    }


def apply_score_ceiling(
    explanation: dict[str, Any] | None,
    ceiling: Any,
    reason: str,
) -> dict[str, Any] | None:
    """Move the explanation with a ceiling applied after it was built.

    The evidence-quality gate runs after calibration and can lower the stored
    score. An explanation sealed before that clamp would state a score the
    record does not hold, so every later ceiling has to come back through here.
    A ceiling that does not bind returns the explanation unchanged.
    """
    if not isinstance(explanation, dict):
        return None
    limit = _int(ceiling)
    if limit <= 0 or limit >= _int(explanation.get("final_score")):
        return explanation
    return {
        **explanation,
        "final_score": limit,
        "applied_ceiling": limit,
        "ceiling_reason": reason if reason in CEILING_REASONS else "other",
        # A ceiling decides the score, so the floor is no longer what set it.
        "floor_applied": False,
    }
