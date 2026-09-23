from __future__ import annotations

import unittest

from experiments.provider_lab.evaluation_manifest import (
    MANIFEST_VERSION,
    build_manifest,
    manifest_json,
    manifest_sha256,
)


class EvaluationManifestTests(unittest.TestCase):
    def test_manifest_freezes_baseline_candidate_and_case_hashes(self) -> None:
        manifest = build_manifest()
        self.assertEqual(manifest["manifest_version"], MANIFEST_VERSION)
        self.assertEqual(manifest["baseline"]["provider"], "vertex-ai")
        self.assertEqual(
            manifest["baseline"]["model_id"],
            "xai/grok-4.20-non-reasoning",
        )
        self.assertEqual(manifest["candidate"]["provider"], "vertex-ai")
        self.assertEqual(
            manifest["candidate"]["model_id"],
            "xai/grok-4.20-reasoning",
        )
        self.assertEqual(len(manifest["cases"]), 6)
        for case in manifest["cases"]:
            self.assertEqual(len(case["authority_hash"]), 64)
            self.assertEqual(len(case["evidence_hash"]), 64)

    def test_manifest_is_deterministic(self) -> None:
        self.assertEqual(manifest_json(), manifest_json())
        self.assertEqual(manifest_sha256(), manifest_sha256())
        self.assertEqual(len(manifest_sha256()), 64)

    def test_follow_up_case_records_history_turns(self) -> None:
        manifest = build_manifest()
        followup = next(
            item for item in manifest["cases"] if item["case_id"] == "follow-up-context"
        )
        self.assertEqual(followup["history_turns"], 2)


if __name__ == "__main__":
    unittest.main()
