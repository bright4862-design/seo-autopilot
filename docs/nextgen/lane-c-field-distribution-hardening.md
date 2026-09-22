# Agent C — provider-neutral field distribution hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint: `c858aac5022929939e992f8cbc2183e613a3dd86`

## Scope

This checkpoint adds a pure, unwired field-only distribution contract for already-observed and already-bound direct CrUX and PageSpeed Insights/CrUX responses. It performs no provider calls, browser work, credential creation, persistence, scoring, authority writes, admission changes, release work, or deployment.

Field and lab evidence remain separate. PSI Lighthouse data is intentionally ignored by this contract even when it is present in the same provider response.

## Contract

`scanner-api/app/nextgen_browser_performance_field_distributions.py` adds:

- `nextgen_field_metric_distribution_v1`;
- `nextgen_field_metric_distribution_integrity_v1`;
- `normalize_crux_field_distribution_evidence(...)`;
- `normalize_psi_field_distribution_evidence(...)`;
- `validate_field_distribution_contract(...)`.

Direct CrUX `histogram` rows and PSI CrUX `distributions` rows normalize into the same field shape:

- canonical metric key (`lcp`, `inp`, `cls`, `fcp`, `ttfb`);
- trusted p75 copied from the already-bound field evidence;
- canonical unit (`ms` or `score`);
- ordered `{min, max, proportion}` bins.

PSI CLS percentile and distribution bounds are converted from the PSI centi-score representation into the same `score` unit already used by Lane C's field contract. No Lighthouse lab value is used to populate or repair field data.

## Fail-closed behavior

A distribution is trusted only after the corresponding source contract succeeds:

- direct CrUX: `nextgen_crux_bound_integrity_v1`;
- PSI: `nextgen_pagespeed_bound_integrity_v1`.

The raw provider payload must also bind back to that trusted evidence. Direct CrUX record identity and collection period must still match the bound provenance. PSI field `initial_url` and field subject identity must still match its bound provenance, including origin-fallback handling.

Per-metric distributions are omitted rather than guessed when:

- the raw p75 disagrees with the trusted normalized p75;
- bins are malformed, overlap, continue after an open-ended range, or have invalid proportions;
- distribution mass does not sum to approximately one;
- the trusted metric/unit is invalid or the provider distribution is absent.

If no trusted metric distribution remains, the derived artifact is `unavailable` with no measurements. Non-connected provider states retain no distribution metrics. The integrity validator also rejects credential-bearing source identities, cross-provider source-contract laundering, tampered bin geometry/mass, and a metric being simultaneously present and omitted.

## Deterministic regression coverage

`scanner-api/tests/test_nextgen_browser_performance_field_distributions.py` adds 18 deterministic cases covering:

1. direct CrUX histogram normalization;
2. PSI distribution normalization into the same provider-neutral shape;
3. PSI CLS score scaling;
4. explicit field/lab separation when Lighthouse reports a conflicting LCP value;
5. invalid bound-CrUX fail-closed behavior;
6. invalid bound-PSI fail-closed behavior;
7. rate-limited field evidence retaining no distribution measurements;
8. raw/trusted percentile disagreement;
9. overlapping histogram bins;
10. invalid distribution mass;
11. all-distributions-unavailable behavior;
12. PSI origin fallback using the field loading-experience block rather than lab data;
13. direct-CrUX raw/source identity mismatch;
14. PSI raw/source identity mismatch;
15. integrity rejection of tampered bin overlap and mass;
16. credential-bearing source identity rejection;
17. provider/source-contract laundering rejection;
18. input immutability and present-vs-omitted integrity.

Focused hermetic contract-boundary harness: **18/18 passed**. The new implementation and repository-shaped test file also passed `py_compile`. A complete exact-branch repository run is still required before integration readiness is claimed.

## Integrator hook

After `normalize_crux_query_record_evidence_bound(...)` + `validate_bound_crux_contract(...)` succeeds, the serialized integrator may derive optional histogram evidence with `normalize_crux_field_distribution_evidence(raw_crux_payload, bound_crux)` and must validate the derived artifact before trusting it.

After `normalize_pagespeed_insights_evidence_bound(...)` + `validate_bound_pagespeed_contract(...)` succeeds, the integrator may derive PSI field distributions with `normalize_psi_field_distribution_evidence(raw_psi_payload, bound_psi)` and must validate the derived artifact. This hook consumes the PSI **field** component only; Lighthouse lab metrics stay on the separate lab path.

The contract adds evidence only. It grants no provider execution entitlement, browser budget, crawl budget, repair priority, customer score, authority, persistence, projection, admission, release, or deployment behavior.

## Rollback

Because the slice is additive and unwired, rollback is deletion of this helper, its focused test, and this note. No migration or production rollback action is required.
