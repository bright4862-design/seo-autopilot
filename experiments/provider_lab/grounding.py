from __future__ import annotations

import re
from typing import Any, Mapping

URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
PAGE_COUNT_PATTERN = re.compile(r"\b(\d[\d,]*)\s+pages?\b", re.IGNORECASE)


def _walk(value: Any):
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    else:
        yield value


def verified_urls(evidence: Mapping[str, Any]) -> set[str]:
    urls: set[str] = set()
    for item in evidence.get("recommendations", []) or []:
        if not isinstance(item, Mapping):
            continue
        for verified in item.get("verified_urls", []) or []:
            if isinstance(verified, str):
                url = verified.strip()
                status = 200
            elif isinstance(verified, Mapping):
                url = str(verified.get("final_url") or verified.get("url") or "").strip()
                try:
                    status = int(verified.get("status_code") or 0)
                except (TypeError, ValueError):
                    status = 0
            else:
                continue
            if url and status == 200:
                urls.add(url.rstrip(".,;:!?"))
    return urls


def page_counts(evidence: Mapping[str, Any]) -> set[int]:
    allowed: set[int] = set()
    for key in ("pages_found", "pages_crawled"):
        value = evidence.get(key)
        try:
            if value is not None:
                allowed.add(int(value))
        except (TypeError, ValueError):
            pass

    fix_list = evidence.get("fix_list")
    if isinstance(fix_list, Mapping):
        for key in (
            "total_fixes",
            "critical_count",
            "high_count",
            "medium_count",
            "low_count",
            "completed_count",
        ):
            value = fix_list.get(key)
            try:
                if value is not None:
                    allowed.add(int(value))
            except (TypeError, ValueError):
                pass

    for item in evidence.get("recommendations", []) or []:
        if not isinstance(item, Mapping):
            continue
        affected = item.get("affected_pages")
        if isinstance(affected, list):
            allowed.add(len(affected))
    return allowed


def unverified_urls(output_text: str, evidence: Mapping[str, Any]) -> list[str]:
    allowed = verified_urls(evidence)
    found = [match.rstrip(".,;:!?") for match in URL_PATTERN.findall(output_text or "")]
    return sorted({url for url in found if url not in allowed})


def unsupported_page_counts(output_text: str, evidence: Mapping[str, Any]) -> list[int]:
    allowed = page_counts(evidence)
    unsupported: set[int] = set()
    for raw in PAGE_COUNT_PATTERN.findall(output_text or ""):
        try:
            count = int(raw.replace(",", ""))
        except ValueError:
            continue
        if count not in allowed:
            unsupported.add(count)
    return sorted(unsupported)


def grounding_failures(output_text: str, evidence: Mapping[str, Any]) -> dict[str, list[Any]]:
    return {
        "unverified_urls": unverified_urls(output_text, evidence),
        "unsupported_page_counts": unsupported_page_counts(output_text, evidence),
    }
