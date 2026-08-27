import httpx
import pytest

from app.extract import extract_page
from app.scanner import fetch_and_extract


DISCOVERY = {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []}


def _page(*, status=200, head="", headers=None, fetch_error=""):
    return extract_page(
        f"<html><head><title>Page</title>{head}</head><body><h1>Page</h1></body></html>",
        "https://example.com/page",
        "https://example.com/page",
        status,
        "text/html",
        DISCOVERY,
        fetch_error=fetch_error,
        response_headers=headers,
    )


def test_x_robots_tag_noindex_controls_indexability():
    page = _page(headers={"X-Robots-Tag": ["noindex, nofollow"]})

    assert page["x_robots_tag_directives"] == {"robots": ["noindex", "nofollow"]}
    assert page["effective_search_robots_directives"] == ["noindex", "nofollow"]
    assert page["indexable"] is False
    assert page["indexability_state"] == "Noindexed"


def test_googlebot_meta_is_separate_and_controls_google_indexability():
    page = _page(
        head=(
            '<meta name="robots" content="index, follow">'
            '<meta name="googlebot" content="noindex, max-snippet:0">'
            '<meta name="bingbot" content="nofollow">'
        )
    )

    assert page["robots_meta_directives"] == {
        "robots": ["index", "follow"],
        "googlebot": ["noindex", "max-snippet:0"],
        "bingbot": ["nofollow"],
    }
    assert page["googlebot_robots"] == "noindex, max-snippet:0"
    assert page["crawler_specific_robots"]["bingbot"] == ["nofollow"]
    assert page["indexable"] is False
    assert page["indexability_state"] == "Noindexed"


def test_agent_scoped_x_robots_directives_remain_scoped_across_header_values():
    page = _page(
        headers={
            "x-robots-tag": [
                "googlebot: noindex, nofollow",
                "bingbot: noarchive",
            ]
        }
    )

    assert page["x_robots_tag_directives"] == {
        "googlebot": ["noindex", "nofollow"],
        "bingbot": ["noarchive"],
    }
    assert page["indexable"] is False


@pytest.mark.parametrize(
    ("status", "expected_state", "expected_indexable"),
    [
        (200, "Indexable", True),
        (301, "Redirected", False),
        (404, "Failed", False),
    ],
)
def test_http_status_has_an_explicit_indexability_state(status, expected_state, expected_indexable):
    page = _page(status=status)

    assert page["indexability_state"] == expected_state
    assert page["indexable"] is expected_indexable


@pytest.mark.asyncio
async def test_fetch_and_extract_preserves_multiple_x_robots_headers(monkeypatch):
    response = httpx.Response(
        200,
        headers=[
            ("content-type", "text/html"),
            ("x-robots-tag", "noarchive"),
            ("x-robots-tag", "googlebot: noindex"),
        ],
        text="<html><head><title>Page</title></head><body><h1>Page</h1></body></html>",
        request=httpx.Request("GET", "https://example.com/page"),
    )

    async def fake_safe_get(_client, _url, **_kwargs):
        return response

    monkeypatch.setattr("app.scanner.is_public_http_url", lambda _url: True)
    monkeypatch.setattr("app.scanner.safe_get", fake_safe_get)

    page = await fetch_and_extract(None, "https://example.com/page", DISCOVERY)

    assert page["x_robots_tag_directives"] == {
        "robots": ["noarchive"],
        "googlebot": ["noindex"],
    }
    assert page["indexability_state"] == "Noindexed"
