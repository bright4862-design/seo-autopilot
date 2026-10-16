from app.extract import extract_page
from app.stage2_coverage_evidence import (
    MAIN_TEXT_EVIDENCE_VERSION,
    PAGE_WEIGHT_VERSION,
    near_duplicate_main_content,
    page_weight_evidence,
)


def _page(url: str, main_text: str, *, chrome: str = "Shared navigation") -> dict:
    html = f"""
    <html>
      <head><title>Useful page</title></head>
      <body>
        <header><nav>{chrome}</nav></header>
        <main><h1>Useful page</h1><p>{main_text}</p></main>
        <footer>Shared footer legal links</footer>
      </body>
    </html>
    """
    return extract_page(
        html,
        url,
        url,
        200,
        "text/html",
        {"discovered_from": ["sitemap"], "source_pages": [], "link_text_samples": []},
    )


def test_b10_extraction_publishes_only_irreversible_main_content_signature_material():
    page = _page(
        "https://example.com/a",
        " ".join(f"alpha{index}" for index in range(80)),
        chrome="Navigation marker that must not enter B10 evidence",
    )

    assert page["main_text_evidence_version"] == MAIN_TEXT_EVIDENCE_VERSION
    assert page["main_text_verified"] is True
    assert page["main_text_source"] == "main_landmark"
    assert page["main_text_representation"] == "sha256_5_token_shingles_v1"
    assert page["main_text_signature"]
    assert page["main_text_token_count"] >= 80
    assert "Navigation marker" not in page["main_text"]
    assert "Shared footer" not in page["main_text"]
    assert "alpha79" not in page["main_text"]
    assert all(len(token) == 16 for token in page["main_text"].split())


def test_b10_empty_main_landmark_does_not_fall_back_to_body_text():
    page = extract_page(
        "<html><head><title>Private title</title></head><body><p>Outside main copy</p><main></main></body></html>",
        "https://example.com/empty-main",
        "https://example.com/empty-main",
        200,
        "text/html",
        {"discovered_from": ["sitemap"], "source_pages": [], "link_text_samples": []},
    )
    assert page["main_text_source"] == "main_landmark"
    assert page["main_text_verified"] is False
    assert page["main_text"] == ""
    assert page["main_text_char_count"] == 0


def test_b10_near_duplicate_analysis_uses_extracted_main_content_not_shared_chrome():
    distinct = near_duplicate_main_content(
        [
            _page("https://example.com/a", " ".join(f"alpha{index}" for index in range(90))),
            _page("https://example.com/b", " ".join(f"beta{index}" for index in range(90))),
        ]
    )
    assert distinct["state"] == "pass"
    assert distinct["clusters"] == []

    common_main = " ".join(f"shared{index}" for index in range(100))
    duplicate = near_duplicate_main_content(
        [
            _page("https://example.com/c", common_main + " first", chrome="Nav A"),
            _page("https://example.com/d", common_main + " second", chrome="Completely different Nav B"),
        ]
    )
    assert duplicate["state"] == "fail"
    assert duplicate["clusters"][0]["page_count"] == 2


def test_b10_unusable_html_cannot_become_verified_main_text():
    page = extract_page(
        "<html><body><main>blocked response body</main></body></html>",
        "https://example.com/blocked",
        "https://example.com/blocked",
        403,
        "text/html",
        {"discovered_from": ["internal_link"], "source_pages": [], "link_text_samples": []},
    )
    assert page["main_text_evidence_version"] == MAIN_TEXT_EVIDENCE_VERSION
    assert page["main_text_verified"] is False
    assert page["main_text"] == ""
    assert page["main_text_signature"] == ""
    assert near_duplicate_main_content([page])["state"] == "not_verified"


def test_b17_extraction_keeps_decoded_and_inline_bytes_distinct_from_unknown_transfer_bytes():
    html = (
        "<html><head><title>Weight</title>"
        "<style>body{margin:0}</style>"
        "<script>window.x=1;</script>"
        "<script src='/external.js'></script>"
        "</head><body><main><h1>Weight</h1><p>Useful content.</p></main></body></html>"
    )
    page = extract_page(
        html,
        "https://example.com/weight",
        "https://example.com/weight",
        200,
        "text/html",
        {"discovered_from": ["sitemap"], "source_pages": [], "link_text_samples": []},
    )

    assert page["page_weight_evidence_version"] == PAGE_WEIGHT_VERSION
    assert page["decoded_bytes"] == len(html.encode("utf-8"))
    assert page["decoded_bytes_basis"] == "utf8_of_decoded_html"
    assert page["inline_script_bytes"] == len("window.x=1;".encode("utf-8"))
    assert page["inline_style_bytes"] == len("body{margin:0}".encode("utf-8"))
    assert page["transfer_bytes"] is None
    assert page["transfer_bytes_state"] == "unknown"

    evidence = page_weight_evidence(
        decoded_bytes=page["decoded_bytes"],
        inline_script_bytes=page["inline_script_bytes"],
        inline_style_bytes=page["inline_style_bytes"],
        transfer_bytes=page["transfer_bytes"],
        transfer_measured=page["transfer_bytes_state"] == "measured",
    )
    assert evidence["state"] == "pass"
    assert evidence["decoded_bytes"] == page["decoded_bytes"]
    assert evidence["transfer_bytes"] is None
    assert evidence["transfer_bytes_state"] == "unknown"
