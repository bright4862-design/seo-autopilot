# Agent C — provider-shape hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`

## Purpose

This checkpoint hardens Lane C against two provider-shape gaps without adding any provider network calls, credentials, browser execution, persistence, scoring, or customer Fix creation.

1. The documented CrUX `queryRecord` response is an envelope under `record`, with URL/origin identity in `record.key`, measurements in `record.metrics`, and an optional `collectionPeriod`. The earlier generic CrUX wrapper accepted simplified metric dictionaries but did not model that full provider envelope or fail closed on contradictory scope/identity claims.
2. PageSpeed Insights can expose URL-level `loadingExperience` and origin-level `originLoadingExperience`. A URL-level shell with no supported metrics must not suppress usable origin-level CrUX field data.

## New pure adapter

`scanner-api/app/nextgen_browser_performance_provider.py` adds `nextgen_performance_provider_adapter_v1` with:

- `normalize_crux_query_record_evidence(...)` for already-observed CrUX `queryRecord` payloads;
- URL-vs-origin scope inferred from the provider record key;
- normalized provider identity with caller-supplied scope/source allowed only as corroboration;
- fail-closed `crux_record_key_invalid`, `crux_scope_invalid`, `crux_scope_mismatch`, `crux_source_identity_invalid`, `crux_record_identity_mismatch`, and `crux_record_metrics_unavailable` states;
- preservation of valid CrUX `collectionPeriod` as `coverage_period` without turning missing/invalid coverage into fabricated dates;
- no metrics retained for non-connected provider states;
- `normalize_pagespeed_insights_evidence_strict(...)`, which keeps field and lab evidence in separate envelopes and falls back from unusable URL-level CrUX data to usable origin-level CrUX data;
- URL-level field data still wins when it contains supported measurements;
- no live provider call, API key, OAuth scope, or credential path.

The existing Lane-C normalizers remain untouched for compatibility. The serialized integrator may adopt this stricter provider-shape adapter after review instead of altering shared orchestration in the lane branch.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_provider.py` adds 8 pure regressions covering:

1. documented CrUX `record.key` / `record.metrics` URL-shape normalization;
2. origin-scope CrUX evidence;
3. ambiguous/missing authoritative record identity failing closed;
4. contradictory caller scope and source identity failing closed;
5. non-connected CrUX state retaining no measurements;
6. input immutability;
7. PSI origin fallback when URL-level experience has no supported metrics;
8. URL-level PSI field evidence taking precedence when usable.

A hermetic pure-function harness for this new module/test slice passed:

```text
8 passed in 0.07s
python -m py_compile app/nextgen_browser_performance_provider.py tests/test_nextgen_browser_performance_provider.py
```

This is execution evidence for the new provider-shape slice only. It is not a claim that the full repository branch has passed. Together with the previously present 37 Lane-C focused tests, 45 focused tests are now present.

## Exact repository gate still required

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py
```

The current automation container still cannot clone `github.com` because DNS resolution fails, and repository CI is configured for `main` pushes / `main`-targeted pull requests rather than this integration-target draft. Therefore the exact-head 45-test repository run remains uncertified.

## Ownership and safety

This checkpoint adds only Lane-C pure helper/test/docs files. It does not modify `scanner.py` / `run_scan`, global budgets, worker deployment config, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, production, schema, IAM, credentials, or provider accounts. Nothing here authorizes extra Lighthouse/browser executions.
