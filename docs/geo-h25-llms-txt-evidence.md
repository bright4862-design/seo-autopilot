# H2-5 llms.txt structural evidence — Lane C checkpoint

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Parent checkpoint: `9b17b5a3970f74f57eb823f9613a212e6048cd66`
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Decision and claim boundary

This checkpoint adds a pure, provider-neutral `llms.txt` structural evidence adapter. It performs **no network request** and is not wired into the crawler, `geo_readiness_v1_experimental`, score authority, sealed persistence, customer projection, deployment, or production.

`llms.txt` is optional structural metadata. Its presence does not establish fetching, indexing, inclusion, citations, ranking, appearance, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or another provider. Its absence is not a GEO failure and must not lower the existing GEO score.

The existing FixList GEO architecture research already records the relevant product decision: special AI files are not required for Google AI features, eligibility does not guarantee inclusion, and FixList should not penalize missing `llms.txt`. The current llms.txt proposal defines a Markdown convention whose required core is an H1 name; optional description/sections/resource lists may follow. This lane treats that as a structural convention only, not as a provider ranking signal or universal standard.

## Candidate contract

`scanner-api/app/geo_llms_txt_evidence.py` introduces `geo_llms_txt_evidence_v1`. Its input is one **already-retained** observation with a bounded `url`, HTTP status, optional content type/body, and explicit uncertainty flags. The adapter never fetches the URL itself.

The observation URL must be a public HTTP(S) `llms.txt` identity without credentials or query data. Subpath files are allowed and retain an explicit `scope_path`, so `/docs/llms.txt` cannot silently masquerade as the site-root file.

Structural states are intentionally narrow:

- HTTP 200 with a bounded body whose first nonblank line is one H1 => `presence=present`, `format_status=valid` under the explicit scope `required_h1_and_bounded_structure_only`.
- HTTP 200 with retained content but no required H1, or with multiple H1 headings => `presence=present`, `format_status=invalid`.
- HTTP 404/410 => `presence=absent`, `format_status=not_applicable`; missing `llms.txt` is neutral.
- Access-limited, rate-limited, server-error, truncated, fetch-error, missing-body, oversized, NUL-bearing, or otherwise untrustworthy observations => `not_verified`, never a fabricated negative.
- Other non-200 responses remain `not_verified` unless the transport semantics are explicitly known.

The adapter records a bounded title, whether a blockquote summary was observed, H2 section count, bounded Markdown resource-link count, a content digest, and deterministic opaque evidence reference. These are structural facts only; link quality, factual accuracy, provider ingestion, and business impact remain outside the contract.

## Observation seam and hard boundary

Current Standard 150 page evidence does not retain an `llms.txt` response body/status artifact that this lane can truthfully consume. The user-requested hard boundary also forbids changing crawl/robots/SSRF budgets here. Therefore this checkpoint deliberately stops at a pure adapter seam and **does not add a request**.

An integrator may later feed this contract only from an explicitly approved retained observation surface. If obtaining that observation requires another network request or shared crawler-budget change, that belongs to a separately reviewed integrator/crawler change, not this lane. Until then, live `llms.txt` status remains unverified rather than guessed from page HTML or provider behavior.

## Compatibility and GEO coverage implications

`scanner-api/app/geo_readiness.py` is unchanged. Exact rational aggregation, `pass|fail|not_applicable|not_verified`, the 80% overall evidence gate, the 50% per-dimension gates, and `authority_verified=false` are unchanged.

This candidate has **zero effect on current v1 coverage or numeric score** because it is not part of the v1 check matrix. Missing `llms.txt` is explicitly neutral and does not make the reported Funbooker scan score. The production scan `6ab314008da962a9f8c58929` is still not independently retrievable from repository/issue evidence or an available production datastore/log connector, so no post-change production coverage claim is made.

## Verification before push

Local hermetic candidate verification:

- `scanner-api/tests/test_geo_llms_txt_evidence.py`: **25 passed**.
- Coverage includes minimal valid structure, BOM/summary/section/link metadata, missing required H1, multiple H1s, neutral 404/410 absence, access/rate/server uncertainty, truncation/fetch uncertainty, empty bodies, bounded-body failures, subpath scope, public-URL identity validation, malformed transport values, determinism, and input immutability.
- `py_compile` passed for the new adapter and test module.

Repository-wide exact-head CI remains authoritative after push.

## Next ordered work

1. Require exact-head full scanner CI to remain green with the new adapter present.
2. Define a `geo_readiness_v2` candidate only after compatibility fixtures explicitly settle observation scope, whether/how optional structural metadata is represented, dimension-score transport, and unknown cells. Do not silently add `llms.txt` as a scored requirement.
3. Prepare the V8 authority-sealing handoff describing versioned GEO payload transport and end-to-end verification. Keep `authority_verified=false` until the GEO block is actually inside the sealed authority snapshot and verified through the customer result path.
