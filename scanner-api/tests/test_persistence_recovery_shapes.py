"""Deterministic regressions for production repair-persistence failure shapes.

Tiqets is the exact 2026-08-24 persistence blocker reproduced in isolation:
22-page and 17-page repairs were all unknown-family evidence, normalized to
mixed scope, then rejected by the old `mixed_scope_without_partitions` rule.

Airbnb's 2026-08-24 persisted ScanRun also failed the repair-coverage authority
predicate, but its exact rejected repair was not logged before diagnostics were
added and a fresh 2026-08-25 crawl no longer reproduces that rejection. The
Airbnb regression below therefore preserves the separately documented historic
126-of-1 denominator shape and must remain fail-closed; it is deliberately not
presented as the missing exact repair from that persisted run.
"""

import pytest

from app.repair_coverage import first_failed_repair_invariant, normalize_repair_scope


@pytest.mark.parametrize("page_count", [22, 17])
def test_tiqets_exact_unknown_only_shapes_are_valid_mixed_repairs(page_count):
    affected = [f"https://example.com/unknown/{index}" for index in range(page_count)]
    repair = normalize_repair_scope(
        {
            "fix_id": f"tiqets-{page_count}",
            "rule": "missing_h1",
            "affected_pages": affected,
            "affected_reported": page_count,
            "affected_observed": page_count,
            "affected_eligible": page_count,
            "checked_eligible": None,
            "indexable_affected": 0,
            "indexable_checked_eligible": None,
        },
        [],
    )

    assert repair["page_scope"] == "mixed"
    assert repair["page_count"] == page_count
    assert repair["family_breakdown"] == {"unknown": page_count}
    assert first_failed_repair_invariant(repair) == ""


def test_airbnb_historical_126_of_1_shape_remains_fail_closed():
    affected = [f"https://example.com/listing/{index}" for index in range(126)]
    repair = {
        "fix_id": "airbnb-historical-126-of-1",
        "rule": "potential_orphan_pages",
        "page_scope": "family",
        "page_template_family": "homepage",
        "affected_pages": affected,
        "page_count": 126,
        "family_breakdown": {"homepage": 126},
        "representative_pages_by_family": {"homepage": affected[0]},
        "affected_pages_complete": True,
        "affected_reported": 126,
        "affected_observed": 126,
        "affected_eligible": 126,
        "checked_eligible": 1,
        "indexable_affected": 126,
        "indexable_checked_eligible": 1,
    }

    assert first_failed_repair_invariant(repair) == "affected_eligible_exceeds_checked_eligible"
