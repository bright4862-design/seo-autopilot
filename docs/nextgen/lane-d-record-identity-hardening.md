# Lane D hardening — logical record identity

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

> **Historical slice note:** this file records the logical-record-identity boundary as it was introduced. It is not the current integration gate. The authoritative final validation sequence, exact-head pytest/`py_compile` commands, and current focused-test total live in `docs/nextgen/lane-d-evidence-connectors.md`. A serialized integrator must not stop at the boundary documented here.

## Why this slice exists

The existing Lane-D stack proves envelope integrity, registered provider/source attribution, provider-record semantics, coverage/accounting integrity and provider property scope. One remaining double-counting path was inside a single otherwise-valid envelope: two transported rows could use different `row_number` values while representing the same logical provider dimensions. Treating transport position as identity would let duplicate GSC aggregates, Bing AI-performance rows, or GA4 referral aggregates be counted twice by later consumers.

`connected_evidence_record_identity_v1` closes that gap as a pure, fail-closed contract. It does not merge or sum duplicates and does not choose a winner.

## Identity semantics

- **GSC Search Analytics:** logical identity is the ordered value tuple for the exact `coverage.dimensions` population. Different transport row numbers or metric values cannot make the same provider dimension tuple distinct.
- **Google URL Inspection:** logical identity is the inspected URL. The earlier contracts already require exactly one observed row and bind it to provenance.
- **Bing AI Performance export:** logical identity is the carried provider dimension population: kind, date, URL, grounding query, topic, intent, geography, country, region, market, and surface. Citation metrics are measurements, not identity.
- **GA4 AI-assistant referrals:** logical identity is assistant, date, source, medium, landing page, geography, country, region, and device category. Accepted assistant aliases are canonicalized before identity comparison. Sessions/users/events/revenue are measurements, not identity.
- **Unavailable states:** no observed rows are claimed, so record-identity population checking is a no-op after the upstream fail-closed boundary.

The validator composes `validate_connected_evidence_scope_semantics(...)` first. Ambiguous/blank required identity fields fail closed rather than being guessed.

## Current integration handoff

For later serialized integration, normalize each already-authorized provider payload/import and validate the **complete logical enrichment set** with `validate_connected_evidence_snapshot_bundle(...)`. The bundle composes `validate_connected_evidence_record_identity_semantics(...)` and all preceding Lane-D boundaries before applying canonical source/snapshot identity and cross-state coherence.

Connected evidence remains optional and separate from canonical crawl authority. This slice performs no network I/O, OAuth/account mutation, Base44 schema change, `run_scan` wiring, repair scoring, authority/persistence/customer projection, admission, release, deployment, or production mutation.

## Historical slice verification

`scanner-api/tests/test_connected_evidence_record_identity_contract.py` contains the deterministic regressions for this boundary. The slice was verified independently when introduced and has since been expanded. Historical slice totals are not the current exact-head integration gate.

For the authoritative exact-head pytest/`py_compile` gate and current focused-test count, use `docs/nextgen/lane-d-evidence-connectors.md` only.

No undocumented Google Generative AI API endpoint is introduced or assumed by this change.
