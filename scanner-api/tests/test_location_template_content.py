from app.extract import extract_page
from app.review import run_review
from app.scanner import build_findings


def _discovery():
    return {
        "discovered_from": ["seed"],
        "source_pages": [],
        "link_text_samples": [],
    }


def _location_page(slug: str, heading: str, body: str) -> dict:
    url = f"https://example.com/locations/{slug}"
    html = f"""
    <html>
      <head>
        <title>{heading} | Example Lending</title>
        <meta name="description" content="Private real estate lending for {heading}." />
        <link rel="canonical" href="{url}" />
      </head>
      <body>
        <h1>{heading}</h1>
        <p>{body}</p>
      </body>
    </html>
    """
    return extract_page(html, url, url, 200, "text/html", _discovery())


def test_location_page_extracts_unresolved_template_tokens_with_bounded_evidence():
    page = _location_page(
        "alaska",
        "Alaska Hard Money Lenders",
        "Talk with #location# specialists about financing in {var-location} today.",
    )

    assert "unresolved_location_token" in page["template_content_issue_types"]
    assert page["template_content_issue_count"] >= 1
    assert 1 <= len(page["template_content_issue_evidence"]) <= 4
    assert any(
        "#location#" in sample or "{var-location}" in sample
        for sample in page["template_content_issue_evidence"]
    )


def test_location_page_detects_all_approved_placeholder_shapes():
    page = _location_page(
        "alaska",
        "Alaska Hard Money Lenders",
        "#CITY# {var-state} {{region}} ${market} {{ area }}",
    )

    assert "unresolved_location_token" in page["template_content_issue_types"]
    assert page["template_content_issue_count"] >= 5
    assert len(page["template_content_issue_evidence"]) <= 4


def test_location_placeholder_in_h1_is_counted_once():
    url = "https://example.com/locations/alaska"
    html = f"""
    <html>
      <head>
        <title>Alaska Lending | Example Lending</title>
        <meta name="description" content="Private real estate lending for Alaska." />
        <link rel="canonical" href="{url}" />
      </head>
      <body>
        <h1>Alaska #location# lenders</h1>
        <p>Fast financing for local investors.</p>
      </body>
    </html>
    """
    page = extract_page(html, url, url, 200, "text/html", _discovery())

    assert page["template_content_issue_count"] == 1
    assert page["template_content_issue_types"] == ["unresolved_location_token"]
    assert len(page["template_content_issue_evidence"]) == 1
    assert "#location#" in page["template_content_issue_evidence"][0]


def test_city_location_page_still_flags_unresolved_template_tokens():
    page = _location_page(
        "houston",
        "Houston Hard Money Lenders",
        "Talk with {var-location} specialists about your next investment.",
    )

    assert "unresolved_location_token" in page["template_content_issue_types"]
    assert "wrong_location_copy" not in page["template_content_issue_types"]


def test_state_location_page_flags_wrong_state_lender_copy():
    page = _location_page(
        "alaska",
        "Alaska Hard Money Lenders",
        "As Georgia hard money lenders, we help investors close quickly.",
    )

    assert "wrong_location_copy" in page["template_content_issue_types"]
    assert any("Georgia hard money lenders" in sample for sample in page["template_content_issue_evidence"])


def test_wrong_state_lender_heading_identifies_page_as_wrong_market():
    page = _location_page(
        "alaska",
        "Georgia Hard Money Lenders",
        "Fast financing for real estate investors.",
    )

    assert "wrong_location_copy" in page["template_content_issue_types"]
    assert any("Georgia Hard Money Lenders" in sample for sample in page["template_content_issue_evidence"])


def test_location_copy_does_not_flag_legitimate_interstate_mentions_or_matching_state():
    alaska = _location_page(
        "alaska",
        "Alaska Hard Money Lenders",
        "We lend nationwide, including Georgia and Texas, while serving Alaska investors locally.",
    )
    partner_network = _location_page(
        "alaska",
        "Alaska Hard Money Lenders",
        "We partner with Georgia hard money lenders when an investor needs help outside Alaska.",
    )
    georgia = _location_page(
        "georgia",
        "Georgia Hard Money Lenders",
        "As Georgia hard money lenders, we help local real estate investors close quickly.",
    )

    assert "wrong_location_copy" not in alaska["template_content_issue_types"]
    assert "wrong_location_copy" not in partner_network["template_content_issue_types"]
    assert "wrong_location_copy" not in georgia["template_content_issue_types"]


def test_location_template_findings_group_into_one_developer_repair():
    pages = [
        _location_page(
            "alaska",
            "Alaska Hard Money Lenders",
            "Talk with #location# specialists. As Georgia hard money lenders, we move quickly.",
        ),
        _location_page(
            "alabama",
            "Alabama Hard Money Lenders",
            "Your {var-location} team is ready. As New Jersey hard money lenders, we can help.",
        ),
        _location_page(
            "houston",
            "Houston Hard Money Lenders",
            "Talk with {{market}} specialists about your next investment.",
        ),
    ]

    result = run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "raw_findings": build_findings(pages),
        "scan_coverage": {
            "pages_found": len(pages),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })

    fixes = [
        fix for fix in result["cleaned_fixes"]
        if fix.get("rule") == "broken_location_template_content"
    ]

    assert len(fixes) == 1
    fix = fixes[0]
    assert len(fix["affected_pages"]) == 3
    assert any("/locations/houston" in page for page in fix["affected_pages"])
    assert fix["who_can_do_this"] == "your_web_person"
    assert fix["requires_developer"] is True
    assert "location" in str(fix.get("issue_title") or fix.get("title") or "").lower()
