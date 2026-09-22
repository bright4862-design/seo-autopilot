# Lane C — direct CrUX form-factor context hardening

Issue: #324  
Draft PR: #331  
Branch: `agent/nextgen-browser-performance-20260921`

## Why this slice exists

Direct CrUX field evidence can be scoped not only by URL/origin but also by device form factor. The CrUX `queryRecord` response echoes an explicit `record.key.formFactor` for `PHONE`, `TABLET`, or `DESKTOP`; when that key is omitted, the record is aggregated across all form factors. Lane C previously bound URL/origin identity and collection period but did not preserve this device dimension as a separately validated field context.

That omission is risky because aggregate field data could later be mislabeled as mobile/desktop, or a Lighthouse lab strategy could be mistaken for the CrUX field population. This slice keeps those meanings separate.

## Contract

`scanner-api/app/nextgen_browser_performance_crux_dimensions.py` adds:

- `nextgen_crux_field_dimension_v1`
- `nextgen_crux_field_dimension_integrity_v1`
- `normalize_crux_field_dimension_context(...)`
- `validate_crux_field_dimension_contract(...)`

The helper accepts only an already-observed direct CrUX `queryRecord` payload plus already source-bound `nextgen_crux_bound_provider_v1` field evidence. It performs no network call and does not authorize provider execution.

Connected dimension evidence requires:

1. a valid direct-CrUX bound field envelope;
2. raw record URL/origin identity equal to the bound field identity;
3. raw collection period equal to the bound field collection period;
4. `record.key.formFactor` equal to `PHONE`, `TABLET`, or `DESKTOP`, or omitted to mean `all`;
5. when the caller supplies the original requested form factor, exact agreement with the provider record.

Any disagreement fails closed to `unavailable` with no device claim. Non-connected provider states retain no form-factor claim.

The field vocabulary is intentionally `phone` / `tablet` / `desktop` / `all`. The helper does **not** accept Lighthouse's `mobile` label as a CrUX request dimension, so lab emulation strategy cannot be laundered into field-population provenance.

## Verification

Deterministic focused regression:

```bash
cd scanner-api
PYTHONPATH=. pytest -q tests/test_nextgen_browser_performance_crux_dimensions.py
python -m py_compile \
  app/nextgen_browser_performance_crux_dimensions.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py
```

Result in the hermetic lane harness: **13/13 passed in 0.07s**; `py_compile` passed.

Coverage includes explicit phone/tablet/desktop handling, omitted-form-factor aggregate semantics, caller/provider mismatch, invalid provider or caller dimensions, raw-vs-bound identity and collection-period mismatch, rejection of foreign PSI field envelopes, non-connected states, tamper detection, and input immutability.

## Serialized integrator hook

Only after direct CrUX evidence has passed `validate_bound_crux_contract(...)`, optionally derive device context with:

```python
context = normalize_crux_field_dimension_context(
    raw_crux_payload,
    bound_crux_field,
    requested_form_factor=original_query_form_factor,
)
assert validate_crux_field_dimension_contract(
    raw_crux_payload,
    bound_crux_field,
    context,
    requested_form_factor=original_query_form_factor,
)["valid"]
```

`original_query_form_factor` should be the actual CrUX query dimension (`PHONE`, `TABLET`, `DESKTOP`, or an explicit internal `all` marker). Do not populate it from Lighthouse/PSI lab strategy. If the original query dimension was not retained, omit the argument and treat the provider record key as the available evidence source.

PSI field evidence is intentionally not passed through this direct-CrUX helper because PSI's Lighthouse strategy is a lab setting and is not proof that the CrUX field population was filtered to the same device class.

## Boundary and rollback

No `run_scan`, global budget, worker deployment configuration, repair/customer scoring, authority/persistence/projection, admission, release/deployment, credentials, provider accounts, or production surface is changed.

Rollback is deletion of this helper/test/doc and removal of its handoff hook. No persistence or schema migration is involved.
