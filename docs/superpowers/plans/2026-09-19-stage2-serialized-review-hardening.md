# Stage 2 serialized integration review-hardening checkpoint — 2026-09-19

Integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

Exact reviewed code/test head before this documentation-only checkpoint: `f904649c9193877181471e1daa01097da0f3062b`.

Exact-head FixList CI: `35472567286` — **SUCCESS**.

## Verification

- immutable checkout: `f904649c9193877181471e1daa01097da0f3062b`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,911 passed / 18 intentional skips**;
- focused B10/B17 extraction suite: **5 passed**;
- focused Stage-2 review-hardening suite: **5 passed**;
- B08 redirect-meaning suite: **6 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision: `01ebe8e90df1e6bd` verified;
- production scanner image: build passed, image SHA `sha256:73902d7ee4728b41d0b26bc956ff51bd388320d40c439faaacd2735ff98b9f63`;
- lint, typecheck, generated release contracts, frontend contract tests and frontend production build: passed.

The workflow's Node setup resolved Node `20.20.2` on the runner. Do not describe this CI run as Node 20.19.5 exact-runtime evidence.

## Review findings fixed in this checkpoint

### Accepted image evidence and destructive sanitization

Image applicability is now reduced to scalar evidence before BeautifulSoup sanitization can `decompose()` hidden/example nodes. Hidden descendants are explicitly classified `excluded / hidden_or_example_content`; no later classification dereferences a decomposed tag.

Regression: `test_hidden_image_control_is_excluded_without_post_sanitize_node_access`.

### Empty main-landmark truthfulness

B10 main-content extraction and visible-template evidence now use explicit `is None` checks instead of BeautifulSoup Tag truthiness. An empty `<main></main>` remains the selected main landmark and cannot fall through to body/title text.

Regression: `test_b10_empty_main_landmark_does_not_fall_back_to_body_text`.

The corresponding CodeRabbit thread was replied to with exact-head CI evidence and resolved after the fix.

### Main-content privacy

The accepted B10 producer no longer places raw page copy into its compatibility field. It computes bounded SHA-256 five-token shingles and an aggregate signature; only the irreversible digest tokens plus token/character-count metadata leave the extraction helper.

Regression: `test_b10_extraction_publishes_only_irreversible_main_content_signature_material` asserts source words and shared chrome/footer copy do not survive.

The independent review thread remains deliberately open pending confirmation whether the hashed compatibility field itself must also be absent from final `pages`/`crawled_pages`. If required, the next serialized slice must compute B10 before response assembly and remove the transient compatibility material entirely rather than weakening the analysis.

### Redirect loop provenance

A diagnostic-only `redirect_loop` label with zero observed redirect hops is no longer treated as a verified destination defect. It remains `not_verified / redirect_loop_unverified`. A real loop with concrete hop provenance remains `verified_unusable / redirect_loop`.

Regressions cover both cases.

### Challenged/rate-limited redirect destinations

Redirect meaning checks normalized `access_block_kind` (`challenge`, `block`, `rate_limit`) before generic HTTP >=400 classification. A challenge response such as HTTP 403 stays `destination_access_unverified` and yields `redirect_destination_unverified`; an ordinary verified 404 remains `redirect_destination_unusable`.

Paired regressions cover the challenged 403 and ordinary 404 cases. The corresponding CodeRabbit thread was replied to and resolved after the fix.

## Current requirement status

Stage 2 is **not source-complete**.

Already integrated on this line: B06 scheduler/internal-link coverage, B07 active soft-404 orchestration/downstream proof, B08 redirect meaning, B09 sitemap evidence, B16 URL variants, and the B10–B15/B17–B18 lane helper contracts. Shared B07/B09/B16 producer wiring uses one existing `SharedCoverageProbeScheduler`; probe-only URLs remain outside Standard 150 assessed pages and the finite request/body/deadline/redirect/robots/SSRF boundaries remain authoritative.

Still open:

- **B10**: final publication-boundary decision for hashed compatibility material; authenticated customer projection only if the duplicate evidence becomes displayed.
- **B11**: stable sample-scoped crawl depth, inlink and navigation provenance; do not infer sitewide orphaning from an observed sample.
- **B12**: bounded paired raw/rendered hub-link evidence for up to five hubs, with completed/failed/unassessed states.
- **B13/B14**: applicable local entity/status/address/phone/regular-hours production plus verified entity-match/NAP provenance.
- **B15**: explicit current-content intent and current-scoped temporal anchors; an old date alone is not freshness failure.
- **B17**: direct transfer-byte measurement remains open; decoded HTML and inline script/style bytes are already separated. CrUX remains optional/disconnected unless actually authorized and current.
- **B18**: GSC remains optional with explicit disconnected/stale/unavailable states until a current owner-authorized response exists.
- Any new customer-visible B09/B10–B18 evidence/count/finding still requires real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export proof.

## Safety and release state

- Standard 150 assessed cap/denominators are unchanged by probe-only evidence.
- Unknown/challenged/robots/budget/deadline evidence remains unknown.
- Historical signatures/readers and preview privacy remain compatibility requirements.
- Python Review remains canonical decision/ranking authority.
- The genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic or historical summary evidence is not a substitute.
- No Stage-2 deployment, admission mutation, worker promotion, live scan, schema change, secret change or customer-data mutation occurred in this checkpoint.
- Stage 3 integration remains blocked on Stage-2 source completion + independent combined review + exact-head CI.