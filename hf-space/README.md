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

A minimal, chat-first SEO audit demo for the FixList scanner.

## What this demo shows

- A clean AI conversation interface
- A compact scan summary and prioritized fixes
- Evidence-grounded answers
- Optional Grok 4.20 Reasoning integration through Google Cloud
- A deterministic demo mode when cloud credentials are not configured
- A Gradio API endpoint that automatically exposes `/agents.md`

## Required Space secrets for live Grok mode

Add these in the Hugging Face Space settings:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Optional variables:

- `VERTEX_LOCATION=global`
- `GROK_MODEL_ID=xai/grok-4.20-reasoning`
- `FIXLIST_API_URL`
- `FIXLIST_API_TOKEN`

`GOOGLE_SERVICE_ACCOUNT_JSON` should contain the full service-account JSON document as a secret.

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

The primary Gradio API endpoint is named `chat`.
