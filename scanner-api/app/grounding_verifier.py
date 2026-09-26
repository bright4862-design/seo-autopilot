"""Deterministic fail-closed grounding for future FixList AI output.

This module does not call a model, crawl the web, persist data, rank repairs, or
create authority. It verifies strict AI envelopes against a read-only EvidenceSet
built from a caller-authenticated L2 snapshot. Seal-marker shape checks are not
cryptographic authentication; a runtime adapter must verify the exact snapshot
before calling the offline builder.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .ai_schemas import AIAnnotationV1, ChatAnswerV1, UnknownAISchemaVersion, validate_ai_schema
from .repair_coverage import published_evidence_url_key, scan_evidence_origin
from .stage3_root_causes import validate_root_cause_evidence

EVIDENCE_SET_VERSION = "ai_evidence_set_v1"
GROUNDING_VERIFIER_VERSION = "grounding_verifier_v1"
DETERMINISTIC_ANNOTATION_TEXT_VERSION = "grounded_annotation_text_v1"
DETERMINISTIC_ANNOTATION_TEXT = "Grounded evidence is available for this annotation."
_STAGE3_HANDOFF_VERSION = "fixlist_handoff_v2"

# URL evidence is intentionally container-bound. A sealed snapshot can contain
# diagnostics/metadata with URL-looking fields; those are not citation evidence
# unless they live inside a known observed-page, Fix, or root-cause collection.
_EVIDENCE_URL_FIELDS = frozenset({
    "url", "final_url", "canonical_url", "source_url", "destination_url",
    "evidence_url", "requested_url", "published_url", "request_url",
    "verified_final_url",
})
_PAGE_URL_FIELDS = _EVIDENCE_URL_FIELDS | frozenset({"page_url", "path"})
_URL_LIST_FIELDS = frozenset({"affected_urls", "evidence_urls", "verified_urls", "urls", "evidence_refs"})
_PAGE_CONTAINERS = frozenset({"pages", "crawled_pages", "scanned_pages", "crawl_pages"})
_STATUS_FIELDS = ("status_code", "http_status", "response_status")
_NESTED_EVIDENCE_CONTAINERS = frozenset({
    "redirect_fetch_evidence",
    "url_provenance",
    "evidence",
    "evidence_detail",
    "evidence_details",
    "source_evidence",
    "observed_evidence",
})
_ROOT_DETAIL_EVIDENCE_CONTAINERS = frozenset({"details"})
_FIX_CONTAINERS = frozenset({"fixes", "cleaned_fixes", "recommended_actions", "findings", "repairs"})
_ROOT_CONTAINERS = frozenset({"root_causes", "root_cause_evidence"})
_FIX_ID_FIELDS = frozenset({"fix_id", "repair_id", "repair_fingerprint"})
_ROOT_ID_FIELDS = frozenset({"root_cause_id"})
_SEAL_FIELDS = ("authority_seal_version", "authority_sealed_at", "authority_proof")

# Evidence membership is path-bound. Recognizing a collection name at an
# arbitrary recursive location (for example ``diagnostics.pages`` or
# ``metadata.fixes``) must never grant sealed evidence authority.
_ROOT_PAGE_PATHS = frozenset((name,) for name in _PAGE_CONTAINERS)
_ROOT_FIX_PATHS = frozenset((name,) for name in _FIX_CONTAINERS)
_ROOT_CAUSE_PATHS = frozenset({("root_causes",)})
_HANDOFF_FIX_PATHS = frozenset({
    ("stage3_handoff_v2_source", "fixes"),
    ("review", "stage3_handoff_v2_source", "fixes"),
    ("health_score_explanation", "stage3_delivery", "handoff_v2_source", "fixes"),
})
_AUTHORIZED_FIX_PATHS = _ROOT_FIX_PATHS | _HANDOFF_FIX_PATHS

# Scalar claims have a separate positive contract from URL/ref membership.
# The exact sealed-schema path, direct field, and JSON scalar type must all
# match. Expand this only with a reviewed producer contract.
_ROOT_SCALAR_FIELD_TYPES = {
    "status": "string",
    "scan_status": "string",
    "health_score": "number",
    "pages_found": "integer",
    "pages_crawled": "integer",
    "pages_retained": "integer",
    "fix_count": "integer",
    "release_gate_eligible": "boolean",
    "evidence_quality_blocking": "boolean",
    "score_is_provisional": "boolean",
    "provisional": "boolean",
    "authority_verified": "boolean",
}
_PAGE_SCALAR_FIELD_TYPES = {
    "status_code": "integer",
    "http_status": "integer",
    "response_status": "integer",
}
_ROOT_CAUSE_SCALAR_FIELD_TYPES = {"state": "string"}
_FIX_COUNT_FIELD_TYPES = {
    "unique_affected_pages": "integer",
    "observations": "integer",
    "known_population": "integer",
    "displayed_examples": "integer",
    "indexable_affected": "integer",
}
_HEALTH_SCORE_DECISION_FIELD_TYPES = {
    "adjusted_health_score": "number",
    "coverage_state": "string",
    "state": "string",
}
_HANDOFF_VERSION_PATHS = {
    path: path[:-1] for path in _HANDOFF_FIX_PATHS
}

Scalar = str | int | float | bool


class EvidenceUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceSet:
    version: str
    fingerprint: str
    scan_origin: str
    url_members: frozenset[str]
    live_urls: frozenset[str]
    numeric_values: Mapping[str, int | float]
    state_values: Mapping[str, Scalar]
    fix_refs: frozenset[str]
    root_cause_refs: frozenset[str]
    ambiguous_fix_refs: frozenset[str]
    ambiguous_root_cause_refs: frozenset[str]
    conflicting_fix_refs: frozenset[str]
    conflicting_root_cause_refs: frozenset[str]


class GroundingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verifier_version: Literal["grounding_verifier_v1"] = GROUNDING_VERIFIER_VERSION
    status: Literal["verified", "redacted", "rejected", "unavailable"]
    schema_version: str = ""
    evidence_fingerprint: str = ""
    verified_payload: dict[str, Any] | None = None
    redacted_annotation_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if key.isidentifier():
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _scalar_matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected == "boolean":
        return type(value) is bool
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float) and not (
            isinstance(value, float) and not isfinite(value)
        )
    return False


def _node_at_path(source: dict[str, Any], parts: tuple[str, ...]) -> Any:
    node: Any = source
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _json_path(parts: tuple[str | int, ...]) -> str:
    path = "$"
    for part in parts:
        path = _path(path, part)
    return path


def _typed_scalar_values(source: dict[str, Any]):
    """Yield only exact-path, exact-field, exact-type scalar evidence."""
    for field, expected in _ROOT_SCALAR_FIELD_TYPES.items():
        value = source.get(field)
        if _scalar_matches_type(value, expected):
            yield _json_path((field,)), value

    decision_parts = ("health_score_explanation", "stage3_delivery", "health_score_decision")
    decision = _node_at_path(source, decision_parts)
    if isinstance(decision, dict):
        for field, expected in _HEALTH_SCORE_DECISION_FIELD_TYPES.items():
            value = decision.get(field)
            if _scalar_matches_type(value, expected):
                yield _json_path((*decision_parts, field)), value

    record_contracts = (
        *((path, _PAGE_SCALAR_FIELD_TYPES, None) for path in _ROOT_PAGE_PATHS),
        *((path, _ROOT_CAUSE_SCALAR_FIELD_TYPES, None) for path in _ROOT_CAUSE_PATHS),
        *((path, {}, _FIX_COUNT_FIELD_TYPES) for path in _AUTHORIZED_FIX_PATHS),
    )
    for collection_parts, field_types, child_field_types in record_contracts:
        version_path = _HANDOFF_VERSION_PATHS.get(collection_parts)
        if version_path is not None:
            handoff = _node_at_path(source, version_path)
            if not isinstance(handoff, dict) or handoff.get("handoff_version") != _STAGE3_HANDOFF_VERSION:
                continue

        records = _node_at_path(source, collection_parts)
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            record_parts: tuple[str | int, ...] = (*collection_parts, index)
            for field, expected in field_types.items():
                value = record.get(field)
                if _scalar_matches_type(value, expected):
                    yield _json_path((*record_parts, field)), value
            if child_field_types:
                counts = record.get("counts")
                if isinstance(counts, dict):
                    for field, expected in child_field_types.items():
                        value = counts.get(field)
                        if _scalar_matches_type(value, expected):
                            yield _json_path((*record_parts, "counts", field)), value


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _url_key(value: Any, scan_origin: str) -> str:
    return published_evidence_url_key(value, scan_origin=scan_origin)


def _observed_status_code(node: dict[str, Any]) -> int:
    for field in _STATUS_FIELDS:
        status = node.get(field)
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return 0


def _strict_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _stage3_handoff_sources(sealed_l2: dict[str, Any]) -> list[dict[str, Any]]:
    """Read only known sealed Stage-3 handoff placements.

    Grounding does not infer scan identity from arbitrary ``scan_id`` fields.
    The producer identity is accepted only from the existing signed/persisted
    Handoff-v2 surfaces used by V8.
    """
    sources: list[dict[str, Any]] = []

    direct = sealed_l2.get("stage3_handoff_v2_source")
    if isinstance(direct, dict):
        sources.append(direct)

    review = sealed_l2.get("review")
    if isinstance(review, dict):
        review_source = review.get("stage3_handoff_v2_source")
        if isinstance(review_source, dict):
            sources.append(review_source)

    explanation = sealed_l2.get("health_score_explanation")
    if isinstance(explanation, dict):
        delivery = explanation.get("stage3_delivery")
        if isinstance(delivery, dict):
            delivery_source = delivery.get("handoff_v2_source")
            if isinstance(delivery_source, dict):
                sources.append(delivery_source)

    return sources


def _trusted_stage3_scan_identity(sealed_l2: dict[str, Any]) -> tuple[str, str]:
    """Return ``(scan_id, state)`` for known sealed Handoff-v2 sources.

    States are ``verified``, ``absent``, and ``invalid``. Any recognized source
    with a malformed/version-mismatched identity, or multiple recognized sources
    that disagree, fails closed to ``invalid``.
    """
    sources = _stage3_handoff_sources(sealed_l2)
    if not sources:
        return "", "absent"

    identities: set[str] = set()
    for source in sources:
        if source.get("handoff_version") != _STAGE3_HANDOFF_VERSION:
            return "", "invalid"
        scan = source.get("scan")
        if not isinstance(scan, dict):
            return "", "invalid"
        scan_id = _strict_text(scan.get("scan_id"))
        scan_run_id = _strict_text(scan.get("scan_run_id"))
        if not scan_id or scan_id != scan_run_id:
            return "", "invalid"
        identities.add(scan_id)

    if len(identities) != 1:
        return "", "invalid"
    return next(iter(identities)), "verified"


def _trusted_stage3_fix_membership(
    sealed_l2: dict[str, Any],
    *,
    trusted_scan_state: str,
) -> tuple[frozenset[int], str]:
    """Return exact recognized Handoff-v2 Fix members for producer binding.

    A verified producer identity must not authorize a different sibling ``fixes``
    collection merely because it lives inside the same sealed snapshot. When at
    least one recognized Handoff-v2 source declares its ``fixes`` list, nested
    Stage-3 root evidence is bound to those exact member objects. Older synthetic
    snapshots that carry producer identity but no Handoff ``fixes`` field retain
    the pre-binding compatibility path. Malformed declared membership fails closed.
    """
    if trusted_scan_state == "invalid":
        return frozenset(), "invalid"
    if trusted_scan_state != "verified":
        return frozenset(), "inactive"

    member_ids: set[int] = set()
    declared = False
    for source in _stage3_handoff_sources(sealed_l2):
        if "fixes" not in source:
            continue
        declared = True
        fixes = source.get("fixes")
        if not isinstance(fixes, list):
            return frozenset(), "invalid"
        for fix in fixes:
            if not isinstance(fix, dict):
                return frozenset(), "invalid"
            member_ids.add(id(fix))

    if not declared:
        return frozenset(), "legacy_unbound"
    return frozenset(member_ids), "enforced"


def _member_matches_trusted_scan(
    fix: dict[str, Any],
    *,
    trusted_scan_id: str,
    trusted_scan_state: str,
) -> bool:
    if trusted_scan_state == "invalid":
        return False

    local_fields = ("scan_id", "scan_run_id")
    asserted = [field for field in local_fields if field in fix]
    if not asserted:
        return True

    # Repair-local scan identity is a consistency assertion only. If a repair
    # chooses to carry it, require the same exact producer invariant as Handoff-v2:
    # both fields must be present, strict non-empty strings, and equal. Partial,
    # null/empty, structured, or internally mismatched local assertions cannot
    # authorize nested root evidence or its URLs.
    if len(asserted) != len(local_fields):
        return False
    raw_scan_id = fix.get("scan_id")
    raw_scan_run_id = fix.get("scan_run_id")
    if not isinstance(raw_scan_id, str) or not isinstance(raw_scan_run_id, str):
        return False
    local_scan_id = raw_scan_id.strip()
    local_scan_run_id = raw_scan_run_id.strip()
    if not local_scan_id or local_scan_id != local_scan_run_id:
        return False

    if trusted_scan_state == "verified":
        return local_scan_id == trusted_scan_id
    return True


def _authorized_fix_record(
    node: Any,
    *,
    schema_path: tuple[str, ...],
    trusted_scan_id: str,
    trusted_scan_state: str,
    trusted_member_ids: frozenset[int],
    trusted_membership_state: str,
) -> bool:
    """Authorize a Fix only at a known path and, when present, signed membership."""
    if not isinstance(node, dict) or schema_path not in _AUTHORIZED_FIX_PATHS:
        return False
    if trusted_membership_state == "invalid" or trusted_scan_state == "invalid":
        return False
    if schema_path in _HANDOFF_FIX_PATHS:
        return (
            trusted_scan_state == "verified"
            and trusted_membership_state == "enforced"
            and id(node) in trusted_member_ids
            and _member_matches_trusted_scan(
                node,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
            )
        )
    if trusted_scan_state == "verified" and trusted_membership_state == "enforced":
        return id(node) in trusted_member_ids
    return _member_matches_trusted_scan(
        node,
        trusted_scan_id=trusted_scan_id,
        trusted_scan_state=trusted_scan_state,
    )


def _verified_root_cause_evidence_identity(
    node: Any,
    *,
    parent_container: str,
    parent_fix: dict[str, Any] | None = None,
    trusted_scan_id: str = "",
    trusted_scan_state: str = "absent",
    trusted_member_ids: frozenset[int] = frozenset(),
    trusted_membership_state: str = "inactive",
) -> tuple[str, str] | None:
    """Return Stage-3 root/surface identity only for trusted producer evidence.

    Grounding reuses the existing Stage-3 evidence validator and, when a sealed
    Handoff-v2 producer identity is present, applies both the repair-local scan
    consistency rule and the signed Handoff ``fixes`` containment rule. A sibling
    Fix collection cannot borrow producer identity to manufacture root authority or
    citation URLs. Legacy/synthetic snapshots with no declared Handoff members keep
    their prior single-definition compatibility behavior.
    """
    if parent_container not in _FIX_CONTAINERS or not isinstance(node, dict) or not isinstance(parent_fix, dict):
        return None
    if trusted_membership_state == "invalid":
        return None
    if (
        trusted_scan_state == "verified"
        and trusted_membership_state == "enforced"
        and id(parent_fix) not in trusted_member_ids
    ):
        return None
    if not _member_matches_trusted_scan(
        parent_fix,
        trusted_scan_id=trusted_scan_id,
        trusted_scan_state=trusted_scan_state,
    ):
        return None
    validated = validate_root_cause_evidence({"root_cause_evidence": node})
    if validated.get("state") != "verified":
        return None
    root_id = validated.get("root_cause_id")
    if not isinstance(root_id, str) or not root_id.strip():
        return None
    surface_id = validated.get("repair_surface_id")
    surface = surface_id.strip() if isinstance(surface_id, str) else ""
    return root_id.strip(), surface


def _nested_evidence_scope_allowed(*, container: str, child_name: str, evidence_scope: bool) -> bool:
    if child_name in _NESTED_EVIDENCE_CONTAINERS:
        return container in _FIX_CONTAINERS or container in _ROOT_CONTAINERS or evidence_scope
    if child_name in _ROOT_DETAIL_EVIDENCE_CONTAINERS:
        return container in _ROOT_CONTAINERS
    return False


def _collect_urls(
    node: Any,
    scan_origin: str,
    members: set[str],
    live: set[str],
    *,
    container: str = "",
    parent_container: str = "",
    schema_path: tuple[str, ...] = (),
    evidence_scope: bool = False,
    trusted_scan_id: str = "",
    trusted_scan_state: str = "absent",
    trusted_member_ids: frozenset[int] = frozenset(),
    trusted_membership_state: str = "inactive",
) -> None:
    if isinstance(node, dict):
        page_record = schema_path in _ROOT_PAGE_PATHS
        fix_record = _authorized_fix_record(
            node,
            schema_path=schema_path,
            trusted_scan_id=trusted_scan_id,
            trusted_scan_state=trusted_scan_state,
            trusted_member_ids=trusted_member_ids,
            trusted_membership_state=trusted_membership_state,
        )
        root_record = schema_path in _ROOT_CAUSE_PATHS
        evidence_record = fix_record or root_record
        authorized = evidence_scope or page_record or evidence_record

        if authorized:
            fields = _PAGE_URL_FIELDS if page_record else _EVIDENCE_URL_FIELDS
            for field in fields:
                if field in node:
                    key = _url_key(node.get(field), scan_origin)
                    if key:
                        members.add(key)
            for field in _URL_LIST_FIELDS:
                values = node.get(field)
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            key = _url_key(value, scan_origin)
                            if key:
                                members.add(key)

        # Liveness belongs only to an observed page record. A diagnostics object
        # carrying ``url`` + ``status_code`` cannot manufacture a live citation.
        if page_record:
            status = _observed_status_code(node)
            if 200 <= status < 400:
                for field in ("verified_final_url", "final_url", "url", "requested_url", "page_url", "path"):
                    key = _url_key(node.get(field), scan_origin)
                    if key:
                        members.add(key)
                        live.add(key)
                        break

        for key, child in node.items():
            child_name = str(key)
            child_path = (*schema_path, child_name)
            if child_name == "root_cause_evidence" and fix_record:
                child_scope = fix_record and bool(
                    _verified_root_cause_evidence_identity(
                        child,
                        parent_container=container,
                        parent_fix=node,
                        trusted_scan_id=trusted_scan_id,
                        trusted_scan_state=trusted_scan_state,
                        trusted_member_ids=trusted_member_ids,
                        trusted_membership_state=trusted_membership_state,
                    )
                )
            else:
                # Evidence scope is never inherited merely because an ancestor
                # was a Fix/root-cause record. Only explicit evidence-shaped child
                # containers may carry citation membership deeper into the tree.
                # Generic ``details`` is intentionally root-only; permitting it
                # on a Fix would let prose/diagnostic metadata launder URLs.
                child_scope = authorized and _nested_evidence_scope_allowed(
                    container=container,
                    child_name=child_name,
                    evidence_scope=evidence_scope,
                )
            _collect_urls(
                child,
                scan_origin,
                members,
                live,
                container=child_name,
                parent_container=container,
                schema_path=child_path,
                evidence_scope=child_scope,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
                trusted_member_ids=trusted_member_ids,
                trusted_membership_state=trusted_membership_state,
            )
    elif isinstance(node, list):
        for child in node:
            _collect_urls(
                child,
                scan_origin,
                members,
                live,
                container=container,
                parent_container=parent_container,
                schema_path=schema_path,
                evidence_scope=evidence_scope,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
                trusted_member_ids=trusted_member_ids,
                trusted_membership_state=trusted_membership_state,
            )


def _fix_container_id_fields(container: str) -> frozenset[str]:
    # Stage-3 Handoff v2 calls the canonical Fix identity ``rule_id`` inside its
    # ``fixes`` collection. Keep that compatibility deliberately container-bound
    # so unrelated ``rule_id`` fields elsewhere cannot become Fix identities.
    if container == "fixes":
        return _FIX_ID_FIELDS | frozenset({"id", "rule_id"})
    if container in _FIX_CONTAINERS:
        return _FIX_ID_FIELDS | frozenset({"id"})
    return frozenset()


def _fix_identity_alias_fields(container: str) -> frozenset[str]:
    # ``repair_fingerprint`` is an independently valid sealed reference, not an
    # alias for the human/stable Fix identifier. A Fix may legitimately carry
    # both ``fix_id`` and a different fingerprint; only canonical ID aliases are
    # required to agree with one another.
    return _fix_container_id_fields(container) - frozenset({"repair_fingerprint"})


def _record_strings(node: dict[str, Any], fields: frozenset[str]) -> set[str]:
    values: set[str] = set()
    for field in fields:
        value = node.get(field)
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    return values


def _collect_refs(
    node: Any,
    *,
    container: str = "",
    parent_container: str = "",
    schema_path: tuple[str, ...] = (),
    fixes: set[str],
    roots: set[str],
    fix_counts: dict[str, int],
    root_counts: dict[str, int],
    grouped_root_surfaces: dict[str, set[str]],
    conflicting_fixes: set[str],
    conflicting_roots: set[str],
    trusted_scan_id: str = "",
    trusted_scan_state: str = "absent",
    trusted_member_ids: frozenset[int] = frozenset(),
    trusted_membership_state: str = "inactive",
) -> None:
    if isinstance(node, dict):
        # Repair identities are evidence only when they are direct fields on a
        # known sealed repair/Fix record. Repeated aliases on one record are one
        # identity occurrence; conflicting canonical aliases on that same record
        # are never guessed and instead become explicit fail-closed conflicts.
        fix_record = _authorized_fix_record(
            node,
            schema_path=schema_path,
            trusted_scan_id=trusted_scan_id,
            trusted_scan_state=trusted_scan_state,
            trusted_member_ids=trusted_member_ids,
            trusted_membership_state=trusted_membership_state,
        )
        if fix_record:
            record_fixes = _record_strings(node, _fix_container_id_fields(container))
            record_fix_aliases = _record_strings(node, _fix_identity_alias_fields(container))
            if len(record_fix_aliases) > 1:
                conflicting_fixes.update(record_fix_aliases)
            for value in record_fixes:
                fixes.add(value)
                fix_counts[value] = fix_counts.get(value, 0) + 1

            # ``root_cause_id`` on a Fix is only a link. It does not establish a
            # sealed root-cause definition. A nested producer evidence object may
            # establish one only after the existing Stage-3 contract, trusted
            # scan-identity checks, and Handoff-member binding succeed for this
            # exact repair record.
            root_evidence = node.get("root_cause_evidence")
            identity = _verified_root_cause_evidence_identity(
                root_evidence,
                parent_container=container,
                parent_fix=node,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
                trusted_member_ids=trusted_member_ids,
                trusted_membership_state=trusted_membership_state,
            )
            if identity:
                root_id, surface_id = identity
                roots.add(root_id)
                if trusted_scan_state == "verified":
                    grouping_key = f"{trusted_scan_id}\u0000{surface_id}"
                    seen_groups = grouped_root_surfaces.setdefault(root_id, set())
                    if grouping_key not in seen_groups:
                        seen_groups.add(grouping_key)
                        root_counts[root_id] = root_counts.get(root_id, 0) + 1
                else:
                    # Without exact sealed producer identity, repeated equivalent
                    # evidence objects cannot be assumed to belong to one run.
                    root_counts[root_id] = root_counts.get(root_id, 0) + 1

        if schema_path in _ROOT_CAUSE_PATHS:
            record_roots = _record_strings(node, _ROOT_ID_FIELDS | {"id"})
            if len(record_roots) > 1:
                conflicting_roots.update(record_roots)
            for value in record_roots:
                roots.add(value)
                # Each explicit root_causes record is an independent definition.
                # Duplicate explicit definitions remain ambiguous even if their
                # IDs match exactly.
                root_counts[value] = root_counts.get(value, 0) + 1

        for key, child in node.items():
            _collect_refs(
                child,
                container=str(key),
                parent_container=container,
                schema_path=(*schema_path, str(key)),
                fixes=fixes,
                roots=roots,
                fix_counts=fix_counts,
                root_counts=root_counts,
                grouped_root_surfaces=grouped_root_surfaces,
                conflicting_fixes=conflicting_fixes,
                conflicting_roots=conflicting_roots,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
                trusted_member_ids=trusted_member_ids,
                trusted_membership_state=trusted_membership_state,
            )
    elif isinstance(node, list):
        for child in node:
            _collect_refs(
                child,
                container=container,
                parent_container=parent_container,
                schema_path=schema_path,
                fixes=fixes,
                roots=roots,
                fix_counts=fix_counts,
                root_counts=root_counts,
                grouped_root_surfaces=grouped_root_surfaces,
                conflicting_fixes=conflicting_fixes,
                conflicting_roots=conflicting_roots,
                trusted_scan_id=trusted_scan_id,
                trusted_scan_state=trusted_scan_state,
                trusted_member_ids=trusted_member_ids,
                trusted_membership_state=trusted_membership_state,
            )


def build_evidence_set(sealed_l2: dict[str, Any], *, scan_origin: str = "") -> EvidenceSet:
    """Build the offline claimable view of a caller-authenticated snapshot.

    Required seal markers are shape/version inputs, not proof verification. A
    runtime caller must authenticate the exact snapshot first through the
    existing version-aware V8 HMAC verifier.
    """
    if not isinstance(sealed_l2, dict):
        raise EvidenceUnavailable("sealed_l2_missing")
    missing = [field for field in _SEAL_FIELDS if not isinstance(sealed_l2.get(field), str) or not sealed_l2[field].strip()]
    if missing:
        raise EvidenceUnavailable("sealed_l2_markers_missing:" + ",".join(missing))

    origin = scan_origin or scan_evidence_origin(sealed_l2)
    if not origin:
        raise EvidenceUnavailable("sealed_l2_scan_origin_missing")

    trusted_scan_id, trusted_scan_state = _trusted_stage3_scan_identity(sealed_l2)
    trusted_member_ids, trusted_membership_state = _trusted_stage3_fix_membership(
        sealed_l2,
        trusted_scan_state=trusted_scan_state,
    )

    members: set[str] = set()
    live: set[str] = set()
    _collect_urls(
        sealed_l2,
        origin,
        members,
        live,
        trusted_scan_id=trusted_scan_id,
        trusted_scan_state=trusted_scan_state,
        trusted_member_ids=trusted_member_ids,
        trusted_membership_state=trusted_membership_state,
    )

    state_values: dict[str, Scalar] = {}
    numeric_values: dict[str, int | float] = {}
    for path, value in _typed_scalar_values(sealed_l2):
        state_values[path] = value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric_values[path] = value

    fixes: set[str] = set()
    roots: set[str] = set()
    fix_counts: dict[str, int] = {}
    root_counts: dict[str, int] = {}
    grouped_root_surfaces: dict[str, set[str]] = {}
    conflicting_fixes: set[str] = set()
    conflicting_roots: set[str] = set()
    _collect_refs(
        sealed_l2,
        fixes=fixes,
        roots=roots,
        fix_counts=fix_counts,
        root_counts=root_counts,
        grouped_root_surfaces=grouped_root_surfaces,
        conflicting_fixes=conflicting_fixes,
        conflicting_roots=conflicting_roots,
        trusted_scan_id=trusted_scan_id,
        trusted_scan_state=trusted_scan_state,
        trusted_member_ids=trusted_member_ids,
        trusted_membership_state=trusted_membership_state,
    )
    ambiguous_fixes = {ref for ref, count in fix_counts.items() if count > 1}
    ambiguous_roots = {ref for ref, count in root_counts.items() if count > 1}

    fingerprint = _canonical_fingerprint({
        "version": EVIDENCE_SET_VERSION,
        "seal": {field: sealed_l2[field] for field in _SEAL_FIELDS},
        "scan_origin": origin,
        "trusted_stage3_scan_id": trusted_scan_id,
        "trusted_stage3_scan_state": trusted_scan_state,
        "trusted_stage3_membership_state": trusted_membership_state,
        "url_members": sorted(members),
        "live_urls": sorted(live),
        "numeric_values": sorted(numeric_values.items()),
        "state_values": sorted(state_values.items()),
        "fix_refs": sorted(fixes),
        "root_cause_refs": sorted(roots),
        "ambiguous_fix_refs": sorted(ambiguous_fixes),
        "ambiguous_root_cause_refs": sorted(ambiguous_roots),
        "conflicting_fix_refs": sorted(conflicting_fixes),
        "conflicting_root_cause_refs": sorted(conflicting_roots),
    })
    return EvidenceSet(
        version=EVIDENCE_SET_VERSION,
        fingerprint=fingerprint,
        scan_origin=origin,
        url_members=frozenset(members),
        live_urls=frozenset(live),
        numeric_values=MappingProxyType(dict(numeric_values)),
        state_values=MappingProxyType(dict(state_values)),
        fix_refs=frozenset(fixes),
        root_cause_refs=frozenset(roots),
        ambiguous_fix_refs=frozenset(ambiguous_fixes),
        ambiguous_root_cause_refs=frozenset(ambiguous_roots),
        conflicting_fix_refs=frozenset(conflicting_fixes),
        conflicting_root_cause_refs=frozenset(conflicting_roots),
    )


def build_evidence_set_from_authenticated_snapshot(
    sealed_l2: dict[str, Any],
    *,
    authenticate_snapshot,
    scan_origin: str = "",
) -> EvidenceSet:
    """Authenticate the exact snapshot before entering the offline builder.

    The callback is supplied by the future serialized integrator and must wrap
    the existing version-aware authority/HMAC verifier. Only the literal boolean
    ``True`` authorizes construction. The callback receives a private copy, and
    the exact copy must remain canonically unchanged across authentication before
    a second private copy enters the offline builder. Callback errors, mutation,
    and non-JSON snapshot values are converted to a bounded unavailable result so
    verifier details are not exposed.
    """
    if not callable(authenticate_snapshot):
        raise EvidenceUnavailable("sealed_l2_authentication_failed")
    try:
        candidate = deepcopy(sealed_l2)
        before_authentication = _canonical_fingerprint(candidate)
        authenticated = authenticate_snapshot(candidate)
        after_authentication = _canonical_fingerprint(candidate)
    except Exception:
        raise EvidenceUnavailable("sealed_l2_authentication_failed") from None
    if authenticated is not True or before_authentication != after_authentication:
        raise EvidenceUnavailable("sealed_l2_authentication_failed")

    authenticated_origin = scan_evidence_origin(candidate)
    if not authenticated_origin:
        raise EvidenceUnavailable("sealed_l2_authentication_failed")
    if scan_origin:
        supplied_root = published_evidence_url_key("/", scan_origin=scan_origin)
        supplied_origin = supplied_root[:-1] if supplied_root else ""
        if supplied_origin != authenticated_origin:
            raise EvidenceUnavailable("sealed_l2_authentication_failed")

    return build_evidence_set(deepcopy(candidate), scan_origin=authenticated_origin)


def _annotations(model: AIAnnotationV1 | ChatAnswerV1) -> list[AIAnnotationV1]:
    return [model] if isinstance(model, AIAnnotationV1) else list(model.annotations)


def _exact_scalar_equal(left: Scalar, right: Scalar) -> bool:
    # JSON distinguishes integer and fractional numeric provenance in the sealed
    # snapshot. Fail closed rather than accepting Python's ``1 == 1.0`` coercion.
    return type(left) is type(right) and left == right


def render_grounded_annotation_text(_annotation: AIAnnotationV1) -> str:
    """Return the only prose emitted by ``ai_annotation_v1`` today.

    V1 deliberately keeps factual detail in the typed evidence, numeric, Fix,
    root-cause, and state atoms that the verifier can check exactly. Free-form
    prose is a separate semantic channel and cannot be proven by validating
    those arrays alone. Until a versioned deterministic renderer exists for a
    richer claim type, the annotation text is therefore a fixed statement that
    asserts only what the envelope itself proves: grounded evidence is present.
    """
    return DETERMINISTIC_ANNOTATION_TEXT


def _annotation_errors(annotation: AIAnnotationV1, evidence: EvidenceSet) -> list[str]:
    errors: set[str] = set()
    for ref in annotation.evidence:
        key = _url_key(ref.url, evidence.scan_origin)
        if not key or key not in evidence.url_members:
            errors.add("url_not_in_evidence")
        elif ref.require_live and key not in evidence.live_urls:
            errors.add("url_not_live")

    for claim in annotation.numeric_claims:
        if claim.source_ref not in evidence.numeric_values:
            errors.add("numeric_source_missing")
        elif not _exact_scalar_equal(evidence.numeric_values[claim.source_ref], claim.value):
            errors.add("numeric_value_mismatch")

    for ref in annotation.fix_refs:
        if ref in evidence.conflicting_fix_refs:
            errors.add("fix_ref_conflicting_alias")
        elif ref in evidence.ambiguous_fix_refs:
            errors.add("fix_ref_ambiguous")
        elif ref not in evidence.fix_refs:
            errors.add("fix_ref_missing")
    for ref in annotation.root_cause_refs:
        if ref in evidence.conflicting_root_cause_refs:
            errors.add("root_cause_ref_conflicting_alias")
        elif ref in evidence.ambiguous_root_cause_refs:
            errors.add("root_cause_ref_ambiguous")
        elif ref not in evidence.root_cause_refs:
            errors.add("root_cause_ref_missing")

    for claim in annotation.state_claims:
        if claim.source_ref not in evidence.state_values:
            errors.add("state_source_missing")
        elif not _exact_scalar_equal(evidence.state_values[claim.source_ref], claim.value):
            errors.add("state_value_mismatch")

    # Check prose only after every typed atom is independently grounded. This
    # avoids presenting regex/substring inspection as semantic verification and
    # keeps existing attribution errors precise. A fully grounded annotation
    # may emit only the deterministic v1 rendering; arbitrary factual prose is
    # rejected rather than trusted because its arrays happen to be valid.
    if not errors and annotation.text != render_grounded_annotation_text(annotation):
        errors.add("text_not_deterministically_rendered")
    return sorted(errors)


def _conflict_key_value(annotation: AIAnnotationV1):
    for claim in annotation.numeric_claims:
        yield ("numeric", claim.source_ref), claim.value
    for claim in annotation.state_claims:
        yield ("state", claim.source_ref), claim.value


def _has_deterministic_conflict(annotations: list[AIAnnotationV1]) -> bool:
    seen: dict[tuple[str, str], Scalar] = {}
    for annotation in annotations:
        for key, value in _conflict_key_value(annotation):
            if key in seen and not _exact_scalar_equal(seen[key], value):
                return True
            seen[key] = value
    return False


def _schema_version(payload: Any) -> str:
    return str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""


def verify_grounded_payload(
    payload: Any,
    *,
    evidence_set: EvidenceSet | None = None,
    sealed_l2: dict[str, Any] | None = None,
    scan_origin: str = "",
) -> GroundingResult:
    if evidence_set is None:
        if sealed_l2 is None:
            return GroundingResult(status="unavailable", schema_version=_schema_version(payload), reasons=["sealed_l2_unavailable"])
        try:
            evidence_set = build_evidence_set(sealed_l2, scan_origin=scan_origin)
        except EvidenceUnavailable as exc:
            return GroundingResult(status="unavailable", schema_version=_schema_version(payload), reasons=[str(exc)])

    try:
        model = validate_ai_schema(payload)
    except (UnknownAISchemaVersion, ValidationError, ValueError):
        return GroundingResult(
            status="rejected",
            schema_version=_schema_version(payload),
            evidence_fingerprint=evidence_set.fingerprint,
            reasons=["schema_invalid"],
        )

    annotations = _annotations(model)  # type: ignore[arg-type]
    if _has_deterministic_conflict(annotations):
        return GroundingResult(
            status="rejected",
            schema_version=model.schema_version,
            evidence_fingerprint=evidence_set.fingerprint,
            reasons=["deterministic_conflict"],
        )

    invalid: list[tuple[AIAnnotationV1, list[str]]] = []
    valid: list[AIAnnotationV1] = []
    for annotation in annotations:
        errors = _annotation_errors(annotation, evidence_set)
        if errors:
            invalid.append((annotation, errors))
        else:
            valid.append(annotation)

    if not invalid:
        return GroundingResult(
            status="verified",
            schema_version=model.schema_version,
            evidence_fingerprint=evidence_set.fingerprint,
            verified_payload=model.model_dump(mode="python"),
        )

    reasons = sorted({reason for _annotation, errors in invalid for reason in errors})
    if isinstance(model, ChatAnswerV1) and valid:
        redacted = model.model_copy(update={"annotations": valid})
        return GroundingResult(
            status="redacted",
            schema_version=model.schema_version,
            evidence_fingerprint=evidence_set.fingerprint,
            verified_payload=redacted.model_dump(mode="python"),
            redacted_annotation_ids=[annotation.annotation_id for annotation, _errors in invalid],
            reasons=reasons,
        )

    return GroundingResult(
        status="rejected",
        schema_version=model.schema_version,
        evidence_fingerprint=evidence_set.fingerprint,
        reasons=reasons,
    )
