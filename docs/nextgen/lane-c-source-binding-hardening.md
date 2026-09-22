# Lane C — performance observation source binding hardening

## Purpose

`nextgen_performance_observation_source_binding_v1` closes an evidence-integrity gap between the representative sample and already-normalized CrUX/Lighthouse evidence.

The existing coverage helper binds an observation's top-level `requested_url` to the selected sample and validates the field/lab component shapes. That is necessary but not sufficient for redirected or tampered evidence: a connected component can also carry its own `source_url`. This helper proves that the connected component source is the sampled request itself, the sampled request's origin for origin-scoped field data, or an explicitly provenance-backed redirect final identity.

It is pure validation only. It performs no provider/browser calls, creates no credentials, grants no execution budget, writes no authority/persistence state, and creates no customer Fixes or scores.

## Contract

Call:

```python
validate_performance_observation_source_binding(sample, observations)
```

Each observation identifies the sampled request with `requested_url` and may carry `field`, `lab`, or both.

The validator:

- validates the representative-sample contract first;
- requires requested identities to be absolute HTTP(S), selected by the sample and unique within the observation set;
- reuses the existing field and Lighthouse integrity contracts;
- requires connected field evidence to declare `scope=url|origin` and an absolute `source_url`;
- accepts origin-scoped field evidence directly only when its source is the actual origin of the sampled request;
- accepts redirected URL/origin field sources only when `nextgen_pagespeed_provenance_v1` proves `field_initial_url=requested_url` and `field_source_url=<connected field source>`;
- requires connected Lighthouse evidence to have an absolute source identity;
- accepts a redirected Lighthouse final identity only when PSI provenance proves `lighthouse_requested_url=requested_url` and `lighthouse_final_url=<connected lab source>`;
- validates any supplied provenance version, URL identities, strategy and origin-fallback type;
- does not require source binding for non-connected provider states because those states do not claim a measurement;
- never mutates the input sample or observations.

Any ambiguity fails closed with `valid=false` and deterministic per-observation reasons.

## Why it matters

Without this boundary, a structurally valid connected CrUX or Lighthouse envelope could be placed under a selected page's `requested_url` while its own measurement `source_url` referred to another page. Aggregate coverage could then overstate page-level evidence.

Redirects require special handling. PSI legitimately reports a requested URL and a different final document. This validator does not reject redirects; it requires explicit provider provenance before a different final identity can be credited to the sampled request.

Field and lab evidence remain independent. A valid field binding does not prove a lab binding, and vice versa.

## Integration hook

The serialized integrator should run source binding after provider normalization and before any connected coverage is treated as trusted:

1. produce and validate the representative sample;
2. normalize direct CrUX or source-bound PSI evidence;
3. assemble observation rows with the sampled `requested_url`;
4. call `validate_performance_observation_source_binding(...)`;
5. only when `valid=true`, call `summarize_performance_evidence_coverage(...)`;
6. keep the field and lab coverage objects separate through later authority/scoring work.

A valid source binding is evidence integrity only. It is not permission to run Lighthouse/browser work.

## Focused verification

The new focused test file covers:

- same-source URL-level field + lab binding;
- foreign URL-scoped field rejection;
- same-origin origin-scoped CrUX acceptance;
- rejection of page paths masquerading as origin-scoped field identity;
- provenance-backed cross-origin field redirect binding;
- provenance-backed Lighthouse redirects and rejection without provenance;
- tampered provenance requested identity;
- non-connected evidence remaining non-measurement evidence;
- duplicate requested observations;
- input immutability.

Hermetic source-binding slice: **10/10 passed**; `py_compile` passed.

The complete Lane-C exact-repository gate still needs to run on an approved repository runner. No full-suite green claim is made by this hardening slice.
