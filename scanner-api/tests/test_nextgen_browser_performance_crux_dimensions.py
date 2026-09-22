from copy import deepcopy

from app.nextgen_browser_performance_crux_dimensions import (
    CRUX_FIELD_DIMENSION_VERSION,
    normalize_crux_field_dimension_context,
    validate_crux_field_dimension_contract,
)


def payload(*, form_factor="PHONE"):
    key = {"url": "https://Example.COM/page#frag"}
    if form_factor is not ...:
        key["formFactor"] = form_factor
    return {
        "record": {
            "key": key,
            "metrics": {"largest_contentful_paint": {"percentiles": {"p75": 2450}}},
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 8, "day": 20},
                "lastDate": {"year": 2026, "month": 9, "day": 16},
            },
        }
    }


def bound_field(*, state="connected"):
    coverage = {"first_date": "2026-08-20", "last_date": "2026-09-16"}
    return {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None if state == "connected" else state,
        "scope": "url",
        "source_url": "https://example.com/page",
        "metrics": {"lcp": {"value": 2450.0, "unit": "ms", "rating": None}} if state == "connected" else None,
        "adapter_version": "nextgen_crux_bound_provider_v1",
        "base_adapter_version": "nextgen_performance_provider_adapter_v1",
        "coverage_period": coverage if state == "connected" else None,
        "provenance": {
            "version": "nextgen_crux_provenance_v1",
            "record_scope": "url" if state == "connected" else None,
            "record_source_url": "https://example.com/page" if state == "connected" else None,
            "requested_scope": "url",
            "requested_source_url": "https://example.com/page",
            "coverage_period": coverage if state == "connected" else None,
            "observed_at": "2026-09-22",
        },
    }


def test_connected_phone_dimension_is_explicit_and_bound():
    evidence = normalize_crux_field_dimension_context(
        payload(), bound_field(), requested_form_factor="phone"
    )
    assert evidence["version"] == CRUX_FIELD_DIMENSION_VERSION
    assert evidence["state"] == "connected"
    assert evidence["form_factor"] == "phone"
    assert evidence["aggregation"] == "single_form_factor"
    assert evidence["dimension_source"] == "record_key_form_factor"
    assert evidence["requested_form_factor"] == "phone"
    assert validate_crux_field_dimension_contract(
        payload(), bound_field(), evidence, requested_form_factor="phone"
    )["valid"] is True


def test_omitted_provider_form_factor_means_all_form_factors():
    raw = payload(form_factor=...)
    evidence = normalize_crux_field_dimension_context(raw, bound_field())
    assert evidence["state"] == "connected"
    assert evidence["form_factor"] == "all"
    assert evidence["aggregation"] == "all_form_factors"
    assert evidence["dimension_source"] == "record_key_form_factor_omitted"


def test_provider_tablet_and_desktop_dimensions_are_preserved():
    for provider_value, expected in (("TABLET", "tablet"), ("desktop", "desktop")):
        evidence = normalize_crux_field_dimension_context(
            payload(form_factor=provider_value), bound_field()
        )
        assert evidence["state"] == "connected"
        assert evidence["form_factor"] == expected


def test_requested_dimension_mismatch_fails_closed():
    evidence = normalize_crux_field_dimension_context(
        payload(form_factor="DESKTOP"), bound_field(), requested_form_factor="phone"
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_requested_form_factor_mismatch"
    assert evidence["form_factor"] is None
    assert evidence["aggregation"] is None


def test_requested_all_requires_aggregate_provider_record():
    connected = normalize_crux_field_dimension_context(
        payload(form_factor=...), bound_field(), requested_form_factor="all_form_factors"
    )
    assert connected["state"] == "connected"
    assert connected["form_factor"] == "all"

    mismatch = normalize_crux_field_dimension_context(
        payload(form_factor="PHONE"), bound_field(), requested_form_factor="all"
    )
    assert mismatch["state"] == "unavailable"
    assert mismatch["reason"] == "crux_requested_form_factor_mismatch"


def test_invalid_provider_form_factor_is_not_guessed():
    evidence = normalize_crux_field_dimension_context(
        payload(form_factor="SMART_TV"), bound_field()
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_record_form_factor_invalid"
    assert evidence["form_factor"] is None


def test_invalid_requested_form_factor_is_not_guessed():
    evidence = normalize_crux_field_dimension_context(
        payload(), bound_field(), requested_form_factor="mobile"
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_requested_form_factor_invalid"


def test_raw_record_identity_must_match_bound_field_identity():
    raw = payload()
    raw["record"]["key"]["url"] = "https://example.com/other"
    evidence = normalize_crux_field_dimension_context(raw, bound_field())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_dimension_source_identity_mismatch"


def test_raw_collection_period_must_match_bound_field_coverage():
    raw = payload()
    raw["record"]["collectionPeriod"]["lastDate"]["day"] = 15
    evidence = normalize_crux_field_dimension_context(raw, bound_field())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_dimension_collection_period_mismatch"


def test_invalid_or_foreign_bound_contract_fails_closed():
    bad_adapter = bound_field()
    bad_adapter["adapter_version"] = "other"
    evidence = normalize_crux_field_dimension_context(payload(), bad_adapter)
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "bound_crux_adapter_version_invalid"

    foreign = bound_field()
    foreign["provider"] = "PageSpeed Insights / CrUX"
    evidence = normalize_crux_field_dimension_context(payload(), foreign)
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "bound_crux_evidence_kind_invalid"


def test_non_connected_bound_state_retains_no_device_claim():
    evidence = normalize_crux_field_dimension_context(
        payload(), bound_field(state="rate_limited"), requested_form_factor="phone"
    )
    assert evidence["state"] == "rate_limited"
    assert evidence["reason"] == "rate_limited"
    assert evidence["form_factor"] is None
    assert evidence["aggregation"] is None
    assert evidence["coverage_period"] is None


def test_integrity_rejects_device_or_aggregation_tampering():
    raw = payload()
    bound = bound_field()
    evidence = normalize_crux_field_dimension_context(raw, bound)
    evidence["form_factor"] = "desktop"
    evidence["aggregation"] = "all_form_factors"
    result = validate_crux_field_dimension_contract(raw, bound, evidence)
    assert result["valid"] is False
    assert "form_factor_mismatch" in result["reasons"]
    assert "aggregation_mismatch" in result["reasons"]


def test_dimension_normalization_does_not_mutate_inputs():
    raw = payload()
    bound = bound_field()
    raw_before = deepcopy(raw)
    bound_before = deepcopy(bound)
    normalize_crux_field_dimension_context(
        raw, bound, requested_form_factor="PHONE"
    )
    assert raw == raw_before
    assert bound == bound_before
