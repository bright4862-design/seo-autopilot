from __future__ import annotations

from pathlib import Path
import unittest

from experiments.provider_lab.vertex_contract import CURRENT_VERTEX_CONTRACT


class VertexContractTests(unittest.TestCase):
    def test_snapshot_matches_current_transport_defaults(self) -> None:
        contract = CURRENT_VERTEX_CONTRACT

        self.assertEqual(contract.identity.provider, "vertex-ai")
        self.assertEqual(contract.identity.model_id, "xai/grok-4.20-non-reasoning")
        self.assertEqual(contract.location, "global")
        self.assertEqual(contract.max_output_tokens, 1_600)
        self.assertFalse(contract.stream)
        self.assertFalse(contract.store)
        self.assertEqual(contract.retryable_status_codes, frozenset({429, 500, 502, 503, 504}))

    def test_payload_shape_matches_current_grok_request_contract(self) -> None:
        payload = CURRENT_VERTEX_CONTRACT.payload_for_prompt("grounded prompt")

        self.assertEqual(
            payload,
            {
                "model": "xai/grok-4.20-non-reasoning",
                "input": "grounded prompt",
                "max_output_tokens": 1_600,
                "stream": False,
                "store": False,
            },
        )

    def test_snapshot_is_guarded_against_production_contract_drift(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        production_source = (repo_root / "scanner-api" / "app" / "grok_chat.py").read_text(
            encoding="utf-8"
        )

        expected_fragments = (
            'GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-non-reasoning").strip()',
            'GROK_LOCATION = os.getenv("VERTEX_LOCATION", "global").strip() or "global"',
            'RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})',
            '"max_output_tokens": 1_600',
            '"stream": False',
            '"store": False',
        )
        for fragment in expected_fragments:
            self.assertIn(fragment, production_source)

    def test_empty_prompt_is_rejected_before_any_provider_adapter(self) -> None:
        with self.assertRaisesRegex(ValueError, "prompt must be non-empty"):
            CURRENT_VERTEX_CONTRACT.payload_for_prompt("   ")


if __name__ == "__main__":
    unittest.main()
