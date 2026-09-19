# Stage 2 B10-B15/B17-B18 coverage-evidence lane

Branch: `agent/stage2-b10-b18-acceptance-20260919`
Base: Stage-2 PR head `b05fe3993422357959c7755a2eda47a2e635943f`

This lane deliberately does not edit `run_scan`, the shared coverage scheduler, redirect meaning, sitemap probes, URL-variant probes, authority writers, or customer projections. It provides bounded feature helpers and behavioral contracts for the integration owner to wire through those shared seams serially.

## Implemented helper contracts

- **B10 near duplicates:** `near_duplicate_main_content` accepts only `usable_html` pages carrying the explicit `main_text_signature_v1` marker and `main_text_verified=true`. It hashes bounded five-word shingles from supplied main text, retains signatures/URL samples rather than copied body text, and cannot use common navigation/footer text unless a producer incorrectly labels that text as main content. Missing verified main text remains `not_verified`.
- **B11 money-page reachability:** `money_page_reachability` reports observed incoming source pages, crawl depth and optional navigation presence for classified money-page families. The result is explicitly scoped to `observed_standard150_sample_only`; weak evidence is never described as sitewide orphaning.
- **B12 raw/rendered hub links:** `compare_raw_rendered_hub_links` accepts at most five selected pairs, compares links only when both raw and rendered evidence succeeded, and discloses selected/completed/failed/unassessed counts. A failed render is `not_verified`, not proof of missing links.
- **B13 local completeness/shell applicability:** `assess_local_entity_completeness` requires applicability + accepted evidence before evaluating name/address/phone/regular hours. Holiday hours, photos, sameAs and parent entities are retained only as optional availability; their absence is not a defect.
- **B14 NAP consistency:** `assess_nap_consistency` compares only provenance-bearing observations with `entity_match=verified`. Ambiguous/unverified entity matches are counted but cannot create a contradiction. Name/address/phone comparisons are normalized independently from page URL identity.
- **B15 contextual freshness:** `assess_contextual_freshness` requires explicit current-content intent evidence plus a date whose scope is explicitly `current`. Historical/archive dates alone are not applicable. Missing temporal evidence remains unknown.
- **B17 page weight/CrUX:** `page_weight_evidence` keeps measured transfer bytes separate from decoded bytes and inline script/style bytes. If wire length was not measured, even a supplied numeric zero is reported as unknown. The optional CrUX adapter labels disconnected, unavailable, stale and connected evidence with provider/scope/time metadata; HTML size is never substituted for field performance.
- **B18 optional GSC:** `optional_gsc_adapter` labels disconnected/unavailable/stale states without fabricating metrics. Connected observations retain only bounded page metrics/index state; arbitrary query payloads are not retained.

## Behavioral regression file

`scanner-api/tests/test_stage2_coverage_evidence.py` covers:

1. substantive near-duplicate clustering from verified main text and exclusion of unverified text;
2. unknown duplicate coverage when verified main text is absent;
3. sample-qualified money-page reachability wording/state;
4. raw/rendered five-hub selection accounting and render-failure unknown semantics;
5. required local fields versus optional holiday/photo/schema-adjacent fields;
6. verified-versus-ambiguous NAP entity matching;
7. archived-date non-applicability and current-intent temporal contradiction;
8. unknown wire length versus measured/decoded/inline byte values;
9. CrUX disconnected/stale/connected behavior;
10. GSC disconnected/stale/connected behavior and bounded retained fields.

## Shared-wiring gaps for the integration owner

These are concrete producer/integration gaps, not claims that the requirements are complete:

- **B10:** `extract_page` does not yet retain a sanitized main-text signature input/marker for this analyzer. Integration should derive main text from accepted content evidence, not full-page `soup.get_text()` chrome, and must authenticate any customer-displayed cluster/count fields.
- **B11:** existing pages retain `source_pages`, but a stable crawl-depth field and explicit navigation-presence provenance are not yet guaranteed on every accepted page. Integration must preserve sample scope in any finding text/counts.
- **B12:** the scanner does not yet produce the bounded five-hub paired raw/rendered input contract. Selection/resource policy belongs in serialized orchestration; this lane intentionally performs no rendering/network I/O.
- **B13/B14:** existing GEO evidence observes limited semantic entity details, but the full applicable address/phone/regular-hours/store-detail observation envelope and cross-surface verified entity key are not yet produced. Integration must not treat optional holiday hours/photos/sameAs/parent entities as universal defects.
- **B15:** no current-intent + scoped temporal producer is wired yet. The analyzer requires both and deliberately cannot infer staleness from an old year alone.
- **B17:** `extract_page` currently exposes decoded `html_size`; transfer bytes and inline script/style sizes need explicit measurement at the accepted-response seam. Unknown Content-Length/wire size must stay unknown. CrUX connection/configuration is not created by this lane.
- **B18:** no owner-authorized GSC connection is created by this lane. Integration may pass a current authorized response into the adapter; disconnected/stale/unavailable must remain explicit and non-blocking.

## Acceptance status after this lane

These helpers make B10-B15/B17-B18 **integration-ready, not source-complete**. No customer-visible report, authority seal, persistence row, score, preview, export, live scan or provider connection changes on this branch solely because these files exist. Source completion requires producer wiring, authenticated downstream projection for any displayed fields, combined regressions, independent review and exact-head CI on the integrated Stage-2 branch.

Safety preserved: Standard 150 assessed-page cap, robots/DNS/SSRF/redirect/body/deadline controls, historical signatures, durable admission/cancellation, preview privacy and provider authorization remain untouched.
