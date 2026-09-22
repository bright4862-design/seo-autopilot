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


def test_html_adapter_excludes_hidden_inert_and_non_http_links_from_evidence():
    html = """
    <html><body>
      <nav hidden><a href="/hidden-nav">Hidden</a></nav>
      <div inert><a href="/inert">Inert</a></div>
      <main>
        <a href="mailto:test@example.com">Mail</a>
        <a href="javascript:void(0)">JS</a>
        <a href="tel:+12025550123">Phone</a>
        <a href="/visible">Visible</a>
      </main>
    </body></html>
    """
    observations = extract_link_zone_observations(html, "https://e.test/")
    assert [row["target_url"] for row in observations] == ["https://e.test/visible"]
    assert infer_link_zone(observations[0])["zone"] == "contextual"


def test_hidden_links_do_not_inflate_listing_sibling_count():
    html = """
    <main><section>
      <a href="/one">One</a>
      <a href="/two">Two</a>
      <span hidden><a href="/hidden-one">Hidden one</a></span>
      <span aria-hidden="true"><a href="/hidden-two">Hidden two</a></span>
      <span style="display:none"><a href="/hidden-three">Hidden three</a></span>
    </section></main>
    """
    observations = extract_link_zone_observations(html, "https://e.test/")
    assert len(observations) == 2
    assert {row["repeated_sibling_links"] for row in observations} == {2}
    assert {infer_link_zone(row)["zone"] for row in observations} == {"contextual"}


def test_html_adapter_fails_closed_for_oversized_or_missing_source():
    assert extract_link_zone_observations("<a href='/x'>x</a>", "") == []
    assert extract_link_zone_observations("<a href='/x'>x</a>", "mailto:test@example.com") == []
    assert extract_link_zone_observations("x" * 2_000_001, "https://e.test/") == []
