from copy import deepcopy

import pytest

from app.adaptive_crawl import select_adaptive_urls
from app.adaptive_selection_trace import (
    ADAPTIVE_SELECTION_TRACE_INTEGRITY_VERSION,
    ADAPTIVE_SELECTION_TRACE_VERSION,
    build_adaptive_selection_trace,
    validate_adaptive_selection_trace,
)


def make_urls(count=620):
    urls=[]
    for i in range(count):
        group=i % 9
        urls.append(f"https://example.test/section-{group}/page-{i}")
    return urls


def family_of(url):
    return "money" if "/section-0/" in url else url.split("/")[3]


def path_of(url):
    return "/" + "/".join(url.split("/")[3:])


def metadata(urls):
    return {
        url: {
            "high_value": i % 41 == 0,
            "template_novelty": (i % 5) / 4,
            "graph_novelty": (i % 3) / 2,
            "finding_affinity": (i % 7) / 6,
        }
        for i, url in enumerate(urls)
    }


def test_standard_150_is_exact_and_has_no_adaptive_steps():
    urls=make_urls(220)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,150,metadata_by_url=metadata(urls))
    assert trace["version"] == ADAPTIVE_SELECTION_TRACE_VERSION
    assert trace["selected_urls"] == tuple(select_adaptive_urls(urls,family_of,path_of,150,metadata_by_url=metadata(urls)))
    assert trace["baseline_selected_count"] == 150
    assert trace["adaptive_selected_count"] == 0
    assert trace["steps"] == ()
    assert trace["production_budget_authorized"] is False


def test_deeper_trace_replays_selector_exactly():
    urls=make_urls(620)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    expected=select_adaptive_urls(urls,family_of,path_of,500,metadata_by_url=meta)
    assert trace["selected_urls"] == tuple(expected)
    assert trace["selected_count"] == 500
    assert trace["baseline_selected_count"] == 150
    assert trace["adaptive_selected_count"] == 350
    assert len(trace["steps"]) == 350


def test_trace_is_deterministic_for_same_evidence():
    urls=make_urls(540)
    meta=metadata(urls)
    first=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    second=build_adaptive_selection_trace(list(urls),family_of,path_of,500,metadata_by_url=deepcopy(meta))
    assert first == second


def test_step_contains_score_reason_and_tie_diagnostics():
    urls=make_urls(170)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,165,metadata_by_url=metadata(urls))
    step=trace["steps"][0]
    assert step["selected_position"] == 150
    assert step["candidate_count_before"] == 20
    assert step["score"] >= 0
    assert isinstance(step["reasons"], tuple)
    assert step["tied_on_score_count"] >= 1
    assert step["score_gap_to_runner_up"] is None or step["score_gap_to_runner_up"] >= 0


def test_duplicate_discovery_identity_is_recorded_without_claiming_completeness():
    urls=make_urls(160)
    urls.insert(10, urls[3])
    trace=build_adaptive_selection_trace(urls,family_of,path_of,161,metadata_by_url=metadata(urls))
    assert trace["discovered_input_count"] == 161
    assert trace["unique_discovered_count"] == 160
    assert trace["population_scope_complete"] is False
    assert trace["site_fully_understood"] is False


def test_target_is_hard_capped_at_1000():
    urls=make_urls(1100)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,5000,metadata_by_url=metadata(urls))
    assert trace["bounded_target"] == 1000
    assert trace["selected_count"] == 1000


def test_integrity_accepts_exact_replay():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    result=validate_adaptive_selection_trace(trace,urls,family_of,path_of,500,metadata_by_url=meta)
    assert result["version"] == ADAPTIVE_SELECTION_TRACE_INTEGRITY_VERSION
    assert result["valid"] is True
    assert result["errors"] == ()


def test_integrity_rejects_selected_fingerprint_tamper():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    forged=dict(trace)
    forged["selected_population_fingerprint"]="0"*64
    result=validate_adaptive_selection_trace(forged,urls,family_of,path_of,500,metadata_by_url=meta)
    assert result["valid"] is False
    assert "selected_population_fingerprint_mismatch" in result["errors"]


def test_integrity_rejects_step_score_tamper_after_json_like_transport():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    transported=deepcopy(trace)
    transported["selected_urls"]=list(transported["selected_urls"])
    transported["steps"]=[dict(step) for step in transported["steps"]]
    transported["steps"][0]["reasons"]=list(transported["steps"][0]["reasons"])
    transported["steps"][0]["score"] += 1
    result=validate_adaptive_selection_trace(transported,urls,family_of,path_of,500,metadata_by_url=meta)
    assert result["valid"] is False
    assert "steps_mismatch" in result["errors"]


def test_integrity_accepts_json_like_sequence_transport_without_tamper():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    transported=deepcopy(trace)
    transported["selected_urls"]=list(transported["selected_urls"])
    transported["steps"]=[dict(step) for step in transported["steps"]]
    for step in transported["steps"]:
        step["reasons"]=list(step["reasons"])
    result=validate_adaptive_selection_trace(transported,urls,family_of,path_of,500,metadata_by_url=meta)
    assert result["valid"] is True


def test_integrity_rejects_metadata_drift():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    changed=deepcopy(meta)
    changed[urls[151]]["finding_affinity"]=1.0
    result=validate_adaptive_selection_trace(trace,urls,family_of,path_of,500,metadata_by_url=changed)
    assert result["valid"] is False
    assert "steps_mismatch" in result["errors"] or "selected_population_fingerprint_mismatch" in result["errors"]


def test_integrity_rejects_discovery_order_drift():
    urls=make_urls(520)
    meta=metadata(urls)
    trace=build_adaptive_selection_trace(urls,family_of,path_of,500,metadata_by_url=meta)
    changed=list(urls)
    changed[0], changed[1] = changed[1], changed[0]
    result=validate_adaptive_selection_trace(trace,changed,family_of,path_of,500,metadata_by_url=meta)
    assert result["valid"] is False
    assert "input_population_fingerprint_mismatch" in result["errors"]


@pytest.mark.parametrize("bad", [[" https://example.test/x"], ["https://example.test/x "], [""] , [123]])
def test_invalid_discovered_identity_fails_closed(bad):
    with pytest.raises(ValueError):
        build_adaptive_selection_trace(bad,family_of,path_of,1)


def test_inputs_are_not_mutated():
    urls=make_urls(180)
    meta=metadata(urls)
    urls_before=list(urls)
    meta_before=deepcopy(meta)
    build_adaptive_selection_trace(urls,family_of,path_of,175,metadata_by_url=meta)
    assert urls == urls_before
    assert meta == meta_before
