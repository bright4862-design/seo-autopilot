"""HTTP header evidence, signed relay, and replay through the staged worker."""

import asyncio
import socket
from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from app import scan_job
from app import scanner
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
from tests import fixtures as fx


ORIGIN = "https://example.com:443"
HOST = "https://example.com"
NOW = 1_790_000_000


@pytest.mark.asyncio
async def test_real_planner_robots_cooldown_stops_unsent_pages(mock_network):
    requests = mock_network({"/robots.txt": {"status": 429, "headers": {"Retry-After": "3600"}}})
    observations = []

    async def publish(observation):
        observations.append(observation)
        return True

    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW)
    with target_cooldown_scope(relay):
        state = await scanner.plan_scan(HOST + "/", scan_mode="standard_150", job_mode=True, staged=True)
        await scanner.crawl_batch(state, max_pages=50)
    await relay.require_acknowledged()
    assert [request.url.path for request in requests] == ["/robots.txt"]
    assert len(observations) == 1
    assert state.limited is True and state.completion_reason == "rate_limit"
    assert state.pages == [] and state.crawl_state["claimed"] == 0
    assert state.scan_coverage_counters == {
        "urls_attempted": 0, "usable_html_pages": 0, "verified_http_failures": 0,
        "access_unverified_pages": 0, "non_html_resources": 0,
    }


@pytest.mark.asyncio
async def test_real_crawl_suppressed_contact_is_not_failed_page(mock_network):
    requests = mock_network({"/robots.txt": {"status": 404}})
    state = await scanner.plan_scan(HOST + "/", path_prefix="/", scan_mode="standard_150", job_mode=True, staged=True)
    requests.clear()

    async def publish(observation):
        return True

    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW)
    response = httpx.Response(429, headers={"Retry-After": "3600"})
    closed = relay.observe_response(httpx.URL(HOST + "/robots.txt"), response)
    closed.set()
    await relay.require_acknowledged()
    with target_cooldown_scope(relay):
        await scanner.crawl_batch(state, max_pages=50)
    assert requests == []
    assert state.pages == [] and state.crawl_state["claimed"] == 0
    assert state.scan_coverage_counters["urls_attempted"] == 0
    assert state.limited is True and state.completion_reason == "rate_limit"
    assert len(state.queue) == 1 and state.seen == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("short_pause", [False, True])
async def test_real_planner_keeps_healthy_and_short_recovered_scans(mock_network, monkeypatch, short_pause):
    routes = {
        "/robots.txt": {"status": 404},
        "/": {"body": "<html><title>Home</title><h1>Home</h1></html>"},
    }
    if short_pause:
        routes["/"] = {"status": 429, "headers": {"Retry-After": "1"}}
    requests = mock_network(routes)
    elapsed, observations = [], []

    async def advance(seconds):
        await relay.drain()
        elapsed.append(seconds)
        routes["/"] = {"body": "<html><title>Home</title><h1>Home</h1></html>"}

    async def publish(observation):
        observations.append(observation)
        return True

    monkeypatch.setattr(scanner.asyncio, "sleep", advance)
    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW + sum(elapsed))
    with target_cooldown_scope(relay):
        state = await scanner.plan_scan(HOST + "/", scan_mode="standard_150", job_mode=True, staged=True)
    await relay.require_acknowledged()
    assert state.limited is False and state.initial_rate_limit_blocked is False
    assert state.initial_rate_limit_retry_count == int(short_pause)
    assert state.initial_rate_limit_recovered is short_pause
    assert len(observations) == int(short_pause)
    assert [request.url.path for request in requests].count("/") == 1 + int(short_pause)


@pytest.mark.asyncio
async def test_suppressed_retry_keeps_actual_429_without_counting_retry(mock_network, monkeypatch):
    routes = {"/robots.txt": {"status": 404}}
    requests = mock_network(routes)
    state = await scanner.plan_scan(HOST + "/", path_prefix="/", scan_mode="standard_150", job_mode=True, staged=True)
    state.concurrency = 1
    routes["/"] = {"status": 429, "headers": {"Retry-After": "1"}}
    requests.clear()

    async def publish(observation):
        return True

    async def premature_wakeup(seconds):
        # The transport fence must still enforce Retry-After if a pacer wakes
        # before the target's independently tracked wall-clock pause expires.
        return None

    monkeypatch.setattr(scanner.asyncio, "sleep", premature_wakeup)
    relay = TargetCooldownRelay(MemoryWorkspace(), "scans/scan/a1/", ORIGIN, publish, lambda: NOW)
    with target_cooldown_scope(relay):
        await scanner.crawl_batch(state)
    assert [request.url.path for request in requests] == ["/"]
    assert len(state.pages) == 1 and state.pages[0]["status_code"] == 429
    assert state.scan_coverage_counters["urls_attempted"] == 1
    assert state.rate_limit_pacer.retry_count == 0
    assert state.rate_limit_pacer.rate_limit_blocked_scan is True


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
async def test_acknowledged_legacy_checkpoint_still_fences_exact_origin(public_dns):
    store, contacts = MemoryWorkspace(), []
    await store.write("scans/scan/a1/target-cooldown.json", {
        "version": "staged_target_cooldown_v1", "pending": False, "hold_until": 0,
        "observation": {"status_code": 429, "target_origin": ORIGIN, "observed_at": NOW, "retry_after_seconds": 3600},
    })

    async def publish(observation):
        pytest.fail("An acknowledged observation must not be republished")

    def target(request):
        contacts.append(request.headers["host"])
        return httpx.Response(200, stream=httpx.ByteStream(b"other origin"))

    relay = TargetCooldownRelay(store, "scans/scan/a1/", ORIGIN, publish, lambda: NOW + 1)
    await relay.resume()
    async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
        with target_cooldown_scope(relay):
            with pytest.raises(FinalizeProbeSuppressed):
                await safe_get_once(client, HOST + "/suppressed")
            assert (await safe_get_once(client, "https://www.example.com/allowed")).status_code == 200
    assert contacts == ["www.example.com"] and relay.remaining_hold() == 3599


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
                "normalized_domain": "example.com", "attempt_count": 2,
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
@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("scenario", ["saved", "missing", "replaced", "uncheckpointed", "invalid", "authority_outage", "expired", "precutoff", "recovered_before_cutoff"])
async def test_prolonged_auxiliary_outage_preserves_cached_report(monkeypatch, public_dns, limited, scenario):
    harness = Harness(monkeypatch)
    harness.now = NOW
    harness.scan["admission_target_origin"] = ORIGIN
    probes, observations = [], []
    relay_available = False

    async def publish(client, scan, observation):
        observations.append(observation)
        return relay_available

    def target(request):
        probes.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "3600"}, stream=UnreadableBody())

    async def finalize(state, *, allow_optional_probes):
        assert allow_optional_probes is True
        async with httpx.AsyncClient(transport=httpx.MockTransport(target)) as client:
            assert (await safe_get_once(client, HOST + "/optional", max_decoded_bytes=1024)).status_code == 429
        return {"success": True, "pages": state.pages, "pages_crawled": len(state.pages),
                "crawl_timing": {"optional_checks_notice_reason": "site_rate_limited"}}

    async def fail(client, scan_id, code, message, *, attempt_count):
        harness.scan.update(status="failed", error_code=code)
        harness.failures.append(code)

    harness.deps.publish_target_cooldown = publish
    harness.deps.finalize, harness.deps.fail = finalize, fail
    await harness.run("plan")
    for batch in range(3):
        await harness.run("batch", batch=batch)
    with pytest.raises(StageRetry, match="publication is pending"):
        await harness.run("finalize", batch=3, limited=limited)
    cached = (await harness.store.read(harness.prefix + "result.json.gz")).value
    assert cached["pipeline_limited"] is limited
    if scenario == "missing":
        await harness.store.delete_prefix(harness.prefix + "result.json.gz")
    elif scenario in {"replaced", "invalid"}:
        snapshot = await harness.store.read(harness.prefix + "result.json.gz")
        replaced = {**cached, "success": False} if scenario == "invalid" else cached
        replacement = await harness.store.write(harness.prefix + "result.json.gz", replaced, generation=snapshot.generation)
        if scenario == "invalid":
            frontier = await harness.frontier()
            await harness.store.write(harness.prefix + "frontier.json", {
                **frontier.value, "target_cooldown_result_generation": replacement,
            }, generation=frontier.generation)
    elif scenario == "uncheckpointed":
        frontier = await harness.frontier()
        value = dict(frontier.value)
        value.pop("target_cooldown_result_generation", None)
        await harness.store.write(harness.prefix + "frontier.json", value, generation=frontier.generation)
    await harness.runtime.request_partial_finalize(None, harness.job)
    if scenario in {"precutoff", "recovered_before_cutoff"}:
        harness.now += 1799
        cutoff = (await harness.frontier()).value["finalize_recovery_until"]
        with pytest.raises(StageRetry, match="publication is pending"):
            await harness.runtime.process(None, "finalize", harness.job, batch=3, recovery_generation=1)
        frontier = (await harness.frontier()).value
        assert frontier["finalize_recovery_until"] == cutoff == NOW + 1800
        assert "finalize_cooldown_fallback_until" not in frontier
        assert "target_cooldown_publication" not in frontier and not harness.results
        if scenario == "recovered_before_cutoff":
            relay_available = True
            assert (await harness.runtime.process(None, "finalize", harness.job, batch=3, recovery_generation=1))["success"] is True
            assert len(harness.results) == 1 and not harness.failures and probes == ["/optional"]
            assert "target_cooldown_publication" not in harness.results[0]["crawl_timing"]
            assert (await harness.store.read(harness.prefix + "target-cooldown.json")).value["pending"] is False
            return
        harness.now -= 1799
    harness.now += 3601 if scenario == "expired" else 2551
    harness.runtime = StagedScanRuntime(harness.store, harness.dispatcher, harness.deps, clock=lambda: harness.now)
    if scenario == "authority_outage":
        persistence = []

        async def unavailable(*args, **kwargs):
            persistence.append(True)
            return {"transient": True}

        harness.deps.complete = unavailable
        with pytest.raises(StageRetry, match="Authority persistence"):
            await harness.runtime.request_partial_finalize(None, harness.job)
        cutoff = (await harness.frontier()).value["finalize_cooldown_fallback_until"]
        assert cutoff == NOW + 3001
        harness.now = cutoff
        with pytest.raises(StageRetry, match="still draining"):
            await harness.runtime.request_partial_finalize(None, harness.job)
        assert (await harness.frontier()).value["finalize_cooldown_fallback_until"] == cutoff
        harness.now += 750
        assert (await harness.runtime.request_partial_finalize(None, harness.job))["error_code"] == "staged_finalize_timeout"
        assert persistence == [True] and not harness.results and probes == ["/optional"]
        return
    outcome = await harness.runtime.request_partial_finalize(None, harness.job)
    if scenario in {"missing", "replaced", "uncheckpointed", "invalid"}:
        assert outcome == {"success": False, "error_code": "staged_finalize_timeout"}
        assert not harness.results and probes == ["/optional"]
        return
    assert outcome["success"] is True and outcome["fix_list_id"] == "list_test"
    assert not harness.failures and probes == ["/optional"]
    assert len(harness.results) == 1 and harness.results[0]["pages"] == cached["pages"]
    assert harness.scan["status"] == ("limited" if limited else "complete")
    notice = harness.results[0]["crawl_timing"]["target_cooldown_publication"]
    expected_state = "expired" if scenario == "expired" else "unconfirmed"
    assert notice["state"] == expected_state
    assert notice["reason"] == ("observation_expired" if scenario == "expired" else "publication_unavailable")
    assert outcome["target_cooldown_publication"] == expected_state
    outbox = await harness.store.read(harness.prefix + "target-cooldown.json")
    assert outbox.value["pending"] is (scenario != "expired")
    assert all(observation == outbox.value["observation"] for observation in observations)
    assert (await harness.runtime.request_partial_finalize(None, harness.job))["skipped"] == "already_terminal"
    assert len(harness.results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limited", [False, True])
async def test_real_optional_canonical_outage_reaches_signed_persistence(mock_network, monkeypatch, limited):
    harness = Harness(monkeypatch)
    harness.now = NOW
    harness.scan["admission_target_origin"] = ORIGIN
    urls = [HOST + f"/products/{index}" for index in range(60)]
    routes = {
        "/robots.txt": {"status": 404},
        "/sitemap.xml": fx._xml(fx._sitemap(urls)),
        "/": fx._html(fx._page("Home", canonical=HOST + "/optional")),
        "/optional": {"status": 429, "headers": {"Retry-After": "3600"}},
        **{url: fx._html(fx._page("Product", canonical=HOST + "/optional")) for url in urls},
    }
    requests = mock_network(routes)
    persistence, signals = [], []

    async def review(result):
        return {"success": True, "release_gate_eligible": True, "recommendations": []}

    async def invoke(client, name, envelope, **kwargs):
        payload = {key: value for key, value in envelope.items() if key != "proof"}
        assert envelope["proof"] == scan_job.create_authority_seal(payload, "test-only-key")
        if name == "durableScanWorkerControlV9":
            assert envelope["action"] == "observe_target_cooldown"
            assert envelope["identity"]["attempt_count"] == 1
            signals.append(envelope["target_cooldown"])
            return {"status_code": 503, "body": {"error_code": "target_cooldown_publish_unavailable"}}
        assert name == ("persistLimitedScanResultV9" if limited else "persistDurableScanAuthorityV9")
        assert envelope["scan"]["crawl_timing"]["target_cooldown_publication"]["state"] == "unconfirmed"
        persistence.append(envelope)
        harness.scan["status"] = "limited" if limited else "complete"
        return {"status_code": 200, "body": {
            "success": True, "fixListId": "list_test", "resultIntegrityVerified": True,
            "fixListVerified": True, "scanRun": {**harness.scan, "authority_proof": "a" * 64},
        }}

    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    monkeypatch.setattr(scan_job, "read_scan_run", harness.read)
    harness.deps.state_type, harness.deps.plan = scanner.ScanState, scanner.plan_scan
    harness.deps.crawl, harness.deps.finalize = scanner.crawl_batch, scanner.finalize_scan
    harness.deps.complete, harness.deps.review = scan_job.complete_authority, review
    harness.deps.publish_target_cooldown = scan_job.publish_target_cooldown
    with scan_job.worker_function_generation("V9"):
        await harness.run("plan")
        await harness.run("batch", batch=0)
        if limited:
            harness.now += 601
        await harness.run("batch", batch=1)
        with pytest.raises(StageRetry, match="publication is pending"):
            await harness.run("finalize", batch=2)
        assert len([request for request in requests if request.url.path == "/optional"]) == 1
        contacts = len(requests)
        await harness.runtime.request_partial_finalize(None, harness.job)
        harness.now += 2551
        harness.runtime = StagedScanRuntime(harness.store, harness.dispatcher, harness.deps, clock=lambda: harness.now)
        assert (await harness.runtime.request_partial_finalize(None, harness.job))["success"] is True
    assert len(requests) == contacts and len(persistence) == 1
    assert persistence[0]["scan"]["pages_crawled"] == (50 if limited else 61)
    assert len(signals) == 2 and signals[0] == signals[1]
    assert not harness.failures


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
