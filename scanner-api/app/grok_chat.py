from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

GROK_CHAT_VERSION = "grok_chat_proxy_v2"
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-non-reasoning").strip()
GROK_LOCATION = os.getenv("VERTEX_LOCATION", "global").strip() or "global"
GROK_TIMEOUT_SECONDS = max(10, int(os.getenv("GROK_TIMEOUT_SECONDS", "90")))
GROK_MAX_ATTEMPTS = max(1, min(4, int(os.getenv("GROK_MAX_ATTEMPTS", "3"))))
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

LOGGER = logging.getLogger(__name__)


class GrokUpstreamError(RuntimeError):
    def __init__(
        self,
        status_code: int | None,
        error_code: str,
        upstream_message: str,
        *,
        retryable: bool,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code or "UNKNOWN"
        self.upstream_message = upstream_message
        self.retryable = retryable
        super().__init__(self.public_detail)

    @property
    def public_detail(self) -> str:
        status = str(self.status_code) if self.status_code is not None else "network"
        suffix = f"{status}/{self.error_code}"
        if self.status_code in {401, 403}:
            return (
                f"Vertex AI denied the Cloud Run service identity ({suffix}). "
                "Grant the service account used by seo-autopilot-4545 the "
                "Agent Platform User role (roles/aiplatform.user)."
            )
        if self.status_code == 404:
            return (
                f"Grok 4.20 is not enabled or available for this Google Cloud project "
                f"({suffix}). Enable the model in Model Garden for the same project."
            )
        if self.status_code == 429:
            return (
                f"Vertex AI has no available Grok quota ({suffix}). Check the project's "
                "global Grok QPM and token quotas."
            )
        if self.status_code in {500, 502, 503, 504} or self.status_code is None:
            return (
                f"Vertex AI's Grok endpoint is temporarily unavailable ({suffix}) "
                f"after {GROK_MAX_ATTEMPTS} attempts."
            )
        if self.status_code == 400:
            detail = _single_line(self.upstream_message)[:180]
            return (
                f"Vertex AI rejected the Grok request ({suffix})."
                + (f" {detail}" if detail else "")
            )
        return f"Vertex AI rejected the Grok request ({suffix})."


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _response_error(response: httpx.Response) -> GrokUpstreamError:
    error_code = "HTTP_ERROR"
    upstream_message = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            error_code = _single_line(error.get("status")) or error_code
            upstream_message = _single_line(error.get("message"))
        elif isinstance(body.get("detail"), str):
            upstream_message = _single_line(body.get("detail"))
    return GrokUpstreamError(
        response.status_code,
        error_code,
        upstream_message,
        retryable=response.status_code in RETRYABLE_STATUS_CODES,
    )


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
        "store": False,
    }

    last_error: GrokUpstreamError | None = None
    async with httpx.AsyncClient(timeout=GROK_TIMEOUT_SECONDS) as client:
        for attempt in range(1, GROK_MAX_ATTEMPTS + 1):
            try:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.RequestError as exc:
                last_error = GrokUpstreamError(
                    None,
                    "NETWORK_ERROR",
                    str(exc),
                    retryable=True,
                )
            else:
                if response.is_success:
                    body = response.json()
                    if not isinstance(body, dict):
                        raise RuntimeError("Grok returned an unexpected response shape.")
                    return extract_output_text(body)
                last_error = _response_error(response)

            LOGGER.warning(
                "grok_upstream_error status=%s code=%s retryable=%s attempt=%s/%s",
                last_error.status_code,
                last_error.error_code,
                last_error.retryable,
                attempt,
                GROK_MAX_ATTEMPTS,
            )
            if not last_error.retryable or attempt >= GROK_MAX_ATTEMPTS:
                raise last_error
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Grok request ended without a response.")
