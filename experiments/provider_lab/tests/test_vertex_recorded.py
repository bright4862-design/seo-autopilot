from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import httpx

from experiments.provider_lab.vertex_recorded import extract_recorded_output, is_retryable_status


def load_production_grok_module():
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "scanner-api" / "app" / "grok_chat.py"
    spec = importlib.util.spec_from_file_location("provider_lab_production_grok_chat", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load production grok_chat.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VertexRecordedParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.production = load_production_grok_module()

    def test_direct_success_shape_matches_production_parser(self) -> None:
        payload = {"output_text": " Grounded answer. "}
        self.assertEqual(
            extract_recorded_output(payload),
            self.production.extract_output_text(payload),
        )

    def test_nested_success_shape_matches_production_parser(self) -> None:
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "First paragraph."},
                        {"type": "output_text", "text": "Second paragraph."},
                    ]
                }
            ]
        }
        self.assertEqual(
            extract_recorded_output(payload),
            self.production.extract_output_text(payload),
        )

    def test_unreadable_shape_raises_same_message(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Grok returned no readable text output"):
            extract_recorded_output({"output": []})
        with self.assertRaisesRegex(RuntimeError, "Grok returned no readable text output"):
            self.production.extract_output_text({"output": []})

    def test_retry_classification_matches_production_for_relevant_statuses(self) -> None:
        for status in (400, 401, 403, 404, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                request = httpx.Request("POST", "https://aiplatform.googleapis.com/test")
                response = httpx.Response(
                    status,
                    request=request,
                    json={"error": {"status": "TEST", "message": "recorded fixture"}},
                )
                production_error = self.production._response_error(response)
                self.assertEqual(is_retryable_status(status), production_error.retryable)


if __name__ == "__main__":
    unittest.main()
