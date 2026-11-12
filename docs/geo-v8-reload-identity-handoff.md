# GEO V8 reload identity handoff

Status: Lane-C pre-seal acceptance contract only. This document does not modify
shared authority, persistence, customer projection, crawler budgets, release
wiring, or production.

## Why this boundary exists

`geo_v8_transport_candidate_v1` is intentionally unsealed. Its
`candidate_digest` detects accidental candidate changes, but it is not an
authority signature. Scope binding and retained-source binding prove that the
candidate can be reproduced from the exact page set and already-retained
robots/`llms.txt` observations. A serialized integrator still needs one more
identity guarantee: the object reloaded from persistence must canonicalize to
the exact same source-bound bytes that were accepted before authority sealing.

`scanner-api/app/geo_v8_transport_reload.py` supplies that pure acceptance seam.
It performs no persistence read/write itself. The integrator provides:

- the exact canonical pre-seal bytes captured after scope/source binding;
- the reloaded candidate object;
- the exact retained page-ID set;
- the explicit parent-authoritative / entry-verified / access-limited gate facts;
- the same retained named-crawler robots observations and optional `llms.txt`
  observation.

The helper reruns the complete source-binding path and then requires exact
canonical byte equality. Mapping insertion order and retained robots-source
order are not identity; semantic payload changes are.

## Integrator acceptance sequence

1. Build `geo_readiness_v2_candidate` from deterministic retained observations.
2. Build `geo_v8_transport_candidate_v1`; keep both candidate-level and nested
   `authority_verified=false`.
3. Bind the exact retained page set and assessment gates.
4. Re-derive named-crawler robots and optional `llms.txt` sidecars from the
   exact retained source observations.
5. Capture the resulting canonical source-bound bytes as the pre-seal identity.
6. Persist/reload through the integrator-owned path.
7. Re-run `validate_geo_v8_transport_reload_identity(...)` against the exact
   pre-seal bytes and retained inputs.
8. Only after byte equality succeeds may the serialized authority owner include
   those exact bytes in a newly versioned authenticated V8 authority snapshot.
9. Prove historical compatibility, tamper rejection, entitlement/customer
   projection behavior, and end-to-end authority verification before any GEO
   `authority_verified=true` projection.

The fixed retained-source vectors live in
`scanner-api/tests/fixtures/geo_v8_retained_source_acceptance_vectors.json`.
They cover observed named-crawler directives with a structurally valid
`llms.txt`, plus unavailable robots evidence with an absent `llms.txt`. Both
produce identical scored readiness from identical scored observations, proving
that these sidecars remain non-scoring structural evidence.

## Claim boundary

This transport contract says nothing about provider outcomes. It does not prove
or predict fetching, indexing, inclusion, appearance, ranking, citations,
visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude,
OpenAI products, or any other provider. No provider/model call is part of this
handoff, and no GEO score threshold is changed.
