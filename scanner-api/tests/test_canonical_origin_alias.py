import pytest

from app.canonical_validation import (
    CANONICAL_TARGET_EVIDENCE_VERSION,
    _is_transport_origin_alias,
    validate_canonical_targets,
)
from app.scanner import canonical_target_finding


def canonical_page(
    requested_url: str,
    target: str,
    *,
    final_url: str | None = None,
    path: str = "/chocolate-milk/",
) -> dict:
    return {
        "url": requested_url,
        "final_url": final_url or requested_url,
        "path": path,
        "status_code": 200,
        "indexable": True,
        "indexability_state": "Indexable",
        "canonical": target,
        "canonical_status": "canonical_to_different_url",
    }


def test_transport_origin_alias_requires_same_scheme_path_and_query():
    assert _is_transport_origin_alias(
        "https://hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/chocolate-milk",
    )
    assert not _is_transport_origin_alias(
        "http://hartzlerdairy.com/chocolate-milk",
        "https://www.hartzlerdairy.com/chocolate-milk",
    )
    assert not _is_transport_origin_alias(
        "https://hartzlerdairy.com/chocolate-milk",
        "https://www.hartzlerdairy.com/milk",
    )
    assert not _is_transport_origin_alias(
        "https://hartzlerdairy.com/chocolate-milk?size=small",
        "https://www.hartzlerdairy.com/chocolate-milk?size=large",
    )


@pytest.mark.asyncio
async def test_requested_apex_final_www_and_www_canonical_are_one_page_identity():
    page = canonical_page(
        "https://hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        final_url="https://www.hartzlerdairy.com/chocolate-milk/",
    )

    summary = await validate_canonical_targets(None, [page], None)

    assert page["canonical_target_state"] == "origin_alias_equivalent"
    assert page["canonical_target_evidence_source"] == "origin_alias_contract"
    assert page["canonical_target_validation_version"] == CANONICAL_TARGET_EVIDENCE_VERSION
    assert summary["origin_alias_equivalent_count"] == 1
    assert summary["representative_issues"] == []
    assert canonical_target_finding(page) is None


@pytest.mark.asyncio
async def test_genuine_external_canonical_still_requires_verification():
    page = canonical_page(
        "https://hartzlerdairy.com/chocolate-milk/",
        "https://example.org/chocolate-milk/",
        final_url="https://www.hartzlerdairy.com/chocolate-milk/",
    )

    summary = await validate_canonical_targets(None, [page], None)

    assert page["canonical_target_state"] == "cross_domain_needs_verification"
    assert summary["origin_alias_equivalent_count"] == 0
    assert summary["representative_issues"] == [
        {
            "page": "/chocolate-milk/",
            "target": "https://example.org/chocolate-milk",
            "state": "cross_domain_needs_verification",
        }
    ]
    assert canonical_target_finding(page)["rule"] == "canonical_cross_domain"


@pytest.mark.asyncio
async def test_apex_www_path_change_is_not_hidden_as_an_alias():
    page = canonical_page(
        "https://hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/milk/",
        final_url="https://www.hartzlerdairy.com/chocolate-milk/",
    )

    await validate_canonical_targets(None, [page], None)

    assert page["canonical_target_state"] != "origin_alias_equivalent"
