from pathlib import Path

import pytest

from app.geo_claim_boundary import assert_claim_boundary, claim_boundary_violations
from app.geo_evidence import assess_geo_pages, extract_geo_evidence


def make_page(html, url='https://example.com/activity/paris-cruise', **overrides):
    page = {
        'url': url,
        'final_url': url,
        'status_code': 200,
        'content_type': 'text/html',
        'page_evidence_class': 'usable_html',
        'canonical_status': 'self_or_equivalent',
        'effective_search_robots_directives': [],
        'discovered_from': ['internal_link'],
        'source_pages': ['https://example.com/activities'],
        'robots_txt_rules_known': True,
        'robots_txt_oai_searchbot_allowed': True,
    }
    page.update(overrides)
    page['geo_evidence'] = extract_geo_evidence(html, page)
    return page


def state_map(page, **kwargs):
    result = assess_geo_pages([page], parent_authoritative=True, entry_verified=True, **kwargs)
    return result, {row['check_id']: row['state'] for row in result['observations']}


def test_funbooker_like_marketplace_product_proves_entity_and_non_article_applicability():
    html = '''<html><head><title>Paris Dinner Cruise</title>
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product",
      "@id":"https://example.com/activity/paris-cruise#product",
      "url":"https://example.com/activity/paris-cruise",
      "name":"Paris Dinner Cruise"
    }</script></head><body><main><h1>Paris Dinner Cruise</h1><p>Book the activity.</p></main></body></html>'''
    result, states = state_map(make_page(html))
    assert states['subject_identity'] == 'pass'
    assert states['schema_agreement'] == 'pass'
    assert states['entity_details'] == 'not_verified'
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_applicable'
    assert result['dimensions']['support']['coverage'] == 0
    assert result['score'] is None  # no threshold weakening
    assert result['authority_verified'] is False


def test_article_jsonld_graph_can_supply_bounded_positive_support_evidence():
    html = '''<html><head><title>How to choose a venue</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[{
      "@type":"Article","@id":"https://example.com/guides/venue#article",
      "mainEntityOfPage":{"@id":"https://example.com/guides/venue"},
      "headline":"How to choose a venue",
      "author":{"@type":"Person","name":"A. Writer","url":"https://example.com/authors/a-writer"},
      "datePublished":"2021-04-03",
      "citation":["https://example.org/research"]
    }]}</script></head><body><main><h1>How to choose a venue</h1><p>Guide text.</p></main></body></html>'''
    _, states = state_map(make_page(html, url='https://example.com/guides/venue'))
    assert states['subject_identity'] == 'pass'
    assert states['schema_agreement'] == 'pass'
    assert states['accountability'] == 'pass'
    assert states['date_context'] == 'pass'
    assert states['source_attribution'] == 'pass'


def test_schema_absent_remains_not_applicable_only_for_schema_agreement():
    html = '<html><head><title>About</title></head><body><main><h1>About</h1><p>Company overview.</p></main></body></html>'
    _, states = state_map(make_page(html, url='https://example.com/about'))
    assert states['schema_agreement'] == 'not_applicable'
    assert states['accountability'] == 'not_verified'
    assert states['date_context'] == 'not_verified'
    assert states['source_attribution'] == 'not_verified'


def test_explicit_article_without_support_evidence_stays_unknown_not_failure_or_na():
    html = '<html><head><title>Guide</title></head><body><main><h1>Guide</h1><article><p>Text only.</p></article></main></body></html>'
    _, states = state_map(make_page(html, url='https://example.com/guide'))
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


def test_mismatched_product_name_does_not_guess_subject_or_support_applicability():
    html = '''<html><head><title>Paris Dinner Cruise</title>
    <script type="application/ld+json">{"@type":"Product","url":"https://example.com/activity/paris-cruise","name":"Different Product"}</script>
    </head><body><main><h1>Paris Dinner Cruise</h1><p>Book it.</p></main></body></html>'''
    _, states = state_map(make_page(html))
    assert states['subject_identity'] == 'not_verified'
    assert states['schema_agreement'] == 'not_verified'
    assert states['accountability'] == 'not_verified'


def test_js_only_uncertainty_revokes_structured_positive_evidence():
    html = '''<html><head><title>Paris Dinner Cruise</title>
    <script type="application/ld+json">{"@type":"Product","url":"https://example.com/activity/paris-cruise","name":"Paris Dinner Cruise"}</script>
    </head><body><main><h1>Paris Dinner Cruise</h1></main></body></html>'''
    page = make_page(html)
    page['client_rendering_suspected'] = True
    result, states = state_map(page)
    assert set(states.values()) == {'not_verified'}
    assert result['score'] is None


def test_access_limited_scan_suppresses_content_diagnostics_and_score():
    html = '<html><head><title>About</title></head><body><main><h1>About</h1></main></body></html>'
    result, states = state_map(make_page(html), access_limited=True)
    assert set(states.values()) == {'not_verified'}
    assert result['assessment_status'] == 'access_limited'
    assert result['score'] is None and result['dimensions'] == {}


def test_structured_address_is_positive_only_when_bound_subject_matches_heading():
    html = '''<html><head><title>Acme Paris</title>
    <script type="application/ld+json">{"@type":"LocalBusiness","@id":"https://example.com/paris#business","name":"Acme Paris",
      "address":{"@type":"PostalAddress","streetAddress":"10 Rue Exemple","addressLocality":"Paris"}}</script>
    </head><body><main><h1>Acme Paris</h1><p>Location.</p></main></body></html>'''
    _, states = state_map(make_page(html, url='https://example.com/paris'))
    assert states['subject_identity'] == states['entity_details'] == states['schema_agreement'] == 'pass'
    assert states['accountability'] == 'not_applicable'


def test_claim_boundary_lint_rejects_provider_outcome_promises_but_allows_disclaimers():
    bad = [
        'FixList helps you rank in ChatGPT.',
        'See your visibility in Perplexity.',
        'Track citations in AI Overviews.',
        'Measure traffic from ChatGPT.',
    ]
    for text in bad:
        with pytest.raises(ValueError):
            assert_claim_boundary(text)
    assert claim_boundary_violations('FixList does not measure rankings, citations, visibility, or traffic in ChatGPT or Perplexity.') == ()
    assert claim_boundary_violations('GEO readiness is a structural diagnostic, not a prediction of citations in AI Overviews.') == ()


def test_customer_geo_copy_files_do_not_make_provider_outcome_claims():
    root = Path(__file__).resolve().parents[2]
    candidates = []
    for path in [
        root / 'src' / 'lib' / 'geoReadinessPresentation.js',
        root / 'src' / 'components' / 'fixlist' / 'GeoReadinessPanel.jsx',
        *sorted((root / 'base44' / 'functions').glob('getCustomerScanResult*/geoReadiness.js')),
    ]:
        if path.exists():
            candidates.append(path)
    for path in candidates:
        violations = claim_boundary_violations(path.read_text(encoding='utf-8'))
        assert not violations, f'{path}: {violations}'


def test_schema_free_explicit_article_fixture_still_meets_existing_v1_gates():
    html = '''<html><head><title>Acme</title></head><body><main aria-labelledby="subject"><h1 id="subject">Acme</h1>
    <address>10 Main Street</address><article><a rel="author" href="https://example.com/author">A. Writer</a>
    <time aria-label="Published" datetime="1998-01-01">January 1, 1998</time>
    <blockquote cite="https://example.org/source">Quoted material</blockquote><a href="https://example.org/source">Source</a>
    </article></main></body></html>'''
    result, states = state_map(make_page(html, url='https://example.com/'))
    assert states['schema_agreement'] == 'not_applicable'
    assert result['assessment_status'] == 'assessed'
    assert result['score'] == 100 and result['coverage'] == 1


def test_nested_arbitrary_jsonld_objects_are_not_recursively_guessed_as_subjects():
    html = '''<html><head><title>Paris Dinner Cruise</title>
    <script type="application/ld+json">{"@type":"WebPage","mainEntity":{"thing":{"@type":"Product","name":"Paris Dinner Cruise"}}}</script>
    </head><body><main><h1>Paris Dinner Cruise</h1></main></body></html>'''
    _, states = state_map(make_page(html))
    assert states['subject_identity'] == 'not_verified'
    assert states['schema_agreement'] == 'not_verified'
    assert states['accountability'] == 'not_verified'
