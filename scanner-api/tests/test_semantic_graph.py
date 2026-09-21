from app.semantic_graph import (
    DeterministicLocalVectorizer,
    build_semantic_graph_evidence,
    build_weighted_internal_link_graph,
    cannibalization_candidates,
    infer_link_zone,
    infer_template_groups,
    internal_link_opportunities,
    near_duplicate_candidates,
    semantic_clusters,
    semantic_similarity_matrix,
)


def page(url, *, title="", h1="", terms=None, indexable=True, family="", main=None):
    row = {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "title": title,
        "h1": h1,
        "semantic_terms": terms or [],
        "indexable": indexable,
    }
    if family:
        row["page_template_family"] = family
    if main is not None:
        row.update(
            {
                "main_text_verified": True,
                "main_text_representation": "sha256_5_token_shingles_v1",
                "main_text": " ".join(main),
            }
        )
    return row


def test_link_zone_inference_requires_positive_structure_for_contextual():
    nav = infer_link_zone({"source_url": "https://e.test/", "target_url": "https://e.test/a", "ancestor_tags": ["nav"], "text": "A"})
    footer = infer_link_zone({"source_url": "https://e.test/", "target_url": "https://e.test/a", "ancestor_tags": ["footer"], "text": "A"})
    contextual = infer_link_zone({"source_url": "https://e.test/", "target_url": "https://e.test/a", "ancestor_tags": ["main", "p"], "text": "A"})
    unknown = infer_link_zone({"source_url": "https://e.test/", "target_url": "https://e.test/a", "navigation_presence": False, "text": "A"})
    assert nav["zone"] == "navigation"
    assert footer["zone"] == "footer"
    assert contextual["zone"] == "contextual"
    assert unknown["zone"] == "unknown"
    assert unknown["state"] == "not_verified"


def test_facet_and_listing_zone_signals_are_distinct():
    facet = infer_link_zone({
        "source_url": "https://shop.test/shoes",
        "target_url": "https://shop.test/shoes?color=black",
        "ancestor_classes": "filters",
    })
    listing = infer_link_zone({
        "source_url": "https://shop.test/shoes",
        "target_url": "https://shop.test/shoes/runner-pro",
        "ancestor_classes": "product-grid card",
        "repeated_sibling_links": 8,
    })
    assert facet["zone"] == "facet"
    assert listing["zone"] == "listing"


def test_template_grouping_is_deterministic_and_marks_single_route_inference_lower_confidence():
    pages = [
        page("https://e.test/blog/first-long-article-slug"),
        page("https://e.test/blog/second-long-article-slug"),
        page("https://e.test/contact"),
        page("https://e.test/products/12345", family="product_page"),
    ]
    first = infer_template_groups(pages)
    second = infer_template_groups(list(reversed(pages)))
    mapping_first = {row["url"]: (row["group_id"], row["confidence"]) for row in first["pages"]}
    mapping_second = {row["url"]: (row["group_id"], row["confidence"]) for row in second["pages"]}
    assert mapping_first == mapping_second
    assert mapping_first["https://e.test/blog/first-long-article-slug"][0] == mapping_first["https://e.test/blog/second-long-article-slug"][0]
    assert mapping_first["https://e.test/contact"][1] < 0.5
    assert mapping_first["https://e.test/products/12345"][1] == 1.0


def test_weighted_graph_prefers_contextual_and_never_claims_sitewide_orphaning():
    pages = [page("https://e.test/a"), page("https://e.test/b"), page("https://e.test/c")]
    links = [
        {"source_url": "https://e.test/a", "target_url": "https://e.test/b", "ancestor_tags": ["main", "p"], "text": "Important topic"},
        {"source_url": "https://e.test/a", "target_url": "https://e.test/c", "ancestor_tags": ["footer"], "text": "Footer"},
    ]
    graph = build_weighted_internal_link_graph(pages, links)
    by_target = {edge["target_url"]: edge for edge in graph["edges"]}
    assert by_target["https://e.test/b"]["weight"] > by_target["https://e.test/c"]["weight"]
    assert graph["sitewide_orphan_claim"] is False
    assert all(node["sitewide_orphan_claim"] is False for node in graph["nodes"])


def test_deterministic_local_semantic_interface_and_clusters():
    pages = [
        page("https://e.test/hard-money", title="Hard Money Loans", h1="Hard Money Loans", terms=["bridge", "real estate"]),
        page("https://e.test/bridge-loans", title="Bridge Loans for Real Estate", h1="Hard Money Bridge Loans", terms=["hard money", "real estate"]),
        page("https://e.test/contact", title="Contact Us", h1="Contact"),
    ]
    vectorizer = DeterministicLocalVectorizer()
    one = semantic_similarity_matrix(pages, vectorizer=vectorizer, min_similarity=0.2)
    two = semantic_similarity_matrix(pages, vectorizer=vectorizer, min_similarity=0.2)
    assert one == two
    pair = next(row for row in one["pairs"] if {row["left_url"], row["right_url"]} == {"https://e.test/hard-money", "https://e.test/bridge-loans"})
    assert pair["similarity"] > 0.4
    clusters = semantic_clusters(pages, threshold=0.4, vectorizer=vectorizer)
    assert any(set(cluster["urls"]) == {"https://e.test/hard-money", "https://e.test/bridge-loans"} for cluster in clusters["clusters"])


def test_near_duplicate_candidates_use_only_verified_b10_hashed_shingles():
    a = [f"{i:016x}" for i in range(1, 11)]
    b = a[:9] + [f"{999:016x}"]
    pages = [
        page("https://e.test/a", main=a),
        page("https://e.test/b", main=b),
        page("https://e.test/c", main=a),
    ]
    pages[2]["main_text_verified"] = False
    result = near_duplicate_candidates(pages, threshold=0.8)
    assert result["eligible_pages"] == 2
    assert result["candidates"] == [{
        "left_url": "https://e.test/a",
        "right_url": "https://e.test/b",
        "similarity": 0.818182,
        "evidence": "verified_b10_main_content_shingles",
    }]


def test_cannibalization_excludes_near_duplicates_and_requires_indexability():
    common = [f"{i:016x}" for i in range(1, 11)]
    pages = [
        page("https://e.test/loan-a", title="Hard Money Loan California", h1="Hard Money Loan", terms=["bridge", "real estate"], main=common),
        page("https://e.test/loan-b", title="California Hard Money Lending", h1="Hard Money Lender", terms=["bridge", "real estate"], main=common),
        page("https://e.test/loan-c", title="California Hard Money Guide", h1="Hard Money Guide", terms=["bridge", "real estate"], indexable=False),
    ]
    result = cannibalization_candidates(pages, semantic_threshold=0.35, duplicate_threshold=0.82)
    assert result["candidates"] == []
    pages[1]["main_text"] = " ".join([f"{i:016x}" for i in range(100, 110)])
    result = cannibalization_candidates(pages, semantic_threshold=0.35, duplicate_threshold=0.82)
    assert any({row["left_url"], row["right_url"]} == {"https://e.test/loan-a", "https://e.test/loan-b"} for row in result["candidates"])
    assert all("loan-c" not in row["left_url"] and "loan-c" not in row["right_url"] for row in result["candidates"])


def test_internal_link_opportunities_are_observed_gap_evidence_not_absence_claims():
    pages = [
        page("https://e.test/guide", title="Hard Money Guide", h1="Hard Money Guide", terms=["bridge", "loans"]),
        page("https://e.test/loans", title="Hard Money Loans", h1="Bridge Loans", terms=["hard money", "bridge"]),
        page("https://e.test/contact", title="Contact", h1="Contact"),
    ]
    graph = build_weighted_internal_link_graph(
        pages,
        [{"source_url": "https://e.test/loans", "target_url": "https://e.test/guide", "ancestor_tags": ["main"], "text": "Guide"}],
    )
    result = internal_link_opportunities(pages, graph, semantic_threshold=0.3)
    candidate = next(row for row in result["candidates"] if row["source_url"] == "https://e.test/guide" and row["target_url"] == "https://e.test/loans")
    assert candidate["observed_edge_present"] is False
    assert candidate["sitewide_link_absence_claim"] is False
    assert candidate["proposed_zone"] == "contextual"
    assert not any(row["source_url"] == "https://e.test/loans" and row["target_url"] == "https://e.test/guide" for row in result["candidates"])


def test_complete_envelope_is_versioned_and_never_creates_customer_fixes():
    pages = [
        page("https://e.test/a", title="SEO Audit Guide", h1="Technical SEO Audit", terms=["crawl", "indexing"]),
        page("https://e.test/b", title="Technical SEO Audit", h1="SEO Audit", terms=["crawl", "indexing"]),
    ]
    links = [{"source_url": "https://e.test/a", "target_url": "https://e.test/b", "ancestor_tags": ["main"], "text": "Technical SEO"}]
    envelope = build_semantic_graph_evidence(pages, links)
    assert envelope["version"] == "semantic_graph_evidence_v1"
    assert envelope["scope"] == "observed_assessed_pages_only"
    assert envelope["sitewide_orphan_claim"] is False
    assert envelope["customer_fix_created"] is False
    assert "template_evidence" in envelope
    assert "graph" in envelope
    assert "semantic_clusters" in envelope
    assert "near_duplicate_candidates" in envelope
    assert "cannibalization_candidates" in envelope
    assert "internal_link_opportunities" in envelope
