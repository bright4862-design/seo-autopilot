import pytest

from app import coverage_probes


@pytest.mark.asyncio
async def test_scheduler_reuses_actual_request_identity_without_spending_twice(monkeypatch):
    calls = []

    async def fake_safe_get_once(_client, url, *, max_decoded_bytes=None):
        calls.append((url, max_decoded_bytes))
        return object()

    monkeypatch.setattr(coverage_probes, "safe_get_once", fake_safe_get_once)
    scheduler = coverage_probes.SharedCoverageProbeScheduler(
        max_probe_requests=3,
        shared_request_limit=20,
        initial_request_count=4,
        deadline=10**12,
    )
    first = await scheduler.fetch_once(object(), "https://example.com/shared", max_decoded_bytes=123)
    second = await scheduler.fetch_once(object(), "https://example.com/shared", max_decoded_bytes=123)

    assert first is second
    assert calls == [("https://example.com/shared", 123)]
    budget = scheduler.summary()["request_budget"]
    assert budget["requests_consumed"] == 1
    assert budget["requests_reused"] == 1


@pytest.mark.asyncio
async def test_scheduler_never_exceeds_shared_frontier_ceiling(monkeypatch):
    calls = []

    async def fake_safe_get_once(_client, url, *, max_decoded_bytes=None):
        calls.append(url)
        return object()

    monkeypatch.setattr(coverage_probes, "safe_get_once", fake_safe_get_once)
    scheduler = coverage_probes.SharedCoverageProbeScheduler(
        max_probe_requests=5,
        shared_request_limit=5,
        initial_request_count=4,
        deadline=10**12,
    )
    await scheduler.fetch_once(object(), "https://example.com/one")
    with pytest.raises(RuntimeError, match="coverage_probe_request_budget_exhausted"):
        await scheduler.fetch_once(object(), "https://example.com/two")
    assert calls == ["https://example.com/one"]
    budget = scheduler.summary()["request_budget"]
    assert budget["requests_consumed"] == 1
    assert budget["budget_exhausted"] is True
