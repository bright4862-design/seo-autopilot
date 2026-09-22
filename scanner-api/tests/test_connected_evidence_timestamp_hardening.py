import pytest

from app.connected_evidence import unavailable_evidence


def test_timestamp_with_valid_date_prefix_and_invalid_suffix_is_rejected():
    with pytest.raises(ValueError, match="retrieved_at must be a parseable timestamp"):
        unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_connected",
            reason="property is not connected",
            retrieved_at="2026-09-20Tinvalid",
        )


def test_date_only_timestamp_remains_valid_and_normalizes_to_utc_midnight():
    evidence = unavailable_evidence(
        provider="google_search_console",
        source_kind="search_analytics",
        state="not_connected",
        reason="property is not connected",
        retrieved_at="2026-09-20",
    )
    assert evidence["retrieved_at"] == "2026-09-20T00:00:00Z"
