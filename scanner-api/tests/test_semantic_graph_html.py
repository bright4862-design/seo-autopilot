from app.semantic_graph import infer_link_zone
from app.semantic_graph_html import extract_link_zone_observations


def test_zero_configuration_html_adapter_yields_zone_evidence_without_raw_html():
    html = """
    <html><body>
      <nav><a href="/nav">Nav</a></nav>
      <main><p><a href="/context">Context Topic</a></p></main>
      <section class="product-grid"><a href="/one">One</a><a href="/two">Two</a><a href="/three">Three</a></section>
      <footer><a href="/footer">Footer</a></footer>
    </body></html>
    """
    observations = extract_link_zone_observations(html, "https://e.test/")
    zones = {row["target_url"]: infer_link_zone(row)["zone"] for row in observations}
    assert zones["https://e.test/nav"] == "navigation"
    assert zones["https://e.test/context"] == "contextual"
    assert zones["https://e.test/one"] == "listing"
    assert zones["https://e.test/footer"] == "footer"
    assert all("html" not in row for row in observations)


def test_html_adapter_fails_closed_for_oversized_or_missing_source():
    assert extract_link_zone_observations("<a href='/x'>x</a>", "") == []
    assert extract_link_zone_observations("x" * 2_000_001, "https://e.test/") == []
