import pytest

from app.artifact_filter import (
    ARTIFACT_FILTER_VERSION,
    MAX_ARTIFACT_EVIDENCE,
    WORDPRESS_ROUTE_NOISE_VERSION,
    is_artifact_url,
    is_non_html_resource_url,
    is_wordpress_route_noise_url,
    record_artifact,
)


def test_detects_encoded_base64_path():
    assert is_artifact_url("https://example.com/section/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw=")


def test_does_not_flag_normal_slug():
    assert not is_artifact_url("https://example.com/pret-immobilier/type-prets/")


def test_human_blog_slugs_are_not_artifacts():
    assert ARTIFACT_FILTER_VERSION == "artifact_filter_v4_wordpress_route_noise"
    assert WORDPRESS_ROUTE_NOISE_VERSION == "wordpress_route_noise_v1_default_utility_routes"
    assert not is_artifact_url("https://www.centerstreetlending.com/blog/10-questions-you-should-ask-your-contractor")
    assert not is_artifact_url("https://www.centerstreetlending.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions")
    assert not is_artifact_url("https://www.centerstreetlending.com/blog/7-hidden-deal-killers-that-slow-down-real-estate-loan-closings-in-2026")


def test_loan_and_conversion_slugs_are_not_artifacts():
    assert not is_artifact_url("https://www.centerstreetlending.com/loans/fix-and-flip")
    assert not is_artifact_url("https://www.centerstreetlending.com/loans/bridge")
    assert not is_artifact_url("https://www.centerstreetlending.com/apply-now")
    assert not is_artifact_url("https://www.centerstreetlending.com/request-a-payoff")


def test_encoded_urls_are_still_artifacts():
    assert is_artifact_url("https://example.com/aHR0cHM6Ly9ldmlsLmV4YW1wbGUvZm9v")
    assert is_artifact_url("https://example.com/%2Fhttps%3A%2F%2Fevil.example%2Ffoo")
    assert is_artifact_url("https://example.com/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")


def test_long_non_human_url_safe_tokens_are_artifacts():
    assert is_artifact_url("https://example.com/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKl")


def test_known_non_html_resources_are_artifacts():
    urls = [
        "https://example.com/wp-content/uploads/photo.PNG?size=large",
        "https://example.com/brochure.pdf#page=2",
        "https://example.com/assets/app.mjs",
        "https://example.com/assets/site.css?v=4",
        "https://example.com/fonts/site.woff2",
        "https://example.com/video/launch.mp4",
        "https://example.com/agents.md",
    ]
    for url in urls:
        assert is_non_html_resource_url(url)
        assert is_artifact_url(url)


def test_sitemap_files_and_html_like_routes_are_not_resource_artifacts():
    assert not is_non_html_resource_url("https://example.com/sitemap.xml")
    assert not is_non_html_resource_url("https://example.com/product-sitemap.xml.gz")
    assert not is_artifact_url("https://example.com/about-us.v2")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/wp-login.php",
        "https://example.com/wp-login.php?action=lostpassword",
        "https://example.com/wp-login.php?jetpack-sso-show-default-form=0",
        "https://example.com/wp-admin/",
        "https://example.com/wp-admin/admin-ajax.php",
        "https://example.com/wp-json/",
        "https://example.com/wp-json/wp/v2/posts",
        "https://example.com/xmlrpc.php",
        "https://example.com/wp-cron.php?doing_wp_cron=1",
        "https://example.com/feed/",
        "https://example.com/comments/feed/",
        "https://example.com/news/feed/",
        "https://example.com/post-name/trackback/",
        "https://example.com/hello-world/",
        "https://example.com/sample-page/",
        "https://example.com/category/uncategorized/",
        "https://example.com/?rest_route=/wp/v2/posts",
        "https://example.com/post-name/?replytocom=123",
        "https://example.com/?feed=rss2",
    ],
)
def test_wordpress_utility_and_default_routes_are_artifacts(url):
    assert is_wordpress_route_noise_url(url)
    assert is_artifact_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://example.com/about/",
        "https://example.com/menu/",
        "https://example.com/category/bread/",
        "https://example.com/category/uncategorized-baking/",
        "https://example.com/tag/sourdough/",
        "https://example.com/author/jane-doe/",
        "https://example.com/hello-world-bakery/",
        "https://example.com/products/bread/",
        "https://example.com/wp-sitemap.xml",
        "https://example.com/post-name/?p=123",
    ],
)
def test_legitimate_wordpress_content_remains_crawlable(url):
    assert not is_wordpress_route_noise_url(url)
    assert not is_artifact_url(url)


def test_resource_artifact_reason_is_explicit():
    artifacts = []
    record_artifact(artifacts, "https://example.com/wp-content/uploads/logo.jpg", "sitemap", "/sitemap.xml", "")
    assert artifacts[0]["url_suspicion_reasons"] == ["non_html_resource_path"]


def test_wordpress_route_noise_reason_is_explicit():
    artifacts = []
    record_artifact(artifacts, "https://example.com/wp-login.php?action=lostpassword", "internal_link", "/", "Log in")
    assert artifacts[0]["url_suspicion_reasons"] == ["wordpress_route_noise"]
    assert artifacts[0]["suppressed_from_crawl"] is True


def test_artifact_evidence_cap():
    artifacts = []
    for index in range(MAX_ARTIFACT_EVIDENCE + 10):
        record_artifact(artifacts, f"https://example.com/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw={index}", "internal_link", "/", "bad")
    assert len(artifacts) == MAX_ARTIFACT_EVIDENCE
