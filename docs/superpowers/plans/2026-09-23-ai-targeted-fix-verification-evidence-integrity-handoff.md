# AI Layer Lane E — H1-4 Targeted Fix Verification Evidence Integrity Handoff

Status: additive Lane-E pure verification boundary only. Do not merge or deploy from this lane. This checkpoint does not wire a customer endpoint, mutate historical scans, persist verification state, change authority/customer projection, modify Standard 150/V8 budgets, or call a private worker.

## Refreshed baseline

At this checkpoint:

- `main` is `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
- Lane E works only on `agent/ai-fix-verification-20260923` and draft PR #340.
- The AI-layer architecture baseline remains additive to Standard 150/V8 and requires fail-closed deterministic verification.
- `repair_identity.py` remains authoritative for stable repair identity and `repair_verification_v3_contract_comparable`; Lane E does not replace `compare_repair_runs()`.
- `SharedCoverageProbeScheduler` remains the one finite bounded follow-up request pool. Lane E does not create or reserve a second pool.
- The latest Rescan Agent dependency is `agent/ai-rescan-comparison-20260923 @ a32cf830823c6327fb1396646ba07918bad8de38`. Its latest handoff still identifies provisional production repair identity as the shared blocker to promoting canonical fixed/still/came-back truth.

## Slice implemented

This slice adds `scanner-api/app/targeted_fix_verification_evidence_integrity.py` with version:

`targeted_fix_verification_evidence_integrity_v1_complete_usable_html`

The new boundary is deliberately upstream of the existing Lane-E evaluator. It decides only whether a targeted page recheck is safe/comparable enough to be admitted as proof-bearing page evidence. It does **not** decide whether a repair is fixed.

An `observed` page must now carry exact, non-ambiguous evidence that:

- FixList was allowed to fetch it under the already-owned robots policy (`robots_txt_fetch_allowed is True`);
- no challenge/block/rate-limit or unknown access-gate marker is present;
- no fetch error is present;
- `raw_html_truncated is False`;
- the status is an exact integer 2xx;
- the response has an explicit HTML/XHTML content type;
- the page evidence class is exactly `usable_html`.

Missing/ambiguous robots state, challenge/block/rate-limit, fetch errors, truncation/body-limit evidence, malformed status transport, non-HTML responses, and non-usable page evidence all fail closed to `COULD_NOT_VERIFY` before the canonical comparator can produce PASS.

Explicit `not_verified` outcomes remain valid transport and continue into the existing evaluator, which maps robots/challenge/timeout/budget failures to `COULD_NOT_VERIFY`. A `not_verified` outcome may not smuggle page evidence. An `observed` outcome may not carry a conflicting failure reason.

The strict entrypoint is:

`strict_evaluate_targeted_fix_verification(...)`

It first runs `validate_recheck_evidence_integrity(...)` and then delegates unchanged repair truth to `evaluate_targeted_fix_verification(...)`, which in turn delegates each affected URL to `compare_repair_runs(...)`. PASS/PARTIAL/FAIL semantics therefore remain the existing canonical comparison semantics.

## Truth invariants preserved

- `PASS`: only when every sealed URL is safely re-observed and the canonical comparator returns `verified_fixed` for each URL.
- `PARTIAL`: only from a complete, comparable population containing both canonical `verified_fixed` and `still_detected`/`came_back` results.
- `FAIL`: only from canonical positive defect evidence (`still_detected`/`came_back`) across the complete sealed population.
- `COULD_NOT_VERIFY`: any missing URL, disappeared URL, robots ambiguity/denial, challenge, block, rate-limit, fetch failure, timeout, deadline/budget exhaustion, truncation/body-limit ambiguity, non-HTML/non-usable page evidence, rule/comparison/evidence-version mismatch, identity ambiguity, or malformed/incomplete transport.

A disappeared URL remains non-proof. Missing one planned outcome produces `one_or_more_planned_urls_were_not_observed` and cannot become PASS.

Historical repair objects are read-only in Lane E. Regression reopening remains a returned recommendation/evidence signal (`reopen_regression`, `regression_evidence_keys`) from existing comparator semantics; this lane does not mutate persisted historical state.

## Safety and abuse coverage

The new focused tests add coverage for:

- complete safe evidence delegating to canonical PASS;
- comparator-backed PARTIAL and FAIL;
- verified-fixed reappearance producing regression-reopen evidence without mutating the historical repair;
- disappeared URL => `COULD_NOT_VERIFY`;
- robots denied, missing, and ambiguous robots evidence;
- challenge, block, rate-limit, and unknown access-gate markers;
- fetch errors;
- body truncation and ambiguous truncation state;
- non-2xx and type-coerced status transport;
- non-HTML response;
- non-usable page evidence class;
- timeout and shared-budget failure remaining `COULD_NOT_VERIFY`;
- rule-version drift remaining `COULD_NOT_VERIFY`;
- `not_verified` page-evidence smuggling rejection;
- conflicting observed failure-reason rejection;
- outside-plan evidence rejection;
- exact complete outcome population validation.

The two new Python files were syntax-checked before publication. Exact code/test head `a5f430d50e7727e42fafe741329e64d2c7c4bed9` passed repository-native FixList CI run `35809922957`: both `Lint, typecheck, contract tests, and build` and `Scanner regression fixtures` completed successfully, including the full scanner-api suite and production scanner image build.

## Serialized integration handoff

The shared integrator should compose Lane E in this order, without weakening any boundary:

1. Authenticate/read the historical scan and select one authoritative sealed repair through existing authority readers.
2. Require stable repair identity and build the exact complete `targeted_fix_verification_plan_v1_sealed_repair_scope`.
3. Read the existing `SharedCoverageProbeScheduler` summary and call `strict_targeted_verification_budget_proposal(...)`; do not create a second request pool.
4. Execute only the planned URLs through the existing protected fetch path and shared scheduler. Existing robots, SSRF/DNS, redirect, body-size, deadline, and request-budget protections remain authoritative.
5. Convert scheduler/protected-fetch results into Lane-E observations. For an `observed` page, retain the exact robots/fetch/access/truncation/status/content-type/evidence-class fields required by the evidence-integrity gate. On uncertainty, emit `not_verified`; never fabricate a complete page.
6. Re-run the originating deterministic rule/evidence semantics under the exact rule/comparison/evidence versions and build the complete `targeted_fix_verification_rule_receipt_v1_complete_population`.
7. Call `strict_evaluate_targeted_fix_verification(...)`. Do not infer PASS from absence of a repair row, absence of a URL, or a customer projection.
8. Any durable persistence, authority transition, customer-facing projection, endpoint admission, or regression-state write belongs to the serialized integrator/owning lane, not Lane E.

## Dependency / blocker

Lane E core comparison truth still depends on the Rescan/authority path supplying an authoritative sealed repair with stable technical identity. The latest Rescan handoff reports that current production FixItems remain provisional unless a sealed source of `repair_surface` and `remediation_family` is available. If stable identity cannot be proven, targeted verification must remain `COULD_NOT_VERIFY`.

Lane E also depends on the serialized integrator to execute the existing shared scheduler/protected fetch path and to provide exact deterministic rule-output completeness. This lane must not call private workers or recreate those protections.

## Next safe Lane-E step

After exact-final-head CI remains green, the next lane-local slice may define a narrow service-adapter contract around the already-green pure core, but it must accept pre-authenticated sealed repair input and protected scheduler observations rather than owning authority, network execution, persistence, or customer routing. If that adapter would require changing V8/customer/shared seams, stop and hand it to the serialized integrator instead.
