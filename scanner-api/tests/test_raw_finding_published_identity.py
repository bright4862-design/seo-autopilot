"""Exercise raw producers through the current scanner and review boundary."""

import pytest

from app import scanner
from app.extract import extract_page
from app.main import apply_post_crawl_transforms
from app.metadata_title_evidence import relative_evidence_url
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.scan_job import build_local_review


ORIGIN = "https://example.com"
CURRENT = {"identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, "scan_origin": ORIGIN}


def html(*, title="", body="<h1>Useful product</h1><p>Useful product details.</p>"):
    return f"<html><head>{'<title>' + title + '</title>' if title else ''}</head><body>{body}</body></html>"


def page(url, **kwargs):
    value = extract_page(html(**kwargs), url, url, 200, "text/html", {"discovered_from": ["internal_link"]})
    value["page_template_family"] = "activity_detail"
    return value


def current_scan(pages):
    raw = scanner.build_findings(pages, **CURRENT)
    return {"success": True, "website_url": ORIGIN, "crawl_scope": {"requested_origin": ORIGIN},
            "pages": pages, "pages_found": len(pages), "pages_crawled": len(pages),
            "raw_findings": raw, "findings": scanner.group_findings(raw)}


def assert_persisted_customer_output(result, rule, urls, *, eligible):
    import json
    from pathlib import Path
    import subprocess
    completed = subprocess.run(["node", "tests/helpers/assertPublishedEvidenceOutput.mjs"],
        input=json.dumps({"scan": result, "review": build_local_review(result), "expectedUrls": urls,
                          "expectedRule": rule, "expectedEligible": eligible}),
        text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2], timeout=30)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("route", ["/x", "/x;v=1", "/x?", "/a%2Fb?b=2&a=1&a=0", "/a/../x", "/café"])
def test_raw_title_evidence_keeps_observed_route_through_real_review(route):
    url = ORIGIN + route
    result = current_scan([page(url)])
    [raw] = [row for row in result["raw_findings"] if row["rule"] == "missing_title"]
    assert raw["page_url"] == url
    [repair] = [row for row in build_local_review(result)["canonical_repairs"] if row["rule"] == "missing_title"]
    assert repair["affected_pages"] == [url]
    assert repair["page_count"] == 1


def test_current_helper_retains_foreign_origin_and_legacy_helper_is_unchanged():
    observed = page("https://www.example.com/x;v=1?")
    assert relative_evidence_url(observed, **CURRENT) == "https://www.example.com/x;v=1?"
    assert relative_evidence_url(observed) == "/x"


@pytest.mark.parametrize("proof", [None, {"html_parse_ok": True, "final_status": 200, "final_url": ORIGIN + "/other"},
                                 {"html_parse_ok": False, "final_status": 200, "final_url": ORIGIN + "/destination"},
                                 {"html_parse_ok": True, "final_status": 403, "final_url": ORIGIN + "/destination"}])
def test_unverified_final_url_cannot_replace_the_observed_request(proof):
    requested = ORIGIN + "/observed;v=1?"
    observed = page(requested, body='<h1>Useful page</h1><figure><img src="subject.jpg"><figcaption>The subject</figcaption></figure>')
    observed["final_url"] = ORIGIN + "/destination"
    if proof is not None:
        observed["redirect_fetch_evidence"] = proof
    assert relative_evidence_url(observed, **CURRENT) == requested
    result = current_scan([observed])
    for rows in (result["raw_findings"], build_local_review(result)["canonical_repairs"]):
        for rule in ("missing_title", "image_alt_text"):
            [repair] = [row for row in rows if row["rule"] == rule]
            assert repair["affected_pages"] == [requested]


def test_verified_content_destination_and_redirect_source_remain_separate():
    requested, destination = ORIGIN + "/old;v=1?", "https://www.example.com/final;v=1?"
    observed = page(requested)
    observed.update(final_url=destination, redirect_hop_count=1, redirect_state="redirected",
                    redirect_destination_status_code=200, redirect_destination_indexability_state="Indexable",
                    redirect_destination_url=destination, redirect_destination_indexable=True,
                    redirect_fetch_evidence={"html_parse_ok": True, "final_status": 200, "final_url": destination})
    result = current_scan([observed])
    [redirect] = [row for row in result["raw_findings"] if row["rule"] == "internal_link_redirect"]
    [title] = [row for row in result["raw_findings"] if row["rule"] == "missing_title"]
    assert redirect["affected_pages"] == [requested]
    assert title["affected_pages"] == [destination]


def test_raw_duplicate_titles_keep_distinct_origin_and_empty_query():
    urls = [ORIGIN + "/x", ORIGIN + "/x?", "https://www.example.com/x", ORIGIN + "/x;v=1"]
    [finding] = scanner.duplicate_title_findings([page(url, title="Useful title") for url in urls], **CURRENT)
    assert set(finding["affected_pages"]) == set(urls)
    assert finding["page_count"] == 4


def test_canonical_target_finding_stays_on_exact_observed_source():
    url = "https://www.example.com/product;v=1?variant=bad"
    observed = page(url)
    observed.update(canonical=ORIGIN + "/missing", canonical_status="canonical_to_different_url", canonical_target_state="target_failed",
                    canonical_target_url=ORIGIN + "/missing", canonical_target_status_code=404)
    result = current_scan([observed])
    [raw] = [row for row in result["raw_findings"] if row["rule"] == "canonical_target_failed"]
    assert raw["page_url"] == url
    [repair] = [row for row in build_local_review(result)["canonical_repairs"] if row["rule"] == "canonical_target_failed"]
    assert repair["affected_pages"] == [url]


def test_navigation_quality_keeps_observed_origin_and_semicolon_routes():
    urls = [ORIGIN + "/x", ORIGIN + "/x;v=1", "https://www.example.com/x"]
    pages = [page(url) for url in urls]
    for observed in pages:
        observed["discovered_from"] = ["sitemap"]
    result = apply_post_crawl_transforms(current_scan(pages))
    [raw] = [row for row in result["raw_findings"] if row["rule"] == "potential_orphan_pages"]
    assert raw["affected_pages"] == urls
    assert raw["page_count"] == 3
    assert result["navigation_indexability_evidence"]["representative_orphan_candidates"] == urls


def test_current_raw_url_selector_rejects_unknown_identity_versions():
    with pytest.raises(ValueError, match="unsupported evidence URL identity version"):
        relative_evidence_url(page(ORIGIN + "/x"), identity_version="unknown")


@pytest.mark.asyncio
async def test_actual_scanner_retains_missing_title_after_apex_to_www_redirect(monkeypatch, mock_network):
    www = "https://www.example.com"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {"max_pages": 3, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2})
    mock_network({
        ORIGIN + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        ORIGIN + "/": {"status": 301, "headers": {"location": www + "/"}},
        www + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        www + "/sitemap.xml": {"body": "<urlset/>", "content_type": "application/xml"},
        www + "/": {"body": html(title="Home page", body='<h1>Home page</h1><a href="/product">Product</a>')},
        www + "/product": {"body": html()},
    })
    result = apply_post_crawl_transforms(await scanner.run_scan(ORIGIN + "/", scan_mode="basic", concurrency=1))
    assert result["crawl_scope"]["requested_origin"] == ORIGIN
    assert any(p["url"] == www + "/product" for p in result["pages"])
    [raw] = [row for row in result["raw_findings"] if row["rule"] == "missing_title"]
    assert raw["page_url"] == www + "/product"
    [repair] = [row for row in build_local_review(result)["canonical_repairs"] if row["rule"] == "missing_title"]
    assert repair["affected_pages"] == [www + "/product"]
    assert_persisted_customer_output(result, "missing_title", [www + "/product"], eligible=0)


@pytest.mark.asyncio
async def test_actual_soft_404_query_does_not_target_healthy_route(monkeypatch, mock_network):
    bad = ORIGIN + "/product?variant=bad"
    good = ORIGIN + "/product"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {"max_pages": 3, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2})
    mock_network({
        ORIGIN + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        ORIGIN + "/sitemap.xml": {"body": "<urlset/>", "content_type": "application/xml"},
        ORIGIN + "/": {"body": html(title="Home page", body='<h1>Home page</h1><a href="/product">Good</a><a href="/product?variant=bad">Bad</a>')},
        good: {"body": html()},
        bad: {"body": html(title="404 Page Not Found", body="<h1>Page not found</h1><p>Missing product.</p>")},
    })
    result = apply_post_crawl_transforms(await scanner.run_scan(ORIGIN + "/", scan_mode="basic", concurrency=1))
    [raw] = [row for row in result["raw_findings"] if row["rule"] == "soft_404"]
    assert raw["page_url"] == bad
    assert result["indexability_quality_evidence"]["representative_soft_404s"] == [bad]
    repairs = build_local_review(result)["canonical_repairs"]
    [repair] = [row for row in repairs if row["rule"] == "soft_404"]
    assert repair["affected_pages"] == [bad]
    [title] = [row for row in repairs if row["rule"] == "missing_title"]
    assert title["affected_pages"] == [good]
    assert_persisted_customer_output(result, "soft_404", [bad], eligible=0)


@pytest.mark.asyncio
async def test_unsampled_internal_link_probe_verifies_broken_target_without_expanding_assessed_cap(monkeypatch, mock_network):
    broken = ORIGIN + "/beyond-sample-broken"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {
        "max_pages": 4, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2,
    })
    requests = mock_network({
        ORIGIN + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        ORIGIN + "/sitemap.xml": {"body": "<urlset/>", "content_type": "application/xml"},
        ORIGIN + "/": {"body": html(
            title="Home page",
            body=(
                '<h1>Home page</h1>'
                '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
                '<a href="/beyond-sample-broken">Broken target</a>'
            ),
        )},
        ORIGIN + "/a": {"body": html(title="A")},
        ORIGIN + "/b": {"body": html(title="B")},
        ORIGIN + "/c": {"body": html(title="C")},
        broken: {"status": 404, "body": "<html><title>Not found</title><h1>Not found</h1></html>"},
    })

    result = apply_post_crawl_transforms(
        await scanner.run_scan(ORIGIN + "/", scan_mode="basic", concurrency=1)
    )

    assert result["pages_crawled"] == 4
    assert broken not in {page["url"] for page in result["pages"]}
    probe = result["coverage_probe_evidence"]
    assert probe["version"] == "coverage_probe_scheduler_v1_shared_request_budget"
    assert probe["request_budget"]["requests_consumed"] == 1
    assert probe["purposes"]["internal_link"]["eligible"] == 1
    assert probe["purposes"]["internal_link"]["attempted"] == 1
    assert probe["purposes"]["internal_link"]["completed"] == 1
    [observation] = [
        row for row in probe["observations"]
        if row["purpose"] == "internal_link" and row["observed_url"] == broken
    ]
    assert observation["state"] == "fail"
    assert observation["status_code"] == 404
    assert observation["source_pages"] == ["/"]
    assert observation["link_text_samples"] == ["Broken target"]

    [raw] = [row for row in result["raw_findings"] if row["rule"] == "404_error"]
    assert raw["affected_pages"] == [broken]
    assert raw["source_pages"] == ["/"]
    assert raw["verification_state"] == "verified"
    assert raw["non_scoring"] is True
    assert raw["score_impact"] == 0

    requested = [
        f"{request.url.scheme}://{request.headers.get('host', '')}{request.url.raw_path.decode('ascii')}"
        for request in requests
    ]
    assert broken in requested
    assert_persisted_customer_output(result, "404_error", [broken], eligible=0)


@pytest.mark.asyncio
async def test_unsampled_link_probe_budget_exhaustion_is_unknown_not_success(monkeypatch, mock_network):
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {
        "max_pages": 4, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2,
    })
    monkeypatch.setattr(scanner, "coverage_probe_request_limit", lambda _mode: 1)
    mock_network({
        ORIGIN + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        ORIGIN + "/sitemap.xml": {"body": "<urlset/>", "content_type": "application/xml"},
        ORIGIN + "/": {"body": html(
            title="Home page",
            body=(
                '<h1>Home</h1><a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
                '<a href="/u1">U1</a><a href="/u2">U2</a>'
            ),
        )},
        ORIGIN + "/a": {"body": html(title="A")},
        ORIGIN + "/b": {"body": html(title="B")},
        ORIGIN + "/c": {"body": html(title="C")},
        ORIGIN + "/u1": {"body": html(title="U1")},
        ORIGIN + "/u2": {"status": 404, "body": "<h1>Not found</h1>"},
    })
    result = await scanner.run_scan(ORIGIN + "/", scan_mode="basic", concurrency=1)
    purpose = result["coverage_probe_evidence"]["purposes"]["internal_link"]
    assert purpose["eligible"] == 2
    assert purpose["completed"] == 1
    assert purpose["exhausted"] == 1
    assert result["coverage_probe_evidence"]["request_budget"]["budget_exhausted"] is True
    assert not [
        row for row in result["raw_findings"]
        if row["rule"] in {"404_error", "410_error"} and row["affected_pages"] == [ORIGIN + "/u2"]
    ]
