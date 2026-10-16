# Stage 2 B10/B17 producer extraction checkpoint — 2026-09-19

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

Verified code/test head: `78c4b09acabac7c811cdf55abbe82631f7e0dd68`

FixList CI: `35470835432` — **SUCCESS** on both jobs.

This checkpoint advances the remaining B10–B15/B17–B18 serialized producer slice without changing customer-visible repair authority, scoring, deployment, admission or production state.

## B10 — real accepted-main-text producer seam

`scanner-api/app/accepted_content_evidence.py` now emits `main_text_signature_v1` producer fields from the same accepted HTML already used by Standard 150 extraction:

- `main_text_evidence_version`
- `main_text_verified`
- `main_text_reason`
- `main_text_source`
- bounded `main_text`
- `main_text_char_count`
- `main_text_truncated`

The producer prefers an explicit `main`, `role=main` or `article` region. If none exists, it falls back to a cloned body with common chrome (`header`, `nav`, `footer`, `aside`) removed. The clone keeps this analysis independent of existing image/template/location extraction.

Only `usable_html` can produce verified substantive text. Empty or over-limit main text remains unverified. The evidence is bounded at 120,000 normalized characters and a truncated sample is not promoted as verified B10 content.

Because `extract_page` already spreads accepted-content evidence into each retained page, these fields now flow through the real Standard-150 page producer rather than only synthetic B10 helper fixtures.

## B17 — decoded and inline byte producer seam

The same accepted-response extraction now retains truthful page-weight inputs:

- `page_weight_evidence_version=page_weight_evidence_v1`
- decoded HTML UTF-8 byte count with explicit basis `utf8_of_decoded_html`
- inline script bytes, excluding external `src` scripts
- inline style bytes
- transfer bytes remain `None` / `unknown` until the hardened network path exposes a directly measured wire-body count

This intentionally does **not** infer transfer bytes from decoded HTML or from a synthetic zero. Optional CrUX remains disconnected unless separately authorized/current.

## Behavioral regressions

New `scanner-api/tests/test_stage2_extraction_producer_evidence.py` proves the real extraction seam:

1. accepted main text excludes shared navigation/footer chrome;
2. distinct substantive main content does not become a near-duplicate merely because chrome is shared;
3. genuinely similar substantive main text still clusters even when navigation differs;
4. unusable/403 HTML cannot become verified B10 main text;
5. decoded/inline byte evidence remains distinct from unknown transfer bytes.

The ordinary exact-head FixList CI succeeded at `78c4b09...`, including immutable checkout, root scanner regressions, full scanner-api tests, labelled Stage-1 synthetic corpus, frozen revision verification, production scanner image, lint, typecheck, generated contracts, frontend contracts and build.

## Requirement status after this checkpoint

- **B10:** real accepted-response main-text production is now implemented and CI verified; aggregate/customer repair wiring and authenticated downstream projection remain open.
- **B17:** decoded and inline byte production is implemented and CI verified; direct transfer-byte measurement and any authenticated customer projection remain open. CrUX remains optional/disconnected.
- **B11–B15/B18:** producer/shared integration remains open.

No new customer-displayed field was introduced by this checkpoint. Therefore no authority-schema or persisted-customer mutation was needed yet. Any future displayed B10/B17 evidence must still pass producer → Review → signed authority → persisted rows → verified customer/card/handoff/export regression coverage before Stage 2 can be source-complete.

No merge, deployment, worker promotion, admission mutation, live scan or production change is claimed.