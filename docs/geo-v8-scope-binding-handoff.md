# GEO V8 exact observation-scope binding — integrator handoff

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Status: pre-seal only; `authority_verified=false`

## Why this adapter exists

`geo_readiness_v2_candidate` intentionally stores a collision-safe SHA-256 digest of the sorted page-ID array instead of transporting the entire page set inside the readiness block. The serialized V8 integrator still has the authoritative retained page IDs available when it prepares a snapshot. The new `geo_v8_transport_scope` adapter binds those exact IDs to the pre-seal candidate before any authority-sealing work.

This closes a transport trust gap that the ordinary semantic validator cannot close by itself: if an attacker or buggy intermediate process rewrites an unknown-cell `page_id` or named-crawler sidecar `page_id` and recomputes the non-authoritative `candidate_digest`, the candidate can remain structurally self-consistent while referring to a page outside the original observation scope. The scope validator rejects that rebinding against the authoritative page set.

## Required integrator sequence

1. Build `geo_v8_transport_candidate_v1` server-side from accepted retained evidence only.
2. Call `validate_geo_v8_transport_scope(candidate, exact_page_ids)` using the exact retained page-ID set owned by the scan/snapshot path.
3. For canonical bytes, use `serialize_geo_v8_transport_candidate_for_scope(candidate, exact_page_ids)`. Do not seal bytes produced without the exact scope check.
4. Include those exact pre-seal bytes in the separately versioned authenticated V8 authority snapshot.
5. Persist/reload and verify the authenticated snapshot before any customer projection may set GEO authority true.

The scope check requires: page count equality; the collision-safe canonical-JSON page-set digest to match; unique bounded page IDs; every explicit unknown cell to belong to that set; and every named-crawler sidecar to belong to that set. Page order is irrelevant. Embedded delimiters such as newlines remain unambiguous because the digest material is canonical JSON, not joined text.

## Regression boundary

The adapter is pure. It does not fetch, call models/providers, modify robots behavior, change crawl/SSRF budgets, persist, project customer data, alter scoring, or establish authority. Existing fixed serialized acceptance-vector bytes remain unchanged because the candidate shape is unchanged; this adapter adds an external exact-scope proof before those bytes are eligible for sealing.

Required regressions cover valid order-independent binding, wrong page sets, the historical newline-join collision shape, duplicate/malformed declarations, access-limited candidates, recomputed-digest foreign unknown cells, recomputed-digest foreign named-crawler sidecars, digest-invalid candidates, and input immutability.

## Claim boundary

Scope binding proves only that the structural GEO evidence belongs to the declared retained page set. It does not prove or predict fetching, indexing, inclusion, appearance, ranking, citations, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider.
