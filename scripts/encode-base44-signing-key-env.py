#!/usr/bin/env python3
"""Encode the canonical signing root for Base44's pinned dotenv parser."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


KEY = b"SCAN_EVIDENCE_SIGNING_KEY"


def _delimiter(payload: bytes) -> bytes | None:
    # dotenv 16.x preserves newlines and surrounding whitespace inside both
    # single-quoted and backtick-quoted values. Unlike double quotes, neither
    # form expands backslash escapes.
    if b"'" not in payload:
        return b"'"
    if b"`" not in payload:
        return b"`"
    return None


def _encode(payload: bytes) -> bytes:
    if not payload or b"\x00" in payload or b"\r" in payload:
        raise ValueError

    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError from exc

    delimiter = _delimiter(payload)
    if delimiter is None:
        raise ValueError

    return KEY + b"=" + delimiter + payload + delimiter + b"\n"


def _write_private(output: Path, rendered: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: encode-base44-signing-key-env.py INPUT OUTPUT", file=sys.stderr)
        return 2

    input_path = Path(argv[1])
    output_path = Path(argv[2])
    try:
        rendered = _encode(input_path.read_bytes())
        _write_private(output_path, rendered)
    except ValueError:
        output_path.unlink(missing_ok=True)
        print(
            "ERROR: signing key cannot be represented exactly by the pinned "
            "Base44 dotenv parser.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
