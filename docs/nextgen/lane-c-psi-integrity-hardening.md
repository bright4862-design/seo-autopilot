# Lane C — PSI bound-integrity hardening

Issue: #324  
Draft PR: #331  
Branch: `agent/nextgen-browser-performance-20260921`

## Gap closed

The existing source-bound PageSpeed Insights adapter records explicit requested/final
identity and separate CrUX-field versus Lighthouse-lab provenance. Before this slice,
the bound composite did not have a dedicated integrity validator equivalent to the
strict direct-CrUX and direct-Lighthouse validators. A transported PSI dictionary could
therefore retain a valid base shape while its additive provenance was mutated after
normalization.

This slice adds `nextgen_pagespeed_bound_integrity_v1` in
`scanner-api/app/nextgen_browser_performance_psi_integrity.py`.

The validator is pure and additive. It performs no provider/network call, creates no
credential, grants no browser/Lighthouse budget, writes no persistence/authority state,
and creates no customer Fix or score.

## Fail-closed rules

`validate_bound_pagespeed_contract(...)` now requires:

- the existing PageSpeed composite contract to remain valid;
- the expected bound-adapter, base-adapter and provenance versions;
- every transported PSI identity to be a credential-free absolute HTTP(S) identity;
- connected field evidence to retain a supported `url`/`origin` scope, a requested
  identity, provider initial identity, and a provenance source matching the component;
- origin-scoped field evidence to identify a true root origin rather than a page-shaped
  path/query;
- connected lab evidence to retain the provider requested identity and a component source
  equal to the explicit Lighthouse final identity, or requested identity when no final
  redirect identity exists;
- field initial and Lighthouse requested identities to agree with the one composite
  requested identity when both components are connected;
- strategy and origin-fallback metadata to retain their expected types/values.

Non-connected field/lab states remain valid when the existing base contract confirms
that they retain no trusted measurements. Field and lab evidence are never merged.

## Deterministic regressions

Added `scanner-api/tests/test_nextgen_browser_performance_psi_integrity.py` with 12 cases:

1. consistent field/lab provenance passes;
2. base field-metric tampering is re-detected;
3. bound-adapter version tampering fails;
4. provenance-version tampering fails;
5. foreign field-source transport fails;
6. foreign Lighthouse-final transport fails;
7. cross-component requested-identity disagreement fails;
8. credential-bearing identity fails;
9. page-shaped origin scope fails;
10. connected lab without provider requested identity fails;
11. truthful unavailable field/lab components remain valid;
12. validation does not mutate the evidence dictionary.

A hermetic contract-boundary package executed this new slice: **12/12 passed in 0.08s**.
The new source and test also passed `py_compile` in that harness.

Exact-repository execution is still required before integration readiness is claimed.
The available container cannot resolve `github.com`, and the integration-target draft PR
has no normal pull-request-triggered repository workflow run.

## Integrator hook

For PSI observations, the serialized integrator should normalize with
`normalize_pagespeed_insights_evidence_bound(...)` and then require
`validate_bound_pagespeed_contract(...).valid` before any connected field or lab evidence
is trusted by later persistence/scoring/repair layers.

This validation is evidence trust only. It does not authorize execution and does not
change the existing browser/provider resource budget.

## Ownership / rollback

Only Lane-C helper/test/docs files are added. No `run_scan`, global budget, worker deploy
configuration, repair priority/customer scoring, authority/persistence/projection,
admission, release/deployment, schema/IAM/credentials, provider account, or production
surface is modified.

Rollback is deletion of this helper/test/doc slice. No stored data migration or authority
rewrite is required because the contract is currently unwired.
