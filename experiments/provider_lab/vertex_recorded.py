from __future__ import annotations

from typing import Any

from .vertex_contract import CURRENT_VERTEX_CONTRACT


def extract_recorded_output(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for output_item in payload.get("output", []) or []:
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []) or []:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    if chunks:
        return "\n\n".join(chunks)
    raise RuntimeError("Grok returned no readable text output.")


def is_retryable_status(status_code: int) -> bool:
    return int(status_code) in CURRENT_VERTEX_CONTRACT.retryable_status_codes
