from app.artifact_filter import (
    ARTIFACT_FILTER_VERSION,
    MAX_ARTIFACT_EVIDENCE,
    is_artifact_url,
    is_non_html_resource_url,
    record_artifact,
)


def test_detects_encoded_base64_path():
    assert is_artifact_url("https://example.com/section/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw=")


def test_does_not_flag_normal_slug():
    assert not is_artifact_url("https://example.com/pret-immobilier/type-prets/")


def test_human_blog_slugs_are_not_artifacts():
    assert ARTIFACT_FILTER_VERSION == "artifact_filter_v3_non_html_resources"
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


def test_resource_artifact_reason_is_explicit():
    artifacts = []
    record_artifact(artifacts, "https://example.com/wp-content/uploads/logo.jpg", "sitemap", "/sitemap.xml", "")
    assert artifacts[0]["url_suspicion_reasons"] == ["non_html_resource_path"]


def test_artifact_evidence_cap():
    artifacts = []
    for index in range(MAX_ARTIFACT_EVIDENCE + 10):
        record_artifact(artifacts, f"https://example.com/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw={index}", "internal_link", "/", "bad")
    assert len(artifacts) == MAX_ARTIFACT_EVIDENCE
