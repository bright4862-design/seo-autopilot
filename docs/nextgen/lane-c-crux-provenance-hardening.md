# Agent C — direct CrUX source/coverage provenance hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint: `5302e6991e7d85337dc7ad3c59f9f58036097c41`

## Why this checkpoint exists

Lane C already had a pure adapter for the documented CrUX `queryRecord` envelope. The
remaining trust gap was at the strict connected-evidence boundary: a caller could receive
structurally normalized field metrics even when the raw record identity was ambiguous,
when an `origin` key actually named a page, or when the provider collection period was
missing or malformed.

This checkpoint adds an additive wrapper rather than changing the existing compatibility
adapter. It performs no provider call, requests no credentials, grants no provider or
browser budget, writes no authority/persistence/customer state, and does not alter shared
scan orchestration.

## New contracts

`nextgen_crux_bound_provider_v1` accepts already-observed direct CrUX `queryRecord`
payloads and requires, before connected field metrics are trusted:

- exactly one non-empty raw provider record key: `url` or `origin`;
- an absolute HTTP(S) identity without embedded userinfo;
- a true root origin (`scheme://host/`, no page path/query) for origin-scoped records;
- caller scope/source corroboration when supplied, without scope broadening;
- a valid ordered provider `collectionPeriod` with both first and last dates.

Failure stays fail-closed as non-measurement evidence. `rate_limited`, `disconnected`,
`unavailable`, and `provider_error` remain non-connected states and retain no measurements
or collection coverage.

`nextgen_crux_provenance_v1` preserves the provider record scope/identity, corroborating
caller scope/identity, collection period and observation timestamp separately from the
field metrics.

`nextgen_crux_bound_integrity_v1` re-validates the base field contract plus additive
adapter versions, source/scope relationships and equality between the evidence collection
period and provenance collection period. Transport mutation therefore cannot silently
turn a foreign or differently scoped record into trusted connected evidence.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_crux_provenance.py` adds ten tests for:

1. connected URL-scoped identity and coverage provenance;
2. connected true-origin scope;
3. raw two-key ambiguity even when one key is malformed;
4. page-shaped or query-bearing origin rejection;
5. missing/reversed collection-period rejection;
6. embedded-credential URL rejection;
7. page URL rejection as an origin-scoped caller identity;
8. non-connected rate-limit state retaining no measurements/coverage;
9. integrity rejection of source and coverage provenance tampering;
10. provider-payload immutability.

The exact new slice passed **10/10 in 0.05s** in a hermetic package using the current base
provider-adapter behavior, and the new source/test passed `py_compile`.

Lane C now contains **122 focused tests across eleven test files**. The full 122-test exact
repository gate is **not claimed green** until an approved repository runner executes the
commands recorded in `docs/nextgen/lane-c-browser-performance-handoff.md`.

## Integrator handoff

For direct CrUX `queryRecord` data, the serialized integrator should prefer
`normalize_crux_query_record_evidence_bound(...)` and require
`validate_bound_crux_contract(...).valid` before treating a connected field component as
trusted. The existing provider adapter remains the underlying compatibility normalizer.

This does not replace the existing owner-authorization / exact-scan-identity / currentness
rules in the shared Stage-2 provider admission path. Lane C supplies a pure observation
contract only; the serialized integrator continues to own any future admission,
authority, persistence, projection or scoring wiring.

## Rollback

The new wrapper and tests are additive and currently unwired. Rollback is deletion of
`scanner-api/app/nextgen_browser_performance_crux_provenance.py`, its focused test file,
and this note; no migration or durable data rewrite is required.
