# Lane D — connected-evidence coverage semantics hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

> **Historical slice note:** this file records the coverage-semantics boundary as it was introduced. It is not the current integration gate. The authoritative final validation sequence, exact-head pytest/`py_compile` commands, and current focused-test total live in `docs/nextgen/lane-d-evidence-connectors.md`. A serialized integrator must not stop at the boundary documented here.

## Purpose

The first three Lane-D validation boundaries prove envelope shape, provider/source identity, and provider-record semantics. They did not independently prove that sample/coverage metadata matched the records actually carried by the envelope. A structurally valid envelope could therefore overstate row counts, present inconsistent import accounting, claim a period end that did not match `observed_at`, or carry dated Bing/GA4 records later than the stated observation time.

This slice adds a fourth pure boundary:

`connected_evidence_coverage_semantics_v1`

implemented by `validate_connected_evidence_coverage_semantics(...)` in `scanner-api/app/connected_evidence_coverage_contract.py`.

It composes after `validate_connected_evidence_record_semantics(...)` and remains pure: no network calls, OAuth/account changes, persistence, scoring, customer projection, Base44 schema mutation, `run_scan`, release/deploy/admission, or production changes.

## Fail-closed invariants

For observed GSC Search Analytics evidence:
- `sample.row_count` and `coverage.row_count` must equal the carried record count;
- `coverage.dimensions` must be non-empty, unique, and match every record's dimension-key population;
- declared period start/end must be ordered;
- when `date` is a dimension, every record date must fall inside the declared period;
- when both are present, `coverage.period_end` must represent the same instant as `observed_at`.

For observed URL Inspection evidence:
- sample kind must be `single_url_inspection`;
- sample and coverage URL counts must match the carried record population;
- exactly one URL is permitted.

For observed Bing AI Performance imports:
- sample row count must match carried records;
- `normalized_row_count` must match carried records;
- `input_row_count == normalized_row_count + rejected_row_count`;
- `coverage.period_end` must match `observed_at` when both are present;
- a record date may not be later than `observed_at`.

For observed GA4 AI-assistant referral evidence:
- sample row count must match carried records;
- `normalized_row_count` must match carried records;
- `input_row_count == normalized_row_count + unmatched_row_count + rejected_row_count`;
- `coverage.period_end` must match `observed_at` when both are present;
- a record date may not be later than `observed_at`.

Unavailable states carry no records, observed timestamp, sample-observation claim, or coverage-observation claim under the current generic contract and therefore have no record-accounting claim to prove at this layer.

## Historical slice verification

`scanner-api/tests/test_connected_evidence_coverage_contract.py` contains the deterministic coverage/accounting regressions for this boundary. The slice was verified independently when introduced. Those results remain useful regression history but are not the current exact-head integration gate because later Lane-D boundaries add provider property scope, logical-record identity, canonical source/snapshot identity and cross-state coherence.

## Current serialized-integrator requirement

This boundary is necessary but no longer sufficient on its own. Any later authorized payload/import must be normalized, then the complete logical enrichment set must pass `validate_connected_evidence_snapshot_bundle(...)` before attachment.

`validate_connected_evidence_snapshot_bundle(...)` composes the current full Lane-D chain, including generic envelope → source identity → record semantics → this coverage semantics boundary → provider property/source scope → logical record identity → canonical source/snapshot identity and cross-state coherence. Do not reproduce the historical four-layer sequence from this slice as an integration gate.

For the authoritative exact-head pytest/`py_compile` gate and current focused-test count, use `docs/nextgen/lane-d-evidence-connectors.md` only.

Connected evidence remains separate from canonical crawl authority, and Standard 150 behavior remains unchanged when no connected evidence is present.
