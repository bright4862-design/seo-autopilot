from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

GROK_CHAT_VERSION = "grok_chat_proxy_v1"
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-non-reasoning").strip()
GROK_LOCATION = os.getenv("VERTEX_LOCATION", "global").strip() or "global"
GROK_TIMEOUT_SECONDS = max(10, int(os.getenv("GROK_TIMEOUT_SECONDS", "90")))


def build_grounded_prompt(message: str, scan: dict[str, Any]) -> str:
    evidence = json.dumps(scan, ensure_ascii=False, separators=(",", ":"))[:120_000]
    return f"""You are FixList AI, an evidence-grounded SEO consultant.

Rules:
1. Treat supplied scan evidence as authoritative only when release_gate_eligible is true.
2. Never invent URLs, counts, findings, owners, or scan outcomes.
3. Never claim a limited or provisional scan is authoritative.
4. Separate confirmed crawl evidence from recommendations.
5. Explain technical SEO in plain language and keep the answer concise.
6. State who should perform a fix when the evidence supports an owner.
7. Do not expose hidden reasoning or chain-of-thought.

SCAN_EVIDENCE:
{evidence}

USER_QUESTION:
{message.strip()}
"""


def extract_output_text(payload: dict[str, Any]) -> str:
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


def _google_access_context() -> tuple[str, str]:
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials, detected_project = google_auth_default(scopes=scopes)
    credentials.refresh(GoogleAuthRequest())
    project_id = (
        os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.getenv("GCP_PROJECT", "").strip()
        or str(detected_project or "").strip()
    )
    if not project_id:
        raise RuntimeError("Cloud Run could not resolve its Google Cloud project.")
    if not credentials.token:
        raise RuntimeError("Cloud Run could not obtain a Google access token.")
    return str(credentials.token), project_id


async def run_grok_chat(message: str, scan: dict[str, Any]) -> str:
    access_token, project_id = await asyncio.to_thread(_google_access_context)
    endpoint = (
        "https://aiplatform.googleapis.com/v1/projects/"
        f"{project_id}/locations/{GROK_LOCATION}/endpoints/openapi/responses"
    )
    payload = {
        "model": GROK_MODEL_ID,
        "input": build_grounded_prompt(message, scan),
        "max_output_tokens": 900,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=GROK_TIMEOUT_SECONDS) as client:
        response = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("Grok returned an unexpected response shape.")
    return extract_output_text(body)
