from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import gradio as gr
import requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location: str = os.getenv("VERTEX_LOCATION", "global").strip() or "global"
    model_id: str = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-reasoning").strip()
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    request_timeout_seconds: int = 90

    @property
    def live_grok_enabled(self) -> bool:
        return bool(self.project_id and self.service_account_json)


SETTINGS = Settings()

DEMO_SCAN: dict[str, Any] = {
    "website": "https://www.funbooker.com/",
    "status": "Complete",
    "score": 68,
    "pages_found": 1200,
    "pages_crawled": 150,
    "pages_retained": 150,
    "grouped_fixes": 9,
    "release_gate_eligible": True,
    "scanner_backend": "Python scanner",
    "review_backend": "Python review",
    "fallbacks_used": False,
    "priorities": [
        {
            "title": "Update redirected internal links",
            "priority": "High",
            "owner": "Web developer",
            "affected_pages": 18,
            "why": "Direct internal links reduce unnecessary hops and make crawling more efficient.",
        },
        {
            "title": "Add useful meta descriptions",
            "priority": "High",
            "owner": "Content team",
            "affected_pages": 42,
            "why": "Clear descriptions can improve search-result messaging and click-through rate.",
        },
        {
            "title": "Add structured data to conversion templates",
            "priority": "Medium",
            "owner": "Web developer",
            "affected_pages": 2,
            "why": "Structured data gives search engines clearer information about page purpose.",
        },
    ],
    "limitations": [
        "This is a 150-page acceptance-scan demo.",
        "Grok may explain and prioritize persisted evidence but must not alter crawl facts.",
    ],
}


def scan_markdown(scan: dict[str, Any]) -> str:
    gate = "Authoritative" if scan.get("release_gate_eligible") else "Limited"
    fallback = "None" if not scan.get("fallbacks_used") else "Used"
    return f"""
<div class="summary">
  <div class="eyebrow">CURRENT SCAN</div>
  <h2>{scan['website']}</h2>
  <div class="score-row">
    <div><span class="score">{scan['score']}</span><span class="muted">/100</span></div>
    <span class="status">{gate}</span>
  </div>
  <div class="metric-grid">
    <div><strong>{scan['pages_crawled']}</strong><span>crawled</span></div>
    <div><strong>{scan['pages_retained']}</strong><span>retained</span></div>
    <div><strong>{scan['grouped_fixes']}</strong><span>grouped fixes</span></div>
    <div><strong>{fallback}</strong><span>fallbacks</span></div>
  </div>
</div>
"""


def priority_markdown(scan: dict[str, Any]) -> str:
    items = []
    for index, fix in enumerate(scan["priorities"], start=1):
        items.append(
            f"""
<div class="priority">
  <div class="priority-index">{index}</div>
  <div>
    <strong>{fix['title']}</strong>
    <p>{fix['priority']} · {fix['owner']} · {fix['affected_pages']} pages</p>
  </div>
</div>
"""
        )
    return '<div class="eyebrow">TOP PRIORITIES</div>' + "".join(items)


def build_grounded_prompt(message: str, scan: dict[str, Any]) -> str:
    evidence = json.dumps(scan, ensure_ascii=False, separators=(",", ":"))
    return f"""You are FixList AI, an evidence-grounded SEO consultant.

Rules:
1. Treat the supplied scan evidence as authoritative.
2. Never invent URLs, counts, findings, or scan outcomes.
3. Never claim a limited or provisional scan is authoritative.
4. Explain technical SEO in plain language.
5. Distinguish confirmed crawl evidence from recommendations.
6. Keep answers concise and organized.
7. When useful, state who should perform the fix.
8. Do not expose hidden reasoning or chain-of-thought.

SCAN_EVIDENCE:
{evidence}

USER_QUESTION:
{message}
"""


def load_google_credentials() -> Any:
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if SETTINGS.service_account_json:
        info = json.loads(SETTINGS.service_account_json)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    credentials, _ = google_auth_default(scopes=scopes)
    return credentials


def extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for output_item in payload.get("output", []) or []:
        for content_item in output_item.get("content", []) or []:
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())

    if chunks:
        return "\n\n".join(chunks)

    raise RuntimeError("Grok returned no readable text output.")


def call_grok(message: str, scan: dict[str, Any]) -> str:
    credentials = load_google_credentials()
    credentials.refresh(GoogleAuthRequest())

    endpoint = (
        "https://aiplatform.googleapis.com/v1/projects/"
        f"{SETTINGS.project_id}/locations/{SETTINGS.location}/endpoints/openapi/responses"
    )
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        json={
            "model": SETTINGS.model_id,
            "input": build_grounded_prompt(message, scan),
            "max_output_tokens": 900,
            "stream": False,
        },
        timeout=SETTINGS.request_timeout_seconds,
    )
    response.raise_for_status()
    return extract_output_text(response.json())


def demo_answer(message: str, scan: dict[str, Any]) -> str:
    normalized = message.lower()

    if "first" in normalized or "priority" in normalized:
        fix = scan["priorities"][0]
        return (
            f"Start with **{fix['title']}**.\n\n"
            f"It affects **{fix['affected_pages']} pages** and should go to your "
            f"**{fix['owner'].lower()}**. {fix['why']}"
        )

    if "score" in normalized:
        return (
            f"The demo score is **{scan['score']}/100**. The biggest visible deductions "
            "come from repeated internal redirects, missing meta descriptions, and incomplete "
            "structured data. The first two affect the largest number of pages."
        )

    if "myself" in normalized or "developer" in normalized or "who" in normalized:
        return (
            "The **meta descriptions** can usually be handled by a content or SEO editor. "
            "The **redirected internal links** and **structured data** are better assigned "
            "to a web developer because they may be generated by shared templates."
        )

    if "affected" in normalized or "pages" in normalized:
        return (
            "This demo groups repeated issues instead of listing every page in the chat. "
            "The current priorities affect **18**, **42**, and **2** pages respectively. "
            "In the production version, selecting a fix will open its exact persisted URLs."
        )

    return (
        f"This authoritative demo scan retained **{scan['pages_retained']} pages** and produced "
        f"**{scan['grouped_fixes']} grouped fixes**. The clearest starting point is updating "
        "redirected internal links, followed by improving meta descriptions. Ask me to explain "
        "the score, assign the work, or summarize the priorities."
    )


def chat(message: str, history: list[dict[str, Any]] | None) -> str:
    del history
    clean_message = (message or "").strip()
    if not clean_message:
        return "Ask a question about the current scan."

    if SETTINGS.live_grok_enabled:
        try:
            return call_grok(clean_message, DEMO_SCAN)
        except Exception as exc:
            return (
                "Live Grok mode could not complete this request, so I kept the interface "
                f"available in demo mode.\n\n`{type(exc).__name__}: {str(exc)[:180]}`\n\n"
                + demo_answer(clean_message, DEMO_SCAN)
            )

    return demo_answer(clean_message, DEMO_SCAN)


CSS = """
:root {
  --surface: #ffffff;
  --background: #f6f7f5;
  --ink: #17201b;
  --muted: #6d756f;
  --line: #e3e7e3;
  --accent: #1f7a4d;
}
.gradio-container {
  max-width: 1500px !important;
  margin: 0 auto !important;
  background: var(--background) !important;
  color: var(--ink) !important;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
.main-shell { min-height: 88vh; }
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 18px;
}
.brand {
  font-weight: 760;
  font-size: 20px;
  letter-spacing: -0.03em;
  margin-bottom: 24px;
}
.nav-item {
  padding: 11px 12px;
  border-radius: 10px;
  color: var(--muted);
  margin: 3px 0;
}
.nav-item.active {
  background: #edf5ef;
  color: var(--accent);
  font-weight: 650;
}
.eyebrow {
  color: var(--muted);
  font-size: 11px;
  font-weight: 760;
  letter-spacing: .12em;
  margin-bottom: 10px;
}
.summary h2 {
  margin: 0;
  font-size: 18px;
  letter-spacing: -0.03em;
  word-break: break-word;
}
.score-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 22px 0;
}
.score { font-size: 40px; font-weight: 760; letter-spacing: -0.06em; }
.muted { color: var(--muted); }
.status {
  border: 1px solid #b9d8c5;
  color: var(--accent);
  background: #f0f8f2;
  padding: 6px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 650;
}
.metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.metric-grid div {
  border-top: 1px solid var(--line);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
}
.metric-grid strong { font-size: 18px; }
.metric-grid span { color: var(--muted); font-size: 12px; }
.priority {
  display: flex;
  gap: 10px;
  border-top: 1px solid var(--line);
  padding: 13px 0;
}
.priority-index {
  width: 24px;
  height: 24px;
  border: 1px solid var(--line);
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
}
.priority p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
footer { display: none !important; }
@media (max-width: 900px) {
  .main-shell { display: block !important; }
}
"""


with gr.Blocks(
    title="FixList AI",
    css=CSS,
    theme=gr.themes.Base(
        primary_hue="green",
        neutral_hue="gray",
        radius_size="lg",
        spacing_size="md",
    ),
) as demo:
    with gr.Row(elem_classes="main-shell"):
        with gr.Column(scale=2, min_width=190, elem_classes="panel"):
            gr.HTML('<div class="brand">FixList AI</div>')
            gr.HTML(
                """
                <div class="nav-item active">Current scan</div>
                <div class="nav-item">Projects</div>
                <div class="nav-item">Scan history</div>
                <div class="nav-item">Settings</div>
                """
            )
            mode = "Live Grok" if SETTINGS.live_grok_enabled else "Demo mode"
            gr.Markdown(f"**{mode}**\n\nMinimal evidence-grounded SEO guidance.")

        with gr.Column(scale=7, min_width=440, elem_classes="panel"):
            gr.Markdown(
                """
                # Ask about your crawl
                Get a clear explanation of what happened, what matters, and what to fix next.
                """
            )
            chatbot = gr.Chatbot(
                type="messages",
                height=560,
                placeholder=(
                    "Your scan is ready.\n\n"
                    "Ask what to fix first, why the score changed, or which work needs a developer."
                ),
            )
            gr.ChatInterface(
                fn=chat,
                chatbot=chatbot,
                type="messages",
                examples=[
                    "What should I fix first?",
                    "Why is my score 68?",
                    "What can I fix myself?",
                    "How many pages are affected?",
                ],
                api_name="chat",
                save_history=False,
            )

        with gr.Column(scale=3, min_width=260, elem_classes="panel"):
            gr.HTML(scan_markdown(DEMO_SCAN))
            gr.HTML(priority_markdown(DEMO_SCAN))


if __name__ == "__main__":
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
