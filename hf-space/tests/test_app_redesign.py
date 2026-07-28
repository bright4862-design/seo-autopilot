from app_redesign import context_markup, score_markup, site_markup


def test_empty_workspace_contains_no_demo_result():
    assert "Ready for a new scan" in site_markup({})
    assert "Your score will appear here" in score_markup({})
    assert "Run a scan to load context" in context_markup({})


def test_live_workspace_matches_one_page_result_contract():
    scan = {
        "source": "live",
        "website": "https://www.funbooker.com",
        "score": 68,
        "pages_crawled": 150,
        "release_gate_eligible": True,
        "score_is_provisional": False,
    }

    assert "www.funbooker.com" in site_markup(scan)
    assert "150 pages checked" in site_markup(scan)
    assert "Authoritative result" in site_markup(scan)
    assert "A solid foundation." in score_markup(scan)
    assert "--v:68" in score_markup(scan)
    assert "Scan context loaded" in context_markup(scan)
