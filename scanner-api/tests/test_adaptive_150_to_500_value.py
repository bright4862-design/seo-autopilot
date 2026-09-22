from copy import deepcopy

import pytest

from app.adaptive_150_to_500_value import (
    ADAPTIVE_150_TO_500_CORPUS_VERSION,
    summarize_150_to_500_value_corpus,
    validate_150_to_500_value_corpus,
)


def _fp(char):
    return char * 64


def _row(
    target,
    pages,
    *,
    fingerprint,
    cumulative_findings,
    reference_covered,
    new_findings,
    cumulative_high,
    reference_high_covered,
    new_high,
    new_templates=1,
    new_families=1,
    new_routes=1,
):
    return {
        "strategy": "smart",
        "target": target,
        "pages_assessed": pages,
        "pages_added": pages if target == 150 else max(0, pages - 150),
        "population_fingerprint": fingerprint,
        "cumulative_finding_fingerprints": cumulative_findings,
        "reference_findings_covered": reference_covered,
        "new_finding_fingerprints": new_findings,
        "new_template_keys": new_templates,
        "new_families": new_families,
        "new_route_signatures": new_routes,
        "cumulative_high_impact_finding_fingerprints": cumulative_high,
        "reference_high_impact_findings_covered": reference_high_covered,
        "new_high_impact_finding_fingerprints": new_high,
    }


def _result(
    *,
    candidate_count=1000,
    ref=20,
    covered150=8,
    covered500=18,
    findings150=8,
    findings500=18,
    new500=10,
    ref_high=4,
    high150=1,
    high500=4,
    new_high500=3,
    high_state="observed",
    fp150=None,
    fp500=None,
    valid=True,
):
    pages150 = min(150, candidate_count)
    pages500 = min(500, candidate_count)
    fp150 = fp150 or _fp("a")
    fp500 = fp500 or (_fp("b") if pages500 > pages150 else fp150)
    smart150 = _row(
        150,
        pages150,
        fingerprint=fp150,
        cumulative_findings=findings150,
        reference_covered=covered150,
        new_findings=findings150,
        cumulative_high=high150 if high_state == "observed" else None,
        reference_high_covered=high150 if high_state == "observed" else None,
        new_high=high150 if high_state == "observed" else None,
        new_templates=2,
        new_families=2,
        new_routes=2,
    )
    smart500 = _row(
        500,
        pages500,
        fingerprint=fp500,
        cumulative_findings=findings500,
        reference_covered=covered500,
        new_findings=new500,
        cumulative_high=high500 if high_state == "observed" else None,
        reference_high_covered=high500 if high_state == "observed" else None,
        new_high=new_high500 if high_state == "observed" else None,
        new_templates=5,
        new_families=4,
        new_routes=7,
    )
    smart1000 = dict(smart500, target=1000, pages_assessed=min(1000, candidate_count))
    return {
        "_integrity_valid": valid,
        "candidate_count": candidate_count,
        "reference_finding_fingerprints": ref,
        "reference_high_impact_finding_fingerprints": ref_high if high_state == "observed" else None,
        "high_impact_evidence_state": high_state,
        "smart": (smart150, smart500, smart1000),
    }


def test_corpus_measures_incremental_value_from_standard_150_to_smart_500(monkeypatch):
    import app.adaptive_150_to_500_value as module

    monkeypatch.setattr(
        module,
        "validate_marginal_population_integrity",
        lambda result: {
            "valid": result.get("_integrity_valid", True) is True,
            "reason": "ok" if result.get("_integrity_valid", True) is True else "fixture_invalid",
        },
    )
    corpus = summarize_150_to_500_value_corpus({"b.test": _result(), "a.test": _result()})
    assert corpus["version"] == ADAPTIVE_150_TO_500_CORPUS_VERSION
    assert corpus["valid"] is True
    assert corpus["state"] == "observed"
    assert corpus["site_ids"] == ("a.test", "b.test")
    assert corpus["full_150_to_500_sites"] == 2
    assert corpus["full_smart_150_to_500_pages_added"] == 700
    assert corpus["full_smart_150_to_500_new_findings"] == 20
    assert corpus["full_smart_150_to_500_new_finding_yield_per_100"] == 2.8571
    assert corpus["full_smart_150_reference_finding_coverage"] == 0.4
    assert corpus["full_smart_500_reference_finding_coverage"] == 0.9
    assert corpus["production_budget_authorized"] is False
    assert corpus["site_fully_understood"] is False


def _patch_integrity(monkeypatch):
    import app.adaptive_150_to_500_value as module

    monkeypatch.setattr(
        module,
        "validate_marginal_population_integrity",
        lambda result: {
            "valid": result.get("_integrity_valid", True) is True,
            "reason": "ok" if result.get("_integrity_valid", True) is True else "fixture_invalid",
        },
    )


def test_inventory_limited_sites_stay_visible_but_do_not_drive_full_500_aggregate(monkeypatch):
    _patch_integrity(monkeypatch)
    limited = _result(
        candidate_count=300,
        ref=12,
        covered150=5,
        covered500=12,
        findings150=5,
        findings500=12,
        new500=7,
        ref_high=2,
        high150=1,
        high500=2,
        new_high500=1,
    )
    corpus = summarize_150_to_500_value_corpus({"full": _result(), "limited": limited})
    assert corpus["site_count"] == 2
    assert corpus["full_150_to_500_sites"] == 1
    assert corpus["inventory_limited_sites"] == 1
    assert corpus["full_smart_150_to_500_pages_added"] == 350


def test_no_full_500_site_is_truthful_insufficient_evidence_not_zero_value_claim(monkeypatch):
    _patch_integrity(monkeypatch)
    limited = _result(
        candidate_count=300,
        ref=12,
        covered150=5,
        covered500=12,
        findings150=5,
        findings500=12,
        new500=7,
        ref_high=2,
        high150=1,
        high500=2,
        new_high500=1,
    )
    corpus = summarize_150_to_500_value_corpus({"limited": limited})
    assert corpus["valid"] is True
    assert corpus["state"] == "insufficient_evidence"
    assert corpus["reason"] == "no_full_150_to_500_sites"
    assert corpus["full_smart_150_to_500_new_finding_yield_per_100"] is None


def test_unknown_high_impact_evidence_remains_unknown(monkeypatch):
    _patch_integrity(monkeypatch)
    source = _result(
        high_state="not_observed",
        ref_high=0,
        high150=0,
        high500=0,
        new_high500=0,
    )
    corpus = summarize_150_to_500_value_corpus({"site": source})
    assert corpus["high_impact_evidence_state"] == "not_observed"
    assert corpus["full_smart_150_to_500_new_high_impact_findings"] is None
    assert corpus["full_smart_150_to_500_new_high_impact_yield_per_100"] is None


def test_partially_observed_high_impact_corpus_does_not_sum_known_sites_as_complete(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus(
        {
            "observed": _result(),
            "unknown": _result(
                high_state="not_observed",
                ref_high=0,
                high150=0,
                high500=0,
                new_high500=0,
            ),
        }
    )
    assert corpus["high_impact_evidence_state"] == "partially_observed"
    assert corpus["full_high_impact_observed_sites"] == 1
    assert corpus["full_smart_150_to_500_new_high_impact_findings"] is None


def test_member_source_integrity_failure_fails_closed(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({"site": _result(valid=False)})
    assert corpus["valid"] is False
    assert corpus["reason"].startswith("member_invalid:site:fixture_invalid")


@pytest.mark.parametrize("site_id", ["", " padded", "padded "])
def test_invalid_site_identity_fails_closed(monkeypatch, site_id):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({site_id: _result()})
    assert corpus["valid"] is False
    assert corpus["reason"] == "invalid_site_identity"


def test_validator_rejects_forged_aggregate_yield(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({"site": _result()})
    forged = deepcopy(corpus)
    forged["full_smart_150_to_500_new_finding_yield_per_100"] = 999.0
    validation = validate_150_to_500_value_corpus(forged)
    assert validation["valid"] is False
    assert validation["reason"] == "full_smart_150_to_500_new_finding_yield_per_100_mismatch"


def test_validator_rejects_false_budget_and_completeness_claims(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({"site": _result()})
    forged = deepcopy(corpus)
    forged["production_budget_authorized"] = True
    assert validate_150_to_500_value_corpus(forged)["reason"] == "production_budget_claim_invalid"
    forged = deepcopy(corpus)
    forged["site_fully_understood"] = True
    assert validate_150_to_500_value_corpus(forged)["reason"] == "site_completeness_claim_invalid"
    forged = deepcopy(corpus)
    forged["population_scope_complete"] = True
    assert validate_150_to_500_value_corpus(forged)["reason"] == "population_scope_claim_invalid"


def test_validator_rejects_population_fingerprint_tampering(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({"site": _result()})
    forged = deepcopy(corpus)
    forged["sites"][0]["smart_500_population_fingerprint"] = "z" * 64
    validation = validate_150_to_500_value_corpus(forged)
    assert validation["valid"] is False
    assert validation["reason"] == "member_population_fingerprint_invalid"


def test_validator_rejects_forged_member_high_impact_yield(monkeypatch):
    _patch_integrity(monkeypatch)
    corpus = summarize_150_to_500_value_corpus({"site": _result()})
    forged = deepcopy(corpus)
    forged["sites"][0]["smart_150_to_500_new_high_impact_yield_per_100"] = 99.0
    validation = validate_150_to_500_value_corpus(forged)
    assert validation["valid"] is False
    assert validation["reason"] == "member_high_impact_yield_mismatch"


def test_inputs_are_not_mutated(monkeypatch):
    _patch_integrity(monkeypatch)
    source = _result()
    before = deepcopy(source)
    summarize_150_to_500_value_corpus({"site": source})
    assert source == before
