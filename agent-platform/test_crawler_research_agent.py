from pathlib import Path
import tempfile
import unittest

import crawler_research_agent as cra


class CrawlerResearchAgentTests(unittest.TestCase):
    def test_license_policy_is_conservative(self):
        self.assertIn("permissive", cra._license_mode("MIT"))
        self.assertEqual(cra._license_mode("GPL-3.0"), "ideas_only_no_code_copy")
        self.assertEqual(cra._license_mode(""), "unknown_license_ideas_only")

    def test_pattern_detection_finds_retry_and_trap_controls(self):
        text = """
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            await exponential_backoff(retry_after)
        # soft-404 crawler trap and repeating path segment guard
        if 'utm_' in url or 'e-page-' in url:
            return
        """
        hits = cra._pattern_hits(text)
        self.assertGreater(hits.get("retry_backoff", 0), 0)
        self.assertGreater(hits.get("crawler_trap_protection", 0), 0)

    def test_source_path_ranking_prefers_crawler_code(self):
        self.assertGreaterEqual(cra._source_path_score("src/crawler/frontier.py"), 2)
        self.assertLess(cra._source_path_score("docs/logo.png"), 0)

    def test_local_capability_scan_detects_existing_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scanner.py"
            path.write_text("robots.txt sitemap.xml canonical redirect_chain", encoding="utf-8")
            hits = cra._local_capabilities(tmp)
        self.assertGreater(hits.get("robots_and_sitemaps", 0), 0)
        self.assertGreater(hits.get("canonical_redirect_validation", 0), 0)

    def test_recommendations_emit_only_public_gaps(self):
        public = {
            "retry_backoff": 3,
            "crawler_trap_protection": 2,
            "link_graph": 1,
        }
        local = {"link_graph": 2}
        recs = cra.FixListCrawlerResearchAgent._recommendations(public, local)
        caps = [item["capability"] for item in recs]
        self.assertIn("retry_backoff", caps)
        self.assertIn("crawler_trap_protection", caps)
        self.assertNotIn("link_graph", caps)
        self.assertEqual(recs[0]["priority"], "P0")

    def test_decode_content_enforces_size_cap(self):
        payload = {"encoding": "base64", "content": "aGVsbG8="}
        self.assertEqual(cra._decode_content(payload, 100), "hello")
        self.assertEqual(cra._decode_content(payload, 3), "")


if __name__ == "__main__":
    unittest.main()
