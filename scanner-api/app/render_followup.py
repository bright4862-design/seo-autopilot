from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from .stage2_hub_render_evidence import build_hub_link_comparison


RENDER_FOLLOWUP_VERSION = "render_followup_v1"
DEFAULT_RENDER_FOLLOWUP_LIMIT = 3

RenderPage = Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]]


def select_render_followup_pages(
    pages: list[dict], max_pages: int = DEFAULT_RENDER_FOLLOWUP_LIMIT
) -> list[dict]:
    """Select a bounded, stable sample of successful pages with app-shell evidence."""
    limit = max(0, min(int(max_pages or 0), DEFAULT_RENDER_FOLLOWUP_LIMIT))
    selected: list[dict] = []
    seen: set[str] = set()
    for page in pages:
        if len(selected) >= limit:
            break
        if page.get("client_rendering_suspected") is not True:
            continue
        if not (200 <= int(page.get("status_code") or 0) < 400) or page.get("fetch_error"):
            continue
        url = str(page.get("final_url") or page.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        selected.append(page)
    return selected


def compare_raw_and_rendered(raw_page: dict, rendered_page: dict) -> dict:
    raw_words = max(0, int(raw_page.get("word_count") or 0))
    rendered_words = max(0, int(rendered_page.get("word_count") or 0))
    raw_title = str(raw_page.get("title") or "").strip()
    rendered_title = str(rendered_page.get("title") or "").strip()
    raw_h1 = str(raw_page.get("h1") or "").strip()
    rendered_h1 = str(rendered_page.get("h1") or "").strip()
    raw_schema = set(raw_page.get("schema_types") or [])
    rendered_schema = set(rendered_page.get("schema_types") or [])

    content_recovered = (
        (rendered_words >= 80 and rendered_words >= raw_words * 2)
        or (raw_words < 50 and rendered_words >= 150)
        or (not raw_title and bool(rendered_title))
        or (not raw_h1 and bool(rendered_h1))
        or bool(rendered_schema - raw_schema)
    )
    render_regression = raw_words >= 150 and rendered_words <= raw_words * 0.5
    return {
        "url": str(raw_page.get("final_url") or raw_page.get("url") or ""),
        "raw_word_count": raw_words,
        "rendered_word_count": rendered_words,
        "word_count_delta": rendered_words - raw_words,
        "title_recovered": not raw_title and bool(rendered_title),
        "h1_recovered": not raw_h1 and bool(rendered_h1),
        "schema_types_recovered": sorted(rendered_schema - raw_schema)[:20],
        "content_recovered": content_recovered,
        "render_regression": render_regression,
    }


async def run_render_followup(
    pages: list[dict],
    render_page: RenderPage | None = None,
    max_pages: int = DEFAULT_RENDER_FOLLOWUP_LIMIT,
    *,
    evidence_pages: list[dict] | None = None,
) -> dict:
    """Run the existing bounded browser policy and attach B12 paired hub evidence.

    B12 does not create a second renderer budget. It consumes only observations
    produced by the pre-existing three-page render follow-up. Up to five
    representative hubs may be selected for disclosure; hubs outside that
    existing browser budget remain explicitly unassessed.

    ``pages`` continues to control which pages are eligible for browser work.
    ``evidence_pages`` is an additive retained-set view for B12 disclosure only,
    so a caller can report eligible hubs as unassessed when browser policy does
    not authorize rendering without quietly enabling extra browser work.
    """
    selected = select_render_followup_pages(pages, max_pages)
    hub_pages = pages if evidence_pages is None else evidence_pages
    hub_evidence = build_hub_link_comparison(hub_pages)
    base = {
        "version": RENDER_FOLLOWUP_VERSION,
        "max_pages": DEFAULT_RENDER_FOLLOWUP_LIMIT,
        "selected_pages": len(selected),
        "attempted_pages": 0,
        "successful_pages": 0,
        "content_recovered_pages": 0,
        "render_regression_pages": 0,
        "results": [],
        "errors": [],
        "hub_link_comparison": hub_evidence,
    }
    if not selected:
        return {**base, "status": "not_needed"}
    if render_page is None:
        return {**base, "status": "recommended_not_run"}

    results: list[dict] = []
    errors: list[dict] = []
    rendered_pages_by_url: dict[str, dict[str, Any]] = {}
    attempted_urls: list[str] = []
    failure_reasons: dict[str, str] = {}
    for raw_page in selected:
        url = str(raw_page.get("final_url") or raw_page.get("url") or "")
        attempted_urls.append(url)
        try:
            value = render_page(url)
            rendered_page = await value if inspect.isawaitable(value) else value
            if not isinstance(rendered_page, dict):
                raise TypeError("renderer must return a page evidence object")
            rendered_pages_by_url[url] = rendered_page
            results.append(compare_raw_and_rendered(raw_page, rendered_page))
        except Exception as exc:
            message = str(exc)[:180]
            errors.append({"url": url, "error": message})
            # B12 is additive to the existing browser-followup diagnostics. Do
            # not duplicate raw exception text into the new persisted evidence.
            failure_reasons[url] = "renderer_failed"

    hub_evidence = build_hub_link_comparison(
        hub_pages,
        rendered_pages_by_url=rendered_pages_by_url,
        attempted_urls=attempted_urls,
        failure_reasons=failure_reasons,
    )
    recovered = sum(1 for item in results if item["content_recovered"])
    regressions = sum(1 for item in results if item["render_regression"])
    status = "rendered_content_recovered" if recovered else (
        "browser_checked_no_material_delta" if results else "browser_followup_failed"
    )
    return {
        **base,
        "status": status,
        "attempted_pages": len(selected),
        "successful_pages": len(results),
        "content_recovered_pages": recovered,
        "render_regression_pages": regressions,
        "results": results,
        "errors": errors[:DEFAULT_RENDER_FOLLOWUP_LIMIT],
        "hub_link_comparison": hub_evidence,
    }
