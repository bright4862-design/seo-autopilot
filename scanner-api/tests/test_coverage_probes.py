import pytest

from app import coverage_probes


def _accepted_page(
    url="https://example.com/catalog/item",
    *,
    title="Useful product",
    h1="Useful product",
    description="Useful product details",
    word_count=80,
    status_code=200,
    access_kind="",
    evidence_class="usable_html",
):
    page = {
        "url": url,
        "final_url": url,
        "path": coverage_probes.urlparse(url).path,
        "status_code": status_code,
        "fetch_error": "",
        "content_type": "text/html",
        "page_evidence_class": evidence_class,
        "raw_html_truncated": False,
        "redirect_hop_count": 0,
        "title": title,
        "h1": h1,
        "meta_description": description,
        "word_count": word_count,
        "page_template_family": "product_page",
    }
    if access_kind:
        page["access_block_kind"] = access_kind
    return page


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


def test_soft_404_candidates_are_deterministic_scoped_and_capped_per_family():
    pages = [
        _accepted_page("https://example.com/fr/shop/a"),
        _accepted_page("https://example.com/fr/shop/b"),
        _accepted_page("https://example.com/fr/shop/c"),
        _accepted_page("https://example.com/fr/shop/d"),
        {**_accepted_page("https://example.com/fr/guide/one"), "page_template_family": "guide_article"},
        {**_accepted_page("https://example.com/fr/guide/two"), "page_template_family": "guide_article"},
        _accepted_page("https://example.com/outside/nope"),
    ]
    first = coverage_probes.build_soft_404_probe_candidates(
        "https://example.com", "/fr", pages
    )
    second = coverage_probes.build_soft_404_probe_candidates(
        "https://example.com", "/fr", pages
    )

    assert first == second
    assert first[0]["metadata"]["probe_kind"] == "scope_root"
    assert all(row["metadata"]["synthetic"] is True for row in first)
    assert all(coverage_probes.urlparse(row["url"]).path.startswith("/fr/") for row in first)
    assert all("__fixlist-missing-" in row["url"] for row in first)
    assert not ({row["url"] for row in first} & {page["url"] for page in pages})
    product_rows = [row for row in first if row["metadata"]["page_family"] == "product_page"]
    guide_rows = [row for row in first if row["metadata"]["page_family"] == "guide_article"]
    assert len(product_rows) == 3
    assert len(guide_rows) == 2
    assert all(row["metadata"]["representative_path"].startswith("/fr/") for row in product_rows + guide_rows)


def test_soft_404_baseline_requires_complete_accepted_missing_intent():
    probe = "https://example.com/__fixlist-missing-0123456789ab"
    missing = _accepted_page(
        probe,
        title="404 Page Not Found",
        h1="Page not found",
        description="We could not find this page",
        word_count=42,
    )
    baseline = coverage_probes.build_soft_404_baseline_record(
        missing,
        probe,
        {"synthetic": True, "probe_kind": "scope_root", "scope_prefix": "/"},
    )
    assert baseline["state"] == "fail"
    assert baseline["reason"] == "http_200_missing_intent_baseline"
    assert baseline["version"] == coverage_probes.SOFT_404_PROBE_VERSION
    assert baseline["provenance"] == "deterministic_nonexistent_path"
    assert baseline["intent_signals"]
    assert baseline["signature"]

    normal = coverage_probes.build_soft_404_baseline_record(
        _accepted_page(probe), probe, {"synthetic": True}
    )
    assert normal["state"] == "not_verified"
    assert normal["reason"] == "missing_intent_not_established"

    hard_missing = coverage_probes.build_soft_404_baseline_record(
        {**_accepted_page(probe, status_code=404), "page_evidence_class": "failed_http"}, probe
    )
    assert hard_missing["state"] == "pass"
    assert hard_missing["reason"] == "hard_missing_http_404"


def test_soft_404_baseline_rejects_challenge_and_incomplete_content():
    probe = "https://example.com/__fixlist-missing-0123456789ab"
    challenge = coverage_probes.build_soft_404_baseline_record(
        _accepted_page(
            probe,
            title="404 Page Not Found",
            h1="Page not found",
            access_kind="challenge",
        ),
        probe,
    )
    assert challenge["state"] == "not_verified"
    assert challenge["reason"] == "challenge"

    incomplete = coverage_probes.build_soft_404_baseline_record(
        _accepted_page(
            probe,
            title="404 Page Not Found",
            h1="Page not found",
            evidence_class="incomplete_html",
        ),
        probe,
    )
    assert incomplete["state"] == "not_verified"
    assert incomplete["reason"] == "incomplete_html"


def test_active_soft_404_comparison_never_uses_unknown_or_generic_baselines():
    page = _accepted_page(
        "https://example.com/catalog/gone",
        title="404 Page Not Found",
        h1="Page not found",
        description="We could not find this page",
        word_count=38,
    )
    unknown = {
        "version": coverage_probes.SOFT_404_PROBE_VERSION,
        "state": "not_verified",
        "reason": "challenge",
        "intent_signals": ["page_not_found"],
        "signature_tokens": ["404", "page", "not", "found"],
    }
    result = coverage_probes.compare_page_to_soft_404_baselines(page, [unknown])
    assert result["state"] == "not_verified"
    assert result["reason"] == "no_verified_soft_404_baseline"

    generic = {
        "version": coverage_probes.SOFT_404_PROBE_VERSION,
        "state": "fail",
        "reason": "http_200_missing_intent_baseline",
        "intent_signals": [],
        "signature_tokens": ["home", "welcome"],
    }
    result = coverage_probes.compare_page_to_soft_404_baselines(page, [generic])
    assert result["state"] == "not_verified"


def test_active_soft_404_comparison_requires_missing_intent_and_similarity():
    probe = "https://example.com/__fixlist-missing-0123456789ab"
    baseline_page = _accepted_page(
        probe,
        title="404 Page Not Found",
        h1="Page not found",
        description="We could not find this page",
        word_count=44,
    )
    baseline = coverage_probes.build_soft_404_baseline_record(baseline_page, probe)
    baseline["signature_tokens"] = coverage_probes.soft_404_signature_tokens(baseline_page)

    missing_page = _accepted_page(
        "https://example.com/catalog/gone",
        title="404 Page Not Found",
        h1="Page not found",
        description="We could not find this page",
        word_count=51,
    )
    matched = coverage_probes.compare_page_to_soft_404_baselines(missing_page, [baseline])
    assert matched["state"] == "fail"
    assert matched["reason"] == "active_soft_404_baseline_match"
    assert matched["baseline_probe_url"] == probe
    assert matched["similarity"] == 1.0
    assert matched["intent_signals"]

    healthy = _accepted_page(
        "https://example.com/catalog/live",
        title="Blue running shoe",
        h1="Blue running shoe",
        description="Buy the blue running shoe",
        word_count=180,
    )
    not_missing = coverage_probes.compare_page_to_soft_404_baselines(healthy, [baseline])
    assert not_missing["state"] == "pass"
    assert not_missing["reason"] == "assessed_page_has_no_missing_intent"


def test_scheduler_authenticates_soft_404_purpose_version_and_synthetic_metadata():
    scheduler = coverage_probes.SharedCoverageProbeScheduler(
        max_probe_requests=4,
        shared_request_limit=20,
        initial_request_count=2,
        deadline=10**12,
    )
    probe = "https://example.com/__fixlist-missing-0123456789ab"
    metadata = {
        "synthetic": True,
        "probe_kind": "scope_root",
        "scope_prefix": "/",
        "untrusted_extra": "must not persist",
    }
    scheduler.register(purpose="soft_404_baseline", url=probe, metadata=metadata)
    [candidate] = scheduler.candidates("soft_404_baseline")
    assert candidate["metadata"] == {
        "synthetic": True,
        "probe_kind": "scope_root",
        "scope_prefix": "/",
    }
    scheduler.begin_candidate("soft_404_baseline")
    scheduler.record_result(
        "soft_404_baseline",
        probe,
        state="fail",
        reason="http_200_missing_intent_baseline",
        status_code=200,
        final_url=probe,
        metadata=metadata,
    )
    [observation] = scheduler.summary()["observations"]
    assert observation["version"] == coverage_probes.SOFT_404_PROBE_VERSION
    assert observation["evidence_ref"].startswith(coverage_probes.SOFT_404_PROBE_VERSION + ":")
    assert observation["metadata"]["synthetic"] is True
    assert "untrusted_extra" not in observation["metadata"]
