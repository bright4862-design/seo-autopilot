---
title: FixList AI
emoji: 🧭
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
fullWidth: true
---

# FixList AI

A minimal, chat-first interface for the FixList scanner.

## Current capabilities

- Launch a bounded 150-page scan through the production Cloud Run scanner
- Run the deterministic Python review after crawling
- Display scan authority, score, page counts, and grouped priorities
- Ask evidence-grounded questions about the current result
- Use Grok 4.20 Reasoning through Vertex AI when configured
- Fall back to structured guided answers when Grok is not configured
- Expose Gradio API endpoints and `/agents.md`

The Run Scan v1 result is held in the active Space session. Durable project history and FixList persistence are a later milestone.

## Required Space secret for new scans

Add this under **Settings → Variables and secrets → Secrets**:

- `SCANNER_API_KEY`

The scanner URL defaults to the production Cloud Run service. It can be overridden with:

- `SCANNER_API_URL`
- `SCANNER_TIMEOUT_SECONDS=240`

The key is sent only from the Space server using the `X-Scanner-Key` header. It is never exposed to the browser.

## Required Space secrets for live Grok mode

Add:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Optional variables:

- `VERTEX_LOCATION=global`
- `GROK_MODEL_ID=xai/grok-4.20-reasoning`
- `GROK_TIMEOUT_SECONDS=90`

`GOOGLE_SERVICE_ACCOUNT_JSON` should contain the complete service-account JSON document as a private secret.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:7860`.

## Docker

```bash
docker build -t fixlist-ai .
docker run --rm -p 7860:7860 fixlist-ai
```

## API

After the Space starts, coding agents can inspect:

```bash
curl https://huggingface.co/spaces/<owner>/<space>/agents.md
```

The primary endpoints are named `run_scan` and `chat`.
