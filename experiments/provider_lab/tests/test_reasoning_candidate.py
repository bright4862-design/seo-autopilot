from __future__ import annotations

from pathlib import Path
import unittest

from experiments.provider_lab.reasoning_candidate import VERTEX_REASONING_CANDIDATE
from experiments.provider_lab.vertex_contract import CURRENT_VERTEX_CONTRACT


class ReasoningCandidateTests(unittest.TestCase):
    def test_reasoning_candidate_changes_only_model_identity(self) -> None:
        baseline = CURRENT_VERTEX_CONTRACT
        candidate = VERTEX_REASONING_CANDIDATE

        self.assertEqual(candidate.identity.provider, baseline.identity.provider)
        self.assertNotEqual(candidate.identity.model_id, baseline.identity.model_id)
        self.assertEqual(candidate.identity.model_id, "xai/grok-4.20-reasoning")
        self.assertEqual(candidate.location, baseline.location)
        self.assertEqual(candidate.max_output_tokens, baseline.max_output_tokens)
        self.assertEqual(candidate.stream, baseline.stream)
        self.assertEqual(candidate.store, baseline.store)
        self.assertEqual(candidate.retryable_status_codes, baseline.retryable_status_codes)

    def test_space_documents_reasoning_but_live_scan_path_routes_through_scanner_chat(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        env_example = (repo_root / "hf-space" / ".env.example").read_text(encoding="utf-8")
        readme = (repo_root / "hf-space" / "README.md").read_text(encoding="utf-8")
        app_source = (repo_root / "hf-space" / "app.py").read_text(encoding="utf-8")

        self.assertIn("GROK_MODEL_ID=xai/grok-4.20-reasoning", env_example)
        self.assertIn("GROK_MODEL_ID=xai/grok-4.20-reasoning", readme)
        self.assertIn('model_id: str = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-non-reasoning").strip()', app_source)
        self.assertIn("if SETTINGS.live_scan_enabled:", app_source)
        self.assertIn('f"{_scanner_base_url()}/chat"', app_source)

    def test_reasoning_candidate_is_not_imported_by_production_runtime(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        production_files = (
            repo_root / "scanner-api" / "app" / "grok_chat.py",
            repo_root / "scanner-api" / "app" / "main.py",
            repo_root / "base44" / "functions" / "grokChat" / "index.ts",
        )
        for path in production_files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("experiments.provider_lab", source)
            self.assertNotIn("VERTEX_REASONING_CANDIDATE", source)


if __name__ == "__main__":
    unittest.main()
