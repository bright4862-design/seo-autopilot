from app.extract import extract_links


def test_raw_link_extraction_marks_only_semantic_navigation_ancestors():
    html = """
    <html><body>
      <nav><a href="/pricing">Pricing</a></nav>
      <div role="navigation"><a href="/products">Products</a></div>
      <div class="menu"><a href="/content">Content link</a></div>
      <footer><a href="/footer">Footer link</a></footer>
    </body></html>
    """
    links = {row["href"]: row for row in extract_links(html, "https://example.com/")}

    assert links["https://example.com/pricing"]["navigation_presence"] is True
    assert links["https://example.com/products"]["navigation_presence"] is True
    # Class names and footer placement are not silently promoted to navigation.
    assert links["https://example.com/content"]["navigation_presence"] is False
    assert links["https://example.com/footer"]["navigation_presence"] is False


def test_link_context_preserves_exact_request_identity_except_fragment():
    html = '<nav><a href="/Pricing?plan=Pro%2FAnnual&src=Nav#details">Buy</a></nav>'
    row = extract_links(html, "https://example.com/base")[0]
    assert row == {
        "href": "https://example.com/Pricing?plan=Pro%2FAnnual&src=Nav",
        "text": "Buy",
        "navigation_presence": True,
    }
