from __future__ import annotations

from pathlib import Path
import unittest

from experiments.provider_lab.contracts import (
    EvaluationCase,
    ProviderIdentity,
    evidence_sha256,
)
from experiments.provider_lab.offline_eval import evaluate_case


class FakeProvider:
    def __init__(self, provider: str = "vertex", model_id: str = "fake-model") -> None:
        self.identity = ProviderIdentity(provider=provider, model_id=model_id)

    async def generate(self, prompt: str) -> str:
        return f"answer for: {prompt}"


class FailingProvider:
    identity = ProviderIdentity(provider="hf-test", model_id="candidate-model")

    async def generate(self, prompt: str) -> str:
        raise RuntimeError("simulated upstream failure\nwith extra detail")


class ProviderLabContractTests(unittest.IsolatedAsyncioTestCase):
    def authoritative_case(self) -> EvaluationCase:
        return EvaluationCase(
            case_id="case-001",
            question="What should I fix first?",
            evidence={
                "scan_id": "fixture-scan",
                "release_gate_eligible": True,
                "pages_crawled": 12,
            },
        )

    def test_rejects_non_authoritative_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "release_gate_eligible=true"):
            EvaluationCase(
                case_id="case-provisional",
                question="What should I fix?",
                evidence={"release_gate_eligible": False},
            )

    def test_evidence_hash_is_deterministic_across_key_order(self) -> None:
        left = {"release_gate_eligible": True, "pages_crawled": 12, "scan_id": "x"}
        right = {"scan_id": "x", "pages_crawled": 12, "release_gate_eligible": True}
        self.assertEqual(evidence_sha256(left), evidence_sha256(right))

    async def test_record_carries_exact_provider_model_and_evidence_identity(self) -> None:
        case = self.authoritative_case()
        record = await evaluate_case(case, FakeProvider(), lambda item: item.question)

        self.assertTrue(record.succeeded)
        self.assertEqual(record.provider, "vertex")
        self.assertEqual(record.model_id, "fake-model")
        self.assertEqual(record.evidence_hash, case.evidence_hash)
        self.assertIn("What should I fix first?", record.output_text or "")
        self.assertIsNone(record.error)

    async def test_provider_failure_is_bounded_and_stays_in_record(self) -> None:
        record = await evaluate_case(
            self.authoritative_case(),
            FailingProvider(),
            lambda item: item.question,
        )

        self.assertFalse(record.succeeded)
        self.assertIsNone(record.output_text)
        self.assertEqual(record.provider, "hf-test")
        self.assertEqual(record.model_id, "candidate-model")
        self.assertIn("RuntimeError: simulated upstream failure with extra detail", record.error or "")
        self.assertNotIn("\n", record.error or "")
        self.assertLessEqual(len(record.error or ""), 420)

    def test_phase_one_lab_has_no_network_or_cloud_sdk_imports(self) -> None:
        lab_root = Path(__file__).resolve().parents[1]
        forbidden = (
            "import httpx",
            "import requests",
            "import socket",
            "from google.auth",
            "import huggingface_hub",
            "from huggingface_hub",
            "import openai",
            "from openai",
        )
        for filename in ("contracts.py", "offline_eval.py"):
            source = (lab_root / filename).read_text(encoding="utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, source, f"{filename} unexpectedly imports {needle}")

    def test_production_scanner_image_does_not_copy_provider_lab(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        dockerfile = (repo_root / "scanner-api" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("COPY app ./app", dockerfile)
        self.assertNotIn("provider_lab", dockerfile)
        self.assertNotIn("experiments", dockerfile)


if __name__ == "__main__":
    unittest.main()
