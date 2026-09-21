# Agent C — browser/performance transport-integrity hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint: `7f7d464c724137b682c944a461d05898cfa5b034`

## Why this checkpoint exists

Lane C already emits versioned, pure CrUX/PSI/Lighthouse, representative-sample, and raw/rendered parity evidence. The remaining integration risk is transport/caller mutation: a future serialized integrator must not treat a malformed or forged dictionary as trusted evidence merely because it resembles a Lane-C output.

This checkpoint adds a pure fail-closed validation boundary in `scanner-api/app/nextgen_browser_performance_contract.py`. It performs no network I/O, browser work, persistence, scoring, authority writes, or customer Fix creation.

## Added integrity contracts

`nextgen_browser_performance_integrity_v1` validates:

- field-performance evidence version/kind/provider/state;
- connected field metrics against the existing Lane-C metric allowlist, units, finite non-negative values, and supported ratings;
- the invariant that non-connected provider states retain no measured field metrics;
- Lighthouse version/kind/provider/state, bounded performance score, allowlisted metrics/opportunities, finite scores/savings, and duplicate/unsupported opportunity rejection;
- the invariant that failed/unavailable/rate-limited lab states retain no measured score, metrics, or opportunities;
- PageSpeed Insights as a composition of independently valid field and lab contracts, preserving field/lab separation;
- representative-sample request/cap/count relationships, duplicate-observation accounting, selected URL uniqueness, template coverage accounting, finite non-negative high-value weights, and supported selection reasons;
- raw/rendered parity state/material-delta semantics, allowed critical fields, scalar observation provenance, set-delta shapes, exact verified/changed-field summaries, and same-identity requirements for matched/material-delta evidence.

The validator returns a deterministic `{version, contract, valid, reasons}` object and never promotes invalid evidence into a site defect.

## Deterministic regressions added

`scanner-api/tests/test_nextgen_browser_performance_contract.py` adds 14 pure regressions covering:

1. accepted normalized connected/unavailable field evidence;
2. forged measurements retained in a non-connected field state;
3. non-finite and unsupported field metrics;
4. accepted allowlisted Lighthouse normalization;
5. forged Lighthouse measurements retained after provider failure;
6. valid PSI field/lab composition;
7. cross-kind field/lab forgery;
8. valid representative-sampler output;
9. forged duplicate selected URLs and population counts;
10. false complete-template-coverage claims;
11. valid matched and material-delta parity outputs;
12. a forged matched result that still contains changed scope;
13. material-delta evidence with mismatched raw/rendered identity;
14. a scalar equality claim without bilateral extractor observation.

Together with the existing 23 Lane-C tests, 37 focused tests are now present across the two focused files.

## Verification status

The exact commands required for this code/test checkpoint are:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py
```

Exact-head execution is **not certified in this automation environment**. The available local Python/container execution backends are returning infrastructure `ClientError`, and this integration-target draft PR has no GitHub Actions run for the checkpoint. The previously executed Lane-C baseline remains 17/17 plus `py_compile`; the later 23-test parity hardening and the 14 new integrity tests must not be claimed green until an approved runner executes the commands above.

No live provider calls or credentials are used by these tests.

## Serialized integration guidance

A future integrator should validate Lane-C evidence after pure normalization/selection/parity construction and before authenticated persistence or downstream repair logic consumes it. Invalid transport evidence should remain unavailable/not-verified and should never create a customer Fix or score effect.

This does not authorize additional browser/Lighthouse executions. The existing 12-candidate pure selection ceiling remains only an upper bound; actual execution stays under integrator-owned global budgets and the existing safe renderer/request controls.

## Ownership / rollback

New files in this checkpoint are Lane-C pure helper/test/docs only:

- `scanner-api/app/nextgen_browser_performance_contract.py`
- `scanner-api/tests/test_nextgen_browser_performance_contract.py`
- `docs/nextgen/lane-c-browser-performance-integrity.md`

No `scanner.py`/`run_scan`, global scan budget, worker deployment configuration, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, schema, credential, or production surface is modified.

Rollback is removal of the three files above. Existing Lane-C normalizers and prior Standard 150 behavior remain untouched.
