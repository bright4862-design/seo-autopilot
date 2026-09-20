import gzip
import ipaddress
import socket

import httpx
import pytest

from app.page_evidence_gate import access_block_header_evidence
from app.scanner import fetch_and_extract
from app.security import safe_get_once
from app.stage2_coverage_evidence import page_weight_evidence
from app.transport_evidence import (
    TRANSFER_BODY_BYTES_BASIS,
    TRANSFER_BODY_BYTES_HEADER,
    measured_transfer_body_bytes,
)


def _answer(address: str, port: int):
    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET if parsed.version == 4 else socket.AF_INET6
    sockaddr = (address, port) if family == socket.AF_INET else (address, port, 0, 0)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def _public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )


def _discovery():
    return {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []}


@pytest.mark.asyncio
async def test_b17_compressed_body_uses_observed_raw_bytes_not_decoded_length_or_remote_header(monkeypatch):
    _public_dns(monkeypatch)
    payload = (
        b"<html><head><title>Measured</title></head><body><main><h1>Measured</h1>"
        + (b"compressible page content " * 120)
        + b"</main></body></html>"
    )
    compressed = gzip.compress(payload)
    assert len(compressed) < len(payload)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
                # A remote site is not allowed to assert FixList's measurement.
                TRANSFER_BODY_BYTES_HEADER: "999999",
                "content-length": "999999",
            },
            stream=httpx.ByteStream(compressed),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        page = await fetch_and_extract(client, "https://bytes.example/page", _discovery())

    assert page["page_evidence_class"] == "usable_html"
    assert page["transfer_bytes_state"] == "measured"
    assert page["transfer_bytes"] == len(compressed)
    assert page["transfer_bytes"] != page["decoded_bytes"]
    assert page["decoded_bytes"] == len(payload)
    assert page["transfer_bytes_basis"] == TRANSFER_BODY_BYTES_BASIS


@pytest.mark.asyncio
async def test_security_boundary_overwrites_remote_measurement_and_keeps_it_out_of_access_headers(monkeypatch):
    _public_dns(monkeypatch)
    payload = b"<html><body>plain body</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html",
                TRANSFER_BODY_BYTES_HEADER: "777777",
                "server": "example-origin",
            },
            stream=httpx.ByteStream(payload),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        response = await safe_get_once(
            client,
            "https://spoofed-bytes.example/page",
            max_decoded_bytes=1024,
        )

    assert response.headers[TRANSFER_BODY_BYTES_HEADER] == str(len(payload))
    assert measured_transfer_body_bytes(response.headers) == len(payload)
    persisted = access_block_header_evidence(
        {
            "server": "example-origin",
            TRANSFER_BODY_BYTES_HEADER: str(len(payload)),
        }
    )
    assert persisted == {"server": "example-origin"}


@pytest.mark.asyncio
async def test_b17_access_limited_response_keeps_page_weight_transfer_unknown(monkeypatch):
    _public_dns(monkeypatch)
    body = b"<html><body>rate limited</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "text/html", "retry-after": "1"},
            stream=httpx.ByteStream(body),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        page = await fetch_and_extract(client, "https://limited-bytes.example/page", _discovery())

    assert page["page_evidence_class"] == "failed_access"
    assert page["transfer_bytes"] is None
    assert page["transfer_bytes_state"] == "unknown"


def test_b17_known_zero_is_distinct_from_unknown_without_using_content_length():
    assert measured_transfer_body_bytes({TRANSFER_BODY_BYTES_HEADER: "0"}) == 0
    assert measured_transfer_body_bytes({}) is None
    assert measured_transfer_body_bytes({"content-length": "0"}) is None

    measured = page_weight_evidence(
        decoded_bytes=None,
        inline_script_bytes=None,
        inline_style_bytes=None,
        transfer_bytes=0,
        transfer_measured=True,
    )
    unknown = page_weight_evidence(
        decoded_bytes=None,
        inline_script_bytes=None,
        inline_style_bytes=None,
        transfer_bytes=0,
        transfer_measured=False,
    )
    assert measured["transfer_bytes"] == 0
    assert measured["transfer_bytes_state"] == "measured"
    assert unknown["transfer_bytes"] is None
    assert unknown["transfer_bytes_state"] == "unknown"
