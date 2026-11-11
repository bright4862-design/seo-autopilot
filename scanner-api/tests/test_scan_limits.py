import pytest

from app.scan_limits import current_page_cap, page_cap_for_mode, scan_page_limit
from app.geo_readiness import evaluate_geo
from app.missing_h1_contract import build_missing_h1_comparison_evidence
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION


def test_caps_are_server_owned_and_context_restores_on_failure():
    assert page_cap_for_mode("standard_150") == 150
    assert page_cap_for_mode("standard_500") == 500
    assert current_page_cap() == 150
    with pytest.raises(RuntimeError):
        with scan_page_limit(500):
            assert current_page_cap() == 500
            raise RuntimeError()
    assert current_page_cap() == 150
    for invalid in (True, 0, 501, "500", 150.5):
        with pytest.raises(ValueError):
            with scan_page_limit(invalid):
                pass
    with pytest.raises(ValueError):
        page_cap_for_mode("customer_unlimited")


def test_geo_remains_150_by_default_but_accepts_server_owned_500():
    pages = [f"p{i}" for i in range(500)]
    with pytest.raises(ValueError):
        evaluate_geo(pages, [])
    with scan_page_limit(500):
        assert evaluate_geo(pages, [])["sample_pages"] == 500
        with pytest.raises(ValueError):
            evaluate_geo(pages + ["overflow"], [])


def test_rescan_evidence_retains_all_assessed_pages_at_500():
    pages = [{"url": f"https://example.com/p{i}", "status_code": 200,
              "content_type": "text/html", "h1_count": 1} for i in range(500)]
    kwargs = dict(scan_origin="https://example.com", identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    assert build_missing_h1_comparison_evidence(pages, **kwargs)["observation_count"] == 150
    with scan_page_limit(500):
        assert build_missing_h1_comparison_evidence(pages, **kwargs)["observation_count"] == 500
