from __future__ import annotations

import unittest

from experiments.provider_lab.comparison import compare_case
from experiments.provider_lab.contracts import (
    AuthorityManifest,
    EvaluationCase,
    ProviderIdentity,
    REPAIR_CONTRACT_V2,
    REPAIR_PRIORITY_MODEL_V2,
)


class CapturingProvider:
    def __init__(self, model_id: str, output: str) -> None:
        self.identity = ProviderIdentity(provider="vertex-ai", model_id=model_id)
        self.output = output
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.output


def case() -> EvaluationCase:
    return EvaluationCase(
        case_id="comparison-1",
        question="What should I fix first?",
        authority=AuthorityManifest(
            scan_id="scan-1",
            release_fingerprint="51c813a6219b4e70",
            repair_contract_version=REPAIR_CONTRACT_V2,
            repair_snapshot_contract_version=REPAIR_CONTRACT_V2,
            repair_snapshot_contract_complete=True,
            repair_priority_model_version=REPAIR_PRIORITY_MODEL_V2,
        ),
        evidence={
            "release_gate_eligible": True,
            "scan_id": "scan-1",
            "project_id": "project-1",
            "normalized_domain": "example.com",
            "pages_found": 120,
            "pages_crawled": 100,
            "recommendations": [
                {
                    "fix_id": "fix-1",
                    "priority": "high",
                    "affected_pages": ["/a", "/b"],
                    "verified_urls": [
                        {"url": "https://example.com/a", "status_code": 200}
                    ],
                }
            ],
        },
    )


class ComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_baseline_and_candidate_receive_identical_frozen_prompt(self) -> None:
        baseline = CapturingProvider(
            "xai/grok-4.20-non-reasoning",
            "Start with the 2 pages including https://example.com/a.",
        )
        candidate = CapturingProvider(
            "xai/grok-4.20-reasoning",
            "Start with the 2 pages including https://example.com/a.",
        )
        prompt_calls = 0

        def prompt_builder(item: EvaluationCase) -> str:
            nonlocal prompt_calls
            prompt_calls += 1
            return f"question={item.question}; evidence={item.evidence_hash}"

        result = await compare_case(case(), baseline, candidate, prompt_builder)

        self.assertEqual(prompt_calls, 1)
        self.assertEqual(baseline.prompts, candidate.prompts)
        self.assertEqual(len(baseline.prompts), 1)
        self.assertTrue(result.baseline.grounded)
        self.assertTrue(result.candidate.grounded)
        self.assertTrue(result.candidate_passes_automatic_gate)
        self.assertEqual(result.authority_hash, result.baseline.record.authority_hash)
        self.assertEqual(result.evidence_hash, result.candidate.record.evidence_hash)

    async def test_candidate_with_invented_url_fails_automatic_grounding_gate(self) -> None:
        baseline = CapturingProvider(
            "xai/grok-4.20-non-reasoning",
            "Review https://example.com/a first.",
        )
        candidate = CapturingProvider(
            "xai/grok-4.20-reasoning",
            "Review https://example.com/invented first.",
        )

        result = await compare_case(case(), baseline, candidate, lambda item: item.question)

        self.assertTrue(result.baseline.grounded)
        self.assertFalse(result.candidate.grounded)
        self.assertFalse(result.candidate_passes_automatic_gate)
        self.assertEqual(
            result.candidate.unverified_urls,
            ("https://example.com/invented",),
        )

    async def test_candidate_with_unsupported_page_count_fails_automatic_gate(self) -> None:
        baseline = CapturingProvider(
            "xai/grok-4.20-non-reasoning",
            "The scan crawled 100 pages.",
        )
        candidate = CapturingProvider(
            "xai/grok-4.20-reasoning",
            "There are 37 pages affected.",
        )

        result = await compare_case(case(), baseline, candidate, lambda item: item.question)

        self.assertFalse(result.candidate_passes_automatic_gate)
        self.assertEqual(result.candidate.unsupported_page_counts, (37,))

    async def test_candidate_failure_is_not_mistaken_for_safe_grounded_output(self) -> None:
        baseline = CapturingProvider(
            "xai/grok-4.20-non-reasoning",
            "Review https://example.com/a first.",
        )

        class FailingProvider(CapturingProvider):
            async def generate(self, prompt: str) -> str:
                self.prompts.append(prompt)
                raise TimeoutError("recorded reasoning timeout")

        candidate = FailingProvider("xai/grok-4.20-reasoning", "")
        result = await compare_case(case(), baseline, candidate, lambda item: item.question)

        self.assertTrue(result.baseline.grounded)
        self.assertFalse(result.candidate.record.succeeded)
        self.assertFalse(result.candidate.grounded)
        self.assertFalse(result.candidate_passes_automatic_gate)
        self.assertIn("TimeoutError", result.candidate.record.error or "")


if __name__ == "__main__":
    unittest.main()
