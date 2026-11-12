"""Bounded Python/V8 canonical JSON for future GEO authority inputs.

This is deliberately narrower than a general-purpose JSON canonicalization
scheme. GEO transport keys are ASCII contract identifiers and its numeric
values are safe integers or bounded decimal measurements. Rejecting values
outside that domain prevents Python and V8 from silently signing different
bytes for the same parsed payload.
"""
from __future__ import annotations

from decimal import Decimal
import json
import math


VERSION = "geo_v8_canonical_json_v1"

_MAX_SAFE_INTEGER = (2**53) - 1
_MIN_PLAIN_DECIMAL = 1e-6
_MAX_PLAIN_DECIMAL = 1e21
_MAX_DECIMAL_PLACES = 6


def _canonical_number(value: int | float) -> str:
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValueError("Unsupported canonical JSON number outside safe-integer range")
        return str(value)

    if not math.isfinite(value):
        raise ValueError("Unsupported canonical JSON number must be finite")
    if value == 0:
        return "0"
    if value.is_integer():
        integer = int(value)
        if abs(integer) > _MAX_SAFE_INTEGER:
            raise ValueError("Unsupported canonical JSON number outside safe-integer range")
        return str(integer)

    magnitude = abs(value)
    if magnitude < _MIN_PLAIN_DECIMAL or magnitude >= _MAX_PLAIN_DECIMAL:
        raise ValueError("Unsupported canonical JSON number outside bounded decimal range")
    if round(value, _MAX_DECIMAL_PLACES) != value:
        raise ValueError("Unsupported canonical JSON number exceeds six decimal places")

    rendered = repr(value).lower()
    if "e" in rendered:
        rendered = format(Decimal(rendered), "f")
    return rendered


def _canonical_text(value) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float):
        return _canonical_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_text(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = list(value)
        if any(not isinstance(key, str) or not key.isascii() for key in keys):
            raise ValueError("Canonical GEO JSON requires ASCII object keys")
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical_text(value[key])}"
            for key in sorted(keys)
        ) + "}"
    raise ValueError("Unsupported canonical GEO JSON value")


def canonical_json_bytes(value) -> bytes:
    """Return deterministic UTF-8 JSON bytes for the bounded GEO domain."""
    return _canonical_text(value).encode("utf-8")
