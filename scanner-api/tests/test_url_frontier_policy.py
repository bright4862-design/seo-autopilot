import unittest

from app.url_frontier_policy import FRONTIER_POLICY_VERSION, classify_frontier_url


class UrlFrontierPolicyTests(unittest.TestCase):
    def test_strips_tracking_without_dropping_real_page(self):
        decision = classify_frontier_url("https://example.com/product?a=1&utm_source=x&gclid=abc")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.url, "https://example.com/product?a=1")
        self.assertEqual(set(decision.removed_params), {"utm_source", "gclid"})

    def test_strips_session_identifier(self):
        decision = classify_frontier_url("https://example.com/account?sid=123&view=summary")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.url, "https://example.com/account?view=summary")

    def test_blocks_elementor_pagination_trap(self):
        decision = classify_frontier_url("https://example.com/blog/?e-page-abc123=854")
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.reason.startswith("crawler_trap_param:"))

    def test_blocks_elementor_filter_trap(self):
        decision = classify_frontier_url("https://example.com/shop/?e-filter-deadbeef=red")
        self.assertFalse(decision.allowed)

    def test_blocks_adjacent_repeating_slug(self):
        decision = classify_frontier_url("https://example.com/our-team/our-team/")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "repeating_path_cycle")

    def test_blocks_repeated_two_segment_cycle(self):
        decision = classify_frontier_url("https://example.com/case-studies/team/case-studies/team/")
        self.assertFalse(decision.allowed)

    def test_keeps_legitimate_market_locale_path(self):
        decision = classify_frontier_url("https://example.com/fr/fr/annonce/example/voir")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.url, "https://example.com/fr/fr/annonce/example/voir")

    def test_keeps_ordinary_faceted_or_search_parameter(self):
        # Conservative by design: do not suppress business query parameters just
        # because they might be facets. That requires site-specific evidence.
        decision = classify_frontier_url("https://example.com/search?q=red+shoes&color=red")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.url, "https://example.com/search?q=red+shoes&color=red")

    def test_version_is_explicit(self):
        self.assertTrue(FRONTIER_POLICY_VERSION.startswith("url_frontier_policy_v1"))


if __name__ == "__main__":
    unittest.main()
