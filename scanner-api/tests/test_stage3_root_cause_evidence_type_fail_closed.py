from app.stage3_root_causes import ROOT_CAUSE_EVIDENCE_VERSION, group_evidenced_root_causes


def _fix_with_evidence(*, root_cause_id, evidence_refs, repair_surface_id="surface:template"):
    return {
        "id": "fix-a",
        "affected_pages": ["https://example.com/a"],
        "root_cause_evidence": {
            "version": ROOT_CAUSE_EVIDENCE_VERSION,
            "state": "verified",
            "root_cause_id": root_cause_id,
            "repair_surface_id": repair_surface_id,
            "evidence_refs": evidence_refs,
        },
    }


def test_b20_structured_root_cause_identity_fails_closed_instead_of_becoming_a_string():
    private_marker = "https://private.example/root-cause-debug"
    groups = group_evidenced_root_causes(
        [
            _fix_with_evidence(
                root_cause_id={"operator_debug": private_marker},
                evidence_refs=["evidence:public"],
            )
        ],
        scan_id="scan-a",
    )

    assert len(groups) == 1
    group = groups[0]
    assert group["grouping_state"] == "not_verified"
    assert group["root_cause_id"] is None
    assert private_marker not in repr(group)


def test_b20_structured_evidence_refs_fail_closed_and_cannot_cross_signed_delivery_boundaries():
    private_marker = "https://private.example/evidence-debug"
    groups = group_evidenced_root_causes(
        [
            _fix_with_evidence(
                root_cause_id="root:template",
                evidence_refs=[{"operator_debug": private_marker}],
                repair_surface_id={"operator_debug": "private-surface"},
            )
        ],
        scan_id="scan-a",
    )

    assert len(groups) == 1
    group = groups[0]
    assert group["grouping_state"] == "not_verified"
    assert group["repair_surface_id"] is None
    assert group["contributing_evidence_refs"] == []
    assert private_marker not in repr(group)
    assert "private-surface" not in repr(group)
