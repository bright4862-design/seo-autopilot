# Hugging Face Space Grok Capability Findings

Date: 2026-08-21

## What the current Space actually does

The existing `hf-space` is a Docker/Gradio application hosted on Hugging Face. It is **not** currently using Hugging Face Inference Providers for Grok.

Its Grok behavior has two routes:

1. When `SCANNER_API_KEY` is configured, `Settings.live_scan_enabled` is true and `call_grok()` sends the request to the production scanner `/chat` endpoint. In that path, the scanner's own Grok model/configuration answers the request.
2. Only when the Space is not using the live scanner path does `call_grok()` perform a direct Vertex AI request using the Space's Google credentials and `GROK_MODEL_ID`.

## Configuration mismatch to resolve before integration

The Space documentation and `.env.example` describe:

`GROK_MODEL_ID=xai/grok-4.20-reasoning`

but `hf-space/app.py` defaults to:

`xai/grok-4.20-non-reasoning`

Meanwhile the production scanner currently defaults to:

`xai/grok-4.20-non-reasoning`

Therefore "the HF Grok capability" is not yet one unambiguous runtime contract. On the normal live-scan path, the Space routes through scanner `/chat` and inherits the production scanner model. The reasoning model setting applies only to the Space's direct-Vertex path (or an explicitly different configuration).

## What not to integrate

Do not route Standard 150 through the HF Space. The Space stores its current scan result in the active session and is not the durable authority system. Do not copy its scan lifecycle, session storage, or direct service-account path into production FixList.

Do not copy the older Space prompt wholesale. The production `grok_chat.py` prompt has already evolved to the newer natural/DIY contract and should remain the parity baseline.

## Preferred interpretation for next week's integration

If the desired capability is **Grok 4.20 reasoning**, the safest candidate is:

```text
current signed FixList authority
  -> existing Base44 gate
  -> existing scanner /chat boundary
  -> existing Vertex transport
  -> reasoning model candidate
```

That path changes only model selection behind an already-proven transport and avoids introducing:

- a new Hugging Face inference token;
- a new inference-provider network dependency;
- new IAM for a separate provider;
- a new authority path;
- a new persistence path;
- HF Space as middleware.

The first reasoning experiment should still be offline/shadow only. Vertex non-reasoning remains the customer-facing default and rollback.

## Separate optional research lane

Hugging Face Inference Providers are a separate possible provider strategy. Current HF documentation lists providers such as Groq, Together, Fireworks, Cerebras, DeepInfra, and HF Inference; xAI is not listed as an HF Inference Provider. Treat an HF-hosted open model comparison as a separate model/provider evaluation, not as a drop-in replacement for the current Grok service.

## Decision gate

Before Wednesday 2026-08-26, freeze one interpretation:

**Preferred:** compare current Vertex Grok 4.20 non-reasoning against Vertex Grok 4.20 reasoning using the same authoritative provider payload and transport contract.

**Separate experiment:** evaluate a named Hugging Face Inference Provider model with its own provider identity and credentials.

Do not combine both changes in the first production adapter PR.
