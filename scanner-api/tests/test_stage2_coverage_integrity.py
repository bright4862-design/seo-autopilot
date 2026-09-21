from app.coverage_probes import SharedCoverageProbeScheduler
from app.sitemap_integrity_evidence import (
    SITEMAP_INTEGRITY_EVIDENCE_VERSION,
    build_sitemap_source_evidence,
    classify_sitemap_target,
    register_sitemap_target_candidates,
    sitemap_coverage_from_scheduler,
)
from app.url_variant_evidence import (
    URL_VARIANT_EVIDENCE_VERSION,
    build_url_variant_candidates,
    classify_url_variant,
    register_url_variant_candidates,
    url_variant_coverage_from_scheduler,
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
    assert result["eligible_unsampled"] == 1
    assert result["skipped_assessed"] == 1
    assert result["skipped_outside_scope"] == 2
    assert result["assessed_page_count_unchanged"] is True
    [candidate] = scheduler.candidates("sitemap_target")
    assert candidate["url"] == "https://example.com/shop/missing"
    assert candidate["source_pages"] == ["https://example.com/products.xml"]
    assert candidate["metadata"]["probe_kind"] == "sitemap_target"
    assert candidate["metadata"]["synthetic"] is False


def test_b09_dedupes_request_identity_and_retains_multiple_sitemap_sources():
    scheduler = _scheduler()
    target = "https://example.com/shop/item"
    result = register_sitemap_target_candidates(
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
    assert result["registered"] == 1
    assert candidate["url"] == target
    assert candidate["source_pages"] == [
        "https://example.com/products-a.xml",
        "https://example.com/products-b.xml",
    ]
    assert scheduler.summary()["purposes"]["sitemap_target"]["eligible"] == 1


def test_b09_registration_discloses_truncation_without_expanding_assessed_pages():
    scheduler = _scheduler()
    entries = [
        {"url": f"https://example.com/shop/{index}", "sitemap_url": "https://example.com/products.xml"}
        for index in range(5)
    ]
    registration = register_sitemap_target_candidates(
        scheduler,
        entries,
        assessed_urls=["https://example.com/shop/assessed"],
        origin="https://example.com",
        scope_prefix="/shop",
        max_candidates=2,
    )
    assert registration["eligible_unsampled"] == 5
    assert registration["registered"] == 2
    assert registration["truncated"] is True
    assert registration["assessed_page_count_unchanged"] is True
    assert len(scheduler.candidates("sitemap_target")) == 2

    coverage = sitemap_coverage_from_scheduler(scheduler.summary(), registration=registration)
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "candidate_universe_truncated"
    assert coverage["eligible_unsampled"] == 5
    assert coverage["candidate_universe_truncated"] is True


def test_b09_classifies_verified_missing_noindex_redirect_and_app_shell_conflicts():
    requested = "https://example.com/shop/item"
    sources = ["https://example.com/products.xml"]

    missing = classify_sitemap_target(
        _page(requested, status=404, evidence_class="failed_http"),
        requested_url=requested,
        sitemap_sources=sources,
    )
    assert (missing["state"], missing["reason"]) == ("fail", "sitemap_target_http_404")

    noindex = classify_sitemap_target(_page(requested, noindex=True), requested_url=requested, sitemap_sources=sources)
    assert (noindex["state"], noindex["reason"]) == ("fail", "sitemap_target_noindex")

    redirected = classify_sitemap_target(
        _page(requested, final_url="https://example.com/shop/new-item", redirect_hops=1),
        requested_url=requested,
        sitemap_sources=sources,
    )
    assert (redirected["state"], redirected["reason"]) == ("fail", "sitemap_target_redirected")

    shell = classify_sitemap_target(_page(requested, app_shell=True), requested_url=requested, sitemap_sources=sources)
    assert (shell["state"], shell["reason"]) == ("fail", "sitemap_target_app_shell")
    assert shell["sitemap_sources"] == sources


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
    result = classify_sitemap_target(_page(requested), requested_url=requested, sitemap_sources=[source])
    assert result["version"] == SITEMAP_INTEGRITY_EVIDENCE_VERSION
    assert result["state"] == "pass"
    assert result["reason"] == "sitemap_target_usable_indexable_html"
    assert result["requested_url"] == requested
    assert result["sitemap_sources"] == [source]


def test_b09_source_diagnostics_fail_closed_when_failure_reason_is_not_attributed_to_source():
    evidence = build_sitemap_source_evidence(
        {
            "sitemap_sources": [
                {
                    "url": "https://example.com/products.xml",
                    "source": "robots_declared",
                    "outcome": "failed",
                    "loc_count": 0,
                },
                {
                    "url": "https://example.com/sitemap.xml",
                    "source": "speculative_default",
                    "outcome": "urls",
                    "loc_count": 12,
                },
            ],
            "sitemap_failure_reason_buckets": {"http_403": 1},
        }
    )
    declared, default, coverage = evidence
    assert declared["state"] == "not_verified"
    assert declared["reason"] == "sitemap_source_retrieval_failed_reason_unattributed"
    assert default["state"] == "pass"
    assert coverage["state"] == "not_verified"
    assert coverage["failure_reason_buckets"] == {"http_403": 1}


def test_b09_exact_source_failure_reason_distinguishes_known_missing_from_access_limited():
    evidence = build_sitemap_source_evidence(
        {
            "sitemap_sources": [
                {"url": "https://example.com/missing.xml", "source": "robots_declared", "outcome": "failed", "reason": "http_404"},
                {"url": "https://example.com/blocked.xml", "source": "robots_declared", "outcome": "failed", "reason": "http_403"},
            ]
        }
    )
    missing, blocked = evidence
    assert (missing["state"], missing["reason"]) == ("fail", "sitemap_source_http_404")
    assert (blocked["state"], blocked["reason"]) == ("not_verified", "sitemap_source_http_403")


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


def test_b16_path_mutation_preserves_empty_query_delimiter_as_identity_evidence():
    source = "https://example.com/Page?"
    rows = build_url_variant_candidates([source], origin="https://example.com", max_candidates=2)
    by_kind = {row["kind"]: row for row in rows}
    assert by_kind["slash"]["probe_url"] == "https://example.com/Page/?"
    assert by_kind["case"]["probe_url"] == "https://example.com/page?"
    assert all(row["source_url"] == source for row in rows)


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


def test_b16_candidate_limit_is_reported_and_cannot_be_described_as_full_coverage():
    sources = [f"https://example.com/shop/item-{index}" for index in range(4)]
    rows = build_url_variant_candidates(sources, origin="https://example.com", max_candidates=2)
    assert len(rows) == 2
    assert all(row["eligible_candidate_count"] == 8 for row in rows)
    assert all(row["candidate_universe_truncated"] is True for row in rows)

    scheduler = _scheduler(max_probe_requests=5)
    register_url_variant_candidates(scheduler, rows)
    for row in rows:
        scheduler.begin_candidate("url_variant")
        scheduler.record_result(
            "url_variant",
            row["probe_url"],
            state="pass",
            reason="variant_not_published",
            status_code=404,
            final_url=row["probe_url"],
        )
    coverage = url_variant_coverage_from_scheduler(scheduler.summary(), candidates=rows)
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "candidate_universe_truncated"
    assert coverage["eligible"] == 2
    assert coverage["eligible_candidate_count"] == 8


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


def test_b16_distinct_live_case_variant_stays_unknown_without_equivalence_evidence():
    source_url = "https://example.com/Product"
    probe_url = "https://example.com/product"
    candidate = {
        "source_url": source_url,
        "probe_url": probe_url,
        "kind": "case",
        "synthetic": True,
    }
    result = classify_url_variant(_page(source_url), _page(probe_url), candidate)
    assert result["state"] == "not_verified"
    assert result["reason"] == "distinct_live_variant_requires_equivalence_evidence"
    assert result["source_url"] == source_url
    assert result["probe_url"] == probe_url
    assert result["source_final_url"] != result["variant_final_url"]


def test_b16_distinct_meaningful_query_variant_stays_unknown_without_equivalence():
    source_url = "https://example.com/search?brand=Acme&sort=price"
    probe_url = "https://example.com/search?brand=Acme&sort=rating"
    candidate = {
        "source_url": source_url,
        "probe_url": probe_url,
        "kind": "meaningful_parameter",
        "synthetic": False,
    }
    result = classify_url_variant(_page(source_url), _page(probe_url), candidate)
    assert (result["state"], result["reason"]) == (
        "not_verified",
        "distinct_live_variant_requires_equivalence_evidence",
    )
    assert result["source_url"].endswith("?brand=Acme&sort=price")
    assert result["probe_url"].endswith("?brand=Acme&sort=rating")


def test_b16_live_noindex_variant_does_not_become_duplicate_risk():
    source_url = "https://example.com/page"
    probe_url = "https://example.com/Page"
    candidate = {"source_url": source_url, "probe_url": probe_url, "kind": "case", "synthetic": True}
    result = classify_url_variant(_page(source_url), _page(probe_url, noindex=True), candidate)
    assert result["state"] == "not_verified"
    assert result["reason"] == "live_noindex_variant_requires_policy_judgment"


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


def test_shared_scheduler_exhaustion_projects_as_unknown_sitemap_coverage():
    scheduler = _scheduler(max_probe_requests=0)
    target = "https://example.com/shop/item"
    scheduler.register(purpose="sitemap_target", url=target)
    assert scheduler.can_start_candidate("sitemap_target", target) is False
    scheduler.record_exhausted("sitemap_target", target)

    coverage = sitemap_coverage_from_scheduler(scheduler.summary())
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
    coverage = url_variant_coverage_from_scheduler(scheduler.summary())
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "eligible_url_variants_not_fully_checked"
    assert coverage["eligible"] == 2
    assert coverage["completed"] == 1
