from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def canonical_json(value: Any) -> str:
    """Return stable JSON for evidence hashing and fixture traceability."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def evidence_sha256(evidence: Mapping[str, Any]) -> str:
    return sha256(canonical_json(dict(evidence)).encode("utf-8")).hexdigest()


def require_authoritative_evidence(evidence: Mapping[str, Any]) -> str:
    """Validate that an offline fixture is eligible for provider evaluation.

    The lab deliberately refuses provisional/non-release evidence so model quality
    is measured against the same authority boundary used by FixList.
    """

    if evidence.get("release_gate_eligible") is not True:
        raise ValueError(
            "Provider Lab fixtures must have release_gate_eligible=true; "
            "provisional or failed scan evidence is not eligible for evaluation."
        )
    return evidence_sha256(evidence)


def _require_non_empty(label: str, value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{label} must be non-empty.")
    return clean


@dataclass(frozen=True)
class ProviderIdentity:
    """Exact identity of one evaluated model endpoint."""

    provider: str
    model_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _require_non_empty("provider", self.provider))
        object.__setattr__(self, "model_id", _require_non_empty("model_id", self.model_id))


@dataclass(frozen=True)
class EvaluationCase:
    """One immutable-by-convention offline evaluation input."""

    case_id: str
    question: str
    evidence: Mapping[str, Any]
    history: tuple[Mapping[str, Any], ...] = ()
    evidence_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _require_non_empty("case_id", self.case_id))
        object.__setattr__(self, "question", _require_non_empty("question", self.question))
        object.__setattr__(self, "evidence_hash", require_authoritative_evidence(self.evidence))


@dataclass(frozen=True)
class EvaluationRecord:
    """Traceable result emitted by the offline evaluator."""

    case_id: str
    provider: str
    model_id: str
    evidence_hash: str
    latency_ms: int
    output_text: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.output_text) and self.error is None
