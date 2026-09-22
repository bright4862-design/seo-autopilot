# Lane D — connected-evidence coverage semantics hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

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

Unavailable states continue to carry no records under the generic contract and therefore have no observation-accounting claim to prove at this layer.

## Verification

New deterministic suite:

`scanner-api/tests/test_connected_evidence_coverage_contract.py`

contains 13 focused regressions covering versioning/non-mutation, GSC sample/coverage counts, GSC dimension population and date-period binding, URL Inspection URL-count binding, Bing normalized/input accounting and date chronology, GA4 normalized/input accounting, period-end binding, and unavailable-state behavior.

Hermetic pure-function check for the new contract: **13/13 passed**.  
`py_compile` for the new module/test: passed.

These checks used a pass-through stub for the already-tested upstream record-semantic validator, so they prove the new fourth-layer logic in isolation only. They are not a substitute for the branch-native exact-head suite.

Before serialized integration, run from `scanner-api/` on the exact branch head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py`

Expected focused count after this slice: **94 tests** (23 adapter + 24 generic contract + 17 source-profile + 2 timestamp hardening + 15 record-semantics + 13 coverage-semantics).

## Serialized integration gate

Any later authorized payload/import must pass, in order:

1. `validate_connected_evidence(...)`
2. `validate_connected_evidence_source_identity(...)`
3. `validate_connected_evidence_record_semantics(...)`
4. `validate_connected_evidence_coverage_semantics(...)`

Only then may the serialized integrator attach the optional evidence. Connected evidence remains separate from canonical crawl authority, and Standard 150 behavior remains unchanged when no connected evidence is present.
