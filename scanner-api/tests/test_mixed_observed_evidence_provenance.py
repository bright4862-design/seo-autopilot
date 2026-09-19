from app.coverage_probes import SOFT_404_PROBE_VERSION
from app.repair_contract_v2 import _merge_repair_group


def _member(url: str, *, version: str = "") -> dict:
    item = {
        "fix_id": f"fix-{url.rsplit('/', 1)[-1]}",
        "repair_fingerprint": "shared-soft404-action",
        "rule": "soft_404",
        "category": "indexability",
        "page_template_family": "activity_detail",
        "affected_pages": [url],
        "page_count": 1,
        # Exercise the persistence-group merge without re-deriving denominator
        # metadata; this regression is specifically about provenance authority.
        "affected_pages_complete": False,
        "priority": "high",
        "base_severity": "high",
        "action_priority": "important",
        "evidence_class": "confirmed_problem",
        "requires_developer": False,
        "requires_approval": False,
        "can_auto_fix": False,
    }
    if version:
        item["observed_evidence_version"] = version
        item["verified_observed_pages"] = [url]
    return item


def test_mixed_versioned_and_unversioned_members_drop_group_authority():
    active_url = "https://example.com/catalog/active-match"
    passive_url = "https://example.com/catalog/passive-heuristic"

    merged = _merge_repair_group([
        _member(active_url, version=SOFT_404_PROBE_VERSION),
        _member(passive_url),
    ], [])

    assert set(merged["affected_pages"]) == {active_url, passive_url}
    assert "observed_evidence_version" not in merged
    assert "verified_observed_pages" not in merged


def test_uniform_versioned_members_preserve_exact_verified_union():
    urls = [
        "https://example.com/catalog/active-a",
        "https://example.com/catalog/active-b",
    ]

    merged = _merge_repair_group([
        _member(urls[0], version=SOFT_404_PROBE_VERSION),
        _member(urls[1], version=SOFT_404_PROBE_VERSION),
    ], [])

    assert merged["observed_evidence_version"] == SOFT_404_PROBE_VERSION
    assert set(merged["verified_observed_pages"]) == set(urls)
