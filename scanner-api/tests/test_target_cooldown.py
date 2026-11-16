"""HTTP header evidence, signed relay, and replay through the staged worker."""

import asyncio
import socket
from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from app import scan_job
from app.finalize_probe_guard import FinalizeProbeSuppressed
from app.security import safe_get, safe_get_once
from app.staged_scan import StageRetry, StagedScanRuntime
from app.target_cooldown import (
    MAX_RETRY_AFTER_SECONDS,
    TargetCooldownRelay,
    explicit_http_origin,
    explicit_retry_after,
    target_cooldown_scope,
)
from app.workspace import MemoryWorkspace
from tests.test_staged_workspace import Harness, State


ORIGIN = "https://example.com:443"
HOST = "https://example.com"
NOW = 1_790_000_000


@pytest.mark.parametrize(("value", "expected"), [
    ("1", 1), (" 0004\t", 4), ("3600", 3600), ("999999999999", MAX_RETRY_AFTER_SECONDS),
    ("0", 0), ("", 0), ("-1", 0), ("+1", 0), ("1.5", 0), ("1e2", 0), ("1, 3", 0),
    (format_datetime(datetime.fromtimestamp(NOW + 20, timezone.utc), usegmt=True), 20),
    (format_datetime(datetime.fromtimestamp(NOW - 20, timezone.utc), usegmt=True), 0),
])
def test_explicit_retry_after(value, expected):
    assert explicit_retry_after(value, NOW) == expected


def test_exact_origin_preserves_scope_boundaries():
    assert explicit_http_origin("https://example.com/a") == ORIGIN
    assert explicit_http_origin("https://example.com:443/b") == ORIGIN
    assert explicit_http_origin("https://www.example.com./b") == "https://www.example.com.:443"
    assert explicit_http_origin("http://example.com:443/b") == "http://example.com:443"
    assert explicit_http_origin("https://example.com:8443/b") == "https://example.com:8443"
    assert explicit_http_origin("https://[2606:4700:4700:0:0:0:0:1111]/") == "https://[2606:4700:4700::1111]:443"
    assert explicit_http_origin("https://user:secret@example.com/a") == ""


@pytest.fixture
def public_dns(monkeypatch):
    def getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


class UnreadableBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        pytest.fail("A verified 429 body must not be read")
        yield b""


@pytest.mark.asyncio
async def test_header_observer_uses_validated_logical_hop_and_not_numeric_ip(public_dns):
    signals = []

    async def publish(observation):
        signals.append(observation)
        return True

    def target(request):
        assert request.url.host == "93.184.216.34"
        host = request.headers["host"]
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "https://www.example.com/throttled"}, stream=httpx.ByteStream(b""))
        if host == "www.example.com":
            return httpx.Response(429, headers={"Retry-After": "60"}, stream=httpx.ByteStream(b"other origin"))
        if request.url.path == "/missing":
            return httpx.Response(429, stream=httpx.ByteStream(b"without an explicit header"))
        if request.url.path == "/multiple":
            return httpx.Response(429, headers=[("Retry-After", "30"), ("Retry-After", "60")], stream=httpx.ByteStream(b"ambiguous"))
        assert host == "example.com"
        return httpx.Response(429, headers={"Retry-After": "3600"}, stream=UnreadableBody())

    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW)
    await relay.resume()
    async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
        with target_cooldown_scope(relay):
            assert (await safe_get(client, HOST + "/redirect", max_decoded_bytes=1024)).text == "other origin"
            assert "without an explicit" in (await safe_get_once(client, HOST + "/missing", max_decoded_bytes=1024)).text
            assert (await safe_get_once(client, HOST + "/multiple", max_decoded_bytes=1024)).text == "ambiguous"
            seen = await safe_get_once(client, HOST + "/canonical", max_decoded_bytes=1024)
    assert seen.status_code == 429 and seen.content == b""
    assert str(seen.url) == HOST + "/canonical"
    await relay.require_acknowledged()
    assert signals == [{
        "status_code": 429, "target_origin": ORIGIN, "observed_at": NOW, "retry_after_seconds": 3600,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "body", "acknowledged"), [
    (200, {"success": True, "outcome": "recorded"}, True),
    (200, {"success": True, "outcome": "unchanged"}, True),
    (200, {"success": True, "outcome": "expired"}, True),
    (503, {"error_code": "target_cooldown_publish_unavailable"}, False),
    (200, {"success": True}, False),
])
async def test_relay_signs_observation_inside_physical_v9_control(monkeypatch, status, body, acknowledged):
    key = "test-cooldown-key"
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", key)
    scan = {
        "id": "scan_test", "request_id": "request_test", "project_id": "project_test",
        "owner_user_id": "owner_test", "attempt_count": 2, "website_url": HOST + "/",
    }
    observation = {"status_code": 429, "target_origin": ORIGIN, "observed_at": NOW, "retry_after_seconds": 3600}

    async def invoke(client, name, envelope, **kwargs):
        assert name == "durableScanWorkerControlV9"
        payload = {key: value for key, value in envelope.items() if key != "proof"}
        assert payload == {
            "version": "durable_standard150_control_v1", "action": "observe_target_cooldown",
            "scan_id": "scan_test", "identity": {
                "scan_id": "scan_test", "request_id": "request_test", "idempotency_key": "request_test",
                "project_id": "project_test", "owner_user_id": "owner_test",
                "normalized_domain": "example.com", "attempt_count": "2",
            }, "failure": None, "target_cooldown": observation,
        }
        assert envelope["proof"] == scan_job.create_authority_seal(payload, key)
        return {"status_code": status, "body": body}

    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    assert await scan_job.publish_target_cooldown(None, scan, observation) is acknowledged


@pytest.mark.asyncio
async def test_plan_replays_failed_relay_before_contact_and_holds_original_expiry(monkeypatch, public_dns):
    harness = Harness(monkeypatch)
    harness.now = NOW
    harness.scan["admission_target_origin"] = ORIGIN
    observations, contacted = [], []

    async def publish(client, scan, observation):
        observations.append(observation)
        return len(observations) > 1

    def target(request):
        contacted.append(request.url.path)
        if len(contacted) == 1:
            return httpx.Response(429, headers={"Retry-After": "60"}, stream=UnreadableBody())
        return httpx.Response(200, stream=httpx.ByteStream(b"fixture site"))

    async def plan(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
            observed = await safe_get_once(client, HOST + "/start", max_decoded_bytes=1024)
            if observed.status_code == 429:
                with pytest.raises(FinalizeProbeSuppressed):
                    await safe_get_once(client, HOST + "/must-not-send", max_decoded_bytes=1024)
        return State()

    harness.deps.plan = plan
    harness.deps.publish_target_cooldown = publish
    with pytest.raises(StageRetry, match="publication is pending"):
        await harness.run("plan")
    assert contacted == ["/start"] and not harness.dispatcher.calls
    outbox = await harness.store.read(harness.prefix + "target-cooldown.json")
    assert outbox.value["pending"] is True

    # A fresh worker must relay the original signal without another fetch.
    harness.runtime = StagedScanRuntime(harness.store, harness.dispatcher, harness.deps, clock=lambda: harness.now)
    harness.now += 1
    with pytest.raises(StageRetry, match="still active") as pending:
        await harness.run("plan")
    assert pending.value.retry_after == 59
    assert observations == [outbox.value["observation"]] * 2
    assert contacted == ["/start"] and not harness.dispatcher.calls
    harness.now = NOW + 60
    await harness.run("plan")
    assert contacted == ["/start", "/start"]
    assert len(observations) == 2


@pytest.mark.asyncio
async def test_optional_relay_failure_keeps_complete_report_and_no_repeated_probe(monkeypatch, public_dns):
    harness = Harness(monkeypatch)
    harness.now = NOW
    harness.scan["admission_target_origin"] = ORIGIN
    observations, probes = [], []

    async def publish(client, scan, observation):
        observations.append(observation)
        return len(observations) > 1

    def target(request):
        probes.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "3600"}, stream=UnreadableBody())

    async def finalize(state, *, allow_optional_probes):
        assert allow_optional_probes is True
        async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
            outcome = await safe_get_once(client, HOST + "/optional", max_decoded_bytes=1024)
            assert outcome.status_code == 429
        return {
            "success": True, "pages": state.pages, "pages_crawled": len(state.pages),
            "crawl_timing": {"optional_checks_notice_reason": "site_rate_limited"},
        }

    harness.deps.publish_target_cooldown = publish
    harness.deps.finalize = finalize
    await harness.run("plan")
    for batch in range(3):
        await harness.run("batch", batch=batch)
    with pytest.raises(StageRetry, match="publication is pending"):
        await harness.run("finalize", batch=3)
    cached = await harness.store.read(harness.prefix + "result.json.gz")
    assert cached.value["pipeline_limited"] is False
    assert cached.value["crawl_timing"]["optional_checks_notice_reason"] == "site_rate_limited"
    assert not harness.results

    harness.runtime = StagedScanRuntime(harness.store, harness.dispatcher, harness.deps, clock=lambda: harness.now)
    await harness.run("finalize", batch=3)
    assert probes == ["/optional"] and len(observations) == 2 and observations[0] == observations[1]
    assert harness.scan["status"] == "complete" and len(harness.results) == 1
    assert harness.results[0]["crawl_timing"]["optional_checks_notice_reason"] == "site_rate_limited"


@pytest.mark.asyncio
async def test_crawl_header_relay_fences_new_contacts_and_checkpoints_its_observation(monkeypatch, public_dns):
    harness = Harness(monkeypatch)
    harness.now = NOW
    harness.scan["admission_target_origin"] = ORIGIN
    entered, failure, next_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    contacts = []

    async def publish(client, scan, observation):
        assert scan["id"] == harness.scan["id"]
        assert (await harness.store.read(harness.prefix + "target-cooldown.json")).value["observation"] == observation
        entered.set()
        await failure.wait()
        return False

    def target(request):
        contacts.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "60"}, stream=UnreadableBody())

    async def crawl(state, *, max_pages):
        async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
            first = asyncio.create_task(safe_get_once(client, HOST + "/crawl", max_decoded_bytes=1024))
            await entered.wait()

            async def next_request():
                next_waiting.set()
                return await safe_get_once(client, HOST + "/already-fenced", max_decoded_bytes=1024)

            later = asyncio.create_task(next_request())
            await next_waiting.wait()
            assert not later.done() and contacts == ["/crawl"]
            failure.set()
            assert (await first).status_code == 429
            with pytest.raises(FinalizeProbeSuppressed):
                await later

    harness.deps.publish_target_cooldown = publish
    harness.deps.crawl = crawl
    await harness.run("plan")
    with pytest.raises(StageRetry, match="publication is pending"):
        await harness.run("batch")
    assert contacts == ["/crawl"] and (await harness.frontier()).value["committed_batches"] == []


@pytest.mark.asyncio
async def test_optional_http_timeout_does_not_include_pending_control_relay(public_dns):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def publish(observation):
        entered.set()
        await finish.wait()
        return True

    def target(request):
        return httpx.Response(429, headers={"Retry-After": "3600"}, stream=UnreadableBody())

    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW, optional=True)
    await relay.resume()
    async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
        with target_cooldown_scope(relay):
            response = await asyncio.wait_for(safe_get_once(client, HOST + "/one", max_decoded_bytes=1024), timeout=1)
            assert response.status_code == 429
            await entered.wait()
            with pytest.raises(FinalizeProbeSuppressed):
                await safe_get_once(client, HOST + "/two", max_decoded_bytes=1024)
    finish.set()
    await relay.require_acknowledged()


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [None, "https://www.example.com:443"])
async def test_legacy_or_different_admitted_origin_does_not_enable_relay(monkeypatch, public_dns, marker):
    harness = Harness(monkeypatch)
    harness.scan["admission_target_origin"] = marker

    async def publish(*args):
        pytest.fail("No claim authorizes relay for this origin")

    def target(request):
        return httpx.Response(429, headers={"Retry-After": "60"}, stream=httpx.ByteStream(b"legacy response"))

    async def plan(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
            response = await safe_get_once(client, HOST + "/start", max_decoded_bytes=1024)
            assert response.status_code == 429 and response.content == b"legacy response"
        return State()

    harness.deps.plan = plan
    harness.deps.publish_target_cooldown = publish
    await harness.run("plan")
    assert (await harness.store.read(harness.prefix + "target-cooldown.json")) is None


@pytest.mark.asyncio
async def test_unexpected_background_error_keeps_verified_429_and_blocks_followup(public_dns):
    async def publish(observation):
        raise RuntimeError("provider client failed")

    def target(request):
        assert request.url.path == "/first"
        return httpx.Response(429, headers={"Retry-After": "60"}, stream=UnreadableBody())

    store = MemoryWorkspace()
    relay = TargetCooldownRelay(store, "scans/scan/a1/", ORIGIN, publish, lambda: NOW)
    await relay.resume()
    async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
        with target_cooldown_scope(relay):
            response = await safe_get_once(client, HOST + "/first", max_decoded_bytes=1024)
            assert response.status_code == 429
            with pytest.raises(FinalizeProbeSuppressed):
                await safe_get_once(client, HOST + "/second", max_decoded_bytes=1024)
    assert (await store.read("scans/scan/a1/target-cooldown.json")).value["pending"] is True
