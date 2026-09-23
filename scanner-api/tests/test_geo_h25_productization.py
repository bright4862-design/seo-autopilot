from pathlib import Path

import pytest

from app.geo_claim_boundary import assert_claim_boundary, claim_boundary_violations
from app.geo_evidence_v2 import assess_geo_pages, extract_geo_evidence


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
      "author":{"@context":"https://schema.org","@type":"Person","name":"A. Writer","url":"https://example.com/authors/a-writer"},
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
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","url":"https://example.com/activity/paris-cruise","name":"Different Product"}</script>
    </head><body><main><h1>Paris Dinner Cruise</h1><p>Book it.</p></main></body></html>'''
    _, states = state_map(make_page(html))
    assert states['subject_identity'] == 'not_verified'
    assert states['schema_agreement'] == 'not_verified'
    assert states['accountability'] == 'not_verified'


def test_js_only_uncertainty_revokes_structured_positive_evidence():
    html = '''<html><head><title>Paris Dinner Cruise</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","url":"https://example.com/activity/paris-cruise","name":"Paris Dinner Cruise"}</script>
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
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","@id":"https://example.com/paris#business","name":"Acme Paris",
      "address":{"@context":"https://schema.org","@type":"PostalAddress","streetAddress":"10 Rue Exemple","addressLocality":"Paris"}}</script>
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
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","mainEntity":{"thing":{"@context":"https://schema.org","@type":"Product","name":"Paris Dinner Cruise"}}}</script>
    </head><body><main><h1>Paris Dinner Cruise</h1></main></body></html>'''
    _, states = state_map(make_page(html))
    assert states['subject_identity'] == 'not_verified'
    assert states['schema_agreement'] == 'not_verified'
    assert states['accountability'] == 'not_verified'


def structured_html(entity, *, extra=''):
    import json
    return ('<html><head><title>Paris Dinner Cruise</title>'
            '<script type="application/ld+json">' + json.dumps(entity) + '</script>'
            + extra + '</head><body><main><h1>Paris Dinner Cruise</h1>'
            '<p>Book this cruise.</p></main></body></html>')


def product(**overrides):
    result = {'@context': 'https://schema.org', '@type': 'Product',
              'url': 'https://example.com/activity/paris-cruise',
              'name': 'Paris Dinner Cruise'}
    result.update(overrides)
    return result


@pytest.mark.parametrize('entity', [
    product(url='https://example.com/different-page'),
    {key: value for key, value in product().items() if key != 'url'},
    product(**{'@context': 'https://unrelated.example/schema'}),
    product(**{'@type': 'https://unrelated.example/Product'}),
    product(**{'@context': {'@vocab': 'https://schema.org/', 'Product': 'https://unrelated.example/Product'}}),
])
def test_ambiguous_or_foreign_subject_cannot_establish_entity_or_non_article_state(entity):
    _, states = state_map(make_page(structured_html(entity)))
    assert states['subject_identity'] == 'not_verified'
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


def test_article_support_requires_matching_page_subject_not_only_shared_page_url():
    entity = product(**{'@type': 'Article', 'name': 'Different guide',
                        'author': {'name': 'Writer', 'url': 'https://example.com/writer'},
                        'datePublished': '2024-01-01', 'citation': 'https://example.com/source'})
    _, states = state_map(make_page(structured_html(entity)))
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


@pytest.mark.parametrize('extra', [
    '<script type="application/ld+json">{malformed</script>',
    '<script type="application/ld+json">' + (' ' * 100_001) + '</script>',
    '<div itemscope itemtype="https://schema.org/Article">An article</div>',
    ''.join('<script type="application/ld+json">{}</script>' for _ in range(25)),
], ids=['malformed', 'oversized', 'article-microdata', 'script-limit'])
def test_incomplete_or_article_markup_cannot_establish_non_article_exclusion(extra):
    _, states = state_map(make_page(structured_html(product(), extra=extra)))
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


def test_v1_evidence_is_never_silently_reinterpreted_as_v2():
    from app.geo_evidence import extract_geo_evidence as extract_v1, assess_geo_pages as assess_v1
    from app.geo_evidence_v2 import VERSION
    html = structured_html(product())
    page = make_page(html)
    assert page['geo_evidence']['version'] == VERSION
    with pytest.raises(ValueError, match='Malformed retained GEO evidence'):
        assess_v1([page])
    page['geo_evidence'] = extract_v1(html, page)
    with pytest.raises(ValueError, match='Malformed retained GEO evidence'):
        state_map(page)
    old = assess_v1([page], parent_authoritative=True, entry_verified=True)
    assert old['evidence_adapter_version'] == 'geo_evidence_v1'
    assert old['authority_verified'] is False


@pytest.mark.parametrize('entity', [
    product(mainEntity={'@type': 'Article', 'headline': 'Guide'}),
    product(**{'@type': ['Product'] + ['Thing'] * 24 + ['Article']}),
    product(address={'@context': {'@vocab': 'https://unrelated.example/'}, '@type': 'PostalAddress', 'streetAddress': 'Not a schema address'}),
], ids=['nested-article', 'truncated-types', 'overridden-nested-context'])
def test_uninspected_or_ambiguous_structure_cannot_be_used_to_exclude_article_checks(entity):
    _, states = state_map(make_page(structured_html(entity)))
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


@pytest.mark.parametrize('entity', [
    product(**{'@type': 'https://schema.org/Product', '@context': {'name': 'https://other.example/value', 'url': 'https://other.example/link'}}),
    product(**{'@type': 'NotASchemaType'}),
])
def test_foreign_property_context_or_unknown_type_is_not_schema_agreement(entity):
    _, states = state_map(make_page(structured_html(entity)))
    assert states['schema_agreement'] == states['subject_identity'] == 'not_verified'


def test_nested_author_context_does_not_manufacture_article_evidence():
    entity = product(**{'@type': 'Article', 'author': {'@context': 'https://other.example/', 'name': 'Writer', 'url': 'https://example.com/writer'}})
    _, states = state_map(make_page(structured_html(entity)))
    assert states['accountability'] == 'not_verified'


def test_duplicate_jsonld_keys_cannot_hide_article_semantics():
    html = '<html><title>Paris Dinner Cruise</title><main><h1>Paris Dinner Cruise</h1></main><script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","@type":"Product","url":"https://example.com/activity/paris-cruise","name":"Paris Dinner Cruise"}</script></html>'
    _, states = state_map(make_page(html))
    assert states['accountability'] == states['date_context'] == states['source_attribution'] == 'not_verified'


def test_remapped_main_entity_url_cannot_supply_page_identity():
    entity = product(mainEntityOfPage={'@context': {'url': 'https://unrelated.example/value'}, 'url': 'https://example.com/activity/paris-cruise'})
    del entity['url']
    _, states = state_map(make_page(structured_html(entity)))
    assert states['subject_identity'] == states['schema_agreement'] == 'not_verified'


@pytest.mark.parametrize('field,value,check', [
    ('citation', 'Smith et al 2024', 'source_attribution'),
    ('citation', 'Smith2024', 'source_attribution'),
    ('author', {'name': 'Writer', 'url': 'not a URL'}, 'accountability'),
    ('citation', 'https://example.com/bad\nurl', 'source_attribution'),
])
def test_plain_citation_text_and_invalid_urls_do_not_manufacture_source_links(field, value, check):
    entity = product(**{'@type': 'Article', field: value})
    _, states = state_map(make_page(structured_html(entity)))
    assert states[check] == 'not_verified'


def test_explicit_relative_structured_links_are_retained_without_fetching():
    entity = product(**{'@type': 'Article', 'author': {'name': 'Writer', 'url': '/writer'}, 'citation': './source'})
    _, states = state_map(make_page(structured_html(entity)))
    assert states['accountability'] == states['source_attribution'] == 'pass'
