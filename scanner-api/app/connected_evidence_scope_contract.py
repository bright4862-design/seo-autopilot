"""Source/property scope semantics for FixList NextGen connected evidence.

This pure guard composes after envelope/source/record/coverage validation and
proves that provider-scoped records actually belong to the declared source
property. It performs no network I/O, authentication, persistence, scoring,
customer projection, release, deployment, or production mutation.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse

from .connected_evidence_coverage_contract import (
    validate_connected_evidence_coverage_semantics,
)

SCOPE_SEMANTICS_VERSION = "connected_evidence_scope_semantics_v1"

_GA4_PROPERTY_ID = re.compile(r"^(?:properties/)?[1-9][0-9]*$")


def _bounded_text(value: Any, *, field: str, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _canonical_host(value: str, *, field: str, allow_ip: bool = True) -> str:
    raw = value.strip().rstrip(".")
    if not raw or any(char.isspace() for char in raw):
        raise ValueError(f"{field} contained an invalid host")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        try:
            ascii_host = raw.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError(f"{field} contained an invalid host") from None
        labels = ascii_host.split(".")
        if (
            len(ascii_host) > 253
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or not re.fullmatch(r"[a-z0-9-]+", label)
                for label in labels
            )
        ):
            raise ValueError(f"{field} contained an invalid host")
        return ascii_host
    if not allow_ip:
        raise ValueError(f"{field} must identify a DNS domain, not an IP address")
    return address.compressed.lower()


def _canonical_http_url(
    value: Any,
    *,
    field: str,
    allow_query: bool = True,
) -> tuple[str, str]:
    text = _bounded_text(value, field=field)
    try:
        parsed = urlparse(text)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError
        if not allow_query and parsed.query:
            raise ValueError
        port = parsed.port
    except ValueError:
        raise ValueError(f"{field} must be a safe absolute HTTP(S) URL") from None

    host = _canonical_host(parsed.hostname, field=field)
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    if ":" in host:
        rendered_host = f"[{host}]"
    else:
        rendered_host = host
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"
    path = parsed.path or "/"
    canonical = urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            path,
            "",
            parsed.query if allow_query else "",
            "",
        )
    )
    return canonical, host


def _gsc_property_scope(value: Any) -> tuple[str, str]:
    text = _bounded_text(value, field="provenance.property_uri")
    prefix = "sc-domain:"
    if text.lower().startswith(prefix):
        domain = text[len(prefix) :].strip()
        if any(token in domain for token in ("/", "?", "#", "@", ":")):
            raise ValueError("provenance.property_uri contained an invalid sc-domain property")
        return "domain", _canonical_host(
            domain,
            field="provenance.property_uri",
            allow_ip=False,
        )

    canonical, _ = _canonical_http_url(
        text,
        field="provenance.property_uri",
        allow_query=False,
    )
    return "url_prefix", canonical


def _url_in_gsc_scope(value: Any, *, scope: tuple[str, str], field: str) -> None:
    canonical, host = _canonical_http_url(value, field=field)
    kind, identity = scope
    if kind == "domain":
        if host != identity and not host.endswith(f".{identity}"):
            raise ValueError(f"{field} was outside the declared Search Console domain property")
        return
    if not canonical.startswith(identity):
        raise ValueError(f"{field} was outside the declared Search Console URL-prefix property")


def _validate_gsc_scope(evidence: Mapping[str, Any]) -> None:
    provenance = evidence["provenance"]
    scope = _gsc_property_scope(provenance.get("property_uri"))
    source_kind = evidence["source_kind"]

    if source_kind == "url_inspection":
        _url_in_gsc_scope(
            provenance.get("inspection_url"),
            scope=scope,
            field="provenance.inspection_url",
        )
        return

    if source_kind != "search_analytics":
        raise ValueError("unsupported Google Search Console source scope")

    coverage = evidence["coverage"]
    dimensions = coverage.get("dimensions")
    if not isinstance(dimensions, list) or "page" not in dimensions:
        return
    records = evidence["records"]
    for index, record in enumerate(records):
        page = record.get("dimensions", {}).get("page")
        _url_in_gsc_scope(
            page,
            scope=scope,
            field=f"records[{index}].dimensions.page",
        )


def _validate_bing_scope(evidence: Mapping[str, Any]) -> None:
    site_prefix, _ = _canonical_http_url(
        evidence["provenance"].get("site_url"),
        field="provenance.site_url",
        allow_query=False,
    )
    for index, record in enumerate(evidence["records"]):
        value = record.get("url")
        if value in (None, ""):
            continue
        candidate, _ = _canonical_http_url(value, field=f"records[{index}].url")
        if not candidate.startswith(site_prefix):
            raise ValueError(f"records[{index}].url was outside provenance.site_url scope")


def _validate_ga4_scope(evidence: Mapping[str, Any]) -> None:
    property_id = _bounded_text(
        evidence["provenance"].get("property_id"),
        field="provenance.property_id",
        max_length=128,
    )
    if not _GA4_PROPERTY_ID.fullmatch(property_id):
        raise ValueError("provenance.property_id was not a GA4 property identifier")

    for index, record in enumerate(evidence["records"]):
        landing_page = record.get("landing_page")
        if landing_page in (None, "", "(not set)"):
            continue
        text = _bounded_text(
            landing_page,
            field=f"records[{index}].landing_page",
            max_length=4096,
        )
        parsed = urlparse(text)
        if (
            not text.startswith("/")
            or text.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
        ):
            raise ValueError(
                f"records[{index}].landing_page must be a root-relative GA4 landing-page path"
            )


def validate_connected_evidence_scope_semantics(
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate source/property scope binding and return ``evidence`` unchanged."""

    validate_connected_evidence_coverage_semantics(evidence)

    profile_key = (evidence["provider"], evidence["source_kind"])
    if profile_key in {
        ("google_search_console", "search_analytics"),
        ("google_search_console", "url_inspection"),
    }:
        _validate_gsc_scope(evidence)
    elif profile_key == ("microsoft_bing_webmaster_tools", "ai_performance_export"):
        _validate_bing_scope(evidence)
    elif profile_key == ("google_analytics_4", "ai_assistant_referrals"):
        _validate_ga4_scope(evidence)
    else:
        raise ValueError("unsupported connected-evidence provider/source_kind profile")
    return evidence
