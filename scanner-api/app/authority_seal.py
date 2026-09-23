"""Canonical authority HMAC primitives shared by the worker and read adapters.

Keep serialization byte-compatible with Base44 authoritySeal.js and historic seals.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return int(value) if value.is_integer() else value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    return None


def stable_serialize(value: Any) -> str:
    return json.dumps(canonicalize(value), separators=(",", ":"), ensure_ascii=False)


def create_authority_seal(payload: Any, secret: str) -> str:
    return hmac.new(secret.encode(), stable_serialize(payload).encode(), hashlib.sha256).hexdigest()
