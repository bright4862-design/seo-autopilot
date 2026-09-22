# Agent D — Evidence Connectors handoff

Issue: #325  
Draft PR: #332  
Integration base: `nextgen/integration-20260921`  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Lane boundary

This lane owns only pure, provider-neutral connected-evidence contracts, import/normalization helpers, sanitized fixtures, tests, and lane-local handoff documentation. It performs no network I/O, OAuth/account mutation, credential creation, Base44 schema change, authority/persistence write, customer projection, repair-priority change, `run_scan` orchestration, release, deployment, admission, or production mutation.

The common envelope is versioned as `connected_evidence_v1`. Every envelope carries provider, surface, method, source kind, retrieval/observation timestamps, sample/coverage disclosure, evidence-quality confidence, provenance, an explicit evidence state, and bounded records. States are `verified`, `stale`, `not_connected`, `not_supported`, `not_verified`, and `provider_error`. Connected evidence remains optional enrichment and never becomes canonical crawl authority.

This file is the **authoritative Lane-D integration handoff**. Per-slice hardening notes under `docs/nextgen/lane-d-*-hardening.md` are historical design/regression records only; they are not standalone integration gates or exact-head test manifests.

## Validation stack

Lane D exposes one strict pre-normalization import boundary plus seven post-normalization fail-closed validation boundaries.

0. `validate_connected_evidence_import_rows(...)` / `connected_evidence_import_shape_v1`, plus `parse_connected_evidence_import_csv(...)` / `connected_evidence_csv_shape_v1`
   - protects Bing AI Performance and GA4 manual/aggregate row imports before tolerant provider alias lookup;
   - rejects registered-header collisions after normalization or underscore-insensitive matching;
   - rejects conflicting non-empty values carried by multiple aliases for the same semantic field while allowing equivalent duplicates;
   - preserves unrelated provider/export columns instead of turning them into evidence fields;
   - strict CSV parsing rejects ragged rows instead of silently dropping overflow fields or accepting truncated rows;
   - caller-supplied CSV byte/row limits may tighten but cannot raise the lane's existing 5 MB / `MAX_IMPORT_ROWS` ceilings;
   - strict Bing/GA4 row and CSV entrypoints preflight imports before delegating to the existing pure provider normalizers.
1. `validate_connected_evidence(...)` / `connected_evidence_v1`
   - strict envelope shape, timestamps, state semantics, JSON bounds, evidence-quality confidence, and unavailable/stale invariants;
   - confidence metadata is closed-world and qualitative: only `kind`, `level`, and optional bounded `limitations` are accepted, and the level must be one of the registered non-probabilistic evidence-quality levels already emitted by Lane-D adapters;
   - unavailable states cannot carry records, `observed_at`, observational sample metadata, or coverage metadata.
2. `validate_connected_evidence_source_identity(...)` / `connected_evidence_source_profile_v1`
   - registered provider/source/surface/method/transport profiles and connector provenance;
   - provenance keys are allowlisted per registered provider/source profile so unversioned OAuth/API/credential claims cannot be smuggled into an otherwise valid envelope;
   - Search Console `sc-domain:` provenance must be a real DNS identity rather than an empty, IP-like, wildcard, scheme-bearing, or path-bearing token;
   - path-scoped GSC/Bing source identities reject malformed hosts and embedded URL userinfo before any later scope check;
   - URL Inspection provenance and record identity URLs reject embedded URL userinfo as well as malformed HTTP(S) ports;
   - ambiguous path-scoped GSC URL-prefix and Bing branch identities fail closed unless their non-root path uses the provider-style trailing `/` directory boundary.
3. `validate_connected_evidence_record_semantics(...)` / `connected_evidence_record_semantics_v1`
   - provider-specific record meaning: GSC metric relationships, URL Inspection URL/timestamp semantics, Bing kind/citation semantics, GA4 assistant/source spoof resistance, and GA4 metric relationships;
   - GA4 referral `source` host parsing rejects embedded URL userinfo before assistant-host classification;
   - `connected_evidence_record_shape_v1` makes each registered provider record closed-world at the field-name boundary.
4. `validate_connected_evidence_coverage_semantics(...)` / `connected_evidence_coverage_semantics_v1`
   - binds sample/coverage metadata to transported records and rejects forged counts, inconsistent import accounting, dimension drift, period contradictions, record dates later than observation, and dated coverage without the observation timestamp needed to support it;
   - GSC date-dimension evidence requires explicit coverage bounds; URL Inspection observed coverage requires `observed_at`; Bing/GA4 dated evidence requires `observed_at`, while deliberately date-less evidence with freshness disabled may remain genuinely unbounded.
5. `validate_connected_evidence_scope_semantics(...)` / `connected_evidence_scope_semantics_v1`
   - binds observed pages/landing paths to declared GSC, Bing, and GA4 source/property scopes;
   - GSC/Bing HTTP paths and GA4 landing-page paths fail closed on raw or percent-encoded dot-segment traversal, encoded `/` or `\\` separators, malformed percent escapes, control characters, raw backslashes, and semicolon path parameters.
6. `validate_connected_evidence_record_identity_semantics(...)` / `connected_evidence_record_identity_v1`
   - rejects duplicate logical provider rows even when transport row numbers or metrics differ;
   - accepted GA4 assistant aliases are canonicalized for identity;
   - GSC `page` dimensions and Bing cited-page URLs canonicalize harmless HTTP(S) representation aliases while preserving path/query identity.
7. `validate_connected_evidence_snapshot_bundle(...)` / `connected_evidence_snapshot_bundle_v1`
   - validates the bounded optional evidence set for one logical enrichment snapshot;
   - composes the full post-normalization chain for every item, canonicalizes source and observation/window identities, rejects duplicate/contradictory source-window observations, and rejects simultaneous observed/unavailable claims for one canonical source scope;
   - `connected_evidence_snapshot_window_coherence_v1` rejects overlapping **provable** observation windows for one semantic series. Date-less evidence does not get an invented start bound.

The producer fails closed before constructing an envelope when `retrieved_at` is not parseable. Bing and GA4 observation dates are accumulated only after row acceptance, so rejected rows cannot advance freshness.

## Safe-now adapters

- **Google Search Console Search Analytics:** `normalize_gsc_search_analytics(...)` accepts already-authorized `searchanalytics.query` response payloads and preserves dimensions, metrics, period coverage, and property provenance.
- **Google Search Console URL Inspection:** `normalize_google_url_inspection(...)` accepts already-authorized `urlInspection.index.inspect` payloads and preserves verdict/indexing/fetch/canonical/last-crawl/referrer/sitemap evidence without treating it as a guarantee of current search visibility.
- **Bing Webmaster Tools AI Performance:** low-level `normalize_bing_ai_performance_rows(...)` remains a pure translator for manual CSV/Excel-derived rows. Future manual/import integration should prefer `normalize_bing_ai_performance_import_rows(...)` or `normalize_bing_ai_performance_import_csv(...)`, which apply `connected_evidence_import_shape_v1` first. `api_used` is explicitly false; this lane does not claim that an AI Performance API exists.
- **GA4 AI-assistant referrals:** low-level `normalize_ga4_ai_referral_rows(...)` remains a pure aggregate-row translator. Future manual/import integration should prefer `normalize_ga4_ai_referral_import_rows(...)` or `normalize_ga4_ai_referral_import_csv(...)`, which fail closed on ambiguous provider aliases before normalization. Referral evidence proves observed traffic only; it does not prove all AI mentions/citations.
- **CSV import boundary:** bounded UTF-8 CSV parsing rejects oversized inputs, row sets, duplicate normalized headers, and ragged rows whose field count differs from the header. The strict import-shape layer additionally protects direct Excel-derived mappings and semantic aliases that CSV header normalization alone cannot disambiguate.

Freshness fails closed when freshness checking is enabled but the observation time cannot be established, parsed, or is later than retrieval. `stale_after_days=None` is the explicit opt-out from a freshness claim.

Sanitized fixtures live under `scanner-api/tests/fixtures_connected_evidence/`. Deterministic tests perform no live provider calls.

## Source, record, import and snapshot integrity notes

- Search Console `sc-domain:` properties accept DNS domain identities only; empty values, URL/scheme/path syntax, wildcard hosts, and IP literals fail closed at the source-profile boundary.
- Search Console URL-prefix and Bing path-scoped property identities reject URL userinfo and malformed host spellings before scope membership is evaluated.
- URL Inspection `provenance.inspection_url` and the carried record `inspection_url` reject URL userinfo before exact identity comparison.
- GA4 referral `source` values may use host or host-plus-medium spellings, but embedded URL userinfo is invalid evidence identity.
- Search Console URL-prefix and Bing path-scoped property identities use a trailing `/` directory boundary for non-root paths.
- Registered provenance is closed-world per provider/source profile. Current optional provenance is only `import_name` for Bing manual exports and GA4 provided rows.
- Evidence-quality confidence metadata is closed-world and non-probabilistic. Current registered levels are `none`, `provider_observed`, `first_party_provider_observed`, and `first_party_analytics_observed`.
- Registered provider record fields are closed-world under `connected_evidence_record_shape_v1`.
- Scope membership refuses ambiguous URL path forms whose meaning can change after ordinary URL normalization: raw/encoded dot segments, encoded path separators, raw backslashes, malformed escapes, controls, and semicolon path parameters.
- Search Analytics page-scope validation applies only when `page` is an observed dimension.
- URL Inspection `inspection_url` must belong to its declared Search Console property.
- Bing cited-page URLs must remain inside the declared site scope.
- GA4 property identities must be numeric (`properties/<id>` or bare numeric import form), and landing-page evidence must be root-relative and unambiguous; `(not set)` remains explicit unknown identity.
- Provider row numbers are transport positions, not semantic identities. Metrics are measurements, not identity fields.
- Strict import preflight treats recognized alias ambiguity as a data-integrity error instead of letting dictionary/header order decide which provider value wins. Unrelated extra export columns remain tolerated and are not promoted into normalized evidence records.
- Strict CSV import treats row/header cardinality as evidence integrity: extra fields are not silently discarded, truncated rows are not padded into apparently valid evidence, quoted commas remain valid CSV, and explicit empty trailing cells remain distinguishable from missing fields.
- GSC page/Bing URL identity canonicalization is intentionally narrow: it does not lowercase paths, drop queries, resolve redirects, or invent provider canonicals.
- Snapshot source identities canonicalize supported source aliases; dated Bing/GA4 evidence without an explicit start derives a conservative start only from accepted carried record dates.
- Snapshot window coherence treats provider periods as closed intervals when both bounds are provable. Date-less evidence remains unknown rather than having a start inferred from retrieval time.

## Unsupported / separately authorized future work

1. GSC live retrieval requires an existing owner-authorized Search Console connection and documented API operations. No OAuth client, scope, token, property access, or credential is created here.
2. URL Inspection live retrieval likewise requires existing owner authorization; this lane does not alter quotas or connection UI.
3. GA4 live retrieval may later use an owner-authorized reporting/Data API connection or explicit export import. This lane creates no Analytics access or credential.
4. Bing AI Performance remains manual/import evidence unless a separately verified official programmatic route is available and approved.
5. **No dedicated Google Generative-AI visibility/report API is assumed or implemented.** Do not invent undocumented endpoints.

## Serialized integrator hook

For any later authorized payload/import, the serialized integration layer must:

1. use the registered Lane-D adapter; for manual/Excel-derived Bing or GA4 rows, prefer the strict `*_import_rows` / `*_import_csv` entrypoints so alias ambiguity and malformed CSV row shape are rejected before normalization;
2. validate the complete logical enrichment set using `validate_connected_evidence_snapshot_bundle(...)`, which composes envelope → source identity → record semantics/closed-world record shape → coverage semantics → source/property scope → logical record identity, then applies canonical snapshot source/window identity, cross-state coherence, and provable observation-window overlap rejection;
3. only then attach evidence as optional connected evidence with provenance/coverage intact;
4. keep connected evidence separate from canonical crawl authority;
5. preserve Standard 150 behavior unchanged when connected evidence is absent.

Any later influence on page value, repair priority, authority, persistence, historical storage, customer projection, or `run_scan` belongs to the serialized integrator, not this lane.

## Verification

Focused suites on this lane now contain:

- `scanner-api/tests/test_connected_evidence.py`: **23 adapter tests**;
- `scanner-api/tests/test_connected_evidence_contract.py`: **27 generic contract tests**;
- `scanner-api/tests/test_connected_evidence_source_contract.py`: **17 source-profile tests**;
- `scanner-api/tests/test_connected_evidence_timestamp_hardening.py`: **2 timestamp-hardening tests**;
- `scanner-api/tests/test_connected_evidence_record_contract.py`: **19 record-semantics tests**;
- `scanner-api/tests/test_connected_evidence_record_shape_hardening.py`: **8 closed-world record-shape tests**;
- `scanner-api/tests/test_connected_evidence_coverage_contract.py`: **18 coverage-semantics tests**;
- `scanner-api/tests/test_connected_evidence_scope_contract.py`: **25 source/property-scope tests**;
- `scanner-api/tests/test_connected_evidence_record_identity_contract.py`: **12 logical-record-identity tests**;
- `scanner-api/tests/test_connected_evidence_bundle_contract.py`: **24 snapshot-bundle/full-chain tests**;
- `scanner-api/tests/test_connected_evidence_snapshot_observation_identity.py`: **6 snapshot-observation-identity tests**;
- `scanner-api/tests/test_connected_evidence_record_url_identity.py`: **4 URL-record-identity tests**;
- `scanner-api/tests/test_connected_evidence_prefix_provenance.py`: **4 path-prefix-provenance tests**;
- `scanner-api/tests/test_connected_evidence_provenance_shape.py`: **6 closed-world provenance-profile tests**;
- `scanner-api/tests/test_connected_evidence_ga4_landing_path_hardening.py`: **8 GA4 landing-path ambiguity tests**;
- `scanner-api/tests/test_connected_evidence_source_identity_hardening.py`: **11 source-identity hardening tests**;
- `scanner-api/tests/test_connected_evidence_snapshot_window_coherence.py`: **9 snapshot-window-coherence tests**;
- `scanner-api/tests/test_connected_evidence_import_contract.py`: **18 strict import-shape/CSV-shape tests**.

Expected focused total: **241 tests**.

Latest verified slice evidence in this runtime:

- strict import/CSV-shape hardening exercised **18/18** focused cases in a hermetic Python package: the prior alias-collision/conflict behaviors remained green; over-wide CSV rows failed closed instead of losing overflow fields; short rows failed closed instead of being padded; quoted commas and explicit empty trailing cells remained valid; byte/row bounds could be tightened but not raised above lane ceilings; and the GA4 strict CSV wrapper rejected malformed row shape before provider normalization;
- `python -m py_compile app/connected_evidence_import_contract.py tests/test_connected_evidence_import_contract.py` passed for the candidate code;
- the hermetic package stubbed only the already-existing low-level `connected_evidence` adapter dependency. Full repository-native exact-head certification is still required;
- GA4 source-host userinfo hardening previously exercised **3/3** focused logic cases;
- coverage/observation coherence previously exercised **18/18** focused cases;
- URL Inspection identity hardening previously exercised **3/3** focused cases;
- closed-world confidence metadata previously exercised the generic-contract suite **27/27** plus a **6/6** smoke slice;
- closed-world provider record shape previously exercised **8/8** intended behaviors;
- snapshot-window coherence previously exercised **9/9** intended behaviors;
- source-identity hardening previously passed **8/8**;
- closed-world provenance + GA4 landing-path hardening previously passed **14/14**;
- ambiguous scope-path hardening previously passed **6/6**;
- path-prefix provenance and URL-record identity hardening previously passed **4/4** each.

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_record_shape_hardening.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py tests/test_connected_evidence_prefix_provenance.py tests/test_connected_evidence_provenance_shape.py tests/test_connected_evidence_ga4_landing_path_hardening.py tests/test_connected_evidence_source_identity_hardening.py tests/test_connected_evidence_snapshot_window_coherence.py tests/test_connected_evidence_import_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_import_contract.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py app/connected_evidence_scope_contract.py app/connected_evidence_record_identity_contract.py app/connected_evidence_bundle_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_import_contract.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_record_shape_hardening.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py tests/test_connected_evidence_prefix_provenance.py tests/test_connected_evidence_provenance_shape.py tests/test_connected_evidence_ga4_landing_path_hardening.py tests/test_connected_evidence_source_identity_hardening.py tests/test_connected_evidence_snapshot_window_coherence.py`

Do not mark Lane D integration-ready until the exact-head **241-test** repository-native run is green and a fresh exact-head review has no unresolved material findings.

The full repository-native exact-head 241-test run is **not yet claimed green** in this runtime. PR #332 intentionally targets `nextgen/integration-20260921`; do not retarget the PR or alter release workflows merely to manufacture CI.

## Known risks / truthful unsupported states

- Connected evidence is optional enrichment, not crawl authority.
- Citation share is observational and is not a ranking, quality, or probability score.
- Search Console and Analytics freshness depends on provider/report windows; stale evidence remains explicitly labelled.
- Date-less GSC/Bing/GA4 evidence does not become fresh by assumption under the default freshness gate.
- GA4 referral classification cannot measure dark/direct AI traffic or uncited mentions.
- Bing/GA4 export columns can evolve; recognized alias contradictions fail closed while unrelated extra columns remain ignored by the normalization contract.
- Dedicated Google Gen-AI reporting remains unsupported/not verified until an official programmatic surface is established.
- Snapshot identities and window-coherence checks prevent ambiguous duplicate/overlapping observations inside one logical snapshot; they are not historical storage keys.
- Window overlap is enforced only when both bounds are provable; missing starts remain explicitly unknown rather than being inferred.
- Unavailable states deliberately do not retain observational count/window metadata.
- Any future envelope/profile/record/confidence/import metadata expansion should be versioned rather than silently accepted.

The lane changes **39 Lane-D-owned files**: eight handoff/hardening docs, nine pure app modules, eighteen focused test modules, and four sanitized fixtures. No serialized-integrator-owned surface is modified.

Rollback is lane-local: omit these pure modules/tests/docs from the serialized integration branch. No production state, credentials, schema, durable authority, or customer data requires reversal.