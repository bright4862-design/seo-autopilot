"""Prepared review indexes keep evidence identity and input isolation intact."""
import copy

import pytest

from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.repair_priority_calibration import annotate_calibrated_repair_priority, prepare_calibrated_priority_pages


IDENTITY = {'scan_origin': 'https://example.com', 'identity_version': PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}


def inputs():
    pages = [
        {'url': 'https://example.com/products/a', 'page_template_family': 'product_page', 'status_code': 200, 'indexable': True},
        {'url': 'https://example.com/products/b', 'page_template_family': 'product_page', 'status_code': 200, 'meta_robots': 'noindex'},
        {'url': 'https://example.com/products/c', 'page_template_family': 'product_page', 'status_code': 403, 'indexable': False},
    ]
    fix = {'rule': 'missing_title', 'category': 'meta_title', 'page_template_family': 'product_page', 'affected_pages': [row['url'] for row in pages], 'verification_state': 'verified', 'confidence_score': 90}
    return fix, pages


def test_prepared_priority_matches_single_repair_path_and_preserves_input():
    fix, pages = inputs()
    original = copy.deepcopy(pages)
    prepared = prepare_calibrated_priority_pages(pages, **IDENTITY)
    direct = annotate_calibrated_repair_priority(fix, pages, **IDENTITY)
    indexed = annotate_calibrated_repair_priority(fix, pages, prepared_pages=prepared, **IDENTITY)
    assert indexed == direct
    assert indexed['priority_context']['checked_eligible'] == 2
    assert indexed['priority_context']['indexable_affected'] == 1
    assert indexed['priority_context']['non_indexable_affected'] == 1
    assert pages == original


def test_prepared_identity_does_not_accept_whitespace_or_non_string_evidence():
    fix, pages = inputs()
    fix['affected_pages'] = [' https://example.com/products/a', 42, None, 'https://example.com/products/b ']
    prepared = prepare_calibrated_priority_pages(pages, **IDENTITY)
    result = annotate_calibrated_repair_priority(fix, pages, prepared_pages=prepared, **IDENTITY)
    assert result['priority_context']['affected_checked'] == 0
    assert result['priority_context']['affected_observed'] == 0


def test_indexes_are_not_reused_for_later_mutated_page_inputs():
    fix, pages = inputs()
    before = annotate_calibrated_repair_priority(fix, pages, **IDENTITY)
    pages[0]['indexable'] = False
    after = annotate_calibrated_repair_priority(fix, pages, **IDENTITY)
    assert before['priority_context']['indexable_affected'] == 1
    assert after['priority_context']['indexable_affected'] == 0


def test_prepared_context_cannot_cross_scan_identity():
    fix, pages = inputs()
    prepared = prepare_calibrated_priority_pages(pages, **IDENTITY)
    with pytest.raises(ValueError, match='identity context'):
        annotate_calibrated_repair_priority(fix, pages, prepared_pages=prepared,
            scan_origin='https://other.example', identity_version=IDENTITY['identity_version'])
