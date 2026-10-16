import copy
import json
from pathlib import Path

from app import geo_runtime
from app.scan_job import build_authority_review_payload


def fixture():
    return json.loads((Path(__file__).parents[2] / 'tests/fixtures/geo/runtime.json').read_text())


def test_entry_requires_accepted_matching_entry_not_any_usable_page():
    data = fixture()
    scan = data['scan']
    result = geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=True)
    assert result['assessment_gates']['entry_verified'] is True
    assert result['assessment_status'] == 'assessed'
    scan['submitted_url'] = 'https://example.com/another'
    result = geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=True)
    assert result['score'] is None
    assert 'entry_not_verified' in result['reasons']


def test_runtime_failure_is_bounded_null_and_does_not_mutate_seo(monkeypatch):
    scan = fixture()['scan']
    before = copy.deepcopy(scan)
    def fail(*args, **kwargs):
        raise RuntimeError('secret URL or HTML')
    monkeypatch.setattr(geo_runtime, 'assess_geo_pages', fail)
    result = geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=True)
    assert result == geo_runtime.empty_geo_readiness('evaluation_error')
    assert scan == before
    assert 'secret' not in json.dumps(result)


def test_authority_review_payload_retains_one_top_level_geo_object():
    scan = fixture()['scan']
    scan['geo_readiness'] = fixture()['assessed']
    result = build_authority_review_payload(scan)
    assert result['geo_readiness'] == scan['geo_readiness']
    assert 'geo_readiness' not in result['technical_audit_summary']


def test_access_limited_runtime_has_no_findings_or_score():
    scan = fixture()['scan']
    result = geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=False, access_limited=True)
    assert result['score'] is None
    assert result['dimensions'] == {}
    assert result['findings'] == []


def test_entry_trailing_slash_is_not_an_equivalent_resource():
    scan = fixture()['scan']
    scan['submitted_url'] = 'https://example.com'
    result = geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=True)
    assert result['assessment_gates']['entry_verified'] is False
    scan['submitted_url'] = 'https://example.com/#section'
    assert geo_runtime.assess_review_geo(scan, scan['crawled_pages'], parent_authoritative=True)['assessment_gates']['entry_verified'] is True
