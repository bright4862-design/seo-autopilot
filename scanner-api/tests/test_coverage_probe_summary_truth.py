import time

from app.coverage_probes import MAX_PROBE_OBSERVATION_SAMPLES, SharedCoverageProbeScheduler


def test_skipped_observations_report_bounded_truncation_truthfully():
    scheduler = SharedCoverageProbeScheduler(
        max_probe_requests=1,
        shared_request_limit=500,
        initial_request_count=0,
        deadline=time.monotonic() + 30,
    )

    total = MAX_PROBE_OBSERVATION_SAMPLES + 7
    for index in range(total):
        scheduler.record_skipped(
            "soft_404_baseline",
            f"https://example.com/__fixlist-missing-{index:014x}",
            reason="robots_disallowed",
            metadata={"synthetic": True, "ordinal": index},
        )

    summary = scheduler.summary()
    assert summary["purposes"]["soft_404_baseline"]["skipped"] == total
    assert len(summary["observations"]) == MAX_PROBE_OBSERVATION_SAMPLES
    assert summary["observation_samples_truncated"] is True


def test_exactly_bounded_observation_sample_is_not_marked_truncated():
    scheduler = SharedCoverageProbeScheduler(
        max_probe_requests=1,
        shared_request_limit=500,
        initial_request_count=0,
        deadline=time.monotonic() + 30,
    )

    for index in range(MAX_PROBE_OBSERVATION_SAMPLES):
        scheduler.record_skipped(
            "soft_404_baseline",
            f"https://example.com/__fixlist-missing-{index:014x}",
            reason="robots_disallowed",
        )

    summary = scheduler.summary()
    assert len(summary["observations"]) == MAX_PROBE_OBSERVATION_SAMPLES
    assert summary["observation_samples_truncated"] is False
