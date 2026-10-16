from app.stage2_probe_budget import (
    STAGE2_PROBE_ALLOCATION_VERSION,
    allocate_stage2_probe_candidates,
    remaining_shared_probe_requests,
)


def summary(remaining):
    return {
        "request_budget": {
            "requests_remaining": remaining,
            "configured_probe_requests": 18,
        }
    }


def test_missing_scheduler_evidence_fails_closed_to_zero_capacity():
    assert remaining_shared_probe_requests(None) == 0
    allocation = allocate_stage2_probe_candidates(
        None,
        {
            "soft_404_baseline": 4,
            "sitemap_target": 4,
            "url_variant": 4,
        },
    )
    assert allocation["version"] == STAGE2_PROBE_ALLOCATION_VERSION
    assert allocation["allocated_total"] == 0
    assert allocation["allocated"] == {
        "soft_404_baseline": 0,
        "sitemap_target": 0,
        "url_variant": 0,
    }
    assert allocation["single_shared_budget"] is True


def test_round_robin_reserves_small_remaining_pool_across_all_three_purposes():
    allocation = allocate_stage2_probe_candidates(
        summary(4),
        {
            "soft_404_baseline": 10,
            "sitemap_target": 10,
            "url_variant": 10,
        },
    )
    assert allocation["allocated"] == {
        "soft_404_baseline": 2,
        "sitemap_target": 1,
        "url_variant": 1,
    }
    assert allocation["allocated_total"] == 4
    assert allocation["unallocated_shared_capacity"] == 0


def test_even_pool_is_shared_evenly_without_creating_more_requests():
    allocation = allocate_stage2_probe_candidates(
        summary(18),
        {
            "soft_404_baseline": 20,
            "sitemap_target": 20,
            "url_variant": 20,
        },
    )
    assert allocation["allocated"] == {
        "soft_404_baseline": 6,
        "sitemap_target": 6,
        "url_variant": 6,
    }
    assert allocation["allocated_total"] == 18
    assert allocation["allocated_total"] <= allocation["shared_requests_remaining_before_allocation"]


def test_allocation_never_exceeds_eligible_candidate_counts():
    allocation = allocate_stage2_probe_candidates(
        summary(12),
        {
            "soft_404_baseline": 1,
            "sitemap_target": 0,
            "url_variant": 3,
        },
    )
    assert allocation["allocated"] == {
        "soft_404_baseline": 1,
        "sitemap_target": 0,
        "url_variant": 3,
    }
    assert allocation["allocated_total"] == 4
    assert allocation["unallocated_shared_capacity"] == 8


def test_malformed_desired_counts_cannot_expand_shared_capacity():
    allocation = allocate_stage2_probe_candidates(
        summary(3),
        {
            "soft_404_baseline": "999999999999",
            "sitemap_target": -50,
            "url_variant": "not-a-number",
            "unapproved_second_scheduler": 999,
        },
    )
    assert allocation["allocated"] == {
        "soft_404_baseline": 3,
        "sitemap_target": 0,
        "url_variant": 0,
    }
    assert allocation["allocated_total"] == 3
