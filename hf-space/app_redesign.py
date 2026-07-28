from __future__ import annotations

import os

import gradio as gr

from app import (
    DEMO_SCAN,
    SETTINGS,
    priority_markdown,
    run_scan_from_ui,
    scan_markdown,
    submit_chat,
)


CSS = """
:root {
  --bg: #f4f7f5;
  --surface: #ffffff;
  --surface-soft: #f8faf9;
  --ink: #132019;
  --muted: #68756d;
  --line: #dfe7e2;
  --accent: #196b45;
  --accent-strong: #0f5837;
  --accent-soft: #eaf5ef;
  --shadow: 0 18px 50px rgba(21, 49, 34, 0.08);
}

* { box-sizing: border-box; }
body, .gradio-container { background: var(--bg) !important; }
.gradio-container {
  max-width: 1560px !important;
  margin: 0 auto !important;
  color: var(--ink) !important;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
  padding: 18px !important;
}
.app-shell { gap: 16px !important; align-items: stretch !important; }
.surface {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: var(--shadow);
}
.sidebar { min-height: calc(100vh - 36px); padding: 18px 14px; }
.workspace { padding: 26px; min-height: calc(100vh - 36px); }
.insights { padding: 20px; min-height: calc(100vh - 36px); }
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  font-size: 19px;
  letter-spacing: -.04em;
  margin: 2px 6px 26px;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: linear-gradient(145deg, var(--accent), var(--accent-strong));
  color: #fff;
  box-shadow: 0 8px 18px rgba(25, 107, 69, .22);
}
.nav-list { display: grid; gap: 5px; }
.nav-item {
  padding: 11px 12px;
  border-radius: 11px;
  color: var(--muted);
  font-size: 14px;
  font-weight: 560;
}
.nav-item.active { background: var(--accent-soft); color: var(--accent-strong); font-weight: 720; }
.nav-icon { display: inline-block; width: 20px; opacity: .72; }
.connection-card { margin-top: 30px; padding: 18px 10px 0; border-top: 1px solid var(--line); }
.connection-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
  color: var(--muted);
  font-size: 12px;
}
.connection-value { color: var(--ink); font-weight: 700; }
.connection-value::before {
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #36a269;
  margin-right: 6px;
}
.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 18px; }
.hero-copy h1 {
  font-size: 30px !important;
  line-height: 1.08 !important;
  letter-spacing: -.052em;
  margin: 0 0 8px !important;
}
.hero-copy p { color: var(--muted); margin: 0 !important; max-width: 620px; font-size: 14px; }
.hero-badge {
  white-space: nowrap;
  padding: 8px 11px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 750;
}
.scan-launcher {
  background: linear-gradient(180deg, #fbfdfc, #f6faf7);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px;
  margin: 0 0 16px;
}
.scan-label { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 11px; }
.scan-label strong { font-size: 14px; }
.scan-label span { color: var(--muted); font-size: 12px; }
.scan-controls { gap: 10px !important; align-items: end !important; }
.scan-status { min-height: 24px; margin-top: 9px; color: var(--muted); font-size: 12px; }
.scan-status p { margin: 0 !important; }
button.primary { background: var(--accent) !important; border-color: var(--accent) !important; box-shadow: none !important; }
button.primary:hover { background: var(--accent-strong) !important; }
.chat-section-title { display: flex; justify-content: space-between; align-items: center; margin: 8px 0 10px; }
.chat-section-title strong { font-size: 14px; }
.chat-section-title span { color: var(--muted); font-size: 12px; }
.chatbot {
  border: 1px solid var(--line) !important;
  border-radius: 18px !important;
  background: var(--surface-soft) !important;
  overflow: hidden;
}
.chatbot .message { border-radius: 14px !important; }
.chat-compose { margin-top: 10px; gap: 9px !important; align-items: stretch !important; }
.chat-input textarea { min-height: 56px !important; border-radius: 14px !important; }
.secondary-action button { background: #fff !important; border-color: var(--line) !important; color: var(--muted) !important; }
#prompt-chips { margin-top: 8px; }
#prompt-chips button { border-radius: 999px !important; font-size: 12px !important; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.eyebrow { color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: .14em; }
.summary h2 { margin: 7px 0 0; font-size: 15px; letter-spacing: -.02em; word-break: break-word; }
.status { padding: 6px 9px; border-radius: 999px; font-size: 10px; font-weight: 760; }
.score-row { margin: 20px 0 18px; }
.score { font-size: 44px; font-weight: 820; letter-spacing: -.07em; }
.muted { color: var(--muted); }
.metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.metric-grid div {
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: 11px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric-grid strong { font-size: 18px; }
.metric-grid span { color: var(--muted); font-size: 10px; }
.priority-section { margin-top: 22px; }
.priority { display: flex; gap: 10px; border-top: 1px solid var(--line); padding: 13px 0; }
.priority-index {
  flex: 0 0 25px;
  width: 25px;
  height: 25px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 10px;
  font-weight: 750;
}
.priority-copy { min-width: 0; flex: 1; }
.priority-copy strong { font-size: 12px; line-height: 1.35; }
.priority-copy p, .empty-copy { margin: 4px 0 0; color: var(--muted); font-size: 10px; }
.insight-note {
  margin-top: 22px;
  padding: 13px;
  border-radius: 14px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
}
footer { display: none !important; }

@media (max-width: 1120px) {
  .app-shell { display: grid !important; grid-template-columns: 180px minmax(0, 1fr) !important; }
  .insights { grid-column: 2; min-height: auto; }
  .workspace { min-height: auto; }
}
@media (max-width: 760px) {
  .gradio-container { padding: 10px !important; }
  .app-shell { display: block !important; }
  .sidebar { min-height: auto; margin-bottom: 10px; }
  .workspace, .insights { min-height: auto; padding: 16px; margin-bottom: 10px; }
  .nav-list { grid-template-columns: 1fr 1fr; }
  .connection-card { margin-top: 14px; }
  .hero { display: block; }
  .hero-badge { display: inline-block; margin-top: 12px; }
  .hero-copy h1 { font-size: 26px !important; }
  .scan-controls { display: block !important; }
  .chat-compose { display: grid !important; grid-template-columns: 1fr 1fr; }
  .chat-input { grid-column: 1 / -1; }
}
"""

scanner_state_label = "Connected" if SETTINGS.live_scan_enabled else "Setup needed"
ai_state_label = "Grok" if SETTINGS.live_grok_enabled else "Guided"

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
    current_scan = gr.State(DEMO_SCAN)

    with gr.Row(elem_classes="app-shell"):
        with gr.Column(scale=2, min_width=180, elem_classes=["surface", "sidebar"]):
            gr.HTML('<div class="brand"><span class="brand-mark">F</span><span>FixList AI</span></div>')
            gr.HTML(
                """
                <div class="nav-list">
                  <div class="nav-item active"><span class="nav-icon">◉</span>Scan workspace</div>
                  <div class="nav-item"><span class="nav-icon">◇</span>Projects</div>
                  <div class="nav-item"><span class="nav-icon">↻</span>History</div>
                  <div class="nav-item"><span class="nav-icon">⚙</span>Settings</div>
                </div>
                """
            )
            gr.HTML(
                f"""
                <div class="connection-card">
                  <div class="eyebrow">SYSTEM STATUS</div>
                  <div class="connection-row"><span>Scanner</span><span class="connection-value">{scanner_state_label}</span></div>
                  <div class="connection-row"><span>Assistant</span><span class="connection-value">{ai_state_label}</span></div>
                </div>
                """
            )

        with gr.Column(scale=7, min_width=520, elem_classes=["surface", "workspace"]):
            gr.HTML(
                """
                <div class="hero">
                  <div class="hero-copy">
                    <h1>Turn a crawl into a clear fix list.</h1>
                    <p>Scan a site, verify the evidence, then ask FixList AI what matters first and who should own each fix.</p>
                  </div>
                  <span class="hero-badge">Evidence-grounded SEO</span>
                </div>
                """
            )

            with gr.Group(elem_classes="scan-launcher"):
                gr.HTML(
                    """
                    <div class="scan-label">
                      <strong>Start a new scan</strong>
                      <span>Advanced mode reviews up to 150 pages</span>
                    </div>
                    """
                )
                with gr.Row(elem_classes="scan-controls"):
                    website_input = gr.Textbox(
                        label="Website URL",
                        placeholder="https://example.com",
                        scale=6,
                    )
                    scan_mode = gr.Dropdown(
                        choices=["advanced", "deep", "quick", "basic"],
                        value="advanced",
                        label="Scan depth",
                        scale=2,
                    )
                    run_scan_button = gr.Button(
                        "Run website scan",
                        variant="primary",
                        scale=2,
                        interactive=SETTINGS.live_scan_enabled,
                    )
                scan_status = gr.Markdown(
                    (
                        "Ready for a new 150-page scan."
                        if SETTINGS.live_scan_enabled
                        else "Add the `SCANNER_API_KEY` Space secret to enable new scans."
                    ),
                    elem_classes="scan-status",
                )

            gr.HTML(
                """
                <div class="chat-section-title">
                  <strong>Ask FixList AI</strong>
                  <span>Answers stay grounded in the current scan</span>
                </div>
                """
            )
            chatbot = gr.Chatbot(
                type="messages",
                allow_tags=False,
                height=455,
                placeholder=(
                    "Run a scan or ask about the current result.\n\n"
                    "Try: What should I fix first?"
                ),
                elem_classes="chatbot",
            )

            with gr.Row(elem_classes="chat-compose"):
                chat_input = gr.Textbox(
                    placeholder="Ask what to fix, why it matters, or who should own it…",
                    show_label=False,
                    lines=2,
                    max_lines=5,
                    scale=8,
                    elem_classes="chat-input",
                )
                send_button = gr.Button("Send", variant="primary", scale=1)
                clear_button = gr.Button(
                    "Clear",
                    variant="secondary",
                    scale=1,
                    elem_classes="secondary-action",
                )

            gr.Examples(
                examples=[
                    "What should I fix first?",
                    "Why did I get this score?",
                    "What can I fix myself?",
                    "How many pages are affected?",
                ],
                inputs=chat_input,
                label="Suggested questions",
                elem_id="prompt-chips",
            )

        with gr.Column(scale=3, min_width=290, elem_classes=["surface", "insights"]):
            summary_panel = gr.HTML(scan_markdown(DEMO_SCAN))
            priority_panel = gr.HTML(priority_markdown(DEMO_SCAN))
            gr.HTML(
                """
                <div class="insight-note">
                  FixList AI separates confirmed crawl evidence from recommendations. Limited or provisional scans are never presented as authoritative.
                </div>
                """
            )

    run_scan_button.click(
        fn=run_scan_from_ui,
        inputs=[website_input, scan_mode, current_scan, chatbot],
        outputs=[current_scan, summary_panel, priority_panel, scan_status, chatbot],
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


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
