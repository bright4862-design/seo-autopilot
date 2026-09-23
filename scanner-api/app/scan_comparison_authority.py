"""Authenticated, read-only adapter for persisted V8 rescan comparisons.

Existing result seals authenticate each result, but do NOT authenticate
``previous_scan_id``. The internal lineage producer must first read that
relationship through the owner-bound, service-owned ScanRun path. It may then
call ``build_scan_comparison_lineage_v1`` to bind that relationship to both
exact result proofs. Neither function is a public endpoint or an access gate:
the serialized integrator still owns paid access, supported release checks,
server-owned lineage lookup, routing and customer delivery.

The consumer verifies both original result seals and this separate HMAC domain.
Only authenticated snapshot recommendations enter the canonical comparator.
Durable snapshots omit the complete observed-page population, so this adapter
always passes an empty page population: a missing finding cannot prove a fix.
No historic snapshot, score, repair identity, or customer row is rewritten.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import hmac
import math
import re
from typing import Any
from urllib.parse import urlsplit

from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from .repair_identity import (
    REPAIR_IDENTITY_VERSION,
    build_repair_identity,
    verification_contract_comparability,
)
from .scan_comparison import _by_reference_fingerprint, build_scan_comparison_v1
from .scan_comparison_integrity import (
    build_validated_customer_scan_comparison_presentation,
    build_validated_scan_comparison_transport_v1,
)
from .authority_seal import create_authority_seal, stable_serialize

SCAN_COMPARISON_AUTHORITY_VERSION = "scan_comparison_authority_v1"
SCAN_COMPARISON_LINEAGE_VERSION = "scan_comparison_lineage_v1"
LINEAGE_INTEGRITY_DOMAIN = "fixlist_scan_comparison_lineage_hmac_sha256_v1"
ACCEPTED_AUTHORITY_VERSIONS = frozenset({
    "standard_review_snapshot_hmac_v1",
    "standard_review_snapshot_hmac_v2_coverage",
    "standard_review_snapshot_hmac_v3_acceptance_evidence",
    "standard_review_snapshot_hmac_v4_focused_scope",
    "standard_review_snapshot_hmac_v5_score_explanation",
    "standard_review_snapshot_hmac_v6_report_evidence",
    "standard_review_snapshot_hmac_geo_v1",
    "standard_review_snapshot_hmac_identity_v1",
})
_PROOF = re.compile(r"[0-9a-f]{64}\Z")
_FIX_FIELDS = (
    "fix_id", "rule", "category", "page_scope", "page_template_family",
    "page_url", "affected_pages", "repair_identity_version",
    "repair_identity_state", "repair_identity_stable", "repair_fingerprint",
    "repair_surface", "remediation_family", "verification_state",
    "repair_verification_state", "rule_definition_version", "comparison_profile_version",
)


def _string(value: Any, field: str, maximum: int = 256, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or value != value.strip() or (not empty and not value):
        raise ValueError(f"{field} must be an exact bounded string")
    return value


def _json_shape(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [100_000]
    budget[0] -= 1
    if depth > 30 or budget[0] < 0:
        raise ValueError("Authority payload exceeds structural bounds")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > 100_000:
            raise ValueError("Authority payload string exceeds bounds")
        return
    if isinstance(value, (int, float)):
        if abs(value) > 2**53 - 1 or not math.isfinite(value):
            raise ValueError("Authority payload contains an unsupported number")
        return
    if isinstance(value, list):
        for item in value:
            _json_shape(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            _json_shape(key, depth=depth + 1, budget=budget)
            _json_shape(item, depth=depth + 1, budget=budget)
        return
    raise ValueError("Authority payload must contain JSON values only")


def _key(signing_key: Any) -> str:
    if not isinstance(signing_key, str) or not signing_key:
        raise ValueError("Authority signing key is unavailable")
    # Key bytes are intentionally not stripped or normalized.
    return signing_key


def _verify(payload: Any, proof: Any, key: str) -> None:
    if not isinstance(payload, dict) or not isinstance(proof, str) or not _PROOF.fullmatch(proof):
        raise ValueError("Malformed authority payload or proof")
    _json_shape(payload)
    if len(stable_serialize(payload).encode("utf-8")) > 2_000_000:
        raise ValueError("Authority payload exceeds byte bound")
    if not hmac.compare_digest(create_authority_seal(payload, key), proof):
        raise ValueError("Authority proof verification failed")


def _origin(value: Any) -> str:
    raw = _string(value, "scan origin", 2_000)
    try:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError("Invalid scan origin")
        host = parsed.hostname.lower()
        port = parsed.port
        suffix = f":{port}" if port and (parsed.scheme, port) not in {("http", 80), ("https", 443)} else ""
        if ":" in host:
            host = f"[{host}]"
        return f"{parsed.scheme}://{host}{suffix}"
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid scan origin") from exc


def _scope(scan: dict[str, Any]) -> dict[str, str]:
    kind = _string(scan.get("scope_type", ""), "scope_type", 40, empty=True)
    prefix = _string(scan.get("requested_path_prefix", ""), "requested_path_prefix", 1_000, empty=True)
    origin = _origin(scan.get("requested_origin") or scan.get("website_url"))
    if kind == "path_prefix":
        if not prefix.startswith("/") or prefix.startswith("//") or any(char in prefix for char in ("?", "#", "\\")) or scan.get("user_confirmed") is not True:
            raise ValueError("Focused scan scope is incomplete")
    elif kind or prefix or scan.get("parent_scan_id") or scan.get("user_confirmed") is True:
        raise ValueError("Unsupported or incomplete scan scope")
    return {"origin": origin, "scope_type": kind, "requested_path_prefix": prefix}


def _count(value: Any, field: str) -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _time(value: Any) -> datetime:
    raw = _string(value, "sealed_at", 80)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError("Missing timezone")
        return result
    except ValueError as exc:
        raise ValueError("Invalid authority seal time") from exc


def _snapshot(snapshot: dict[str, Any], proof: str, key: str, owner: str, project: str) -> dict[str, Any]:
    _verify(snapshot, proof, key)
    if snapshot.get("version") not in ACCEPTED_AUTHORITY_VERSIONS:
        raise ValueError("Unsupported authority version")
    if snapshot.get("owner_user_id") != owner or snapshot.get("project_id") != project:
        raise ValueError("Authority owner or project mismatch")
    _string(snapshot.get("scan_id"), "scan_id")
    _time(snapshot.get("sealed_at"))
    scan, fix_list, fixes = snapshot.get("scan"), snapshot.get("fix_list"), snapshot.get("recommendations")
    if not isinstance(scan, dict) or not isinstance(fix_list, dict) or not isinstance(fixes, list) or len(fixes) > 100:
        raise ValueError("Incomplete authority snapshot")
    if (scan.get("status") != "complete" or scan.get("release_gate_eligible") is not True
            or scan.get("score_is_provisional") is not False or scan.get("evidence_quality_blocking") is not False
            or fix_list.get("is_authoritative") is not True or fix_list.get("score_is_provisional") is not False):
        raise ValueError("Comparison requires terminal authoritative snapshots")
    if _count(fix_list.get("total_fixes"), "total_fixes") != len(fixes):
        raise ValueError("Authority repair count mismatch")
    _count(scan.get("pages_crawled"), "pages_crawled")
    score = scan.get("health_score")
    if type(score) not in (int, float) or not 0 <= score <= 100 or type(fix_list.get("health_score")) not in (int, float) or fix_list["health_score"] != score:
        raise ValueError("Authority health score mismatch")
    domain = _string(snapshot.get("normalized_domain"), "normalized_domain", 2_000)
    scope = _scope(scan)
    if domain != domain.lower() or scan.get("normalized_domain") != domain or (urlsplit(scope["origin"]).hostname or "").removeprefix("www.") != domain:
        raise ValueError("Authority domain or origin mismatch")
    if scan.get("completed_at") != snapshot["sealed_at"]:
        raise ValueError("Authority completion time mismatch")
    ids = [_string(fix.get("fix_id"), "fix_id") if isinstance(fix, dict) else "" for fix in fixes]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("Invalid or duplicate authority repair identity")
    return scope


def _pair(*, previous_snapshot, previous_proof, current_snapshot, current_proof,
          expected_owner_user_id, expected_project_id, expected_current_scan_id, signing_key):
    key = _key(signing_key)
    owner = _string(expected_owner_user_id, "expected_owner_user_id")
    project = _string(expected_project_id, "expected_project_id")
    current_id = _string(expected_current_scan_id, "expected_current_scan_id")
    previous_scope = _snapshot(previous_snapshot, previous_proof, key, owner, project)
    current_scope = _snapshot(current_snapshot, current_proof, key, owner, project)
    if current_snapshot["scan_id"] != current_id or previous_snapshot["scan_id"] == current_id:
        raise ValueError("Authority scan identity mismatch")
    if previous_scope != current_scope or previous_snapshot["normalized_domain"] != current_snapshot["normalized_domain"]:
        raise ValueError("Authority scan scope mismatch")
    if _time(previous_snapshot["sealed_at"]) >= _time(current_snapshot["sealed_at"]):
        raise ValueError("Previous scan must precede current scan")
    return {
        "version": SCAN_COMPARISON_LINEAGE_VERSION,
        "integrity_domain": LINEAGE_INTEGRITY_DOMAIN,
        "owner_user_id": owner,
        "project_id": project,
        "normalized_domain": current_snapshot["normalized_domain"],
        "scope": current_scope,
        "previous_scan_id": previous_snapshot["scan_id"],
        "current_scan_id": current_id,
        "previous_authority_proof": previous_proof,
        "current_authority_proof": current_proof,
    }


def build_scan_comparison_lineage_v1(*, current_previous_scan_id: str, **pair: Any) -> dict[str, Any]:
    """Internal producer only: pointer MUST come from the service-owned run.

    Cryptography cannot prove that this caller read the database. Do not expose
    this helper to a customer endpoint that accepts a caller-chosen pointer.
    The artifact records the trusted producer's assertion, with a distinct
    domain, after both source results have independently authenticated.
    """
    payload = _pair(**pair)
    if _string(current_previous_scan_id, "current_previous_scan_id") != payload["previous_scan_id"]:
        raise ValueError("Server-owned scan lineage mismatch")
    return {**payload, "proof": create_authority_seal(payload, pair["signing_key"])}


def _repairs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    repairs = []
    for original in snapshot["recommendations"]:
        fix = {key: deepcopy(original[key]) for key in _FIX_FIELDS if key in original}
        published = original.get("raw_finding", {}).get("published_evidence", {}) if isinstance(original.get("raw_finding", {}), dict) else {}
        if not isinstance(published, dict):
            raise ValueError("Malformed authenticated published evidence")
        evidence_version = published.get("evidence_url_identity_version", "")
        if evidence_version:
            fix["evidence_url_identity_version"] = evidence_version
        supported = original.get("repair_identity_version") == REPAIR_IDENTITY_VERSION and evidence_version in ("", PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
        if supported:
            identity = build_repair_identity(fix)
            if (type(fix.get("repair_identity_stable")) is not bool
                    or fix["repair_identity_stable"] is not identity["stable"]
                    or fix.get("repair_identity_state") != identity["state"]
                    or (identity["stable"] and fix.get("repair_fingerprint") != identity["fingerprint"])):
                raise ValueError("Authenticated technical identity is contradictory")
        else:
            # Preserve an authenticated reference fingerprint without promoting
            # historical/unknown identity semantics into verification authority.
            fix.pop("repair_surface", None)
            fix.pop("remediation_family", None)
        repairs.append(fix)
    return repairs


def build_authenticated_scan_comparison_v1(*, lineage_artifact: dict[str, Any], **pair: Any) -> dict[str, Any]:
    """Verify exact snapshot/pair bytes and derive a comparison, without I/O."""
    expected = _pair(**pair)
    if not isinstance(lineage_artifact, dict):
        raise ValueError("Authenticated lineage artifact is required")
    payload = {key: value for key, value in lineage_artifact.items() if key != "proof"}
    _verify(payload, lineage_artifact.get("proof"), pair["signing_key"])
    if payload != expected:
        raise ValueError("Authenticated lineage does not match the exact scan pair")
    previous, current = pair["previous_snapshot"], pair["current_snapshot"]
    previous_fixes, current_fixes = _repairs(previous), _repairs(current)
    current_evidence_versions = {fix.get("evidence_url_identity_version", "") for fix in current_fixes}
    if len(current_evidence_versions) > 1:
        raise ValueError("Current repairs have incompatible evidence identity contracts")
    # v1 presents row counts, while unmatched references are grouped by the
    # comparator. An ambiguous population cannot become a complete customer tally.
    for population, fixes in (("previous", previous_fixes), ("current", current_fixes)):
        by_reference, _ = _by_reference_fingerprint(fixes, population=population)
        if any(len(rows) != 1 for rows in by_reference.values()):
            raise ValueError("Duplicate repair references cannot be represented in the comparison")
    current_evidence_version = next(iter(current_evidence_versions),
                                    PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
                                    if current["version"] == "standard_review_snapshot_hmac_identity_v1" else "")
    for prior in previous_fixes:
        prior_identity = build_repair_identity(prior)
        if not prior_identity["stable"]:
            continue
        for current_fix in current_fixes:
            identity = build_repair_identity(current_fix)
            if identity["stable"] and identity["fingerprint"] == prior_identity["fingerprint"]:
                if verification_contract_comparability(prior, current_fix)[0] == "incomparable":
                    raise ValueError("Matching repairs have incompatible comparison contracts")
    comparison = build_scan_comparison_v1(
        previous_scan_id=expected["previous_scan_id"], current_scan_id=expected["current_scan_id"],
        current_previous_scan_id=expected["previous_scan_id"], previous_fixes=previous_fixes,
        current_fixes=current_fixes, current_pages=[],
        current_contract={"evidence_url_identity_version": current_evidence_version},
        previous_score=previous["scan"]["health_score"], current_score=current["scan"]["health_score"],
        previous_pages_checked=previous["scan"]["pages_crawled"], current_pages_checked=current["scan"]["pages_crawled"],
        previous_scan_origin=expected["scope"]["origin"], current_scan_origin=expected["scope"]["origin"],
    )
    def receipt(snapshot, proof):
        return {"state": "verified", "scan_id": snapshot["scan_id"], "authority_seal_version": snapshot["version"],
                "authority_proof_fingerprint": hashlib.sha256(proof.encode()).hexdigest()}
    return {
        "version": SCAN_COMPARISON_AUTHORITY_VERSION,
        "comparison": comparison,
        "presentation": build_validated_customer_scan_comparison_presentation(comparison),
        "transport": build_validated_scan_comparison_transport_v1(
            comparison, previous_authority_receipt=receipt(previous, pair["previous_proof"]),
            current_authority_receipt=receipt(current, pair["current_proof"])),
        "current_pages_available": False,
        "customer_projection_authorized": False,
    }
