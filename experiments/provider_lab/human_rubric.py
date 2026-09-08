from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HumanUsefulnessScore:
    """Manual product-quality score layered after automatic grounding checks.

    Scores are deliberately human-entered. The lab does not pretend that model
    usefulness can be certified by a self-referential LLM judge alone.
    """

    answers_question_directly: int
    actionable_steps: int
    risk_calibration: int
    evidence_vs_guidance_clarity: int
    conversation_continuity: int
    unnecessary_length: int
    notes: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "answers_question_directly",
            "actionable_steps",
            "risk_calibration",
            "evidence_vs_guidance_clarity",
            "conversation_continuity",
        ):
            value = getattr(self, field_name)
            if value not in {1, 2, 3, 4, 5}:
                raise ValueError(f"{field_name} must be an integer from 1 to 5.")
        if self.unnecessary_length not in {0, 1, 2, 3, 4}:
            raise ValueError("unnecessary_length must be an integer from 0 to 4.")

    @property
    def positive_total(self) -> int:
        return (
            self.answers_question_directly
            + self.actionable_steps
            + self.risk_calibration
            + self.evidence_vs_guidance_clarity
            + self.conversation_continuity
        )

    @property
    def net_score(self) -> int:
        return self.positive_total - self.unnecessary_length


@dataclass(frozen=True)
class HumanComparison:
    baseline: HumanUsefulnessScore
    candidate: HumanUsefulnessScore

    @property
    def candidate_delta(self) -> int:
        return self.candidate.net_score - self.baseline.net_score

    @property
    def candidate_not_worse(self) -> bool:
        return self.candidate_delta >= 0

    @property
    def candidate_materially_better(self) -> bool:
        """Conservative product signal, not an automatic release authorization."""

        return self.candidate_delta >= 2
