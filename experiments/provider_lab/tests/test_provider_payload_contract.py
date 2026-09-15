from __future__ import annotations

from pathlib import Path
import unittest

from experiments.provider_lab.provider_payload_contract import (
    CANONICAL_V2_FIELDS_NOT_CURRENTLY_SENT,
    validate_provider_payload,
)


class ProviderPayloadContractTests(unittest.TestCase):
    def current_payload(self) -> dict:
        return {
            "release_gate_eligible": True,
            "scan_id": "scan-1",
            "project_id": "project-1",
            "normalized_domain": "example.com",
            "recommendations": [
                {
                    "fix_id": "fix-1",
                    "priority": "high",
                    "verified_urls": [{"url": "https://example.com/page", "status_code": 200}],
                }
            ],
        }

    def test_accepts_current_compact_provider_payload(self) -> None:
        validate_provider_payload(self.current_payload())

    def test_rejects_canonical_v2_fields_that_are_not_in_current_provider_payload(self) -> None:
        for field in sorted(CANONICAL_V2_FIELDS_NOT_CURRENTLY_SENT):
            with self.subTest(field=field):
                payload = self.current_payload()
                payload["recommendations"][0][field] = "unexpected"
                with self.assertRaisesRegex(ValueError, "does not match the current provider payload"):
                    validate_provider_payload(payload)

    def test_current_base44_source_keeps_authority_v2_before_compact_provider_payload(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        authority_source = (
            repo_root / "base44" / "functions" / "grokChat" / "authoritySnapshot.js"
        ).read_text(encoding="utf-8")
        gateway_source = (
            repo_root / "base44" / "functions" / "grokChat" / "index.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated"', authority_source)
        self.assertIn("canonical_action_rank", authority_source)
        self.assertIn("const authoritySnapshot = await assertServerAuthoritySeal", gateway_source)
        self.assertIn("assertAuthoritativeScan(authoritySnapshot.scan)", gateway_source)
        self.assertIn("function buildScanEvidence", gateway_source)
        self.assertIn("priority: cleanText(item.priority, 40)", gateway_source)
        self.assertNotIn("canonical_action_rank: cleanText", gateway_source)

    def test_current_gateway_checks_authority_before_building_provider_evidence(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        source = (
            repo_root / "base44" / "functions" / "grokChat" / "index.ts"
        ).read_text(encoding="utf-8")
        authority_index = source.index("const authoritySnapshot = await assertServerAuthoritySeal")
        build_call_index = source.index("scan: buildScanEvidence")
        self.assertLess(authority_index, build_call_index)


if __name__ == "__main__":
    unittest.main()
