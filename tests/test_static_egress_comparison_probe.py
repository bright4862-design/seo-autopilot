"""Exercise the isolated comparison boundary without DNS or outbound requests."""
import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SHA = "ca94e93af02fc6eccd47ea79dffd374af8b9fdbb"
IMAGE = "europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/fixlist-standard150-worker@sha256:" + "a" * 64
ORIGIN = "https://ironwoodcrecapital.com"


def environment(**updates):
    values = {
        "FIXLIST_COMPARISON_TARGET": "ironwood",
        "FIXLIST_COMPARISON_PROFILE": "static",
        "FIXLIST_COMPARISON_EXPECTED_IP": "34.52.147.10",
        "FIXLIST_COMPARISON_SOURCE_SHA": SHA,
        "FIXLIST_COMPARISON_REVISION": "fixlist-standard150-worker-00100-abc",
        "FIXLIST_COMPARISON_IMAGE": IMAGE,
    }
    values.update(updates)
    return values


@pytest.fixture
def probe(monkeypatch):
    path = ROOT / "scripts/static_egress_comparison_probe.py"
    assert path.exists(), "The isolated Standard 150 comparison probe is missing"
    monkeypatch.syspath_prepend(str(ROOT / "scanner-api"))
    spec = importlib.util.spec_from_file_location("static_egress_probe_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = [0.0]

    async def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(module, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "_sleep", sleep)
    return module


def install_network(monkeypatch, probe, *, robots="User-agent: *\nAllow: /", ip="34.52.147.10", replies=None):
    calls = []
    replies = dict(replies or {})

    async def fetch(client, url, *, max_decoded_bytes=None):
        calls.append((url, max_decoded_bytes, client._trust_env))
        if url == "https://api.ipify.org":
            status, body, headers = 200, ip, {}
        elif url == ORIGIN + "/robots.txt":
            response = replies.get(url, (200, robots, {}))
            if isinstance(response, list):
                response = response.pop(0)
            status, body, headers = response
        else:
            status, body, headers = replies.get(url, (404, "", {}))
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, content=body, headers=headers, request=httpx.Request("GET", url))

    monkeypatch.setattr(probe.security, "safe_get_once", fetch)
    monkeypatch.setattr(probe.scanner, "is_public_http_url", lambda _url: True)
    return calls


@pytest.mark.parametrize("changes", [
    {"FIXLIST_COMPARISON_TARGET": "https://evil.example/?token=secret"},
    {"FIXLIST_COMPARISON_PROFILE": "production"},
    {"FIXLIST_COMPARISON_EXPECTED_IP": "127.0.0.1"},
    {"FIXLIST_COMPARISON_EXPECTED_IP": "224.0.0.1"},
    {"FIXLIST_COMPARISON_EXPECTED_IP": "034.52.147.10"},
    {"FIXLIST_COMPARISON_EXPECTED_IP": "2001:4860::1"},
    {"FIXLIST_COMPARISON_SOURCE_SHA": "a" * 39},
    {"FIXLIST_COMPARISON_SOURCE_SHA": "A" * 40},
    {"FIXLIST_COMPARISON_REVISION": "foreign-worker-00100-abc"},
    {"FIXLIST_COMPARISON_IMAGE": "mutable:latest"},
    {"FIXLIST_COMPARISON_IMAGE": IMAGE + "\nsecret"},
    {"HTTP_PROXY": "https://proxy.example/?secret"},
    {"SSL_CERT_FILE": "/private/custom.pem"},
    {"SCAN_EVIDENCE_SIGNING_KEY": "never copy me"},
])
def test_unsafe_config_refuses_before_any_network(probe, monkeypatch, changes):
    calls = install_network(monkeypatch, probe)
    with pytest.raises(ValueError):
        asyncio.run(probe.run_probe(environment(**changes)))
    assert calls == []


def test_missing_config_refuses_before_any_network(probe, monkeypatch):
    calls = install_network(monkeypatch, probe)
    values = environment()
    del values["FIXLIST_COMPARISON_TARGET"]
    with pytest.raises(ValueError):
        asyncio.run(probe.run_probe(values))
    assert calls == []


def test_static_ip_mismatch_stops_before_target_requests(probe, monkeypatch):
    calls = install_network(monkeypatch, probe, ip="8.8.8.8")
    row = asyncio.run(probe.run_probe(environment()))
    assert row["failure_code"] == "source_ip_mismatch"
    assert row["static_ip_verified"] is False
    assert row["scan_completed"] is False
    assert [url for url, *_ in calls] == ["https://api.ipify.org"]


@pytest.mark.parametrize("ip", ["", "not-an-ip secret", "127.0.0.1", "224.0.0.1", "34.52.147.10\n8.8.8.8"])
def test_malformed_ip_echo_stops_before_target_requests(probe, monkeypatch, ip):
    calls = install_network(monkeypatch, probe, ip=ip)
    row = asyncio.run(probe.run_probe(environment()))
    assert row["failure_code"] == "ip_probe_failed"
    assert row["classification"] == "transport_failure"
    assert len(calls) == 1


@pytest.mark.parametrize("status,body,want", [
    (200, "User-agent: *\nDisallow: /", "robots_blocked"),
    (503, "unavailable", "robots_unknown"),
    (403, "access denied", "robots_unknown"),
])
def test_robots_refusal_fetches_no_pages_or_sitemaps(probe, monkeypatch, status, body, want):
    calls = install_network(monkeypatch, probe, replies={ORIGIN + "/robots.txt": (status, body, {})})
    row = asyncio.run(probe.run_probe(environment()))
    assert row["classification"] == want
    assert row["pages_crawled"] == 0
    assert [url for url, *_ in calls] == ["https://api.ipify.org", ORIGIN + "/robots.txt"]


def test_unknown_scanner_robots_reload_never_reopens_page_fetching(probe, monkeypatch):
    calls = install_network(monkeypatch, probe, replies={ORIGIN + "/robots.txt": [
        (200, "User-agent: *\nAllow: /", {}), (503, "temporarily unavailable", {}),
    ]})
    row = asyncio.run(probe.run_probe(environment()))
    assert row["classification"] == "robots_unknown"
    assert row["robots_unknown_seen"] is True
    assert all(url in {"https://api.ipify.org", ORIGIN + "/robots.txt"} for url, *_ in calls)


@pytest.mark.parametrize("last_robots,want", [
    ((503, "temporarily unavailable", {}), "robots_unknown"),
    ((200, "User-agent: *\nDisallow: /", {}), "robots_blocked"),
    ((0, httpx.ConnectError("Bearer SECRET"), {}), "robots_unknown"),
])
def test_native_sitemap_robots_reload_cannot_reuse_old_allow(probe, monkeypatch, last_robots, want):
    calls = install_network(monkeypatch, probe, replies={ORIGIN + "/robots.txt": [
        (200, "User-agent: *\nAllow: /", {}),
        (200, "User-agent: *\nAllow: /", {}),
        last_robots,
    ], ORIGIN + "/": (200, "<html><title>Allowed initial landing</title></html>", {"content-type": "text/html"})})
    row = asyncio.run(probe.run_probe(environment()))
    assert row["classification"] == want
    urls = [url for url, *_ in calls]
    assert urls[-1] == ORIGIN + "/robots.txt"
    assert urls.count(ORIGIN + "/robots.txt") == 3
    assert urls.count(ORIGIN + "/") == 1  # Native landing was allowed before the changed policy.
    assert ORIGIN + "/sitemap.xml" not in urls


def test_guard_denies_all_imported_fetch_aliases_and_sitemap_redirect_hops(probe, monkeypatch):
    calls = install_network(monkeypatch, probe, robots="User-agent: *\nDisallow: /private")

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            with guard.activate():
                await guard.load_policy(client, ORIGIN)
                for module in (probe.security, probe.redirect_validation, probe.canonical_validation, probe.coverage_probes):
                    assert await module.safe_get_once(client, ORIGIN + "/private", max_decoded_bytes=1024) is None
                    assert await module.safe_get_once(client, "https://evil.example/private?token=secret") is None
                assert await probe.security.safe_get(client, ORIGIN + "/sitemap.xml") is None
        return guard

    # A real safe_get redirect traversal must pass through the same strict guard.
    original = probe.security.safe_get_once

    async def redirect(client, url, *, max_decoded_bytes=None):
        if url == ORIGIN + "/sitemap.xml":
            calls.append((url, max_decoded_bytes, client._trust_env))
            return httpx.Response(302, headers={"location": "https://evil.example/captcha?token=secret"}, request=httpx.Request("GET", url))
        return await original(client, url, max_decoded_bytes=max_decoded_bytes)

    monkeypatch.setattr(probe.security, "safe_get_once", redirect)
    guard = asyncio.run(check())
    assert guard.refusals == 9
    assert [url for url, *_ in calls] == [ORIGIN + "/robots.txt", ORIGIN + "/sitemap.xml"]


def test_guard_honors_crawl_delay_and_keeps_original_decoded_body_limit(probe, monkeypatch):
    calls = install_network(monkeypatch, probe, robots="User-agent: *\nAllow: /\nCrawl-delay: 7\nRequest-rate: 1/9")
    timings = []
    original = probe.security.safe_get_once

    async def timed(client, url, *, max_decoded_bytes=None):
        timings.append(probe._monotonic())
        return await original(client, url, max_decoded_bytes=max_decoded_bytes)

    monkeypatch.setattr(probe.security, "safe_get_once", timed)

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        async with httpx.AsyncClient(trust_env=False) as client:
            with guard.activate():
                await guard.load_policy(client, ORIGIN)
                await probe.security.safe_get_once(client, ORIGIN + "/one", max_decoded_bytes=1234)
                await probe.security.safe_get_once(client, ORIGIN + "/two", max_decoded_bytes=4321)

    asyncio.run(check())
    assert timings == [0.0, 9.0, 18.0]
    assert [limit for _, limit, _ in calls][-2:] == [1234, 4321]


def test_guard_request_ceiling_never_reaches_transport_after_budget(probe, monkeypatch):
    calls = install_network(monkeypatch, probe)

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        async with httpx.AsyncClient(trust_env=False) as client:
            with guard.activate():
                await guard.load_policy(client, ORIGIN)
                for _ in range(205):
                    await probe.security.safe_get_once(client, ORIGIN + "/same")
        return guard

    guard = asyncio.run(check())
    assert len(calls) == guard.hops == 200
    assert guard.budget_exhausted is True


@pytest.mark.parametrize("status,headers", [(429, {}), (200, {"retry-after": "120"})])
def test_first_pressure_response_stops_every_later_site_hop(probe, monkeypatch, status, headers):
    calls = install_network(monkeypatch, probe, replies={ORIGIN + "/first": (status, "", headers)})

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        async with httpx.AsyncClient(trust_env=False) as client:
            with guard.activate():
                await guard.load_policy(client, ORIGIN)
                await probe.canonical_validation.safe_get_once(client, ORIGIN + "/first")
                assert await probe.coverage_probes.safe_get_once(client, ORIGIN + "/later") is None
                assert await probe.security.safe_get_once(client, ORIGIN + "/robots.txt") is None
        return guard

    guard = asyncio.run(check())
    assert guard.pressure_seen is True
    assert [url for url, *_ in calls] == [ORIGIN + "/robots.txt", ORIGIN + "/first"]


@pytest.mark.parametrize("status,headers", [(429, {}), (200, {"retry-after": "120"})])
def test_pressure_headers_stop_later_hops_even_when_original_body_decoder_raises(probe, monkeypatch, status, headers):
    monkeypatch.setattr(probe.security.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (2, 1, 6, "", ("34.52.147.10", 443))
    ])
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, headers=({"content-encoding": "unsupported", **headers} if status == 200 else headers),
                              stream=httpx.ByteStream(b"SECRET_BODY"))

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        guard.policy = probe.robots_policy.RobotsPolicy(ORIGIN + "/robots.txt", "missing", 404)
        with guard.activate():
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with pytest.raises((httpx.DecodingError, probe.security.ResponseBodyTooLarge)):
                    await probe.security.safe_get_once(client, ORIGIN + "/first", max_decoded_bytes=8)
                assert await probe.coverage_probes.safe_get_once(client, ORIGIN + "/later") is None
        return guard

    guard = asyncio.run(check())
    assert guard.pressure_seen is True
    assert len(requests) == 1


def test_cancelled_mandatory_crawl_delay_never_fetches_early(probe, monkeypatch):
    calls = install_network(monkeypatch, probe, robots="User-agent: *\nAllow: /\nCrawl-delay: 999")

    async def cancelled_sleep(_seconds):
        raise asyncio.CancelledError()

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        async with httpx.AsyncClient(trust_env=False) as client:
            with guard.activate():
                await guard.load_policy(client, ORIGIN)
                monkeypatch.setattr(probe, "_sleep", cancelled_sleep)
                with pytest.raises(asyncio.CancelledError):
                    await probe.security.safe_get_once(client, ORIGIN + "/never")

    asyncio.run(check())
    assert [url for url, *_ in calls] == [ORIGIN + "/robots.txt"]


@pytest.mark.parametrize("answers", [["169.254.169.254"], ["34.52.147.10", "10.0.0.1"]])
def test_guard_retains_original_private_and_mixed_dns_refusal(probe, monkeypatch, answers):
    monkeypatch.setattr(probe.security.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (2, 1, 6, "", (address, 443)) for address in answers
    ])

    class NoNetwork:
        async def get(self, *_args, **_kwargs):
            pytest.fail("Unsafe DNS answers reached the HTTP transport")

    async def check():
        guard = probe.RobotsGuard(ORIGIN)
        guard.policy = probe.robots_policy.RobotsPolicy(ORIGIN + "/robots.txt", "missing", 404)
        with guard.activate():
            assert await probe.security.safe_get_once(NoNetwork(), ORIGIN + "/allowed") is None
        return guard

    guard = asyncio.run(check())
    assert guard.hops == 1
    assert guard.scope_refused is False  # Refusal came from the unchanged DNS helper.


def test_native_scan_of_allowed_fixture_uses_only_paced_canonical_origin(probe, monkeypatch):
    html = "<html><head><title>Allowed fixture</title></head><body><h1>Company</h1><p>" + "Useful content. " * 100
    calls = install_network(monkeypatch, probe, replies={
        ORIGIN + "/": (200, html + '<a href="/about">About</a></body></html>', {"content-type": "text/html"}),
        ORIGIN + "/about": (200, html + "</p></body></html>", {"content-type": "text/html"}),
    })
    row = asyncio.run(probe.run_probe(environment()))
    assert row["classification"] == "usable_html"
    assert row["usable_html_pages"] >= 1
    assert row["scan_completed"] is True
    assert row["authoritative_scan"] is False
    assert row["failure_code"] == ""
    assert all(url == "https://api.ipify.org" or url.startswith(ORIGIN + "/") for url, *_ in calls)
    assert row["http_hops"] == len(calls) <= 200
    assert row["elapsed_ms"] >= (len(calls) - 2) * 500


def test_scanner_failure_restores_every_process_local_guard(probe, monkeypatch):
    install_network(monkeypatch, probe)
    modules = (probe.security, probe.redirect_validation, probe.canonical_validation, probe.coverage_probes)
    old_fetches = [module.safe_get_once for module in modules]
    old_allowed = probe.robots_policy.RobotsPolicy.allowed
    old_loader = probe.scanner.load_robots_policy
    old_client = httpx.AsyncClient

    async def failing_scan(**_kwargs):
        assert probe.robots_policy.owner_robots_override_active() is False
        raise RuntimeError("Bearer SECRET https://example.com/?token=SECRET")

    monkeypatch.setattr(probe.scanner, "run_scan", failing_scan)
    with probe.robots_policy.owner_robots_override(True):
        row = asyncio.run(probe.run_probe(environment()))
        assert probe.robots_policy.owner_robots_override_active() is True
    assert row["failure_code"] == "scanner_failed"
    assert "SECRET" not in json.dumps(row)
    assert [module.safe_get_once for module in modules] == old_fetches
    assert probe.robots_policy.RobotsPolicy.allowed is old_allowed
    assert probe.scanner.load_robots_policy is old_loader
    assert httpx.AsyncClient is old_client


def test_complete_row_contains_only_bounded_aggregate_evidence(probe, monkeypatch):
    calls = install_network(monkeypatch, probe)

    async def scan(**kwargs):
        assert kwargs == {"website_url": ORIGIN + "/", "scan_mode": "advanced", "timeout_seconds": 210, "job_mode": True}
        assert probe.robots_policy.owner_robots_override_active() is False
        # Context-created clients must ignore environment proxy/cert settings.
        async with httpx.AsyncClient() as client:
            assert client._trust_env is False
        return {"success": True, "pages_crawled": 999999, "pages_found": "secret", "pages": [
            {"status_code": 200, "html_size": 100, "page_evidence_class": "usable_html", "url": ORIGIN + "/?secret=hidden", "raw_html": "SECRET_BODY"},
            {"status_code": 403, "page_evidence_class": "failed_access"},
            {"status_code": 429, "page_evidence_class": "failed_access"},
            {"status_code": 0, "fetch_error": "timeout Bearer SECRET"},
        ], "raw_findings": [{"secret": "never publish"}]}

    monkeypatch.setattr(probe.scanner, "run_scan", scan)
    row = asyncio.run(probe.run_probe(environment()))
    assert row["classification"] == "usable_html"
    assert row["pages_crawled"] == 4
    assert row["usable_html_pages"] == 1
    assert row["access_limited_pages"] == 2
    assert row["transport_failure_pages"] == 1
    assert row["http_403_pages"] == row["http_429_pages"] == 1
    assert row["authoritative_scan"] is row["worker_process"] is False
    assert row["static_ip_verified"] is True
    assert row["scan_completed"] is True
    assert all(trust_env is False for _, _, trust_env in calls)
    text = json.dumps(row)
    assert "SECRET" not in text and "raw_findings" not in text and "?secret" not in text
    assert len(text) < 3000


def test_default_profile_records_different_public_ip_without_static_claim(probe, monkeypatch):
    install_network(monkeypatch, probe, ip="8.8.8.8", robots="User-agent: *\nDisallow: /")
    row = asyncio.run(probe.run_probe(environment(FIXLIST_COMPARISON_PROFILE="default")))
    assert row["observed_ip"] == "8.8.8.8"
    assert row["static_ip_verified"] is False
    assert row["classification"] == "robots_blocked"
    assert row["failure_code"] == ""


def test_main_sanitizes_invalid_configuration_and_exception_output(probe, monkeypatch, capsys):
    assert probe.main(environment(FIXLIST_COMPARISON_TARGET="SECRET")) == 2
    row = json.loads(capsys.readouterr().out)
    assert row == {"diagnostic": "static_egress_comparison_v1", "event": "error", "failure_code": "invalid_configuration"}

    async def broken(_env):
        raise RuntimeError("Bearer SECRET https://example.com/?token=SECRET")

    monkeypatch.setattr(probe, "run_probe", broken)
    assert probe.main(environment()) == 1
    row = json.loads(capsys.readouterr().out)
    assert row["failure_code"] == "probe_failed"
    assert "SECRET" not in json.dumps(row)
