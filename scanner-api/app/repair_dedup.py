"""Which repair cards survive: defect classes, group cards, and their duplicates.

Split out of review.py as the first increment of the recommended review/ package
(evidence -> rules -> aggregation -> prioritization -> projection). This cluster
earned isolation: both the Ike duplicate-card incident and the `mixed` family
collapse were defects in exactly these functions, and they now carry the tests
that pin them rather than sharing a 3 000-line module with everything else.

Layering: review_primitives (leaf) -> repair_coverage (evidence identity) ->
this module -> review. Nothing here imports review, so the dependency runs one
way only.
"""
from __future__ import annotations

import re
from typing import Any

from .repair_coverage import evidence_url_key
from .review_primitives import clean_path, dedupe_strings, has_any, int_or_zero

FAILURE_EVIDENCE_DEDUP_VERSION = "failure_evidence_dedup_v2_group_covered_page_rows"

GENERATOR_GROUP_SOURCES = ("page_pattern:", "scanner_verified_failed_pages:", "archetype_")

# Mirrors scanner.GROUP_MIN_AFFECTED, the threshold at which group_findings()
# collapses a rule into one template card. review.py deliberately does not
# import scanner, so the value is restated here and pinned by a contract test.
GROUP_CARD_MIN_AFFECTED = 3


def failure_remediation_family(fix: dict[str, Any]) -> str:
    """Canonical customer action for overlapping terminal crawl evidence."""
    rule = str(fix.get("rule") or "").lower()
    raw_statuses = list(fix.get("status_codes") or []) + [
        fix.get("status_code"),
        fix.get("http_status"),
    ]
    statuses = {int_or_zero(value) for value in raw_statuses if int_or_zero(value)}
    current = str(fix.get("current_value") or "").lower()
    if rule in {"rate_limited_page", "blocked_page", "site_access_limited"} or 429 in statuses:
        return "verify_crawler_access"
    if (
        rule == "server_error"
        or any(500 <= status <= 599 for status in statuses)
        or re.search(r"\b5(?:00|02|03|04)\b", current)
    ):
        return "restore_server_availability"
    if rule in {"broken_page", "404_error", "410_error", "failed_page"}:
        return "restore_or_redirect_unavailable_url"
    if rule == "redirect_destination_failed":
        return "repair_redirect_destination"
    return ""


def fix_dedup_class(fix: dict[str, Any]) -> str:
    remediation = failure_remediation_family(fix)
    if remediation:
        return remediation
    text = " ".join(str(fix.get(k, "")) for k in ["rule", "category", "issue_title", "title"]).lower()
    if "canonical" in text:
        return "canonical"
    if has_any(text, ["h1", "heading"]):
        return "h1"
    if has_any(text, ["alt text", "image_alt", "alt_text", "image description"]):
        return "image_alt"
    if has_any(text, ["meta description", "meta_description"]):
        return "meta_description"
    if has_any(text, ["schema", "structured data"]):
        return "schema"
    if has_any(text, ["429", "blocked", "rate limit"]):
        return "blocked_access"
    if has_any(text, ["404", "410", "500", "503", "5xx", "broken", "server error", "not found"]):
        return "broken_page"
    return str(fix.get("rule") or fix.get("category") or "general")


def suppress_duplicate_group_cards(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate grouped cards of the same defect with substantial page overlap."""

    def pages_of(fix: dict[str, Any]) -> set[str]:
        return {evidence_url_key(u) for u in (fix.get("affected_pages") or []) if evidence_url_key(u)}

    grouped = [fix for fix in fixes if len(pages_of(fix)) > 1]
    if len(grouped) < 2:
        return fixes

    def strength(fix: dict[str, Any]) -> tuple[int, int, int, int]:
        generator = 1 if str(fix.get("source", "")).startswith(GENERATOR_GROUP_SOURCES) else 0
        return (
            generator,
            len(pages_of(fix)),
            int_or_zero(fix.get("confidence_score")),
            int_or_zero(fix.get("overall_priority_score") or fix.get("overall_score") or fix.get("score")),
        )

    kept: list[dict[str, Any]] = []
    dropped: set[int] = set()
    for fix in sorted(grouped, key=strength, reverse=True):
        cls = fix_dedup_class(fix)
        pf = pages_of(fix)
        duplicate = False
        for keep in kept:
            if fix_dedup_class(keep) != cls:
                continue
            pk = pages_of(keep)
            overlap = len(pf & pk) / max(1, min(len(pf), len(pk)))
            if overlap >= 0.5:
                duplicate = True
                break
        if duplicate:
            dropped.add(id(fix))
        else:
            kept.append(fix)
    if not dropped:
        return fixes
    return [fix for fix in fixes if id(fix) not in dropped]


def suppress_group_covered_singletons(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop per-page fixes already covered by one of our grouped template/evidence cards of the same defect class."""

    def pages_of(fix: dict[str, Any]) -> list[str]:
        return dedupe_strings([evidence_url_key(u) for u in (fix.get("affected_pages") or []) if evidence_url_key(u)])

    def is_generator_group(fix: dict[str, Any]) -> bool:
        return str(fix.get("source", "")).startswith(GENERATOR_GROUP_SOURCES)

    def is_validated_group_card(fix: dict[str, Any]) -> bool:
        """A card that explicitly lists a template's worth of pages it repairs.

        `scanner.group_findings()` builds these by copying a member finding and
        blanking `page_url`, but it never stamps a generator source -- so the
        prefix test above cannot see them. That is how Ike's scan persisted one
        redirect_destination_noindex family card *and* ~27 page-scope rows for
        URLs that card already listed.

        Blank `page_url` is deliberately NOT the signal: `normalize_fix` runs
        first and backfills it from the first affected page, so by the time this
        sees the card its page_url is populated again. Explicit page coverage is
        the property that survives normalization.
        """
        if is_generator_group(fix):
            return False
        if not str(fix.get("rule") or "").strip():
            return False
        return len(pages_of(fix)) >= GROUP_CARD_MIN_AFFECTED

    covered: set[tuple[str, str]] = set()
    # Keyed on the exact rule rather than the remediation family, so a group of
    # one rule never suppresses a different rule that happens to share a family.
    rule_covered: set[tuple[str, str]] = set()
    for fix in fixes:
        # A generator card is authoritative for its pages regardless of how many were sampled.
        if is_generator_group(fix):
            cls = fix_dedup_class(fix)
            for page in pages_of(fix):
                covered.add((cls, page))
        elif is_validated_group_card(fix):
            rule = str(fix.get("rule")).strip()
            for page in pages_of(fix):
                rule_covered.add((rule, page))
    if not covered and not rule_covered:
        return fixes

    output = []
    for fix in fixes:
        if is_generator_group(fix) or is_validated_group_card(fix):
            output.append(fix)  # never suppress a group card
            continue
        pages = pages_of(fix)
        fallback = evidence_url_key(fix.get("page_url") or "")
        scope = pages or ([fallback] if fallback else [])
        if len(scope) <= 1:
            page = scope[0] if scope else ""
            if page and (fix_dedup_class(fix), page) in covered:
                continue  # non-generator singleton already covered by a generator card
        # Every page this row names is already listed by a group card for the
        # same exact rule, so the row duplicates that action. A row naming any
        # page the group does not list is a real outlier and survives.
        rule = str(fix.get("rule") or "").strip()
        if rule and scope and all((rule, page) in rule_covered for page in scope):
            continue
        output.append(fix)
    return output
