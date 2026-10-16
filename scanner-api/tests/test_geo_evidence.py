from copy import deepcopy
from urllib import robotparser

import pytest

from app.extract import extract_page
from app.geo_evidence import assess_geo_pages, extract_geo_evidence, MAX_HTML
from app.robots_policy import RobotsPolicy, annotate_robots_evidence, owner_robots_override

HTML = '<html><title>Acme</title><main><h1>Acme</h1><p>Acme services.</p></main></html>'


def page(html=HTML, url='https://example.com/', **kwargs):
    return extract_page(html, url, url, kwargs.pop('status_code', 200), 'text/html', kwargs.pop('discovery', {}), **kwargs)


def states(p):
    return {r['check_id']: r['state'] for r in assess_geo_pages([p])['observations']}


def test_structural_passes_and_unknown_semantics():
    p = page()
    result = states(p)
    assert result['main_text'] == result['page_identity'] == 'pass'
    assert result['schema_agreement'] == 'not_applicable'
    assert result['accountability'] == result['date_context'] == 'not_verified'
    assert assess_geo_pages([p], parent_authoritative=True, entry_verified=True)['score'] is None


@pytest.mark.parametrize('kwargs', [dict(status_code=202), dict(body_truncated=True), dict(response_headers={'cf-mitigated':'challenge'})])
def test_unaccepted_has_no_content_diagnostics(kwargs):
    p = page(**kwargs)
    assert set(states(p).values()) == {'not_verified'}
    assert assess_geo_pages([p])['findings'] == []


@pytest.mark.parametrize('field', ['client_rendering_suspected', 'render_error', 'rendering_failed', 'raw_html_truncated'])
def test_later_uncertainty_revokes_retained_passes(field):
    p = page()
    p[field] = True
    assert set(states(p).values()) == {'not_verified'}


def test_empty_access_limited_and_missing_evidence():
    result = assess_geo_pages([], parent_authoritative=True, access_limited=True)
    assert result['score'] is None and result['assessment_status'] == 'access_limited'
    assert result['findings'] == []
    p = page(); del p['geo_evidence']
    assert set(states(p).values()) == {'not_verified'}


def test_rejects_malformed_duplicates_and_over_cap():
    p = page()
    for pages in [[p, p], [dict(p, url=f'https://example.com/{i}') for i in range(151)], [None], {}]:
        with pytest.raises(ValueError):
            assess_geo_pages(pages)
    p['geo_evidence']['signals']['main_text'] = 'yes'
    with pytest.raises(ValueError):
        assess_geo_pages([p])


def test_deterministic_and_no_mutation():
    pages = [page(url='https://example.com/b'), page(url='https://example.com/a')]
    original = deepcopy(pages)
    assert assess_geo_pages(pages) == assess_geo_pages(list(reversed(pages)))
    extract_geo_evidence(HTML, pages[0])
    assert pages == original


def test_training_optout_and_owner_override_do_not_change_search_policy():
    parser = robotparser.RobotFileParser()
    parser.parse('User-agent: GPTBot\nDisallow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n\nUser-agent: FixListPythonScanner\nDisallow: /'.splitlines())
    policy = RobotsPolicy('https://example.com/robots.txt', 'available', 200, parser)
    p = page()
    with owner_robots_override(True):
        annotate_robots_evidence(p, policy, p['url'])
    assert p['robots_txt_scanner_allowed'] is False
    assert p['robots_txt_fetch_allowed'] is True
    assert states(p)['search_policy'] == 'pass'
    parser = robotparser.RobotFileParser()
    parser.parse('User-agent: OAI-SearchBot\nDisallow: /'.splitlines())
    policy.parser = parser
    with owner_robots_override(True):
        annotate_robots_evidence(p, policy, p['url'])
    assert states(p)['search_policy'] == 'fail'


def test_code_script_template_hidden_examples_ignored():
    p = page(HTML.replace('</main>', '<pre>{{sample}}</pre><code>{{code}}</code><template>{{hidden}}</template><script>{{script}}</script><span hidden>{{secret}}</span></main>'))
    assert states(p)['template_integrity'] == 'pass'
    p = page(HTML.replace('Acme services.', 'Welcome {{city}}.'))
    assert states(p)['template_integrity'] == 'fail'


def test_scope_exclusion_requires_explicit_evidence():
    p = page(HTML.replace('<title>', '<meta name="robots" content="noindex"><title>'), url='https://example.com/login')
    assert states(p)['main_text'] == 'not_verified'
    p.update(geo_scope='intentional_utility', geo_scope_reason='Owner declares sign-in page')
    assert set(states(p).values()) == {'not_applicable'}
    p['discovered_from'] = ['sitemap']
    assert states(p)['indexability'] == 'fail'
    assert states(p)['main_text'] == 'pass'


def test_canonical_variants_not_assessed_as_independent_content():
    p = page(HTML.replace('<title>', '<link rel="canonical" href="https://example.com/other"><title>'))
    assert states(p)['main_text'] == 'not_verified'


def test_positive_structural_fixture_can_meet_gates_with_historical_date():
    html = '''<html><title>Acme</title><main><h1>Acme</h1>
    <section itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Acme</span><address itemprop="address">10 Main Street</address></section>
    <article><a rel="author" href="https://example.com/author">A. Writer</a>
    <time itemprop="datePublished" datetime="1998-01-01">January 1, 1998</time>
    <blockquote cite="https://example.org/source">Quoted material</blockquote><a href="https://example.org/source">Source</a></article></main>
    <script type="application/ld+json">{"url":"https://example.com/","name":"Acme"}</script></html>'''
    p = page(html, discovery={'discovered_from':['internal_link'], 'source_pages':['https://example.com/about']})
    p.update(robots_txt_rules_known=True, robots_txt_oai_searchbot_allowed=True)
    result = assess_geo_pages([p], parent_authoritative=True, entry_verified=True)
    assert result['assessment_status'] == 'assessed'
    assert result['score'] == 100 and result['coverage'] == 1
    assert result['findings'] == []


def test_grouped_bounded_findings_and_access_limited_suppression():
    pages = [page(HTML.replace('Acme services.', '{{city}}'), url=f'https://example.com/{i}') for i in range(8)]
    finding = assess_geo_pages(pages)['findings'][0]
    assert finding['affected_page_count'] == 8
    assert len(finding['evidence_samples']) == 5 and finding['sample_truncated']
    assert len(set(finding['page_ids'])) == 8
    result = assess_geo_pages(pages, access_limited=True)
    assert result['findings'] == []
    assert {o['state'] for o in result['observations']} == {'not_verified'}


def test_bounded_html_rejected_without_partial_assessment():
    assert extract_geo_evidence('x' * (MAX_HTML + 1), page())['accepted'] is False


def test_location_token_and_sanitized_evidence_url():
    p = page(HTML.replace('Acme services.', '#location#'), url='https://example.com/page?token=secret#fragment')
    finding = assess_geo_pages([p])['findings'][0]
    assert finding['evidence_samples'][0]['page_url'] == 'https://example.com/page'
    assert 'secret' not in str(assess_geo_pages([p]))
    first = finding['evidence_samples'][0]['evidence_ref']
    p = page(HTML.replace('Acme services.', '#location# again'), url='https://example.com/page?token=secret#fragment')
    assert assess_geo_pages([p])['findings'][0]['evidence_samples'][0]['evidence_ref'] != first


def test_malformed_discovery_rejected():
    p = page(); p['source_pages'] = 'not a list'
    with pytest.raises(ValueError):
        assess_geo_pages([p])


def test_schema_free_explicit_structure_can_meet_gates():
    html = '''<html><title>Acme</title><main aria-labelledby="subject"><h1 id="subject">Acme</h1>
    <address>Contact: 10 Main Street</address>
    <article><a rel="author" href="https://example.com/author">A. Writer</a>
    <time aria-label="Published" datetime="1998-01-01">January 1, 1998</time>
    <blockquote cite="https://example.org/source">Quoted material</blockquote><a href="https://example.org/source">Source</a></article></main></html>'''
    p = page(html, discovery={'discovered_from':['internal_link'], 'source_pages':['https://example.com/about']})
    p.update(robots_txt_rules_known=True, robots_txt_oai_searchbot_allowed=True)
    result = assess_geo_pages([p], parent_authoritative=True, entry_verified=True)
    assert states(p)['schema_agreement'] == 'not_applicable'
    assert result['assessment_status'] == 'assessed'
    assert result['score'] == 100 and result['coverage'] == 1


def test_public_extract_handles_nested_inline_hidden_nodes():
    p = page(HTML.replace('</main>', '<div style="display:none"><span style="display:none">{{hidden}}</span></div></main>'))
    assert p['page_evidence_class'] == 'usable_html'
    assert p['title'] == 'Acme'
    assert p['geo_evidence']['accepted'] is True
    assert states(p)['template_integrity'] == 'pass'


def test_geo_extraction_exception_preserves_seo_with_rejected_evidence(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('sensitive diagnostic must not be retained')
    monkeypatch.setattr('app.extract.extract_geo_evidence', broken)
    p = page()
    assert p['page_evidence_class'] == 'usable_html'
    assert p['title'] == p['h1'] == 'Acme'
    assert p['geo_evidence']['accepted'] is False
    assert p['geo_evidence']['signals'] == {}
    assert p['geo_evidence_error'] == 'extraction_error'
    result = assess_geo_pages([p], parent_authoritative=True, entry_verified=True)
    assert result['score'] is None and result['findings'] == []
    assert {row['state'] for row in result['observations']} == {'not_verified'}
    assert all('extraction failed' in row['reason'] for row in result['observations'])
    assert 'sensitive diagnostic' not in str(p)


@pytest.mark.parametrize('relation, expected', [('author', 'pass'), ('nofollow author external', 'pass'), ('notauthor', 'not_verified'), ('authorish external', 'not_verified')])
def test_author_requires_exact_relation_token(relation, expected):
    p = page(HTML.replace('</main>', f'<article><a rel="{relation}" href="https://example.com/author">Writer</a></article></main>'))
    assert states(p)['accountability'] == expected


@pytest.mark.parametrize('context', ['accepted', 'truncated', 'excluded', 'access_limited'])
def test_malformed_search_policy_always_rejected(context):
    p = page()
    p['robots_txt_oai_searchbot_allowed'] = 'garbage'
    if context == 'truncated':
        p['raw_html_truncated'] = True
    elif context == 'excluded':
        p.update(effective_search_robots_directives=['noindex'], geo_scope='intentional_utility', geo_scope_reason='Owner declared utility page')
    with pytest.raises(ValueError, match='Malformed OAI search directive'):
        assess_geo_pages([p], access_limited=context == 'access_limited')
