"""Measurements of the real HTTP request, independent of signing."""

from hashlib import sha256
from time import monotonic

import httpx
import pytest

from app.scan_job import invoke_function
from app.staged_telemetry import DeliveryReceipt, active_delivery
from app.workspace import MemoryWorkspace


@pytest.mark.asyncio
@pytest.mark.parametrize("function", ["persistDurableScanAuthorityV9", "persistLimitedScanResultV9"])
@pytest.mark.parametrize("connection_failed", [False, True])
async def test_receipt_measures_exact_completion_transport_bytes(function, connection_failed):
    store = MemoryWorkspace()
    prefix = "scans/scan_test/a1/"
    job = {"scan_id": "scan_test", "request_id": "request_test", "scan_mode": "standard_500", "page_cap": 500}
    receipt = DeliveryReceipt(store, prefix, job, "finalize", 10, "a" * 32, 5)
    wire = []
    body = {"proof": "signature-only-for-test", "scan": {"label": "é 😀"}}

    async def send(request):
        wire.append(request.content)
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/json"
        assert int(request.headers["content-length"]) == len(request.content)
        assert request.extensions["timeout"]["read"] == 1.25
        assert request.url.path.endswith("/" + function)
        if connection_failed:
            raise httpx.ConnectError("test connection failed", request=request)
        return httpx.Response(202, json={"data": {"success": True}})

    token = active_delivery.set(receipt)
    try:
        receipt.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
            response = await invoke_function(client, function, body, timeout=1.25)
    finally:
        receipt.stop_sampling()
        active_delivery.reset(token)
        await receipt.finish()

    assert response == ({"status_code": 503, "body": {}} if connection_failed else
                        {"status_code": 202, "body": {"success": True}})
    assert wire == [b'{"proof":"signature-only-for-test","scan":{"label":"\xc3\xa9 \xf0\x9f\x98\x80"}}']
    finished = (await store.read(prefix + receipt.finished_ref)).value
    assert finished["completion_request"] == {
        "function": function,
        "body_bytes": len(wire[0]),
        "body_sha256": sha256(wire[0]).hexdigest(),
        "status_code": None if connection_failed else 202,
    }
    assert "signature-only-for-test" not in str(finished)


@pytest.mark.asyncio
async def test_receipt_does_not_start_a_write_near_the_delivery_deadline():
    prefix = "scans/scan_test/a1/"
    job = {"scan_id": "scan_test", "request_id": "request_test", "scan_mode": "standard_500", "page_cap": 500}
    store = MemoryWorkspace()
    receipt = DeliveryReceipt(store, prefix, job, "finalize", 10, "a" * 32, 5)
    receipt.start()
    await receipt.started_write
    receipt.stop_sampling()
    await receipt.finish(deadline=monotonic())

    assert await store.keys(prefix) == [prefix + receipt.started_ref]
