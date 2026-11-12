# GEO V8 transport acceptance vectors — Lane C

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Transport: `geo_v8_transport_candidate_v1`
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`
Authority state: `authority_verified=false`

## Purpose

The serialized V8 integrator needs one exact byte contract for the Lane-C GEO pre-seal payload. `scanner-api/app/geo_v8_transport_serialization.py` exposes `serialize_geo_v8_transport_candidate(...)`, which validates the complete candidate and emits deterministic UTF-8 JSON using sorted keys, compact separators, and unescaped Unicode. The serialized bytes include the ordinary `candidate_digest` field.

This helper is not an authority primitive. It does not sign, HMAC, seal, persist, project, fetch, call a provider/model, or change any GEO score. The integrator may authenticate these exact validated bytes inside a separately versioned V8 authority snapshot; Lane C itself keeps both envelope and readiness `authority_verified=false`.

## Fixed vectors

`scanner-api/tests/fixtures/geo_v8_transport_acceptance_vectors.json` pins four compatibility cases:

- `assessed_full_pass`: complete verified matrix; status `assessed`, score 100, coverage 1.0.
- `all_unknown_insufficient_evidence`: no verified cells; status `insufficient_evidence`, score null, coverage 0.0.
- `marketplace_support_not_applicable`: Access/Clarity/Entity pass and all three article-only Support cells are deterministically N/A. Coverage remains exactly 0.75, so the unchanged 80% overall and 50% Support gates still withhold the numeric score.
- `access_limited`: status `access_limited`, score null, coverage 0.0, no content diagnostics.

Each vector pins the candidate digest, SHA-256 of the exact serialized transport bytes, byte length, assessment status, score/null state, and coverage. Any intentional serialization/schema change must version the transport or explicitly regenerate and review these vectors; silently changing the bytes is a compatibility failure.

The vector SHA-256 values remain non-authoritative test fingerprints. Matching them does not make a GEO result sealed, trusted, or indicative of provider outcomes.

## Integrator acceptance

Before adding GEO to a new authenticated V8 snapshot revision, the serialized integrator should:

1. reconstruct the fixed vectors with repository code and require exact vector equality;
2. build GEO only from trusted retained evidence and pass `validate_geo_v8_transport_candidate(...)`;
3. obtain bytes only through `serialize_geo_v8_transport_candidate(...)` rather than reimplementing JSON canonicalization;
4. authenticate the exact bytes as part of the versioned authority snapshot;
5. reject post-build changes to score, coverage, observation scope, unknown cells, sidecars, claim boundary, or authority state even if an attacker recomputes the ordinary candidate digest;
6. persist and reload the authenticated block without rescoring historical scans; and
7. set projected GEO authority true only after the shared V8 verifier proves that the exact block was included in the authenticated snapshot.

Historical V8 snapshots without this block must remain compatible and project a neutral legacy/not-assessed GEO state.

## Refreshed production control

Read-only production evidence was refreshed on 2026-09-23 for Funbooker scan `6ab314008da962a9f8c58929`: `complete`, 5,000 pages found, 139 crawled, 139 retained. Persisted GEO remains `insufficient_evidence` with `score=null`, overall coverage 0.456835, Access coverage 0.829736 / score 100, Clarity coverage 0.997602 / score 100, Entity coverage 0.0, and Support coverage 0.0. All 139 retained pages remain `not_verified` for `subject_identity`, `entity_details`, `schema_agreement`, `accountability`, `date_context`, and `source_attribution`.

The parent Standard 150 result is authority-sealed under `standard_review_snapshot_hmac_identity_v1`, while nested GEO remains `authority_verified=false`. These serialization vectors do not change production evidence, applicability, thresholds, or authority state. In particular, the marketplace vector proves that deterministic Support N/A cells alone do not weaken the unchanged evidence gates.

## Claim boundary

These vectors test FixList structural readiness transport only. They do not measure or predict appearance, ranking, citations, inclusion, visibility, indexing, fetching, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider.
