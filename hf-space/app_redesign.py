from __future__ import annotations

import html
import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import gradio as gr
from app import (
    SETTINGS,
    submit_chat,
)
from app import (
    run_scan_from_ui as run_scan_pipeline_ui,
)

STANDARD_SCAN_MODE = "advanced"
SCAN_MODE_CHOICES = [("Standard · 150", STANDARD_SCAN_MODE)]


def _text(value: Any, fallback: str = "") -> str:
    rendered = str(value if value not in (None, "") else fallback)
    return html.escape(rendered)


def _number(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return fallback


def _is_live_scan(scan: dict[str, Any]) -> bool:
    return bool(scan.get("source") == "live" and scan.get("website"))


def _gate_label(scan: dict[str, Any]) -> str:
    if scan.get("release_gate_eligible"):
        return "Authoritative result"
    if scan.get("score_is_provisional"):
        return "Provisional result"
    return "Limited result"


def _hostname(scan: dict[str, Any]) -> str:
    raw = str(scan.get("website") or scan.get("website_url") or "")
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        return parsed.netloc or parsed.path or raw
    except ValueError:
        return raw


def _verdict(score: int) -> str:
    if score >= 85:
        return "Looking strong."
    if score >= 65:
        return "A solid foundation."
    if score >= 40:
        return "Room to improve."
    return "Needs attention."


def site_markup(scan: dict[str, Any]) -> str:
    if not _is_live_scan(scan):
        return """
<div class="site-copy">
  <h1>Ready for a new scan</h1>
  <p>Enter a public website URL below to load verified crawl evidence.</p>
</div>
"""

    pages = _number(scan.get("pages_crawled"))
    page_phrase = f"{pages} page{'s' if pages != 1 else ''} checked"
    return f"""
<div class="site-copy">
  <h1>{_text(_hostname(scan), "Website scan")}</h1>
  <p>Scanned just now · {page_phrase} · {_text(_gate_label(scan))}</p>
</div>
"""


def score_markup(scan: dict[str, Any]) -> str:
    if not _is_live_scan(scan):
        return """
<div class="score-summary empty" aria-label="No live score yet">
  <span class="score-ring" style="--v:0"><span>—</span></span>
  <div class="verdict-copy">
    <h2>Your score will appear here.</h2>
    <p>Run a scan to load the site’s current SEO health.</p>
  </div>
</div>
"""

    score = min(100, _number(scan.get("score")))
    return f"""
<div class="score-summary" aria-label="Health score {score} out of 100">
  <span class="score-ring" style="--v:{score}"><span>{score}</span></span>
  <div class="verdict-copy">
    <h2>{_verdict(score)}</h2>
  </div>
</div>
"""


def context_markup(scan: dict[str, Any]) -> str:
    loaded = _is_live_scan(scan)
    label = "Scan context loaded" if loaded else "Run a scan to load context"
    state_class = "loaded" if loaded else "waiting"
    return f"""
<div class="assistant-heading">
  <div>
    <h2>Grok audit assistant</h2>
    <p>Ask follow-up questions or get step-by-step help with any finding.</p>
  </div>
  <span class="context-pill {state_class}">{label}</span>
</div>
"""


def run_workspace_scan(
    website_url: str,
    scan_mode: str,
    current_scan: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    progress: gr.Progress = gr.Progress(),  # noqa: B008 - Gradio injects progress
) -> tuple[
    dict[str, Any],
    str,
    str,
    str,
    str,
    list[dict[str, Any]],
    dict[str, Any],
]:
    # Each request is a new site boundary. The reset transition has already
    # cleared the browser, and the backend must not receive stale scan/chat data.
    del current_scan, history
    scan, _, _, status, messages = run_scan_pipeline_ui(
        website_url,
        scan_mode,
        {},
        [],
        progress,
    )
    return (
        scan,
        site_markup(scan),
        score_markup(scan),
        context_markup(scan),
        status,
        messages,
        scan,
    )


def run_workspace_scan_transitions(
    website_url: str,
    scan_mode: str,
    current_scan: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    progress: gr.Progress = gr.Progress(),  # noqa: B008 - Gradio injects progress
) -> Iterator[tuple[Any, ...]]:
    """Yield an immediate reset followed by one terminal workspace state."""
    del current_scan, history
    empty_scan: dict[str, Any] = {}
    yield (
        empty_scan,
        site_markup(empty_scan),
        score_markup(empty_scan),
        context_markup(empty_scan),
        "⏳ **Scanning…** Previous results and Grok context were cleared.",
        [],
        empty_scan,
        "",
        gr.update(value="Scanning…", interactive=False),
    )

    try:
        terminal = run_workspace_scan(
            website_url,
            scan_mode,
            {},
            [],
            progress,
        )
    except Exception as exc:  # Defensive: the pipeline normally returns failures.
        status = f"❌ **Scan failed:** {html.escape(str(exc)[:260])}"
        terminal = (
            empty_scan,
            site_markup(empty_scan),
            score_markup(empty_scan),
            context_markup(empty_scan),
            status,
            [],
            empty_scan,
        )

    yield (
        *terminal,
        "",
        gr.update(
            value="Run scan",
            interactive=SETTINGS.live_scan_enabled,
        ),
    )


CSS = """
:root {
  --bg: #f8f8f6;
  --surface: #ffffff;
  --ink: #1b1b19;
  --soft: #70706b;
  --faint: #a4a49e;
  --line: #e7e6e1;
  --line-strong: #deddd7;
  --ring: #c55d30;
  --ring-track: #ecebe7;
  --good: #3f7f4c;
  --good-bg: #eef5ef;
  --assistant: #f2f1ee;
  --shadow: 0 12px 34px rgba(28, 28, 24, 0.045);
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
    "Helvetica Neue", Helvetica, Arial, sans-serif;
}

* {
  box-sizing: border-box;
}

html {
  font-size: 17px;
}

html,
body,
.gradio-container {
  min-height: 100%;
  margin: 0 !important;
  color: var(--ink) !important;
  background: var(--bg) !important;
  font-family: var(--font) !important;
  -webkit-font-smoothing: antialiased;
  letter-spacing: -0.012em;
  line-height: 1.5;
}

.gradio-container {
  width: 100% !important;
  max-width: none !important;
  padding: 0 0 70px !important;
}

button,
input,
textarea {
  font-family: var(--font) !important;
}

button:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--ink) !important;
  outline-offset: 2px !important;
}

.topbar {
  width: 100%;
  border-bottom: 1px solid var(--line);
  background: rgba(248, 248, 246, 0.9);
  backdrop-filter: saturate(150%) blur(20px);
  -webkit-backdrop-filter: saturate(150%) blur(20px);
}

.nav-shell {
  display: flex;
  width: min(100%, 1440px);
  min-height: 100px;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin: 0 auto;
  padding: 0 16px;
}

.logo {
  color: var(--ink);
  font-size: 1.55rem;
  font-weight: 720;
  letter-spacing: -0.045em;
}

.workspace-state {
  display: flex;
  align-items: center;
  gap: 30px;
  color: var(--faint);
  font-size: 0.82rem;
}

.online-pill {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 9px 15px;
  border-radius: 999px;
  color: var(--good);
  background: var(--good-bg);
  font-weight: 650;
}

.online-pill::before,
.context-pill::before {
  width: 9px;
  height: 9px;
  flex: 0 0 9px;
  border-radius: 50%;
  background: currentColor;
  content: "";
}

.online-pill.offline {
  color: #986126;
  background: #f7efe2;
}

.page-shell {
  width: min(100%, 1440px);
  margin: 0 auto;
  padding: 32px 16px 0;
  gap: 24px !important;
}

.site-actions {
  align-items: center !important;
  gap: 20px !important;
  margin: 0 16px !important;
}

.site-panel {
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.site-copy h1 {
  margin: 0;
  color: var(--ink);
  font-size: 1.48rem;
  font-weight: 720;
  letter-spacing: -0.032em;
  word-break: break-word;
}

.site-copy p {
  margin: 2px 0 0;
  color: var(--faint);
  font-size: 0.9rem;
}

#export-pdf {
  min-width: 118px !important;
  max-width: 118px !important;
  min-height: 46px !important;
  padding: 10px 17px !important;
  border: 1px solid var(--line-strong) !important;
  border-radius: 999px !important;
  color: var(--ink) !important;
  background: var(--surface) !important;
  box-shadow: none !important;
  font-size: 0.88rem !important;
  font-weight: 650 !important;
}

.score-card,
.assistant-card {
  margin: 0 !important;
  border: 1px solid var(--line) !important;
  border-radius: 24px !important;
  background: var(--surface) !important;
  box-shadow: var(--shadow) !important;
}

.score-card {
  padding: 16px 34px 22px !important;
}

.score-panel {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.score-summary {
  display: flex;
  min-height: 150px;
  align-items: center;
  gap: 48px;
  padding: 0 12px;
}

.score-ring {
  display: grid;
  width: 118px;
  height: 118px;
  flex: 0 0 118px;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(closest-side, var(--surface) 84%, transparent 86% 100%),
    conic-gradient(var(--ring) calc(var(--v) * 1%), var(--ring-track) 0);
}

.score-ring span {
  color: var(--ink);
  font-size: 2.5rem;
  font-weight: 740;
  letter-spacing: -0.055em;
}

.score-summary.empty .score-ring span {
  color: var(--faint);
}

.verdict-copy h2 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(1.7rem, 3vw, 2rem);
  font-weight: 720;
  letter-spacing: -0.035em;
  line-height: 1.12;
}

.verdict-copy p {
  margin: 7px 0 0;
  color: var(--faint);
  font-size: 0.9rem;
}

.scan-divider {
  height: 1px;
  margin: 0 0 19px;
  background: var(--line);
}

.scan-label {
  margin: 0 0 10px;
  color: var(--soft);
  font-size: 0.78rem;
  font-weight: 650;
}

.scan-controls {
  align-items: stretch !important;
  gap: 16px !important;
}

#website-url,
#scan-depth {
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

#website-url .wrap,
#scan-depth .wrap {
  min-height: 54px !important;
  border: 1px solid var(--line-strong) !important;
  border-radius: 16px !important;
  background: var(--surface) !important;
  box-shadow: none !important;
}

#website-url input,
#website-url textarea,
#scan-depth input {
  min-height: 52px !important;
  padding-inline: 18px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-size: 0.92rem !important;
}

#website-url input::placeholder,
#website-url textarea::placeholder {
  color: var(--faint) !important;
}

#run-scan {
  min-width: 220px !important;
  min-height: 54px !important;
  padding: 12px 24px !important;
  border: 1px solid var(--ink) !important;
  border-radius: 999px !important;
  color: #fff !important;
  background: var(--ink) !important;
  box-shadow: none !important;
  font-size: 0.9rem !important;
  font-weight: 660 !important;
  transition: background 150ms ease, transform 150ms ease;
}

#run-scan:hover {
  background: #343431 !important;
  transform: translateY(-1px);
}

#run-scan:active {
  transform: translateY(0);
}

#run-scan:disabled {
  border-color: var(--line) !important;
  color: var(--faint) !important;
  background: #efefec !important;
}

.scan-status {
  min-height: 18px;
  margin: 8px 2px 0 !important;
  color: var(--faint);
  font-size: 0.76rem;
}

.scan-status p {
  margin: 0 !important;
}

.premium-note {
  margin: 7px 4px 0;
  color: var(--faint);
  font-size: 0.72rem;
  text-align: right;
}

.assistant-card {
  min-height: 510px;
  padding: 22px 34px 14px !important;
}

.assistant-header {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.assistant-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  min-height: 72px;
  padding-bottom: 17px;
  border-bottom: 1px solid var(--line);
}

.assistant-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: 1.4rem;
  font-weight: 720;
  letter-spacing: -0.035em;
}

.assistant-heading p {
  margin: 2px 0 0;
  color: var(--soft);
  font-size: 0.88rem;
}

.context-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 999px;
  color: var(--good);
  background: var(--good-bg);
  font-size: 0.76rem;
  font-weight: 650;
  white-space: nowrap;
}

.context-pill.waiting {
  color: var(--faint);
  background: #f3f3f0;
}

.chatbot {
  min-height: 280px !important;
  margin: 0 !important;
  padding: 22px 0 10px !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.chatbot .bubble-wrap {
  padding: 0 !important;
}

.chatbot .message.user,
.chatbot .message.bot {
  max-width: 72% !important;
  padding: 16px 24px !important;
  border: 0 !important;
  border-radius: 20px !important;
  color: var(--ink) !important;
  background: var(--assistant) !important;
  box-shadow: none !important;
  font-size: 0.94rem !important;
  line-height: 1.55 !important;
}

.chatbot .message .message {
  width: 100% !important;
  max-width: none !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.chatbot .message.user {
  color: #fff !important;
  background: var(--ink) !important;
  border-radius: 17px !important;
}

.chatbot .message.bot::before {
  display: block;
  margin-bottom: 8px;
  color: var(--ring);
  content: "GROK";
  font-size: 0.72rem;
  font-weight: 760;
  letter-spacing: 0.02em;
}

.suggestion-row {
  justify-content: flex-end !important;
  margin: 0 32px 4px !important;
}

#first-question {
  width: min(100%, 420px) !important;
  min-height: 50px !important;
  border: 1px solid var(--ink) !important;
  border-radius: 16px !important;
  color: #fff !important;
  background: var(--ink) !important;
  box-shadow: none !important;
  font-size: 0.88rem !important;
  font-weight: 500 !important;
}

.chat-compose {
  align-items: stretch !important;
  gap: 16px !important;
  margin-top: 4px !important;
}

.chat-input {
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.chat-input .wrap {
  min-height: 60px !important;
  border: 1px solid var(--line-strong) !important;
  border-radius: 18px !important;
  background: #fafaf8 !important;
  box-shadow: none !important;
}

.chat-input textarea {
  min-height: 58px !important;
  padding: 17px 20px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-size: 0.88rem !important;
}

.chat-input textarea::placeholder {
  color: var(--faint) !important;
}

#send-message {
  min-width: 60px !important;
  max-width: 60px !important;
  min-height: 60px !important;
  padding: 0 !important;
  border: 1px solid var(--ink) !important;
  border-radius: 50% !important;
  color: #fff !important;
  background: var(--ink) !important;
  box-shadow: none !important;
  font-size: 1.9rem !important;
  font-weight: 350 !important;
}

.chat-note {
  margin: 4px 0 0;
  color: var(--faint);
  font-size: 0.7rem;
}

.debug-accordion {
  margin: 0 !important;
  border: 1px solid var(--line) !important;
  border-radius: 18px !important;
  background: var(--surface) !important;
  box-shadow: var(--shadow) !important;
  overflow: hidden;
}

.debug-accordion > .label-wrap {
  min-height: 76px !important;
  padding: 0 28px !important;
  color: var(--ink) !important;
  font-weight: 680 !important;
}

.debug-copy {
  margin: 0 0 8px !important;
  color: var(--faint);
  font-size: 0.75rem;
}

.debug-json {
  border: 0 !important;
  background: #fafaf8 !important;
}

footer {
  display: none !important;
}

@media (max-width: 900px) {
  .nav-shell {
    min-height: 74px;
    padding: 0 24px;
  }

  .page-shell {
    padding: 26px 24px 0;
  }

  .score-summary {
    gap: 30px;
  }

  .scan-controls {
    display: grid !important;
    grid-template-columns: 1fr 1fr;
  }

  #website-url {
    grid-column: 1 / -1;
  }

  #run-scan {
    min-width: 0 !important;
  }
}

@media (max-width: 620px) {
  html {
    font-size: 16px;
  }

  .nav-shell {
    min-height: 64px;
    padding: 0 18px;
  }

  .workspace-label {
    display: none;
  }

  .online-pill {
    padding: 7px 11px;
    font-size: 0.72rem;
  }

  .page-shell {
    padding: 22px 14px 0;
    gap: 16px !important;
  }

  .site-actions {
    margin: 0 4px !important;
  }

  #export-pdf {
    min-width: 104px !important;
    max-width: 104px !important;
  }

  .score-card,
  .assistant-card {
    border-radius: 20px !important;
  }

  .score-card {
    padding: 14px 18px 18px !important;
  }

  .score-summary {
    min-height: 130px;
    gap: 20px;
    padding: 0;
  }

  .score-ring {
    width: 92px;
    height: 92px;
    flex-basis: 92px;
  }

  .score-ring span {
    font-size: 2rem;
  }

  .verdict-copy h2 {
    font-size: 1.45rem;
  }

  .scan-controls {
    display: block !important;
  }

  #scan-depth,
  #run-scan {
    margin-top: 10px !important;
  }

  .assistant-card {
    padding: 20px 18px 12px !important;
  }

  .assistant-heading {
    display: block;
  }

  .context-pill {
    margin-top: 12px;
  }

  .chatbot .message.user,
  .chatbot .message.bot {
    max-width: 90% !important;
  }

  .suggestion-row {
    margin-inline: 0 !important;
  }

  .chat-compose {
    gap: 10px !important;
  }
}

@media print {
  .topbar,
  #export-pdf,
  .scan-controls,
  .scan-label,
  .scan-divider,
  .scan-status,
  .suggestion-row,
  .chat-compose,
  .chat-note,
  .debug-accordion {
    display: none !important;
  }

  .page-shell {
    width: 100%;
    padding: 0;
  }

  .score-card,
  .assistant-card {
    break-inside: avoid;
    box-shadow: none !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
  }
}
"""


scanner_online = SETTINGS.live_scan_enabled
grok_online = SETTINGS.live_grok_enabled
system_online = scanner_online and grok_online
system_label = "Scanner + Grok online" if system_online else "Setup needed"
system_class = "online" if system_online else "offline"

with gr.Blocks(
    title="FixList",
    css=CSS,
    theme=gr.themes.Base(
        primary_hue="orange",
        neutral_hue="gray",
        radius_size="lg",
        spacing_size="md",
    ),
) as demo:
    current_scan = gr.State({})

    gr.HTML(
        f"""
        <header class="topbar">
          <div class="nav-shell">
            <span class="logo">FixList</span>
            <div class="workspace-state">
              <span class="workspace-label">One-page workspace</span>
              <span class="online-pill {system_class}">{system_label}</span>
            </div>
          </div>
        </header>
        """
    )

    with gr.Column(elem_classes="page-shell"):
        with gr.Row(elem_classes="site-actions"):
            with gr.Column(scale=8, min_width=0, elem_classes="site-panel"):
                site_panel = gr.HTML(site_markup({}))
            export_button = gr.Button(
                "Export PDF",
                variant="secondary",
                scale=1,
                elem_id="export-pdf",
            )

        with gr.Group(elem_classes="score-card"):
            score_panel = gr.HTML(score_markup({}), elem_classes="score-panel")
            gr.HTML('<div class="scan-divider" aria-hidden="true"></div>')
            gr.HTML('<p class="scan-label">Scan a URL</p>')
            with gr.Row(elem_classes="scan-controls"):
                website_input = gr.Textbox(
                    placeholder="https://example.com",
                    show_label=False,
                    container=False,
                    scale=7,
                    elem_id="website-url",
                )
                scan_mode = gr.Dropdown(
                    choices=SCAN_MODE_CHOICES,
                    value=STANDARD_SCAN_MODE,
                    show_label=False,
                    container=False,
                    scale=2,
                    elem_id="scan-depth",
                )
                run_scan_button = gr.Button(
                    "Run scan",
                    variant="primary",
                    scale=2,
                    interactive=SETTINGS.live_scan_enabled,
                    elem_id="run-scan",
                )
            gr.HTML(
                '<p class="premium-note">Premium · 5,000 — coming soon</p>'
            )
            scan_status = gr.Markdown(
                (
                    ""
                    if SETTINGS.live_scan_enabled
                    else "Add the `SCANNER_API_KEY` Space secret to enable scans."
                ),
                elem_classes="scan-status",
            )

        with gr.Group(elem_classes="assistant-card"):
            assistant_header = gr.HTML(
                context_markup({}),
                elem_classes="assistant-header",
            )
            chatbot = gr.Chatbot(
                type="messages",
                allow_tags=False,
                height=280,
                show_label=False,
                container=False,
                placeholder=(
                    "Run a scan, then ask Grok what to fix, whether you can do it "
                    "yourself, or for exact step-by-step instructions."
                ),
                elem_classes="chatbot",
            )

            with gr.Row(elem_classes="suggestion-row"):
                first_question = gr.Button(
                    "What should I fix first?",
                    variant="secondary",
                    elem_id="first-question",
                )

            with gr.Row(elem_classes="chat-compose"):
                chat_input = gr.Textbox(
                    placeholder=(
                        "Ask Grok what to fix, how to do it yourself, or which pages "
                        "are affected…"
                    ),
                    show_label=False,
                    container=False,
                    lines=1,
                    max_lines=5,
                    scale=12,
                    elem_classes="chat-input",
                )
                send_button = gr.Button(
                    "→",
                    variant="primary",
                    scale=1,
                    elem_id="send-message",
                )
            gr.HTML(
                """
                <p class="chat-note">
                  Grok uses the current scan context and can also explain general SEO
                  implementation. It will distinguish verified evidence from guidance.
                </p>
                """
            )

        with gr.Accordion(
            "Debug JSON",
            open=False,
            elem_classes="debug-accordion",
        ):
            gr.Markdown(
                "Raw scanner response, release metadata, fallback flags, and review fields.",
                elem_classes="debug-copy",
            )
            debug_json = gr.JSON(
                value={},
                show_label=False,
                elem_classes="debug-json",
            )

    export_button.click(fn=None, js="() => window.print()")

    run_scan_button.click(
        fn=run_workspace_scan_transitions,
        inputs=[website_input, scan_mode, current_scan, chatbot],
        outputs=[
            current_scan,
            site_panel,
            score_panel,
            assistant_header,
            scan_status,
            chatbot,
            debug_json,
            chat_input,
            run_scan_button,
        ],
        api_name="run_scan",
        concurrency_limit=1,
        trigger_mode="once",
        show_progress="minimal",
    )
    send_button.click(
        fn=submit_chat,
        inputs=[chat_input, chatbot, current_scan],
        outputs=[chat_input, chatbot],
        api_name="chat",
    )
    chat_input.submit(
        fn=submit_chat,
        inputs=[chat_input, chatbot, current_scan],
        outputs=[chat_input, chatbot],
    )
    first_question.click(
        fn=lambda: "What should I fix first?",
        outputs=chat_input,
    ).then(
        fn=submit_chat,
        inputs=[chat_input, chatbot, current_scan],
        outputs=[chat_input, chatbot],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
