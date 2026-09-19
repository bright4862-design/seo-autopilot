import pytest
from app.extract import extract_page
from app.scanner import build_findings, group_findings
from app.scan_job import build_local_review
from app.indexability_postprocess import apply_indexability_quality_to_result
from app.search_applicability import SEARCH_METADATA_RULES

ORIGIN = 'https://example.com'

def page(path='/x', body='<h1>Useful page</h1><p>Useful information for visitors.</p>', head='', **extra):
    result = extract_page(f'<html><head>{head}</head><body><main>{body}</main></body></html>', ORIGIN+path, ORIGIN+path,200,'text/html',{'discovered_from':['internal_link']})
    result.update({'page_template_family':'activity_detail', **extra})
    return result

def scan(pages):
    raw = build_findings(pages)
    return {'success':True,'website_url':ORIGIN, 'crawl_scope':{'requested_origin':ORIGIN},'pages':pages,
            'pages_found':len(pages),'pages_crawled':len(pages),'raw_findings':raw,'findings':group_findings(raw)}

def repairs(pages):
    return build_local_review(scan(pages))['canonical_repairs']

@pytest.mark.parametrize('kind', ['utility','sitemap','declared','canonical'])
def test_inapplicable_metadata_does_not_return_in_scanner_or_review(kind):
    p = page(head='<meta name="robots" content="noindex">' if kind != 'canonical' else '',
             geo_scope='intentional_utility',geo_scope_reason='Account utility')
    if kind == 'sitemap': p['discovered_from']=['sitemap']
    if kind == 'declared': p['geo_search_intent']=True
    if kind == 'canonical': p.update(canonical_status='canonical_to_different_url',canonical_target_state='valid',canonical='https://example.com/preferred')
    result = apply_indexability_quality_to_result(scan([p]))
    for source in [build_findings([p]), result['findings'], build_local_review(result)['canonical_repairs']]:
        assert not [f for f in source if f['rule'] in SEARCH_METADATA_RULES]
    if kind in {'sitemap','declared'}:
        conflicts=[f for f in result['raw_findings'] if f['rule']=='sitemap_indexability_conflict']
        assert len(conflicts)==1
        if kind=='declared': assert 'sitemap' not in conflicts[0]['plain_english_explanation'].lower()


def test_uncertain_alt_remains_review_only_through_both_producers():
    p=page(body='<h1>Gallery</h1><img src="photo.jpg">')
    for source in [build_findings([p]),repairs([p])]:
        [fix]=[f for f in source if f['category']=='image_alt_text']
        assert fix['rule']=='image_alt_review'
        assert fix['non_scoring'] is True
        assert fix['verification_state']=='needs_verification'
        assert 'review' in (fix.get('issue_title') or fix.get('title')).lower()


def test_mixed_alt_group_counts_only_material_pages_without_hiding_uncertainty():
    pages=[page('/x',body='<h1>Exhibit</h1><figure><img src="photo.jpg"><figcaption>A described exhibit</figcaption></figure>'),
           page('/x/',body='<h1>Gallery</h1><img src="photo.jpg">'),
           page('/X',body='<h1>Decoration</h1><img alt="" src="photo.jpg">')]
    fixes=repairs(pages)
    [material]=[f for f in fixes if f['rule']=='image_alt_text']
    [uncertain]=[f for f in fixes if f['rule']=='image_alt_review']
    assert material['affected_pages']==[ORIGIN+'/x']
    assert material['page_count']==1
    assert uncertain['affected_pages']==[ORIGIN+'/x/']
    assert uncertain['non_scoring'] is True


def test_generic_template_has_signed_observation_shape_without_duplicate_location_repair():
    p=page('/locations/texas',body='<h1>{{city}}</h1><p>Visit #location# today.</p>')
    for source in [build_findings([p]),repairs([p])]:
        matches=[f for f in source if f['rule'] in {'visible_template_content','broken_location_template_content'}]
        assert len(matches)==1
        fix=matches[0]
        assert fix['rule']=='visible_template_content'
        assert fix['repair_observation_count']>=2
        assert any('h1:' in o['excerpt'] for o in fix['repair_observation_samples'])


def test_material_image_remains_actionable_on_utility_noindex():
    p=page(head='<meta name="robots" content="noindex">',body='<h1>Account</h1><button><img src="save.svg"></button>')
    assert any(f['rule']=='image_alt_text' for f in repairs([p]))

@pytest.mark.parametrize('route,target', [('/store?view=print','/store'),('/x/','/x'),('/X','/x'),('/a%2Fb','/a/b')])
def test_canonical_target_equivalence_does_not_erase_published_identity(route,target):
    p=page(route,head=f'<link rel="canonical" href="{ORIGIN}{target}">')
    assert p['canonical_status']=='canonical_to_different_url'

def test_one_page_keeps_material_and_uncertain_image_observations_separate():
    p=page(body='<h1>Exhibit</h1><figure><img src="subject.jpg"><figcaption>The exhibit</figcaption></figure><img src="other.jpg"><img src="third.jpg">')
    rows=repairs([p])
    [uncertain]=[r for r in rows if r['rule']=='image_alt_review']
    assert '2 images' in uncertain['current_value']
    assert uncertain['non_scoring'] is True
    assert all(o['decorative_state']=='uncertain' for o in uncertain['repair_observation_samples'])


def test_actual_content_evidence_is_sealed_and_survives_customer_and_chat_readers():
    import json
    import subprocess
    from pathlib import Path
    pages=[page('/x',body='<h1>{{city}}</h1><figure><img src="photo.jpg"><figcaption>The exhibit</figcaption></figure><img src="other.jpg">')]
    result=scan(pages)
    completed=subprocess.run(['node','tests/helpers/assertContentEvidenceOutput.mjs'],
        input=json.dumps({'scan':result,'review':build_local_review(result)}),text=True,capture_output=True,
        cwd=Path(__file__).resolve().parents[2],timeout=30)
    assert completed.returncode==0,completed.stderr
