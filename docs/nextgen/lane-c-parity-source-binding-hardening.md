# Lane C parity source-binding hardening

Checkpoint code/test head: `0a8f43b087ee62a50bd60007f93850f974de2b9d`

## Purpose

`validate_resolved_critical_parity_contract()` proves that a transported raw/rendered parity envelope is internally well-formed, but internal consistency alone does not prove that the envelope was produced from the retained raw and rendered observations currently being reviewed.

This slice adds `nextgen_critical_parity_source_binding_v1` in `scanner-api/app/nextgen_browser_performance_parity_source_binding.py`.

The helper is pure and additive. It recomputes `nextgen_critical_content_parity_v2_resolved` from caller-supplied raw/rendered source observations and render outcome, validates both the transported and recomputed parity contracts, then requires every parity-owned field to match exactly:

- version and base/canonical-resolution versions;
- raw/rendered document identity;
- state and reason;
- material-delta flag;
- verified and changed field sets;
- full field-level parity evidence.

Extra top-level transport metadata is deliberately not authoritative and does not affect the binding.

## Safety semantics

- A failed or unavailable render can bind only to `not_verified` parity evidence.
- A previously matched/material-delta envelope cannot be rebound to a failed render or a different raw/rendered document pair.
- A structurally valid field-level forgery is rejected when it differs from recomputed source evidence.
- Relative canonical resolution remains delegated to the existing resolved-parity comparator, so source binding uses the same browser-correct canonical semantics.
- The helper performs no browser execution, provider call, network I/O, persistence, authority write, repair/customer scoring, or budget allocation.

## Deterministic verification

Added `scanner-api/tests/test_nextgen_browser_performance_parity_source_binding.py` with 14 deterministic regressions covering:

1. exact matched-source binding;
2. material-delta binding;
3. relative-canonical binding;
4. structurally plausible field-value forgery rejection;
5. wrong raw source identity;
6. wrong rendered source identity;
7. truthful failed-render `not_verified` binding;
8. matched evidence rejected for a failed render;
9. render-reason binding;
10. invalid transported contract rejection;
11. non-authoritative extra transport metadata;
12. non-object evidence fail-closed behavior;
13. source changes after evidence creation;
14. input immutability.

A hermetic local contract-boundary harness passed `14/14`, and the new source/test pair passed `py_compile`. This is not a claim that the complete repository suite or exact PR head CI is green.

## Integrator hook

After raw and rendered observations have been paired through the existing safe browser path:

1. build `compare_critical_content_parity_resolved(...)`;
2. validate `validate_resolved_critical_parity_contract(...)`;
3. validate `validate_resolved_critical_parity_source_binding(raw_page, rendered_page, parity, render_state=..., render_reason=...)` using the exact retained source observations and render outcome;
4. only then pass the parity artifact into sufficiency/coverage aggregation.

The serialized integrator remains responsible for orchestration, execution budgets, persistence, authority, customer projection, and repair priority. This lane does not wire any of those surfaces.

## Rollback

Drop the new helper, test file, and this note. No shared schema, production state, provider configuration, credentials, or historical reconstruction bytes are changed.
