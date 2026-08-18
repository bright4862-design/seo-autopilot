from app.extract import extract_page
from app.page_evidence_gate import page_evidence_class
from app.review import run_review


def test_ratp_cloudflare_403_challenge_remains_fail_closed_and_non_authoritative():
    html = """
    <!DOCTYPE html>
    <html lang="en-US">
      <head>
        <title>Just a moment...</title>
        <meta name="robots" content="noindex,nofollow">
        <meta http-equiv="content-security-policy" content="script-src https://challenges.cloudflare.com">
      </head>
      <body>
        <div class="main-wrapper" role="main">
          <div class="main-content"><h1>www.ratp.fr</h1><p>Performing security verification</p></div>
        </div>
      </body>
    </html>
    """
    page = extract_page(
        html,
        "https://www.ratp.fr/",
        "https://www.ratp.fr/",
        403,
        "text/html; charset=UTF-8",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )

    assert page_evidence_class(page) == "failed_access"

    result = run_review({
        "website_url": "https://www.ratp.fr/",
        "pages_found": 1,
        "pages_crawled": 1,
        "queued_remaining": 0,
        "crawl_timing": {
            "queue_exhausted": True,
            "crawl_deadline_reached": False,
            "failed_fetch_count": 1,
            "failure_reason_buckets": {"client_error_4xx": 1},
        },
        "crawled_pages": [page],
    })

    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["access_evidence_state"] == "blocked"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False
    assert result["health_score"] is None
