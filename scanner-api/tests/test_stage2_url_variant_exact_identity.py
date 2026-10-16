from app.url_variant_evidence import build_url_variant_candidates


def test_verified_origin_alias_preserves_reserved_escape_query_order_and_empty_delimiter():
    source = "https://example.com/Catalog%2FItem?"
    rows = build_url_variant_candidates(
        [source],
        origin="https://example.com",
        verified_alias_origins=["https://www.example.com"],
        max_candidates=4,
    )
    [alias] = [row for row in rows if row["kind"] == "verified_origin_alias"]
    assert alias["source_url"] == source
    assert alias["probe_url"] == "https://www.example.com/Catalog%2FItem?"
    assert alias["verified_alias"] is True
    assert alias["synthetic"] is True


def test_verified_origin_alias_preserves_nonempty_raw_query_order():
    source = "https://example.com/Page?z=2&a=1"
    rows = build_url_variant_candidates(
        [source],
        origin="https://example.com",
        verified_alias_origins=["http://example.com"],
        max_candidates=4,
    )
    [alias] = [row for row in rows if row["kind"] == "verified_origin_alias"]
    assert alias["probe_url"] == "http://example.com/Page?z=2&a=1"
