import asyncio
import json
from urllib.parse import urlparse

import httpx
import pytest

from app import canonical_validation, scanner
from app.robots_policy import RobotsPolicy
from tests import fixtures as fx


@pytest.mark.asyncio
@pytest.mark.parametrize("first_throttle", ["internal_link", "sitemap_target", "canonical", "browser"])
async def test_finalize_429_stops_optional_requests_without_changing_retained_pages(mock_network, first_throttle):
    origin = "https://finalize-throttle.example"
    home = origin + "/"
    sitemap_urls = [f"{origin}/products/{number:03d}" for number in range(155)]
    canonical_urls = [f"{origin}/canonical/{number:03d}" for number in range(155)]
    link_urls = [f"{origin}/uncrawled-link-{number}" for number in range(2)]
    throttle = {"status": 429, "headers": {"Retry-After": "30"}}
    routes = {
        home: fx._html(fx._page("Home")),
        origin + "/sitemap.xml": fx._xml(fx._sitemap(sitemap_urls)),
        **dict.fromkeys(canonical_urls, fx._html(fx._page("Canonical target"))),
    }
    if first_throttle == "internal_link":
        routes[link_urls[0]] = throttle
        routes[link_urls[1]] = fx._html(fx._page("Second link target"))
    for number, url in enumerate(sitemap_urls):
        target = canonical_urls[number] if first_throttle == "canonical" else canonical_urls[0]
        if number == 0:
            target = home  # Cached canonical evidence remains useful after a probe 429.
        routes[url] = fx._html(fx._page(
            f"Product {number}",
            canonical=target,
            body='<div id="root"></div>',
            links=link_urls if first_throttle == "internal_link" else None,
        ))

    requests = mock_network(routes)
    state = await scanner.plan_scan(home, job_mode=True)
    while not state.finished:
        await scanner.crawl_batch(state)
        state = scanner.ScanState.from_dict(json.loads(json.dumps(state.to_dict())))

    retained = {page["url"]: page["status_code"] for page in state.pages}
    assert len(retained) == state.max_pages == 150
    assert set(retained.values()) == {200}
    assert sitemap_urls[0] in retained
    assert state.rate_limit_pacer.rate_limit_blocked_scan is False
    assert not state.rate_limit_pacer.rate_limit_cooldown_until
    pending_sitemap = set(sitemap_urls) - retained.keys()
    assert pending_sitemap
    if first_throttle == "sitemap_target":
        routes.update(dict.fromkeys(pending_sitemap, throttle))
    if first_throttle == "canonical":
        routes.update(dict.fromkeys(canonical_urls, throttle))

    requests.clear()
    rendered = []

    async def render(url):
        rendered.append(url)
        return {"status_code": 429}

    state.render_page = render
    result = await scanner.finalize_scan(state)
    paths = [request.url.path for request in requests]

    assert result["success"] is True
    assert {page["url"]: page["status_code"] for page in result["pages"]} == retained
    assert result["crawl_timing"]["rate_limit_retry_count"] == 0
    assert state.rate_limit_pacer.rate_limit_blocked_scan is False
    cached_canonical = next(page for page in result["pages"] if page["url"] == sitemap_urls[0])
    assert cached_canonical["canonical_target_evidence_source"] == "crawl"
    browser = result["render_evidence"]["browser_followup"]
    if first_throttle == "browser":
        assert len(rendered) == browser["attempted_pages"] == 1
        assert browser["skip_reason"] == "finalize_rate_limited"
        assert browser["successful_pages"] == 0
        assert browser["selected_pages"] > 1
        assert browser["status"] == "browser_followup_failed"
        return

    if first_throttle == "internal_link":
        assert paths == [urlparse(link_urls[0]).path]
    elif first_throttle == "sitemap_target":
        pending_paths = {urlparse(url).path for url in pending_sitemap}
        assert [path for path in paths if path in pending_paths] == [paths[-1]]
        assert not any(path.startswith("/canonical/") for path in paths)
    else:
        assert [path for path in paths if path.startswith("/canonical/")] == [paths[-1]]
        canonical_states = result["canonical_target_evidence"]["state_counts"]
        assert canonical_states["unknown_access_limited"] == 1
        assert canonical_states["not_checked_due_to_limit"] > 0
        assert "target_failed" not in canonical_states

    assert not rendered
    assert browser["attempted_pages"] == 0
    assert browser["status"] == "recommended_not_run"
    assert browser["skip_reason"] == "finalize_rate_limited"
    assert browser["successful_pages"] == 0
    if first_throttle in {"internal_link", "sitemap_target"}:
        coverage = result["coverage_probe_evidence"]
        assert coverage["stage2_orchestration_state"] == "not_verified"
        assert coverage["stage2_orchestration_reason"] == "finalize_rate_limited"


@pytest.mark.asyncio
async def test_canonical_429_blocks_waiting_request_while_its_body_is_still_pending(mock_network, monkeypatch):
    from app.finalize_probe_guard import FinalizeProbeGuard

    origin = "https://concurrent-probes.example"
    first = "/target-0"
    second = "/target-1"
    waiting = "/target-2"
    requests = []
    second_started = asyncio.Event()
    throttle_body_started = asyncio.Event()
    release_throttle_body = asyncio.Event()
    waiting_checked = asyncio.Event()

    class SlowThrottleBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            throttle_body_started.set()
            await release_throttle_body.wait()
            yield b"Throttled"

    async def target_response(request):
        path = request.url.path
        requests.append(path)
        if path == first:
            await second_started.wait()
            return httpx.Response(429, stream=SlowThrottleBody())
        if path == second:
            second_started.set()
            await throttle_body_started.wait()
        return httpx.Response(200, text="<html><body>Checked</body></html>")

    fetch_target = canonical_validation._fetch_target

    async def observe_waiting_check(client, target, *args, **kwargs):
        evidence = await fetch_target(client, target, *args, **kwargs)
        if target.endswith(waiting):
            waiting_checked.set()
        return evidence

    monkeypatch.setattr(canonical_validation, "_fetch_target", observe_waiting_check)
    real_client = httpx.AsyncClient
    mock_network({})  # Keep the production IP-pinning code, using offline DNS.
    guard = FinalizeProbeGuard()
    pages = [
        {
            "url": f"{origin}/page-{i}",
            "canonical": origin + path,
            "canonical_status": "canonical_to_different_url",
        }
        for i, path in enumerate((first, second, waiting))
    ]

    async with real_client(
        transport=httpx.MockTransport(target_response),
        event_hooks={"request": [guard.before_request], "response": [guard.after_response]},
    ) as client:
        validation = asyncio.create_task(canonical_validation.validate_canonical_targets(
            client,
            pages,
            RobotsPolicy(origin + "/robots.txt", "missing", 404),
            concurrency=2,
            finalize_guard=guard,
        ))
        try:
            await asyncio.wait_for(waiting_checked.wait(), timeout=2)
            assert requests == [first, second]
            assert not validation.done()
        finally:
            release_throttle_body.set()
            await validation

    assert pages[0]["canonical_target_state"] == "unknown_access_limited"
    assert pages[1]["canonical_target_evidence_source"] == "validation"
    assert pages[2]["canonical_target_evidence_source"] == "rate_limit"
