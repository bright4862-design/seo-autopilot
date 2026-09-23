from __future__ import annotations

from pathlib import Path
import unittest

from experiments.provider_lab.contracts import (
    AuthorityManifest,
    EvaluationCase,
    ProviderIdentity,
    REPAIR_CONTRACT_V2,
    REPAIR_PRIORITY_MODEL_V2,
)
from experiments.provider_lab.offline_eval import evaluate_case
from experiments.provider_lab.provider_payload_contract import validate_provider_payload


class FakeProvider:
    def __init__(self, provider: str = "vertex", model_id: str = "fake-model") -> None:
        self.identity = ProviderIdentity(provider=provider, model_id=model_id)

    async def generate(self, prompt: str) -> str:
        return f"answer for: {prompt}"


class FailingProvider:
    identity = ProviderIdentity(provider="hf-test", model_id="candidate-model")

    async def generate(self, prompt: str) -> str:
        raise RuntimeError("simulated upstream failure\nwith extra detail")


def current_v2_authority(scan_id: str = "fixture-scan") -> AuthorityManifest:
    return AuthorityManifest(
        scan_id=scan_id,
        release_fingerprint="51c813a6219b4e70",
        repair_contract_version=REPAIR_CONTRACT_V2,
        repair_snapshot_contract_version=REPAIR_CONTRACT_V2,
        repair_snapshot_contract_complete=True,
        repair_priority_model_version=REPAIR_PRIORITY_MODEL_V2,
    )


def provider_evidence(scan_id: str = "fixture-scan") -> dict:
    return {
        "release_gate_eligible": True,
        "scan_id": scan_id,
        "project_id": "project-1",
        "normalized_domain": "example.com",
        "pages_crawled": 12,
        "project": {"website_url": "https://example.com"},
        "fix_list": {"total_fixes": 1},
        "recommendations": [
            {
                "fix_id": "fix-1",
                "rule": "missing_title",
                "priority": "high",
                "verified_urls": [{"url": "https://example.com/page", "status_code": 200}],
            }
        ],
    }


class ProviderLabContractTests(unittest.IsolatedAsyncioTestCase):
    def authoritative_case(self) -> EvaluationCase:
        evidence = provider_evidence()
        validate_provider_payload(evidence)
        return EvaluationCase(
            case_id="case-001",
            question="What should I fix first?",
            authority=current_v2_authority(),
            evidence=evidence,
        )

    def test_accepts_current_repair_v2_authority_manifest(self) -> None:
        manifest = current_v2_authority()
        self.assertEqual(manifest.repair_mode, "repair_v2")
        self.assertEqual(len(manifest.authority_hash), 64)

    def test_accepts_legacy_already_authoritative_manifest(self) -> None:
        manifest = AuthorityManifest(
            scan_id="legacy-scan",
            release_fingerprint="51c813a6219b4e70",
        )
        self.assertEqual(manifest.repair_mode, "legacy")

    def test_rejects_mixed_or_partial_repair_v2_manifest(self) -> None:
        with self.assertRaisesRegex(ValueError, "mixed or incomplete repair-v2"):
            AuthorityManifest(
                scan_id="mixed-scan",
                release_fingerprint="51c813a6219b4e70",
                repair_contract_version=REPAIR_CONTRACT_V2,
            )

    def test_rejects_non_authoritative_scan_states(self) -> None:
        bad_cases = (
            {"authority_verified": False},
            {"scan_status": "failed"},
            {"release_gate_eligible": False},
            {"score_is_provisional": True},
            {"evidence_quality_blocking": True},
        )
        for overrides in bad_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    AuthorityManifest(
                        scan_id="bad-scan",
                        release_fingerprint="51c813a6219b4e70",
                        **overrides,
                    )

    def test_provider_payload_identity_must_match_authority(self) -> None:
        with self.assertRaisesRegex(ValueError, "scan_id does not match"):
            EvaluationCase(
                case_id="mismatch",
                question="What should I fix?",
                authority=current_v2_authority("scan-a"),
                evidence=provider_evidence("scan-b"),
            )

    async def test_record_carries_provider_authority_and_evidence_identity(self) -> None:
        case = self.authoritative_case()
        record = await evaluate_case(case, FakeProvider(), lambda item: item.question)

        self.assertTrue(record.succeeded)
        self.assertEqual(record.provider, "vertex")
        self.assertEqual(record.model_id, "fake-model")
        self.assertEqual(record.authority_hash, case.authority_hash)
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

    def test_lab_runtime_modules_have_no_network_or_cloud_sdk_imports(self) -> None:
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
        for filename in (
            "contracts.py",
            "offline_eval.py",
            "provider_payload_contract.py",
            "vertex_contract.py",
        ):
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
