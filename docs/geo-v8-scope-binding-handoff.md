# GEO V8 exact observation-scope + readiness-gate + retained-source binding — integrator handoff

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Status: pre-seal only; `authority_verified=false`

## Why these adapters exist

`geo_readiness_v2_candidate` intentionally stores a collision-safe SHA-256 digest of the sorted page-ID array instead of transporting the entire page set inside the readiness block. The serialized V8 integrator still has the authoritative retained page IDs, assessment-gate facts, and any optional retained robots/`llms.txt` source observations available when it prepares a snapshot. The Lane-C transport adapters bind those exact inputs to the pre-seal candidate before any authority-sealing work.

Three independent trust gaps are covered here. First, a buggy or hostile intermediate process must not be able to rewrite an unknown-cell `page_id` or named-crawler sidecar `page_id`, recompute the non-authoritative `candidate_digest`, and rebind evidence outside the original observation scope. Second, the candidate digest must not be able to legitimize a rewritten `assessment_status`, numeric `score`, overall `coverage`, score bounds, dimension arithmetic, summary cell accounting, or gate reasons. `geo_v8_transport_semantics` reconstructs a count-equivalent matrix and delegates arithmetic back to the frozen `geo_readiness.evaluate_geo` implementation using explicit upstream `parent_authoritative`, `entry_verified`, and `access_limited` facts. Third, optional named-crawler and `llms.txt` sidecars must match the exact already-retained source observations; a recomputed candidate digest is not evidence that those derived sidecars are truthful.

## Required integrator sequence

1. Build `geo_v8_transport_candidate_v1` server-side from accepted retained evidence only.
2. Obtain the exact retained page-ID set plus the actual upstream `parent_authoritative`, `entry_verified`, and `access_limited` booleans from the serialized scan/snapshot path. Do not infer these facts from the candidate.
3. Call `validate_geo_v8_transport_scope(candidate, exact_page_ids, parent_authoritative=..., entry_verified=..., access_limited=...)`.
4. Supply the exact already-retained robots page objects used for named-crawler normalization and the exact retained `llms.txt` observation, when present, to `validate_geo_v8_transport_sources(...)`. If the candidate has no optional sidecar, pass the corresponding empty/`None` source. Access-limited candidates must have neither.
5. For canonical bytes, use `serialize_geo_v8_transport_candidate_for_sources(...)` with those same exact page IDs, gate facts, and retained source observations. Do not seal bytes produced without scope, semantic-gate, and retained-source validation.
6. Include those exact pre-seal bytes in a separately versioned authenticated V8 authority snapshot owned by the serialized integrator.
7. Persist/reload and verify that authenticated snapshot before any customer projection may set GEO authority true.

The scope check requires page-count equality; the collision-safe canonical-JSON page-set digest to match; unique bounded page IDs; every explicit unknown cell to belong to that set; and every named-crawler sidecar to belong to that set. Page order is irrelevant. Embedded delimiters such as newlines remain unambiguous because the digest material is canonical JSON, not joined text.

The semantic check first runs the existing candidate shape/digest validator, then independently reconstructs the v1-compatible result from transported per-check counts. It compares assessment status, numeric score/null state, overall coverage, score bounds, dimension/check arithmetic, reasons, sample size, and `authority_verified=false` against `geo_readiness.evaluate_geo`. It also derives the complete per-dimension summary, including unknown/N/A/verified cell counts, from the reconstructed check counts rather than trusting transported summary totals. Explicit gate facts are mandatory at the scope/sealing boundary, so recomputing the non-authoritative candidate digest cannot turn a low-coverage or gate-blocked result into an assessed numeric score.

The retained-source check reruns only the pure already-existing sidecar normalizers over exact retained observations and byte-compares their normalized structures to the candidate sidecars. It performs no network request. This prevents a rewritten named-crawler directive, evidence reference, or `llms.txt` structural field from becoming seal-eligible merely because the candidate digest was recomputed.

## Regression boundary

These adapters are pure. They do not fetch, call models/providers, modify robots behavior, change crawl/SSRF budgets, persist, project customer data, alter score thresholds, or establish authority. Existing fixed serialized acceptance-vector bytes remain unchanged because the candidate shape is unchanged; this hardening adds external exact-scope, exact-gate, and exact-retained-source proofs before those bytes are eligible for sealing.

Required regressions cover valid order-independent scope binding, wrong page sets, the historical newline-join collision shape, duplicate/malformed declarations, access-limited candidates, recomputed-digest foreign unknown cells, recomputed-digest foreign named-crawler sidecars, digest-invalid candidates, recomputed-digest score/coverage/bounds tampering, parent/entry gate tampering, unknown-cell/count disagreement, forged dimension-summary N/A/verified counts, forged named-crawler directives, forged `llms.txt` structural fields, missing/extra retained sidecar sources, and input immutability.

## Claim boundary

Scope/gate/source binding proves only internal arithmetic consistency, declared observation identity, and reproducible structural sidecar derivation from retained evidence. It does not prove or predict fetching, indexing, inclusion, appearance, ranking, citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider.
