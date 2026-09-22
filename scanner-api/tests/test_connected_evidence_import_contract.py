import pytest

from app.connected_evidence_import_contract import (
    BING_AI_PERFORMANCE_PROFILE,
    GA4_AI_REFERRAL_PROFILE,
    normalize_bing_ai_performance_import_csv,
    normalize_bing_ai_performance_import_rows,
    normalize_ga4_ai_referral_import_csv,
    normalize_ga4_ai_referral_import_rows,
    parse_connected_evidence_import_csv,
    validate_connected_evidence_import_rows,
)


def test_bing_accepts_unambiguous_aliases_and_preserves_row():
    row = {"Cited Page": "https://example.com/a", "Citation Count": "2", "Extra": "ok"}
    result = validate_connected_evidence_import_rows([row], profile=BING_AI_PERFORMANCE_PROFILE)
    assert result == [row]
    assert result[0] is row


def test_bing_rejects_duplicate_normalized_registered_header():
    row = {"Citation Count": "1", "citation-count": "2"}
    with pytest.raises(ValueError, match="duplicate normalized headers"):
        validate_connected_evidence_import_rows([row], profile=BING_AI_PERFORMANCE_PROFILE)


def test_bing_rejects_compact_registered_header_collision():
    row = {"citation_count": "1", "citationcount": "2"}
    with pytest.raises(ValueError, match="ambiguous compact headers"):
        validate_connected_evidence_import_rows([row], profile=BING_AI_PERFORMANCE_PROFILE)


def test_bing_rejects_conflicting_semantic_alias_values():
    row = {"Citation Count": "1", "total_citations": "2"}
    with pytest.raises(ValueError, match="conflicting aliases for citations"):
        validate_connected_evidence_import_rows([row], profile=BING_AI_PERFORMANCE_PROFILE)


def test_bing_allows_equivalent_semantic_alias_values():
    row = {"Citation Count": "2", "total_citations": 2}
    assert validate_connected_evidence_import_rows([row], profile=BING_AI_PERFORMANCE_PROFILE) == [row]


def test_ga4_accepts_unambiguous_source_aliases():
    row = {"session_source": "chatgpt.com", "session_medium": "referral", "sessions": 3}
    assert validate_connected_evidence_import_rows([row], profile=GA4_AI_REFERRAL_PROFILE) == [row]


def test_ga4_rejects_conflicting_source_aliases():
    row = {"session_source": "chatgpt.com", "source": "perplexity.ai"}
    with pytest.raises(ValueError, match="conflicting aliases for source"):
        validate_connected_evidence_import_rows([row], profile=GA4_AI_REFERRAL_PROFILE)


def test_ga4_rejects_conflicting_assistant_aliases():
    row = {"ai_assistant": "chatgpt", "assistant": "perplexity"}
    with pytest.raises(ValueError, match="conflicting aliases for assistant"):
        validate_connected_evidence_import_rows([row], profile=GA4_AI_REFERRAL_PROFILE)


def test_unknown_extra_columns_remain_ignored_by_ambiguity_guard():
    row = {"session_source": "chatgpt.com", "custom_field": "x", "customfield": "y"}
    assert validate_connected_evidence_import_rows([row], profile=GA4_AI_REFERRAL_PROFILE) == [row]


def test_import_guard_cannot_raise_global_row_bound():
    with pytest.raises(ValueError, match="max_rows must be within"):
        validate_connected_evidence_import_rows(
            [],
            profile=BING_AI_PERFORMANCE_PROFILE,
            max_rows=50_001,
        )


def test_bing_strict_row_wrapper_preflights_then_delegates():
    row = {"Cited Page": "https://example.com/a", "Citation Count": "2"}
    result = normalize_bing_ai_performance_import_rows(
        [row],
        site_url="https://example.com",
        retrieved_at="2026-09-23T00:00:00Z",
        stale_after_days=None,
    )
    assert result["provider"] == "microsoft_bing_webmaster_tools"
    assert result["state"] == "verified"
    assert result["records"][0]["url"] == "https://example.com/a"


def test_bing_strict_csv_wrapper_preflights_then_delegates():
    result = normalize_bing_ai_performance_import_csv(
        "Cited Page,Citation Count\nhttps://example.com/a,2\n",
        site_url="https://example.com",
        retrieved_at="2026-09-23T00:00:00Z",
        stale_after_days=None,
    )
    assert result["provider"] == "microsoft_bing_webmaster_tools"
    assert result["state"] == "verified"
    assert result["records"][0]["citations"] == 2


def test_ga4_strict_row_wrapper_blocks_conflict_before_delegate():
    row = {"session_source": "chatgpt.com", "source": "perplexity.ai"}
    with pytest.raises(ValueError, match="conflicting aliases for source"):
        normalize_ga4_ai_referral_import_rows([row], property_id="123")


def test_strict_csv_rejects_row_wider_than_header():
    with pytest.raises(ValueError, match="row 1 has more fields than header"):
        parse_connected_evidence_import_csv(
            "Cited Page,Citation Count\nhttps://example.com/a,2,unexpected\n"
        )


def test_strict_csv_rejects_row_shorter_than_header():
    with pytest.raises(ValueError, match="row 1 has fewer fields than header"):
        parse_connected_evidence_import_csv(
            "Cited Page,Citation Count\nhttps://example.com/a\n"
        )


def test_strict_csv_preserves_quoted_commas_and_explicit_empty_trailing_cells():
    rows = parse_connected_evidence_import_csv(
        'Cited Page,Topic,Citation Count\nhttps://example.com/a,"travel, europe",\n'
    )
    assert rows == [
        {
            "Cited Page": "https://example.com/a",
            "Topic": "travel, europe",
            "Citation Count": "",
        }
    ]


def test_strict_csv_limits_can_only_be_lowered():
    with pytest.raises(ValueError, match="max_bytes must be within"):
        parse_connected_evidence_import_csv("a\n1\n", max_bytes=5_000_001)
    with pytest.raises(ValueError, match="max_rows must be within"):
        parse_connected_evidence_import_csv("a\n1\n", max_rows=50_001)
    with pytest.raises(ValueError, match="exceeds max_rows"):
        parse_connected_evidence_import_csv("a\n1\n2\n", max_rows=1)


def test_ga4_strict_csv_wrapper_rejects_ragged_row_before_normalization():
    with pytest.raises(ValueError, match="row 1 has more fields than header"):
        normalize_ga4_ai_referral_import_csv(
            "session_source,sessions\nchatgpt.com,1,unexpected\n",
            property_id="123",
            retrieved_at="2026-09-23T00:00:00Z",
            stale_after_days=None,
        )
