# Agent D — Evidence Connectors handoff

Issue: #325  
Draft PR: #332  
Integration base: `nextgen/integration-20260921`  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Lane boundary

This lane owns only pure, provider-neutral connected-evidence contracts, import/normalization helpers, sanitized fixtures, and tests. It performs no network I/O, OAuth/account mutation, Base44 schema change, authority/persistence write, customer projection, repair-priority change, `run_scan` orchestration, release, deployment, admission, or production mutation.

The common envelope is versioned as `connected_evidence_v1`. Every envelope carries provider, surface, method, source kind, retrieval/observation timestamps, sample/coverage disclosure, evidence-quality confidence, provenance, explicit state, and bounded records. States are `verified`, `stale`, `not_connected`, `not_supported`, `not_verified`, and `provider_error`. Connected evidence remains optional enrichment and never becomes canonical crawl authority.

## Validation stack

Lane D now exposes four pure fail-closed validation boundaries.

1. `validate_connected_evidence(...)` / `connected_evidence_v1`
   - strict envelope shape, timestamps, state semantics, JSON bounds, confidence semantics and unavailable/stale invariants.
2. `validate_connected_evidence_source_identity(...)` / `connected_evidence_source_profile_v1`
   - exact registered provider/source/surface/method/transport profiles, connector provenance, strict boolean provenance, URL Inspection identities, Bing same-host evidence and invalid-port rejection.
3. `validate_connected_evidence_record_semantics(...)` / `connected_evidence_record_semantics_v1`
   - provider-specific record meaning: GSC metric relationships and row identity, URL Inspection URL/timestamp semantics, Bing kind/citation semantics, GA4 assistant/source spoof resistance and metric semantics.
4. `validate_connected_evidence_coverage_semantics(...)` / `connected_evidence_coverage_semantics_v1`
   - binds sample/coverage metadata to the records actually carried by the envelope. It rejects forged row/URL counts, inconsistent import accounting, dimension-population drift, period/observation contradictions, and record dates later than the stated observation time.

The producer itself fails closed before constructing an envelope when `retrieved_at` is not parseable. Timestamp parsing validates the full input rather than truncating malformed timestamp suffixes. Bing and GA4 observation dates are accumulated only after row acceptance, so rejected rows cannot advance freshness.

## Safe-now adapters

- **Google Search Console Search Analytics:** `normalize_gsc_search_analytics(...)` normalizes already-authorized `searchanalytics.query` response payloads and preserves dimensions, metrics, period coverage and property provenance.
- **Google Search Console URL Inspection:** `normalize_google_url_inspection(...)` normalizes already-authorized `urlInspection.index.inspect` payloads and preserves verdict/indexing/fetch/canonical/last-crawl/referrer/sitemap evidence without treating it as a guarantee of current search visibility.
- **Bing Webmaster Tools AI Performance:** `normalize_bing_ai_performance_rows(...)` and the CSV wrapper accept manual CSV/Excel-derived rows only. `api_used` is explicitly false; this lane does not claim that an AI Performance API exists.
- **GA4 AI-assistant referrals:** `normalize_ga4_ai_referral_rows(...)` and the CSV wrapper normalize aggregate referral rows for recognized assistant hosts. Referral evidence proves observed traffic only; it does not prove all AI mentions/citations.
- **CSV import boundary:** bounded UTF-8 CSV parsing rejects oversized files/row sets and duplicate normalized headers.

Freshness fails closed whenever freshness checking is enabled but the provider observation time cannot be established, parsed, or is later than retrieval. `stale_after_days=None` is the explicit opt-out from making a freshness claim.

Sanitized fixtures live under `scanner-api/tests/fixtures_connected_evidence/`. No deterministic test performs a live provider call.

## Unsupported / separately authorized future work

1. GSC live retrieval requires an existing owner-authorized Search Console connection and documented API operations. No OAuth client, scope, token, property access or credential is created here.
2. URL Inspection live retrieval likewise requires existing owner authorization; this lane does not alter quotas or connection UI.
3. GA4 live retrieval may later use an owner-authorized reporting/Data API connection or explicit export import. This lane creates no Analytics access or credential.
4. Bing AI Performance remains manual/import evidence unless a separately verified official programmatic route is available and approved.
5. **No dedicated Google Generative-AI visibility/report API is assumed or implemented.** Do not invent undocumented endpoints.

## Serialized integrator hook

For any later authorized payload/import, the integration layer must:

1. normalize with the registered Lane-D adapter;
2. run `validate_connected_evidence(...)`;
3. run `validate_connected_evidence_source_identity(...)`;
4. run `validate_connected_evidence_record_semantics(...)`;
5. run `validate_connected_evidence_coverage_semantics(...)`;
6. only then attach the evidence as optional connected evidence with provenance/coverage intact;
7. keep connected evidence separate from canonical crawl authority;
8. preserve Standard 150 behavior unchanged when connected evidence is absent.

Any later influence on page value, repair priority, authority, persistence or customer projection belongs to the serialized integrator, not this lane.

## Verification

Focused suites on this lane now contain:

- `scanner-api/tests/test_connected_evidence.py`: **23 adapter tests**;
- `scanner-api/tests/test_connected_evidence_contract.py`: **24 generic contract tests**;
- `scanner-api/tests/test_connected_evidence_source_contract.py`: **17 source-profile tests**;
- `scanner-api/tests/test_connected_evidence_timestamp_hardening.py`: **2 timestamp-hardening tests**;
- `scanner-api/tests/test_connected_evidence_record_contract.py`: **15 record-semantics tests**;
- `scanner-api/tests/test_connected_evidence_coverage_contract.py`: **13 coverage-semantics tests**.

Expected focused total: **94 tests**.

The latest coverage/accounting slice passed **13/13** in a hermetic pure-function harness with the already-tested upstream record-semantic validator stubbed as pass-through. `py_compile` for the new coverage module/test also passed. These are slice checks only, not branch-native repository certification.

Previously executed repository checkpoint:

- `PYTHONPATH=. pytest -q tests/test_connected_evidence_contract.py` → **24 passed**;
- `python -m py_compile app/connected_evidence_contract.py` → passed.

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py`

Do not mark Lane D integration-ready until the exact-head 94-test run is green and a fresh exact-head review has no unresolved material findings.

## Known risks / truthful unsupported states

- Connected evidence is optional enrichment, not crawl authority.
- Citation share is observational and is not a ranking, quality or probability score.
- Search Console and Analytics freshness depends on provider/report windows; stale evidence remains explicitly labelled.
- Date-less GSC/Bing/GA4 evidence does not become fresh by assumption under the default freshness gate.
- GA4 referral classification cannot measure dark/direct AI traffic or uncited mentions.
- Bing export columns can evolve; unknown/contradictory rows fail closed rather than being guessed.
- Dedicated Google Gen-AI reporting remains unsupported/not verified until an official programmatic surface is established.
- Any future envelope/profile metadata expansion should be versioned rather than silently accepted.

Rollback is lane-local: omit these pure modules/tests/docs from the serialized integration branch. No production state, credentials, schema, durable authority or customer data requires reversal.
