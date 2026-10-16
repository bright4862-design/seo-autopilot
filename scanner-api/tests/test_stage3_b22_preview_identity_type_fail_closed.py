from app.stage3_delivery import select_private_preview


def _candidate(*, scan_id, owner_id):
    return {
        "authority_verified": True,
        "preview_allowed": True,
        "evidence_state": "verified",
        "scan_id": scan_id,
        "owner_id": owner_id,
        "rule_id": "preview-identity",
        "title": "Verified preview finding",
        "impact": 5,
        "priority_score": 5.0,
        "evidence_summary": "Verified evidence",
    }


def test_private_preview_rejects_matching_structured_scan_identity():
    private_scan = {"operator_debug": "private-scan-sentinel"}
    result = select_private_preview(
        [_candidate(scan_id=private_scan, owner_id="owner-123")],
        authority_verified=True,
        requested_scan_id=private_scan,
        requested_owner_id="owner-123",
    )

    assert result["state"] == "not_available"
    assert result["findings"] == []
    assert "private-scan-sentinel" not in repr(result)


def test_private_preview_rejects_matching_structured_owner_identity():
    private_owner = ["private-owner-sentinel"]
    result = select_private_preview(
        [_candidate(scan_id="scan-123", owner_id=private_owner)],
        authority_verified=True,
        requested_scan_id="scan-123",
        requested_owner_id=private_owner,
    )

    assert result["state"] == "not_available"
    assert result["findings"] == []
    assert "private-owner-sentinel" not in repr(result)


def test_private_preview_keeps_literal_exact_string_identity():
    result = select_private_preview(
        [_candidate(scan_id="scan-123", owner_id="owner-123")],
        authority_verified=True,
        requested_scan_id="scan-123",
        requested_owner_id="owner-123",
    )

    assert result["state"] == "findings"
    assert [finding["rule_id"] for finding in result["findings"]] == ["preview-identity"]
