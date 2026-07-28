from __future__ import annotations

import html
import os
from typing import Any
from urllib.parse import urlparse

import gradio as gr

from app import (
    DEMO_SCAN,
    SETTINGS,
    run_scan_from_ui as run_scan_pipeline_ui,
    submit_chat,
)


def _text(value: Any, fallback: str = "") -> str:
    rendered = str(value if value not in (None, "") else fallback)
    return html.escape(rendered)


def _number(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return fallback


def _priorities(scan: dict[str, Any]) -> list[dict[str, Any]]:
    value = scan.get("priorities")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _gate_label(scan: dict[str, Any]) -> str:
    if scan.get("release_gate_eligible"):
        return "Authoritative"
    if scan.get("score_is_provisional"):
        return "Provisional"
    return "Limited"


def _hostname(scan: dict[str, Any]) -> str:
    raw = str(scan.get("website") or "No scan selected")
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


def dashboard_markup(scan: dict[str, Any]) -> str:
    score = min(100, _number(scan.get("score")))
    pages_found = _number(scan.get("pages_found"))
    pages_crawled = _number(scan.get("pages_crawled"))
    pages_retained = _number(scan.get("pages_retained"), pages_crawled)
    fixes = _priorities(scan)
    source = "Live scan" if scan.get("source") == "live" else "Preview result"
    first_fix = str(fixes[0].get("title") or "") if fixes else ""
    checked_phrase = (
        f"We checked <b>{pages_retained}</b> of the "
        f"<b>~{max(pages_found, pages_retained)}</b> pages we found"
    )
    if first_fix:
        summary = (
            f"{checked_phrase}. Start with <b>{_text(first_fix)}</b>, "
            "then work down the list by impact."
        )
    else:
        summary = (
            f"{checked_phrase}. The available crawl evidence did not produce "
            "a grouped priority list."
        )
    if scan.get("score_is_provisional") or not scan.get("release_gate_eligible"):
        caveat = (
            "This result is limited or provisional. Treat the findings as a "
            "diagnostic starting point until a complete evidence set is available."
        )
    else:
        caveat = (
            "This scan is read-only, so it cannot see private analytics, ad "
            "performance, server logs, or content behind a login."
        )

    return f"""
<section class="result-head" aria-label="Latest scan summary">
  <div class="site-row">
    <div class="site">
      <h2>{_text(_hostname(scan))}</h2>
      <p>{source} · {pages_crawled} pages checked · {_gate_label(scan)}</p>
    </div>
    <div class="result-badges">
      <span class="status-pill scanner">Scanner connected</span>
      <span class="status-pill grok">Grok connected</span>
    </div>
  </div>

  <div class="verdict">
    <span class="score-ring" style="--v:{score}" aria-label="Health score {score} out of 100">
      {score}
    </span>
    <div class="verdict-copy">
      <h1>{_verdict(score)}</h1>
      <p>{len(fixes)} grouped fixes to work through — start at the top.</p>
      <span>{pages_crawled} crawled · {pages_retained} retained</span>
    </div>
  </div>

  <p class="result-summary">{summary}</p>
  <p class="result-caveat">{_text(caveat)}</p>
</section>
"""


def issues_markup(scan: dict[str, Any]) -> str:
    priorities = _priorities(scan)
    if not priorities:
        return """
<section class="fix-section">
  <div class="section-label">Fix now <span>0</span></div>
  <div class="issues">
    <p class="empty-fixes">No grouped fixes were returned for this scan.</p>
  </div>
</section>
"""

    rows: list[str] = []
    for item in priorities[:10]:
        title = _text(item.get("title"), "Review confirmed finding")
        why = _text(
            item.get("why"),
            "Confirmed crawl evidence supports reviewing and correcting this pattern.",
        )
        affected = _number(item.get("affected_pages"))
        priority = str(item.get("priority") or "Medium").lower()
        owner = str(item.get("owner") or "SEO team")
        is_developer = any(
            term in owner.lower()
            for term in ("developer", "web person", "engineer", "technical")
        )
        dot_class = "high" if priority in {"critical", "high"} else "medium"
        tag_class = "developer" if is_developer else "you"
        owner_label = _text(owner)
        scope = (
            f"Affects {affected} page{'s' if affected != 1 else ''}"
            if affected
            else "Sitewide or grouped pattern"
        )
        rows.append(
            f"""
    <article class="issue">
      <span class="issue-dot {dot_class}" aria-hidden="true"></span>
      <div class="issue-main">
        <h3>{title}</h3>
        <p>{why}</p>
        <span>{scope}</span>
      </div>
      <span class="owner-tag {tag_class}">{owner_label}</span>
    </article>
"""
        )

    return f"""
<section class="fix-section">
  <div class="section-label">Fix now <span>{len(priorities)}</span></div>
  <div class="issues">
    {''.join(rows)}
  </div>
</section>
"""


def run_dashboard_scan(
    website_url: str,
    scan_mode: str,
    current_scan: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    progress: gr.Progress = gr.Progress(),
) -> tuple[
    dict[str, Any],
    str,
    str,
    str,
    list[dict[str, Any]],
]:
    scan, _, _, status, messages = run_scan_pipeline_ui(
        website_url,
        scan_mode,
        current_scan,
        history,
        progress,
    )
    return (
        scan,
        dashboard_markup(scan),
        issues_markup(scan),
        status,
        messages,
    )


CSS = """
:root {
  --bg: #f7f7f5;
  --surface: #ffffff;
  --ink: #1a1a18;
  --soft: #6e6e68;
  --faint: #a3a39c;
  --line: #e8e7e2;
  --ring: #c25e32;
  --ring-track: #ebeae5;
  --good: #3d7a46;
  --good-bg: #edf3ec;
  --dev: #8c5a17;
  --dev-bg: #f6eedf;
  --high: #b4442c;
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue",
    Helvetica, Arial, sans-serif;
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
  margin: 0 !important;
  min-height: 100%;
  color: var(--ink) !important;
  background: var(--bg) !important;
  font-family: var(--font) !important;
  -webkit-font-smoothing: antialiased;
  letter-spacing: -0.008em;
  line-height: 1.5;
}

.gradio-container {
  width: 100% !important;
  max-width: none !important;
  padding: 0 0 100px !important;
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
  background: rgba(247, 247, 245, 0.9);
  backdrop-filter: saturate(150%) blur(20px);
  -webkit-backdrop-filter: saturate(150%) blur(20px);
}

.nav-shell {
  display: flex;
  width: min(100%, 820px);
  height: 60px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin: 0 auto;
  padding: 0 24px;
}

.logo {
  color: var(--ink);
  font-size: 1.05rem;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 25px;
  color: var(--faint);
  font-size: 0.88rem;
}

.nav-link {
  transition: color 150ms ease;
}

.nav-link:hover,
.nav-link.active {
  color: var(--ink);
}

.nav-link.active {
  font-weight: 520;
}

.system-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.system-indicator::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--good);
  content: "";
}

.page-shell {
  width: min(100%, 820px);
  margin: 0 auto;
  padding: 40px 24px 0;
}

.scan-launcher {
  margin: 0 0 42px !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.scan-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

.scan-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: 1.15rem;
  font-weight: 620;
  letter-spacing: -0.015em;
}

.scan-header span {
  color: var(--faint);
  font-size: 0.78rem;
}

.scan-controls {
  align-items: stretch !important;
  gap: 9px !important;
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
  min-height: 44px !important;
  border: 1px solid var(--line) !important;
  border-radius: 999px !important;
  background: var(--surface) !important;
  box-shadow: none !important;
}

#website-url input,
#website-url textarea,
#scan-depth input {
  min-height: 42px !important;
  padding-inline: 17px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-size: 0.88rem !important;
}

#website-url input::placeholder,
#website-url textarea::placeholder {
  color: var(--faint) !important;
}

#run-scan {
  min-width: 120px !important;
  min-height: 44px !important;
  padding: 10px 20px !important;
  border: 1px solid var(--ink) !important;
  border-radius: 999px !important;
  color: #fff !important;
  background: var(--ink) !important;
  box-shadow: none !important;
  font-size: 0.88rem !important;
  font-weight: 540 !important;
  transition: background 150ms ease, transform 150ms ease;
}

#run-scan:hover {
  background: #333 !important;
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
  min-height: 20px;
  margin-top: 7px;
  padding: 0 5px;
  color: var(--faint);
  font-size: 0.76rem;
}

.scan-status p {
  margin: 0 !important;
}

.result-head {
  margin-bottom: 55px;
}

.site-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 42px;
}

.site h2 {
  margin: 0;
  color: var(--ink);
  font-size: 1.15rem;
  font-weight: 620;
  letter-spacing: -0.015em;
}

.site p {
  margin: 2px 0 0;
  color: var(--faint);
  font-size: 0.78rem;
}

.result-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  color: var(--good);
  background: var(--good-bg);
  font-size: 0.7rem;
  font-weight: 520;
  white-space: nowrap;
}

.status-pill::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  content: "";
}

.verdict {
  display: flex;
  align-items: center;
  gap: 28px;
  margin-bottom: 27px;
}

.score-ring {
  display: grid;
  width: 118px;
  height: 118px;
  flex: 0 0 118px;
  place-items: center;
  border-radius: 50%;
  color: var(--ink);
  background:
    radial-gradient(closest-side, var(--bg) 86%, transparent 87% 100%),
    conic-gradient(var(--ring) calc(var(--v) * 1%), var(--ring-track) 0);
  font-size: 2.2rem;
  font-weight: 720;
  letter-spacing: -0.04em;
}

.verdict-copy h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(1.7rem, 4vw, 2.3rem);
  font-weight: 710;
  letter-spacing: -0.035em;
  line-height: 1.08;
}

.verdict-copy p {
  margin: 6px 0 0;
  color: var(--soft);
  font-size: 1rem;
}

.verdict-copy span {
  display: block;
  margin-top: 9px;
  color: var(--faint);
  font-size: 0.76rem;
  font-feature-settings: "tnum";
}

.result-summary {
  max-width: 56ch;
  margin: 0 0 13px;
  color: var(--soft);
  font-size: 0.98rem;
}

.result-summary b {
  color: var(--ink);
  font-weight: 610;
}

.result-caveat {
  max-width: 56ch;
  margin: 0;
  padding-left: 14px;
  border-left: 2px solid var(--line);
  color: var(--faint);
  font-size: 0.78rem;
}

.fix-section {
  margin-bottom: 58px;
}

.section-label {
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin-bottom: 4px;
  color: var(--soft);
  font-size: 0.74rem;
  font-weight: 640;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.section-label span {
  color: var(--faint);
  font-weight: 500;
  letter-spacing: 0;
}

.issues {
  border-top: 1px solid var(--line);
}

.issue {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 20px 2px;
  border-bottom: 1px solid var(--line);
}

.issue-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  align-self: center;
  border-radius: 50%;
}

.issue-dot.high {
  background: var(--high);
}

.issue-dot.medium {
  background: var(--ring);
}

.issue-main {
  min-width: 0;
  flex: 1;
}

.issue-main h3 {
  margin: 0;
  color: var(--ink);
  font-size: 1rem;
  font-weight: 620;
  letter-spacing: -0.015em;
}

.issue-main p {
  max-width: 60ch;
  margin: 3px 0 0;
  color: var(--soft);
  font-size: 0.85rem;
}

.issue-main span {
  display: block;
  margin-top: 5px;
  color: var(--faint);
  font-size: 0.75rem;
  font-feature-settings: "tnum";
}

.owner-tag {
  flex: 0 0 auto;
  align-self: center;
  padding: 4px 11px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 530;
  white-space: nowrap;
}

.owner-tag.you {
  color: var(--good);
  background: var(--good-bg);
}

.owner-tag.developer {
  color: var(--dev);
  background: var(--dev-bg);
}

.empty-fixes {
  margin: 0;
  padding: 24px 2px;
  border-bottom: 1px solid var(--line);
  color: var(--soft);
  font-size: 0.88rem;
}

.assistant-shell {
  margin-top: 12px !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.assistant-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 10px;
}

.assistant-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: 1.12rem;
  font-weight: 620;
}

.assistant-heading span {
  color: var(--faint);
  font-size: 0.76rem;
}

.chatbot {
  min-height: 300px !important;
  border: 1px solid var(--line) !important;
  border-radius: 18px !important;
  background: var(--surface) !important;
  box-shadow: none !important;
}

.chatbot .message {
  border: 0 !important;
  border-radius: 15px !important;
  color: var(--ink) !important;
  background: #f2f2ef !important;
  box-shadow: none !important;
  font-size: 0.85rem !important;
  line-height: 1.55 !important;
}

.chatbot .message.user {
  color: #fff !important;
  background: var(--ink) !important;
}

.chat-compose {
  align-items: stretch !important;
  gap: 8px !important;
  margin-top: 9px;
}

.chat-input {
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.chat-input .wrap {
  min-height: 44px !important;
  border: 1px solid var(--line) !important;
  border-radius: 999px !important;
  background: var(--surface) !important;
  box-shadow: none !important;
}

.chat-input textarea {
  min-height: 42px !important;
  padding: 11px 17px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-size: 0.85rem !important;
}

#send-message,
#clear-chat,
.question-chip {
  min-height: 44px !important;
  border-radius: 999px !important;
  box-shadow: none !important;
  font-size: 0.8rem !important;
  font-weight: 530 !important;
}

#send-message {
  min-width: 80px !important;
  border-color: var(--ink) !important;
  color: #fff !important;
  background: var(--ink) !important;
}

#clear-chat {
  min-width: 70px !important;
  border-color: var(--line) !important;
  color: var(--soft) !important;
  background: var(--surface) !important;
}

.suggestion-row {
  flex-wrap: wrap !important;
  gap: 6px !important;
  margin-top: 8px;
}

.question-chip {
  width: auto !important;
  min-width: 0 !important;
  flex: 0 1 auto !important;
  min-height: 34px !important;
  padding: 6px 11px !important;
  border-color: var(--line) !important;
  color: var(--soft) !important;
  background: transparent !important;
}

.question-chip:hover {
  color: var(--ink) !important;
  border-color: #cfcec8 !important;
}

.footnote {
  margin: 50px 0 0;
  color: var(--faint);
  font-size: 0.76rem;
  text-align: center;
}

footer {
  display: none !important;
}

@media (max-width: 700px) {
  .nav-shell {
    height: auto;
    min-height: 58px;
    padding: 12px 18px;
  }

  .nav-links {
    gap: 15px;
    font-size: 0.76rem;
  }

  .system-indicator {
    display: none;
  }

  .page-shell {
    padding: 31px 18px 0;
  }

  .scan-launcher {
    margin-bottom: 34px !important;
  }

  .scan-header span {
    display: none;
  }

  .scan-controls,
  .chat-compose {
    display: grid !important;
    grid-template-columns: 1fr 1fr;
  }

  #website-url,
  .chat-input {
    grid-column: 1 / -1;
  }

  #run-scan {
    min-width: 0 !important;
  }

  .site-row {
    margin-bottom: 32px;
  }

  .result-badges {
    display: none;
  }

  .verdict {
    gap: 20px;
  }

  .score-ring {
    width: 96px;
    height: 96px;
    flex-basis: 96px;
    font-size: 1.8rem;
  }

  .issue {
    flex-wrap: wrap;
  }

  .owner-tag {
    order: 3;
    margin-left: 22px;
  }
}

@media (max-width: 470px) {
  .nav-link.grok-nav {
    display: none;
  }

  .verdict-copy h1 {
    font-size: 1.55rem;
  }

  .verdict-copy p {
    font-size: 0.88rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
  }
}
"""


scanner_state_label = "Connected" if SETTINGS.live_scan_enabled else "Setup needed"
ai_state_label = "Grok" if SETTINGS.live_grok_enabled else "Guided"

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
    current_scan = gr.State(DEMO_SCAN)

    gr.HTML(
        f"""
        <header class="topbar">
          <div class="nav-shell">
            <span class="logo">FixList</span>
            <nav class="nav-links" aria-label="Main">
              <span class="nav-link active">Dashboard</span>
              <span class="nav-link">New scan</span>
              <span class="nav-link grok-nav">Grok</span>
              <span class="nav-link system-indicator">
                {scanner_state_label} · {ai_state_label}
              </span>
            </nav>
          </div>
        </header>
        """
    )

    with gr.Column(elem_classes="page-shell"):
        with gr.Group(elem_classes="scan-launcher"):
            gr.HTML(
                """
                <div class="scan-header">
                  <h2>Scan a website</h2>
                  <span>Advanced mode reviews up to 150 pages</span>
                </div>
                """
            )
            with gr.Row(elem_classes="scan-controls"):
                website_input = gr.Textbox(
                    label="Website URL",
                    placeholder="https://example.com",
                    show_label=False,
                    container=False,
                    scale=7,
                    elem_id="website-url",
                )
                scan_mode = gr.Dropdown(
                    choices=["advanced", "deep", "quick", "basic"],
                    value="advanced",
                    label="Scan depth",
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
            scan_status = gr.Markdown(
                (
                    "Ready for a new 150-page scan."
                    if SETTINGS.live_scan_enabled
                    else "Add the `SCANNER_API_KEY` Space secret to enable new scans."
                ),
                elem_classes="scan-status",
            )

        dashboard_panel = gr.HTML(dashboard_markup(DEMO_SCAN))
        issues_panel = gr.HTML(issues_markup(DEMO_SCAN))

        with gr.Group(elem_classes="assistant-shell"):
            gr.HTML(
                f"""
                <div class="assistant-heading">
                  <h2>Ask Grok about this scan</h2>
                  <span>{ai_state_label} · answers stay grounded in crawl evidence</span>
                </div>
                """
            )
            chatbot = gr.Chatbot(
                type="messages",
                allow_tags=False,
                height=300,
                show_label=False,
                container=False,
                placeholder=(
                    "Run a scan, then ask what matters most.\n\n"
                    "Try: What should I fix first?"
                ),
                elem_classes="chatbot",
            )
            with gr.Row(elem_classes="chat-compose"):
                chat_input = gr.Textbox(
                    placeholder="Ask what to fix, why it matters, or who should own it…",
                    show_label=False,
                    container=False,
                    lines=1,
                    max_lines=4,
                    scale=9,
                    elem_classes="chat-input",
                )
                send_button = gr.Button(
                    "Send",
                    variant="primary",
                    scale=1,
                    elem_id="send-message",
                )
                clear_button = gr.Button(
                    "Clear",
                    variant="secondary",
                    scale=1,
                    elem_id="clear-chat",
                )

            with gr.Row(elem_classes="suggestion-row"):
                first_chip = gr.Button(
                    "What should I fix first?",
                    variant="secondary",
                    elem_classes="question-chip",
                )
                score_chip = gr.Button(
                    "Why this score?",
                    variant="secondary",
                    elem_classes="question-chip",
                )
                owner_chip = gr.Button(
                    "Who owns each fix?",
                    variant="secondary",
                    elem_classes="question-chip",
                )
                pages_chip = gr.Button(
                    "Pages affected",
                    variant="secondary",
                    elem_classes="question-chip",
                )

        gr.HTML(
            """
            <p class="footnote">
              FixList scans public website evidence only. Export or share confirmed
              fixes with the person responsible for the work.
            </p>
            """
        )

    run_scan_button.click(
        fn=run_dashboard_scan,
        inputs=[website_input, scan_mode, current_scan, chatbot],
        outputs=[
            current_scan,
            dashboard_panel,
            issues_panel,
            scan_status,
            chatbot,
        ],
        api_name="run_scan",
        concurrency_limit=1,
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
    clear_button.click(fn=lambda: ("", []), outputs=[chat_input, chatbot])

    first_chip.click(fn=lambda: "What should I fix first?", outputs=chat_input)
    score_chip.click(fn=lambda: "Why did I get this score?", outputs=chat_input)
    owner_chip.click(fn=lambda: "Who should own each fix?", outputs=chat_input)
    pages_chip.click(fn=lambda: "How many pages are affected?", outputs=chat_input)


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
