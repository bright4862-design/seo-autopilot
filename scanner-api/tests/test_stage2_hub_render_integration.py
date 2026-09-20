import pytest

from app.render_followup import run_render_followup
from app.stage2_hub_render_evidence import (
    HUB_RENDER_SCOPE,
    MAX_HUBS,
    build_hub_link_comparison,
    select_representative_hubs,
)
from app.stage2_reachability_provenance import (
    REACHABILITY_PROVENANCE_VERSION,
    REACHABILITY_SCOPE,
)


def _hub(url: str, family: str, *, suspected: bool = True, sources=None, status: int = 200, truncated: bool = False):
    usable = status == 200
    return {
        "url": url,
        "final_url": url,
        "status_code": status,
        "fetch_error": "" if usable else "access_limited",
        "page_evidence_class": "usable_html" if usable else "failed_access",
        "page_template_family": family,
        "client_rendering_suspected": suspected,
        "word_count": 20,
        "title": "",
        "h1": "",
        "schema_types": [],
        "reachability_provenance_version": REACHABILITY_PROVENANCE_VERSION,
        "reachability_scope": REACHABILITY_SCOPE,
        "reachability_evidence_state": "observed_sample" if usable else "not_verified",
        "observed_internal_inlink_count": len(sources or []),
        "internal_source_pages": list(sources or []),
        "internal_source_pages_truncated": truncated,
        "navigation_presence": None,
        "crawl_depth": 0 if family == "homepage" else 1,
        "sitewide_orphan_claim": False,
    }


def test_b12_selects_at_most_five_verified_structural_hubs_and_excludes_failed_pages():
    pages = [
        _hub("https://example.com/", "homepage"),
        _hub("https://example.com/c1", "collection_page"),
        _hub("https://example.com/locations", "location_landing"),
        _hub("https://example.com/compare", "comparison_page"),
        _hub("https://example.com/c2", "collection_page"),
        _hub("https://example.com/c3", "collection_page"),
        _hub("https://example.com/failed", "collection_page", status=429),
        _hub("https://example.com/product", "product_page"),
    ]

    selected = select_representative_hubs(pages)
    evidence = build_hub_link_comparison(pages)

    assert len(selected) == MAX_HUBS
    assert [page["url"] for page in selected[:4]] == [
        "https://example.com/",
        "https://example.com/c1",
        "https://example.com/locations",
        "https://example.com/compare",
    ]
    assert "https://example.com/failed" not in [page["url"] for page in selected]
    assert "https://example.com/product" not in [page["url"] for page in selected]
    assert evidence["eligible_hubs"] == 6
    assert evidence["selection_truncated"] is True


def test_b12_exact_retained_identity_ignores_unsampled_and_variant_render_links():
    home = "https://example.com/"
    exact = "https://example.com/Pricing?plan=Pro%2FAnnual"
    other = "https://example.com/collection"
    pages = [
        _hub(home, "homepage"),
        _hub(exact, "collection_page", sources=[home]),
        _hub(other, "collection_page", sources=[]),
    ]

    evidence = build_hub_link_comparison(
        pages,
        attempted_urls=[home],
        rendered_pages_by_url={
            home: {
                "links": [
                    "/Pricing?plan=Pro%2FAnnual#details",
                    "/pricing?plan=Pro%2FAnnual",
                    "/outside-sample",
                ]
            }
        },
    )

    home_row = next(row for row in evidence["hubs"] if row["hub_url"] == home)
    assert evidence["scope"] == HUB_RENDER_SCOPE
    assert home_row["state"] == "completed"
    assert home_row["raw_link_count"] == 1
    assert home_row["rendered_link_count"] == 1
    assert home_row["render_only_count"] == 0
    assert home_row["raw_only_count"] == 0
    assert exact not in home_row["render_only_samples"]
    assert "https://example.com/pricing?plan=Pro%2FAnnual" not in home_row["render_only_samples"]


def test_b12_preserves_explicit_empty_query_delimiter_identity():
    home = "https://example.com/"
    empty_query = "https://example.com/page?"
    plain = "https://example.com/page"
    pages = [
        _hub(home, "homepage"),
        _hub(empty_query, "collection_page", sources=[home]),
        _hub(plain, "collection_page", sources=[]),
    ]

    evidence = build_hub_link_comparison(
        pages,
        attempted_urls=[home],
        rendered_pages_by_url={home: {"links": ["/page?"]}},
    )
    row = next(item for item in evidence["hubs"] if item["hub_url"] == home)

    assert row["state"] == "completed"
    assert row["raw_link_count"] == 1
    assert row["rendered_link_count"] == 1
    assert row["render_only_count"] == 0
    assert row["raw_only_count"] == 0


def test_b12_truncated_b11_source_samples_fail_closed_instead_of_inventing_raw_absence():
    home = "https://example.com/"
    target = "https://example.com/collection"
    pages = [
        _hub(home, "homepage"),
        _hub(target, "collection_page", sources=["https://example.com/other"], truncated=True),
    ]

    evidence = build_hub_link_comparison(
        pages,
        attempted_urls=[home],
        rendered_pages_by_url={home: {"links": [target]}},
    )
    row = next(item for item in evidence["hubs"] if item["hub_url"] == home)

    assert row["state"] == "failed"
    assert row["reason"] == "raw_retained_link_evidence_incomplete"
    assert row["raw_link_count"] is None
    assert row["render_only_count"] is None


def test_b12_missing_renderer_link_collection_is_failed_not_an_empty_success():
    home = "https://example.com/"
    pages = [_hub(home, "homepage")]

    evidence = build_hub_link_comparison(
        pages,
        attempted_urls=[home],
        rendered_pages_by_url={home: {"word_count": 200}},
    )

    row = evidence["hubs"][0]
    assert row["state"] == "failed"
    assert row["reason"] == "rendered_link_evidence_unavailable"
    assert row["rendered_link_count"] is None
    assert evidence["failed"] == 1


@pytest.mark.asyncio
async def test_b12_reuses_existing_three_page_render_budget_and_discloses_unassessed_hubs():
    home = "https://example.com/"
    c1 = "https://example.com/c1"
    locations = "https://example.com/locations"
    compare = "https://example.com/compare"
    c2 = "https://example.com/c2"
    pages = [
        _hub(home, "homepage"),
        _hub(c1, "collection_page", sources=[home]),
        _hub(locations, "location_landing", sources=[home]),
        _hub(compare, "comparison_page", sources=[home]),
        _hub(c2, "collection_page", sources=[c1]),
    ]
    calls = []

    async def renderer(url):
        calls.append(url)
        if url == locations:
            raise RuntimeError("browser timeout")
        return {
            "word_count": 180,
            "title": "Rendered",
            "h1": "Rendered",
            "schema_types": [],
            "links": [c1, locations, compare],
        }

    result = await run_render_followup(pages, renderer)
    b12 = result["hub_link_comparison"]

    assert len(calls) == 3
    assert result["attempted_pages"] == 3
    assert b12["selected"] == 5
    assert b12["completed"] == 2
    assert b12["failed"] == 1
    assert b12["unassessed"] == 2
    assert b12["evidence_state"] == "partial"
    assert b12["interpretation"] == "paired_comparison_neither_surface_is_sole_truth"
    assert next(row for row in b12["hubs"] if row["hub_url"] == compare)["state"] == "unassessed"
    assert next(row for row in b12["hubs"] if row["hub_url"] == c2)["state"] == "unassessed"


@pytest.mark.asyncio
async def test_b12_without_renderer_stays_unassessed_and_does_not_invent_rendered_links():
    pages = [
        _hub("https://example.com/", "homepage"),
        _hub("https://example.com/c1", "collection_page", sources=["https://example.com/"]),
    ]

    result = await run_render_followup(pages, render_page=None)
    b12 = result["hub_link_comparison"]

    assert result["status"] == "recommended_not_run"
    assert b12["selected"] == 2
    assert b12["completed"] == 0
    assert b12["failed"] == 0
    assert b12["unassessed"] == 2
    assert b12["evidence_state"] == "not_assessed"
    assert all(row["rendered_link_count"] is None for row in b12["hubs"])
