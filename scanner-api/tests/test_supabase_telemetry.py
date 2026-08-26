import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from app import supabase_telemetry as telemetry


def scan_result() -> dict:
    return {
        "success": True,
        "scanner_version": "python_scanner_v3_bounded_request",
        "scanner_build_revision": "candidate-17-v5",
        "scan_mode": "advanced",
        "scanner_elapsed_ms": 1234,
        "scan_deadline_reached": False,
        "pages_crawled": 3,
        "pages_found": 9,
        "health_score": 81,
        "website_url": "https://customer.example/private?email=owner@example.com",
        "business_name": "Private Customer Ltd",
        "owner_user_id": "owner-private-123",
        "request_id": "request-private-123",
        "idempotency_key": "idempotency-private-123",
        "authority_proof": "authority-private-secret",
        "sampling_evidence": {
            "sampling_version": "balanced_sitemap_buckets_v1",
            "sitemap_urls_discovered": 9,
            "sitemap_urls_sampled": 3,
            "family_totals": {"product_page": 6, "standard": 3},
            "family_sampled": {"product_page": 2, "standard": 1},
            "families_never_sampled": ["legal_page"],
            "trust_pages_in_sitemap": 1,
            "trust_pages_sampled": 1,
            "crawl_scope": {
                "requested_origin": "https://customer.example",
                "requested_seed_path": "/private",
            },
        },
        "crawl_timing": {
            "failure_reason_buckets": {"http_429": 1, "network_error": 2},
        },
        "pages": [
            {
                "url": "https://customer.example/private-a",
                "final_url": "https://customer.example/private-a",
                "status_code": 200,
                "page_template_family": "product_page",
                "title": "Private product",
                "_html": "<html>customer secret</html>",
            },
            {
                "url": "https://customer.example/private-b",
                "status_code": 429,
                "page_template_family": "product_page",
                "fetch_error": "blocked_rate_limit",
            },
            {
                "url": "https://customer.example/private-c",
                "status_code": 0,
                "estimated_page_intent": "standard",
                "fetch_error": "network_error",
            },
        ],
        "findings": [
            {
                "rule": "missing_meta_description",
                "category": "meta_description",
                "priority": "medium",
                "title": "Private finding title",
                "recommendation": "Customer-only recommendation",
                "page_url": "https://customer.example/private-a",
            },
            {
                "rule": "rate_limited_page",
                "category": "web_dev",
                "priority": "high",
                "current_value": "Bearer customer-secret-token",
            },
        ],
    }


def enable(monkeypatch) -> None:
    monkeypatch.setenv("SCANNER_SUPABASE_TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("SCANNER_TELEMETRY_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SCANNER_TELEMETRY_SUPABASE_SECRET_KEY", "server-test-key")


def test_payload_contains_only_allowlisted_aggregate_scanner_evidence():
    result = scan_result()

    payload = telemetry.build_scan_telemetry("scan-123", result)

    assert payload == {
        "scan_id": "scan-123",
        "telemetry_version": "scanner_supabase_telemetry_v1",
        "outcome": "complete",
        "scanner_version": "python_scanner_v3_bounded_request",
        "scanner_build_revision": "candidate-17-v5",
        "scan_mode": "advanced",
        "scanner_elapsed_ms": 1234,
        "scan_deadline_reached": False,
        "pages_crawled": 3,
        "pages_found": 9,
        "health_score": 81,
        "page_type_counts": {"product_page": 2, "standard": 1},
        "response_class_counts": {"2xx": 1, "4xx": 1, "unfetched": 1},
        "failure_reason_counts": {"http_429": 1, "network_error": 2},
        "issue_counts": {
            "total": 2,
            "by_priority": {"high": 1, "medium": 1},
            "by_category": {"meta_description": 1, "web_dev": 1},
            "by_rule": {"missing_meta_description": 1, "rate_limited_page": 1},
        },
        "sampling_decisions": {
            "sampling_version": "balanced_sitemap_buckets_v1",
            "sitemap_urls_discovered": 9,
            "sitemap_urls_sampled": 3,
            "family_totals": {"product_page": 6, "standard": 3},
            "family_sampled": {"product_page": 2, "standard": 1},
            "families_never_sampled": ["legal_page"],
            "trust_pages_in_sitemap": 1,
            "trust_pages_sampled": 1,
        },
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "customer.example",
        "owner@example.com",
        "Private Customer Ltd",
        "Private product",
        "customer secret",
        "Private finding title",
        "Customer-only recommendation",
        "customer-secret-token",
        "owner-private-123",
        "request-private-123",
        "idempotency-private-123",
        "authority-private-secret",
        "requested_origin",
        "requested_seed_path",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_default_off_never_opens_a_supabase_client(monkeypatch):
    monkeypatch.delenv("SCANNER_SUPABASE_TELEMETRY_ENABLED", raising=False)

    class ForbiddenClient:
        def __init__(self, **_kwargs):
            raise AssertionError("disabled telemetry opened an HTTP client")

    monkeypatch.setattr(telemetry.httpx, "AsyncClient", ForbiddenClient)

    assert await telemetry.persist_scan_telemetry("scan-123", scan_result()) is False
    assert telemetry.schedule_scan_telemetry("scan-123", scan_result()) is False
    assert telemetry.pending_telemetry_task_count() == 0


@pytest.mark.asyncio
async def test_writer_uses_one_idempotent_post_and_never_reads(monkeypatch):
    enable(monkeypatch)
    request = {}
    events = []

    class Response:
        status_code = 201

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            request["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            raise AssertionError("scanner telemetry must never read from Supabase")

        async def post(self, url, **kwargs):
            request["url"] = url
            request.update(kwargs)
            return Response()

    monkeypatch.setattr(telemetry.httpx, "AsyncClient", Client)
    monkeypatch.setattr(telemetry, "emit", lambda event, **fields: events.append((event, fields)))

    original = scan_result()
    before = copy.deepcopy(original)
    assert await telemetry.persist_scan_telemetry("scan-123", original) is True
    assert original == before
    assert request["url"] == "https://project.supabase.co/rest/v1/scanner_telemetry_v1"
    assert request["params"] == {"on_conflict": "scan_id"}
    assert request["headers"] == {
        "apikey": "server-test-key",
        "Authorization": "Bearer server-test-key",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    assert request["json"]["scan_id"] == "scan-123"
    assert request["client_kwargs"]["follow_redirects"] is False
    assert request["client_kwargs"]["trust_env"] is False
    assert events == [
        (
            "scanner_supabase_telemetry_persisted",
            {"scan_id": "scan-123", "telemetry_version": "scanner_supabase_telemetry_v1"},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("offline"), "transport_error"),
        (
            httpx.HTTPStatusError(
                "service unavailable",
                request=httpx.Request("POST", "https://project.supabase.co/rest/v1/scanner_telemetry_v1"),
                response=httpx.Response(503),
            ),
            "http_error",
        ),
    ],
)
async def test_timeout_or_outage_is_fail_open_and_logs_only_a_safe_reason(monkeypatch, failure, reason):
    enable(monkeypatch)
    events = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise failure

    monkeypatch.setattr(telemetry.httpx, "AsyncClient", Client)
    monkeypatch.setattr(telemetry, "emit", lambda event, **fields: events.append((event, fields)))

    result = scan_result()
    before = copy.deepcopy(result)
    assert await telemetry.persist_scan_telemetry("scan-123", result) is False
    assert result == before
    assert events == [
        (
            "scanner_supabase_telemetry_warning",
            {
                "severity": "WARNING",
                "scan_id": "scan-123",
                "telemetry_version": "scanner_supabase_telemetry_v1",
                "reason": reason,
            },
        ),
    ]
    assert "sb_secret" not in json.dumps(events)


@pytest.mark.asyncio
async def test_scheduler_is_detached_and_holds_task_until_completion(monkeypatch):
    enable(monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()

    async def persist(_payload):
        started.set()
        await release.wait()
        return True

    monkeypatch.setattr(telemetry, "_persist_payload", persist)
    result = scan_result()
    before = copy.deepcopy(result)

    assert telemetry.schedule_scan_telemetry("scan-123", result) is True
    await asyncio.wait_for(started.wait(), timeout=0.2)
    assert telemetry.pending_telemetry_task_count() == 1
    assert result == before

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert telemetry.pending_telemetry_task_count() == 0


def test_migration_denies_client_roles_and_uses_scan_id_as_the_upsert_key():
    repository_root = Path(__file__).resolve().parents[2]
    migration = (repository_root / "supabase/migrations/202608260001_scanner_telemetry_v1.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(migration.lower().split())

    assert "scan_id text primary key" in normalized
    assert "alter table public.scanner_telemetry_v1 enable row level security" in normalized
    assert "revoke all on table public.scanner_telemetry_v1 from anon, authenticated" in normalized
    assert "grant insert, update on table public.scanner_telemetry_v1 to service_role" in normalized
    assert "create policy" not in normalized
