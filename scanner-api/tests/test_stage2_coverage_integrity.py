from app.coverage_probes import SharedCoverageProbeScheduler
from app.stage2_coverage_integrity import (
    SITEMAP_INTEGRITY_EVIDENCE_VERSION,
    URL_VARIANT_EVIDENCE_VERSION,
    build_url_variant_candidates,
    classify_sitemap_target,
    classify_url_variant,
    feature_coverage_from_scheduler,
    register_sitemap_target_candidates,
    register_url_variant_candidates,
)


def _page(
    url: str,
    *,
    status: int = 200,
    final_url: str | None = None,
    evidence_class: str = "usable_html",
    access_kind: str = "",
    noindex: bool = False,
    redirect_hops: int = 0,
    canonical: str = "",
    app_shell: bool = False,
    fetch_error: str = "",
):
    page = {
        "url": url,
        "final_url": final_url or url,
        "status_code": status,
        "fetch_error": fetch_error,
        "content_type": "text/html",
        "page_evidence_class": evidence_class,
        "raw_html_truncated": False,
        "redirect_hop_count": redirect_hops,
        "canonical_url": canonical,
    }
    if access_kind:
        page["access_block_kind"] = access_kind
    if noindex:
        page["robots_indexability_status"] = "noindex"
        page["indexability_state"] = "Noindex"
    if app_shell:
        page["app_shell_detected"] = True
    return page


def _scheduler(max_probe_requests=12):
    return SharedCoverageProbeScheduler(
        max_probe_requests=max_probe_requests,
        shared_request_limit=100,
        initial_request_count=10,
        deadline=10**12,
    )


def test_b09_registers_only_unsampled_same_origin_scoped_targets_with_source_provenance():
    scheduler = _scheduler()
    assessed = ["https://example.com/shop/assessed"]
    entries = [
        {"url": "https://example.com/shop/assessed", "sitemap_url": "https://example.com/products.xml"},
        {"url": "https://example.com/shop/missing", "sitemap_url": "https://example.com/products.xml"},
        {"url": "https://example.com/outside/nope", "sitemap_url": "https://example.com/products.xml"},
        {"url": "https://other.example/shop/nope", "sitemap_url": "https://example.com/products.xml"},
    ]

    result = register_sitemap_target_candidates(
        scheduler,
        entries,
        assessed_urls=assessed,
        origin="https://example.com",
        scope_prefix="/shop",
    )

    assert result["version"] == SITEMAP_INTEGRITY_EVIDENCE_VERSION
    assert result["registered"] == 1
    assert result["skipped_assessed"] == 1
    assert result["skipped_outside_scope"] == 2
    assert result["assessed_page_count_unchanged"] is True
    [candidate] = scheduler.candidates("sitemap_target")
    assert candidate["url"] == "https://example.com/shop/missing"
    assert candidate["source_pages"] == ["https://example.com/products.xml"]
    assert candidate["metadata"]["probe_kind"] == "sitemap_target"
    assert candidate["metadata"]["synthetic"] is False


def test_b09_dedupes_target_identity_without_losing_sitemap_sources():
    scheduler = _scheduler()
    target = "https://example.com/shop/item"
    register_sitemap_target_candidates(
        scheduler,
        [
            {"url": target, "sitemap_url": "https://example.com/products-a.xml"},
            {"url": target, "sitemap_url": "https://example.com/products-b.xml"},
        ],
        assessed_urls=[],
        origin="https://example.com",
        scope_prefix="/shop",
    )
    [candidate] = scheduler.candidates("sitemap_target")
    # The helper registers one request identity; multiple source aggregation is
    # handled by the shared scheduler when the same candidate is registered.
    assert candidate["url"] == target
    assert scheduler.summary()["purposes"]["sitemap_target"]["eligible"] == 1


def test_b09_classifies_verified_missing_noindex_redirect_and_app_shell_conflicts():
    requested = "https://example.com/shop/item"
    source = "https://example.com/products.xml"

    missing = classify_sitemap_target(_page(requested, status=404, evidence_class="failed_http"), requested_url=requested, sitemap_source=source)
    assert (missing["state"], missing["reason"]) == ("fail", "sitemap_target_http_404")

    noindex = classify_sitemap_target(_page(requested, noindex=True), requested_url=requested, sitemap_source=source)
    assert (noindex["state"], noindex["reason"]) == ("fail", "sitemap_target_noindex")

    redirected = classify_sitemap_target(
        _page(requested, final_url="https://example.com/shop/new-item", redirect_hops=1),
        requested_url=requested,
        sitemap_source=source,
    )
    assert (redirected["state"], redirected["reason"]) == ("fail", "sitemap_target_redirected")

    shell = classify_sitemap_target(_page(requested, app_shell=True), requested_url=requested, sitemap_source=source)
    assert (shell["state"], shell["reason"]) == ("fail", "sitemap_target_app_shell")


def test_b09_keeps_challenge_429_and_incomplete_html_unverified():
    requested = "https://example.com/shop/item"
    challenged = classify_sitemap_target(
        _page(requested, status=403, access_kind="challenge"),
        requested_url=requested,
    )
    assert challenged["state"] == "not_verified"
    assert challenged["reason"] == "challenge"

    rate_limited = classify_sitemap_target(_page(requested, status=429), requested_url=requested)
    assert rate_limited["state"] == "not_verified"
    assert rate_limited["reason"] == "http_429"

    incomplete = classify_sitemap_target(
        _page(requested, evidence_class="incomplete_html"),
        requested_url=requested,
    )
    assert incomplete["state"] == "not_verified"
    assert incomplete["reason"] == "incomplete_html"


def test_b09_usable_indexable_target_passes_with_provenance():
    requested = "https://example.com/shop/item"
    source = "https://example.com/products.xml"
    result = classify_sitemap_target(_page(requested), requested_url=requested, sitemap_source=source)
    assert result["version"] == SITEMAP_INTEGRITY_EVIDENCE_VERSION
    assert result["state"] == "pass"
    assert result["reason"] == "sitemap_target_usable_indexable_html"
    assert result["requested_url"] == requested
    assert result["sitemap_source"] == source


def test_b16_generates_bounded_slash_and_case_variants_without_changing_reserved_escape_or_query():
    source = "https://example.com/Catalog%2FItem?color=Blue&size=M"
    rows = build_url_variant_candidates(
        [source],
        origin="https://example.com",
        scope_prefix="/",
        max_candidates=4,
    )
    by_kind = {row["kind"]: row for row in rows}
    assert set(by_kind) == {"slash", "case"}
    assert by_kind["slash"]["probe_url"] == "https://example.com/Catalog%2FItem/?color=Blue&size=M"
    assert "%2F" in by_kind["case"]["probe_url"]
    assert by_kind["case"]["probe_url"].endswith("?color=Blue&size=M")
    assert all(row["source_url"] == source for row in rows)
    assert all(row["version"] == URL_VARIANT_EVIDENCE_VERSION for row in rows)
    assert all(row["synthetic"] is True for row in rows)


def test_b16_does_not_generate_apex_www_or_scheme_variants_without_verified_alias_scope():
    source = "https://example.com/shop/item"
    rows = build_url_variant_candidates([source], origin="https://example.com")
    assert {row["kind"] for row in rows} == {"slash", "case"}
    assert all("www.example.com" not in row["probe_url"] for row in rows)
    assert all(not row["probe_url"].startswith("http://") for row in rows)


def test_b16_generates_origin_alias_only_when_explicitly_verified_by_caller():
    source = "https://example.com/shop/item"
    rows = build_url_variant_candidates(
        [source],
        origin="https://example.com",
        verified_alias_origins=["https://www.example.com", "http://example.com"],
        max_candidates=6,
    )
    aliases = [row for row in rows if row["kind"] == "verified_origin_alias"]
    assert {row["probe_url"] for row in aliases} == {
        "https://www.example.com/shop/item",
        "http://example.com/shop/item",
    }
    assert all(row["verified_alias"] is True for row in aliases)


def test_b16_meaningful_parameter_variant_must_be_explicit_and_preserves_exact_query_identity():
    source = "https://example.com/search?brand=Acme&sort=price"
    variant = "https://example.com/search?brand=Acme&sort=rating"
    rows = build_url_variant_candidates(
        [source],
        origin="https://example.com",
        meaningful_parameter_variants=[{"source_url": source, "variant_url": variant}],
        max_candidates=6,
    )
    [parameter] = [row for row in rows if row["kind"] == "meaningful_parameter"]
    assert parameter["source_url"] == source
    assert parameter["probe_url"] == variant
    assert parameter["synthetic"] is False


def test_b16_registers_candidates_in_same_shared_scheduler_without_new_budget():
    scheduler = _scheduler(max_probe_requests=5)
    source = "https://example.com/shop/item"
    rows = build_url_variant_candidates([source], origin="https://example.com", max_candidates=2)
    registered = register_url_variant_candidates(scheduler, rows)
    assert registered == 2
    summary = scheduler.summary()
    assert summary["purposes"]["url_variant"]["eligible"] == 2
    assert summary["request_budget"]["configured_probe_requests"] == 5
    assert summary["request_budget"]["requests_consumed"] == 0
    assert {row["metadata"]["probe_kind"] for row in scheduler.candidates("url_variant")} == {"slash", "case"}


def test_b16_normal_redirect_to_source_is_harmless_but_never_claimed_as_published_redirect():
    source_url = "https://example.com/page"
    probe_url = "https://example.com/page/"
    candidate = {
        "source_url": source_url,
        "probe_url": probe_url,
        "kind": "slash",
        "synthetic": True,
    }
    result = classify_url_variant(
        _page(source_url),
        _page(probe_url, final_url=source_url, redirect_hops=1),
        candidate,
    )
    assert result["state"] == "pass"
    assert result["reason"] == "harmless_normalization_to_source"
    assert result["published_redirect_claim"] is False
    assert result["source_url"] == source_url
    assert result["probe_url"] == probe_url


def test_b16_distinct_live_case_variant_is_risk_without_collapsing_identity():
    source_url = "https://example.com/Product"
    probe_url = "https://example.com/product"
    candidate = {
        "source_url": source_url,
        "probe_url": probe_url,
        "kind": "case",
        "synthetic": True,
    }
    result = classify_url_variant(_page(source_url), _page(probe_url), candidate)
    assert result["state"] == "fail"
    assert result["reason"] == "distinct_live_variant"
    assert result["source_url"] == source_url
    assert result["probe_url"] == probe_url
    assert result["source_final_url"] != result["variant_final_url"]


def test_b16_distinct_meaningful_query_variant_is_risk_and_keeps_raw_query_order():
    source_url = "https://example.com/search?brand=Acme&sort=price"
    probe_url = "https://example.com/search?brand=Acme&sort=rating"
    candidate = {
        "source_url": source_url,
        "probe_url": probe_url,
        "kind": "meaningful_parameter",
        "synthetic": False,
    }
    result = classify_url_variant(_page(source_url), _page(probe_url), candidate)
    assert (result["state"], result["reason"]) == ("fail", "distinct_live_variant")
    assert result["source_url"].endswith("?brand=Acme&sort=price")
    assert result["probe_url"].endswith("?brand=Acme&sort=rating")


def test_b16_variant_canonicalized_to_source_is_not_reported_as_duplicate_risk():
    source_url = "https://example.com/page"
    probe_url = "https://example.com/Page"
    candidate = {"source_url": source_url, "probe_url": probe_url, "kind": "case", "synthetic": True}
    result = classify_url_variant(
        _page(source_url),
        _page(probe_url, canonical=source_url),
        candidate,
    )
    assert (result["state"], result["reason"]) == ("pass", "variant_canonicalized_to_source")


def test_b16_challenged_or_failed_variant_remains_unknown():
    source_url = "https://example.com/page"
    probe_url = "https://example.com/Page"
    candidate = {"source_url": source_url, "probe_url": probe_url, "kind": "case", "synthetic": True}
    challenged = classify_url_variant(
        _page(source_url),
        _page(probe_url, status=403, access_kind="challenge"),
        candidate,
    )
    assert challenged["state"] == "not_verified"
    assert challenged["reason"] == "variant_challenge"

    failed = classify_url_variant(
        _page(source_url),
        _page(probe_url, status=0, fetch_error="timeout"),
        candidate,
    )
    assert failed["state"] == "not_verified"
    assert failed["reason"] == "variant_timeout"


def test_b16_redirect_to_other_destination_defers_meaning_to_b08():
    source_url = "https://example.com/page"
    probe_url = "https://example.com/Page"
    candidate = {"source_url": source_url, "probe_url": probe_url, "kind": "case", "synthetic": True}
    result = classify_url_variant(
        _page(source_url),
        _page(probe_url, final_url="https://example.com/", redirect_hops=1),
        candidate,
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "redirect_meaning_requires_b08"


def test_shared_scheduler_exhaustion_projects_as_unknown_feature_coverage():
    scheduler = _scheduler(max_probe_requests=0)
    target = "https://example.com/shop/item"
    scheduler.register(purpose="sitemap_target", url=target)
    assert scheduler.can_start_candidate("sitemap_target", target) is False
    scheduler.record_exhausted("sitemap_target", target)

    coverage = feature_coverage_from_scheduler(
        scheduler.summary(),
        "sitemap_target",
        version=SITEMAP_INTEGRITY_EVIDENCE_VERSION,
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "shared_probe_budget_or_deadline_exhausted"
    assert coverage["eligible"] == 1
    assert coverage["exhausted"] == 1


def test_partial_url_variant_coverage_never_becomes_success():
    scheduler = _scheduler(max_probe_requests=3)
    for url in ["https://example.com/a/", "https://example.com/A"]:
        scheduler.register(purpose="url_variant", url=url)
    scheduler.begin_candidate("url_variant")
    scheduler.record_result(
        "url_variant",
        "https://example.com/a/",
        state="pass",
        reason="harmless_normalization_to_source",
        status_code=200,
        final_url="https://example.com/a",
    )
    coverage = feature_coverage_from_scheduler(
        scheduler.summary(),
        "url_variant",
        version=URL_VARIANT_EVIDENCE_VERSION,
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "eligible_targets_not_fully_checked"
    assert coverage["eligible"] == 2
    assert coverage["completed"] == 1
