import json
import time
from urllib import robotparser

import pytest

from app import scanner
from app.robots_policy import RobotsPolicy


def test_robots_snapshot_preserves_rules_and_unknown_state():
    parser = robotparser.RobotFileParser()
    parser.parse(['User-agent: *', 'Disallow: /private', 'Allow: /private/public'])
    policy = RobotsPolicy('https://example.com/robots.txt', 'available', 200, parser)
    restored = RobotsPolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
    assert restored.allowed('FixListPythonScanner', 'https://example.com/private') is False
    assert restored.allowed('FixListPythonScanner', 'https://example.com/blog') is True
    unknown = RobotsPolicy.from_dict(RobotsPolicy('', 'unavailable', 0).to_dict())
    assert unknown.allowed('FixListPythonScanner', 'https://example.com/') is None


def test_pacer_snapshot_uses_wall_clock_and_restores_pressure():
    pacer = scanner._AdaptiveRateLimitPacer(deadline=time.monotonic() + 300, enabled=True)
    pacer.next_request_at = time.monotonic() + 25
    pacer.retry_count = 3
    pacer.pressure_429_count = 2
    snapshot = pacer.to_dict()
    assert snapshot['deadline_at'] > time.time() + 290
    assert snapshot['next_request_at'] > time.time() + 20
    restored = scanner._AdaptiveRateLimitPacer.from_dict(json.loads(json.dumps(snapshot)))
    assert 20 < restored.next_request_at - time.monotonic() <= 25
    assert restored.retry_count == 3
    assert restored.pressure_429_count == 2


def test_scan_state_public_batch_interface_exists():
    assert callable(scanner.plan_scan)
    assert callable(scanner.crawl_batch)
    assert callable(scanner.finalize_scan)
    assert callable(scanner.ScanState.from_dict)


@pytest.mark.asyncio
async def test_checkpoint_between_batches_preserves_dedup_and_pages(mock_network):
    from tests import fixtures as fx
    origin = 'https://checkpoint.example'
    paths = ['/products', '/products/a', '/products/b', '/solutions', '/solutions/a', '/solutions/b']
    routes = {
        origin + '/': fx._html(fx._page('Home', links=paths)),
        origin + '/robots.txt': {'body': 'User-agent: *\nDisallow: /private', 'content_type': 'text/plain'},
        origin + '/sitemap.xml': fx._xml(fx._sitemap([origin + path for path in paths])),
        **{origin + path: fx._html(fx._page(path)) for path in paths},
    }
    requests = mock_network(routes)
    state = await scanner.plan_scan(origin + '/', concurrency=1)
    await scanner.crawl_batch(state, max_pages=2)
    assert len(state.pages) == 2
    snapshot = json.loads(json.dumps(state.to_dict()))
    assert snapshot['deadline'] > time.time()
    first_urls = {page['url'] for page in state.pages}
    state = scanner.ScanState.from_dict(snapshot)
    assert state.robots_policy.allowed('FixListPythonScanner', origin + '/private') is False
    while not state.finished:
        await scanner.crawl_batch(state, max_pages=2)
        state = scanner.ScanState.from_dict(json.loads(json.dumps(state.to_dict())))
    result = await scanner.finalize_scan(state)
    assert result['pages_crawled'] == 7
    assert len({page['url'] for page in result['pages']}) == 7
    assert first_urls.issubset({page['url'] for page in result['pages']})
    # Homepage landing discovery plus its one assessed fetch; no re-fetch on resume.
    assert sum(request.url.path == '/' for request in requests) == 2
    for path in paths:
        assert sum(request.url.path == path for request in requests) == 1


@pytest.mark.asyncio
async def test_downtime_consumes_original_scan_budget(mock_network, monkeypatch):
    from tests import fixtures as fx
    origin = 'https://deadline.example'
    mock_network({origin + '/': fx._html(fx._page('Home', links=['/other']))})
    state = await scanner.plan_scan(origin + '/', scan_mode='basic')
    snapshot = json.loads(json.dumps(state.to_dict()))
    original_wall = time.time
    monkeypatch.setattr(scanner.time, 'time', lambda: original_wall() + 500)
    restored = scanner.ScanState.from_dict(snapshot)
    assert restored.finished
    assert restored.completion_reason == "wall_budget"
    assert restored.limited is True
    assert await scanner.crawl_batch(restored, max_pages=50) == []


@pytest.mark.asyncio
async def test_first_partial_batch_contains_navigation_and_section_heads(mock_network):
    from tests import fixtures as fx
    origin = 'https://priority.example'
    sections = ['solutions', 'stores', 'insights', 'products']
    inventory = [origin + '/' + section for section in sections]
    inventory += [origin + '/' + section + '/' + str(n) for section in sections for n in range(90)]
    routes = {
        origin + '/': fx._html(fx._page('Home', links=['/' + section for section in sections])),
        origin + '/sitemap.xml': fx._xml(fx._sitemap(inventory)),
        **{url: fx._html(fx._page(url)) for url in inventory},
    }
    mock_network(routes)
    state = await scanner.plan_scan(origin + '/', concurrency=8)
    await scanner.crawl_batch(state, max_pages=45)
    retained = {page['url'] for page in state.pages}
    assert origin + '/' in retained
    assert {origin + '/' + section for section in sections}.issubset(retained)
    assert state.first_pass_urls.issubset(retained)
    assert state.rescored is True
    assert len(state.pages) == 45


@pytest.mark.asyncio
async def test_homepage_tracking_links_use_frontier_identity(mock_network):
    from tests import fixtures as fx
    origin = 'https://nav.example'
    mock_network({origin + '/': fx._html(fx._page('Home', links=[
        '/pricing?utm_source=navigation', '/products/widget?variant=red&utm_source=home',
    ]))})
    state = await scanner.plan_scan(origin + '/', concurrency=1)
    assert set(state.homepage_links) == {origin + '/pricing', origin + '/products/widget?variant=red'}
    for url in state.homepage_links:
        assert state.importance[url]['selection_reason'] == 'Linked from your homepage'
        assert url in state.first_pass_urls


@pytest.mark.asyncio
async def test_refused_pacer_slot_keeps_url_for_next_batch(mock_network, monkeypatch):
    from tests import fixtures as fx
    origin = 'https://paced.example'
    mock_network({origin + '/': fx._html(fx._page('Home'))})
    state = await scanner.plan_scan(origin + '/', concurrency=1)

    async def no_slot():
        return False

    monkeypatch.setattr(state.rate_limit_pacer, 'wait_for_slot', no_slot)
    assert await scanner.crawl_batch(state, max_pages=1) == []
    assert origin + '/' not in state.seen
    assert origin + '/' in state.queued
    assert state.crawl_state['claimed'] == 0
    assert state.finished is False

    async def slot():
        return True

    monkeypatch.setattr(state.rate_limit_pacer, 'wait_for_slot', slot)
    await scanner.crawl_batch(state, max_pages=1)
    assert len(state.pages) == 1
    assert state.pages[0]['url'] == origin + '/'
