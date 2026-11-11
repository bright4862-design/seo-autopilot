"""Deterministic pre-fetch importance; scores are scheduling hints, not evidence."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from .market_scope import strip_market_locale_prefix

PAGE_IMPORTANCE_VERSION = "page_importance_v1_observed_navigation_sections"


def _segments(path: str) -> list[str]:
    clean = str(path or "/").split("?", 1)[0].split("#", 1)[0]
    return [part for part in strip_market_locale_prefix(clean).split("/") if part]


def build_page_importance(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    homepage_links: Iterable[str] = (),
    lastmod: Mapping[str, str] | None = None,
    observed_inlinks: Mapping[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, dict]:
    """Rank every inventory URL using bounded, explainable local signals.

    Uniform sitemap dates carry no recency information. Dates are compared by
    UTC day so ordering does not drift between calls within the same scan day.
    Only observed links belong in ``homepage_links`` and ``observed_inlinks``.
    """
    from .sampling import HUB_ROLES, MONEY_FAMILIES, selection_role

    urls = sorted(set(urls))
    navigation = set(homepage_links)
    inlinks = observed_inlinks or {}
    parts = {url: _segments(path_of(url)) for url in urls}
    descendants: Counter[tuple[str, ...]] = Counter()
    for segments in parts.values():
        for end in range(1, len(segments)):
            descendants[tuple(segments[:end])] += 1
    max_descendants = max(descendants.values(), default=0)
    max_inlinks = max((max(0, int(value)) for value in inlinks.values()), default=0)
    dates: dict[str, datetime] = {}
    for url, value in (lastmod or {}).items():
        if url not in parts:
            continue
        try:
            date = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            dates[url] = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
    informative_dates = len({value.date() for value in dates.values()}) > 1
    today = (now or datetime.now(timezone.utc)).date()
    output = {}
    for url in urls:
        segments = parts[url]
        family = family_of(url)
        role = selection_role(path_of(url), family)
        role_prior = 1.0 if role in MONEY_FAMILIES else 0.8 if role in HUB_ROLES else 0.5 if family in {"guide_article", "blog_article", "article", "archive"} else 0.1
        child_count = descendants[tuple(segments)]
        parent = math.log1p(child_count) / math.log1p(max_descendants) if max_descendants else 0.0
        depth = 1.0 / max(1, len(segments))
        incoming = max(0, int(inlinks.get(url, 0)))
        observed = math.log1p(incoming) / math.log1p(max_inlinks) if max_inlinks else 0.0
        recency = 0.0
        if informative_dates and url in dates:
            age = (today - dates[url].date()).days
            # Future timestamps are not proof of maintenance.
            recency = max(0.0, 1.0 - age / 365.0) if age >= 0 else 0.0
        linked = url in navigation
        score = 0.30 * linked + 0.20 * parent + 0.15 * depth + 0.20 * role_prior + 0.05 * recency + 0.10 * observed
        if not segments:
            score, reason = 1.0, "Homepage"
        elif linked:
            reason = "Linked from your homepage"
        elif child_count:
            reason = "Main page of a section"
        elif role in HUB_ROLES:
            reason = "Main business page"
        else:
            reason = "Example of a repeated page type"
        output[url] = {
            "importance_score": round(min(1.0, max(0.0, score)), 6),
            "importance_tier": "critical" if score >= 0.5 else "high" if score >= 0.3 else "standard",
            "selection_reason": reason,
            "signals": {"homepage_link": linked, "descendant_count": child_count, "path_depth": len(segments), "role_prior": role_prior, "lastmod_informative": informative_dates, "observed_inlinks": incoming},
        }
    return output
