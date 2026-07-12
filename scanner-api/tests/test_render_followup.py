import pytest

from app.render_followup import (
    compare_raw_and_rendered,
    run_render_followup,
    select_render_followup_pages,
)


def _raw(index, *, suspected=True, status=200):
    return {
        "url": f"https://example.com/app-{index}",
        "final_url": f"https://example.com/app-{index}",
        "status_code": status,
        "fetch_error": "",
        "client_rendering_suspected": suspected,
        "word_count": 10,
        "title": "",
        "h1": "",
        "schema_types": [],
    }


def test_selection_is_bounded_and_excludes_non_suspected_or_failed_pages():
    pages = [_raw(index) for index in range(5)]
    pages += [_raw(6, suspected=False), _raw(7, status=429)]

    selected = select_render_followup_pages(pages, max_pages=20)

    assert [page["url"] for page in selected] == [
        "https://example.com/app-0",
        "https://example.com/app-1",
        "https://example.com/app-2",
    ]


def test_comparison_reports_content_recovered_without_mutating_raw_page():
    raw = _raw(1)
    rendered = {
        "word_count": 140,
        "title": "Rendered title",
        "h1": "Rendered heading",
        "schema_types": ["Product"],
    }

    result = compare_raw_and_rendered(raw, rendered)

    assert result["content_recovered"] is True
    assert result["word_count_delta"] == 130
    assert result["title_recovered"] is True
    assert result["h1_recovered"] is True
    assert result["schema_types_recovered"] == ["Product"]
    assert result["render_regression"] is False
    assert raw["word_count"] == 10


def test_small_hydration_delta_is_not_reported_as_content_recovery():
    raw = {**_raw(1), "word_count": 600, "title": "Title", "h1": "Heading"}
    rendered = {
        "word_count": 655,
        "title": "Title",
        "h1": "Heading",
        "schema_types": [],
    }

    result = compare_raw_and_rendered(raw, rendered)

    assert result["content_recovered"] is False
    assert result["render_regression"] is False


def test_large_rendered_content_drop_is_reported_as_regression():
    raw = {**_raw(1), "word_count": 900, "title": "Title", "h1": "Heading"}
    rendered = {
        "word_count": 400,
        "title": "Title",
        "h1": "Heading",
        "schema_types": [],
    }

    result = compare_raw_and_rendered(raw, rendered)

    assert result["content_recovered"] is False
    assert result["render_regression"] is True


@pytest.mark.asyncio
async def test_followup_is_explicit_when_renderer_is_not_configured():
    result = await run_render_followup([_raw(1), _raw(2)])

    assert result["status"] == "recommended_not_run"
    assert result["selected_pages"] == 2
    assert result["attempted_pages"] == 0


@pytest.mark.asyncio
async def test_followup_uses_injected_renderer_and_contains_failures():
    async def renderer(url):
        if url.endswith("app-1"):
            return {"word_count": 120, "title": "Loaded", "h1": "", "schema_types": []}
        raise RuntimeError("browser timeout")

    result = await run_render_followup([_raw(1), _raw(2)], renderer)

    assert result["status"] == "rendered_content_recovered"
    assert result["attempted_pages"] == 2
    assert result["successful_pages"] == 1
    assert result["content_recovered_pages"] == 1
    assert result["render_regression_pages"] == 0
    assert result["errors"] == [
        {"url": "https://example.com/app-2", "error": "browser timeout"}
    ]
