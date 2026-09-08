from app.extract import extract_page
from app.review import run_review
from app.scanner import build_findings


def _discovery():
    return {
        "discovered_from": ["seed"],
        "source_pages": [],
        "link_text_samples": [],
    }


def _page(path: str, heading: str, body: str) -> dict:
    url = f"https://example.com{path}"
    html = f"""
    <html>
      <head>
        <title>{heading} | Example</title>
        <meta name="description" content="Useful information about {heading}." />
        <link rel="canonical" href="{url}" />
      </head>
      <body>
        <h1>{heading}</h1>
        <p>{body}</p>
      </body>
    </html>
    """
    return extract_page(html, url, url, 200, "text/html", _discovery())


def _review(pages: list[dict]) -> dict:
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "raw_findings": build_findings(pages),
        "scan_coverage": {
            "pages_found": len(pages),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def test_extracts_strong_visible_template_placeholder_signatures():
    page = _page(
        "/",
        "Private Real Estate Lending",
        "gvar+ Flexible funding for investors. Visit our XX page to learn more.",
    )

    assert page["unresolved_template_placeholder_count"] >= 2
    assert "global_variable_placeholder" in page["unresolved_template_placeholder_types"]
    assert "contextual_xx_placeholder" in page["unresolved_template_placeholder_types"]
    assert 1 <= len(page["unresolved_template_placeholder_evidence"]) <= 4
    assert any("gvar+" in sample.lower() for sample in page["unresolved_template_placeholder_evidence"])
    assert any("XX page" in sample for sample in page["unresolved_template_placeholder_evidence"])


def test_extracts_approved_delimited_variable_syntax_on_commercial_page():
    page = _page(
        "/loans/dscr",
        "DSCR Rental Loans",
        "Financing for {{ product }} investors in ${market}. Call {var-phone} today.",
    )

    assert "delimited_template_variable" in page["unresolved_template_placeholder_types"]
    assert page["unresolved_template_placeholder_count"] >= 3
    assert len(page["unresolved_template_placeholder_evidence"]) <= 4


def test_bare_xx_and_single_literal_gvar_do_not_trigger():
    page = _page(
        "/",
        "Private Real Estate Lending",
        "Model XX is available. GVAR is an internal acronym mentioned once in this public explanation.",
    )

    assert page["unresolved_template_placeholder_count"] == 0
    assert page["unresolved_template_placeholder_types"] == []
    assert page["unresolved_template_placeholder_evidence"] == []


def test_guide_code_example_does_not_create_customer_placeholder_repair():
    guide = _page(
        "/blog/template-variables",
        "How template variables work",
        "Example code: {{ product }} and ${market}. This article teaches developers how placeholders work.",
    )

    result = _review([guide])
    fixes = [
        fix for fix in result["cleaned_fixes"]
        if fix.get("rule") == "unresolved_template_placeholder"
    ]

    assert fixes == []


def test_review_groups_placeholder_repairs_by_template_family_without_false_shared_fix_claim():
    pages = [
        _page(
            "/",
            "Private Real Estate Lending",
            "gvar+ Visit our XX page for current lending options.",
        ),
        _page(
            "/loans/dscr",
            "DSCR Rental Loans",
            "gvar+ Long-term rental financing for ${market} investors.",
        ),
        _page(
            "/loans/bridge",
            "Bridge Loans",
            "Visit our XX page for bridge financing. {{ product }} terms apply.",
        ),
        _page(
            "/blog/template-variables",
            "Template Variable Guide",
            "Example code: {{ product }} and ${market}.",
        ),
    ]

    result = _review(pages)
    fixes = [
        fix for fix in result["cleaned_fixes"]
        if fix.get("rule") == "unresolved_template_placeholder"
    ]

    assert len(fixes) == 2
    by_family = {fix.get("page_template_family"): fix for fix in fixes}
    assert set(by_family) == {"homepage", "loan_program"}
    assert len(by_family["homepage"]["affected_pages"]) == 1
    assert len(by_family["loan_program"]["affected_pages"]) == 2
    assert by_family["homepage"].get("shared_repair_confirmed") is False
    assert by_family["loan_program"].get("shared_repair_confirmed") is False
    assert all(len(fix.get("template_placeholder_evidence") or []) <= 4 for fix in fixes)
    assert all(fix.get("requires_developer") is True for fix in fixes)


def test_location_placeholder_stays_owned_by_existing_location_repair():
    location = _page(
        "/locations/alaska",
        "Alaska Hard Money Lenders",
        "Talk with #location# specialists about financing today.",
    )

    result = _review([location])
    rules = [fix.get("rule") for fix in result["cleaned_fixes"]]

    assert "broken_location_template_content" in rules
    assert "unresolved_template_placeholder" not in rules
