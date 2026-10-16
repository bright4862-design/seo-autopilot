from __future__ import annotations

from collections import defaultdict

import pytest

from app.stage2_shared_probe_orchestration import run_stage2_shared_probe_orchestration


ORIGIN = "https://example.com"
SITEMAP_TARGET = ORIGIN + "/from-sitemap"
SITEMAP_SOURCE = ORIGIN + "/sitemap.xml"


class FakeRobots:
    def __init__(self, denied=None):
        self.denied = set(denied or [])

    def allowed(self, _user_agent, url):
        return url not in self.denied

    def directive_allowed(self, _user_agent, url):
        return url not in self.denied

    def evidence(self):
        return {
            "robots_txt_url": ORIGIN + "/robots.txt",
            "robots_txt_status": "available",
            "robots_txt_status_code": 200,
            "robots_txt_rules_known": True,
        }


class FakeScheduler:
    """A network-free scheduler double with the production accounting surface."""

    def __init__(self, *, remaining=8, deadline_exhausted=False):
        self.remaining = max(0, int(remaining))
        self.initial = self.remaining
        self.requests_consumed = 0
        self.reused_requests = 0
        self.deadline_exhausted = bool(deadline_exhausted)
        self.budget_exhausted = False
        self.events = []
        self._candidates = defaultdict(dict)
        self._stats = defaultdict(
            lambda: {
                "eligible": 0,
                "selected": 0,
                "attempted": 0,
                "completed": 0,
                "passed": 0,
                "failed": 0,
                "not_verified": 0,
                "skipped": 0,
                "exhausted": 0,
            }
        )
        self._observations = []

    def register(self, *, purpose, url, source_pages=None, link_text_samples=None, metadata=None):
        if not purpose or not url:
            return
        current = self._candidates[purpose].get(url)
        if current is None:
            self._candidates[purpose][url] = {
                "url": url,
                "source_pages": list(source_pages or []),
                "link_text_samples": list(link_text_samples or []),
                "metadata": dict(metadata or {}),
            }
            self._stats[purpose]["eligible"] += 1
            self.events.append(("register", purpose, url))
            return
        for source in source_pages or []:
            if source not in current["source_pages"]:
                current["source_pages"].append(source)

    def candidates(self, purpose):
        return [dict(self._candidates[purpose][url]) for url in sorted(self._candidates[purpose])]

    def can_start_candidate(self, _purpose, _url):
        if self.deadline_exhausted:
            return False
        if self.remaining <= 0:
            self.budget_exhausted = True
            return False
        return True

    def begin_candidate(self, purpose):
        self._stats[purpose]["selected"] += 1
        self._stats[purpose]["attempted"] += 1

    async def fetch_once(self, _client, url, **_kwargs):
        if self.deadline_exhausted:
            raise RuntimeError("coverage_probe_deadline_exhausted")
        if self.remaining <= 0:
            self.budget_exhausted = True
            raise RuntimeError("coverage_probe_request_budget_exhausted")
        self.remaining -= 1
        self.requests_consumed += 1
        self.events.append(("fetch", "request", url))
        return object()

    def record_exhausted(self, purpose, url, **_kwargs):
        self._stats[purpose]["exhausted"] += 1
        self._observations.append((purpose, url, "not_verified", "deadline_exhausted" if self.deadline_exhausted else "request_budget_exhausted"))

    def record_skipped(self, purpose, url, *, reason, **_kwargs):
        self._stats[purpose]["skipped"] += 1
        self._observations.append((purpose, url, "not_verified", reason))

    def record_result(self, purpose, url, *, state, reason, **_kwargs):
        self._stats[purpose]["completed"] += 1
        if state == "pass":
            self._stats[purpose]["passed"] += 1
        elif state == "fail":
            self._stats[purpose]["failed"] += 1
        else:
            self._stats[purpose]["not_verified"] += 1
        self._observations.append((purpose, url, state, reason))

    def summary(self):
        return {
            "version": "coverage_probe_scheduler_v1_shared_request_budget",
            "request_budget": {
                "configured_probe_requests": self.initial,
                "shared_request_limit": 100,
                "crawl_requests_consumed": 10,
                "requests_consumed": self.requests_consumed,
                "requests_reused": self.reused_requests,
                "requests_remaining": self.remaining,
                "budget_exhausted": self.budget_exhausted,
                "deadline_exhausted": self.deadline_exhausted,
                "time_budget_seconds": 30.0,
            },
            "purposes": {purpose: dict(stats) for purpose, stats in sorted(self._stats.items())},
            "observations": list(self._observations),
            "observation_samples_truncated": False,
        }


def assessed_page():
    return {
        "url": ORIGIN + "/page",
        "request_url": ORIGIN + "/page",
        "final_url": ORIGIN + "/page",
        "path": "/page",
        "status_code": 200,
        "fetch_error": "",
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "raw_html_truncated": False,
        "redirect_hop_count": 0,
        "title": "Useful page",
        "h1": "Useful page",
        "meta_description": "A useful page",
        "word_count": 180,
        "page_template_family": "content",
    }


def sitemap_diagnostics():
    return {
        "sitemap_sources": [
            {
                "url": SITEMAP_SOURCE,
                "source": "speculative_default",
                "outcome": "urls",
                "loc_count": 1,
            }
        ],
        "sitemap_target_sources": [
            {
                "url": SITEMAP_TARGET,
                "sitemap_url": SITEMAP_SOURCE,
                "source_kind": "speculative_default",
            }
        ],
    }


def response_page(url, *, status=200, access_kind="", final_url=None, redirect_hops=0):
    page = {
        "url": url,
        "request_url": url,
        "final_url": final_url or url,
        "status_code": status,
        "fetch_error": "",
        "content_type": "text/html",
        "page_evidence_class": "usable_html" if 200 <= status < 300 else "failed_access",
        "raw_html_truncated": False,
        "redirect_hop_count": redirect_hops,
        "title": "Useful page",
        "h1": "Useful page",
        "meta_description": "A useful page",
        "word_count": 120,
    }
    if access_kind:
        page["access_block_kind"] = access_kind
    return page


async def make_fetch(routes=None):
    routes = routes or {}

    async def fetch(_client, url, _discovery, *, request_provider=None, **_kwargs):
        if request_provider is not None:
            await request_provider(None, url)
        if "__fixlist-missing-" in url:
            page = response_page(url)
            page.update({
                "title": "Page not found",
                "h1": "Page not found",
                "meta_description": "This page does not exist",
                "word_count": 30,
            })
            return page
        if url in routes:
            value = routes[url]
            return value(url) if callable(value) else dict(value)
        if url == SITEMAP_TARGET:
            return response_page(url, status=404)
        if url == ORIGIN + "/page/":
            return response_page(url, final_url=ORIGIN + "/page", redirect_hops=1)
        if url == ORIGIN + "/Page":
            return response_page(url, status=404)
        return response_page(url)

    return fetch


@pytest.mark.asyncio
async def test_registers_b07_b09_b16_before_io_and_preserves_assessed_pages():
    pages = [assessed_page()]
    pool = FakeScheduler(remaining=6)
    fetch = await make_fetch()

    evidence = await run_stage2_shared_probe_orchestration(
        client=object(),
        pages=pages,
        sitemap_urls=[SITEMAP_TARGET],
        sitemap_diagnostics=sitemap_diagnostics(),
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(),
        probe_scheduler=pool,
        fetch_page=fetch,
    )

    first_fetch = next(index for index, event in enumerate(pool.events) if event[0] == "fetch")
    registered_before_fetch = {event[1] for event in pool.events[:first_fetch] if event[0] == "register"}
    assert registered_before_fetch == {"soft_404_baseline", "sitemap_target", "url_variant"}
    assert evidence["single_shared_scheduler"] is True
    assert evidence["assessed_page_count_before"] == 1
    assert evidence["assessed_page_count_after"] == 1
    assert evidence["assessed_page_count_unchanged"] is True
    assert pages == [assessed_page()]
    assert evidence["stage2_probe_allocation"]["allocated_total"] <= 6
    assert any(row["state"] == "fail" for row in evidence["soft_404_baselines"])
    assert evidence["sitemap_integrity"]["target_provenance_complete"] is True
    assert evidence["sitemap_integrity"]["target_evidence"][0]["reason"] == "sitemap_target_http_404"
    assert any(row["reason"] == "harmless_normalization_to_source" for row in evidence["url_variants"]["evidence"])
    assert evidence["request_budget"]["requests_consumed"] <= 6


@pytest.mark.asyncio
async def test_shared_budget_shortfall_stays_unknown_for_unselected_purposes():
    pool = FakeScheduler(remaining=1)
    fetch = await make_fetch()

    evidence = await run_stage2_shared_probe_orchestration(
        client=object(),
        pages=[assessed_page()],
        sitemap_urls=[SITEMAP_TARGET],
        sitemap_diagnostics=sitemap_diagnostics(),
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(),
        probe_scheduler=pool,
        fetch_page=fetch,
    )

    allocated = evidence["stage2_probe_allocation"]["allocated"]
    assert allocated == {"soft_404_baseline": 1, "sitemap_target": 0, "url_variant": 0}
    assert evidence["sitemap_integrity"]["coverage"]["state"] == "not_verified"
    assert evidence["sitemap_integrity"]["coverage"]["candidate_universe_truncated"] is True
    assert evidence["url_variants"]["coverage"]["state"] == "not_verified"
    assert evidence["url_variants"]["coverage"]["candidate_universe_truncated"] is True
    assert evidence["assessed_page_count_unchanged"] is True
    assert all(event[1] == "request" for event in pool.events if event[0] == "fetch")


@pytest.mark.asyncio
async def test_robots_denied_sitemap_target_is_explicit_unknown():
    pool = FakeScheduler(remaining=6)
    fetch = await make_fetch()

    evidence = await run_stage2_shared_probe_orchestration(
        client=object(),
        pages=[assessed_page()],
        sitemap_urls=[SITEMAP_TARGET],
        sitemap_diagnostics=sitemap_diagnostics(),
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots({SITEMAP_TARGET}),
        probe_scheduler=pool,
        fetch_page=fetch,
    )

    target = evidence["sitemap_integrity"]["target_evidence"][0]
    assert target["state"] == "not_verified"
    assert target["reason"] == "blocked_by_robots_txt"
    assert evidence["sitemap_integrity"]["coverage"]["state"] == "not_verified"
    assert any(row[0] == "sitemap_target" and row[2] == "not_verified" for row in evidence["observations"])


@pytest.mark.asyncio
async def test_challenge_and_rate_limit_evidence_remain_unknown():
    pool = FakeScheduler(remaining=6)
    fetch = await make_fetch({
        SITEMAP_TARGET: response_page(SITEMAP_TARGET, status=429, access_kind="rate_limit"),
        ORIGIN + "/page/": response_page(ORIGIN + "/page/", status=403, access_kind="challenge"),
    })

    evidence = await run_stage2_shared_probe_orchestration(
        client=object(),
        pages=[assessed_page()],
        sitemap_urls=[SITEMAP_TARGET],
        sitemap_diagnostics=sitemap_diagnostics(),
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(),
        probe_scheduler=pool,
        fetch_page=fetch,
    )

    assert evidence["sitemap_integrity"]["target_evidence"][0]["state"] == "not_verified"
    assert evidence["sitemap_integrity"]["target_evidence"][0]["reason"] == "rate_limit"
    slash = next(row for row in evidence["url_variants"]["evidence"] if row["probe_url"] == ORIGIN + "/page/")
    assert slash["state"] == "not_verified"
    assert slash["reason"] == "variant_challenge"


@pytest.mark.asyncio
async def test_deadline_exhaustion_never_fetches_or_claims_verified_coverage():
    pool = FakeScheduler(remaining=6, deadline_exhausted=True)
    fetch = await make_fetch()

    evidence = await run_stage2_shared_probe_orchestration(
        client=object(),
        pages=[assessed_page()],
        sitemap_urls=[SITEMAP_TARGET],
        sitemap_diagnostics=sitemap_diagnostics(),
        origin=ORIGIN,
        scope_prefix="/",
        robots_policy=FakeRobots(),
        probe_scheduler=pool,
        fetch_page=fetch,
    )

    assert not any(event[0] == "fetch" for event in pool.events)
    assert evidence["request_budget"]["deadline_exhausted"] is True
    assert evidence["sitemap_integrity"]["coverage"]["state"] == "not_verified"
    assert evidence["url_variants"]["coverage"]["state"] == "not_verified"
    assert evidence["soft_404_baselines"]
    assert {row["state"] for row in evidence["soft_404_baselines"]} == {"not_verified"}
    assert {row["reason"] for row in evidence["soft_404_baselines"]} == {"deadline_exhausted"}
