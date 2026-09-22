# Lane C — PSI field form-factor hardening

Issue: #324  
Draft PR: #331  
Lane: `agent/nextgen-browser-performance-20260921`

## Why this slice exists

PageSpeed Insights returns two fundamentally different performance evidence classes:
CrUX field metrics and Lighthouse lab measurements. The provider's CrUX metric objects can
carry their own `formFactor`, while Lighthouse has a separate analysis/device strategy.
Those two device contexts must not be treated as interchangeable.

Before this slice, Lane C bound PSI field and lab source identities separately but did not
produce a dedicated contract for the CrUX metric-level form factor inside PSI. A future
integrator could therefore be tempted to infer field device context from Lighthouse's
`mobile`/`desktop` strategy when the field metadata was missing.

## Contract

`scanner-api/app/nextgen_browser_performance_psi_dimensions.py` adds:

- `nextgen_psi_field_dimension_v1`;
- `nextgen_psi_field_dimension_integrity_v1`;
- `normalize_psi_field_dimension_context(...)`;
- `validate_psi_field_dimension_contract(...)`.

The helper accepts an already-observed PSI payload plus the already source-bound
`nextgen_pagespeed_bound_provider_v1` evidence envelope. It performs no provider call and
does not grant browser/provider execution budget.

For connected PSI field evidence it:

1. rechecks the bound PSI adapter/provenance identity;
2. selects the same URL/origin loading-experience source used by the bound field envelope,
   including truthful origin fallback;
3. rechecks raw provider source/initial identity against the bound evidence;
4. looks only at the raw PSI CrUX metric objects corresponding to the field metrics that
   were actually retained;
5. requires those retained metrics to report one consistent supported field `formFactor`;
6. emits `phone`, `tablet`, or `desktop` only from that field metadata.

Missing field form-factor metadata stays `unavailable`; unlike direct CrUX `queryRecord`,
this contract does not interpret omission as an all-form-factor aggregate. Partial,
mixed, unknown, mismatched, or structurally untrusted metadata also fails closed.
Lighthouse strategy/configuration is never used to fill the field form factor.

## Deterministic verification

Focused tests cover:

- PHONE, DESKTOP, and TABLET normalization;
- case normalization;
- missing form-factor metadata with a mobile Lighthouse strategy present;
- incomplete metric dimension coverage;
- mixed field form factors;
- unknown form factors;
- non-connected provider states;
- forged bound adapter identity;
- origin fallback source selection;
- raw/bound field source mismatch;
- integrity tampering;
- input immutability.

Focused gate:

```bash
cd scanner-api
PYTHONPATH=. pytest -q tests/test_nextgen_browser_performance_psi_dimensions.py
python -m py_compile \
  app/nextgen_browser_performance_psi_dimensions.py \
  tests/test_nextgen_browser_performance_psi_dimensions.py
```

Hermetic lane verification: **13 passed**; `py_compile` passed.

## Integrator hook

After `normalize_pagespeed_insights_evidence_bound(...)` and
`validate_bound_pagespeed_contract(...).valid` succeed, the serialized integrator may call:

```python
context = normalize_psi_field_dimension_context(raw_psi_payload, bound_psi)
check = validate_psi_field_dimension_contract(raw_psi_payload, bound_psi, context)
```

Only a connected, integrity-valid context may be used as PSI CrUX field device context.
Lighthouse strategy remains lab-only. No customer scoring, persistence, authority, scan
budget, or execution behavior is changed by this lane helper.

## Rollback

Delete the helper, its focused test, and this note. The helper is unwired from shared
orchestration and requires no data migration or production rollback.
