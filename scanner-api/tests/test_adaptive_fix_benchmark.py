import copy
import hashlib
import json

import pytest

from app.adaptive_fix_benchmark import (
    ADAPTIVE_FIX_BENCHMARK_VERSION,
    build_manifest_bound_fix_benchmark,
    validate_manifest_bound_fix_benchmark,
)


def _pf(urls):
    return hashlib.sha256(
        json.dumps(list(urls), ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _make_manifest(count=1200, *, duplicate_tail=False):
    unique = tuple(f"https://x.test/p/{i}" for i in range(count))
    raw = unique + ((unique[3],) if duplicate_tail and unique else ())
    if count < 150:
        targets = (count,) if count else ()
    elif count < 500:
        targets = (150, count) if count != 150 else (150,)
    elif count < 1000:
        targets = (150, 500, count) if count != 500 else (150, 500)
    else:
        targets = (150, 500, 1000)

    standard = unique[: min(150, count)]
    selected_by_target = {}
    if count:
        selected_by_target[targets[0]] = standard
    if 500 in targets:
        if count >= 1200:
            smart = standard + unique[850:1200]
        else:
            smart = standard + unique[150:500]
        selected_by_target[500] = smart
    if count >= 1000:
        smart = selected_by_target[500]
        remaining = tuple(url for url in unique if url not in set(smart))
        selected_by_target[1000] = smart + remaining[: 1000 - len(smart)]
    elif count > 500:
        smart = selected_by_target[500]
        remaining = tuple(url for url in unique if url not in set(smart))
        selected_by_target[count] = smart + remaining[: count - len(smart)]
    elif count > 150 and count < 500:
        selected_by_target[count] = unique

    tranches = []
    previous = ()
    previous_target = None
    for target in targets:
        selected = selected_by_target[target]
        if previous_target is None:
            added = selected
            checked = False
            valid = None
        elif previous_target >= 150:
            added = selected[len(previous) :]
            checked = True
            valid = True
        else:
            added = tuple(url for url in selected if url not in set(previous))
            checked = False
            valid = None
        tranches.append(
            {
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
            }
        )
        previous = selected
        previous_target = target

    standard_target = min(150, count) if count else None
    manifest = {
        "version": "adaptive_tranche_selection_manifest_v1",
        "planner_version": "adaptive_crawl_v1_shadow",
        "discovered_input_count": len(raw),
        "unique_discovered_count": len(unique),
        "input_population_fingerprint": _pf(raw),
        "requested_ceiling": 1000,
        "assessment_ceiling": min(1000, count),
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
    return raw, manifest, integrity


def _fixes(urls):
    fixes = {}
    high = {}
    for i, url in enumerate(dict.fromkeys(urls)):
        values = set()
        if i % 40 == 0:
            values.add(f"route-fix-{i // 40}")
        if i in (100, 900, 1100):
            values.add(f"special-{i}")
        if values:
            fixes[url] = values
        if i in (100, 900, 1100):
            high[url] = {f"special-{i}"}
    return fixes, high


def test_fix_benchmark_compares_exact_smart_500_and_blind_1000_populations():
    raw, manifest, integrity = _make_manifest()
    fixes, high = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert result["version"] == ADAPTIVE_FIX_BENCHMARK_VERSION
    assert result["standard_reference_pages"] == 150
    assert result["smart_pages_assessed"] == 500
    assert result["blind_pages_assessed"] == 1000
    assert result["pages_saved_by_smart"] == 500
    assert result["smart_manifest_target"] == 500
    assert result["standard_150_preserved"] is True
    assert result["production_budget_authorized"] is False
    assert result["population_scope_complete"] is False
    assert result["site_fully_understood"] is False


def test_smart_fix_coverage_exposes_blind_only_and_smart_only_evidence():
    raw, manifest, integrity = _make_manifest()
    fixes = {
        raw[0]: {"shared"},
        raw[700]: {"blind-only"},
        raw[1100]: {"smart-only"},
    }
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url=fixes
    )
    assert result["shared_fix_fingerprints"] == 1
    assert result["blind_only_fix_fingerprints"] == 1
    assert result["smart_only_fix_fingerprints"] == 1
    assert result["smart_fix_fingerprints"] == 2
    assert result["blind_fix_fingerprints"] == 2
    assert result["smart_fix_coverage_vs_blind"] == 0.5


def test_incremental_smart_fix_yield_is_measured_from_unchanged_standard_prefix():
    raw, manifest, integrity = _make_manifest()
    fixes = {raw[0]: {"base"}, raw[900]: {"new-a"}, raw[1100]: {"new-b"}}
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url=fixes
    )
    assert result["standard_fix_fingerprints"] == 1
    assert result["smart_incremental_pages_vs_standard"] == 350
    assert result["smart_incremental_fix_fingerprints_vs_standard"] == 2
    assert result["smart_incremental_fix_yield_per_100"] == pytest.approx(0.5714)


def test_unknown_high_impact_fix_evidence_stays_unknown_not_zero():
    raw, manifest, integrity = _make_manifest()
    fixes, _ = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url=fixes
    )
    assert result["high_impact_evidence_state"] == "not_observed"
    assert result["smart_high_impact_fix_fingerprints"] is None
    assert result["blind_high_impact_fix_fingerprints"] is None
    assert result["smart_high_impact_coverage_vs_blind"] is None


def test_high_impact_fix_must_belong_to_same_fix_population():
    raw, manifest, integrity = _make_manifest(500)
    with pytest.raises(ValueError, match="high_impact_fix_not_in_fix_population"):
        build_manifest_bound_fix_benchmark(
            manifest,
            integrity,
            raw,
            fix_fingerprints_by_url={raw[0]: {"fix-a"}},
            high_impact_fix_fingerprints_by_url={raw[0]: {"fix-b"}},
        )


def test_inventory_limited_620_uses_exact_500_smart_and_620_blind_reference():
    raw, manifest, integrity = _make_manifest(620)
    fixes, high = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert result["smart_pages_assessed"] == 500
    assert result["blind_pages_assessed"] == 620
    assert result["pages_saved_by_smart"] == 120


def test_sub_500_inventory_binds_terminal_population_without_inventing_pages():
    raw, manifest, integrity = _make_manifest(320)
    fixes, _ = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url=fixes
    )
    assert result["smart_manifest_target"] == 320
    assert result["smart_pages_assessed"] == 320
    assert result["blind_pages_assessed"] == 320
    assert result["pages_saved_by_smart"] == 0


def test_sub_150_inventory_preserves_exact_terminal_standard_reference():
    raw, manifest, integrity = _make_manifest(80)
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url={}
    )
    assert result["standard_reference_target"] == 80
    assert result["smart_manifest_target"] == 80
    assert result["standard_reference_pages"] == 80
    assert result["standard_150_preserved"] is True


def test_discovery_duplicates_are_removed_only_for_blind_reference_population():
    raw, manifest, integrity = _make_manifest(620, duplicate_tail=True)
    result = build_manifest_bound_fix_benchmark(
        manifest, integrity, raw, fix_fingerprints_by_url={}
    )
    assert result["candidate_urls_supplied"] == 621
    assert result["candidate_urls_unique"] == 620
    assert result["duplicate_candidate_identities_removed"] == 1
    assert result["blind_pages_assessed"] == 620


def test_replay_integrity_must_match_exact_manifest_identity():
    raw, manifest, integrity = _make_manifest(500)
    bad = dict(integrity)
    bad["input_population_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="manifest_integrity_input_population_fingerprint_mismatch"):
        build_manifest_bound_fix_benchmark(
            manifest, bad, raw, fix_fingerprints_by_url={}
        )


def test_transplanted_same_count_discovery_sequence_fails_closed():
    raw, manifest, integrity = _make_manifest(500)
    transplanted = list(raw)
    transplanted[10], transplanted[11] = transplanted[11], transplanted[10]
    with pytest.raises(ValueError, match="manifest_input_population_mismatch"):
        build_manifest_bound_fix_benchmark(
            manifest, integrity, transplanted, fix_fingerprints_by_url={}
        )


def test_smart_population_cannot_reference_url_outside_discovery():
    raw, manifest, integrity = _make_manifest(500)
    bad = copy.deepcopy(manifest)
    row = bad["tranches"][1]
    selected = list(row["selected_urls"])
    selected[-1] = "https://foreign.test/not-discovered"
    row["selected_urls"] = tuple(selected)
    row["selected_population_fingerprint"] = _pf(selected)
    with pytest.raises(ValueError, match="smart_population_outside_discovery"):
        build_manifest_bound_fix_benchmark(
            bad, integrity, raw, fix_fingerprints_by_url={}
        )


def test_validator_rejects_metric_and_authority_tampering():
    raw, manifest, integrity = _make_manifest(620)
    fixes, high = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    tampered = copy.deepcopy(result)
    tampered["blind_only_fix_fingerprints"] += 1
    tampered["production_budget_authorized"] = True
    checked = validate_manifest_bound_fix_benchmark(
        tampered,
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert checked["valid"] is False
    assert "blind_only_fix_fingerprints_mismatch" in checked["errors"]
    assert "production_budget_authorized_mismatch" in checked["errors"]
    assert "forbidden_authority_claim" in checked["errors"]


def test_json_round_trip_validates_exactly():
    raw, manifest, integrity = _make_manifest(620)
    fixes, high = _fixes(raw)
    result = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    transported = json.loads(json.dumps(result))
    checked = validate_manifest_bound_fix_benchmark(
        transported,
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert checked["valid"] is True


def test_build_is_deterministic_and_does_not_mutate_inputs():
    raw, manifest, integrity = _make_manifest(620)
    fixes, high = _fixes(raw)
    before_manifest = copy.deepcopy(manifest)
    before_integrity = copy.deepcopy(integrity)
    before_fixes = copy.deepcopy(fixes)
    before_high = copy.deepcopy(high)
    first = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    second = build_manifest_bound_fix_benchmark(
        manifest,
        integrity,
        raw,
        fix_fingerprints_by_url=fixes,
        high_impact_fix_fingerprints_by_url=high,
    )
    assert first == second
    assert manifest == before_manifest
    assert integrity == before_integrity
    assert fixes == before_fixes
    assert high == before_high
