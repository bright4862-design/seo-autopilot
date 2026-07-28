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
  --canvas: #f5f5f7;
  --surface: rgba(255, 255, 255, 0.88);
  --surface-solid: #ffffff;
  --surface-muted: #f8f8fa;
  --ink: #1d1d1f;
  --ink-soft: #3a3a3c;
  --muted: #737378;
  --muted-light: #a1a1a6;
  --line: rgba(60, 60, 67, 0.12);
  --line-strong: rgba(60, 60, 67, 0.18);
  --green: #147a50;
  --green-strong: #0b6741;
  --green-soft: #e8f5ee;
  --green-wash: #f2faf6;
  --blue-soft: #eef5ff;
  --shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 18px 50px rgba(0, 0, 0, 0.055);
  --font:
    -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
    "Helvetica Neue", Inter, ui-sans-serif, system-ui, sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  min-height: 100%;
  background: var(--canvas) !important;
}

body,
.gradio-container {
  color: var(--ink) !important;
  font-family: var(--font) !important;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

body::before {
  position: fixed;
  inset: 0;
  z-index: -1;
  content: "";
  pointer-events: none;
  background:
    radial-gradient(circle at 16% 0%, rgba(20, 122, 80, 0.065), transparent 30rem),
    radial-gradient(circle at 92% 12%, rgba(75, 126, 206, 0.04), transparent 28rem);
}

.gradio-container {
  width: 100% !important;
  max-width: 1710px !important;
  margin: 0 auto !important;
  padding: 16px !important;
  background: transparent !important;
}

.app-shell {
  min-height: calc(100dvh - 32px);
  align-items: stretch !important;
  gap: 14px !important;
}

.surface {
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 26px;
  background: var(--surface);
  box-shadow: var(--shadow);
  backdrop-filter: saturate(150%) blur(28px);
  -webkit-backdrop-filter: saturate(150%) blur(28px);
}

.sidebar {
  display: flex !important;
  min-height: calc(100dvh - 32px);
  padding: 20px 14px 16px;
  flex-direction: column !important;
}

.workspace {
  min-height: calc(100dvh - 32px);
  padding: clamp(24px, 2.7vw, 40px);
}

.insights {
  min-height: calc(100dvh - 32px);
  padding: 24px 22px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  margin: 1px 7px 28px;
}

.brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(145deg, #1b8c5e, #0a633d);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.24),
    0 8px 20px rgba(20, 122, 80, 0.2);
  font-size: 17px;
  font-weight: 760;
  letter-spacing: -0.04em;
}

.brand-name {
  color: var(--ink);
  font-size: 17px;
  font-weight: 720;
  letter-spacing: -0.035em;
}

.brand-meta {
  display: block;
  margin-top: 1px;
  color: var(--muted-light);
  font-size: 10px;
  font-weight: 560;
  letter-spacing: 0.01em;
}

.nav-label,
.eyebrow {
  color: var(--muted-light);
  font-size: 10px;
  font-weight: 720;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.nav-label {
  margin: 0 12px 8px;
}

.nav-list {
  display: grid;
  gap: 4px;
}

.nav-item {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 580;
  transition:
    color 150ms ease,
    background 150ms ease,
    border-color 150ms ease,
    transform 150ms ease;
}

.nav-item:hover {
  color: var(--ink);
  background: rgba(118, 118, 128, 0.065);
}

.nav-item.active {
  color: var(--green-strong);
  border-color: rgba(20, 122, 80, 0.08);
  background: var(--green-soft);
  font-weight: 680;
}

.nav-icon {
  display: grid;
  width: 19px;
  height: 19px;
  flex: 0 0 19px;
  place-items: center;
}

.nav-icon svg {
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.7;
}

.connection-card {
  margin-top: auto;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(248, 248, 250, 0.72);
}

.connection-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.live-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--green-strong);
  font-size: 10px;
  font-weight: 690;
}

.live-pill::before,
.connection-value::before {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #30b06c;
  box-shadow: 0 0 0 3px rgba(48, 176, 108, 0.11);
  content: "";
}

.connection-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
  color: var(--muted);
  font-size: 11px;
}

.connection-value {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink-soft);
  font-weight: 620;
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.hero-kicker {
  display: block;
  margin-bottom: 8px;
  color: var(--green);
  font-size: 11px;
  font-weight: 680;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hero-copy h1 {
  max-width: 720px;
  margin: 0 0 9px !important;
  color: var(--ink);
  font-size: clamp(31px, 3vw, 43px) !important;
  font-weight: 720 !important;
  letter-spacing: -0.055em;
  line-height: 1.02 !important;
}

.hero-copy p {
  max-width: 660px;
  margin: 0 !important;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.55;
}

.hero-badge {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  padding: 8px 11px;
  border: 1px solid rgba(20, 122, 80, 0.12);
  border-radius: 999px;
  color: var(--green-strong);
  background: var(--green-wash);
  font-size: 10px;
  font-weight: 670;
  letter-spacing: 0.01em;
}

.hero-badge::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #30b06c;
  content: "";
}

.scan-launcher {
  margin: 0 0 22px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(248, 248, 250, 0.86);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.scan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 4px 10px;
}

.scan-title {
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 680;
}

.scan-limit {
  color: var(--muted-light);
  font-size: 10px;
  font-weight: 540;
}

.scan-controls {
  align-items: stretch !important;
  gap: 8px !important;
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
  border: 1px solid var(--line) !important;
  border-radius: 13px !important;
  background: var(--surface-solid) !important;
  box-shadow: none !important;
}

#website-url input,
#website-url textarea,
#scan-depth input {
  min-height: 46px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
}

#website-url input::placeholder,
#website-url textarea::placeholder {
  color: var(--muted-light) !important;
}

#run-scan {
  min-width: 148px !important;
  min-height: 46px !important;
  border: 0 !important;
  border-radius: 13px !important;
  color: white !important;
  background: linear-gradient(180deg, #198457, #106d47) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 7px 18px rgba(20, 122, 80, 0.18) !important;
  font-family: var(--font) !important;
  font-size: 12px !important;
  font-weight: 680 !important;
  transition:
    transform 150ms ease,
    box-shadow 150ms ease,
    filter 150ms ease;
}

#run-scan:hover {
  filter: brightness(0.98);
  transform: translateY(-1px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 9px 22px rgba(20, 122, 80, 0.22) !important;
}

#run-scan:active {
  transform: translateY(0);
}

#run-scan:disabled {
  color: var(--muted) !important;
  background: #e8e8ed !important;
  box-shadow: none !important;
}

.scan-status {
  min-height: 20px;
  margin-top: 7px;
  padding: 0 5px;
  color: var(--muted);
  font-size: 10px;
}

.scan-status p {
  margin: 0 !important;
}

.chat-card {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: var(--surface-solid);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
}

.chat-card-head {
  display: flex;
  min-height: 55px;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 17px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
}

.assistant-identity {
  display: flex;
  align-items: center;
  gap: 10px;
}

.assistant-avatar {
  position: relative;
  display: grid;
  width: 29px;
  height: 29px;
  flex: 0 0 29px;
  place-items: center;
  border-radius: 10px;
  color: var(--green-strong);
  background: var(--green-soft);
  font-size: 12px;
  font-weight: 760;
}

.assistant-avatar::after {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 7px;
  height: 7px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #30b06c;
  content: "";
}

.assistant-title {
  display: block;
  color: var(--ink);
  font-size: 12px;
  font-weight: 680;
}

.assistant-subtitle {
  display: block;
  margin-top: 1px;
  color: var(--muted-light);
  font-size: 9px;
  font-weight: 520;
}

.grounded-label {
  color: var(--muted);
  font-size: 10px;
  font-weight: 560;
}

.chatbot {
  min-height: 378px !important;
  border: 0 !important;
  border-radius: 0 !important;
  background:
    linear-gradient(180deg, rgba(248, 248, 250, 0.78), rgba(255, 255, 255, 0.98)) !important;
  box-shadow: none !important;
}

.chatbot .message {
  max-width: 84% !important;
  border: 1px solid var(--line) !important;
  border-radius: 16px !important;
  color: var(--ink-soft) !important;
  background: #fff !important;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.035) !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  line-height: 1.55 !important;
}

.chatbot .message.user {
  border-color: rgba(20, 122, 80, 0.15) !important;
  color: #16432f !important;
  background: var(--green-wash) !important;
}

.chatbot .message p {
  margin-top: 0.4em !important;
  margin-bottom: 0.4em !important;
}

.compose-shell {
  padding: 10px 11px 11px;
  border-top: 1px solid var(--line);
  background: rgba(248, 248, 250, 0.72);
}

.chat-compose {
  align-items: stretch !important;
  gap: 8px !important;
}

.chat-input {
  min-width: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.chat-input .wrap {
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
  background: #fff !important;
  box-shadow: none !important;
}

.chat-input textarea {
  min-height: 46px !important;
  color: var(--ink) !important;
  background: transparent !important;
  font-family: var(--font) !important;
  font-size: 12px !important;
}

.chat-input textarea::placeholder {
  color: var(--muted-light) !important;
}

#send-message,
#clear-chat {
  min-height: 46px !important;
  border-radius: 13px !important;
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 660 !important;
}

#send-message {
  min-width: 82px !important;
  border-color: var(--green) !important;
  color: #fff !important;
  background: var(--green) !important;
  box-shadow: 0 6px 14px rgba(20, 122, 80, 0.14) !important;
}

#clear-chat {
  min-width: 66px !important;
  border-color: var(--line) !important;
  color: var(--muted) !important;
  background: #fff !important;
  box-shadow: none !important;
}

.suggestion-wrap {
  margin-top: 10px;
}

.suggestion-label {
  margin-bottom: 6px;
  padding-left: 2px;
  color: var(--muted-light);
  font-size: 9px;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.question-chips {
  flex-wrap: wrap !important;
  gap: 6px !important;
}

.question-chip {
  width: auto !important;
  min-width: 0 !important;
  flex: 0 1 auto !important;
  padding: 6px 10px !important;
  border: 1px solid var(--line) !important;
  border-radius: 999px !important;
  color: var(--muted) !important;
  background: rgba(255, 255, 255, 0.82) !important;
  box-shadow: none !important;
  font-family: var(--font) !important;
  font-size: 9px !important;
  font-weight: 570 !important;
}

.question-chip:hover {
  border-color: rgba(20, 122, 80, 0.16) !important;
  color: var(--green-strong) !important;
  background: var(--green-wash) !important;
}

.rail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 22px;
}

.rail-head h2 {
  margin: 4px 0 0;
  color: var(--ink);
  font-size: 17px;
  font-weight: 690;
  letter-spacing: -0.035em;
}

.rail-icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 11px;
  color: var(--muted);
  background: var(--surface-muted);
}

.rail-icon svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.7;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.summary h2 {
  overflow: hidden;
  margin: 11px 0 0;
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 610;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status {
  padding: 5px 8px;
  border: 1px solid rgba(20, 122, 80, 0.12);
  border-radius: 999px;
  color: var(--green-strong);
  background: var(--green-wash);
  font-size: 9px;
  font-weight: 680;
}

.score-row {
  margin: 20px 0 15px;
}

.score {
  color: var(--ink);
  font-size: 47px;
  font-weight: 720;
  letter-spacing: -0.075em;
  line-height: 1;
}

.score + .muted {
  margin-left: 4px;
  font-size: 11px;
}

.muted {
  color: var(--muted);
}

.metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.metric-grid div {
  display: flex;
  min-height: 64px;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  padding: 10px 11px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--surface-muted);
}

.metric-grid strong {
  color: var(--ink-soft);
  font-size: 16px;
  font-weight: 680;
}

.metric-grid span {
  color: var(--muted-light);
  font-size: 9px;
  font-weight: 560;
}

.priority-section {
  margin-top: 25px;
}

.priority {
  display: flex;
  gap: 10px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}

.priority:first-of-type {
  margin-top: 7px;
  border-top: 1px solid var(--line);
}

.priority-index {
  display: grid;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  place-items: center;
  border-radius: 8px;
  color: var(--green-strong);
  background: var(--green-soft);
  font-size: 9px;
  font-weight: 720;
}

.priority-copy {
  min-width: 0;
  flex: 1;
}

.priority-copy strong {
  display: block;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.35;
}

.priority-copy p,
.empty-copy {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 9px;
  line-height: 1.45;
}

.insight-note {
  margin-top: 20px;
  padding: 12px 13px;
  border: 1px solid rgba(20, 122, 80, 0.1);
  border-radius: 14px;
  color: #537064;
  background: var(--green-wash);
  font-size: 9px;
  line-height: 1.55;
}

.insight-note strong {
  display: block;
  margin-bottom: 3px;
  color: var(--green-strong);
  font-size: 10px;
}

footer {
  display: none !important;
}

@media (max-width: 1180px) {
  .gradio-container {
    padding: 12px !important;
  }

  .app-shell {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) 290px !important;
    min-height: auto;
  }

  .sidebar {
    display: grid !important;
    grid-column: 1 / -1;
    grid-template-columns: auto minmax(0, 1fr) auto;
    min-height: auto;
    align-items: center;
    gap: 18px;
    padding: 11px 13px;
  }

  .brand {
    margin: 0;
  }

  .brand-meta,
  .nav-label,
  .connection-card .eyebrow,
  .connection-row {
    display: none;
  }

  .nav-list {
    display: flex;
    justify-content: center;
    gap: 3px;
  }

  .nav-item {
    min-height: 38px;
    padding: 8px 10px;
  }

  .connection-card {
    margin: 0;
    padding: 8px 10px;
    border-radius: 12px;
  }

  .connection-head {
    margin: 0;
  }

  .workspace {
    grid-column: 1;
    min-height: auto;
  }

  .insights {
    grid-column: 2;
    min-height: auto;
  }
}

@media (max-width: 820px) {
  .app-shell {
    display: block !important;
  }

  .sidebar,
  .workspace,
  .insights {
    min-height: auto;
    margin-bottom: 10px;
  }

  .sidebar {
    display: flex !important;
    overflow-x: auto;
    flex-direction: row !important;
  }

  .brand {
    flex: 0 0 auto;
    margin-right: 6px;
  }

  .brand-mark {
    width: 34px;
    height: 34px;
    flex-basis: 34px;
  }

  .brand-meta,
  .brand-name,
  .connection-card,
  .nav-label {
    display: none;
  }

  .nav-list {
    min-width: max-content;
    justify-content: flex-start;
  }

  .workspace,
  .insights {
    padding: 20px;
  }

  .hero {
    display: block;
  }

  .hero-badge {
    margin-top: 13px;
  }

  .insights {
    display: grid !important;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
  }

  .rail-head,
  .insight-note {
    grid-column: 1 / -1;
  }

  .priority-section {
    margin-top: 0;
  }
}

@media (max-width: 600px) {
  .gradio-container {
    padding: 8px !important;
  }

  .surface {
    border-radius: 20px;
  }

  .sidebar {
    padding: 9px 10px;
  }

  .nav-item {
    min-height: 35px;
    padding: 7px 9px;
    font-size: 11px;
  }

  .nav-icon {
    display: none;
  }

  .workspace,
  .insights {
    padding: 17px;
  }

  .hero-copy h1 {
    font-size: 29px !important;
  }

  .hero-copy p {
    font-size: 12px;
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

  .grounded-label,
  .scan-limit {
    display: none;
  }

  .chatbot {
    min-height: 335px !important;
  }

  .insights {
    display: block !important;
  }

  .priority-section {
    margin-top: 24px;
  }
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
            gr.HTML(
                """
                <div class="brand">
                  <span class="brand-mark">F</span>
                  <span>
                    <span class="brand-name">FixList AI</span>
                    <span class="brand-meta">SEO workspace</span>
                  </span>
                </div>
                """
            )
            gr.HTML(
                """
                <div class="nav-label">Workspace</div>
                <div class="nav-list">
                  <div class="nav-item active">
                    <span class="nav-icon">
                      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/></svg>
                    </span>
                    Scan
                  </div>
                  <div class="nav-item">
                    <span class="nav-icon">
                      <svg viewBox="0 0 24 24"><rect x="4.5" y="5" width="15" height="14" rx="3"/><path d="M8 9h8M8 13h5"/></svg>
                    </span>
                    Projects
                  </div>
                  <div class="nav-item">
                    <span class="nav-icon">
                      <svg viewBox="0 0 24 24"><path d="M5 8v-4m0 0h4M5 4l3.2 3.2A7 7 0 1 1 6 15.5"/></svg>
                    </span>
                    History
                  </div>
                  <div class="nav-item">
                    <span class="nav-icon">
                      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.5 1A7 7 0 0 0 14.7 6L14.3 3h-4.1L9.8 6a7 7 0 0 0-1.7 1L5.6 6 3.5 9.5l2 1.5a7 7 0 0 0 0 2l-2 1.5L5.6 18l2.5-1a7 7 0 0 0 1.7 1l.4 3h4.1l.4-3a7 7 0 0 0 1.7-1l2.5 1 2-3.5-2-1.5c.1-.3.1-.7.1-1Z"/></svg>
                    </span>
                    Settings
                  </div>
                </div>
                """
            )
            gr.HTML(
                f"""
                <div class="connection-card">
                  <div class="connection-head">
                    <span class="eyebrow">System</span>
                    <span class="live-pill">Live</span>
                  </div>
                  <div class="connection-row">
                    <span>Scanner</span>
                    <span class="connection-value">{scanner_state_label}</span>
                  </div>
                  <div class="connection-row">
                    <span>Assistant</span>
                    <span class="connection-value">{ai_state_label}</span>
                  </div>
                </div>
                """
            )

        with gr.Column(scale=8, min_width=500, elem_classes=["surface", "workspace"]):
            gr.HTML(
                """
                <div class="hero">
                  <div class="hero-copy">
                    <span class="hero-kicker">Technical SEO, clarified</span>
                    <h1>Fix the signal.<br>Lose the noise.</h1>
                    <p>Scan your site, verify the evidence, and turn every finding into a prioritized action your team can ship.</p>
                  </div>
                  <span class="hero-badge">Evidence verified</span>
                </div>
                """
            )

            with gr.Group(elem_classes="scan-launcher"):
                gr.HTML(
                    """
                    <div class="scan-header">
                      <span class="scan-title">New website scan</span>
                      <span class="scan-limit">Advanced mode reviews up to 150 pages</span>
                    </div>
                    """
                )
                with gr.Row(elem_classes="scan-controls"):
                    website_input = gr.Textbox(
                        label="Website URL",
                        placeholder="Enter a domain or URL",
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

            with gr.Group(elem_classes="chat-card"):
                gr.HTML(
                    """
                    <div class="chat-card-head">
                      <div class="assistant-identity">
                        <span class="assistant-avatar">AI</span>
                        <span>
                          <span class="assistant-title">FixList consultant</span>
                          <span class="assistant-subtitle">Evidence-grounded guidance</span>
                        </span>
                      </div>
                      <span class="grounded-label">Answers use the current crawl</span>
                    </div>
                    """
                )
                chatbot = gr.Chatbot(
                    type="messages",
                    allow_tags=False,
                    height=378,
                    show_label=False,
                    container=False,
                    placeholder=(
                        "Run a scan, then ask what matters most.\n\n"
                        "Try: What should I fix first?"
                    ),
                    elem_classes="chatbot",
                )

                with gr.Group(elem_classes="compose-shell"):
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

            gr.HTML(
                '<div class="suggestion-wrap"><div class="suggestion-label">Suggested</div></div>'
            )
            with gr.Row(elem_classes="question-chips"):
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

        with gr.Column(scale=3, min_width=280, elem_classes=["surface", "insights"]):
            gr.HTML(
                """
                <div class="rail-head">
                  <div>
                    <span class="eyebrow">Current result</span>
                    <h2>Scan brief</h2>
                  </div>
                  <span class="rail-icon">
                    <svg viewBox="0 0 24 24"><path d="M4 19V9m6 10V5m6 14v-7m4 7H2"/></svg>
                  </span>
                </div>
                """
            )
            summary_panel = gr.HTML(scan_markdown(DEMO_SCAN))
            priority_panel = gr.HTML(priority_markdown(DEMO_SCAN))
            gr.HTML(
                """
                <div class="insight-note">
                  <strong>Evidence comes first</strong>
                  Provisional or limited scans stay clearly labeled and are never presented as authoritative.
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

    first_chip.click(
        fn=lambda: "What should I fix first?",
        outputs=chat_input,
    )
    score_chip.click(
        fn=lambda: "Why did I get this score?",
        outputs=chat_input,
    )
    owner_chip.click(
        fn=lambda: "Who should own each fix?",
        outputs=chat_input,
    )
    pages_chip.click(
        fn=lambda: "How many pages are affected?",
        outputs=chat_input,
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
