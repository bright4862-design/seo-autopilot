import copy
import time

import pytest

from app.active_soft404_orchestration import (
    collect_active_soft404_baselines,
    uniform_observed_group_provenance,
)
from app.coverage_probes import (
    SOFT_404_PROBE_VERSION,
    SharedCoverageProbeScheduler,
    compare_page_to_soft_404_baselines,
)


ORIGIN = "https://example.com"


class FakeRobots:
    def __init__(self, allowed=True):
        self._allowed = allowed

    def allowed(self, _user_agent, _url):
        return self._allowed

    def directive_allowed(self, _user_agent, _url):
        return self._allowed

    def evidence(self):
        return {
            "robots_txt_url": ORIGIN + "/robots.txt",
            "robots_txt_status": "available",
            "robots_txt_status_code": 200,
            "robots_txt_rules_known": True,
        }


def assessed_page(url=ORIGIN + "/catalog/gone", *, missing=True):
    return {
        "url": url,
        "final_url": url,
        "path": "/" + url.split(ORIGIN + "/", 1)[-1],
        "status_code": 200,
        "fetch_error": "",
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "raw_html_truncated": False,
        "redirect_hop_count": 0,
        "title": "Page not found" if missing else "Useful product",
        "h1": "Catalog entry" if missing else "Useful product",
        "meta_description": (
            "This catalog entry is no longer available"
            if missing
            else "Useful product details"
        ),
        "word_count": 80 if missing else 180,
        "page_template_family": "activity_detail",
    }


def probe_page(url, *, status=200, access_kind="", fetch_error=""):
    page = {
        "url": url,
        "final_url": url,
        "path": "/" + url.split(ORIGIN + "/", 1)[-1],
        "status_code": status,
        "fetch_error": fetch_error,
        "content_type": "text/html",
        "page_evidence_class": "usable_html" if 200 <= status < 300 and not fetch_error else "failed_access",
        "raw_html_truncated": False,
        "redirect_hop_count": 0,
        "title": "Page not found",
        "h1": "Catalog entry",
        "meta_description": "This catalog entry is no longer available",
        "word_count": 70,
        "page_template_family": "activity_detail",
    }
    if access_kind:
        page["access_block_kind"] = access_kind
    return page


def scheduler(*, request_limit=8, shared_limit=100, initial=3, deadline=None):
    return SharedCoverageProbeScheduler(
        max_probe_requests=request_limit,
        shared_request_limit=shared_limit,
        initial_request_count=initial,
        deadline=time.monotonic() + 60 if deadline is None else deadline,
    )


def test_uniform_group_provenance_fails_closed_for_mixed_members():
    active = {
        "observed_evidence_version": SOFT_404_PROBE_VERSION,
        "verified_observed_pages": [ORIGIN + "/catalog/a"],
    }
    passive = {"verified_observed_pages": [ORIGIN + "/catalog/b"]}

    assert uniform_observed_group_provenance([active, passive]) == {}


def test_uniform_group_provenance_preserves_exact_verified_union():
    urls = [ORIGIN + "/catalog/a", ORIGIN + "/catalog/b", ORIGIN + "/catalog/c"]
    members = [
        {
            "observed_evidence_version": SOFT_404_PROBE_VERSION,
            "verified_observed_pages": [url],
        }
        for url in urls
    ]

    assert uniform_observed_group_provenance(members) == {
        "observed_evidence_version": SOFT_404_PROBE_VERSION,
        "verified_observed_pages": urls,
    }


@pytest.mark.asyncio
async def test_active_probe_discovers_verified_baseline_without_mutating_assessed_pages():
    pages = [assessed_page()]
    original = copy.deepcopy(pages)
    calls = []

    async def fake_fetch(_client, url, discovery, *, robots_policy=None, request_provider=None):
        calls.append((url, discovery, robots_policy, request_provider))
        return probe_page(url)

    pool = scheduler(request_limit=6)
    baselines = await collect_active_soft404_baselines(
        client=object(),
        pages=pages,
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(True),
        probe_scheduler=pool,
        fetch_page=fake_fetch,
    )

    verified = [row for row in baselines if row["state"] == "fail"]
    assert verified
    assert all(row["version"] == SOFT_404_PROBE_VERSION for row in baselines)
    assert all(row["provenance"] == "deterministic_nonexistent_path" for row in baselines)
    assert all(row.get("signature_tokens") for row in verified)
    assert pages == original
    assert all("__fixlist-missing-" in call[0] for call in calls)
    assert all(call[1]["discovered_from"] == ["synthetic_soft_404_probe"] for call in calls)
    assert all(call[3] == pool.fetch_once for call in calls)

    matched = compare_page_to_soft_404_baselines(pages[0], baselines)
    assert matched["state"] == "fail"
    assert matched["reason"] == "active_soft_404_baseline_match"
    summary = pool.summary()
    assert summary["purposes"]["soft_404_baseline"]["attempted"] == len(calls)
    assert summary["request_budget"]["requests_consumed"] == 0
    # The injected fetch path deliberately did no I/O; production passes the
    # scheduler's fetch_once into the hardened request path, which spends it.


@pytest.mark.asyncio
async def test_robots_denied_probe_is_unknown_and_never_fetched():
    pages = [assessed_page()]
    calls = []

    async def forbidden_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("robots-denied synthetic path must not be fetched")

    pool = scheduler()
    baselines = await collect_active_soft404_baselines(
        client=object(),
        pages=pages,
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(False),
        probe_scheduler=pool,
        fetch_page=forbidden_fetch,
    )

    assert calls == []
    assert baselines
    assert {row["state"] for row in baselines} == {"not_verified"}
    assert {row["reason"] for row in baselines} == {"blocked_by_robots_txt"}
    summary = pool.summary()
    assert summary["purposes"]["soft_404_baseline"]["skipped"] == len(baselines)
    assert summary["request_budget"]["requests_consumed"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "access_kind", "expected_reason"),
    [
        (429, "rate_limit", "rate_limit"),
        (403, "challenge", "challenge"),
    ],
)
async def test_access_limited_probe_stays_unknown(status, access_kind, expected_reason):
    pages = [assessed_page()]

    async def fake_fetch(_client, url, _discovery, **_kwargs):
        return probe_page(url, status=status, access_kind=access_kind)

    pool = scheduler()
    baselines = await collect_active_soft404_baselines(
        client=object(),
        pages=pages,
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(True),
        probe_scheduler=pool,
        fetch_page=fake_fetch,
    )

    assert baselines
    assert {row["state"] for row in baselines} == {"not_verified"}
    assert {row["reason"] for row in baselines} == {expected_reason}
    assert compare_page_to_soft_404_baselines(pages[0], baselines)["state"] == "not_verified"


@pytest.mark.asyncio
async def test_shared_budget_exhaustion_is_explicit_unknown_without_fetch():
    calls = []

    async def forbidden_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("exhausted pool must not fetch")

    pool = scheduler(request_limit=0)
    baselines = await collect_active_soft404_baselines(
        client=object(),
        pages=[assessed_page()],
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(True),
        probe_scheduler=pool,
        fetch_page=forbidden_fetch,
    )

    assert calls == []
    assert baselines
    assert {row["state"] for row in baselines} == {"not_verified"}
    assert {row["reason"] for row in baselines} == {"request_budget_exhausted"}
    summary = pool.summary()
    assert summary["request_budget"]["budget_exhausted"] is True
    assert summary["purposes"]["soft_404_baseline"]["exhausted"] == len(baselines)


@pytest.mark.asyncio
async def test_deadline_exhaustion_is_explicit_unknown_without_fetch():
    calls = []

    async def forbidden_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("expired pool must not fetch")

    pool = scheduler(deadline=time.monotonic() - 1)
    baselines = await collect_active_soft404_baselines(
        client=object(),
        pages=[assessed_page()],
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(True),
        probe_scheduler=pool,
        fetch_page=forbidden_fetch,
    )

    assert calls == []
    assert baselines
    assert {row["state"] for row in baselines} == {"not_verified"}
    assert {row["reason"] for row in baselines} == {"deadline_exhausted"}
    summary = pool.summary()
    assert summary["request_budget"]["deadline_exhausted"] is True
    assert summary["purposes"]["soft_404_baseline"]["exhausted"] == len(baselines)
