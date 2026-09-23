from __future__ import annotations

import pytest

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


def sealed_l2() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T02:00:00Z",
        "authority_proof": "url-scope-proof",
        "website_url": "https://example.com",
        "pages": [
            {
                "url": "https://example.com/real",
                "final_url": "https://example.com/real",
                "status_code": 200,
            }
        ],
        "fixes": [
            {
                "fix_id": "fix-1",
                "evidence_refs": ["https://example.com/real"],
            }
        ],
        "root_causes": [
            {
                "root_cause_id": "root-1",
                "evidence_refs": ["https://example.com/real"],
            }
        ],
        "diagnostics": {},
    }


def annotation(url: str, *, require_live: bool = False) -> dict:
    return {
        "schema_version": "ai_annotation_v2",
        "annotation_id": "url-scope",

        "evidence": [{"url": url, "require_live": require_live}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": [],
        "state_claims": [],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://example.com/diagnostic-url"),
        ("evidence_url", "https://example.com/diagnostic-evidence"),
        ("published_url", "https://example.com/diagnostic-published"),
    ],
)
def test_unrelated_diagnostics_url_fields_do_not_become_evidence_members(field, value):
    source = sealed_l2()
    source["diagnostics"][field] = value
    evidence = build_evidence_set(source)

    assert value not in evidence.url_members
    result = verify_grounded_payload(annotation(value), evidence_set=evidence)
    assert result.status == "rejected"
    assert "url_not_in_evidence" in result.reasons


def test_unrelated_diagnostics_url_lists_do_not_become_evidence_members():
    value = "https://example.com/diagnostic-list"
    source = sealed_l2()
    source["diagnostics"]["evidence_urls"] = [value]
    evidence = build_evidence_set(source)

    assert value not in evidence.url_members
    result = verify_grounded_payload(annotation(value), evidence_set=evidence)
    assert result.status == "rejected"
    assert "url_not_in_evidence" in result.reasons


def test_unrelated_diagnostics_status_cannot_forge_live_evidence():
    value = "https://example.com/plausible-live"
    source = sealed_l2()
    source["diagnostics"].update({"url": value, "status_code": 200})
    evidence = build_evidence_set(source)

    assert value not in evidence.url_members
    assert value not in evidence.live_urls
    result = verify_grounded_payload(annotation(value, require_live=True), evidence_set=evidence)
    assert result.status == "rejected"
    assert "url_not_in_evidence" in result.reasons


@pytest.mark.parametrize(
    ("container", "status_field"),
    [
        ("crawled_pages", "status_code"),
        ("scanned_pages", "http_status"),
        ("crawl_pages", "response_status"),
    ],
)
def test_authorized_page_aliases_are_members_and_live(container, status_field):
    source = sealed_l2()
    source.pop("pages")
    source[container] = [
        {
            "url": "https://example.com/alias",
            "final_url": "https://example.com/alias",
            status_field: 200,
        }
    ]
    evidence = build_evidence_set(source)

    assert "https://example.com/alias" in evidence.url_members
    assert "https://example.com/alias" in evidence.live_urls


def test_verified_final_url_on_page_is_membership_and_live():
    source = sealed_l2()
    source["pages"] = [
        {
            "url": "https://example.com/requested",
            "final_url": "https://example.com/final",
            "verified_final_url": "https://example.com/final",
            "status_code": 200,
        }
    ]
    evidence = build_evidence_set(source)

    assert "https://example.com/final" in evidence.url_members
    assert "https://example.com/final" in evidence.live_urls


def test_fix_and_root_cause_nested_evidence_urls_remain_members():
    source = sealed_l2()
    source["fixes"][0]["url_provenance"] = {
        "published_url": "https://example.com/fix-proof",
        "request_url": "https://example.com/fix-request",
    }
    source["root_causes"][0]["details"] = {
        "evidence_url": "https://example.com/root-proof",
    }
    evidence = build_evidence_set(source)

    assert {
        "https://example.com/fix-proof",
        "https://example.com/fix-request",
        "https://example.com/root-proof",
    } <= evidence.url_members
