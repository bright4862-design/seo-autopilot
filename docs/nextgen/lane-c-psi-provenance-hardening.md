# Agent C — PSI source/provenance hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint: `1053b4f94fe8d5d44b28ad5780b11b3600efd47a`

## Purpose

This checkpoint strengthens the PageSpeed Insights side of Lane C without adding
network calls, credentials, browser execution, persistence, customer scoring, or
shared scan orchestration.

The documented PSI v5 response carries multiple identities and execution signals:

- top-level `id` is the canonical/final document URL after redirects;
- `loadingExperience.id` / `initial_url` identify the CrUX field-data subject and
  original requested URL;
- `loadingExperience.origin_fallback` states when page field data is actually an
  origin fallback;
- `lighthouseResult.requestedUrl` and `finalUrl` identify the lab request and final
  audited document;
- `analysisUTCTimestamp`, `fetchTime`, `lighthouseVersion`, and
  `configSettings.emulatedFormFactor` carry execution provenance;
- `lighthouseResult.runtimeError` indicates a serious Lighthouse runtime failure.

The earlier strict PSI adapter normalized measurements but did not retain or bind
all of those identities. A foreign/mismatched provider payload could therefore be
well-shaped while referring to a different requested page, and a Lighthouse
runtime error could still be mistaken for usable lab evidence.

## Pure source-bound adapter

`scanner-api/app/nextgen_browser_performance_psi_provenance.py` provides:

- `nextgen_pagespeed_bound_provider_v1`;
- `nextgen_pagespeed_provenance_v1`;
- requested/final URL normalization with fragments stripped and HTTP(S)-only
  identity validation;
- redirect-safe semantics: the requested identity must match the caller, while a
  different documented final URL is allowed and becomes the lab evidence identity;
- component-local fail-closed behavior, so a bad Lighthouse identity does not erase
  otherwise valid CrUX field evidence and vice versa;
- Lighthouse `runtimeError` => lab `provider_error` with no retained score,
  metrics, or opportunities;
- truthful `origin_fallback=true` handling: field evidence is reclassified to
  `scope=origin` instead of being presented as page-level CrUX;
- field `id` / `initial_url` binding and same-origin checks for origin evidence;
- deterministic provenance for analysis timestamp, Lighthouse fetch time/version,
  strategy, requested/final identities, and field source identity;
- no mutation of provider input dictionaries.

### Fail-closed request-identity hardening

CodeRabbit's review of exact head `3ad579754097d7fab81d8ec7c90820e28b23cf00`
identified one material provenance gap: when the caller supplied `source_url`, the
wrapper could retain connected PSI evidence even if the provider omitted the
corresponding requested identity.

That gap is closed at code/test checkpoint
`1053b4f94fe8d5d44b28ad5780b11b3600efd47a`:

- connected lab evidence now requires `lighthouseResult.requestedUrl` whenever a
  caller `source_url` is supplied; absence fails only lab evidence closed with
  `lighthouse_requested_identity_missing`;
- connected field evidence now requires the selected loading experience's
  `initial_url` whenever a caller `source_url` is supplied; absence fails only field
  evidence closed with `psi_field_initial_identity_missing`;
- an `id`/final subject alone is not accepted as proof that the provider observation
  was requested for the caller page;
- invalid and mismatched identities continue to fail only the affected component
  closed;
- redirect semantics remain unchanged when the provider supplies a matching request
  identity and a different valid final identity.

The existing provider-shape adapter remains unchanged. The serialized integrator
may choose the source-bound adapter only after review and exact-head verification.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_psi_provenance.py` now contains
10 pure regressions covering:

1. requested/final redirect identity preservation;
2. foreign Lighthouse requested identity failing lab evidence closed only;
3. missing Lighthouse requested identity failing lab evidence closed when caller
   source identity is known;
4. Lighthouse runtime error invalidating lab evidence while retaining field data;
5. PSI `origin_fallback=true` preserving origin-level field truth;
6. foreign field `initial_url` failing field evidence closed only;
7. missing field `initial_url` failing field evidence closed when caller source
   identity is known;
8. invalid caller source identity failing both components closed;
9. provider analysis/fetch/version/strategy provenance;
10. provider payload immutability.

A hermetic wrapper harness using stubbed existing Lane-C normalizers passed
**10/10**, and the modified wrapper/test files passed `py_compile`. This validates
the changed pure wrapper logic only; it is not a substitute for the repository
suite.

## Exact repository gate still required

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py
```

With the prior 45 focused tests plus the 10 provenance regressions, Lane C now
contains **55 focused tests**. Exact-head 55/55 repository execution is not claimed
until an approved repository runner executes the commands above.

## Integration handoff

The serialized integrator should bind the PSI request URL to the exact candidate
selected by the representative sampler. When it supplies that candidate as
`source_url`, connected field/lab evidence must retain the provider request identity
that corroborates the candidate. Missing provider request identity is unknown /
unavailable provenance, not permission to infer a match.

A redirect is valid when the provider reports the original request identity
consistently and supplies a valid final URL. Downstream consumers should use the
final lab identity for Lighthouse evidence and the field subject identity/scope for
CrUX evidence.

A Lighthouse runtime failure is not evidence of a site performance defect. It is a
provider/lab observation failure. Likewise, origin fallback field data must never
be displayed or scored as URL-level field evidence.

This helper does not authorize any additional PSI/Lighthouse call. Browser/provider
execution budgets remain integrator-owned and shadow/off by default.

## Ownership and safety

This checkpoint changes only Lane-C pure helper/test/docs surfaces. It does not
modify `scanner.py` / `run_scan`, global budgets, worker deployment config, repair
priority/customer scoring, authority/persistence/projection, admission, release,
deployment, production, schema, IAM, credentials, or provider accounts.
