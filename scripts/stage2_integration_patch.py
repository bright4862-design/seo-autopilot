from pathlib import Path


SCANNER_PATH = Path("scanner-api/app/scanner.py")
TEST_PATH = Path("scanner-api/tests/test_stage2_run_scan_integration.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_scanner() -> None:
    text = SCANNER_PATH.read_text()

    if "import inspect\n" not in text:
        text = replace_once(text, "import hashlib\n", "import hashlib\nimport inspect\n", "inspect import")
    if "from .active_soft404_orchestration import uniform_observed_group_provenance" not in text:
        text = replace_once(
            text,
            "from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact\n",
            "from .active_soft404_orchestration import uniform_observed_group_provenance\n"
            "from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact\n",
            "active-soft404 provenance import",
        )
    if "from .stage2_shared_probe_orchestration import run_stage2_shared_probe_orchestration" not in text:
        text = replace_once(
            text,
            "from .search_applicability import search_applicability, search_metadata_applicable, filter_search_findings\n",
            "from .search_applicability import search_applicability, search_metadata_applicable, filter_search_findings\n"
            "from .stage2_shared_probe_orchestration import run_stage2_shared_probe_orchestration\n",
            "shared Stage 2 orchestration import",
        )

    helper = '''\n\ndef _supports_stage2_probe_fetch(fetcher) -> bool:\n    """Require the hardened callback seam before active Standard-150 probes run.\n\n    Stage-2 active probes are allowed only when the active fetch callback accepts\n    both robots policy and the shared scheduler's request provider. This keeps the\n    finite request pool enforceable and fails closed for legacy/injected callbacks\n    that cannot honor that contract.\n    """\n    try:\n        parameters = inspect.signature(fetcher).parameters\n    except (TypeError, ValueError):\n        return False\n    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):\n        return True\n    return "robots_policy" in parameters and "request_provider" in parameters\n\n\n'''
    if "def _supports_stage2_probe_fetch(fetcher)" not in text:
        text = replace_once(text, "\n\nasync def run_scan(\n", helper + "async def run_scan(\n", "Stage 2 fetch capability helper")

    text = replace_once(
        text,
        "        coverage_probe_evidence = probe_scheduler.summary()\n",
        "        if int(budget.get(\"max_pages\") or 0) >= 150 and _supports_stage2_probe_fetch(fetch_and_extract):\n"
        "            coverage_probe_evidence = await run_stage2_shared_probe_orchestration(\n"
        "                client=client,\n"
        "                pages=pages,\n"
        "                sitemap_urls=sitemap_urls,\n"
        "                sitemap_diagnostics=sitemap_diagnostics,\n"
        "                origin=origin,\n"
        "                scope_prefix=prefix,\n"
        "                robots_policy=robots_policy,\n"
        "                probe_scheduler=probe_scheduler,\n"
        "                fetch_page=fetch_and_extract,\n"
        "            )\n"
        "        else:\n"
        "            coverage_probe_evidence = probe_scheduler.summary()\n"
        "            if int(budget.get(\"max_pages\") or 0) >= 150:\n"
        "                coverage_probe_evidence.update({\n"
        "                    \"stage2_orchestration_state\": \"not_verified\",\n"
        "                    \"stage2_orchestration_reason\": \"hardened_probe_fetch_contract_unavailable\",\n"
        "                })\n",
        "run_scan shared Stage 2 orchestration call",
    )

    old_provenance = '''        observed_versions = {
            str(finding.get("observed_evidence_version") or "").strip()
            for finding in members
            if str(finding.get("observed_evidence_version") or "").strip()
        }
        verified_observed_pages = _unique_nonempty([
            page
            for finding in members
            for page in (
                finding.get("verified_observed_pages")
                if isinstance(finding.get("verified_observed_pages"), list)
                else []
            )
        ])
'''
    text = replace_once(
        text,
        old_provenance,
        "        group_provenance = uniform_observed_group_provenance(members)\n",
        "group observed provenance derivation",
    )
    text = replace_once(
        text,
        "        grouped = dict(sample)\n        grouped.update({\n",
        "        grouped = dict(sample)\n"
        "        # A lead/sample row must never lend active observed authority to\n"
        "        # an unversioned group member. Restore provenance only through\n"
        "        # the all-members-same-version contract above.\n"
        "        grouped.pop(\"observed_evidence_version\", None)\n"
        "        grouped.pop(\"verified_observed_pages\", None)\n"
        "        grouped.update({\n",
        "strip inherited group provenance",
    )
    old_splat = '''            **({
                "observed_evidence_version": next(iter(observed_versions)),
                "verified_observed_pages": verified_observed_pages,
            } if len(observed_versions) == 1 and verified_observed_pages else {}),
'''
    text = replace_once(text, old_splat, "            **group_provenance,\n", "group provenance restore")

    text = replace_once(
        text,
        '"This URL reaches a working page, but the redirect collapses a specific deep URL onto the site homepage instead of a relevant replacement page.",',
        '"This URL reaches working HTML, but the redirect sends a specific URL to an unrelated or catch-all destination instead of a relevant replacement page.",',
        "B08 single explanation",
    )
    text = replace_once(
        text,
        '"Point the source URL to the closest relevant replacement page, or restore the intended page. Do not use the homepage as a catch-all destination.",',
        '"Point the source URL to the closest relevant replacement page, or restore the intended page. Avoid unrelated or catch-all redirects that erase the source URL meaning.",',
        "B08 single recommendation",
    )
    text = replace_once(
        text,
        '"These source URLs reach working HTML, but they collapse onto a generic homepage rather than a relevant replacement. "\n        "That is a redirect-destination problem, not a page-availability failure.",',
        '"These source URLs reach working HTML, but they collapse onto unrelated or catch-all destinations rather than relevant replacements. "\n        "That is a redirect-destination problem, not a page-availability failure.",',
        "B08 grouped explanation",
    )
    text = replace_once(
        text,
        '"Map each source URL to the closest relevant replacement page, or restore the intended page. Avoid homepage catch-all redirects.",',
        '"Map each source URL to the closest relevant replacement page, or restore the intended page. Avoid unrelated or catch-all redirects that erase the source URL meaning.",',
        "B08 grouped recommendation",
    )
    text = replace_once(
        text,
        'return "Fix redirects that send specific URLs to the homepage"',
        'return "Fix redirects that send specific URLs to unrelated destinations"',
        "B08 grouped title",
    )

    SCANNER_PATH.write_text(text)


def write_tests() -> None:
    TEST_PATH.write_text(r'''import pytest

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
''')


def main() -> None:
    patch_scanner()
    write_tests()


if __name__ == "__main__":
    main()
