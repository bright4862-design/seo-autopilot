# FixList Provider Lab

Status: **isolated experiment — not production runtime**

This directory is the only approved surface for the first provider-abstraction and Hugging Face evaluation work.

## Isolation contract

The lab must not change or become a dependency of any protected FixList runtime surface.

Protected surfaces include:

- `scanner-api/app/` crawler, worker, review, persistence, terminalization, and `/chat` runtime;
- Base44 ownership, authority-snapshot reconstruction, HMAC verification, and release gates;
- Standard 150 page-cap, robots/SSRF, durable `scan_id`, admission, reconciliation, or kill-switch behavior;
- deployment workflows, IAM, secrets, feature flags, or serving revisions.

The production scanner image currently copies only `scanner-api/app` from the scanner build context. This lab lives outside that directory and is not imported by production code.

**Hard rule:** production code must never import `experiments.provider_lab`. Any future production integration requires a separate reviewed change after the lab has passed its gates.

## Current architecture boundary

```text
Standard 150
  -> persisted + signed FixList evidence
  -> Base44 ownership / authority / release checks
  -> scanner /chat kill switch
  -> current Vertex Grok provider
```

Provider experimentation belongs strictly to the right of the signed-evidence boundary.

## Phase plan

### Phase 0 — baseline

- Freeze the exact `main` parent SHA used by the lab branch.
- Keep `GROK_CHAT_ENABLED=false` and `GROK_PROXY_ENABLED=false` in production.
- Do not deploy or modify credentials.

### Phase 1 — data-only contracts (this slice)

Build a provider-neutral offline contract that:

- requires `release_gate_eligible == true` for evaluation fixtures;
- records exact provider name and model ID;
- hashes canonical evidence so every result is traceable to one fixture;
- measures latency and bounded errors;
- contains no network client or cloud SDK imports.

### Phase 2 — Vertex parity adapter

Inside this lab only:

- reproduce the current Vertex request/response contract with fakes/recorded fixtures;
- compare prompt, model ID, retry classification, output extraction, and public error semantics;
- make no live model calls from automated tests;
- do not edit `scanner-api/app/grok_chat.py` yet.

Exit gate: lab evidence demonstrates a provider interface can represent current Vertex behavior without changing customer-visible semantics.

### Phase 3 — Hugging Face offline candidate

- name the exact HF model and exact inference provider;
- use sanitized authoritative fixtures only;
- run outside the customer request path;
- record evidence hash, model/provider identity, latency, output, failure class, and human grounding score;
- reject any candidate that invents URLs/counts/findings or treats provisional evidence as authoritative.

No live shadow traffic is allowed in this phase.

### Phase 4 — internal shadow proposal

Only after Phase 3 passes:

- design a separate, reviewable production adapter;
- preserve both Grok kill switches;
- provider output remains advisory only and cannot mutate ScanRun/FixList/FixItem authority;
- Vertex remains the rollback/default path;
- shadow traffic requires explicit enablement and independent deployment evidence.

## Acceptance gates before any production wiring

1. Exact-SHA Standard 150 regression suite is green.
2. `GROK_CHAT_ENABLED=false` produces zero provider calls.
3. `GROK_PROXY_ENABLED=false` produces zero provider calls.
4. Wrong-owner, tampered, unsigned, provisional, failed, or release-ineligible evidence produces zero provider calls.
5. Provider failures cannot mutate authoritative scan state.
6. Vertex-only rollback needs no migration, resealing, or scan replay.
7. Exact serving image/revision and live flags are verified before enablement.

## Running the Phase 1 lab checks

From the repository root:

```bash
python -m unittest discover -s experiments/provider_lab/tests -p 'test_*.py'
```

These tests are intentionally independent of the scanner runtime and require no network credentials.
