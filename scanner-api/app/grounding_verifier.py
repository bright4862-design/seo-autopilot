"""Deterministic fail-closed grounding for future FixList AI output.

This module does not call a model, crawl the web, persist data, rank repairs, or
create authority. It verifies strict AI envelopes against a read-only EvidenceSet
built from an already sealed L2 snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .ai_schemas import AIAnnotationV1, ChatAnswerV1, UnknownAISchemaVersion, validate_ai_schema
from .repair_coverage import published_evidence_url_key, scan_evidence_origin

EVIDENCE_SET_VERSION = "ai_evidence_set_v1"
GROUNDING_VERIFIER_VERSION = "grounding_verifier_v1"

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


def _walk(value: Any, path: str = "$", containers: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            name = str(key)
            yield from _walk(child, _path(path, name), containers + (name,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, _path(path, index), containers)
    else:
        yield path, value, containers


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not (
        isinstance(value, float) and not isfinite(value)
    )


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
    evidence_scope: bool = False,
) -> None:
    if isinstance(node, dict):
        page_record = container in _PAGE_CONTAINERS
        evidence_record = container in _FIX_CONTAINERS or container in _ROOT_CONTAINERS
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
            # Evidence scope is never inherited merely because an ancestor was a
            # Fix/root-cause record. Only explicit evidence-shaped child
            # containers may carry citation membership deeper into the tree.
            # Generic ``details`` is intentionally root-only; permitting it on a
            # Fix would let prose/diagnostic metadata launder arbitrary URLs.
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
                evidence_scope=child_scope,
            )
    elif isinstance(node, list):
        for child in node:
            _collect_urls(
                child,
                scan_origin,
                members,
                live,
                container=container,
                evidence_scope=evidence_scope,
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
    fixes: set[str],
    roots: set[str],
    fix_counts: dict[str, int],
    root_counts: dict[str, int],
    conflicting_fixes: set[str],
    conflicting_roots: set[str],
) -> None:
    if isinstance(node, dict):
        # Repair identities are evidence only when they are direct fields on a
        # known sealed repair/Fix record. Repeated aliases on one record are one
        # identity occurrence; conflicting aliases on that same record are never
        # guessed and instead become explicit fail-closed conflicts.
        if container in _FIX_CONTAINERS:
            record_fixes = _record_strings(node, _fix_container_id_fields(container))
            if len(record_fixes) > 1:
                conflicting_fixes.update(record_fixes)
            for value in record_fixes:
                fixes.add(value)
                fix_counts[value] = fix_counts.get(value, 0) + 1

            # ``root_cause_id`` on a Fix is only a link. It does not establish a
            # sealed root-cause definition and therefore cannot authorize an AI
            # root_cause_ref by itself. A definition must appear in a recognized
            # root-cause evidence container below or elsewhere in sealed L2.

        if container in _ROOT_CONTAINERS:
            record_roots = _record_strings(node, _ROOT_ID_FIELDS | {"id"})
            if len(record_roots) > 1:
                conflicting_roots.update(record_roots)
            for value in record_roots:
                roots.add(value)
                root_counts[value] = root_counts.get(value, 0) + 1

        for key, child in node.items():
            _collect_refs(
                child,
                container=str(key),
                fixes=fixes,
                roots=roots,
                fix_counts=fix_counts,
                root_counts=root_counts,
                conflicting_fixes=conflicting_fixes,
                conflicting_roots=conflicting_roots,
            )
    elif isinstance(node, list):
        for child in node:
            _collect_refs(
                child,
                container=container,
                fixes=fixes,
                roots=roots,
                fix_counts=fix_counts,
                root_counts=root_counts,
                conflicting_fixes=conflicting_fixes,
                conflicting_roots=conflicting_roots,
            )


def build_evidence_set(sealed_l2: dict[str, Any], *, scan_origin: str = "") -> EvidenceSet:
    if not isinstance(sealed_l2, dict):
        raise EvidenceUnavailable("sealed_l2_missing")
    missing = [field for field in _SEAL_FIELDS if not isinstance(sealed_l2.get(field), str) or not sealed_l2[field].strip()]
    if missing:
        raise EvidenceUnavailable("sealed_l2_markers_missing:" + ",".join(missing))

    origin = scan_origin or scan_evidence_origin(sealed_l2)
    if not origin:
        raise EvidenceUnavailable("sealed_l2_scan_origin_missing")

    members: set[str] = set()
    live: set[str] = set()
    _collect_urls(sealed_l2, origin, members, live)

    state_values: dict[str, Scalar] = {}
    numeric_values: dict[str, int | float] = {}
    for path, value, _containers in _walk(sealed_l2):
        if not _scalar(value):
            continue
        state_values[path] = value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric_values[path] = value

    fixes: set[str] = set()
    roots: set[str] = set()
    fix_counts: dict[str, int] = {}
    root_counts: dict[str, int] = {}
    conflicting_fixes: set[str] = set()
    conflicting_roots: set[str] = set()
    _collect_refs(
        sealed_l2,
        fixes=fixes,
        roots=roots,
        fix_counts=fix_counts,
        root_counts=root_counts,
        conflicting_fixes=conflicting_fixes,
        conflicting_roots=conflicting_roots,
    )
    ambiguous_fixes = {ref for ref, count in fix_counts.items() if count > 1}
    ambiguous_roots = {ref for ref, count in root_counts.items() if count > 1}

    fingerprint = _canonical_fingerprint({
        "version": EVIDENCE_SET_VERSION,
        "seal": {field: sealed_l2[field] for field in _SEAL_FIELDS},
        "scan_origin": origin,
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


def _annotations(model: AIAnnotationV1 | ChatAnswerV1) -> list[AIAnnotationV1]:
    return [model] if isinstance(model, AIAnnotationV1) else list(model.annotations)


def _exact_scalar_equal(left: Scalar, right: Scalar) -> bool:
    # JSON distinguishes integer and fractional numeric provenance in the sealed
    # snapshot. Fail closed rather than accepting Python's ``1 == 1.0`` coercion.
    return type(left) is type(right) and left == right


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
