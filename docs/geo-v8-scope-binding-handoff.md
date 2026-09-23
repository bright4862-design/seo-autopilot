# GEO V8 exact observation-scope + readiness-gate binding — integrator handoff

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Status: pre-seal only; `authority_verified=false`

## Why this adapter exists

`geo_readiness_v2_candidate` intentionally stores a collision-safe SHA-256 digest of the sorted page-ID array instead of transporting the entire page set inside the readiness block. The serialized V8 integrator still has the authoritative retained page IDs and assessment-gate facts available when it prepares a snapshot. The `geo_v8_transport_scope` adapter binds those exact inputs to the pre-seal candidate before any authority-sealing work.

Two independent trust gaps are covered here. First, a buggy or hostile intermediate process must not be able to rewrite an unknown-cell `page_id` or named-crawler sidecar `page_id`, recompute the non-authoritative `candidate_digest`, and rebind evidence outside the original observation scope. Second, the candidate digest must not be able to legitimize a rewritten `assessment_status`, numeric `score`, overall `coverage`, score bounds, dimension arithmetic, or gate reasons. `geo_v8_transport_semantics` therefore reconstructs a count-equivalent matrix and delegates the arithmetic back to the frozen `geo_readiness.evaluate_geo` implementation using explicit upstream `parent_authoritative`, `entry_verified`, and `access_limited` facts.

## Required integrator sequence

1. Build `geo_v8_transport_candidate_v1` server-side from accepted retained evidence only.
2. Obtain the exact retained page-ID set plus the actual upstream `parent_authoritative`, `entry_verified`, and `access_limited` booleans from the serialized scan/snapshot path. Do not infer these facts from the candidate.
3. Call `validate_geo_v8_transport_scope(candidate, exact_page_ids, parent_authoritative=..., entry_verified=..., access_limited=...)`.
4. For canonical bytes, use `serialize_geo_v8_transport_candidate_for_scope(...)` with those same exact page IDs and gate facts. Do not seal bytes produced without this scope + semantic gate check.
5. Include those exact pre-seal bytes in the separately versioned authenticated V8 authority snapshot.
6. Persist/reload and verify the authenticated snapshot before any customer projection may set GEO authority true.

The scope check requires page-count equality; the collision-safe canonical-JSON page-set digest to match; unique bounded page IDs; every explicit unknown cell to belong to that set; and every named-crawler sidecar to belong to that set. Page order is irrelevant. Embedded delimiters such as newlines remain unambiguous because the digest material is canonical JSON, not joined text.

The semantic check first runs the existing candidate shape/digest validator, then independently reconstructs the v1-compatible result from transported per-check counts. It compares assessment status, numeric score/null state, overall coverage, score bounds, dimension/check arithmetic, reasons, sample size, and `authority_verified=false` against `geo_readiness.evaluate_geo`. Explicit gate facts are mandatory at the scope/sealing boundary, so recomputing the non-authoritative candidate digest cannot turn a low-coverage or gate-blocked result into an assessed numeric score.

## Regression boundary

These adapters are pure. They do not fetch, call models/providers, modify robots behavior, change crawl/SSRF budgets, persist, project customer data, alter score thresholds, or establish authority. Existing fixed serialized acceptance-vector bytes remain unchanged because the candidate shape is unchanged; this hardening adds external exact-scope and exact-gate proofs before those bytes are eligible for sealing.

Required regressions cover valid order-independent binding, wrong page sets, the historical newline-join collision shape, duplicate/malformed declarations, access-limited candidates, recomputed-digest foreign unknown cells, recomputed-digest foreign named-crawler sidecars, digest-invalid candidates, recomputed-digest score/coverage/bounds tampering, parent/entry gate tampering, unknown-cell/count disagreement, and input immutability.

## Claim boundary

Scope/gate binding proves only internal arithmetic consistency and that structural GEO evidence belongs to the declared retained page set under the supplied assessment gates. It does not prove or predict fetching, indexing, inclusion, appearance, ranking, citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider.
