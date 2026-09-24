"""Bind Grounding to the exact current V8 authority snapshot.

This adapter is deliberately read-only and model-free. It verifies the whole
persisted V8 authority payload with the canonical HMAC primitive before
projecting a bounded subset of those already-signed fields into Grounding's
EvidenceSet vocabulary.

The projection is not authority and is never persisted. Unknown/historical
seal versions fail closed until their exact reconstruction semantics are
reviewed for Grounding.
"""
from __future__ import annotations

from copy import deepcopy
import hmac
import json
import re
from typing import Any

from .authority_seal import create_authority_seal, stable_serialize
from .grounding_verifier import EvidenceSet, EvidenceUnavailable, build_evidence_set

GROUNDING_V8_AUTHORITY_ADAPTER_VERSION = "grounding_v8_authority_adapter_v1"
GROUNDING_V8_AUTHORITY_VERSION = "standard_review_snapshot_hmac_identity_v1"
_MAX_AUTHORITY_BYTES = 2_000_000
_PROOF = re.compile(r"[0-9a-f]{64}\Z")


def _fail_auth() -> None:
    raise EvidenceUnavailable("sealed_l2_authentication_failed")


def _json_copy(value: Any) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise EvidenceUnavailable("v8_grounding_projection_unavailable") from None


def _authenticate_v8_snapshot(snapshot: Any, proof: Any, signing_key: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("version") != GROUNDING_V8_AUTHORITY_VERSION:
        _fail_auth()
    if not isinstance(proof, str) or not _PROOF.fullmatch(proof):
        _fail_auth()
    if not isinstance(signing_key, str) or not signing_key:
        _fail_auth()

    candidate = _json_copy(snapshot)
    try:
        serialized = stable_serialize(candidate)
    except (TypeError, ValueError, OverflowError, RecursionError):
        _fail_auth()
    if len(serialized.encode("utf-8")) > _MAX_AUTHORITY_BYTES:
        _fail_auth()

    try:
        expected = create_authority_seal(candidate, signing_key)
    except Exception:
        _fail_auth()
    if not hmac.compare_digest(expected, proof):
        _fail_auth()
    return candidate


def _project_authenticated_v8_snapshot(snapshot: dict[str, Any], proof: str) -> dict[str, Any]:
    scan = snapshot.get("scan")
    fix_list = snapshot.get("fix_list")
    recommendations = snapshot.get("recommendations")
    if not isinstance(scan, dict) or not isinstance(fix_list, dict) or not isinstance(recommendations, list):
        raise EvidenceUnavailable("v8_grounding_projection_unavailable")
    if len(recommendations) > 100 or any(not isinstance(item, dict) for item in recommendations):
        raise EvidenceUnavailable("v8_grounding_projection_unavailable")

    if (
        scan.get("status") != "complete"
        or scan.get("release_gate_eligible") is not True
        or scan.get("score_is_provisional") is not False
        or scan.get("evidence_quality_blocking") is not False
        or fix_list.get("is_authoritative") is not True
        or fix_list.get("score_is_provisional") is not False
    ):
        raise EvidenceUnavailable("v8_grounding_projection_unavailable")

    sealed_at = snapshot.get("sealed_at")
    website_url = scan.get("website_url")
    requested_origin = scan.get("requested_origin")
    if not isinstance(sealed_at, str) or not sealed_at or not isinstance(website_url, str) or not website_url:
        raise EvidenceUnavailable("v8_grounding_projection_unavailable")
    if requested_origin is not None and not isinstance(requested_origin, str):
        raise EvidenceUnavailable("v8_grounding_projection_unavailable")

    # Copy only fields already covered by the verified V8 HMAC. Renaming
    # recommendations to fixes and lifting signed scan fields is a projection
    # into Grounding's existing allowlisted vocabulary; it does not create new
    # factual content or new authority.
    source: dict[str, Any] = {
        "authority_seal_version": snapshot["version"],
        "authority_sealed_at": sealed_at,
        "authority_proof": proof,
        "website_url": website_url,
        "crawl_scope": {
            "requested_origin": requested_origin or website_url,
        },
        "status": scan.get("status"),
        "scan_status": scan.get("scan_status"),
        "health_score": scan.get("health_score"),
        "pages_found": scan.get("pages_found"),
        "pages_crawled": scan.get("pages_crawled"),
        "pages_retained": scan.get("pages_retained"),
        "release_gate_eligible": scan.get("release_gate_eligible"),
        "evidence_quality_blocking": scan.get("evidence_quality_blocking"),
        "score_is_provisional": scan.get("score_is_provisional"),
        "fix_count": fix_list.get("total_fixes"),
        "health_score_explanation": deepcopy(scan.get("health_score_explanation") or {}),
        "fixes": deepcopy(recommendations),
    }
    return _json_copy(source)


def build_evidence_set_from_v8_authority(
    snapshot: Any,
    *,
    proof: Any,
    signing_key: Any,
) -> EvidenceSet:
    """Verify one current V8 snapshot, then derive Grounding evidence from it.

    This function is the only integration entrypoint introduced by this module.
    It does not accept a pre-asserted authority_verified marker and does not
    expose a path that skips HMAC verification.
    """
    authenticated = _authenticate_v8_snapshot(snapshot, proof, signing_key)
    projected = _project_authenticated_v8_snapshot(authenticated, proof)
    return build_evidence_set(projected)
