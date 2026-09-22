# Agent C — raw/rendered parity coverage hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`

## Why this checkpoint exists

Lane C already produces deterministic representative-page samples and per-page raw-vs-rendered critical-content parity evidence. The remaining coverage risk was aggregate omission: a future serialized integrator needs a pure way to distinguish pages that were selected and successfully paired from pages whose render/parity attempt failed and pages that were never assessed. Missing work must not silently disappear from coverage or be interpreted as a healthy page.

This checkpoint adds `nextgen_browser_parity_coverage_v1` in `scanner-api/app/nextgen_browser_performance_coverage.py`. It is pure data accounting only. It performs no rendering, provider/network calls, persistence, scoring, customer-Fix creation, or execution-budget decisions.

## Contract

`summarize_critical_parity_coverage(sample, parity_results)` binds a `nextgen_performance_sample_v1` sample to `nextgen_critical_content_parity_v1` results and reports:

- selected pages/URLs;
- completed paired observations (`matched` or `material_delta`);
- failed/unverifiable attempts (`not_verified`);
- selected but unassessed URLs (no parity result supplied);
- material-delta page count/URLs;
- a completion ratio only when there is a non-empty selected population.

An empty selected population is `not_applicable`, not a false `complete` result.

The aggregate fails closed to `not_verified` when sample/result binding is ambiguous or malformed, including:

- non-HTTP(S) or missing selected identities;
- duplicate selected identities;
- foreign parity-result URLs;
- duplicate parity results for one selected URL;
- unsupported/malformed result versions/states;
- a `matched`/`material_delta` result whose rendered identity does not equal the selected/raw identity;
- contradictory `material_delta` flags.

On an invalid aggregate, completed/failed/unassessed counts are left `None` rather than manufacturing a trustworthy coverage denominator.

## Deterministic verification

A hermetic pure-function run of the new module/tests completed successfully:

```text
PYTHONPATH=. python -m pytest -q tests/test_nextgen_browser_performance_coverage.py
.........                                                                [100%]
9 passed in 0.06s
```

`python -m py_compile app/nextgen_browser_performance_coverage.py tests/test_nextgen_browser_performance_coverage.py` also passed.

The nine regressions cover complete coverage, failed-vs-unassessed separation, empty samples, foreign-result binding, duplicate-result ambiguity, rendered-identity mismatch, contradictory material-delta flags, non-HTTP sample identities, and input immutability.

Together with the prior 55 Lane-C focused tests, the branch now contains **64 focused tests**. The complete exact-head 64-test repository run is still not certified in this environment because the available container cannot resolve `github.com` and this integration-target PR has no normal PR-triggered workflow run. Do not infer 64/64 repository green from the hermetic 9/9 checkpoint.

Required exact-head command after materializing the repository:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  app/nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py
```

## Serialized integration guidance

After the serialized integrator selects a representative candidate set and executes only a global-budget-approved subset through the existing safe browser path, it may call the parity helper for each attempted pair and then call this aggregate coverage helper over the original selected sample plus available parity results.

This makes unexecuted pages remain `unassessed`, unsuccessful or unverifiable pairs remain `failed`, and only same-identity paired evidence count as completed. The helper is not permission to execute every selected candidate; Lane C's selection ceiling remains an upper bound, while actual browser/Lighthouse execution budgets remain integrator-owned.

## Ownership / rollback

This checkpoint changes only Lane-C-owned pure helper/test/docs files:

- `scanner-api/app/nextgen_browser_performance_coverage.py`
- `scanner-api/tests/test_nextgen_browser_performance_coverage.py`
- `docs/nextgen/lane-c-parity-coverage-hardening.md`

No `scanner.py`/`run_scan`, global scan budget, worker deployment configuration, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, schema, IAM, credentials, or production surface is modified.

Rollback is removal of the three files above. Existing Standard 150 behavior is unchanged because the helper is not wired into shared orchestration.
