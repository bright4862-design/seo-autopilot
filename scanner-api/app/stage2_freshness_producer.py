from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timezone
from typing import Any

from .page_evidence_gate import page_has_usable_html
from .stage2_coverage_evidence import FRESHNESS_VERSION, assess_contextual_freshness


FRESHNESS_PRODUCER_VERSION = "contextual_freshness_producer_v1_explicit_current_scope"
MAX_INTENT_EVIDENCE = 4
MAX_TEMPORAL_EVIDENCE = 8

_EXPLICIT_CURRENT = re.compile(
    r"\b(?:current|currently|latest|today(?:'s)?|this\s+(?:week|month|year)|up[- ]to[- ]date|now)\b",
    re.I,
)
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])(?!\d)")
_MONTH_YEAR = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d{2})\b",
    re.I,
)
_MONTHS = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if index and name
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _temporal_anchors(text: str, *, scope: str, source: str) -> list[dict[str, Any]]:
    """Return bounded conservative dates from one already-extracted visible field.

    Year-only anchors use 31 December of that year. That is deliberately the
    latest possible date represented by the token, so a stale verdict cannot be
    caused merely by treating an unknown month as January.
    """
    value = _clean(text)
    if not value:
        return []

    rows: list[dict[str, Any]] = []
    consumed_years: set[str] = set()
    for match in _ISO_DATE.finditer(value):
        stamp = _safe_iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if not stamp:
            continue
        consumed_years.add(match.group(1))
        rows.append({
            "date": stamp,
            "scope": scope,
            "source": source,
            "precision": "day",
        })

    for match in _MONTH_YEAR.finditer(value):
        year = int(match.group(2))
        month = _MONTHS.get(match.group(1).lower())
        if not month:
            continue
        consumed_years.add(match.group(2))
        rows.append({
            "date": date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
            "scope": scope,
            "source": source,
            "precision": "month",
        })

    for match in _YEAR.finditer(value):
        if match.group(1) in consumed_years:
            continue
        year = int(match.group(1))
        rows.append({
            "date": date(year, 12, 31).isoformat(),
            "scope": scope,
            "source": source,
            "precision": "year",
        })

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (str(row["date"]), str(row["scope"]), str(row["source"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= MAX_TEMPORAL_EVIDENCE:
            break
    return deduped


def build_contextual_freshness_page_evidence(
    page: dict[str, Any],
    *,
    as_of: date,
) -> dict[str, Any]:
    """Produce B15 evidence only from accepted, already-extracted page fields.

    Old years are retained as historical anchors but cannot become a freshness
    defect unless the same visible field explicitly claims current/latest/today
    intent. URL years remain historical context and are never promoted to a
    current-scope contradiction by themselves.
    """
    if not isinstance(page, dict) or not page_has_usable_html(page):
        assessment = {
            "version": FRESHNESS_VERSION,
            "state": "not_verified",
            "reason": "accepted_html_unavailable",
        }
        return {
            "producer_version": FRESHNESS_PRODUCER_VERSION,
            "current_content_intent": "",
            "current_content_intent_evidence": [],
            "temporal_evidence": [],
            "assessment": assessment,
        }

    fields = [
        ("title", _clean(page.get("title"))),
        ("h1", _clean(page.get("h1"))),
        ("meta_description", _clean(page.get("meta_description"))),
    ]
    intent_rows: list[str] = []
    temporal_rows: list[dict[str, Any]] = []

    for source, value in fields:
        if not value:
            continue
        marker = _EXPLICIT_CURRENT.search(value)
        scope = "current" if marker else "historical"
        if marker and len(intent_rows) < MAX_INTENT_EVIDENCE:
            intent_rows.append(f"{source}:{marker.group(0).lower()}")
        temporal_rows.extend(_temporal_anchors(value, scope=scope, source=source))

    # A dated path is useful provenance, but by design it is historical scope.
    # `/rates/2022/` cannot make a current page stale unless accepted visible
    # content independently establishes current intent and a current-scoped date.
    temporal_rows.extend(
        _temporal_anchors(_clean(page.get("path")), scope="historical", source="path")
    )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in temporal_rows:
        key = (str(row.get("date")), str(row.get("scope")), str(row.get("source")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= MAX_TEMPORAL_EVIDENCE:
            break

    current_intent = "explicit_current_language" if intent_rows else ""
    assessment_input = {
        "current_content_intent": current_intent,
        "current_content_intent_evidence": intent_rows,
        "temporal_evidence": deduped,
    }
    assessment = assess_contextual_freshness(assessment_input, as_of=as_of)
    return {
        "producer_version": FRESHNESS_PRODUCER_VERSION,
        **assessment_input,
        "assessment": assessment,
    }


def enrich_pages_with_contextual_freshness_evidence(
    pages: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> None:
    """Attach bounded B15 evidence to retained page objects in-place."""
    observed_on = as_of or datetime.now(timezone.utc).date()
    for page in pages:
        if not isinstance(page, dict):
            continue
        page["contextual_freshness_evidence"] = build_contextual_freshness_page_evidence(
            page,
            as_of=observed_on,
        )
