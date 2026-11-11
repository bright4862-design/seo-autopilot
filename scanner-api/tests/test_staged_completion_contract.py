import pytest

from app import scan_job
from app.authority_seal import create_authority_seal


@pytest.mark.asyncio
async def test_worker_generation_is_context_local_and_legacy_default_unchanged(monkeypatch):
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "test-key")
    names = []
    async def invoke(client, name, payload, **kwargs):
        names.append(name)
        return {"status_code": 200, "body": {"success": True, "scanRun": {"id": "s"}}}
    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    await scan_job.read_scan_run(None, "s")
    with scan_job.worker_function_generation("V9"):
        await scan_job.read_scan_run(None, "s")
    await scan_job.read_scan_run(None, "s")
    assert names == ["durableScanWorkerControlV8", "durableScanWorkerControlV9", "durableScanWorkerControlV8"]


def test_progress_is_signed_but_does_not_change_legacy_control_documents():
    legacy = scan_job.build_control_envelope("read", "key", scan_id="s")
    assert set(legacy) == {"version", "action", "scan_id", "identity", "failure", "proof"}
    progress = scan_job.build_control_envelope(
        "progress", "key", identity={"scan_id": "s"},
        progress={"pages_crawled": 50, "pages_planned": 500},
    )
    signed = {key: value for key, value in progress.items() if key != "proof"}
    assert progress["proof"] == create_authority_seal(signed, "key")


def test_legacy_review_envelope_defaults_stay_byte_compatible_and_500_is_explicit():
    basic = scan_job.build_authority_review_payload({"pages_crawled": 150})
    assert basic["scan_mode"] == basic["canonical_mode"] == "standard_150"
    assert "page_cap" not in basic
    extended = scan_job.build_authority_review_payload({
        "pages_crawled": 500, "scan_mode": "standard_500", "page_cap": 500,
        "crawled_pages": [{"url": f"https://example.com/{i}"} for i in range(500)],
    })
    assert extended["scan_mode"] == extended["canonical_mode"] == "standard_500"
    assert extended["page_cap"] == 500
    assert len(extended["crawled_pages"]) == 60


def test_importance_is_public_but_private_page_evidence_stays_internal():
    result = scan_job.build_authority_review_payload({"crawled_pages": [{
        "url": "https://example.com/", "importance_score": 1.0,
        "importance_tier": "critical", "selection_reason": "Homepage",
        "main_text": "private body", "_reachability_links": ["/private"],
    }]})
    page = result["crawled_pages"][0]
    assert page["importance_score"] == 1.0
    assert page["selection_reason"] == "Homepage"
    assert "main_text" not in page
    assert "_reachability_links" not in page


def test_importance_ranks_repairs_without_overriding_verified_gsc():
    from app.stage3_priority_factors import build_four_factor_priority, GSC_PAGE_VALUE_EVIDENCE_VERSION
    fix = {"rule": "missing_meta_description", "verification_state": "verified",
           "affected_pages": ["/solutions/a"], "page_template_family": "product_page"}
    pages = [{"url": "/solutions/a", "importance_score": 0.8,
              "page_template_family": "product_page", "indexable": True}]
    result = build_four_factor_priority(fix, pages)
    assert result["page_value"] == 0.8
    assert result["page_value_source"] == "page_importance"
    fix["gsc_priority_evidence"] = {"version": GSC_PAGE_VALUE_EVIDENCE_VERSION,
        "provider": "gsc", "state": "verified", "freshness_state": "current", "normalized_page_value": 0.9}
    assert build_four_factor_priority(fix, pages)["page_value_source"] == "base_role+gsc_verified"


@pytest.mark.asyncio
async def test_partial_staged_result_is_demoted_even_when_review_would_be_authoritative(monkeypatch):
    scan = {"id": "scan-partial", "attempt_count": 1, "status": "crawling",
            "scan_mode": "standard_500", "page_cap": 500,
            "respect_robots_txt": True, "owner_attested_robots_override": False}
    async def read(client, scan_id):
        return scan
    captured = []
    async def limited(client, current, result, reviewed, key, **kwargs):
        captured.append(reviewed)
        return {"ok": True, "limited": True}
    monkeypatch.setattr(scan_job, "read_scan_run", read)
    monkeypatch.setattr(scan_job, "persist_limited_result", limited)
    review = {"release_gate_eligible": True, "score_is_provisional": False,
              "site_fingerprint": {"coverage_assessment": {"state": "sufficient", "reasons": []}},
              "recommendations": []}
    with scan_job.worker_function_generation("V9"):
        outcome = await scan_job.complete_authority(None, scan, {
            "pages_crawled": 50, "pipeline_limited": True, "pipeline_limit_reason": "wall_budget",
            "respect_robots_txt": True, "owner_attested_robots_override": False,
        }, "key", review=review)
    assert outcome["limited"] is True
    assert captured[0]["release_gate_eligible"] is False
    assert captured[0]["coverage_state"] == "limited_coverage"
    assert captured[0]["site_fingerprint"]["coverage_assessment"]["authoritative"] is False
    assert review["release_gate_eligible"] is True


@pytest.mark.asyncio
async def test_cancelled_scan_cannot_be_reviewed_or_persisted(monkeypatch):
    scan = {"id": "cancelled-scan", "status": "cancelled", "attempt_count": 1}
    async def read(client, scan_id):
        return scan
    monkeypatch.setattr(scan_job, "read_scan_run", read)
    outcome = await scan_job.complete_authority(None, scan, {}, "key")
    assert outcome["failure_code"] == "already_terminal"
    assert outcome["superseded"] is True


def test_v9_transport_deduplicates_equal_aliases_without_truncating_evidence():
    pages = [{"url": f"https://example.com/{index}"} for index in range(500)]
    result = {"pages": pages, "crawled_pages": pages, "raw_findings": [{"rule": "missing_h1"}] * 500}
    review = {"recommendations": [{"fix_id": "a"}], "fixes": [{"fix_id": "a"}],
              "canonical_repairs": [{"fix_id": "a"}], "stage3_delivery": {"proof": "kept"}}
    scan = {"id": "scan", "owner_user_id": "owner", "project_id": "project"}
    legacy = scan_job.build_completion_envelope(scan, result, review, "key")
    with scan_job.worker_function_generation("V9"):
        compact = scan_job.build_completion_envelope(scan, result, review, "key")
    assert len(compact["scan"]["crawled_pages"]) == 500
    assert len(compact["scan"]["raw_findings"]) == 500
    assert "pages" not in compact["scan"]
    assert "fixes" not in compact["review"]
    assert compact["review"]["canonical_repairs"] == review["canonical_repairs"]
    assert compact["review"]["stage3_delivery"] == review["stage3_delivery"]
    assert "pages" in legacy["scan"] and "fixes" in legacy["review"]
    assert "pages" in result and "fixes" in review
