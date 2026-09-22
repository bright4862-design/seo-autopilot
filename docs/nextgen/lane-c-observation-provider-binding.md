# Agent C — sampled observation provider binding

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Code/test checkpoint: `d6ea7998f370a6f191bcb346472edda70e1abfad`

## Trust gap closed

Lane C already had three separate protections around sampled performance evidence:

1. deterministic representative-sample population and site-origin binding;
2. sampled request/source binding for field and lab observations;
3. provider-specific bound CrUX, PSI and Lighthouse provenance/integrity contracts.

What was still missing was an explicit proof that a transported base `field` or `lab` component
was the exact component contained in one of those already-valid provider-bound envelopes. A
caller could otherwise transport a structurally valid component independently of the provider
envelope and rely on source URL shape alone.

`scanner-api/app/nextgen_browser_performance_observation_provider_binding.py` adds
`nextgen_performance_observation_provider_binding_v1` to close that gap without changing any
shared scanner wiring.

## Contract

Each sampled observation identifies one selected `requested_url`, carries one or both base
`field` / `lab` components, and supplies `provider_bindings` entries shaped as:

```text
{"kind": "crux" | "psi" | "lighthouse", "evidence": <bound provider envelope>}
```

The validator:

- revalidates the representative-sample contract and selected identities;
- rejects malformed, non-HTTP(S), credential-bearing or duplicate sampled identities;
- revalidates every supplied bound provider envelope with the existing CrUX, PSI or Lighthouse
  bound validator;
- requires provider-request identity to match the sampled request (origin equivalence is allowed
  only for an origin-scoped direct-CrUX field record);
- requires the transported base component to exactly match the corresponding component from the
  provider envelope;
- rejects duplicate provider kinds and valid-but-unused provider bindings so extra provenance
  cannot be attached misleadingly;
- leaves an empty observation list valid without claiming any coverage.

## Field/lab separation

The binding capabilities are intentionally asymmetric:

- direct CrUX can satisfy `field` only;
- direct Lighthouse can satisfy `lab` only;
- PSI can carry both, but its field and lab components are compared independently.

A Lighthouse envelope cannot justify a field metric. A CrUX envelope cannot justify a lab
metric. The helper performs no conversion between field and lab context and does not use
Lighthouse strategy to fill CrUX device evidence.

## Integration order

The future serialized integrator should use this order for sampled performance observations:

1. validate deterministic sample population binding;
2. validate sample site-origin binding;
3. execute only an integrator-budget-approved subset via existing safe browser/provider paths;
4. normalize and validate provider-specific bound CrUX/PSI/Lighthouse envelopes;
5. validate sampled request/source binding;
6. validate `nextgen_performance_observation_provider_binding_v1`;
7. only then summarize field/lab coverage.

None of these Lane-C helpers grants provider/browser/Lighthouse execution budget, changes crawl
budgets, writes persistence/authority state, or computes repair/customer priority.

## Deterministic verification

`scanner-api/tests/test_nextgen_browser_performance_observation_provider_binding.py` adds 19
regressions for direct and PSI binding, origin-scoped CrUX, malformed/credential-bearing
identities, invalid provider envelopes, requested-identity disagreement, component tampering,
field↔lab laundering attempts, duplicate/unused provider bindings, duplicate observations,
truthful rate-limited evidence, empty observations, and input immutability.

Isolated contract-boundary result for the new slice: **19/19 passed**. The source/test pair also
passed `py_compile`. This is not an exact-repository CI claim; the full Lane-C gate remains
required in a complete checkout.

## Rollback and boundary

The helper is additive and unwired. Rollback is deletion of this helper, its tests and this note.
No `run_scan`/global budget, worker deployment configuration, repair/customer scoring,
authority/persistence/projection, admission, release/deployment, credentials/provider accounts,
or production surface is changed by this checkpoint.
