from __future__ import annotations

from typing import Any, Mapping


# Internal-only scalar added by the hardened bounded fetch boundary after the
# response body has actually been read. Remote responses are not authoritative
# for this header: security.py strips any server-supplied value and overwrites it
# with the byte count observed from aiter_raw().
TRANSFER_BODY_BYTES_HEADER = "x-fixlist-transfer-body-bytes"
TRANSFER_BODY_BYTES_BASIS = "raw_response_body_before_content_decoding"


def measured_transfer_body_bytes(headers: Mapping[str, Any] | None) -> int | None:
    """Return a bounded non-negative internal transfer-body measurement.

    This is response-body payload bytes observed before gzip/deflate decoding.
    It intentionally does not claim HTTP headers, TLS overhead, or chunk framing,
    and it never falls back to Content-Length or decoded HTML length.
    """
    if not headers:
        return None
    raw = next(
        (
            value
            for key, value in headers.items()
            if str(key or "").strip().lower() == TRANSFER_BODY_BYTES_HEADER
        ),
        None,
    )
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    if len(values) != 1:
        return None
    text = str(values[0] if values else "").strip()
    if not text or not text.isdigit():
        return None
    try:
        value = int(text)
    except (TypeError, ValueError, OverflowError):
        return None
    # Scanner responses are already bounded to 5 MB decoded content. The raw
    # representation can be slightly larger for incompressible encoded data,
    # but an absurd integer here is never accepted as measured evidence.
    if value < 0 or value > 25_000_000:
        return None
    return value
