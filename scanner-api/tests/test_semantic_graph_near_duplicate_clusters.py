from copy import deepcopy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.semantic_graph_near_duplicate_clusters import (
    NEAR_DUPLICATE_CLUSTER_VERSION,
    near_duplicate_cluster_evidence,
)


def _page(url, shingles=None, *, verified=True):
    return {
        "url": url,
        "main_text_verified": verified,
        "main_text_representation": "sha256_5_token_shingles_v1" if verified else None,
        "main_text": " ".join(shingles or []),
    }


def test_builds_transitive_cluster_and_marks_chaining_without_sitewide_claim():
    a = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc", "dddddddddddddddd"]
    b = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc", "eeeeeeeeeeeeeeee"]
    c = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "eeeeeeeeeeeeeeee", "ffffffffffffffff"]
    result = near_duplicate_cluster_evidence(
        [_page("https://e.test/a", a), _page("https://e.test/b", b), _page("https://e.test/c", c)],
        threshold=0.55,
    )

    assert result["version"] == NEAR_DUPLICATE_CLUSTER_VERSION
    assert result["state"] == "candidate"
    assert result["cluster_count"] == 1
    cluster = result["clusters"][0]
    assert cluster["page_count"] == 3
    assert cluster["chaining_observed"] is True
    assert cluster["all_pairs_meet_threshold"] is False
    assert cluster["pair_similarity_min"] == pytest.approx(1 / 3, abs=1e-6)
    assert result["sitewide_near_duplicate_claim"] is False
    assert result["customer_fix_created"] is False


def test_complete_verified_sample_reports_complete_coverage_and_no_candidate():
    result = near_duplicate_cluster_evidence(
        [
            _page("https://e.test/a", ["aaaaaaaaaaaaaaaa"]),
            _page("https://e.test/b", ["bbbbbbbbbbbbbbbb"]),
        ]
    )
    assert result["state"] == "no_candidate_observed"
    assert result["coverage_state"] == "complete"
    assert result["pair_scan_complete"] is True
    assert result["cluster_count"] == 0


def test_partial_verified_sample_never_becomes_sitewide_coverage_claim():
    result = near_duplicate_cluster_evidence(
        [
            _page("https://e.test/a", ["aaaaaaaaaaaaaaaa"]),
            _page("https://e.test/b", verified=False),
            {"title": "missing identity"},
        ]
    )
    assert result["coverage_state"] == "partial"
    assert result["eligible_page_count"] == 1
    assert result["unverified_main_content_page_count"] == 1
    assert result["unidentified_page_count"] == 1
    assert result["sitewide_coverage_claim"] is False


def test_duplicate_page_identity_fails_closed():
    result = near_duplicate_cluster_evidence(
        [
            _page("https://e.test/a", ["aaaaaaaaaaaaaaaa"]),
            _page("https://e.test/a", ["aaaaaaaaaaaaaaaa"]),
        ]
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "duplicate_page_identity"
    assert result["pair_scan_complete"] is False
    assert result["clusters"] == []


def test_no_verified_b10_main_content_is_not_verified_not_clean():
    result = near_duplicate_cluster_evidence(
        [_page("https://e.test/a", verified=False), _page("https://e.test/b", verified=False)]
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "no_verified_b10_main_content"
    assert result["coverage_state"] == "not_verified"


def test_representative_is_highest_mean_similarity_with_deterministic_url_tie_break():
    shared = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc"]
    result = near_duplicate_cluster_evidence(
        [
            _page("https://e.test/b", shared),
            _page("https://e.test/a", shared),
        ],
        threshold=1.0,
    )
    cluster = result["clusters"][0]
    assert cluster["representative_url"] == "https://e.test/a"
    assert cluster["representative_mean_similarity"] == 1.0
    assert cluster["weakest_pair"] == cluster["strongest_pair"]


def test_output_is_deterministic_across_page_order():
    pages = [
        _page("https://e.test/c", ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]),
        _page("https://e.test/a", ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]),
        _page("https://e.test/b", ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]),
    ]
    forward = near_duplicate_cluster_evidence(pages)
    reverse = near_duplicate_cluster_evidence(list(reversed(pages)))
    assert forward == reverse


def test_input_is_not_mutated():
    pages = [
        _page("https://e.test/a", ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]),
        _page("https://e.test/b", ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]),
    ]
    before = deepcopy(pages)
    near_duplicate_cluster_evidence(pages)
    assert pages == before


@pytest.mark.parametrize("threshold", [0.49, 1.01, True, "0.82"])
def test_threshold_validation_fails_closed_at_call_boundary(threshold):
    with pytest.raises(ValueError, match="threshold out of bounds"):
        near_duplicate_cluster_evidence(
            [_page("https://e.test/a", ["aaaaaaaaaaaaaaaa"])],
            threshold=threshold,
        )
