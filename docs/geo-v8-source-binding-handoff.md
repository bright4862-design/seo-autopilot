# GEO V8 exact retained-source binding — integrator handoff

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Status: pre-seal only; `authority_verified=false`

## Purpose

`geo_v8_transport_sources` is the final Lane-C pure validation seam before a serialized integrator may treat GEO candidate bytes as eligible input to an authenticated V8 snapshot. It does not create authority.

The transport candidate already carries normalized named-crawler robots and optional `llms.txt` structural sidecars. Those sidecars are derived from retained observations, but `candidate_digest` is intentionally non-authoritative. Without source rebinding, an intermediate process could alter a structurally valid sidecar, recompute the digest, and preserve candidate-shape validity.

This adapter closes that gap by regenerating every optional sidecar from the exact retained source observations already held by the integrator and requiring canonical structural equality.

## Contract

`validate_geo_v8_transport_sources(...)` first executes the exact page-set and readiness-gate validator. It then:

- bounds retained robots source pages to Standard 150 and requires page objects;
- re-runs `extract_named_robots_evidence` for every supplied retained robots source page, sorts by opaque page identity, and requires exact equality with `candidate.named_robots`;
- re-runs `extract_llms_txt_evidence` for the supplied retained `llms.txt` observation and requires exact equality with `candidate.llms_txt`;
- requires omitted sidecars to have omitted source observations as well;
- rejects optional source observations for an access-limited candidate; and
- never mutates the candidate or retained source inputs.

The source adapter does not fetch robots.txt or `llms.txt`. It can only normalize observations that another accepted scan path already retained. It does not add crawler budget, robots behavior, SSRF surface, provider calls, or model calls.

## Seal eligibility sequence

The serialized integrator should call `serialize_geo_v8_transport_candidate_for_sources(...)` only with:

1. the exact candidate built from accepted retained GEO evidence;
2. the exact retained page-ID set;
3. the actual `parent_authoritative`, `entry_verified`, and `access_limited` gate facts;
4. the exact retained robots page objects used to derive any named-crawler sidecars; and
5. the exact retained `llms.txt` observation used to derive the optional structural sidecar.

The returned bytes are still **unsealed** and **non-authoritative**. A separately versioned authenticated V8 snapshot must include those exact bytes and then pass persistence/reload verification before GEO authority can become true anywhere downstream.

## Acceptance regressions

The Lane-C contract locks:

- exact retained robots + `llms.txt` observations reproduce the candidate and preserve canonical candidate bytes;
- recomputed-digest named-crawler directive tampering fails source binding;
- recomputed-digest `llms.txt` structural-count tampering fails source binding;
- missing or extra retained robots sources fail;
- missing or extra retained `llms.txt` sources fail;
- access-limited candidates accept no optional sources and reject any supplied source observations; and
- validation is input-immutable.

## Claim boundary

This binding says only that optional structural sidecars were reproducibly derived from the supplied retained observations. It does not prove a named crawler fetched the site, that `llms.txt` is consumed by any provider, or that a site appears, ranks, is cited, is included, gains visibility, or receives traffic from ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider.
