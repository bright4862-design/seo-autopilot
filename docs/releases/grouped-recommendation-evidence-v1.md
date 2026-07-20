# Grouped recommendation evidence v1

## Scope

- Python Review groups missing, empty, and malformed meta-description states by page-template family.
- Mixed states become one `meta_description_unusable` task with exact counts and original-rule provenance.
- Single-state groups keep their specific rule and do not invent `combined_rules`.
- All repeated page-pattern findings receive an evidence-specific grouping explanation.
- `FixItem` persists metadata counts, combined-rule provenance, and grouping rationale as first-class fields.

## Production acceptance

1. Funbooker grouped description tasks report non-zero missing/empty counts matching affected pages.
2. Saved FixItems retain the same counts and grouping copy after refresh.
3. A single-state group keeps `combined_rules: []`.
