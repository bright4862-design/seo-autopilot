import copy

from app.adaptive_marginal_corpus import (
    ADAPTIVE_MARGINAL_CORPUS_VERSION,
    summarize_marginal_gap_corpus,
    validate_marginal_gap_corpus,
)


def _fp(ch):
    return ch * 64


def _source_result(
    *,
    candidate_count=1200,
    reference_findings=100,
    smart_covered=95,
    blind_500_findings=80,
    high_state="observed",
    reference_high=10,
    smart_high_covered=9,
    blind_500_high=7,
):
    final_pages = min(candidate_count, 1000)
    smart_500_pages = min(candidate_count, 500)
    smart = [
        {"pages_assessed": min(candidate_count, 150), "population_fingerprint": _fp("a")},
        {
            "pages_assessed": smart_500_pages,
            "population_fingerprint": _fp("b"),
            "reference_findings_covered": min(smart_covered, reference_findings),
            "reference_high_impact_findings_covered": (
                min(smart_high_covered, reference_high) if high_state == "observed" else None
            ),
        },
        {"pages_assessed": final_pages, "population_fingerprint": _fp("c")},
    ]
    blind = [
        {"pages_assessed": min(candidate_count, 150), "population_fingerprint": _fp("d")},
        {
            "pages_assessed": min(candidate_count, 500),
            "population_fingerprint": _fp("e"),
            "cumulative_finding_fingerprints": min(blind_500_findings, reference_findings),
            "cumulative_high_impact_finding_fingerprints": (
                min(blind_500_high, reference_high) if high_state == "observed" else None
            ),
        },
        {
            "pages_assessed": final_pages,
            "population_fingerprint": _fp("f"),
            "cumulative_finding_fingerprints": reference_findings,
            "cumulative_high_impact_finding_fingerprints": (
                reference_high if high_state == "observed" else None
            ),
        },
    ]
    return {
        "candidate_count": candidate_count,
        "reference_finding_fingerprints": reference_findings,
        "reference_high_impact_finding_fingerprints": reference_high if high_state == "observed" else None,
        "high_impact_evidence_state": high_state,
        "smart": smart,
        "blind": blind,
    }


def test_corpus_aggregates_only_full_500_vs_1000_sites_deterministically(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    alpha = _source_result(reference_findings=100, smart_covered=95, blind_500_findings=80)
    beta = _source_result(reference_findings=50, smart_covered=50, blind_500_findings=40)
    limited = _source_result(candidate_count=700, reference_findings=30, smart_covered=29, blind_500_findings=20)
    corpus = summarize_marginal_gap_corpus({"z-limited": limited, "beta": beta, "alpha": alpha})
    assert corpus["version"] == ADAPTIVE_MARGINAL_CORPUS_VERSION
    assert corpus["valid"] is True
    assert corpus["state"] == "observed"
    assert corpus["site_ids"] == ("alpha", "beta", "z-limited")
    assert corpus["full_500_vs_1000_sites"] == 2
    assert corpus["inventory_limited_sites"] == 1
    assert corpus["full_reference_finding_fingerprints"] == 150
    assert corpus["full_smart_500_reference_findings_covered"] == 145
    assert corpus["full_smart_500_missed_reference_findings"] == 5
    assert corpus["full_smart_500_reference_finding_coverage"] == 0.9667
    assert corpus["full_blind_tail_pages"] == 1000
    assert corpus["full_blind_tail_new_findings"] == 30
    assert corpus["full_blind_tail_new_finding_yield_per_100"] == 3.0
    assert corpus["production_budget_authorized"] is False
    assert corpus["site_fully_understood"] is False


def test_inventory_limited_only_corpus_is_explicitly_insufficient(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({"small": _source_result(candidate_count=700)})
    assert corpus["valid"] is True
    assert corpus["state"] == "insufficient_evidence"
    assert corpus["reason"] == "no_full_500_vs_1000_sites"
    assert corpus["full_500_vs_1000_sites"] == 0
    assert corpus["full_blind_tail_pages"] == 0
    assert corpus["full_smart_500_reference_finding_coverage"] is None
    assert corpus["high_impact_evidence_state"] == "not_applicable"


def test_partial_high_impact_evidence_never_becomes_zero_evidence(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    observed = _source_result(high_state="observed")
    unknown = _source_result(high_state="not_observed")
    corpus = summarize_marginal_gap_corpus({"observed": observed, "unknown": unknown})
    assert corpus["high_impact_evidence_state"] == "partially_observed"
    assert corpus["full_high_impact_observed_sites"] == 1
    assert corpus["full_reference_high_impact_finding_fingerprints"] is None
    assert corpus["full_smart_500_reference_high_impact_coverage"] is None
    assert corpus["full_blind_tail_new_high_impact_findings"] is None


def test_all_observed_high_impact_evidence_is_aggregated_separately(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    first = _source_result(reference_high=10, smart_high_covered=9, blind_500_high=7)
    second = _source_result(reference_high=5, smart_high_covered=5, blind_500_high=4)
    corpus = summarize_marginal_gap_corpus({"a": first, "b": second})
    assert corpus["high_impact_evidence_state"] == "observed"
    assert corpus["full_reference_high_impact_finding_fingerprints"] == 15
    assert corpus["full_smart_500_reference_high_impact_findings_covered"] == 14
    assert corpus["full_smart_500_missed_reference_high_impact_findings"] == 1
    assert corpus["full_smart_500_reference_high_impact_coverage"] == 0.9333
    assert corpus["full_blind_tail_new_high_impact_findings"] == 4
    assert corpus["full_blind_tail_new_high_impact_yield_per_100"] == 0.4


def test_invalid_site_identity_fails_closed_without_sorting_type_error(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({"good": _source_result(), 7: _source_result()})
    assert corpus["valid"] is False
    assert corpus["reason"] == "invalid_site_identity"


def test_invalid_member_population_is_rejected_before_aggregation(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": False, "reason": "population_mismatch"},
    )
    corpus = summarize_marginal_gap_corpus({"bad": _source_result()})
    assert corpus["valid"] is False
    assert corpus["reason"] == "member_invalid:bad:population_mismatch"


def test_summarizer_does_not_mutate_source_results(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    source = {"a": _source_result(), "b": _source_result(candidate_count=700)}
    before = copy.deepcopy(source)
    summarize_marginal_gap_corpus(source)
    assert source == before


def test_validator_rejects_forged_aggregate_count(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({"a": _source_result(), "b": _source_result()})
    forged = copy.deepcopy(corpus)
    forged["full_blind_tail_new_findings"] += 1
    checked = validate_marginal_gap_corpus(forged)
    assert checked["valid"] is False
    assert checked["reason"] == "aggregate_count_mismatch:full_blind_tail_new_findings"


def test_validator_rejects_forged_member_tail_yield(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({"a": _source_result()})
    forged = copy.deepcopy(corpus)
    forged["sites"][0]["blind_tail_new_finding_yield_per_100"] = 999.0
    checked = validate_marginal_gap_corpus(forged)
    assert checked["valid"] is False
    assert checked["reason"] == "member_tail_finding_yield_mismatch"


def test_validator_rejects_false_population_or_budget_authority_claims(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({"a": _source_result()})
    for field in ("population_scope_complete", "production_budget_authorized", "site_fully_understood"):
        forged = copy.deepcopy(corpus)
        forged[field] = True
        checked = validate_marginal_gap_corpus(forged)
        assert checked["valid"] is False


def test_validator_requires_high_impact_aggregate_to_remain_unknown_when_partial(monkeypatch):
    monkeypatch.setattr(
        "app.adaptive_marginal_corpus.validate_marginal_population_integrity",
        lambda result: {"valid": True, "reason": "ok"},
    )
    corpus = summarize_marginal_gap_corpus({
        "observed": _source_result(high_state="observed"),
        "unknown": _source_result(high_state="not_observed"),
    })
    forged = copy.deepcopy(corpus)
    forged["full_blind_tail_new_high_impact_findings"] = 0
    checked = validate_marginal_gap_corpus(forged)
    assert checked["valid"] is False
    assert checked["reason"] == "aggregate_high_impact_must_remain_unknown"
