# GEO V8 exact scored-observation binding — integrator handoff

Date: 2026-09-23  
Lane: `agent/ai-geo-readiness-20260923`

## Refreshed baseline

This checkpoint is reconciled with current `main`
`a9a96faf24ee9a841720981dcfbcee7bf0967a84`, which contains the customer
rescan-comparison milestone but does not seal, score, or customer-project the
Lane-C GEO v2 candidate.

The latest read-only production control remains Funbooker scan
`6ab314008da962a9f8c58929`: 5,000 URLs found, 139 crawled and retained,
`assessment_status=insufficient_evidence`, numeric score `null`, overall
coverage about 45.68%, Access about 82.97% with score 100, Clarity about 99.76%
with score 100, and Entity/Support at zero verified coverage. All six
Entity/Support checks remain `not_verified` across 139 pages, and the nested GEO
result remains `authority_verified=false`. This transport-only change has no
effect on those values.

## Purpose

The existing Lane-C pre-seal chain revalidates GEO arithmetic and gates, binds
the declared page set, and reproduces optional robots and `llms.txt` sidecars
from retained sources. Aggregate check counts alone do not identify which page
carried a pass, fail, or unknown result. Two different page-level allocations
can therefore produce the same internally valid aggregate candidate.

`geo_v8_transport_observation_binding_v1` closes that provenance gap. It
rebuilds the complete candidate from the exact typed `Observation` population
and records a canonical SHA-256 fingerprint over every observation's opaque
page identity, check identity, state, evidence reference, and reason.
Observation order is non-authoritative; population content is authoritative.

## Fail-closed contract

Before bytes are eligible for the serialized integrator, the binding requires:

1. exact bounded page identities and explicit boolean gate facts;
2. the frozen v1 evaluator's typed-field, state, evidence-reference, duplicate,
   and Standard-150 bounds;
3. byte-equivalent candidate reconstruction from those exact observations and
   retained optional sidecar sources;
4. an exact observation count and canonical population fingerprint;
5. strict version, field-set, claim-boundary, digest, and reload-byte identity;
6. `seal_state=unsealed_candidate` and `authority_verified=false`.

An access-limited binding cannot carry content observations. A changed
page-level allocation or evidence reference changes the binding even when the
aggregate score and coverage remain identical.

## Serialized integration sequence

The shared owner should use this order:

`trusted retained observations -> candidate reconstruction -> exact observation binding -> canonical pre-seal bytes -> versioned authenticated V8 snapshot -> persistence/reload byte equality -> customer projection acceptance`

This helper is not an authority seal. The ordinary SHA-256 binding digest is an
integrity checkpoint only. The integrator must authenticate the exact bound
bytes inside a separately versioned V8 authority snapshot before any downstream
surface may set GEO authority true.

## Product and claim boundaries

This change does not alter evidence classification, applicability, score
thresholds, dimension weights, crawler budgets, robots behavior, persistence,
or customer copy. It performs no fetch and no model/provider call.

FixList continues to report structural readiness only. The binding does not
measure or predict fetching, indexing, inclusion, appearance, ranking,
citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini,
Claude, OpenAI products, or any other provider. `authority_verified=false`
remains mandatory until the authenticated end-to-end V8 path is accepted.
