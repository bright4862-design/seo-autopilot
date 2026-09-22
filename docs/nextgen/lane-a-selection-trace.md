# Lane A — deterministic adaptive selection replay trace

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Why this checkpoint exists

Lane A already selects deeper pages deterministically, but the selector returned only the final page sequence. For corpus experiments and future serialized integration, that made it harder to prove *why* a particular page entered the 500-page tranche, detect stale transported evidence, or reproduce a selection decision after metadata drift.

`scanner-api/app/adaptive_selection_trace.py` adds a pure, shadow-only replay trace around the existing selector. It does **not** create a second selector and does not change Standard 150.

## Contract

`adaptive_selection_trace_v1` records:

- exact ordered discovered-input and selected-population SHA-256 fingerprints;
- discovered and exact-unique population counts;
- unchanged Standard-150 baseline count;
- each post-150 selected page's position and original discovery index;
- candidate count before each deeper choice;
- the exact `adaptive_candidate_score_v1` score/reasons used at that step;
- score gap to the next candidate and count of candidates tied on score;
- route signature, path prefix and family evidence for the chosen page.

The trace rejects non-string, empty, or surrounding-whitespace discovered URL identities instead of silently normalizing them. Exact duplicate identities remain represented in the discovered-input fingerprint while the deeper selector retains its existing exact-dedup behavior.

Every trace hard-codes:

- `population_scope_complete=false`;
- `production_budget_authorized=false`;
- `site_fully_understood=false`.

## Replay integrity

`validate_adaptive_selection_trace(...)` reruns the existing selector from the caller-supplied discovered population, family/path classifiers and metadata and compares every transported field with recomputed evidence.

The integrity boundary therefore detects:

- discovery-order drift;
- target drift;
- metadata/score drift;
- selected-population drift;
- fingerprint tampering;
- per-step score/reason/tie-diagnostic tampering;
- forged completeness or production-budget authority.

JSON-like list transport is accepted where the builder used tuples, so sequence serialization alone does not create a false mismatch.

## Standard 150 preservation

The builder computes the baseline by invoking the existing `select_adaptive_urls(...)` at the current Standard-150 bound, then requires the deeper result to contain that exact baseline prefix. It never reimplements or replaces the production sampler.

A divergence raises immediately instead of creating a misleading trace.

## Verification in this run

A hermetic pure-function package exercised the exact new helper/test bytes:

- `PYTHONPATH=. pytest -q tests/test_adaptive_selection_trace.py` → **17 passed**;
- `python -m py_compile app/adaptive_selection_trace.py tests/test_adaptive_selection_trace.py` → **passed**.

Coverage includes exact Standard-150 prefix replay, deterministic deeper replay, score/tie diagnostics, duplicate discovered identities, hard 1,000-page cap, valid JSON-like transport, fingerprint/step/metadata/order tampering, malformed identities and input immutability.

This raises Lane A to **171 focused tests by file inventory** (prior 154 + 17 selection-trace regressions).

## Exact-head repository gate still required

The execution shell still cannot resolve `github.com`, so it cannot clone/materialize the complete branch for a branch-native exact-head pytest run. The connector can read/write GitHub, but that is not a substitute for repository-native test execution.

The new exact-head focused commands are:

```text
cd scanner-api
PYTHONPATH=. pytest -q tests/test_adaptive_selection_trace.py
PYTHONPATH=. python -m py_compile \
  app/adaptive_selection_trace.py \
  tests/test_adaptive_selection_trace.py
```

The full Lane-A exact-head gate should include this test module in addition to the prior 154 focused tests.

## Serialized integrator handoff

No shared integration surface changes are required in this lane. If the integrator later runs an off-by-default adaptive shadow experiment, it may optionally emit this trace beside the existing Lane-A benchmark artifacts using the *same already-discovered URL population and metadata snapshot*. The trace must remain operator/shadow evidence; it does not authorize deeper crawl budgets, persist authority, rank repairs, or project customer state.

No `run_scan`, global budget, repair priority, authority/persistence, customer projection, admission, release, deployment, worker, schema, credential, or production surface is modified by this checkpoint.
