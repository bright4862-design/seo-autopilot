"""Coverage/accounting integrity for FixList NextGen connected evidence.

This fourth pure validation boundary composes after generic envelope, source
identity, and provider-record semantic validation. It proves that sample and
coverage metadata truthfully describe the records actually carried by the
envelope. It performs no network I/O, authentication, persistence, scoring,
projection, or production mutation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .connected_evidence_record_contract import (
    validate_connected_evidence_record_semantics,
)

COVERAGE_SEMANTICS_VERSION = "connected_evidence_coverage_semantics_v1"

_UNAVAILABLE_STATES = frozenset(
    {"not_connected", "not_supported", "not_verified", "provider_error"}
)


def _non_negative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _text(value: Any, *, field: str, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _temporal(value: Any, *, field: str) -> datetime:
    text = _text(value, field=field, max_length=128)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise ValueError(f"{field} must be an ISO-8601 date/timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_temporal(value: Any, *, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    return _temporal(value, field=field)


def _require_exact_count(
    mapping: Mapping[str, Any],
    key: str,
    expected: int,
    *,
    field_prefix: str,
) -> None:
    actual = _non_negative_integer(mapping.get(key), field=f"{field_prefix}.{key}")
    if actual != expected:
        raise ValueError(f"{field_prefix}.{key} did not match carried record count")


def _require_sample_kind(evidence: Mapping[str, Any], expected: str) -> None:
    actual = evidence["sample"].get("kind")
    if actual != expected:
        raise ValueError("sample.kind did not match the registered source profile")


def _validate_period_end_matches_observed(evidence: Mapping[str, Any]) -> datetime | None:
    observed = _optional_temporal(evidence.get("observed_at"), field="observed_at")
    period_end_value = evidence["coverage"].get("period_end")
    period_end = _optional_temporal(period_end_value, field="coverage.period_end")
    if observed is not None and period_end is not None and observed != period_end:
        raise ValueError("coverage.period_end did not match observed_at")
    return observed


def _validate_record_dates_not_after_observed(
    records: Sequence[Mapping[str, Any]],
    *,
    observed: datetime | None,
) -> None:
    for index, record in enumerate(records):
        value = record.get("date")
        if value in (None, ""):
            continue
        record_date = _temporal(value, field=f"records[{index}].date")
        if observed is not None and record_date > observed:
            raise ValueError(f"records[{index}].date cannot be later than observed_at")


def _validate_gsc(evidence: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    _require_sample_kind(evidence, "provider_aggregate_rows")
    _require_exact_count(evidence["sample"], "row_count", len(records), field_prefix="sample")
    _require_exact_count(evidence["coverage"], "row_count", len(records), field_prefix="coverage")

    dimensions = evidence["coverage"].get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("coverage.dimensions must be a non-empty list")
    normalized_dimensions: list[str] = []
    for index, dimension in enumerate(dimensions):
        normalized_dimensions.append(
            _text(dimension, field=f"coverage.dimensions[{index}]", max_length=128)
        )
    if len(set(normalized_dimensions)) != len(normalized_dimensions):
        raise ValueError("coverage.dimensions must be unique")

    expected_dimensions = set(normalized_dimensions)
    for index, record in enumerate(records):
        record_dimensions = record.get("dimensions")
        if not isinstance(record_dimensions, Mapping):
            raise ValueError(f"records[{index}].dimensions must be an object")
        if set(record_dimensions) != expected_dimensions:
            raise ValueError(
                f"records[{index}].dimensions did not match coverage.dimensions"
            )

    period_start = _optional_temporal(
        evidence["coverage"].get("period_start"), field="coverage.period_start"
    )
    period_end = _optional_temporal(
        evidence["coverage"].get("period_end"), field="coverage.period_end"
    )
    if period_start is not None and period_end is not None and period_start > period_end:
        raise ValueError("coverage.period_start cannot be later than coverage.period_end")

    observed = _optional_temporal(evidence.get("observed_at"), field="observed_at")
    if observed is not None and period_end is not None and observed != period_end:
        raise ValueError("coverage.period_end did not match observed_at")

    if "date" in expected_dimensions:
        for index, record in enumerate(records):
            record_date = _temporal(
                record["dimensions"].get("date"),
                field=f"records[{index}].dimensions.date",
            )
            if period_start is not None and record_date < period_start:
                raise ValueError(
                    f"records[{index}].dimensions.date preceded coverage.period_start"
                )
            if period_end is not None and record_date > period_end:
                raise ValueError(
                    f"records[{index}].dimensions.date exceeded coverage.period_end"
                )


def _validate_url_inspection(
    evidence: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    _require_sample_kind(evidence, "single_url_inspection")
    _require_exact_count(evidence["sample"], "url_count", len(records), field_prefix="sample")
    _require_exact_count(
        evidence["coverage"], "url_count", len(records), field_prefix="coverage"
    )
    if len(records) != 1:
        raise ValueError("URL Inspection observed coverage must contain exactly one URL")


def _validate_bing(
    evidence: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    _require_sample_kind(evidence, "provider_export_rows")
    _require_exact_count(evidence["sample"], "row_count", len(records), field_prefix="sample")
    coverage = evidence["coverage"]
    normalized = _non_negative_integer(
        coverage.get("normalized_row_count"), field="coverage.normalized_row_count"
    )
    input_count = _non_negative_integer(
        coverage.get("input_row_count"), field="coverage.input_row_count"
    )
    rejected = _non_negative_integer(
        coverage.get("rejected_row_count"), field="coverage.rejected_row_count"
    )
    if normalized != len(records):
        raise ValueError("coverage.normalized_row_count did not match carried record count")
    if input_count != normalized + rejected:
        raise ValueError(
            "coverage.input_row_count must equal normalized_row_count + rejected_row_count"
        )
    observed = _validate_period_end_matches_observed(evidence)
    _validate_record_dates_not_after_observed(records, observed=observed)


def _validate_ga4(
    evidence: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    _require_sample_kind(evidence, "analytics_aggregate_rows")
    _require_exact_count(evidence["sample"], "row_count", len(records), field_prefix="sample")
    coverage = evidence["coverage"]
    normalized = _non_negative_integer(
        coverage.get("normalized_row_count"), field="coverage.normalized_row_count"
    )
    input_count = _non_negative_integer(
        coverage.get("input_row_count"), field="coverage.input_row_count"
    )
    unmatched = _non_negative_integer(
        coverage.get("unmatched_row_count"), field="coverage.unmatched_row_count"
    )
    rejected = _non_negative_integer(
        coverage.get("rejected_row_count"), field="coverage.rejected_row_count"
    )
    if normalized != len(records):
        raise ValueError("coverage.normalized_row_count did not match carried record count")
    if input_count != normalized + unmatched + rejected:
        raise ValueError(
            "coverage.input_row_count must equal normalized_row_count + unmatched_row_count + rejected_row_count"
        )
    observed = _validate_period_end_matches_observed(evidence)
    _validate_record_dates_not_after_observed(records, observed=observed)


def validate_connected_evidence_coverage_semantics(
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate sample/coverage accounting and return ``evidence`` unchanged.

    This validator intentionally runs after record semantics. Unavailable
    evidence carries no observations under the generic contract, so it has no
    record-accounting claim to prove. Observed evidence must truthfully bind
    sample/coverage counts and periods to the records that are actually carried.
    """

    validate_connected_evidence_record_semantics(evidence)

    if evidence["state"] in _UNAVAILABLE_STATES:
        return evidence

    records = evidence["records"]
    profile_key = (evidence["provider"], evidence["source_kind"])
    if profile_key == ("google_search_console", "search_analytics"):
        _validate_gsc(evidence, records)
    elif profile_key == ("google_search_console", "url_inspection"):
        _validate_url_inspection(evidence, records)
    elif profile_key == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        _validate_bing(evidence, records)
    elif profile_key == ("google_analytics_4", "ai_assistant_referrals"):
        _validate_ga4(evidence, records)
    else:
        raise ValueError("unsupported connected-evidence provider/source_kind profile")
    return evidence
