"""Repairs from bounded, accepted raw-HTML content observations."""
from __future__ import annotations

import hashlib
from .accepted_content_evidence import IMAGE_APPLICABILITY_VERSION, VISIBLE_TEMPLATE_VERSION
from .page_evidence_gate import page_has_usable_html
from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from .stage2_reachability_provenance import enrich_pages_from_retained_link_evidence
from .url_evidence import page_content_evidence_url


def _url(page):
    if not any(page.get(key) for key in ('url', 'final_url', 'path')):
        return ''
    return page_content_evidence_url(page, identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)


def _fix(page, rule, category, title, explanation, recommendation, observations, count, *, uncertain=False):
    url = _url(page)
    return {
        'fix_id':'finding_'+hashlib.sha256(f'{rule}|{url}'.encode()).hexdigest()[:12],
        'rule':rule, 'category':category, 'priority':'low' if uncertain else 'medium',
        'title':title, 'issue_title':title, 'plain_english_explanation':explanation,
        'why_it_matters':explanation, 'current_value':explanation,
        'recommendation':recommendation, 'recommended_value':recommendation,
        'page_url':url, 'affected_pages':[url], 'page_count':1,
        'source_pages':[url], 'page_template_family':page.get('page_template_family') or 'standard',
        'source':f'accepted_content:{rule}', 'difficulty':'easy' if uncertain else 'developer',
        'non_scoring':uncertain, 'verification_state':'needs_verification' if uncertain else 'confirmed',
        'evidence_status':'needs_verification' if uncertain else 'confirmed',
        **({'score_impact':0, 'evidence_class':'opportunity'} if uncertain else {}),
        'repair_observation_count':count, 'repair_observation_samples':observations[:20],
    }


def content_evidence_findings(pages):
    # ``run_scan`` invokes this only after the final assessed-page cap. Use that
    # stable page set to project the temporary raw-link cache into B11 sample-
    # scoped reachability evidence, then discard the private cache before result
    # persistence/customer projection. Review can call this function again later;
    # already-enriched pages have no private cache and are left unchanged.
    if any(isinstance(page, dict) and '_reachability_links' in page for page in pages):
        enrich_pages_from_retained_link_evidence(pages)

    output=[]
    for page in pages:
        if not page_has_usable_html(page) or not _url(page):
            continue
        url=_url(page)
        status=int(page.get('status_code') or 0)
        alt=page.get('image_alt_applicability') or {}
        if alt.get('version')==IMAGE_APPLICABILITY_VERSION and alt.get('accepted') is True:
            for applicability, rule, key in [('material','image_alt_text','material_missing_alt_count'),
                                              ('uncertain','image_alt_review','uncertain_missing_alt_count')]:
                count=alt.get(key) or 0
                if not count:
                    continue
                uncertain=applicability=='uncertain'
                observations=[{'page_url':url,'status':status,'issue_type':rule,'alt_state':'absent',
                               'decorative_state':applicability,
                               'excerpt':f"Image {o['ordinal']}, {o['placement']}: {o['reason']}"}
                              for o in alt.get('observations',[])
                              if o.get('alt_state')=='absent' and o.get('applicability')==applicability]
                output.append(_fix(page,rule,'image_alt_text',
                    'Review the purpose of images without alt attributes' if uncertain else 'Add descriptions to meaningful images',
                    f'{count} images have no alt attribute; their purpose needs review before a repair can be confirmed.' if uncertain
                    else f'{count} meaningful or functional images have no alt attribute. Accepted HTML contains caption, subject-image or unnamed-control evidence.',
                    'Check each image in its page context. Give informative or functional images appropriate text; decorative images can use an empty alt attribute.' if uncertain
                    else 'Describe the evidenced informative images or give image controls an accessible name. Preserve deliberately decorative empty alt attributes.',
                    observations,count,uncertain=uncertain))
        template=page.get('visible_template_evidence') or {}
        if template.get('version')==VISIBLE_TEMPLATE_VERSION and template.get('accepted') is True and template.get('state')=='fail':
            observations=[{'page_url':url,'status':status,'issue_type':o['kind'],
                           'excerpt':f"{o['placement']}: {o['snippet']}"} for o in template.get('samples',[])]
            count=template.get('issue_count') or len(observations)
            if 'wrong_location_copy' in (page.get('template_content_issue_types') or []):
                observations += [{'page_url':url,'status':status,'issue_type':'wrong_location_copy','excerpt':text[:500]}
                                 for text in (page.get('template_content_issue_evidence') or [])[:4]]
                count += len(observations)-len(template.get('samples',[]))
            output.append(_fix(page,'visible_template_content','web_dev','Fix unfinished visible page content',
                'Accepted HTML contains unresolved template output, placeholder copy or an unfinished page shell. Review the recorded placement and excerpts.',
                'Correct the source field or template responsible for the shown output. Verify the page content in its intended context after publication.',
                observations,count))
    groups={}
    for fix in output:
        groups.setdefault((fix['rule'],fix['page_template_family']),[]).append(fix)
    grouped=[]
    for (rule,family),members in groups.items():
        if len(members)==1:
            grouped.extend(members)
            continue
        urls=list(dict.fromkeys(url for member in members for url in member['affected_pages']))
        observations=[o for member in members for o in member['repair_observation_samples']]
        count=sum(member['repair_observation_count'] for member in members)
        item={**members[0], 'fix_id':'finding_'+hashlib.sha256(f'{rule}|{family}|{urls}'.encode()).hexdigest()[:12],
              'page_url':urls[0],'affected_pages':urls,'source_pages':urls[:30],'page_count':len(urls),
              'repair_observation_count':count,'repair_observation_samples':observations[:20]}
        if rule in {'image_alt_text','image_alt_review'}:
            purpose='whose purpose needs review' if rule=='image_alt_review' else 'with material applicability evidence'
            explanation=f'{count} images {purpose} have no alt attribute across {len(urls)} observed pages.'
            item.update(current_value=explanation,plain_english_explanation=explanation,why_it_matters=explanation)
        grouped.append(item)
    return grouped
