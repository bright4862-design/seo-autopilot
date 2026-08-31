"""Leaf text and URL helpers shared by the review layer.

Extracted from review.py so the repair-dedup logic can be a module of its own
without importing the 3 000-line orchestrator it used to live inside. Pure
functions with no project imports: this is the bottom of the layering, and
nothing here may grow a dependency on review or scanner.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def clean_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path = parsed.path or "/"
        query = ("?" + parsed.query) if parsed.query else ""
    else:
        path = raw if raw.startswith("/") else f"/{raw}"
        query = ""
        if "?" in path:
            path, rest = path.split("?", 1)
            query = "?" + rest
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return f"{path}{query}"


def has_any(text: str, needles: list[str]) -> bool:
    haystack = str(text or "").lower()
    return any(str(needle or "").lower() in haystack for needle in needles)


def dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output
