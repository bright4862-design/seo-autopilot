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

_URL_FIELDS = frozenset({
    "url", "final_url", "canonical_url", "source_url", "destination_url",
    "evidence_url", "requested_url",
})
_URL_LIST_FIELDS = frozenset({"affected_urls", "evidence_urls", "verified_urls", "urls", "evidence_refs"})
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


def _collect_urls(node: Any, scan_origin: str, members: set[str], live: set[str]) -> None:
    if isinstance(node, dict):
        for field in _URL_FIELDS:
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
        status = node.get("status_code")
        if isinstance(status, int) and not isinstance(status, bool) and 200 <= status < 400:
            for field in ("final_url", "url"):
                key = _url_key(node.get(field), scan_origin)
                if key:
                    members.add(key)
                    live.add(key)
                    break
        for child in node.values():
            _collect_urls(child, scan_origin, members, live)
    elif isinstance(node, list):
        for child in node:
            _collect_urls(child, scan_origin, members, live)


def _collect_refs(node: Any, *, container: str = "", fixes: set[str], roots: set[str]) -> None:
    if isinstance(node, dict):
        if container in _FIX_CONTAINERS:
            for field in _FIX_ID_FIELDS | {"id"}:
                value = node.get(field)
                if isinstance(value, str) and value.strip():
                    fixes.add(value.strip())
        if container in _ROOT_CONTAINERS:
            for field in _ROOT_ID_FIELDS | {"id"}:
                value = node.get(field)
                if isinstance(value, str) and value.strip():
                    roots.add(value.strip())
        for field in _FIX_ID_FIELDS:
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                fixes.add(value.strip())
        for field in _ROOT_ID_FIELDS:
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                roots.add(value.strip())
        for key, child in node.items():
            _collect_refs(child, container=str(key), fixes=fixes, roots=roots)
    elif isinstance(node, list):
        for child in node:
            _collect_refs(child, container=container, fixes=fixes, roots=roots)


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
    _collect_refs(sealed_l2, fixes=fixes, roots=roots)

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
    )


def _annotations(model: AIAnnotationV1 | ChatAnswerV1) -> list[AIAnnotationV1]:
    return [model] if isinstance(model, AIAnnotationV1) else list(model.annotations)


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
        elif evidence.numeric_values[claim.source_ref] != claim.value:
            errors.add("numeric_value_mismatch")

    for ref in annotation.fix_refs:
        if ref not in evidence.fix_refs:
            errors.add("fix_ref_missing")
    for ref in annotation.root_cause_refs:
        if ref not in evidence.root_cause_refs:
            errors.add("root_cause_ref_missing")

    for claim in annotation.state_claims:
        if claim.source_ref not in evidence.state_values:
            errors.add("state_source_missing")
        elif evidence.state_values[claim.source_ref] != claim.value:
            errors.add("state_value_mismatch")
    return sorted(errors)


def _conflict_key_value(annotation: AIAnnotationV1):
    for claim in annotation.numeric_claims:
        yield ("numeric", claim.source_ref), claim.value
    for claim in annotation.state_claims:
        yield ("state", claim.source_ref), claim.value


def _has_deterministic_conflict(annotations: list[AIAnnotationV1]) -> bool:
    seen: dict[tuple[str, str], Any] = {}
    for annotation in annotations:
        for key, value in _conflict_key_value(annotation):
            if key in seen and seen[key] != value:
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
