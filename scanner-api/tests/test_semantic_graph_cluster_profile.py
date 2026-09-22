from hashlib import sha256

from app.semantic_graph import semantic_clusters
from app.semantic_graph_cluster_profile import (
    SEMANTIC_CLUSTER_PROFILE_VERSION,
    semantic_cluster_profile_evidence,
)


def cluster_id(*urls):
    ordered = sorted(urls)
    return "sem_" + sha256("|".join(ordered).encode("utf-8")).hexdigest()[:12]


def vector_evidence(vectors, *, coverage="complete", pair_complete=True):
    return {
        "version": "semantic_vector_contract_v1",
        "scope": "observed_assessed_pages_only",
        "state": "verified",
        "reason": "validated",
        "determinism_checked": True,
        "determinism_verified": True,
        "input_isolation_enforced": True,
        "semantic_vector_coverage_state": coverage,
        "semantic_pair_population_complete": pair_complete,
        "semantic_pair_scope": (
            "all_assessed_page_identities"
            if pair_complete
            else "vectorized_assessed_page_subset"
        ),
        "vectors": vectors,
    }


class StaticVectorizer:
    version = "test_static_vectors_v1"

    def __init__(self, vectors):
        self._vectors = vectors

    def vectors(self, pages):
        return {
            url: dict(vector)
            for url, vector in self._vectors.items()
        }


def authentic_cluster_evidence(vectors, *, threshold=0.0):
    evidence = semantic_clusters(
        [],
        threshold=threshold,
        vectorizer=StaticVectorizer(vectors),
    )
    evidence = dict(evidence)
    evidence["version"] = "semantic_cluster_evidence_v1_vector_bound"
    evidence["scope"] = "observed_assessed_pages_only"
    evidence["state"] = (
        "candidate" if evidence["clusters"] else "no_candidate_observed"
    )
    return evidence


def row(*urls):
    ordered = sorted(urls)
    return {
        "cluster_id": cluster_id(*ordered),
        "page_count": len(ordered),
        "urls": ordered,
    }


def test_profiles_valid_cluster_with_deterministic_representative_and_terms():
    vectors = {
        "https://e.test/a": {"seo": 2.0, "audit": 1.0},
        "https://e.test/b": {"seo": 2.0, "audit": 1.0},
        "https://e.test/c": {"seo": 1.0, "links": 2.0},
    }
    result = semantic_cluster_profile_evidence(
        authentic_cluster_evidence(vectors, threshold=0.39),
        vector_evidence(vectors),
    )

    assert result["version"] == SEMANTIC_CLUSTER_PROFILE_VERSION
    assert result["state"] == "verified"
    assert result["cluster_count"] == 1
    profile = result["profiles"][0]
    assert profile["state"] == "verified"
    assert profile["representative_url"] == "https://e.test/a"
    assert [item["term"] for item in profile["top_terms"]][:2] == ["seo", "audit"]
    assert profile["member_to_centroid_similarity_min"] <= profile[
        "member_to_centroid_similarity_mean"
    ] <= profile["member_to_centroid_similarity_max"]
    assert result["sitewide_semantic_coverage_claim"] is False
    assert result["customer_fix_created"] is False


def test_profile_is_independent_of_cluster_and_vector_input_order():
    urls = ["https://e.test/a", "https://e.test/b", "https://e.test/c"]
    vectors_a = {
        urls[0]: {"x": 2.0, "y": 1.0},
        urls[1]: {"x": 1.0, "y": 2.0},
        urls[2]: {"x": 1.0, "y": 1.0},
    }
    vectors_b = {
        urls[2]: {"y": 1.0, "x": 1.0},
        urls[1]: {"y": 2.0, "x": 1.0},
        urls[0]: {"y": 1.0, "x": 2.0},
    }
    forward = semantic_cluster_profile_evidence(
        authentic_cluster_evidence(vectors_a, threshold=0.0),
        vector_evidence(vectors_a),
    )
    reverse_clusters = authentic_cluster_evidence(vectors_b, threshold=0.0)
    reverse_clusters["clusters"] = list(reversed(reverse_clusters["clusters"]))
    for cluster in reverse_clusters["clusters"]:
        cluster["urls"] = list(reversed(cluster["urls"]))
    reverse = semantic_cluster_profile_evidence(
        reverse_clusters,
        vector_evidence(vectors_b),
    )

    assert forward == reverse


def test_forged_cluster_identity_fails_closed():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["clusters"][0]["cluster_id"] = "sem_forged"
    result = semantic_cluster_profile_evidence(
        clusters,
        vector_evidence(vectors),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_id_mismatch"
    assert result["profiles"] == []


def test_cluster_members_may_not_overlap():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
        "https://e.test/c": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["clusters"] = [
        row("https://e.test/a", "https://e.test/b"),
        row("https://e.test/b", "https://e.test/c"),
    ]
    result = semantic_cluster_profile_evidence(
        clusters,
        vector_evidence(vectors),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_member_overlap"


def test_cluster_member_must_exist_in_validated_vector_population():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/c": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["clusters"] = [row("https://e.test/a", "https://e.test/b")]
    result = semantic_cluster_profile_evidence(
        clusters,
        vector_evidence(vectors),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_vector_population_mismatch"


def test_forged_valid_member_partition_that_does_not_follow_threshold_fails_closed():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
        "https://e.test/c": {"y": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["clusters"] = [row("https://e.test/a", "https://e.test/c")]
    result = semantic_cluster_profile_evidence(
        clusters,
        vector_evidence(vectors),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_derivation_mismatch"
    assert result["profiles"] == []


def test_partial_semantic_population_is_preserved_without_sitewide_claim():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    result = semantic_cluster_profile_evidence(
        authentic_cluster_evidence(vectors, threshold=0.9),
        vector_evidence(vectors, coverage="partial", pair_complete=False),
    )

    assert result["state"] == "verified"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "vectorized_assessed_page_subset"
    assert result["sitewide_semantic_coverage_claim"] is False


def test_clean_no_cluster_observed_remains_descriptive_not_sitewide():
    vectors = {"https://e.test/a": {"x": 1.0}}
    result = semantic_cluster_profile_evidence(
        authentic_cluster_evidence(vectors, threshold=0.9),
        vector_evidence(vectors),
    )

    assert result["state"] == "no_cluster_observed"
    assert result["cluster_count"] == 0
    assert result["profiles"] == []
    assert result["sitewide_semantic_coverage_claim"] is False


def test_unverified_vector_integrity_never_profiles_clusters():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    evidence = vector_evidence(vectors)
    evidence["state"] = "not_verified"
    evidence["reason"] = "vectorizer_nondeterministic"
    result = semantic_cluster_profile_evidence(
        authentic_cluster_evidence(vectors, threshold=0.9),
        evidence,
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_vector_integrity_not_verified"
    assert result["profiles"] == []


def test_forged_qualifying_pair_count_fails_closed():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
        "https://e.test/c": {"y": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["qualifying_pair_count"] += 1
    result = semantic_cluster_profile_evidence(clusters, vector_evidence(vectors))

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_qualifying_pair_count_mismatch"


def test_incomplete_pair_scan_cannot_profile_clusters():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["pair_scan_complete"] = False
    result = semantic_cluster_profile_evidence(clusters, vector_evidence(vectors))

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_pair_scan_incomplete"


def test_forged_vectorized_page_count_fails_closed():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["vectorized_pages"] += 1
    result = semantic_cluster_profile_evidence(clusters, vector_evidence(vectors))

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_vectorized_page_count_mismatch"


def test_invalid_cluster_threshold_fails_closed_before_profile_generation():
    vectors = {
        "https://e.test/a": {"x": 1.0},
        "https://e.test/b": {"x": 1.0},
    }
    clusters = authentic_cluster_evidence(vectors, threshold=0.9)
    clusters["threshold"] = True
    result = semantic_cluster_profile_evidence(clusters, vector_evidence(vectors))

    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_threshold_invalid"
    assert result["profiles"] == []
