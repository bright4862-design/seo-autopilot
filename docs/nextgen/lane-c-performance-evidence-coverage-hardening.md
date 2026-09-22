# Agent C — field/lab performance coverage hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint before this document: `41aadf9105cc14cf8132246403605fc4fac92176`

## Why this checkpoint exists

Lane C already had provider-neutral CrUX/PSI evidence, strict PSI source provenance, deterministic representative sampling, sample-to-population binding, Lighthouse normalization, and raw/rendered parity coverage. One remaining integration risk was omission at the performance-observation layer: a future integrator could collect field evidence for some selected pages, lab evidence for a different subset, and accidentally present the aggregate as though both evidence types covered the same population.

This checkpoint adds pure coverage accounting that keeps field CrUX evidence and lab Lighthouse evidence separate through aggregation. It performs no provider calls, browser work, persistence, scoring, customer-Fix creation, or execution-budget decisions.

## New pure contract

`scanner-api/app/nextgen_browser_performance_evidence_coverage.py` adds `nextgen_performance_evidence_coverage_v1` and `summarize_performance_evidence_coverage(sample, observations)`.

Each observation is bound to the representative sample by an explicit `requested_url` and may contain a field component, a lab component, or both. The helper:

- validates the representative-sample contract before using its denominator;
- requires selected request identities to be absolute HTTP(S) and unique after normalization;
- rejects foreign or duplicate observation identities;
- validates supplied field and lab components with the existing Lane-C integrity validators before counting them;
- treats an explicit `disconnected`, `unavailable`, `rate_limited`, or `provider_error` component as an attempted observation, never as a connected measurement;
- treats a missing component as unassessed rather than unavailable;
- reports field and lab attempted pages, connected pages, unassessed pages, attempted/connected ratios, per-provider-state counts, and URL lists independently;
- fails the entire coverage aggregate closed when observation binding or component integrity is ambiguous;
- leaves an empty selected population `not_applicable` rather than manufacturing a successful coverage claim.

This means a URL may have valid field evidence and no lab evidence, or vice versa, without collapsing the two evidence types into a synthetic combined state.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_evidence_coverage.py` adds 9 pure regressions covering:

1. independent field and lab assessment accounting;
2. rate-limited/provider-error attempts not becoming measured evidence;
3. selected pages with no observations remaining unassessed;
4. an empty selected population remaining not applicable;
5. foreign requested identities failing closed;
6. duplicate observation identities failing closed;
7. invalid component contracts failing closed;
8. observations with neither field nor lab evidence failing closed;
9. input immutability.

A hermetic helper/test harness completed successfully:

```text
.........                                                                [100%]
9 passed in 0.04s
```

`py_compile` also passed for the new helper/test slice. The harness validates the new pure coverage logic and expected existing contract boundary only; it is not a claim that the full repository branch has executed.

With the previously recorded 73 focused Lane-C tests, the branch now contains **82 focused tests across seven test files**.

## Exact repository gate still required

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  app/nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py
```

The available execution container still cannot resolve `github.com`, and this integration-target draft does not currently have a normal PR-triggered repository CI run. Exact-head 82/82 remains uncertified until an approved repository runner executes the commands above.

## Serialized integration guidance

After the serialized integrator selects and validates the representative candidate population, it may attach already-observed field/lab evidence to the sampled request identity and pass those observations to `summarize_performance_evidence_coverage(...)`.

The resulting field/lab coverage object is evidence accounting only. A `complete` field or lab coverage state means every selected page has an attempted component; it does **not** mean every provider attempt connected successfully, and it does not authorize any extra PSI/Lighthouse/browser calls. The integrator still owns global budgets, execution policy, persistence, repair priority and customer scoring.

## Ownership / rollback

This checkpoint adds only Lane-C pure helper/test/docs files. It does not modify `scanner.py` / `run_scan`, global scan budgets, worker deployment configuration, repair priority/customer scoring, authority/persistence/projection, admission, release/deployment, schema/IAM/credentials, provider accounts, or production.

Rollback is deletion of the new helper/test/doc. Standard 150 behavior remains unchanged because the new contract is not wired into shared orchestration.
