from __future__ import annotations

import unittest

from experiments.provider_lab.grounding import grounding_failures


class GroundingTests(unittest.TestCase):
    def evidence(self) -> dict:
        return {
            "release_gate_eligible": True,
            "scan_id": "scan-1",
            "project_id": "project-1",
            "normalized_domain": "example.com",
            "pages_found": 120,
            "pages_crawled": 100,
            "fix_list": {
                "total_fixes": 4,
                "high_count": 2,
                "medium_count": 2,
            },
            "recommendations": [
                {
                    "fix_id": "fix-1",
                    "affected_pages": ["/a", "/b"],
                    "verified_urls": [
                        {
                            "url": "https://example.com/a",
                            "status_code": 200,
                        },
                        {
                            "url": "https://example.com/broken",
                            "status_code": 404,
                        },
                    ],
                }
            ],
        }

    def test_verified_live_url_and_supported_page_counts_pass(self) -> None:
        failures = grounding_failures(
            "You crawled 100 pages. Start with the 2 pages including https://example.com/a.",
            self.evidence(),
        )
        self.assertEqual(failures["unverified_urls"], [])
        self.assertEqual(failures["unsupported_page_counts"], [])

    def test_invented_or_non_200_url_is_flagged(self) -> None:
        failures = grounding_failures(
            "Edit https://example.com/made-up and https://example.com/broken.",
            self.evidence(),
        )
        self.assertEqual(
            failures["unverified_urls"],
            ["https://example.com/broken", "https://example.com/made-up"],
        )

    def test_unsupported_page_count_is_flagged(self) -> None:
        failures = grounding_failures(
            "There are 37 pages affected.",
            self.evidence(),
        )
        self.assertEqual(failures["unsupported_page_counts"], [37])

    def test_numbers_not_described_as_page_counts_are_not_over_flagged(self) -> None:
        failures = grounding_failures(
            "Use a 301 redirect and verify the result twice.",
            self.evidence(),
        )
        self.assertEqual(failures["unsupported_page_counts"], [])


if __name__ == "__main__":
    unittest.main()
