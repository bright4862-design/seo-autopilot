from copy import deepcopy

from app.nextgen_browser_performance_sample_origin import (
    SAMPLE_ORIGIN_BINDING_INTEGRITY_VERSION,
    SAMPLE_ORIGIN_BINDING_VERSION,
    bind_representative_sample_to_site_origin,
    validate_representative_sample_origin_contract,
)


def _sample(*urls):
    return {
        "version": "nextgen_performance_sample_v1",
        "pages": [
            {
                "url": url,
                "template_family": "product_page",
                "high_value_weight": 1.0,
                "selection_reason": "template_representative",
            }
            for url in urls
        ],
    }


def test_accepts_selected_pages_on_exact_origin():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://example.com/", "https://example.com/products/a?x=1"),
        site_url="https://example.com/start",
    )
    assert evidence == {
        "version": SAMPLE_ORIGIN_BINDING_VERSION,
        "contract": "nextgen_performance_sample_v1",
        "valid": True,
        "reasons": [],
        "site_origin": "https://example.com",
        "selected_pages_checked": 2,
        "selected_same_origin_pages": 2,
        "foreign_origins": [],
    }


def test_normalizes_default_https_port_and_host_case():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://EXAMPLE.com:443/a"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is True
    assert evidence["site_origin"] == "https://example.com"


def test_rejects_foreign_selected_origin_without_retaining_full_url():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://example.com/a", "https://cdn.example.net/path?secret=1"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["reasons"] == ["selected_origin_mismatch"]
    assert evidence["foreign_origins"] == ["https://cdn.example.net"]
    assert evidence["selected_same_origin_pages"] == 1


def test_rejects_scheme_change_as_different_origin():
    evidence = bind_representative_sample_to_site_origin(
        _sample("http://example.com/a"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["foreign_origins"] == ["http://example.com"]


def test_rejects_non_default_port_change_as_different_origin():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://example.com:8443/a"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["foreign_origins"] == ["https://example.com:8443"]


def test_rejects_credential_bearing_site_identity():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://example.com/a"),
        site_url="https://user:pass@example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["site_origin"] is None
    assert evidence["reasons"] == ["site_identity_contains_credentials"]


def test_rejects_credential_bearing_selected_identity_without_echoing_it():
    evidence = bind_representative_sample_to_site_origin(
        _sample("https://user:pass@example.com/a"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["reasons"] == ["selected_row_0_identity_contains_credentials"]
    assert evidence["foreign_origins"] == []


def test_rejects_non_http_selected_identity():
    evidence = bind_representative_sample_to_site_origin(
        _sample("file:///etc/passwd"),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["reasons"] == ["selected_row_0_identity_not_absolute_http"]


def test_rejects_wrong_sample_version_before_trusting_rows():
    sample = _sample("https://example.com/a")
    sample["version"] = "nextgen_performance_sample_v0"
    evidence = bind_representative_sample_to_site_origin(
        sample,
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["reasons"] == ["sample_version_mismatch"]
    assert evidence["selected_pages_checked"] == 0


def test_rejects_non_list_pages():
    sample = {"version": "nextgen_performance_sample_v1", "pages": "https://example.com/"}
    evidence = bind_representative_sample_to_site_origin(
        sample,
        site_url="https://example.com/",
    )
    assert evidence["valid"] is False
    assert evidence["reasons"] == ["sample_pages_not_list"]


def test_empty_valid_sample_is_same_origin_valid_but_grants_no_execution():
    evidence = bind_representative_sample_to_site_origin(
        _sample(),
        site_url="https://example.com/",
    )
    assert evidence["valid"] is True
    assert evidence["selected_pages_checked"] == 0
    assert evidence["selected_same_origin_pages"] == 0


def test_integrity_accepts_truthful_valid_binding():
    sample = _sample("https://example.com/a")
    artifact = bind_representative_sample_to_site_origin(sample, site_url="https://example.com/")
    integrity = validate_representative_sample_origin_contract(
        sample,
        site_url="https://example.com/",
        artifact=artifact,
    )
    assert integrity == {
        "version": SAMPLE_ORIGIN_BINDING_INTEGRITY_VERSION,
        "contract": SAMPLE_ORIGIN_BINDING_VERSION,
        "valid": True,
        "reasons": [],
        "expected_binding_valid": True,
    }


def test_integrity_accepts_truthful_fail_closed_binding_but_reports_invalid_source():
    sample = _sample("https://foreign.example/a")
    artifact = bind_representative_sample_to_site_origin(sample, site_url="https://example.com/")
    integrity = validate_representative_sample_origin_contract(
        sample,
        site_url="https://example.com/",
        artifact=artifact,
    )
    assert integrity["valid"] is True
    assert integrity["expected_binding_valid"] is False


def test_integrity_rejects_laundered_foreign_binding():
    sample = _sample("https://foreign.example/a")
    artifact = bind_representative_sample_to_site_origin(sample, site_url="https://example.com/")
    artifact["valid"] = True
    artifact["reasons"] = []
    artifact["foreign_origins"] = []
    integrity = validate_representative_sample_origin_contract(
        sample,
        site_url="https://example.com/",
        artifact=artifact,
    )
    assert integrity["valid"] is False
    assert {"valid_mismatch", "reasons_mismatch", "foreign_origins_mismatch"} <= set(integrity["reasons"])
    assert integrity["expected_binding_valid"] is False


def test_binding_does_not_mutate_inputs():
    sample = _sample("https://example.com/a")
    before = deepcopy(sample)
    artifact = bind_representative_sample_to_site_origin(sample, site_url="https://example.com/")
    validate_representative_sample_origin_contract(
        sample,
        site_url="https://example.com/",
        artifact=artifact,
    )
    assert sample == before
