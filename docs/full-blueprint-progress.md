# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This file is the current requirement ledger. Older checkpoints remain available in Git history and the executable plan/handoff documents linked below; stale approval-blocker language is not current authority.

## Release sequencing

Stage 1 and the later blueprint remain separate release states.

- Stage-1 source was completed and merged before this later-stage integration line. Its exact-source production publication/promotion/non-owner live acceptance is a separate guarded operation and is **not** implied by later-stage CI.
- The later-stage integration branch is `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, change schema/secrets, or otherwise move production while the Stage-1 exact-source release operator still owns that cutover.
- After Stage-1 live acceptance is recorded, this integration line must reconcile onto the then-current accepted `main` without reverting V7 runtime/public-build changes or the durable ownership-before-admission fix, followed by fresh exact-head combined CI.

## Stage 1 — source complete; live release acceptance is separate

Stage-1 implementation established the published-route evidence identity, authenticated authority/persistence/readers, image/template/search-evidence correctness, historical signature compatibility, preview privacy, and the named synthetic acceptance runner. The synthetic corpus remains explicitly synthetic and is not the genuine 30-site full-blueprint gate.

Historical Stage-1 acceptance detail: `docs/stage-one-evidence-acceptance.md`.

The frozen scanner revision checked by current later-stage CI remains `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 integration in progress

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated lane PRs are review/CI lanes only and must not be merged directly to `main`.

### Integrated and materially wired

- **B06 — shared bounded coverage scheduler/internal-link verification.** One finite follow-up scheduler reuses the hardened robots/DNS/SSRF/redirect/body/deadline request path. Probe-only URLs do not enter the Standard 150 assessed-page set or denominator. Verified unsampled broken-link evidence has authenticated producer → Review → authority → persistence → customer-output coverage.
- **B07 — active soft-404 evidence/orchestration.** Deterministic same-origin/effective-scope missing-page candidates use the shared finite scheduler. Challenge/429/robots/budget/deadline/incomplete outcomes remain unknown. Synthetic probes remain outside assessed pages. Versioned active evidence is kept separate from historical/passive heuristic evidence and has downstream signed/persisted/customer coverage.
- **B08 — redirect meaning.** Harmless normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access are distinct. A diagnostic-only loop without concrete hops is unverified; an observed loop with hop provenance is unusable. Challenge/block/rate-limit destinations remain unknown even when the HTTP response is 403/429/503; an ordinary verified 404 remains unusable.
- **B09 — sitemap integrity helper/probe integration.** Same-origin/in-scope unsampled targets reuse the shared scheduler; candidate-universe truncation and access/budget uncertainty remain explicit. Exact source-level sitemap provenance enrichment and any customer-visible promotion still require the serialized producer/customer path.
- **B16 — URL variants.** Exact path/query/case/reserved-escape/empty-query identity is retained. No implicit sibling-host expansion occurs. Live alternate routes are not declared duplicates without independent equivalence evidence. Redirect meaning is delegated to B08.
- **B10 — accepted main-content producer seam.** Accepted usable HTML prefers `main`, `role=main`, then `article`; body fallback strips common chrome on a clone. Empty landmarks remain landmarks. Raw customer copy is not retained in the compatibility evidence: the producer emits bounded deterministic SHA-256 five-token shingle fingerprints plus aggregate signature/token/character-count metadata. CodeRabbit independently confirmed the raw-copy exposure is addressed and resolved the review thread. These fingerprints are not described as secret against candidate-text dictionary matching.
- **B11 — truthful sample-scoped reachability producer wiring.** Versioned B11 evidence reaches the retained assessed page set after the final Standard-150 cap. Accepted raw HTML temporarily retains only exact target URL + semantic navigation state, then a bounded post-cap adapter creates edges only where both source and target are retained assessed pages. Sources are re-gated as accepted usable HTML; sitemap discovery never creates inlinks/depth; unsampled targets never expand `pages`; exact path/query/case/reserved-escape identity is preserved; and `sitewide_orphan_claim` is always false. The private `_reachability_links` cache is removed unconditionally before scan result persistence/customer projection. No second request scheduler/budget is created. Exact producer CI is green; fresh independent review of the retained-link hook remains open.
- **B12 partial — paired raw/rendered hub evidence seam.** `run_render_followup` now carries a versioned `hub_link_comparison` produced from B11 retained-page provenance plus only the pre-existing bounded browser-followup observations. It selects at most five verified structural hubs, separately reports the full eligible count and selection truncation, and exposes completed/failed/unassessed rows. Missing renderer link collections are failed/unavailable rather than empty success; B11-truncated source samples fail closed instead of inventing raw-link absence; unsampled rendered links cannot expand the Standard-150 set; path/query/case/reserved escapes and explicit empty-query identity are preserved; and new B12 renderer-failure provenance uses a normalized reason rather than duplicating raw exception text. The existing renderer call ceiling remains three; B12 adds no renderer request or second request budget. **B12 is not closed yet:** the shared `run_scan` caller currently passes the retained page set to `run_render_followup` only when material rendering risk was already detected, so scans outside that rendering policy do not yet disclose otherwise eligible hubs as selected/unassessed. That caller integration gap must be fixed before B12 is source-complete.
- **B17 partial — truthful decoded/inline page weight.** Decoded HTML bytes and inline script/style bytes are separately measured from accepted content. Transfer/wire bytes remain `unknown`; decoded size or zero is never substituted for network transfer bytes.

Shared B07/B09/B16 integration checkpoint: `ca70b7380011e93437fc993185e511a5847618e6`, Stage2IntegrationRun `35469815094`.

### Current B12 executable checkpoint

Exact executable head: `e3155ae722631189f338f7bd76225a5e35950bf5`.

FixList CI `35480882511` — **SUCCESS** on both jobs for that exact head:

- immutable checkout passed;
- root scanner regression suite passed;
- full scanner-api suite passed, including **7 new B12 behavioral regressions**;
- labelled Stage-1 synthetic corpus verification passed and remains synthetic-only;
- frozen scanner revision verification passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

The B12 regressions cover: five-hub bounded/family-diverse selection and eligible-count truncation; exact query/case/reserved-escape identity; explicit empty-query identity; fail-closed B11 source-sample truncation; absent rendered-link collections; reuse of the existing three-page browser budget with completed/failed/unassessed disclosure; and the no-renderer unassessed state. The browser-failure case also proves the new B12 evidence does not copy raw renderer exception detail.

Detailed B12 checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`.

### B11 verification history

B11 retained-set producer hook exact head `f51869adf8eac44de4fa7c9387590ab3c330c5a9` passed FixList CI `35478073142` with **115 root passed**, **1,924 scanner-api passed / 18 skips**, the labelled synthetic Stage-1 corpus, frozen revision, production scanner-image build, lint, typecheck, generated contracts, frontend contract tests and production frontend build.

Before that, semantic navigation context exact head `0b657afad65bf6c9aef883de11fd23093c6a1f90` exposed one compatibility assertion that had not yet included `navigation_presence`: the B11 suites passed while scanner-api ended **1 failed, 1,920 passed, 18 skipped**. The assertion was strengthened rather than weakened, and exact head `c26a0495162359a6af72de0371ea33207e6df505` then passed CI `35475725233` with **115 root passed** and **1,921 scanner-api passed / 18 skips**.

A focused CodeRabbit review reported no correctness defect in the semantic-link checkpoint and confirmed semantic-only navigation evidence, exact URL identity, sitemap/inlink separation, exclusion of challenged/failed/truncated source pages, and `sitewide_orphan_claim=false`. A new review request now targets the retained-link hook together with the B12 exact head; do not mark that independent review passed until a current review response is recorded.

Detailed B11 checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`.

### Prior exact reviewed code/test checkpoint

Exact code head before B11 work: `f904649c9193877181471e1daa01097da0f3062b`.

FixList CI `35472567286` passed both jobs on that exact code head with **115 root scanner tests** and **1,911 scanner-api tests / 18 intentional skips**, plus the labelled synthetic Stage-1 corpus, frozen revision, production scanner-image build, lint, typecheck, generated release contracts, frontend contract tests and production frontend build.

Fresh independent-review findings corrected before that green run:

1. accepted-image applicability is reduced to scalar evidence before BeautifulSoup sanitization/decomposition;
2. empty `main`/body tags use explicit `is None` selection rather than truthiness fallback;
3. raw B10 page text is replaced by deterministic cryptographic fingerprint shingles/signature metadata;
4. zero-hop diagnostic redirect loops remain unverified while concrete loops remain unusable;
5. access-block/challenge/rate-limit evidence is evaluated before generic HTTP error classification.

CodeRabbit independently confirmed and resolved the reported B10 empty-landmark, B10 raw-copy, and B08 access-block threads after the exact-head fixes.

Detailed prior hardening checkpoint: `docs/superpowers/plans/2026-09-19-stage2-serialized-review-hardening.md`.

### Stage 2 still open

Stage 2 is **not source-complete**. Remaining serialized requirements:

- **B10:** if duplicate evidence becomes customer-visible, add authenticated Review → authority → persistence → customer/card/handoff/export coverage before closing displayed behavior.
- **B11:** producer/source wiring is implemented and exact-head CI green. Fresh independent review of the retained-link hook remains a gate. No customer-facing B11 repair/card is introduced by this slice; if B11 source URL samples become persisted/previewed/exported downstream, add bounded authenticated entitlement/privacy coverage before closing that display behavior.
- **B12:** exact paired-evidence adapter and existing browser-followup seam are CI green. Fix the shared `run_scan` caller so eligible retained hubs are still disclosed as selected/unassessed when the explicit rendering policy declines browser execution, while keeping actual renderer calls under the existing bounded policy. Resolve fresh independent review. No customer repair/card is introduced by B12 yet.
- **B13/B14:** produce applicable local entity/status/address/phone/regular-hours evidence and verified entity-match/NAP provenance. Optional fields remain optional and Coming Soon/unknown applicability fails closed.
- **B15:** produce explicit current-content intent plus current-scoped temporal evidence. An old date alone is not freshness failure.
- **B17:** add directly measured transfer-byte evidence without confusing it with decoded bytes. CrUX remains optional and must expose disconnected/stale/unavailable states unless a current authorized response actually exists.
- **B18:** GSC remains optional with explicit disconnected/stale/unavailable behavior unless a current owner-authorized response exists.
- **B09:** exact sitemap root/child provenance and exact child failure reasons must be retained if promoted into displayed findings.
- Any newly displayed B09/B10–B18 evidence/count/finding requires real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage before the requirement can close.
- Final combined independent review plus a fresh exact-head CI after the remaining shared wiring are mandatory before Stage 3 integration.

## Stage 3 — isolated lanes built; integration held behind Stage 2

The existing lane work is implementation input only until Stage 2 closes.

- `agent/stage3-b19-b20-decisions-20260919`: B19 exact **impact × reach × page value × confidence** factor evidence/explanations and B20 explicit evidenced shared root causes across SEO/GEO. Family similarity alone is not root-cause proof. Exact lane head `e74d87acd0cec2955402b96f635f13bc275f3a91` previously passed its lane CI.
- `agent/stage3-b21-b24-delivery-20260919`: B21 exact unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 explicit evidenced root-cause score caps preserving existing ceilings; B24 backward-compatible handoff v2. The lane is integration-ready, not source-complete.

Do not integrate B19–B24 into shared ranking/authority/customer interfaces until Stage 2 is source-complete, independently reviewed and exact-head green. Python Review remains the canonical ranking authority.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` contains isolated B25–B28 compatibility/acceptance/release-preparation work. It does not constitute release authorization or live acceptance.

Spec numbering controls:

- **B25:** named synthetic corpus plus a genuine provenance-labelled 30-site baseline/candidate gate. Historical summaries and synthetic fixtures cannot satisfy the real gate.
- **B26:** reproduced own-site serving defects/fixes with source evidence; deployed HTTP behavior must be verified only on the exact eventual release.
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility for new evidence while original historical signatures remain readable and unknown versions fail closed.
- **B28:** exact-source review/CI/deployment/live acceptance, including runtime identities, rollback, one bounded real customer Standard-150 submit → persistence → exact `scan_id` reload/history → linked rescan verification.

The genuine 30-site baseline/candidate gate is currently **not assessed**. No Stage-4 deployment, live scan or production claim is authorized by an isolated lane CI result.

## Hard invariants for all remaining work

- Standard 150 assessed-page cap and truthful denominators remain authoritative.
- Stage-2 follow-up checks share one finite request pool; no second scheduler/budget.
- Existing robots ownership, DNS/SSRF, redirect, decoded-body and deadline protections remain authoritative.
- One active scan/account, cancellation/terminalization and exact scan isolation remain intact.
- Missing, blocked, stale, disconnected or invalid evidence remains unknown rather than a pass/fail invention.
- Historical signatures/readers stay byte/read compatible; unknown new versions fail closed.
- Preview privacy and entitlement boundaries remain intact.
- Python Review remains the canonical priority/ranking authority.
- Premium/Grok remain outside this blueprint integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or a real customer live acceptance.

## Exact next engineering action

Remain on Stage 2. First close the B12 shared-caller gap: the final retained page set must be available to the B12 disclosure builder even when the explicit rendering resource policy chooses not to execute a browser render, while browser calls themselves remain bounded by the existing policy and no second budget is created. Resolve the current independent review request for B11/B12. Then continue B13–B15/B17 transfer/B18 in serialized slices, adding authenticated downstream coverage for anything customer-visible. Require exact-head FixList CI and independent review at meaningful combined checkpoints. Only then begin shared Stage-3 integration.