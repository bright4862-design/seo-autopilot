from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

GROK_CHAT_VERSION = "grok_chat_proxy_v3_natural_diy"
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


def _conversation_context(history: list[dict[str, Any]] | None) -> str:
    turns: list[dict[str, str]] = []
    for item in (history or [])[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        clean_content = content.strip()
        if not clean_content:
            continue
        turns.append({"role": role, "content": clean_content[:2_000]})
    return json.dumps(turns, ensure_ascii=False, separators=(",", ":"))[:12_000]


def build_grounded_prompt(
    message: str,
    scan: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> str:
    evidence = json.dumps(scan, ensure_ascii=False, separators=(",", ":"))[:120_000]
    conversation = _conversation_context(history)
    return f"""You are Grok inside FixList, a practical SEO consultant helping a real person improve their website.

Voice and approach:
- Sound like a thoughtful human adviser: natural, direct, warm, and confident.
- Answer the user's actual question first. Do not begin every reply with a scan recap or a canned phrase such as "Based on the evidence."
- Use contractions and varied sentence structure. Avoid corporate language, repetitive disclaimers, and report-like filler.
- Match the detail to the request. A quick question can get a quick answer; an implementation request deserves usable steps.
- Use headings, bullets, or numbered steps only when they make the answer easier to follow.

Evidence and honesty:
1. Treat supplied scan evidence as authoritative only when release_gate_eligible is true.
2. Never invent URLs, counts, findings, owners, or scan outcomes.
3. A clickable example URL is verified only when it appears exactly in a finding's verified_urls or url_evidence with status_code 200. Never construct, complete, modify, or guess a URL from a page title, template, path pattern, hostname, or conversation.
4. If a finding has no verified URL, say that the current crawl did not return a verified live example. Do not substitute a plausible URL.
5. Never present a 404/410 URL as a live page to edit. If discussing a confirmed broken-URL finding, label the URL as broken rather than as a working example.
6. Never claim a limited or provisional scan is authoritative.
7. Separate confirmed crawl evidence from recommendations.
8. You may answer broader SEO, CMS, website, and implementation questions using general expertise. Clearly distinguish general guidance from facts confirmed by this scan.
9. If a detail depends on an unknown CMS, theme, plugin, hosting setup, or codebase, give the most likely options and ask at most one short clarifying question when it is genuinely needed.

Implementation and DIY support:
10. Never use an owner label such as "Web developer" as a reason to withhold instructions.
11. If the user wants to do a fix themselves, help them do it. Start with a clear "yes", "yes, with care", or "this is risky without access/experience", then provide the safest practical route.
12. For hands-on instructions, include the prerequisites or backup, the exact settings/files/code pattern to change, the implementation steps, and how to verify the result. Include a rollback note when a change could break templates, routing, indexing, or production behavior.
13. Adapt instructions to the detected platform when the scan supports one. If the platform is unknown, give concise WordPress, Shopify, and custom-site variants where useful.
14. If a developer is still recommended, explain why and name the specific risky portion, while continuing to explain everything the user can safely do themselves.
15. Use the conversation context to understand follow-ups such as "Can I do this myself?", "How?", or "What about the next one?"
16. Do not expose hidden reasoning or chain-of-thought.

CONVERSATION_CONTEXT:
{conversation}

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


async def run_grok_chat(
    message: str,
    scan: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> str:
    access_token, project_id = await asyncio.to_thread(_google_access_context)
    endpoint = (
        "https://aiplatform.googleapis.com/v1/projects/"
        f"{project_id}/locations/{GROK_LOCATION}/endpoints/openapi/responses"
    )
    payload = {
        "model": GROK_MODEL_ID,
        "input": build_grounded_prompt(message, scan, history),
        "max_output_tokens": 1_600,
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
