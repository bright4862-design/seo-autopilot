from datetime import date

from app.content_evidence_findings import content_evidence_findings
from app.stage2_freshness_producer import (
    FRESHNESS_PRODUCER_VERSION,
    build_contextual_freshness_page_evidence,
)


def _page(**extra):
    return {
        "url": "https://example.com/rates",
        "final_url": "https://example.com/rates",
        "path": "/rates",
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "fetch_error": "",
        "raw_html_truncated": False,
        "title": "Mortgage rates",
        "h1": "Mortgage rates",
        "meta_description": "Compare mortgage rates.",
        **extra,
    }


def test_b15_old_historical_year_alone_is_not_a_freshness_defect():
    evidence = build_contextual_freshness_page_evidence(
        _page(
            url="https://example.com/archive/2022",
            final_url="https://example.com/archive/2022",
            path="/archive/2022",
            title="Mortgage rates in 2022",
            h1="Mortgage rates in 2022",
        ),
        as_of=date(2026, 9, 20),
    )

    assert evidence["producer_version"] == FRESHNESS_PRODUCER_VERSION
    assert evidence["current_content_intent"] == ""
    assert evidence["assessment"]["state"] == "not_applicable"
    assert evidence["assessment"]["reason"] == "no_current_content_intent"
    assert all(row["scope"] == "historical" for row in evidence["temporal_evidence"])


def test_b15_explicit_current_intent_plus_old_visible_date_can_fail():
    evidence = build_contextual_freshness_page_evidence(
        _page(
            title="Current mortgage rates — January 2023",
            h1="Current mortgage rates",
        ),
        as_of=date(2026, 9, 20),
    )

    assert evidence["current_content_intent"] == "explicit_current_language"
    assert "title:current" in evidence["current_content_intent_evidence"]
    assert {
        "date": "2023-01-31",
        "scope": "current",
        "source": "title",
        "precision": "month",
    } in evidence["temporal_evidence"]
    assert evidence["assessment"]["state"] == "fail"
    assert evidence["assessment"]["reason"] == "current_intent_conflicts_with_old_temporal_evidence"


def test_b15_dated_path_does_not_become_current_scope_contradiction():
    evidence = build_contextual_freshness_page_evidence(
        _page(
            url="https://example.com/rates/2022",
            final_url="https://example.com/rates/2022",
            path="/rates/2022",
            title="Current mortgage rates",
            h1="Latest mortgage rates",
        ),
        as_of=date(2026, 9, 20),
    )

    assert evidence["current_content_intent"] == "explicit_current_language"
    assert evidence["assessment"]["state"] == "not_verified"
    assert evidence["assessment"]["reason"] == "no_current_scope_date"
    assert any(row["source"] == "path" and row["scope"] == "historical" for row in evidence["temporal_evidence"])


def test_b15_current_visible_date_can_pass():
    evidence = build_contextual_freshness_page_evidence(
        _page(
            title="Latest mortgage rates — September 2026",
            h1="Current mortgage rates",
        ),
        as_of=date(2026, 9, 20),
    )

    assert evidence["assessment"]["state"] == "pass"
    assert evidence["assessment"]["reason"] == "current_intent_temporal_evidence_consistent"
    assert evidence["assessment"]["latest_current_scope_date"] == "2026-09-30"


def test_b15_year_only_uses_latest_possible_day_to_avoid_false_staleness():
    evidence = build_contextual_freshness_page_evidence(
        _page(title="Current mortgage rates 2025", h1="Current mortgage rates"),
        as_of=date(2026, 9, 20),
    )

    row = next(row for row in evidence["temporal_evidence"] if row["source"] == "title")
    assert row["date"] == "2025-12-31"
    assert row["precision"] == "year"
    assert evidence["assessment"]["state"] == "pass"


def test_b15_unusable_page_cannot_produce_current_or_temporal_claims():
    evidence = build_contextual_freshness_page_evidence(
        _page(
            status_code=403,
            page_evidence_class="access_unverified",
            title="Current mortgage rates January 2022",
        ),
        as_of=date(2026, 9, 20),
    )

    assert evidence["current_content_intent"] == ""
    assert evidence["temporal_evidence"] == []
    assert evidence["assessment"]["state"] == "not_verified"
    assert evidence["assessment"]["reason"] == "accepted_html_unavailable"


def test_b15_real_content_evidence_seam_enriches_retained_pages_without_emitting_a_repair():
    page = _page(title="Current mortgage rates January 2023", h1="Current mortgage rates")

    findings = content_evidence_findings([page])

    # B15 is evidence-only at this stage: no customer repair/card is introduced.
    assert findings == []
    evidence = page["contextual_freshness_evidence"]
    assert evidence["producer_version"] == FRESHNESS_PRODUCER_VERSION
    assert evidence["assessment"]["state"] == "fail"
