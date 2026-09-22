"""Provider/source identity validation for FixList NextGen connected evidence.

This pure guard complements ``connected_evidence_v1`` structural validation by
checking that a normalized envelope is attributed to the provider surface and
provenance profile that produced it. It performs no network I/O, authentication,
persistence, scoring, or customer projection.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

from .connected_evidence_contract import validate_connected_evidence

SOURCE_PROFILE_VERSION = "connected_evidence_source_profile_v1"

_PROFILES: dict[tuple[str, str], dict[str, Any]] = {
    ("google_search_console", "search_analytics"): {
        "surface": "google_search_console.search_analytics",
        "method": "api_response_normalization",
        "transport": "provided_payload",
        "exact_provenance": {"provider_operation": "searchanalytics.query"},
        "required_provenance": ("property_uri",),
        "optional_provenance": (),
    },
    ("google_search_console", "url_inspection"): {
        "surface": "google_search_console.url_inspection",
        "method": "api_response_normalization",
        "transport": "provided_payload",
        "exact_provenance": {"provider_operation": "urlInspection.index.inspect"},
        "required_provenance": ("property_uri", "inspection_url"),
        "optional_provenance": (),
    },
    ("microsoft_bing_webmaster_tools", "ai_performance_export"): {
        "surface": "bing_webmaster_tools.ai_performance",
        "method": "manual_export_normalization",
        "transport": "manual_export",
        "exact_provenance": {
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "api_used": False,
        },
        "required_provenance": ("site_url",),
        "optional_provenance": ("import_name",),
    },
    ("google_analytics_4", "ai_assistant_referrals"): {
        "surface": "google_analytics_4.referral_traffic",
        "method": "aggregate_row_normalization",
        "transport": "provided_rows",
        "exact_provenance": {"provider_surface": "ga4_reporting_export_or_response"},
        "required_provenance": ("property_id",),
        "optional_provenance": ("import_name",),
    },
}


def _bounded_text(value: Any, *, field: str, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _absolute_url(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field)
    try:
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        parsed.port
    except ValueError:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL") from None
    return text


def _validate_path_prefix_identity(
    value: Any,
    *,
    field: str,
    allow_sc_domain: bool = False,
) -> str:
    """Fail closed on ambiguous path-scoped provider property identities.

    Search Console URL-prefix properties and Bing branch properties represent
    directory-like scopes. A non-root path that omits its trailing slash makes a
    later textual prefix check ambiguous (`/docs` versus `/docs-foreign`).
    Require the provider-style directory form instead of guessing membership.
    """

    text = _bounded_text(value, field=field)
    if allow_sc_domain and text.lower().startswith("sc-domain:"):
        return text

    text = _absolute_url(text, field=field)
    parsed = urlparse(text)
    if parsed.query or parsed.fragment:
        raise ValueError(f"{field} must not contain a query or fragment")
    path = parsed.path or "/"
    if path != "/" and not path.endswith("/"):
        raise ValueError(f"{field} path-scoped prefixes must end with '/'")
    return text


def _require_exact(actual: Any, expected: Any, *, field: str) -> None:
    if actual != expected:
        raise ValueError(f"{field} did not match the registered source profile")


def _http_host(value: Any, *, field: str) -> str:
    text = _absolute_url(value, field=field)
    parsed = urlparse(text)
    return parsed.hostname.lower().rstrip(".")


def _validate_optional_import_name(provenance: Mapping[str, Any]) -> None:
    value = provenance.get("import_name")
    if value is not None:
        _bounded_text(value, field="provenance.import_name", max_length=512)


def _validate_provenance_shape(
    provenance: Mapping[str, Any],
    *,
    profile: Mapping[str, Any],
) -> None:
    allowed = {
        "transport",
        *profile["exact_provenance"].keys(),
        *profile["required_provenance"],
        *profile.get("optional_provenance", ()),
    }
    unknown = sorted(set(provenance) - allowed)
    if unknown:
        raise ValueError(f"provenance has unregistered fields: {unknown}")


def _validate_profile_records(
    evidence: Mapping[str, Any],
    *,
    profile_key: tuple[str, str],
    provenance: Mapping[str, Any],
) -> None:
    records = evidence["records"]

    if profile_key == ("google_search_console", "url_inspection"):
        if evidence["state"] in {"verified", "stale"} and len(records) != 1:
            raise ValueError("URL Inspection observed evidence must contain exactly one record")
        expected_url = _absolute_url(
            provenance["inspection_url"], field="provenance.inspection_url"
        )
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ValueError(f"records[{index}] must be an object")
            record_url = _absolute_url(
                record.get("inspection_url"), field=f"records[{index}].inspection_url"
            )
            if record_url != expected_url:
                raise ValueError("URL Inspection record identity did not match provenance.inspection_url")

    if profile_key == ("microsoft_bing_webmaster_tools", "ai_performance_export"):
        site_host = _http_host(provenance["site_url"], field="provenance.site_url")
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ValueError(f"records[{index}] must be an object")
            url = record.get("url")
            if url in (None, ""):
                continue
            record_host = _http_host(url, field=f"records[{index}].url")
            if record_host != site_host:
                raise ValueError("Bing cited-page host did not match provenance.site_url")


def validate_connected_evidence_source_identity(
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate provider/source attribution and return ``evidence`` unchanged.

    The generic connected-evidence contract proves the envelope shape. This
    second boundary proves that the provider/source pair uses the expected
    surface, normalization method, transport, and connector-specific provenance.
    It intentionally fails closed for an unregistered provider/source profile.
    """

    validate_connected_evidence(evidence)

    profile_key = (evidence["provider"], evidence["source_kind"])
    profile = _PROFILES.get(profile_key)
    if profile is None:
        raise ValueError("unsupported connected-evidence provider/source_kind profile")

    _require_exact(evidence["surface"], profile["surface"], field="surface")
    _require_exact(evidence["method"], profile["method"], field="method")

    provenance = evidence["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be an object")
    _validate_provenance_shape(provenance, profile=profile)
    _require_exact(provenance.get("transport"), profile["transport"], field="provenance.transport")

    for field, expected in profile["exact_provenance"].items():
        actual = provenance.get(field)
        if type(expected) is bool and type(actual) is not bool:
            raise ValueError(f"provenance.{field} must be an explicit boolean")
        _require_exact(actual, expected, field=f"provenance.{field}")

    for field in profile["required_provenance"]:
        _bounded_text(provenance.get(field), field=f"provenance.{field}")

    if profile_key in {
        ("google_search_console", "search_analytics"),
        ("google_search_console", "url_inspection"),
    }:
        _validate_path_prefix_identity(
            provenance.get("property_uri"),
            field="provenance.property_uri",
            allow_sc_domain=True,
        )
    elif profile_key == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        _validate_path_prefix_identity(
            provenance.get("site_url"),
            field="provenance.site_url",
        )

    if profile_key in {
        ("microsoft_bing_webmaster_tools", "ai_performance_export"),
        ("google_analytics_4", "ai_assistant_referrals"),
    }:
        _validate_optional_import_name(provenance)

    _validate_profile_records(evidence, profile_key=profile_key, provenance=provenance)
    return evidence
