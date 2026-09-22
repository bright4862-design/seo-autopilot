import copy
import hashlib
import json

import pytest

from app.adaptive_fix_yield import (
    ADAPTIVE_FIX_YIELD_VERSION,
    build_manifest_bound_fix_yield,
    validate_manifest_bound_fix_yield,
)


def _pf(urls):
    payload = json.dumps(list(urls), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _manifest(count=1000):
    urls = tuple(f"https://x.test/p/{i}" for i in range(count))
    targets = tuple(t for t in (150, 500, 1000) if t <= count)
    if count and (not targets or targets[-1] != count) and count < 1000:
        targets = tuple(sorted(set(targets + (count,))))
    tranches = []
    previous = ()
    previous_target = None
    for target in targets:
        selected = urls[:target]
        if previous_target is None:
            added = selected
            checked = False
            valid = None
        elif previous_target >= 150:
            added = selected[len(previous):]
            checked = True
            valid = True
        else:
            prev = set(previous)
            added = tuple(url for url in selected if url not in prev)
            checked = False
            valid = None
        tranches.append({
            "target": target,
            "role": "standard_reference" if target <= 150 else "adaptive_intermediate",
            "selected_count": len(selected),
            "selected_urls": selected,
            "selected_population_fingerprint": _pf(selected),
            "previous_target": previous_target,
            "prefix_nesting_checked": checked,
            "prefix_nesting_valid": valid,
            "added_count": len(added),
            "added_urls": added,
            "added_population_fingerprint": _pf(added),
            "inventory_limited": len(selected) < target,
        })
        previous = selected
        previous_target = target
    standard_target = min(150, count) if targets else None
    standard = urls[:standard_target] if standard_target is not None else ()
    manifest = {
        "version": "adaptive_tranche_selection_manifest_v1",
        "planner_version": "adaptive_crawl_v1_shadow",
        "discovered_input_count": count,
        "unique_discovered_count": count,
        "input_population_fingerprint": _pf(urls),
        "requested_ceiling": 1000,
        "assessment_ceiling": 1000,
        "planner_targets": targets,
        "selection_targets": targets,
        "ignored_pre_standard_targets": (),
        "standard_reference_target": standard_target,
        "standard_reference_population_fingerprint": _pf(standard),
        "tranches": tuple(tranches),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    integrity = {
        "version": "adaptive_tranche_selection_manifest_integrity_v1",
        "valid": True,
        "errors": (),
        "input_population_fingerprint": manifest["input_population_fingerprint"],
        "selection_targets": manifest["selection_targets"],
        "standard_reference_population_fingerprint": manifest[
            "standard_reference_population_fingerprint"
        ],
    }
    return urls, manifest, integrity


def _fixes(urls):
    fixes = {}
    high = {}
    for i, url in enumerate(urls):
        if i % 50 == 0:
            fixes[url] = {f"fix-{i // 50}"}
        if i % 200 == 0:
            high[url] = {f"fix-{i // 50}"}
    return fixes, high


def test_fix_yield_tracks_150_500_1000_marginal_counts():
    urls, manifest, integrity = _manifest()
    fixes, high = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert result["version"] == ADAPTIVE_FIX_YIELD_VERSION
    assert result["standard_150_preserved"] is True
    assert [row["target"] for row in result["tranches"]] == [150, 500, 1000]
    assert [row["pages_added"] for row in result["tranches"]] == [150, 350, 500]
    assert [row["new_fix_fingerprints"] for row in result["tranches"]] == [3, 7, 10]
    assert [row["new_high_impact_fix_fingerprints"] for row in result["tranches"]] == [1, 2, 2]
    assert result["production_budget_authorized"] is False
    assert result["population_scope_complete"] is False
    assert result["site_fully_understood"] is False


def test_unknown_high_impact_evidence_stays_unknown_not_zero():
    urls, manifest, integrity = _manifest()
    fixes, _ = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity, fix_fingerprints_by_url=fixes
    )
    assert result["high_impact_evidence_state"] == "not_observed"
    for row in result["tranches"]:
        assert row["new_high_impact_fix_fingerprints"] is None
        assert row["new_high_impact_fix_yield_per_100"] is None
        assert row["cumulative_high_impact_fix_fingerprints"] is None


def test_inventory_limited_terminal_tranche_is_measured_exactly():
    urls, manifest, integrity = _manifest(620)
    fixes, high = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert result["selection_targets"] == (150, 500, 620)
    assert result["tranches"][-1]["pages_assessed"] == 620
    assert result["tranches"][-1]["pages_added"] == 120


def test_sub_150_inventory_preserves_exact_terminal_reference():
    urls, manifest, integrity = _manifest(80)
    fixes, high = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert result["standard_reference_target"] == 80
    assert result["standard_150_preserved"] is True
    assert len(result["tranches"]) == 1
    assert result["tranches"][0]["pages_assessed"] == 80


def test_fix_fingerprints_are_deduplicated_across_pages_and_tranches():
    urls, manifest, integrity = _manifest(500)
    fixes = {url: {"same-fix"} for url in urls}
    result = build_manifest_bound_fix_yield(
        manifest, integrity, fix_fingerprints_by_url=fixes
    )
    assert result["tranches"][0]["new_fix_fingerprints"] == 1
    assert result["tranches"][1]["new_fix_fingerprints"] == 0
    assert result["tranches"][1]["cumulative_fix_fingerprints"] == 1


def test_high_impact_fix_must_belong_to_observed_fix_population():
    urls, manifest, integrity = _manifest(150)
    with pytest.raises(ValueError, match="high_impact_fix_not_in_fix_population"):
        build_manifest_bound_fix_yield(
            manifest, integrity,
            fix_fingerprints_by_url={urls[0]: {"fix-a"}},
            high_impact_fix_fingerprints_by_url={urls[0]: {"fix-b"}},
        )


def test_manifest_must_be_replay_validated():
    urls, manifest, integrity = _manifest(500)
    fixes, _ = _fixes(urls)
    bad = dict(integrity)
    bad["valid"] = False
    with pytest.raises(ValueError, match="manifest_not_replay_validated"):
        build_manifest_bound_fix_yield(
            manifest, bad, fix_fingerprints_by_url=fixes
        )


def test_manifest_integrity_must_match_exact_population_identity():
    urls, manifest, integrity = _manifest(500)
    fixes, _ = _fixes(urls)
    bad = dict(integrity)
    bad["input_population_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="manifest_integrity_input_fingerprint_mismatch"):
        build_manifest_bound_fix_yield(
            manifest, bad, fix_fingerprints_by_url=fixes
        )


def test_tampered_selected_population_fingerprint_fails_closed():
    urls, manifest, integrity = _manifest(500)
    fixes, _ = _fixes(urls)
    bad = copy.deepcopy(manifest)
    bad["tranches"][1]["selected_population_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match="selected_population_fingerprint_mismatch"):
        build_manifest_bound_fix_yield(
            bad, integrity, fix_fingerprints_by_url=fixes
        )


def test_tampered_prefix_population_fails_closed():
    urls, manifest, integrity = _manifest(500)
    fixes, _ = _fixes(urls)
    bad = copy.deepcopy(manifest)
    row = bad["tranches"][1]
    selected = list(row["selected_urls"])
    selected[0], selected[200] = selected[200], selected[0]
    row["selected_urls"] = tuple(selected)
    row["selected_population_fingerprint"] = _pf(selected)
    with pytest.raises(ValueError, match="tranche_prefix_drift"):
        build_manifest_bound_fix_yield(
            bad, integrity, fix_fingerprints_by_url=fixes
        )


def test_validator_rejects_telemetry_tampering_and_authority_claims():
    urls, manifest, integrity = _manifest(500)
    fixes, high = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    tampered = copy.deepcopy(result)
    tampered["tranches"][1]["new_fix_fingerprints"] += 1
    tampered["production_budget_authorized"] = True
    checked = validate_manifest_bound_fix_yield(
        tampered, manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert checked["valid"] is False
    assert "tranches_mismatch" in checked["errors"]
    assert "production_budget_authorized_mismatch" in checked["errors"]
    assert "forbidden_authority_claim" in checked["errors"]


def test_json_round_trip_validates():
    urls, manifest, integrity = _manifest(620)
    fixes, high = _fixes(urls)
    result = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    transported = json.loads(json.dumps(result))
    checked = validate_manifest_bound_fix_yield(
        transported, manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert checked["valid"] is True


def test_build_is_deterministic_and_does_not_mutate_inputs():
    urls, manifest, integrity = _manifest(500)
    fixes, high = _fixes(urls)
    before_manifest = copy.deepcopy(manifest)
    before_integrity = copy.deepcopy(integrity)
    before_fixes = copy.deepcopy(fixes)
    before_high = copy.deepcopy(high)
    first = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    second = build_manifest_bound_fix_yield(
        manifest, integrity,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert first == second
    assert manifest == before_manifest
    assert integrity == before_integrity
    assert fixes == before_fixes
    assert high == before_high
