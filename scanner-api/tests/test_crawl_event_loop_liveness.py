"""The crawl must never starve the worker's event loop.

GetYourGuide scan 6a88783ce15cfbde38607f34 stalled with a single heartbeat at
exactly 60.07s after start and then silence: the periodic beat fired once and
was never scheduled again. Bounding the post-crawl phase was not enough,
because the crawl itself parsed every page synchronously on the event loop
(`extract_page`, `extract_links`). A blocked loop starves the heartbeat task
and every asyncio deadline together, so the run could neither report liveness
nor terminate itself.

These tests assert the property, not the implementation: while a page is being
parsed, other tasks on the loop still get scheduled.
"""

import asyncio
import time

import pytest

from app import scanner
from app.page_evidence_gate import page_evidence_class

REAL_HTML = "<!doctype html><html><head><title>Tours</title></head><body><h1>Tours</h1></body></html>"


class _Headers:
    def __init__(self, content_type="text/html"):
        self._content_type = content_type

    def get(self, key, default=""):
        return self._content_type if key.lower() == "content-type" else default

    def get_list(self, _key):
        return []


class _Response:
    def __init__(self, text, status_code=200, url="https://example.com/"):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = _Headers()


def _discovery():
    return {"discovered_from": "seed", "source_pages": [], "link_text_samples": []}


@pytest.fixture
def stub_fetch(monkeypatch):
    def install(response):
        async def fake_safe_get(_client, _url):
            return response
        monkeypatch.setattr(scanner, "safe_get", fake_safe_get)
    return install


# ------------------------------------------------------- loop responsiveness --

@pytest.mark.asyncio
async def test_page_parsing_does_not_starve_the_event_loop(monkeypatch, stub_fetch):
    """A slow parse must not stop other tasks -- this is the heartbeat's lifeline."""
    stub_fetch(_Response(REAL_HTML))

    real_extract = scanner.extract_page

    def slow_extract(*args, **kwargs):
        time.sleep(0.30)  # stand in for a pathological page
        return real_extract(*args, **kwargs)

    monkeypatch.setattr(scanner, "extract_page", slow_extract)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    beat = asyncio.create_task(ticker())
    try:
        await scanner.fetch_and_extract(None, "https://example.com/", _discovery())
    finally:
        beat.cancel()

    # On the event loop this was 0. Off it, the loop keeps scheduling.
    assert ticks > 0, "the event loop was starved for the whole parse"


@pytest.mark.asyncio
async def test_a_blocking_parse_cannot_stop_an_asyncio_deadline(monkeypatch, stub_fetch):
    """If deadlines cannot fire, nothing can terminate the run. They must fire."""
    stub_fetch(_Response(REAL_HTML))

    real_extract = scanner.extract_page

    def slow_extract(*args, **kwargs):
        time.sleep(0.30)
        return real_extract(*args, **kwargs)

    monkeypatch.setattr(scanner, "extract_page", slow_extract)

    async def crawl_then_wait():
        await scanner.fetch_and_extract(None, "https://example.com/", _discovery())
        await asyncio.Event().wait()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(crawl_then_wait(), timeout=0.45)


# ------------------------------------------------------------ body ceiling ---

@pytest.mark.asyncio
async def test_a_pathological_body_is_bounded_and_marked_truncated(stub_fetch):
    """An unbounded body is what makes a parse pathological in the first place."""
    huge = "<html><body>" + ("<p>x</p>" * 10) + "y" * (scanner.MAX_PARSED_HTML_CHARS + 1000) + "</body></html>"
    stub_fetch(_Response(huge))

    page = await scanner.fetch_and_extract(None, "https://example.com/", _discovery())

    assert page.get("raw_html_truncated") is True
    assert len(page.get("_html") or "") <= scanner.MAX_PARSED_HTML_CHARS


@pytest.mark.asyncio
async def test_a_truncated_page_is_not_authoritative_evidence(stub_fetch):
    """Truncated markup must fail closed, never produce invented findings."""
    huge = "<html><body>" + "y" * (scanner.MAX_PARSED_HTML_CHARS + 1000) + "</body></html>"
    stub_fetch(_Response(huge))

    page = await scanner.fetch_and_extract(None, "https://example.com/", _discovery())
    assert page_evidence_class(page) == "incomplete_html"


@pytest.mark.asyncio
async def test_a_normal_page_is_untouched_by_the_ceiling(stub_fetch):
    """The ceiling must not change ordinary crawling."""
    stub_fetch(_Response(REAL_HTML))

    page = await scanner.fetch_and_extract(None, "https://example.com/", _discovery())

    assert page.get("raw_html_truncated") is not True
    assert page["_html"] == REAL_HTML
    assert page["status_code"] == 200
    assert page_evidence_class(page) == "usable_html"
