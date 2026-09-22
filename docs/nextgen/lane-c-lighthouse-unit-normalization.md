# Lane C — Lighthouse metric-unit normalization hardening

Issue: #324  
Draft PR: #331  
Branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint: `f4af80ca05e798f5107e1dda19710faace5e8493`

## Why this slice exists

The existing bounded Lighthouse evidence contract intentionally allowlists metric IDs and
preserves the provider's `numericUnit`. Its integrity validator only requires that a retained
unit is a string. That means a structurally valid lab envelope could still carry a semantically
wrong unit such as LCP=`2100 byte` and remain superficially valid.

This slice adds a separate, pure, lab-only unit-normalization contract. It does not alter the
existing Lighthouse envelope or provenance contract and it does not make provider calls.

## Contract

`scanner-api/app/nextgen_browser_performance_lighthouse_units.py` adds:

- `nextgen_lighthouse_metric_units_v1` — a derived lab-metric unit artifact;
- `nextgen_lighthouse_metric_units_integrity_v1` — fail-closed integrity validation;
- canonical timing units (`ms`) for LCP, INP, FCP, server response time, speed index and total
  blocking time;
- canonical score units (`score`) for CLS;
- deterministic exclusion of unsupported, malformed, negative, missing-unit or contradictory-unit
  metric rows instead of guessing units;
- explicit `not_applicable` when connected Lighthouse evidence contains no metric rows (for example,
  score/opportunity-only evidence);
- explicit `not_verified` for non-connected input, wrong source version, wrong evidence kind or when
  all metric units are unverifiable;
- source immutability: normalization operates on copies and never rewrites the input Lighthouse
  evidence dictionary.

The artifact intentionally contains only normalized lab metrics and their exclusions. It does not
copy or synthesize field-performance evidence, customer scoring, repair priority, persistence or
execution entitlement.

## Integration hook

The serialized integrator may use this only after direct-Lighthouse or PSI lab evidence has already
passed its existing source/provenance contract:

1. Produce and validate the existing bound Lighthouse lab envelope.
2. Pass that trusted lab envelope to `normalize_lighthouse_metric_units(...)`.
3. Require `validate_lighthouse_metric_unit_contract(...)["valid"]` before using canonicalized lab
   metric units.
4. Keep this derived lab artifact separate from CrUX field evidence and from the field-only CWV
   assessment. Never use Lighthouse lab values as field-CWV truth.

This helper grants no browser/Lighthouse execution budget and does not alter the existing bounded
sample policy.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_lighthouse_units.py` adds 10 tests covering:

- millisecond/unitless provider units normalized to `ms`/`score`;
- already-canonical aliases remaining deterministic;
- contradictory timing units excluded without discarding unrelated valid lab metrics;
- missing units remaining unverified rather than guessed;
- malformed, negative and unsupported metrics excluded fail-closed;
- connected score-only Lighthouse evidence becoming `not_applicable`, not a false failure;
- non-connected states never becoming normalized measurements;
- field evidence being rejected rather than laundered into lab-unit evidence;
- source-evidence immutability;
- integrity rejection of forged non-canonical units and source-version tampering.

Hermetic verification of the exact new module/test contents:

```text
10 passed in 0.07s
python -m py_compile: passed
```

Lane C now contains 154 focused tests across fourteen test files. Exact-repository `154/154` is not
claimed until the recorded Lane-C suite runs against the branch head in an approved repository
runner.

## Ownership / safety

This slice modifies only a Lane-C pure helper, its deterministic tests and this documentation. It
does not touch `scanner.py` / `run_scan`, global budgets, worker deployment configuration, repair
priority/customer scoring, authority/persistence/projection, admission, release/deployment,
schema/IAM/credentials, provider accounts or production.

No live CrUX/PSI/Lighthouse call and no credential are used by the deterministic tests.

## Risk and rollback

The risk being addressed is unit laundering: retaining a numeric Lighthouse measurement under a
semantically incompatible unit. The helper fails that metric closed while preserving other
independently valid lab metrics.

Rollback is deletion of this helper, test and note. Because the slice is not wired into shared
orchestration or persistence, rollback requires no data migration or production change.
