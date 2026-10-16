from app.stage2_reachability_provenance import (
    REACHABILITY_PROVENANCE_VERSION,
    REACHABILITY_SCOPE,
    enrich_pages_with_reachability_provenance,
    ensure_reachability_record,
    observed_crawl_depths,
    record_internal_link_observation,
)


def _page(url: str, **extra):
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "fetch_error": "",
        "raw_html_truncated": False,
        "page_evidence_class": "usable_html",
        **extra,
    }


def _record():
    return ensure_reachability_record(
        {"discovered_from": [], "source_pages": [], "link_text_samples": []}
    )


def test_navigation_link_produces_depth_one_and_verified_inlink_without_changing_page_count():
    seed = "https://example.com/"
    pricing = "https://example.com/Pricing?plan=Pro%2FAnnual"
    pages = [_page(seed), _page(pricing, page_template_family="pricing_page")]
    discovery = {seed: _record(), pricing: _record()}
    record_internal_link_observation(
        discovery[pricing],
        source_url=seed,
        source_usable_html=True,
        navigation_presence=True,
    )

    before = list(page["url"] for page in pages)
    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)

    assert [page["url"] for page in pages] == before
    row = pages[1]
    assert row["reachability_provenance_version"] == REACHABILITY_PROVENANCE_VERSION
    assert row["reachability_scope"] == REACHABILITY_SCOPE
    assert row["observed_internal_inlink_count"] == 1
    assert row["internal_source_pages"] == [seed]
    assert row["crawl_depth"] == 1
    assert row["navigation_presence"] is True
    assert row["sitewide_orphan_claim"] is False
    # Evidence identity preserves case, query order and reserved-escape spelling.
    assert row["url"] == pricing


def test_sitemap_only_money_page_has_known_zero_observed_inlinks_but_unknown_depth_and_navigation():
    seed = "https://example.com/"
    pricing = "https://example.com/pricing"
    pages = [_page(seed), _page(pricing, page_template_family="pricing_page")]
    discovery = {
        seed: _record(),
        pricing: {
            **_record(),
            "discovered_from": ["sitemap"],
            "source_pages": ["/sitemap.xml"],
        },
    }

    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)
    row = pages[1]
    assert row["observed_internal_inlink_count"] == 0
    assert row["internal_source_pages"] == []
    assert row["crawl_depth"] is None
    assert row["navigation_presence"] is None
    assert row["sitewide_orphan_claim"] is False


def test_content_only_link_records_navigation_false_not_sitewide_orphaning():
    seed = "https://example.com/"
    product = "https://example.com/product/widget"
    pages = [_page(seed), _page(product, page_template_family="product_page")]
    discovery = {seed: _record(), product: _record()}
    record_internal_link_observation(
        discovery[product],
        source_url=seed,
        source_usable_html=True,
        navigation_presence=False,
    )

    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)
    row = pages[1]
    assert row["observed_internal_inlink_count"] == 1
    assert row["crawl_depth"] == 1
    assert row["navigation_presence"] is False
    assert row["sitewide_orphan_claim"] is False


def test_challenged_or_unusable_source_cannot_become_verified_reachability_evidence():
    seed = "https://example.com/"
    challenged = "https://example.com/challenge"
    pricing = "https://example.com/pricing"
    pages = [
        _page(seed),
        {
            **_page(challenged),
            "page_evidence_class": "failed_access",
            "access_block_kind": "challenge",
        },
        _page(pricing, page_template_family="pricing_page"),
    ]
    discovery = {seed: _record(), challenged: _record(), pricing: _record()}
    record_internal_link_observation(
        discovery[pricing],
        source_url=challenged,
        source_usable_html=False,
        navigation_presence=True,
    )
    # Even if a malformed producer tries to put the challenged source into the
    # verified list, final enrichment revalidates source-page evidence class.
    discovery[pricing]["reachability_internal_sources"].append(challenged)
    discovery[pricing]["reachability_navigation_sources"].append(challenged)

    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)
    row = pages[2]
    assert row["observed_internal_inlink_count"] == 0
    assert row["internal_source_pages"] == []
    assert row["crawl_depth"] is None
    assert row["navigation_presence"] is None


def test_shortest_observed_depth_is_independent_of_discovery_order():
    seed = "https://example.com/"
    a = "https://example.com/a"
    b = "https://example.com/b"
    pricing = "https://example.com/pricing"
    pages = [_page(seed), _page(a), _page(b), _page(pricing, page_template_family="pricing_page")]
    discovery = {url: _record() for url in (seed, a, b, pricing)}
    # Long path seed -> a -> b -> pricing is recorded first.
    record_internal_link_observation(discovery[a], source_url=seed, source_usable_html=True, navigation_presence=False)
    record_internal_link_observation(discovery[b], source_url=a, source_usable_html=True, navigation_presence=False)
    record_internal_link_observation(discovery[pricing], source_url=b, source_usable_html=True, navigation_presence=False)
    # A later observed navigation link creates the truthful shortest depth 1.
    record_internal_link_observation(discovery[pricing], source_url=seed, source_usable_html=True, navigation_presence=True)

    depths = observed_crawl_depths(pages, discovery, seed_url=seed)
    assert depths[a] == 1
    assert depths[b] == 2
    assert depths[pricing] == 1

    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)
    assert pages[-1]["crawl_depth"] == 1
    assert pages[-1]["observed_internal_inlink_count"] == 2
    assert pages[-1]["navigation_presence"] is True


def test_unaccepted_target_gets_no_zero_or_depth_claim():
    seed = "https://example.com/"
    failed = "https://example.com/pricing"
    pages = [
        _page(seed),
        {
            "url": failed,
            "final_url": failed,
            "status_code": 429,
            "fetch_error": "",
            "page_evidence_class": "failed_access",
            "raw_html_truncated": False,
            "page_template_family": "pricing_page",
        },
    ]
    discovery = {seed: _record(), failed: _record()}
    record_internal_link_observation(
        discovery[failed], source_url=seed, source_usable_html=True, navigation_presence=True
    )

    enrich_pages_with_reachability_provenance(pages, discovery, seed_url=seed)
    row = pages[1]
    assert row["reachability_evidence_state"] == "not_verified"
    assert row["observed_internal_inlink_count"] is None
    assert row["crawl_depth"] is None
    assert row["navigation_presence"] is None
