# GEO V8 pre-seal transport candidate — Lane C

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Purpose

`scanner-api/app/geo_v8_transport_candidate.py` packages the existing `geo_readiness_v2_candidate` together with optional named-crawler robots and `llms.txt` structural sidecars into one bounded **unsealed** transport candidate for the serialized V8 integrator.

The helper performs no fetch, model/provider call, persistence, customer projection, authority signing, crawler/robots/SSRF change, score-threshold change, release action, deployment, or production mutation. `authority_verified` is false both inside the readiness result and at the transport envelope.

The candidate SHA-256 digest is only a deterministic integrity/checkpoint aid. It is not an HMAC, signature, authority proof, provider signal, or production seal.

## Why this exists

The V8 handoff already requires one exact GEO block to be included inside a future authenticated snapshot. Before the serialized integrator touches shared authority/persistence code, Lane C now supplies a pure fail-closed envelope that:

- computes readiness server-side from typed observations through `evaluate_geo_v2`;
- retains the frozen v1 score/coverage arithmetic and gate behavior;
- binds the v2 observation-scope digest, dimension summaries, unknown cells, versions, reasons and score/null state;
- optionally attaches already-retained named-crawler robots evidence for pages inside the same observation scope;
- optionally attaches an already-retained `llms.txt` structural observation;
- keeps both sidecars outside the scored readiness matrix, so they cannot rescue insufficient evidence or change the numeric score;
- rejects malformed/tampered internal counts, scope metadata, versions, unknown-cell accounting, sidecars, claim boundaries, or authority state; and
- strips optional sidecars on globally access-limited assessments to preserve the existing fail-closed diagnostic boundary.

## Integrator use

The serialized integrator may call `build_geo_v8_transport_candidate(...)` only from trusted server-side retained evidence. It must not accept a client-provided candidate. The integrator should validate the candidate, then include the **exact candidate object** inside a newly versioned authenticated V8 snapshot and verify persistence/reload equality.

`validate_geo_v8_transport_candidate(...)` is a structural validator only. It is not a substitute for the repository's authority verifier. A passing Lane-C validation must never set `authority_verified=true`.

The integrator still owns all shared changes required by `docs/geo-v8-authority-handoff.md`: authenticated snapshot versioning, persistence, historical compatibility, tamper rejection through the real authority path, customer projection/entitlement, generated contract propagation, staged acceptance, and any eventual authority=true projection.

## Sidecar rules

### Named crawlers

Only exact retained user-agent evaluations from `geo_named_robots_evidence_v1` are accepted. Sidecars must bind to page identities already present in the readiness observation scope. GPTBot training policy remains neutral and cannot affect the readiness score.

### llms.txt

Only an already-retained observation accepted by `geo_llms_txt_evidence_v1` may be attached. The Lane-C helper performs no network request. `llms.txt` absence remains neutral; presence/validity is structural metadata only and cannot affect the readiness score.

## Claim boundary

This transport describes FixList structural readiness evidence. It does **not** measure, predict, or prove fetching, indexing, inclusion, appearance, ranking, citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or another provider.

Authority sealing, when eventually implemented by the integrator, will prove only that the FixList result was authenticated; it will not turn structural evidence into a provider-outcome claim.

## Verification in this checkpoint

Before push, a hermetic Lane-C harness passed **31/31 focused transport regressions** and **54/54 broader relevant GEO compatibility checks**. Coverage included v1/v2 compatibility, 80% coverage-gate behavior, unknown/N/A handling, access-limited behavior, exact named-crawler policy evidence, GPTBot neutrality, `llms.txt` valid/invalid/absent/unknown states, sidecar score isolation, scope binding, deterministic candidate generation, authority=false invariants, and tamper rejection.

Repository exact-head CI remains authoritative after push.

## Production/Funbooker implication

This transport candidate does not change GEO evidence extraction, applicability, score thresholds, dimension weights, or the current production result. The reported Funbooker baseline therefore remains `assessment_status=insufficient_evidence` with score null unless a future rerun genuinely gains enough deterministic Entity/Support evidence to satisfy the unchanged gates.

The scan ID `6ab314008da962a9f8c58929` was searched in the repository/issue surface again during this run and was not independently retrievable there. No new production-coverage claim is made from this transport-only checkpoint.

## Next step

Wait for exact-head CI on this branch, then hand the pure pre-seal candidate plus `docs/geo-v8-authority-handoff.md` to the serialized integrator. The integrator should add authenticated V8 transport only after historical compatibility, tamper rejection, reload equality, entitlement, and claim-boundary tests are green. No production deployment belongs to Lane C.
