from app.repair_contract_v2 import _group_canonical_repairs


def _page(url: str) -> dict:
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "collection_page",
    }


def test_provisional_fingerprint_does_not_merge_distinct_customer_actions():
    """A related-pattern fingerprint is not proof of one shared repair."""
    base = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "base_severity": "medium",
        "action_priority": "improve",
        "evidence_class": "improvement",
        "page_scope": "page",
        "page_template_family": "collection_page",
        "page_count": 1,
        "affected_pages_complete": False,
        "difficulty": "easy",
        "repair_fingerprint": "provisional-same-fingerprint",
        "repair_identity_state": "provisional",
        "repair_identity_stable": False,
    }
    first = {
        **base,
        "fix_id": "first",
        "affected_pages": ["https://example.com/a"],
    }
    second = {
        **base,
        "fix_id": "second",
        "affected_pages": ["https://example.com/b"],
    }

    grouped = _group_canonical_repairs(
        [first, second],
        [_page("https://example.com/a"), _page("https://example.com/b")],
    )

    assert [item["fix_id"] for item in grouped] == ["first", "second"]
    assert all(len(item["repair_evidence_groups"]) == 1 for item in grouped)
