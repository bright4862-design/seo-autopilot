# Lane C representative sample site-origin binding

Issue: #324  
Draft PR: #331  
Lane: `agent/nextgen-browser-performance-20260921`

## Why

The representative sampler and its deterministic population binding prove *which*
retained pages were selected, but they do not prove that every selected final URL still
belongs to the authoritative site origin. A retained page may legitimately carry a final
URL after redirects; if that final identity is foreign, later browser/performance work
must not treat it as a representative page for the target site.

## Contract

`nextgen_performance_sample_origin_binding_v1` is a pure, fail-closed identity contract.
The serialized integrator supplies the already-selected representative sample plus its
authoritative `site_url`.

The helper:

- canonicalizes only absolute HTTP(S) origins;
- rejects credentials in either the site identity or selected page identity;
- normalizes host case, trailing dots, and default ports;
- treats scheme changes and non-default port changes as different origins;
- records only foreign **origins**, not full foreign URLs/query strings;
- preserves empty valid samples as valid identity evidence while granting no execution;
- performs no network/browser/provider call and grants no execution budget.

`nextgen_performance_sample_origin_binding_integrity_v1` recomputes the artifact from
the original sample and site identity. A truthful fail-closed source artifact can itself
be integrity-valid; `expected_binding_valid` carries the source validity separately.

## Integration hook

After `validate_representative_sample_binding(authoritative_pages, sample)` succeeds, the
serialized integrator may call:

```python
origin_binding = bind_representative_sample_to_site_origin(
    sample,
    site_url=authoritative_site_url,
)
origin_integrity = validate_representative_sample_origin_contract(
    sample,
    site_url=authoritative_site_url,
    artifact=origin_binding,
)
```

Browser/provider execution remains forbidden unless both the deterministic sample
binding and the site-origin binding are trusted **and** the existing integrator-owned
budget/safe-request path separately authorizes the work.

This helper must not be used to alter `run_scan`, global browser budgets, repair/customer
scoring, authority/persistence/projection, admission, deployment, or production.

## Focused verification

`tests/test_nextgen_browser_performance_sample_origin.py` contains 15 deterministic
regressions covering same-origin success, default-port normalization, foreign origin,
scheme/port changes, credential-bearing identities, non-HTTP identities, malformed
sample shape/version, empty samples, integrity laundering, truthful fail-closed
transport, and input immutability.

Focused local result: **15/15 passed**. Source/test `py_compile` also passed.
No live provider calls or credentials are used.
