from copy import deepcopy

import pytest

from app.semantic_graph_evidence_bound import (
    LINK_ZONE_SUMMARY_VERSION,
    VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
    build_vector_bound_semantic_graph_evidence,
)


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "article",
    }


def contextual_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "shared intent",
        "ancestor_tags": ["a", "main"],
    }


class StableVectorizer:
    version = "stable_mapping_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class ThirdCallChangesVectorizer:
    version = "third_call_changes_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls <= 2 else 999.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class MutatingVectorizer:
    version = "mutating_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        pages[0]["page_template_family"] = "mutated"
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class NondeterministicVectorizer:
    version = "nondeterministic_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = float(self.calls)
        return {row["url"]: {"shared_intent": weight} for row in pages}


class ForeignVectorizer:
    version = "foreign_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            pages[0]["url"]: {"shared_intent": 1.0},
            "https://foreign.test/page": {"shared_intent": 1.0},
        }


class CountingVectorizer:
    version = "counting_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def test_vector_bound_envelope_composes_template_graph_zone_and_semantic_evidence():
    left = "https://e.test/articles/a"
    right = "https://e.test/articles/b"
    pages = [page(left), page(right)]
    links = [contextual_link(left, right)]
    before_pages = deepcopy(pages)
    before_links = deepcopy(links)
    vectorizer = StableVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == VECTOR_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["state"] == "verified"
    assert result["reason"] == "validated"
    assert result["assessed_page_identity_count"] == 2
    assert vectorizer.calls == 2
    assert len(result["template_evidence"]["groups"]) == 1
    assert len(result["graph"]["edges"]) == 1
    assert result["graph"]["edges"][0]["strongest_zone"] == "contextual"
    assert result["link_zone_summary"]["version"] == LINK_ZONE_SUMMARY_VERSION
    assert result["link_zone_summary"]["strongest_zone_counts"]["contextual"] == 1
    assert result["semantic_clusters"]["state"] == "candidate"
    assert result["cannibalization_candidates"]["candidate_count"] == 1
    assert result["contextual_internal_link_opportunities"]["candidate_count"] == 1
    assert result["customer_fix_created"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
    assert pages == before_pages
    assert links == before_links


def test_envelope_never_reinvokes_adapter_after_two_call_contract_verification():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = ThirdCallChangesVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "verified"
    assert result["semantic_analysis"]["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_clusters"]["state"] == "candidate"


def test_mutating_adapter_fails_semantic_evidence_closed_but_preserves_local_graph_and_templates():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [contextual_link(pages[0]["url"], pages[1]["url"])]
    before_pages = deepcopy(pages)
    vectorizer = MutatingVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 1
    assert result["state"] == "not_verified"
    assert result["reason"] == "vectorizer_input_mutation"
    assert result["semantic_analysis"]["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_clusters"]["state"] == "not_verified"
    assert len(result["template_evidence"]["groups"]) == 1
    assert len(result["graph"]["edges"]) == 1
    assert pages == before_pages


def test_nondeterministic_adapter_fails_envelope_closed():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = NondeterministicVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "not_verified"
    assert result["reason"] == "vectorizer_nondeterministic"
    assert result["cannibalization_candidates"]["state"] == "not_verified"
    assert result["contextual_internal_link_opportunities"]["state"] == "not_verified"


def test_foreign_vector_population_cannot_be_promoted_to_graph_envelope_evidence():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = ForeignVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "vector_population_mismatch"
    assert result["semantic_analysis"]["semantic_vectorized_pages"] == 0


def test_duplicate_page_identity_is_rejected_before_adapter_execution():
    url = "https://e.test/a"
    pages = [page(url), page(url)]
    vectorizer = CountingVectorizer()

    with pytest.raises(ValueError, match="duplicate_page_identity"):
        build_vector_bound_semantic_graph_evidence(
            pages,
            [],
            vectorizer=vectorizer,
        )

    assert vectorizer.calls == 0


def test_invalid_threshold_is_rejected_before_adapter_execution():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = CountingVectorizer()

    with pytest.raises(ValueError, match="cluster_threshold out of bounds"):
        build_vector_bound_semantic_graph_evidence(
            pages,
            [],
            vectorizer=vectorizer,
            cluster_threshold=True,
        )

    assert vectorizer.calls == 0
