from app import repair_contract_v2
from app.scan_job import build_completion_envelope, create_authority_seal
from app.stage3_delivery import DEFAULT_PRESENTATION_LIMIT


def _page(index: int, *, indexable: bool = True) -> dict:
    url = f"https://example.com/products/{index}"
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": indexable,
        "page_template_family": "product_page",
        "page_value_role": "money",
    }


def _fix(index: int, *, high_impact: bool = False, broken: bool = False) -> dict:
    url = f"https://example.com/products/{index}"
    if broken:
        rule = "broken_page"
        category = "404_error"
        prefix = "broken"
        priority = "critical"
        action_priority = "fix_first"
    elif high_impact:
        rule = "duplicate_content"
        category = "duplicate_content"
        prefix = "duplicate"
        priority = "high"
        action_priority = "fix_first"
    else:
        rule = "missing_meta_description"
        category = "meta_description"
        prefix = "meta"
        priority = "medium"
        action_priority = "improve"
    return {
        "fix_id": f"{prefix}-{index}",
        "rule": rule,
        "category": category,
        "priority": priority,
        "base_severity": priority,
        "evidence_class": "confirmed_problem",
        "action_priority": action_priority,
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


def _apply_with_all_candidates(monkeypatch, fixes: list[dict], pages: list[dict]) -> dict:
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
    return repair_contract_v2.apply_canonical_repair_contract(review, scan_result)


def test_b21_ranked_delivery_and_counts_are_attached_before_signed_completion(monkeypatch):
    # Use a family-scoped high-impact candidate rather than a cross-cutting
    # access failure: B19 intentionally leaves cross-cutting reach unknown, while
    # B21's ordering requirement applies to candidates with a comparable B19
    # four-factor score.
    fixes = [_fix(index) for index in range(39)] + [_fix(39, high_impact=True)]
    pages = [_page(index) for index in range(40)]

    integrated = _apply_with_all_candidates(monkeypatch, fixes, pages)
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

    scan_result = {
        "scan_id": "scan-stage3-b21",
        "scan_run_id": "scan-stage3-b21",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": pages,
    }
    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    assert envelope["review"]["stage3_delivery"] == delivery
    assert envelope["review"]["canonical_repairs"][0].get("stage3_counts") is not None
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")


def test_b21_unknown_b19_score_cannot_displace_known_zero_score_before_truncation(monkeypatch):
    # 35 positive known-score candidates + one known score of exactly zero fill
    # the 36-item presentation set. The final broken-page repair is cross-cutting,
    # so B19 truthfully leaves its reach/composite score unknown. It must not be
    # treated as score zero and then use impact as a substitute comparison that
    # displaces the genuinely known zero-score repair.
    fixes = [_fix(index) for index in range(35)]
    fixes.append(_fix(35))
    fixes.append(_fix(36, broken=True))
    pages = [_page(index) for index in range(35)]
    pages.append(_page(35, indexable=False))
    pages.append(_page(36))

    integrated = _apply_with_all_candidates(monkeypatch, fixes, pages)
    delivery = integrated["stage3_delivery"]
    by_id = {item["fix_id"]: item for item in integrated["canonical_repairs"]}

    zero_factors = by_id["meta-35"]["stage3_priority_factors"]
    unknown_factors = by_id["broken-36"]["stage3_priority_factors"]
    assert zero_factors["score_state"] == "known"
    assert zero_factors["priority_factor_score"] == 0.0
    assert unknown_factors["score_state"] == "unknown"
    assert unknown_factors["priority_factor_score"] is None

    assert delivery["eligible_candidate_count"] == 37
    assert delivery["displayed_candidate_count"] == DEFAULT_PRESENTATION_LIMIT
    assert delivery["presentation_omitted_count"] == 1
    assert "meta-35" in delivery["displayed_fix_ids"]
    assert "broken-36" not in delivery["displayed_fix_ids"]

    # Prove the truncation decision is not merely a helper result: it is the exact
    # Review payload authenticated by the existing completion HMAC. This protects
    # the real customer/persistence authority seam from reintroducing unknown-as-zero
    # ordering after the B21 presentation cap has been applied.
    scan_result = {
        "scan_id": "scan-stage3-b21",
        "scan_run_id": "scan-stage3-b21",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": pages,
    }
    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    signed_delivery = envelope["review"]["stage3_delivery"]
    assert signed_delivery == delivery
    assert "meta-35" in signed_delivery["displayed_fix_ids"]
    assert "broken-36" not in signed_delivery["displayed_fix_ids"]
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")
