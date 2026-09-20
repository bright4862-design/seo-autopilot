from app.stage3_delivery import select_private_preview


def test_b22_preview_projection_rejects_non_string_customer_fields():
    private_sentinel = "PRIVATE-PREVIEW-EVIDENCE https://private.example/internal"
    preview = select_private_preview(
        [
            {
                "authority_verified": True,
                "preview_allowed": True,
                "evidence_state": "verified",
                "scan_id": "scan-a",
                "owner_id": "owner-a",
                "impact": 5,
                "priority_score": 1.0,
                "rule_id": {"private": private_sentinel},
                "title": [private_sentinel],
                "evidence_summary": {"debug": private_sentinel},
            }
        ],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
    )

    assert preview["state"] == "findings"
    assert preview["findings"] == [
        {
            "rule_id": None,
            "title": None,
            "impact": 5,
            "evidence_summary": None,
        }
    ]
    assert private_sentinel not in repr(preview)


def test_b22_preview_projection_preserves_allowed_string_fields():
    preview = select_private_preview(
        [
            {
                "authority_verified": True,
                "preview_allowed": True,
                "evidence_state": "verified",
                "scan_id": "scan-a",
                "owner_id": "owner-a",
                "impact": 4,
                "priority_score": 0.0,
                "rule_id": "duplicate-main-content",
                "title": "Duplicate main content",
                "evidence_summary": "Verified substantive content similarity.",
            }
        ],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
    )

    assert preview["findings"] == [
        {
            "rule_id": "duplicate-main-content",
            "title": "Duplicate main content",
            "impact": 4,
            "evidence_summary": "Verified substantive content similarity.",
        }
    ]
