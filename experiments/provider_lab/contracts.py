from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_v1"
REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated"
REPAIR_PRIORITY_MODEL_V2 = "repair_priority_v2_technical_severity"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_non_empty(label: str, value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{label} must be non-empty.")
    return clean


@dataclass(frozen=True)
class AuthorityManifest:
    """Offline provenance assertion for an already-verified FixList snapshot.

    This does not verify HMACs. Production Base44 remains the only authority
    verifier. The lab requires an explicit manifest so a raw provider payload can
    never be mistaken for proof of authority.
    """

    scan_id: str
    release_fingerprint: str
    authority_seal_version: str = REVIEW_ATTESTATION_VERSION
    authority_verified: bool = True
    scan_status: str = "complete"
    release_gate_eligible: bool = True
    score_is_provisional: bool = False
    evidence_quality_blocking: bool = False
    repair_contract_version: str = ""
    repair_snapshot_contract_version: str = ""
    repair_snapshot_contract_complete: bool = False
    repair_priority_model_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "scan_id", _require_non_empty("scan_id", self.scan_id))
        object.__setattr__(
            self,
            "release_fingerprint",
            _require_non_empty("release_fingerprint", self.release_fingerprint),
        )
        if self.authority_seal_version != REVIEW_ATTESTATION_VERSION:
            raise ValueError("authority_seal_version does not match the current server authority contract.")
        if self.authority_verified is not True:
            raise ValueError("authority_verified must be true before provider evaluation.")
        if self.scan_status != "complete":
            raise ValueError("provider evaluation requires scan_status=complete.")
        if self.release_gate_eligible is not True:
            raise ValueError("provider evaluation requires release_gate_eligible=true.")
        if self.score_is_provisional:
            raise ValueError("provisional scan evidence is not eligible for provider evaluation.")
        if self.evidence_quality_blocking:
            raise ValueError("evidence_quality_blocking scan evidence is not eligible for provider evaluation.")
        self._validate_repair_contract()

    def _validate_repair_contract(self) -> None:
        values_present = any(
            (
                self.repair_contract_version,
                self.repair_snapshot_contract_version,
                self.repair_snapshot_contract_complete,
                self.repair_priority_model_version,
            )
        )
        if not values_present:
            return  # valid legacy authoritative snapshot
        if (
            self.repair_contract_version != REPAIR_CONTRACT_V2
            or self.repair_snapshot_contract_version != REPAIR_CONTRACT_V2
            or self.repair_snapshot_contract_complete is not True
            or self.repair_priority_model_version != REPAIR_PRIORITY_MODEL_V2
        ):
            raise ValueError("mixed or incomplete repair-v2 authority manifest is not eligible for evaluation.")

    @property
    def repair_mode(self) -> str:
        return "repair_v2" if self.repair_snapshot_contract_complete else "legacy"

    @property
    def authority_hash(self) -> str:
        return sha256_json(asdict(self))


@dataclass(frozen=True)
class ProviderIdentity:
    provider: str
    model_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _require_non_empty("provider", self.provider))
        object.__setattr__(self, "model_id", _require_non_empty("model_id", self.model_id))


@dataclass(frozen=True)
class EvaluationCase:
    """One offline case: verified authority provenance + actual provider payload."""

    case_id: str
    question: str
    authority: AuthorityManifest
    evidence: Mapping[str, Any]
    history: tuple[Mapping[str, Any], ...] = ()
    evidence_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _require_non_empty("case_id", self.case_id))
        object.__setattr__(self, "question", _require_non_empty("question", self.question))
        if self.evidence.get("release_gate_eligible") is not True:
            raise ValueError("provider payload must have release_gate_eligible=true.")
        evidence_scan_id = str(self.evidence.get("scan_id") or "").strip()
        if not evidence_scan_id:
            raise ValueError("provider payload must include scan_id.")
        if evidence_scan_id != self.authority.scan_id:
            raise ValueError("provider payload scan_id does not match authority manifest.")
        object.__setattr__(self, "evidence_hash", sha256_json(dict(self.evidence)))

    @property
    def authority_hash(self) -> str:
        return self.authority.authority_hash


@dataclass(frozen=True)
class EvaluationRecord:
    case_id: str
    provider: str
    model_id: str
    authority_hash: str
    evidence_hash: str
    latency_ms: int
    output_text: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.output_text) and self.error is None
