import importlib.util
import json
from pathlib import Path

import httpx
import pytest


def module():
    path = Path(__file__).resolve().parents[2] / "scripts/ironwood_probe.py"
    assert path.exists(), "Bounded HTTP comparison not implemented"
    spec = importlib.util.spec_from_file_location("ironwood_probe", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.asyncio
async def test_comparison_is_sequential_bounded_and_never_follows_challenge(monkeypatch):
    m = module()
    seen, waits, rows = [], [], []
    async def get(client, url, **kwargs):
        seen.append((url, client.headers["user-agent"], kwargs))
        return httpx.Response(202, headers={"sg-captcha": "challenge", "set-cookie": "private=secret", "x-robots-tag": "noindex"}, text='<meta http-equiv="refresh" content="0;url=/.well-known/sgcaptcha/test?token=secret">')
    async def pause(seconds): waits.append(seconds)
    monkeypatch.setattr(m, "safe_get_once", get)
    monkeypatch.setattr(m.asyncio, "sleep", pause)
    await m.compare(rows.append)
    assert len(seen) == 6  # No repeated challenged root.
    assert {url for url, _, _ in seen} == {"https://ironwoodcrecapital.com/", "https://ironwoodcrecapital.com/robots.txt", "https://ironwoodcrecapital.com/sitemap.xml"}
    assert all(k["max_decoded_bytes"] == 2_000_000 for _, _, k in seen)
    assert waits == [5] * 5
    requests = [r for r in rows if r["event"] == "response"]
    assert all(r["challenge"]["vendor"] == "siteground" for r in requests)
    assert all(r["meta_refresh_target"] == "https://ironwoodcrecapital.com/.well-known/sgcaptcha/test" for r in requests)
    assert "secret" not in json.dumps(rows)
    assert "set-cookie" not in json.dumps(rows)
    assert rows[-1]["event"] == "complete"


@pytest.mark.asyncio
async def test_rate_limit_stops_entire_matrix(monkeypatch):
    m, rows = module(), []
    async def get(*args, **kwargs): return httpx.Response(429, headers={"retry-after": "60"})
    monkeypatch.setattr(m, "safe_get_once", get)
    await m.compare(rows.append)
    assert [r["event"] for r in rows] == ["response", "complete"]
    assert rows[-1]["requests"] == 1
    assert rows[-1]["stop_reason"] == "rate_limited"


@pytest.mark.asyncio
async def test_success_has_single_baseline_repeat_and_no_cookies(monkeypatch):
    m, profiles, rows = module(), [], []
    async def get(client, url, **kwargs):
        assert not client.cookies
        client.cookies.set("challenge", "do-not-replay")
        profiles.append(client.headers["user-agent"])
        return httpx.Response(200, text="<html><body>Public page</body></html>")
    async def pause(seconds): pass
    monkeypatch.setattr(m, "safe_get_once", get)
    monkeypatch.setattr(m.asyncio, "sleep", pause)
    await m.compare(rows.append)
    assert len(profiles) == 7
    assert profiles[0] == profiles[-1] == "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"
    assert profiles[1] == "FixListBot/1.0 (+https://getfixlist.com/crawler)"
    assert rows[-1]["requests"] == 7


@pytest.mark.asyncio
async def test_real_security_path_pins_dns_and_never_follows_redirects(mock_network, monkeypatch):
    m, requests, rows = module(), [], []
    mock_network({"/": {"status": 302, "headers": {"location": "http://169.254.169.254/latest/meta-data/"}},
                  "/robots.txt": {"status": 429}})
    original = httpx.MockTransport.handle_async_request
    async def observe(self, request):
        requests.append(request)
        return await original(self, request)
    async def pause(seconds): pass
    monkeypatch.setattr(httpx.MockTransport, "handle_async_request", observe)
    monkeypatch.setattr(m.asyncio, "sleep", pause)
    await m.compare(rows.append)
    assert len(requests) == 3
    assert all(r.headers["host"] == "ironwoodcrecapital.com" for r in requests)
    assert all(r.headers["connection"] == "close" for r in requests)
    assert all(r.extensions["sni_hostname"] == "ironwoodcrecapital.com" for r in requests)
    assert all(r.url.path in ("/", "/robots.txt") for r in requests)
    assert rows[-1]["stop_reason"] == "rate_limited"
