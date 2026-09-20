from app import repair_contract_v2
from app.scan_job import build_completion_envelope, create_authority_seal
from app.stage3_delivery import DEFAULT_PRESENTATION_LIMIT


def _page(index: int) -> dict:
    url = f"https://example.com/products/{index}"
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "product_page",
        "page_value_role": "money",
    }


def _fix(index: int, *, high_impact: bool = False) -> dict:
    url = f"https://example.com/products/{index}"
    rule = "duplicate_content" if high_impact else "missing_meta_description"
    return {
        "fix_id": f"{'duplicate' if high_impact else 'meta'}-{index}",
        "rule": rule,
        "category": "duplicate_content" if high_impact else "meta_description",
        "priority": "high" if high_impact else "medium",
        "base_severity": "high" if high_impact else "medium",
        "evidence_class": "confirmed_problem",
        "action_priority": "fix_first" if high_impact else "improve",
        "priority_reason": "verified synthetic delivery fixture",
        "page_scope": "page",
        "page_template_family": "product_page",
        "affected_pages": [url],
        "confidence_score": 95,
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "repair_surface": f"cms_field_{index}",
        "remediation_family": f"repair_{index}",
        "issue_title": f"candidate {index}",
    }


def _scan_record() -> dict:
    return {
        "id": "scan-stage3-b21",
        "owner_user_id": "owner-stage3",
        "project_id": "project-stage3",
        "request_id": "request-stage3-b21",
        "idempotency_key": "idem-stage3-b21",
        "attempt_count": 1,
    }


def test_b21_ranked_delivery_and_counts_are_attached_before_signed_completion(monkeypatch):
    # Use a family-scoped high-impact candidate rather than a cross-cutting
    # access failure: B19 intentionally leaves cross-cutting reach unknown, while
    # B21's ordering requirement applies to candidates with a comparable B19
    # four-factor score.
    fixes = [_fix(index) for index in range(39)] + [_fix(39, high_impact=True)]
    pages = [_page(index) for index in range(40)]
    review = {"cleaned_fixes": fixes}
    scan_result = {
        "scan_id": "scan-stage3-b21",
        "scan_run_id": "scan-stage3-b21",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": pages,
    }

    # The real shadow builder applies an upstream presentation limit. B21 must be
    # proven at the later canonical authority seam with every eligible candidate
    # still present, so isolate that seam while retaining the normal canonical
    # validator and identity derivation.
    monkeypatch.setattr(
        repair_contract_v2,
        "build_calibrated_shadow_review_analysis",
        lambda review_result, _pages, **_kwargs: {"proposed_fixes": list(review_result["cleaned_fixes"])},
    )

    integrated = repair_contract_v2.apply_canonical_repair_contract(review, scan_result)
    delivery = integrated["stage3_delivery"]

    assert delivery["eligible_candidate_count"] == 40
    assert delivery["displayed_candidate_count"] == DEFAULT_PRESENTATION_LIMIT
    assert delivery["presentation_truncated"] is True
    assert delivery["presentation_omitted_count"] == 4
    assert delivery["displayed_fix_ids"][0] == "duplicate-39"
    assert "duplicate-39" in delivery["displayed_fix_ids"]
    assert len(delivery["displayed_fix_ids"]) == DEFAULT_PRESENTATION_LIMIT
    assert "displayed_candidates" not in delivery

    duplicate = next(item for item in integrated["canonical_repairs"] if item["fix_id"] == "duplicate-39")
    factors = duplicate["stage3_priority_factors"]
    assert factors["score_state"] == "known"
    assert factors["priority_factor_score"] > 0
    counts = duplicate["stage3_counts"]
    assert counts["unique_affected_page_count"] == 1
    assert counts["observation_count"] == 0
    assert counts["known_population_count"] is None
    assert counts["displayed_sample_count"] == 1
    assert counts["displayed_samples"] == ["https://example.com/products/39"]
    assert counts["examples_partial"] is False

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    assert envelope["review"]["stage3_delivery"] == delivery
    assert envelope["review"]["canonical_repairs"][0].get("stage3_counts") is not None
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")
