from app import scanner
from app.extract import extract_page


DISCOVERY = {"discovered_from": ["internal_link"], "source_pages": ["/source"], "link_text_samples": []}


def page(url, status, content_type="text/html", html="", fetch_error=""):
    return extract_page(
        html,
        url,
        url,
        status,
        content_type,
        DISCOVERY,
        fetch_error=fetch_error,
    )


def test_scan_coverage_counts_observed_status_access_and_content_separately():
    observed = [
        page("https://example.com/ok", 200, html="<html><head><title>OK</title></head><body><h1>OK</h1><p>Useful content.</p></body></html>"),
        page("https://example.com/missing", 404, html="<html><body>Not found</body></html>"),
        page("https://example.com/forbidden", 403, html="<html><body>Forbidden</body></html>"),
        page("https://example.com/rate", 429, html="<html><body>Rate limited</body></html>"),
        page("https://example.com/robots", 0, fetch_error="blocked_by_robots_txt"),
        page("https://example.com/transport", 0, fetch_error="timed out"),
        page("https://example.com/file.pdf", 200, content_type="application/pdf", html=""),
        page("https://example.com/invalid-html", 200, content_type="text/html", html=""),
    ]

    counters = scanner._new_scan_coverage_counters()
    for item in observed:
        scanner._observe_scan_coverage(counters, item)
    coverage = scanner._finalize_scan_coverage(counters, observed)

    assert coverage == {
        "urls_attempted": 8,
        "usable_html_pages": 1,
        "verified_http_failures": 3,
        "access_unverified_pages": 4,
        "non_html_resources": 1,
        "unique_retained_destinations": 8,
    }


def test_scan_coverage_keeps_attempts_separate_from_final_url_dedup():
    counters = scanner._new_scan_coverage_counters()
    first = page("https://example.com/one", 200, html="<html><head><title>One</title></head><body><h1>One</h1><p>Useful content.</p></body></html>")
    second = page("https://example.com/two", 200, html="<html><head><title>Two</title></head><body><h1>Two</h1><p>Useful content.</p></body></html>")
    scanner._observe_scan_coverage(counters, first)
    scanner._observe_scan_coverage(counters, second)

    coverage = scanner._finalize_scan_coverage(counters, [first])
    assert coverage["urls_attempted"] == 2
    assert coverage["usable_html_pages"] == 2
    assert coverage["unique_retained_destinations"] == 1
