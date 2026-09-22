from copy import deepcopy

import pytest

from app.adaptive_crawl import select_adaptive_urls
from app.adaptive_tranche_manifest import (
    ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION,
    ADAPTIVE_TRANCHE_MANIFEST_VERSION,
    build_adaptive_tranche_selection_manifest,
    validate_adaptive_tranche_selection_manifest,
)


def make_urls(count=1100):
    return [f"https://example.test/section-{i % 11}/page-{i}" for i in range(count)]


def family_of(url):
    return "money" if "/section-0/" in url else url.split("/")[3]


def path_of(url):
    return "/" + "/".join(url.split("/")[3:])


def metadata(urls):
    return {
        url: {
            "high_value": i % 37 == 0,
            "template_novelty": (i % 5) / 4,
            "graph_novelty": (i % 3) / 2,
            "finding_affinity": (i % 7) / 6,
        }
        for i, url in enumerate(urls)
    }


def test_default_manifest_is_exact_150_500_1000_and_nested():
    urls=make_urls(1100)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls))
    assert manifest["version"] == ADAPTIVE_TRANCHE_MANIFEST_VERSION
    assert manifest["selection_targets"] == (150,500,1000)
    assert [t["selected_count"] for t in manifest["tranches"]] == [150,500,1000]
    assert manifest["tranches"][1]["selected_urls"][:150] == manifest["tranches"][0]["selected_urls"]
    assert manifest["tranches"][2]["selected_urls"][:500] == manifest["tranches"][1]["selected_urls"]


def test_standard_150_reference_matches_existing_selector_exactly():
    urls=make_urls(700)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    expected=tuple(select_adaptive_urls(urls,family_of,path_of,150,metadata_by_url=meta))
    assert manifest["tranches"][0]["selected_urls"] == expected
    assert manifest["standard_reference_target"] == 150


def test_added_populations_reconcile_exact_prefix_deltas():
    urls=make_urls(1100)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls))
    first,second,third=manifest["tranches"]
    assert first["added_count"] == 150
    assert second["added_count"] == 350
    assert third["added_count"] == 500
    assert second["added_urls"] == second["selected_urls"][150:]
    assert third["added_urls"] == third["selected_urls"][500:]
    assert second["prefix_nesting_valid"] is True
    assert third["prefix_nesting_valid"] is True


def test_inventory_bound_is_recorded_without_site_completeness_claim():
    urls=make_urls(620)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls))
    assert manifest["selection_targets"] == (150,500,620)
    assert manifest["tranches"][-1]["role"] == "inventory_bound"
    assert manifest["population_scope_complete"] is False
    assert manifest["site_fully_understood"] is False


def test_sub_150_inventory_uses_existing_sampler_bound():
    urls=make_urls(83)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    assert manifest["selection_targets"] == (83,)
    assert manifest["standard_reference_target"] == 83
    assert manifest["tranches"][0]["selected_urls"] == tuple(select_adaptive_urls(urls,family_of,path_of,83,metadata_by_url=meta))


def test_manifest_hard_caps_selection_at_1000():
    urls=make_urls(1400)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls),ceiling=5000)
    assert manifest["assessment_ceiling"] == 1000
    assert manifest["selection_targets"][-1] == 1000
    assert manifest["tranches"][-1]["selected_count"] == 1000


def test_custom_intermediate_targets_remain_prefix_stable_above_150():
    urls=make_urls(1100)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls),tranche_targets=(150,300,500,750,1000))
    assert manifest["selection_targets"] == (150,300,500,750,1000)
    for previous,current in zip(manifest["tranches"],manifest["tranches"][1:]):
        assert current["prefix_nesting_checked"] is True
        assert current["selected_urls"][:previous["selected_count"]] == previous["selected_urls"]


def test_pre_standard_custom_target_is_not_used_as_deeper_prefix_reference():
    urls=make_urls(500)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,tranche_targets=(100,500))
    assert 100 in manifest["ignored_pre_standard_targets"]
    assert manifest["selection_targets"][0] == 150


def test_duplicate_discovery_identities_are_fingerprinted_but_do_not_authorize_more_pages():
    urls=make_urls(520)
    urls.extend(urls[:20])
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=metadata(urls))
    assert manifest["discovered_input_count"] == 540
    assert manifest["unique_discovered_count"] == 520
    assert manifest["tranches"][-1]["selected_count"] <= 520
    assert manifest["production_budget_authorized"] is False


def test_manifest_is_deterministic_for_same_evidence():
    urls=make_urls(700)
    meta=metadata(urls)
    first=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    second=build_adaptive_tranche_selection_manifest(list(urls),family_of,path_of,metadata_by_url=deepcopy(meta))
    assert first == second


def test_integrity_accepts_exact_json_like_transport():
    urls=make_urls(700)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    transported=deepcopy(manifest)
    transported["selection_targets"]=list(transported["selection_targets"])
    transported["planner_targets"]=list(transported["planner_targets"])
    transported["tranches"]=[dict(item) for item in transported["tranches"]]
    for item in transported["tranches"]:
        item["selected_urls"]=list(item["selected_urls"])
        item["added_urls"]=list(item["added_urls"])
    result=validate_adaptive_tranche_selection_manifest(transported,urls,family_of,path_of,metadata_by_url=meta)
    assert result["version"] == ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION
    assert result["valid"] is True


def test_integrity_rejects_selected_population_tamper():
    urls=make_urls(700)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    forged=deepcopy(manifest)
    forged["tranches"]=list(forged["tranches"])
    forged["tranches"][1]=dict(forged["tranches"][1])
    forged["tranches"][1]["selected_population_fingerprint"]="0"*64
    result=validate_adaptive_tranche_selection_manifest(forged,urls,family_of,path_of,metadata_by_url=meta)
    assert result["valid"] is False
    assert "tranches_mismatch" in result["errors"]


def test_integrity_rejects_added_population_tamper():
    urls=make_urls(700)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    forged=deepcopy(manifest)
    forged["tranches"]=list(forged["tranches"])
    forged["tranches"][1]=dict(forged["tranches"][1])
    forged["tranches"][1]["added_count"] += 1
    result=validate_adaptive_tranche_selection_manifest(forged,urls,family_of,path_of,metadata_by_url=meta)
    assert result["valid"] is False
    assert "tranches_mismatch" in result["errors"]


def test_integrity_rejects_discovery_order_or_metadata_drift():
    urls=make_urls(700)
    meta=metadata(urls)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    reordered=list(urls)
    reordered[0],reordered[1]=reordered[1],reordered[0]
    result=validate_adaptive_tranche_selection_manifest(manifest,reordered,family_of,path_of,metadata_by_url=meta)
    assert result["valid"] is False
    assert "input_population_fingerprint_mismatch" in result["errors"] or "tranches_mismatch" in result["errors"]


def test_integrity_rejects_forbidden_authority_claim():
    urls=make_urls(300)
    manifest=build_adaptive_tranche_selection_manifest(urls,family_of,path_of)
    forged=dict(manifest)
    forged["production_budget_authorized"] = True
    result=validate_adaptive_tranche_selection_manifest(forged,urls,family_of,path_of)
    assert result["valid"] is False
    assert "forbidden_authority_claim" in result["errors"]


@pytest.mark.parametrize("bad", [[" https://example.test/x"], ["https://example.test/x "], [""], [123]])
def test_invalid_discovered_identity_fails_closed(bad):
    with pytest.raises(ValueError):
        build_adaptive_tranche_selection_manifest(bad,family_of,path_of)


def test_inputs_are_not_mutated():
    urls=make_urls(700)
    meta=metadata(urls)
    urls_before=list(urls)
    meta_before=deepcopy(meta)
    build_adaptive_tranche_selection_manifest(urls,family_of,path_of,metadata_by_url=meta)
    assert urls == urls_before
    assert meta == meta_before
