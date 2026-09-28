# H2-5 GEO named-crawler robots evidence — Lane C checkpoint

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Parent checkpoint: `afa4ddf0a953c078803a74c7c9ee48b4ea91a7ac`
Refreshed main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Scope and boundaries

This checkpoint stays inside the GEO evidence/applicability lane. It does not alter `geo_readiness.py`, score thresholds, exact rational aggregation, crawler/robots/SSRF behavior or budgets, admission, worker/deployment configuration, authority/persistence/customer projection, release, or production. It makes no model or provider visibility calls.

FixList GEO readiness remains a structural diagnostic. Robots evidence is policy evidence only. It does **not** prove or predict fetching, indexing, inclusion, citations, ranking, appearance, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, OpenAI products, or another provider.

## Exact-head compatibility correction

FixList CI run 2827 on the parent lane head found one real compatibility regression: `scanner-api/tests/test_geo_evidence.py::test_positive_structural_fixture_can_meet_gates_with_historical_date` expected full coverage, but the new structured evidence rules returned coverage `0.916667`. The rest of that scanner run was `2112 passed, 18 skipped, 1 failed`; the lint/typecheck/frontend-contract/build job passed.

Root cause: historical `geo_evidence_v1` accepts an untyped but page-bound JSON-LD object such as `{"url":"https://example.com/","name":"Acme"}` as positive `schema_agreement` when its name exactly matches the retained H1. The first H2-5 patch accidentally required a recognized schema `@type` for that agreement path.

This checkpoint restores only that compatibility behavior: any bounded top-level or one-level `@graph` object may establish `schema_agreement` when an explicit `name`/`headline` exactly matches the H1 and its `url`, `@id`, or `mainEntityOfPage` binds to the page. A recognized `@type` is still required for structured `subject_identity` and deterministic non-article applicability. Therefore an untyped object cannot invent subject identity or turn article-only checks into N/A.

No score threshold, coverage threshold, state mapping, authority gate, or dimension weight changes.

## Named-crawler robots evidence

`scanner-api/app/geo_robots_evidence.py` introduces the pure candidate contract `geo_named_robots_evidence_v1` for three fixed user-agent identities:

- `OAI-SearchBot` — purpose `search`.
- `GPTBot` — purpose `training`.
- `Googlebot` — purpose `search`.

The adapter performs no network request and never impersonates any crawler. It only normalizes exact per-user-agent decisions that already exist in the supplied page evidence. A crawler is `observed` only when `robots_txt_rules_known` is true and that exact crawler's retained boolean is present. Otherwise it is `not_verified`; one crawler's policy is never copied to another.

Current scanner page evidence already retains exact `OAI-SearchBot` and `Googlebot` decisions. It does not currently retain a GPTBot decision, so GPTBot remains `not_verified` in current production-shaped page objects. This lane deliberately does not modify `robots_policy.py` or add a fetch. A future integrator may populate `robots_txt_gptbot_allowed` only from the already-fetched robots policy if that shared change is separately approved and tested.

A GPTBot `disallow` is neutral structural policy evidence. It is not a GEO defect and does not affect the v1 score. The candidate is not wired into `geo_readiness_v1_experimental`, sealed authority, or customer transport in this lane.

## Fail-closed rules

The named-crawler adapter rejects malformed boolean values, impossible status/rules-known combinations, and any claimed per-bot decision when robots rules are not retained as known. It emits opaque page/evidence references and does not expose owner-override state. `available`/`missing` and `unavailable`/`access_limited` contradictions fail rather than being guessed through.

## Verification before push

Local hermetic candidate verification:

- `scanner-api/tests/test_geo_named_robots_evidence.py`: **15 passed**.
  - 13 named-crawler/fail-closed/determinism cases.
  - 2 schema-agreement compatibility cases, including the exact historical shape that caused CI run 2827 to lose one coverage cell.
- `py_compile` passed for `geo_evidence.py`, `geo_robots_evidence.py`, and the new test module.

The repository-wide exact-head CI remains authoritative after this checkpoint is pushed. Do not treat the local harness as a replacement for full scanner regression execution.

## GEO coverage implications

The compatibility correction restores an evidence cell that v1 historically verified; it does not create new score eligibility. The named-crawler artifact is additive evidence for a future versioned candidate and has **no effect** on current GEO dimension coverage or numeric score. In particular, it does not lower the 80% overall gate or 50% per-dimension gates and does not make the reported Funbooker run score merely by adding robots metadata.

The production scan `6ab314008da962a9f8c58929` is still not available in repository/issue evidence or through a production datastore connector in this lane, so the supplied 139-page baseline cannot be independently re-read here. No claim is made that these changes alter that production scan until a future post-integration rerun supplies sealed evidence.

## Claim-boundary status

The existing `geo_claim_boundary.py` guard remains unchanged. No customer-facing GEO copy is changed in this checkpoint. The new robots contract itself explicitly states that policy observations are not provider access or visibility evidence.

## Next ordered work

1. Require exact-head full scanner CI to pass the restored historical compatibility fixture and all new named-crawler tests.
2. Add `llms.txt` presence/validity only as a bounded structural signal if existing retained evidence can supply it without any new request or crawler-budget change; otherwise document a precise integrator observation seam instead of fetching here.
3. Run explicit compatibility fixtures before defining any `geo_readiness_v2` candidate observation scope, dimension scores, or unknown-cell transport.
4. Prepare the V8 authority-sealing handoff. Keep `authority_verified=false` until the GEO block is actually included in the sealed snapshot and verified end-to-end.
