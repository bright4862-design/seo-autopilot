# FixList Provider Lab

Status: **isolated experiment — not production runtime**

Baseline parent: `main@8f03c4600eb8c8504cd90b6c5861e32e83a5568b`

This directory is the only approved surface for provider-abstraction and Hugging Face evaluation work before a separately reviewed production integration.

## Isolation contract

The lab must not change or become a dependency of any protected FixList runtime surface.

Protected surfaces include:

- `scanner-api/app/` crawler, worker, review, persistence, terminalization, and `/chat` runtime;
- Base44 ownership, authority-snapshot reconstruction, HMAC verification, and release gates;
- Standard 150 page-cap, robots/SSRF, durable `scan_id`, admission, reconciliation, or kill-switch behavior;
- deployment workflows, IAM, secrets, feature flags, or serving revisions.

The production scanner image copies only `scanner-api/app` from the scanner build context. This lab lives outside that directory and is not imported by production code.

**Hard rule:** production code must never import `experiments.provider_lab`. Any future production integration requires a separate reviewed change after this lab has passed its gates.

## Current architecture boundary

```text
Standard 150
  -> persisted + signed FixList evidence
  -> Base44 ownership / authority / release checks
  -> compact provider-facing scan evidence
  -> scanner /chat kill switch
  -> current Vertex Grok provider
```

Provider experimentation belongs strictly to the right of the signed-evidence boundary.

### Important current behavior

Canonical repair-v2 fields are part of the signed Base44 authority snapshot, but the current `buildScanEvidence()` payload sent to `/chat` is intentionally compact and legacy-compatible. The provider currently receives fields such as `priority`, URLs, steps, counts, and verified URLs; it does **not** receive canonical action rank or the full repair-v2 priority context.

The lab therefore models two different things:

1. an **authority manifest** proving the fixture came from a valid authoritative scan boundary; and
2. the **provider payload** that the model actually receives.

The lab must never reimplement HMAC verification or become a second authority system.

## Phase plan

### Phase 0 — refreshed baseline

- Freeze the exact current-main parent SHA above.
- Keep `GROK_CHAT_ENABLED=false` and `GROK_PROXY_ENABLED=false` in production.
- Do not deploy or modify credentials.

### Phase 1 — authority + provider contracts

- Require a validated authority manifest before a case can be evaluated.
- Accept current repair-v2 manifests only when their contract fields are complete and mutually consistent.
- Preserve intentional support for already-valid legacy authoritative snapshots.
- Reject mixed/partial v2 manifests, failed/provisional/blocking scans, and identity mismatches.
- Hash provider evidence and authority metadata separately for traceability.
- Keep all code network-free.

### Phase 2 — Vertex parity

Inside this lab only:

- reproduce the current Vertex request/response contract with fakes/recorded fixtures;
- compare model ID, payload shape, retry classification, output extraction, and public error semantics;
- make no live model calls from automated tests;
- do not edit `scanner-api/app/grok_chat.py`.

Exit gate: the lab demonstrates a provider interface can represent current Vertex behavior without changing customer-visible semantics.

### Phase 3 — Hugging Face offline candidate

- name the exact HF model and exact inference provider;
- use sanitized authoritative fixtures only;
- run outside the customer request path;
- record authority hash, evidence hash, model/provider identity, latency, output, and failure class;
- reject candidates that invent URLs/counts/findings or treat provisional evidence as authoritative.

No live shadow traffic is allowed in this phase.

### Phase 4 — production integration proposal

Target planning window: **Wednesday 2026-08-26 or Thursday 2026-08-27**, only if all earlier gates are green.

- create a separate production adapter PR from then-current `main`;
- preserve both Grok kill switches;
- keep Vertex as default/rollback;
- provider output remains advisory and cannot mutate ScanRun/FixList/FixItem authority;
- stage at 0% traffic with Grok OFF;
- verify exact SHA/image/Base44 revision before any shadow enablement.

## Acceptance gates before any production wiring

1. Refreshed provider-lab exact SHA is green.
2. `GROK_CHAT_ENABLED=false` produces zero provider calls.
3. `GROK_PROXY_ENABLED=false` produces zero provider calls.
4. Wrong-owner, tampered, unsigned, provisional, failed, blocking, mixed-contract, or release-ineligible evidence produces zero provider calls.
5. Provider failures cannot mutate authoritative scan state.
6. Vertex-only rollback needs no migration, resealing, or scan replay.
7. Exact serving image/revision and live flags are verified before enablement.
8. No provider-lab module is packaged into or imported by production scanner code.

## Running the lab checks

From the repository root:

```bash
python -m unittest discover -s experiments/provider_lab/tests -p 'test_*.py'
```

These tests are intentionally independent of the scanner runtime and require no network credentials.
