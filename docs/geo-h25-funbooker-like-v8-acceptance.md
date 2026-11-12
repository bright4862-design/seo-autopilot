# H2-5 GEO V8 Funbooker-like insufficient-evidence acceptance

Date: 2026-09-23  
Lane: `agent/ai-geo-readiness-20260923`  
Parent checkpoint: `094ba07e19a6899eda5b6f94ae8d1b06df8bc076`  
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Purpose

This checkpoint adds a production-shaped synthetic acceptance case for the GEO V8 pre-seal transport. It is deliberately an aggregate-shape fixture rather than a copy of customer page content: 139 opaque page IDs reproduce the current Funbooker evidence distribution while retaining no customer HTML, URLs, provider credentials, or provider visibility data.

The acceptance case proves that an `insufficient_evidence` GEO result with strong Access and Clarity evidence but zero verified Entity and Support evidence survives the Lane-C V8 candidate, exact scope/source binding, canonical serialization, and post-reload byte identity without becoming scored or authoritative.

## Refreshed production control

The production `ScanRun` for `6ab314008da962a9f8c58929` was re-read on 2026-09-23 before this checkpoint. It remains complete with 5,000 pages found, 139 crawled, and 139 retained. Its persisted GEO result remains:

- `assessment_status=insufficient_evidence`
- numeric `score=null`
- overall coverage `0.456835`
- Access coverage `0.829736`, score `100`
- Clarity coverage `0.997602`, score `100`
- Entity coverage `0`, score `null`
- Support coverage `0`, score `null`
- reasons: overall coverage below 80%, Entity coverage below 50%, Support coverage below 50%
- `authority_verified=false`

The persisted check distribution is 139/139 pass for `search_policy` and `indexability`, 68 pass plus 71 `not_verified` for `discovery`, 139/139 pass for `main_text` and `template_integrity`, 138 pass plus one `not_verified` for `page_identity`, and 139/139 `not_verified` for each of `subject_identity`, `entity_details`, `schema_agreement`, `accountability`, `date_context`, and `source_attribution`.

## Acceptance contract

`scanner-api/tests/test_geo_v8_funbooker_like_acceptance.py` constructs that same 1,668-cell distribution over synthetic opaque page IDs. It asserts:

- exact overall and per-dimension display coverage;
- Access and Clarity can score 100 while the overall score remains withheld;
- Entity and Support remain unscored at zero verified coverage;
- the 906 unresolved cells remain explicit in `geo_readiness_v2_candidate`;
- the unchanged v1 evidence-gate reasons remain present;
- both readiness and transport remain `authority_verified=false`;
- the source-bound candidate survives exact post-reload byte identity; and
- page/observation ordering cannot change canonical pre-seal bytes.

This is a compatibility/transport regression only. It does not change `geo_evidence.py`, `geo_readiness.py`, applicability, score thresholds, dimension weights, crawler/robots/SSRF behavior, persistence, authority, customer projection, deployment, or production.

## GEO coverage implication

Zero. The fixture freezes the current insufficient-evidence state rather than trying to make it score. In particular, the 80% overall evidence gate and 50% per-dimension gates are unchanged. Future deterministic evidence improvements may legitimately convert individual unknown cells to verified or `not_applicable`, but only actual evidence/applicability changes may move coverage.

## Claim boundary

FixList continues to report structural readiness only. This acceptance case does not measure or predict fetching, indexing, inclusion, appearance, ranking, citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or another provider. No model or provider-visibility API is involved.

## Integrator handoff

The serialized integrator should use this production-shaped regression when it places the exact source-bound GEO candidate bytes inside a newly versioned authenticated V8 snapshot. The post-seal acceptance must prove historical compatibility, tamper rejection, persistence/reload byte equality, entitlement/customer projection behavior, and end-to-end authority verification. Until the exact GEO block is covered by that authenticated snapshot and verified end-to-end, `authority_verified=false` remains mandatory.
