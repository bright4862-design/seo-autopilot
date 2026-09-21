"""Local accepted-HTML adapter for Lane-B semantic link-zone evidence.

No network I/O occurs here. Raw HTML is consumed transiently and never returned;
only bounded structural evidence required by ``semantic_graph.infer_link_zone``
is emitted.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from .semantic_graph import MAX_LINKS_PER_SOURCE

MAX_HTML_BYTES = 2_000_000
MAX_ANCESTOR_DEPTH = 10
MAX_CONTAINER_LINK_COUNT = 50
MAX_ANCHOR_TEXT_CHARS = 180


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def extract_link_zone_observations(
    html: str,
    source_url: str,
    *,
    limit: int = MAX_LINKS_PER_SOURCE,
) -> list[dict[str, Any]]:
    """Return bounded structural observations for already-accepted HTML."""
    source = _text(source_url)
    raw = str(html or "")
    if not source or len(raw.encode("utf-8")) > MAX_HTML_BYTES:
        return []
    bounded_limit = max(1, min(int(limit or MAX_LINKS_PER_SOURCE), MAX_LINKS_PER_SOURCE))
    soup = BeautifulSoup(raw, "lxml")
    observations: list[dict[str, Any]] = []

    for anchor in soup.find_all("a", href=True):
        try:
            target, _ = urldefrag(urljoin(source, anchor.get("href", "")))
        except Exception:
            continue
        if not target:
            continue

        tags: list[str] = []
        roles: list[str] = []
        classes: list[str] = []
        ids: list[str] = []
        repeated_sibling_links = 0
        current = anchor
        depth = 0
        while current is not None and depth < MAX_ANCESTOR_DEPTH:
            name = str(getattr(current, "name", "") or "").strip().lower()
            if name:
                tags.append(name)
            attrs = getattr(current, "attrs", {}) or {}
            role = _text(attrs.get("role")).lower()
            if role:
                roles.append(role)
            raw_classes = attrs.get("class") or []
            if isinstance(raw_classes, str):
                raw_classes = raw_classes.split()
            classes.extend(_text(value).lower() for value in raw_classes if _text(value))
            node_id = _text(attrs.get("id")).lower()
            if node_id:
                ids.append(node_id)
            if repeated_sibling_links == 0 and name in {"li", "ul", "ol", "section", "div", "article"}:
                try:
                    repeated_sibling_links = min(
                        MAX_CONTAINER_LINK_COUNT,
                        len(current.find_all("a", href=True)),
                    )
                except Exception:
                    repeated_sibling_links = 0
            current = getattr(current, "parent", None)
            depth += 1

        observations.append(
            {
                "source_url": source,
                "target_url": target,
                "anchor_text": _text(anchor.get_text(" "))[:MAX_ANCHOR_TEXT_CHARS],
                "ancestor_tags": tags,
                "ancestor_roles": roles,
                "ancestor_classes": classes,
                "ancestor_ids": ids,
                "navigation_presence": "nav" in tags or "navigation" in roles,
                "repeated_sibling_links": repeated_sibling_links,
            }
        )
        if len(observations) >= bounded_limit:
            break

    return observations
