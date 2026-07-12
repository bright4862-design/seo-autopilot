from app.extract import client_rendering_signals, extract_page


def test_detects_common_app_shell_roots_with_single_or_double_quotes():
    assert client_rendering_signals('<div id="root"></div>', 200, 0) == ["react_root"]
    assert client_rendering_signals("<main id='app'></main>", 200, 4) == ["generic_app_root"]
    assert client_rendering_signals('<div id="__next"></div>', 200, 5) == ["next_root"]
    assert client_rendering_signals("<div id='__nuxt'></div>", 200, 6) == ["nuxt_root"]


def test_does_not_flag_content_rich_or_failed_pages():
    html = '<div id="root">' + ("word " * 100) + "</div>"
    assert client_rendering_signals(html, 200, 100) == []
    assert client_rendering_signals('<div id="root"></div>', 429, 0) == []
    assert client_rendering_signals('<div class="root"></div>', 200, 0) == []


def test_extract_page_exposes_bounded_rendering_evidence():
    page = extract_page(
        "<html><body><div id='__next'></div></body></html>",
        "https://example.com/app",
        "https://example.com/app",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )

    assert page["client_rendering_suspected"] is True
    assert page["client_rendering_signals"] == ["next_root"]
