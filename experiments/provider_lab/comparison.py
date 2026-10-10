from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import EvaluationCase, EvaluationRecord
from .grounding import grounding_failures
from .offline_eval import OfflineProvider, PromptBuilder, evaluate_case


@dataclass(frozen=True)
class ProviderAssessment:
    record: EvaluationRecord
    unverified_urls: tuple[str, ...]
    unsupported_page_counts: tuple[int, ...]

    @property
    def grounded(self) -> bool:
        return (
            self.record.succeeded
            and not self.unverified_urls
            and not self.unsupported_page_counts
        )


@dataclass(frozen=True)
class ComparisonResult:
    case_id: str
    authority_hash: str
    evidence_hash: str
    baseline: ProviderAssessment
    candidate: ProviderAssessment

    @property
    def candidate_passes_automatic_gate(self) -> bool:
        """Automatic safety gate only; human usefulness scoring is still required."""

        return self.baseline.grounded and self.candidate.grounded

    @property
    def latency_delta_ms(self) -> int:
        return self.candidate.record.latency_ms - self.baseline.record.latency_ms


def _assessment(record: EvaluationRecord, evidence: dict[str, Any]) -> ProviderAssessment:
    failures = (
        grounding_failures(record.output_text or "", evidence)
        if record.succeeded
        else {"unverified_urls": [], "unsupported_page_counts": []}
    )
    return ProviderAssessment(
        record=record,
        unverified_urls=tuple(failures["unverified_urls"]),
        unsupported_page_counts=tuple(failures["unsupported_page_counts"]),
    )


async def compare_case(
    case: EvaluationCase,
    baseline_provider: OfflineProvider,
    candidate_provider: OfflineProvider,
    prompt_builder: PromptBuilder,
) -> ComparisonResult:
    """Compare two providers against one exact immutable case.

    The prompt is built once and reused for both providers so candidate comparison
    cannot accidentally drift because a mutable prompt builder was called twice.
    No network behavior exists here; providers are injected by the caller.
    """

    prompt = prompt_builder(case)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt_builder must return a non-empty string.")
    frozen_prompt = prompt.strip()

    baseline_record = await evaluate_case(
        case,
        baseline_provider,
        lambda _: frozen_prompt,
    )
    candidate_record = await evaluate_case(
        case,
        candidate_provider,
        lambda _: frozen_prompt,
    )

    for record in (baseline_record, candidate_record):
        if record.authority_hash != case.authority_hash:
            raise RuntimeError("comparison record authority hash drifted from evaluation case.")
        if record.evidence_hash != case.evidence_hash:
            raise RuntimeError("comparison record evidence hash drifted from evaluation case.")

    evidence = dict(case.evidence)
    return ComparisonResult(
        case_id=case.case_id,
        authority_hash=case.authority_hash,
        evidence_hash=case.evidence_hash,
        baseline=_assessment(baseline_record, evidence),
        candidate=_assessment(candidate_record, evidence),
    )
