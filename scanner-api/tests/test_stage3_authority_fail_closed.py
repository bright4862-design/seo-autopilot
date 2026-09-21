import pytest

from app.stage3_delivery import build_handoff_v2, select_private_preview


def test_b22_unverified_authority_cannot_publish_sufficient_coverage_qualification():
    preview = select_private_preview(
        [],
        authority_verified=False,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        coverage_qualification={
            "state": "sufficient",
            "text": "PRIVATE-COVERAGE-DIAGNOSTIC https://private.example/internal",
        },
    )

    assert preview == {
        "state": "not_available",
        "findings": [],
        "coverage_qualification": None,
    }


@pytest.mark.parametrize(
    "operator_authorized",
    [1, "true", {"authorized": True}],
)
def test_b24_suppressed_findings_require_literal_operator_authorization(operator_authorized):
    handoff = build_handoff_v2(
        scan_identity={"scan_id": "scan-a"},
        fixes=[],
        user_agent="FixListBot/1.0",
        suppressed_findings=[
            {
                "rule_id": "operator-only",
                "reason": "PRIVATE-SUPPRESSION-REASON",
            }
        ],
        operator_authorized=operator_authorized,
    )

    assert "suppressed_findings" not in handoff
