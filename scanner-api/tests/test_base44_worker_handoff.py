import httpx
import pytest

from app import scan_job


class _Response:
    def __init__(self, status_code=403, headers=None, body=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body or {}

    def json(self):
        return self._body


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def test_base44_worker_headers_include_stable_browser_compatible_user_agent():
    headers = scan_job._service_headers()
    assert headers["content-type"] == "application/json"
    assert headers["X-FixList-Worker"] == scan_job.WORKER_VERSION
    assert headers["User-Agent"] == scan_job.BASE44_WORKER_USER_AGENT
    assert "Mozilla/5.0" in headers["User-Agent"]
    assert "FixListStandard150Worker/1.0" in headers["User-Agent"]


@pytest.mark.asyncio
async def test_invoke_function_emits_only_safe_base44_handoff_metadata(monkeypatch):
    events = []

    def capture(event, **fields):
        events.append((event, fields))
        return fields

    monkeypatch.setattr(scan_job, "emit", capture)
    response = _Response(
        status_code=403,
        headers={
            "content-type": "text/html; charset=UTF-8",
            "cf-ray": "abc123-CDG",
            "x-request-id": "base44-safe-request-id",
        },
        body={"ignored": True},
    )
    client = _Client(response=response)
    payload = {
        "scan_id": "customer-scan-must-not-log",
        "proof": "super-secret-proof-must-not-log",
        "customer_data": "must-not-log",
    }

    result = await scan_job.invoke_function(client, "durableScanWorkerControl", payload)

    assert result["status_code"] == 403
    assert len(client.calls) == 1
    _url, call = client.calls[0]
    assert call["headers"]["User-Agent"] == scan_job.BASE44_WORKER_USER_AGENT

    assert len(events) == 1
    event, fields = events[0]
    assert event == "base44_function_handoff"
    assert fields == {
        "severity": "WARNING",
        "function": "durableScanWorkerControl",
        "response_status": 403,
        "content_type": "text/html",
        "base44_request_id": "base44-safe-request-id",
        "cloudflare_ray_id": "abc123-CDG",
    }
    rendered = repr(events)
    assert "customer-scan-must-not-log" not in rendered
    assert "super-secret-proof-must-not-log" not in rendered
    assert "customer_data" not in rendered


@pytest.mark.asyncio
async def test_invoke_function_reports_transport_error_class_without_payload(monkeypatch):
    events = []

    def capture(event, **fields):
        events.append((event, fields))
        return fields

    monkeypatch.setattr(scan_job, "emit", capture)
    error = httpx.ConnectError("private upstream detail")
    client = _Client(error=error)

    result = await scan_job.invoke_function(
        client,
        "durableScanWorkerControl",
        {"proof": "must-not-log", "scan_id": "must-not-log"},
    )

    assert result == {"status_code": 503, "body": {}}
    assert events == [
        (
            "base44_function_handoff",
            {
                "severity": "WARNING",
                "function": "durableScanWorkerControl",
                "transport_error_class": "ConnectError",
            },
        )
    ]
