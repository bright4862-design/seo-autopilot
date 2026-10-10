from __future__ import annotations

import unittest

from experiments.provider_lab.human_rubric import HumanComparison, HumanUsefulnessScore


def score(**overrides) -> HumanUsefulnessScore:
    values = {
        "answers_question_directly": 4,
        "actionable_steps": 4,
        "risk_calibration": 4,
        "evidence_vs_guidance_clarity": 4,
        "conversation_continuity": 4,
        "unnecessary_length": 1,
    }
    values.update(overrides)
    return HumanUsefulnessScore(**values)


class HumanRubricTests(unittest.TestCase):
    def test_net_score_rewards_usefulness_and_penalizes_unnecessary_length(self) -> None:
        concise = score(unnecessary_length=0)
        verbose = score(unnecessary_length=3)
        self.assertGreater(concise.net_score, verbose.net_score)

    def test_candidate_delta_is_relative_to_same_case_baseline(self) -> None:
        comparison = HumanComparison(
            baseline=score(actionable_steps=3),
            candidate=score(actionable_steps=5),
        )
        self.assertEqual(comparison.candidate_delta, 2)
        self.assertTrue(comparison.candidate_not_worse)
        self.assertTrue(comparison.candidate_materially_better)

    def test_small_improvement_is_not_called_material(self) -> None:
        comparison = HumanComparison(
            baseline=score(actionable_steps=3),
            candidate=score(actionable_steps=4),
        )
        self.assertEqual(comparison.candidate_delta, 1)
        self.assertTrue(comparison.candidate_not_worse)
        self.assertFalse(comparison.candidate_materially_better)

    def test_invalid_scores_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            score(answers_question_directly=6)
        with self.assertRaises(ValueError):
            score(unnecessary_length=5)


if __name__ == "__main__":
    unittest.main()
