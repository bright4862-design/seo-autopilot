import pytest

from app import scanner
from app.active_soft404_orchestration import ACTIVE_SOFT404_ORCHESTRATION_VERSION
from app.extract import extract_page


class Policy:
    def directive_allowed(self, _user_agent, _url):
        return True

    def allowed(self, _user_agent, _url):
        return True

    def evidence(self):
        return {}


class LandingResponse:
    def __init__(self, url):
        self.url = url
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.text = "<html><body>landing</body></html>"


def test_stage2_probe_fetch_requires_hardened_shared_request_provider_contract():
    async def legacy_fetch(_client, _url, _discovery, robots_policy=None):
        return {}

    async def hardened_fetch(_client, _url, _discovery, robots_policy=None, request_provider=None):
        return {}

    async def kwargs_fetch(_client, _url, _discovery, **kwargs):
        return {}

    assert scanner._supports_stage2_probe_fetch(legacy_fetch) is False
    assert scanner._supports_stage2_probe_fetch(hardened_fetch) is True
    assert scanner._supports_stage2_probe_fetch(kwargs_fetch) is True


@pytest.mark.asyncio
async def test_run_scan_calls_one_shared_stage2_orchestrator_without_expanding_assessed_pages(monkeypatch):
    monkeypatch.setattr(scanner, "is_public_http_url", lambda _url: True)

    async def fake_load_robots_policy(_client, _origin):
        return Policy()

    async def fake_safe_get(_client, url, **_kwargs):
        return LandingResponse(url)

    async def fake_load_sitemap_urls(*_args, **_kwargs):
        return []

    async def fake_fetch_and_extract(_client, url, discovery, robots_policy=None, request_provider=None):
        return extract_page(
            "<html><head><title>Useful page</title></head><body><h1>Useful page</h1><p>Substantive accepted content for the assessed page.</p></body></html>",
            url,
            url,
            200,
            "text/html",
            discovery,
            include_links=True,
        )

    async def fake_validate(*_args, **_kwargs):
        return {}

    async def fake_render_followup(*_args, **_kwargs):
        return {"attempted": 0}

    captured = {}

    async def fake_stage2_orchestration(**kwargs):
        captured.update(kwargs)
        summary = kwargs["probe_scheduler"].summary()
        summary.update({
            "stage2_orchestration_version": "test_shared_stage2_orchestration",
            "soft_404_baselines": [{
                "version": ACTIVE_SOFT404_ORCHESTRATION_VERSION,
                "state": "not_verified",
                "reason": "test_only",
            }],
            "assessed_page_count_before": len(kwargs["pages"]),
            "assessed_page_count_after": len(kwargs["pages"]),
            "assessed_page_count_unchanged": True,
        })
        return summary

    monkeypatch.setattr(scanner, "load_robots_policy", fake_load_robots_policy)
    monkeypatch.setattr(scanner, "safe_get", fake_safe_get)
    monkeypatch.setattr(scanner, "load_sitemap_urls", fake_load_sitemap_urls)
    monkeypatch.setattr(scanner, "fetch_and_extract", fake_fetch_and_extract)
    monkeypatch.setattr(scanner, "validate_canonical_targets", fake_validate)
    monkeypatch.setattr(scanner, "run_render_followup", fake_render_followup)
    monkeypatch.setattr(scanner, "run_stage2_shared_probe_orchestration", fake_stage2_orchestration)

    result = await scanner.run_scan("https://example.com/", scan_mode="advanced", concurrency=1)

    assert result["success"] is True
    assert result["pages_crawled"] == 1
    assert len(result["pages"]) == 1
    assert captured["pages"] is result["pages"]
    assert captured["origin"] == "https://example.com"
    assert captured["scope_prefix"] == "/"
    assert captured["fetch_page"] is fake_fetch_and_extract
    assert result["coverage_probe_evidence"]["stage2_orchestration_version"] == "test_shared_stage2_orchestration"
    assert result["coverage_probe_evidence"]["assessed_page_count_unchanged"] is True
    assert result["technical_audit_summary"]["coverage_probe_evidence"] == result["coverage_probe_evidence"]


def _group_member(path, *, version=None):
    finding = scanner.create_finding(
        "missing_h1",
        "thin_content",
        "medium",
        "Add one clear page heading",
        path,
        explanation="Missing H1",
        recommendation="Add an H1",
    )
    if version:
        finding["observed_evidence_version"] = version
        finding["verified_observed_pages"] = [f"https://example.com{path}"]
    return finding


def test_group_findings_drops_observed_authority_when_any_member_is_unversioned():
    rows = [
        _group_member("/blog/post-a", version="observed_v1"),
        _group_member("/blog/post-b"),
        _group_member("/blog/post-c", version="observed_v1"),
    ]
    grouped = scanner.group_findings(rows)
    assert len(grouped) == 1
    assert grouped[0]["page_count"] == 3
    assert "observed_evidence_version" not in grouped[0]
    assert "verified_observed_pages" not in grouped[0]


def test_group_findings_restores_exact_observed_union_only_for_uniform_version():
    rows = [
        _group_member("/blog/post-a", version="observed_v1"),
        _group_member("/blog/post-b", version="observed_v1"),
        _group_member("/blog/post-c", version="observed_v1"),
    ]
    grouped = scanner.group_findings(rows)
    assert len(grouped) == 1
    assert grouped[0]["observed_evidence_version"] == "observed_v1"
    assert grouped[0]["verified_observed_pages"] == [
        "https://example.com/blog/post-a",
        "https://example.com/blog/post-b",
        "https://example.com/blog/post-c",
    ]


def _wrong_redirect(source, destination):
    return {
        "url": source,
        "redirect_source_path": source.replace("https://example.com", ""),
        "redirect_hop_count": 1,
        "redirect_state": "redirect_complete",
        "redirect_outcome": "redirect_to_wrong_destination",
        "redirect_destination_url": destination,
        "final_url": destination,
        "redirect_destination_status_code": 200,
        "redirect_destination_indexability_state": "Indexable",
        "redirect_chain": [source, destination],
        "discovered_from": ["internal_link"],
    }


def test_b08_wrong_destination_copy_covers_unrelated_sections_not_only_homepage():
    finding = scanner.redirect_finding_for_page(
        _wrong_redirect("https://example.com/old-product", "https://example.com/blog/"),
        scan_origin="https://example.com",
        identity_version="",
    )
    assert finding is not None
    assert finding["rule"] == "redirect_wrong_destination"
    assert "unrelated or catch-all destination" in finding["plain_english_explanation"]
    assert "unrelated or catch-all redirects" in finding["recommendation"]

    grouped = scanner.group_findings([
        scanner.redirect_finding_for_page(_wrong_redirect(f"https://example.com/old-{i}", "https://example.com/blog/"))
        for i in range(3)
    ])
    assert len(grouped) == 1
    assert grouped[0]["title"] == "Fix redirects that send specific URLs to unrelated destinations"
    assert "unrelated or catch-all destinations" in grouped[0]["plain_english_explanation"]
