from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Any
from urllib.parse import urlparse

REPAIR_ARCHITECTURE_PRIORITY_VERSION = "repair_architecture_priority_v1_role_coverage"

STRUCTURAL_FAMILIES = {
    "homepage",
    "collection_page",
    "location_landing",
    "comparison_page",
}

BUSINESS_CRITICAL_FAMILIES = {
    "calculator",
    "conversion",
    "booking_or_checkout",
    "loan_program",
    "pricing_page",
}

COMMERCIAL_LEAF_FAMILIES = {
    "activity_detail",
    "product_page",
    "product_detail",
}

SUPPORT_FAMILIES = {
    "guide_article",
    "article",
    "standard",
    "trust",
    "help",
}


@dataclass(frozen=True)
class RoleCounts:
    structural: int = 0
    business_critical: int = 0
    commercial_leaf: int = 0
    support: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        return (
            self.structural
            + self.business_critical
            + self.commercial_leaf
            + self.support
            + self.other
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "structural": self.structural,
            "business_critical": self.business_critical,
            "commercial_leaf": self.commercial_leaf,
            "support": self.support,
            "other": self.other,
        }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _path(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        parsed = urlparse(
            raw
            if "://" in raw
            else f"https://fixlist.invalid{raw if raw.startswith('/') else '/' + raw}"
        )
        path = parsed.path or "/"
        return path.rstrip("/") or "/"
    except Exception:
        return raw.rstrip("/") or "/"


def _page_url(page: dict[str, Any]) -> str:
    return _clean(
        page.get("url")
        or page.get("final_url")
        or page.get("page_url")
        or page.get("path")
    )


def _template_family(page: dict[str, Any]) -> str:
    return _lower(page.get("page_template_family") or page.get("template_family"))


def _fix_family(fix: dict[str, Any]) -> str:
    return _lower(fix.get("page_template_family") or fix.get("template_family"))


def _affected_paths(fix: dict[str, Any]) -> list[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not values:
        fallback = fix.get("page_url") or fix.get("representative_page_url")
        values = [fallback] if fallback else []

    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        key = _path(raw)
        if key and key not in seen:
            seen.add(key)
            output.append(key)
    return output


def page_role(page: dict[str, Any]) -> str:
    family = _template_family(page)
    path = _path(_page_url(page))

    if path in {"/", "/index.html"} or family == "homepage":
        return "structural"
    if family in STRUCTURAL_FAMILIES:
        return "structural"
    if family in BUSINESS_CRITICAL_FAMILIES:
        return "business_critical"
    if family in COMMERCIAL_LEAF_FAMILIES:
        return "commercial_leaf"
    if family in SUPPORT_FAMILIES:
        return "support"
    return "other"


def role_counts_for_affected(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
) -> RoleCounts:
    page_lookup = {
        _path(_page_url(page)): page
        for page in pages or []
        if isinstance(page, dict) and _path(_page_url(page))
    }
    fix_family = _fix_family(fix)
    counts = {
        "structural": 0,
        "business_critical": 0,
        "commercial_leaf": 0,
        "support": 0,
        "other": 0,
    }

    for key in _affected_paths(fix):
        page = page_lookup.get(key)
        if page is None:
            page = {"path": key, "page_template_family": fix_family}
        counts[page_role(page)] += 1

    return RoleCounts(**counts)


def bounded_role_bonus(counts: RoleCounts) -> int:
    """Reward distinct high-value roles while saturating repeated leaf volume."""
    structural = (
        0
        if counts.structural == 0
        else min(24, 16 + 4 * (counts.structural - 1))
    )
    business_critical = (
        0
        if counts.business_critical == 0
        else min(24, 16 + 4 * (counts.business_critical - 1))
    )
    leaves = (
        0
        if counts.commercial_leaf == 0
        else min(8, 2 + round(2 * log2(counts.commercial_leaf + 1)))
    )
    support = min(4, counts.support)
    other = min(3, counts.other)
    return structural + business_critical + leaves + support + other


def repair_reach(
    *,
    affected_checked: int,
    checked_eligible: int | None,
    counts: RoleCounts,
) -> str:
    if counts.structural or counts.business_critical:
        return "structural"
    if (
        checked_eligible
        and affected_checked >= 3
        and affected_checked / max(1, checked_eligible) >= 0.60
    ):
        return "broad_in_sample"
    if affected_checked >= 2:
        return "repeated"
    return "isolated"


def architecture_context(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    checked_eligible: int | None,
) -> dict[str, Any]:
    counts = role_counts_for_affected(fix, pages)
    affected_checked = len(_affected_paths(fix))
    return {
        "version": REPAIR_ARCHITECTURE_PRIORITY_VERSION,
        "role_counts": counts.as_dict(),
        "role_bonus": bounded_role_bonus(counts),
        "repair_reach": repair_reach(
            affected_checked=affected_checked,
            checked_eligible=checked_eligible,
            counts=counts,
        ),
    }


def architecture_priority_reason(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    checked_eligible: int | None,
    fallback_reason: str,
) -> str:
    """Add role-aware wording only when a stronger coverage reason is unavailable."""
    if checked_eligible:
        return fallback_reason

    counts = role_counts_for_affected(fix, pages)
    bits: list[str] = []
    if counts.structural:
        bits.append(
            f"{counts.structural} structural page"
            + ("s" if counts.structural != 1 else "")
        )
    if counts.business_critical:
        bits.append(
            f"{counts.business_critical} customer-journey page"
            + ("s" if counts.business_critical != 1 else "")
        )
    if counts.commercial_leaf:
        bits.append(
            f"{counts.commercial_leaf} checked commercial leaf page"
            + ("s" if counts.commercial_leaf != 1 else "")
        )

    if bits:
        return "Affected evidence includes " + ", ".join(bits) + "."
    return fallback_reason
