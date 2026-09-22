# Lane C — strict Lighthouse provenance hardening

Issue: #324  
Draft PR: #331  
Branch: `agent/nextgen-browser-performance-20260921`

## Purpose

This additive slice tightens direct Lighthouse lab evidence without changing execution,
budgets, scoring, persistence, or production. It accepts already-observed Lighthouse JSON
only and performs no network/provider calls.

The existing PSI-bound adapter already protects Lighthouse evidence inside PageSpeed
Insights responses. This slice closes the same provenance gap for direct Lighthouse
observations produced by any future integrator-owned browser/lab execution path.

## Contract

`normalize_lighthouse_evidence_bound(...)` emits the existing
`nextgen_lighthouse_evidence_v1` lab envelope plus:

- `adapter_version = nextgen_lighthouse_bound_provider_v1`
- `provenance.version = nextgen_lighthouse_provenance_v1`
- normalized caller/requested/final URL identities
- Lighthouse fetch time and version
- mobile/desktop strategy when explicitly supplied
- runtime-error provenance
- an allowlisted record of audits excluded because Lighthouse marked them as errors

Connected evidence requires a valid provider `requestedUrl`. When the caller supplies a
sampled `source_url`, the provider requested identity must match it. A distinct valid
`finalUrl` is allowed and becomes the lab evidence source, preserving legitimate redirects.

A Lighthouse `runtimeError` becomes `provider_error` and retains no performance score,
metrics, or opportunities. Individual audits with `errorMessage` or
`scoreDisplayMode=error` are removed before normalization so failed audits cannot become
measurements.

`validate_bound_lighthouse_contract(...)` reuses the existing lab contract and additionally
checks the adapter/provenance versions, requested/provider-requested/source/final identity
relationship, strategy, runtime-error shape, and excluded-audit provenance.

## Deterministic verification

A hermetic contract-boundary harness ran the exact new helper/test logic with no provider
or browser calls:

- `10 passed in 0.08s`
- new source/test `py_compile` passed

The focused regressions cover:

1. explicit redirect provenance;
2. runtime errors becoming provider errors;
3. missing provider requested identity;
4. requested-identity mismatch;
5. invalid final identity;
6. invalid caller source identity;
7. failed-audit exclusion while retaining valid lab measurements;
8. non-connected states retaining no measurements;
9. input immutability;
10. forged source/provenance failing integrity validation.

This does **not** certify the full branch-native repository suite. The exact-head repository
gate must include the new test file before integration readiness can be claimed.

## Integration hook

For direct Lighthouse observations, the serialized integrator should call
`normalize_lighthouse_evidence_bound(...)` instead of the legacy unbound lab normalizer,
then require `validate_bound_lighthouse_contract(...).valid` before trusting connected lab
evidence. CrUX field evidence remains separate and must continue through its field-specific
adapter/binding path.

This helper grants no Lighthouse execution entitlement. The representative sample remains
a candidate set only; actual browser/lab execution count is owned by the serialized
integrator.

## Ownership / rollback

Only Lane-C helper/test/docs files are added. No `run_scan`, global budget, worker
configuration, repair/customer scoring, authority/persistence/projection, admission,
release/deploy, schema/IAM/credential, provider-account, or production surface changes.

Rollback is deletion of this helper, test, and note. No migration or historical evidence
rewrite is required.
