from __future__ import annotations

import unittest

from experiments.provider_lab.fixtures import representative_cases
from experiments.provider_lab.grounding import verified_urls


class RepresentativeFixtureTests(unittest.TestCase):
    def test_fixture_pack_covers_planned_evaluation_categories(self) -> None:
        cases = representative_cases()
        ids = {item.case_id for item in cases}
        self.assertEqual(
            ids,
            {
                "redirects-internal-links",
                "metadata-content",
                "indexability-robots",
                "canonical-structured-data",
                "no-high-confidence-findings",
                "follow-up-context",
            },
        )

    def test_fixture_hashes_are_unique_and_traceable(self) -> None:
        cases = representative_cases()
        authority_hashes = {item.authority_hash for item in cases}
        evidence_hashes = {item.evidence_hash for item in cases}
        self.assertEqual(len(authority_hashes), len(cases))
        self.assertEqual(len(evidence_hashes), len(cases))
        self.assertTrue(all(len(value) == 64 for value in authority_hashes))
        self.assertTrue(all(len(value) == 64 for value in evidence_hashes))

    def test_every_fixture_is_current_repair_v2_authority(self) -> None:
        for item in representative_cases():
            with self.subTest(case_id=item.case_id):
                self.assertEqual(item.authority.repair_mode, "repair_v2")
                self.assertTrue(item.authority.release_gate_eligible)
                self.assertFalse(item.authority.score_is_provisional)
                self.assertFalse(item.authority.evidence_quality_blocking)

    def test_all_fixture_urls_marked_live_are_status_200_verified(self) -> None:
        for item in representative_cases():
            with self.subTest(case_id=item.case_id):
                for recommendation in item.evidence.get("recommendations", []) or []:
                    for entry in recommendation.get("verified_urls", []) or []:
                        self.assertEqual(int(entry.get("status_code") or 0), 200)
                self.assertTrue(
                    all(url.startswith("https://") for url in verified_urls(item.evidence))
                )

    def test_no_findings_fixture_has_no_recommendations(self) -> None:
        case = next(
            item for item in representative_cases()
            if item.case_id == "no-high-confidence-findings"
        )
        self.assertEqual(case.evidence["recommendations"], [])
        self.assertTrue(case.evidence["fix_list"]["no_high_confidence_findings"])

    def test_follow_up_fixture_preserves_conversation_context(self) -> None:
        case = next(
            item for item in representative_cases()
            if item.case_id == "follow-up-context"
        )
        self.assertEqual(len(case.history), 2)
        self.assertEqual(case.history[0]["role"], "user")
        self.assertEqual(case.history[1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
