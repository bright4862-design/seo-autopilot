# GEO readiness v2 candidate — explicit scope and unknown-cell transport

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Parent checkpoint: `f285b8e8b5e74651182be861425fe658d6bac97f`
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Purpose

`scanner-api/app/geo_readiness_v2.py` defines an isolated `geo_readiness_v2_candidate`. It is a transport/productization candidate, not a production scorer. It delegates all score and gate arithmetic to the existing `geo_readiness_v1_experimental` evaluator so the exact rational aggregation, 80% overall coverage gate, 50% per-dimension gates, equal dimension weights, and `pass|fail|not_applicable|not_verified` semantics remain unchanged.

The candidate adds the three pieces that v1 consumers currently have to infer:

1. an explicit observation scope for the declared sampled page set;
2. stable per-dimension score/coverage summaries with verified, unknown, and not-applicable cell counts; and
3. an explicit bounded list of unknown matrix cells, distinguishing omitted observations from explicit `not_verified` observations.

It performs no fetching, model/provider call, persistence, authority verification, customer projection, crawler/robots/SSRF change, budget change, release action, or deployment.

## Contract

`evaluate_geo_v2(page_ids, observations, *, parent_authoritative=False, entry_verified=False, access_limited=False) -> dict`

The v2 candidate keeps the v1 values for `assessment_status`, `score`, `coverage`, `score_bounds`, `bounds_kind`, `sample_pages`, `dimensions`, `reasons`, and `authority_verified`. Compatibility tests compare these fields directly against `evaluate_geo`.

Additional fields:

- `geo_readiness_version`: `geo_readiness_v2_candidate`.
- `compatibility_base_version`: `geo_readiness_v1_experimental`.
- `observation_scope`: `{kind, page_count, page_set_digest, origin, access_limited}`. The digest is SHA-256 of the sorted declared page IDs; it binds the page set without adding URLs or page content to the scope metadata. `origin=retained_evidence_only` is explicit because this lane adds no request.
- `dimension_scores`: stable `access`, `clarity`, `entity`, `support` entries carrying the v1 dimension `score` and `coverage`, plus counts of verified, unknown and not-applicable cells. For a globally access-limited assessment these values are null rather than inferred.
- `unknown_cells`: sorted by page ID then the fixed v1 check registry. Omitted observations are emitted with reason `observation_missing`; explicit `not_verified` observations retain only their bounded reason. Evidence references are not surfaced for unknown cells.
- `unknown_cell_count`: exact size of that list.
- `claim_boundary`: `structural_readiness_not_ai_citations_inclusion_visibility_or_traffic`.
- `authority_verified`: remains false.

`not_applicable` cells are deliberately absent from `unknown_cells`: they represent deterministically resolved applicability, not missing evidence. They remain counted in the per-dimension summaries and in the inherited v1 check counts.

## Compatibility decisions

The v2 candidate does not add named-crawler or `llms.txt` evidence to the scored matrix. Those artifacts remain optional structural sidecars until a separately reviewed contract decides whether and how they belong in a future scored ruleset. In particular:

- GPTBot training policy is not a readiness deduction.
- `llms.txt` absence is not a readiness failure.
- OAI-SearchBot/Googlebot/GPTBot policy evidence does not establish provider fetching, indexing, inclusion, citations, ranking, appearance, visibility, or traffic.
- `llms.txt` presence or structural validity does not establish any provider outcome.

No threshold, check weight, dimension weight, applicability rule, or score rounding behavior changes in this checkpoint.

## Production/Funbooker implication

The production scan ID `6ab314008da962a9f8c58929` is still not retrievable from repository code/issues or an available production datastore/log connector in this lane, so its reported 139-page payload cannot be independently re-read here. The supplied baseline therefore remains an external production reference, not a newly verified fixture.

This v2 candidate by itself would not change that scan's v1 evidence coverage or make its null score numeric. It only makes scope, dimension summaries, and unknown cells explicit. Entity/support coverage can improve only from newly verified or deterministically not-applicable evidence supplied by the evidence adapter; the score gates are unchanged.

## Verification

Local hermetic compatibility run against the current v1 evaluator:

- `scanner-api/tests/test_geo_readiness_v2.py`: **19 passed**.
- Current `scanner-api/tests/test_geo_readiness.py` compatibility suite + v2 candidate suite: **39 passed**.
- `py_compile` passed for the candidate and its test module.

The parent exact head `f285b8e8b5e74651182be861425fe658d6bac97f` had FixList CI run **2847** green in both `Scanner regression fixtures` and `Lint, typecheck, contract tests, and build`. The new head still requires its own exact-head CI after push.

## Claim boundary

This remains a structural-readiness diagnostic. It does not measure or predict citations, inclusion, appearance, ranking, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or any other provider. Existing `geo_claim_boundary.py` remains the customer-copy guard; this candidate adds the same boundary as machine-readable metadata.

## Next integration gate

The next step is not deployment. The serialized integrator must review the V8 authority handoff, run exact-head scanner/customer compatibility, decide the versioned sealed snapshot shape, and only then wire a candidate GEO block. Historical results must not be recomputed on read.
