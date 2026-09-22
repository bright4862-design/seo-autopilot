# Lane D hardening — logical record identity

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

## Why this slice exists

The existing Lane-D stack proves envelope integrity, registered provider/source attribution, provider-record semantics, coverage/accounting integrity, provider property scope, and duplicate snapshot identities. One remaining double-counting path was inside a single otherwise-valid envelope: two transported rows could use different `row_number` values while representing the same logical provider dimensions. Treating transport position as identity would let duplicate GSC aggregates, Bing AI-performance rows, or GA4 referral aggregates be counted twice by later consumers.

`connected_evidence_record_identity_v1` closes that gap as a pure, fail-closed contract. It does not merge or sum duplicates and does not choose a winner.

## Identity semantics

- **GSC Search Analytics:** logical identity is the ordered value tuple for the exact `coverage.dimensions` population. Different transport row numbers or metric values cannot make the same provider dimension tuple distinct.
- **Google URL Inspection:** logical identity is the inspected URL. The earlier contracts already require exactly one observed row and bind it to provenance.
- **Bing AI Performance export:** logical identity is the carried provider dimension population: kind, date, URL, grounding query, topic, intent, geography, country, region, market, and surface. Citation metrics are measurements, not identity.
- **GA4 AI-assistant referrals:** logical identity is assistant, date, source, medium, landing page, geography, country, region, and device category. Sessions/users/events/revenue are measurements, not identity.
- **Unavailable states:** no observed rows are claimed, so record-identity population checking is a no-op after the upstream fail-closed boundary.

The validator composes `validate_connected_evidence_scope_semantics(...)` first. Ambiguous/blank required identity fields fail closed rather than being guessed.

## Integration handoff

For later serialized integration, normalize each provider payload/import, validate each observed envelope through `validate_connected_evidence_record_identity_semantics(...)` (which composes the preceding envelope → source → record → coverage → property-scope stack), then validate the complete logical enrichment set with `validate_connected_evidence_snapshot_bundle(...)`. Connected evidence remains optional and separate from canonical crawl authority.

This slice performs no network I/O, OAuth/account mutation, Base44 schema change, `run_scan` wiring, repair scoring, authority/persistence/customer projection, admission, release, deployment, or production mutation.

## Verification

New deterministic suite:

`PYTHONPATH=. pytest -q tests/test_connected_evidence_record_identity_contract.py`

Expected new slice: **10 tests**.

A hermetic package run of this new suite passed **10/10** and the module/test compile cleanly. Full exact-head repository certification remains required before serialized integration.

With the prior 125 focused tests, the expected Lane-D focused total becomes **135 tests**. The exact-head gate should add:

- `tests/test_connected_evidence_record_identity_contract.py`
- `app/connected_evidence_record_identity_contract.py`

to the previously documented Lane-D pytest and `py_compile` commands.

No undocumented Google Generative AI API endpoint is introduced or assumed by this change.
