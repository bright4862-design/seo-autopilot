# FixList 50-site production audit - Claude Code handoff

Date: 2026-08-21 (Europe/Paris)

## Executive verdict

Do not treat the current production build as beta-release evidence yet.

The product successfully created authoritative FixLists for 30 of 50 requested sites and never exceeded the 150-page cap. The visual hierarchy and plain-English repair cards are promising, and no image, script, document, font, or other asset URL was promoted as a page-level FixItem in the completed matrix.

However, only 2 of the 30 completed FixLists passed the full reliability-and-clarity review without a material qualification. The main release blockers are authority truthfulness, release-marker disagreement, internally impossible evidence counts, classification accuracy, duplicated/overstated repairs, and customer-facing status/priority copy that disagrees with durable state.

The production audit changed no source code or deployment. It submitted the 50 requested scans and used the owner stop control only for two vanished workers so the single-scan queue could continue.

## Production baseline

- Repository: `bright4862-design/seo-autopilot`
- Main/deployed source observed: PR #152 merge commit `1eb20072095dd182fb41e276e57050eee071bd50`
- Published custom-domain bundle observed at audit start: `index-B9PMsbn4.js`
- Base44 preview bundle observed at audit start: `index-C9EGhomR.js`
- Published product: `https://getfixlist.com/`
- Base44 app ID: `6a498732ec779dfaaeab0e53`
- Active Standard 150 worker: `fixlist-standard150-worker` / revision `fixlist-standard150-worker-00030-fj6`
- Legacy public scanner service: `seo-autopilot-4545` / revision `seo-autopilot-4545-eddf450-b8301297`

Authenticated `/health` and `/revision` on the active Standard 150 worker at the end of the audit:

- scanner: `python_scanner_v3_bounded_request`
- scanner build: `authenticated_health_probe_v1`
- review: `python_review_v2_structural_marketplace`
- classifier: `archetype_classifier_v9_local_business_hospitality`
- fingerprint: `03dbfa67f4b708cf`
- source SHA: `1eb20072095dd182fb41e276e57050eee071bd50`

Every one of the 30 completed authoritative ScanRuns consistently persisted:

- durable fingerprint: `03dbfa67f4b708cf`
- `release_gate_eligible: true`

The unauthenticated legacy `seo-autopilot-4545` service still reports the older fingerprint `51c813a6219b4e70`. That is an operational topology/observability problem, not evidence that the active Standard 150 worker falsely sealed the 30 audited scans.

## Quantitative result

| Gate | Result | Verdict |
|---|---:|---|
| Sites submitted | 50/50 | Complete |
| Completed FixLists | 30/50 (60.0%) | Too low for a broad beta matrix |
| Failed or cancelled | 20/50 (40.0%) | 15 access-limited; 5 worker/save failures |
| Completed scans over 150 pages | 0/30 | Pass |
| Completed scans using fallback | 0/30 observed | Pass |
| Completed scans marked authoritative/release eligible | 30/30 | Mechanically consistent, substantively unsafe |
| Conclusive classification cases | 27/50 | 23 access/coverage-inconclusive controls |
| Strictly correct classifications | 18/27 (66.7%) | Fail |
| Wrong classifications | 8/27 (29.6%) | Fail |
| Partial classification | 1/27 (3.7%) | Needs refinement |
| Clean result-quality passes | 2/30 (6.7%) | Fail |
| Mixed completed results | 17/30 (56.7%) | Needs correction |
| Failed completed results | 11/30 (36.7%) | Fail |
| Asset URLs promoted as page-level FixItems | 0 observed | Pass |

The two clean result-quality passes were Cambridge Wine and Spendesk. A "mixed" result can contain useful technical evidence but also contains a material classification, denominator, duplication, authority, representative-page, or UI truthfulness problem.

## Release blockers, in priority order

### P1 - Release topology and source constants expose two different contracts

The actual Standard 150 worker and all 30 completed ScanRuns agree on `03dbfa67f4b708cf`. The originally inspected public `seo-autopilot-4545` endpoint is a separate legacy service still serving `51c813a6219b4e70` from an August 5 revision. This creates a misleading production-health surface.

The current source also contains both contracts: durable/front-end/customer-result paths use `03db...`, while legacy `aiReviewScan`, `persistScanAuthority`, and Grok authority paths still contain `51c...`. The audited asynchronous Standard 150 path uses the newer durable authority flow, so its sealed rows are internally consistent; the unused or alternate paths remain a latent mixed-contract risk.

Required behavior:

- one canonical fingerprint source for each release and generated consumers rather than copied literals;
- clearly retire, rename, or update the legacy public scanner service so monitoring cannot probe the wrong release surface;
- document the active Standard 150 worker as the authoritative health/revision target and provide an authenticated monitoring probe;
- `release_gate_eligible` must be false when any exact component marker or fingerprint differs;
- no silent replacement with an older or frontend-local fingerprint;
- an executable production-contract test must compare live health/revision with a newly persisted ScanRun.

### P0 - Materially thin crawls are authoritative

Three controls demonstrate that coverage truthfulness is not safe:

- Tanners: 38 of 3,689 discovered URLs (1.0%), status complete, non-provisional, authoritative, release eligible.
- Decathlon: 40 of 1,374 discovered URLs (2.9%), status complete, non-provisional, authoritative, release eligible, score 79.
- Habito: only one page discovered and crawled on a real multi-page site, status complete, non-provisional, authoritative, release eligible, score 85.

The current severe-under-coverage rule requires fewer than 20 received pages, so it misses 38/3,689 and 40/1,374. It also cannot identify false "one-page site" discovery when discovery itself is blocked.

Required behavior:

- use a scanner-owned coverage contract containing the positively discovered
  target, attempted/claimed count, retained unique HTML count, and terminal
  reason; ratio alone cannot distinguish a valid 150/5,000 Standard sample
  from a crawl that stopped at 38 pages;
- as a tactical fail-closed gate, treat fewer than 50 retained pages and less
  than 10% coverage on inventories of at least 100 as insufficient, while
  retaining 150/5,000 and 21/172 as controls;
- separately detect suspicious one/default-route-only discovery using positive
  sitemap or inventory proof, navigation, redirect, render, and sitemap-failure
  evidence;
- mark materially limited results provisional and ineligible;
- prevent a high score or classification-validation credit when coverage is insufficient.

Hands-on source reproduction at the PR #152 commit confirmed the full local
review currently returns `complete`, non-provisional, and release-eligible for
synthetic 38/3,689, 40/1,374, and a false one-page case whose sitemap failed.
Changing only the Python gate would currently turn these into generic failed
scans. A useful provisional FixList needs a distinct limited-result integrity,
persistence, and customer-read path rather than an authoritative seal.

### P0 - Mixed-family findings produce impossible evidence denominators

20 of 30 completed FixLists contained `potential_orphan_pages`. The recurring customer output assigns a mixed set of URLs to the representative URL's family-usually Homepage-and then compares the full affected set against that tiny family denominator.

Examples:

- Wecandoo: 127/126 affected versus 1 homepage.
- Airbnb: 126 affected versus 1 homepage.
- N26: 69 affected versus 5 homepage pages.
- Mojo Mortgages: 66 affected versus 1 homepage.
- Castorama: 79 affected versus 1 homepage.
- Pretto: 35 affected loan pages versus 30 eligible loan pages.
- Meilleurtaux: 47 access-limited loan pages versus 6 eligible, and 22 failed loan pages versus 6 eligible.

Confirmed source path:

- `scanner-api/app/navigation_indexability.py:164-197,201-230` creates a
  cross-family orphan group through the generic finding constructor with an
  empty URL.
- `scanner-api/app/scanner.py:1175-1199` classifies that empty URL, and
  `scanner-api/app/extract.py:442-453` returns `homepage`; the finding is born
  with the wrong family before representative selection.
- `scanner-api/app/review.py:1850-1858,1958-1959` ranks the representative and
  then preserves the already-present Homepage family while defaulting the
  multi-page group to family scope.
- `scanner-api/app/repair_priority.py:238-284` counts all affected URLs but
  derives the denominator from usable HTML pages in one family, so numerator
  and denominator are different URL universes.

Required behavior:

- preserve per-family partitions for orphan and other mixed findings;
- use `mixed`/`cross_cutting` when no single family is valid;
- compute each denominator from the same URL subset as the numerator;
- assert `affected <= eligible` for every displayed ratio;
- never label a mixed orphan group Homepage because the selected representative
  happens to be `/` or a homepage-classified route;
- reject coverage values outside `[0,1]` at both Python and Base44 authority
  boundaries without silently falling back to the legacy repair contract;
- persist `page_count`, `family_breakdown`, and representative pages by family.

The denominator-domain defect is not orphan-specific. Live records also
contained Pretto 35/30, Meilleurtaux access evidence 47/6, and Meilleurtaux
failed-page evidence 22/6.

### P1 - Admission reconciliation repeatedly retries superseded releases

Production Base44 logs contained hundreds of repeated
`durableScanWorkerControl admission release failed` events. The coordinator's
fencing is correct; the five-minute sweep is wrong:

- every server-admitted terminal row from the last two hours is selected for
  another release because its durable `admission_access_id` remains present;
- that field is permanent admission provenance, not a release-pending flag;
- after a later scan claims the same owner's coordinator slot, releasing an
  older scan correctly returns `scan_not_bound` before the new bind or
  `scan_identity_conflict` afterward;
- the sweep records those safe stale outcomes as errors, returns
  `success:false`, and makes `/scan-reconcile` retry with 503.

Required behavior:

- add a durable pending/released/superseded reconciliation state instead of
  inferring pending work from permanent `admission_access_id` provenance;
- paginate and rotate all unresolved terminal rows rather than querying only
  the newest 50 per status;
- do not abandon an exact bound lease after the two-hour terminal lookback,
  because bound coordinator leases intentionally do not expire;
- release only when the exact candidate scan is still the bound generation;
- count released or provably superseded generations as satisfied;
- keep coordinator identity fencing unchanged;
- retain retryable failure when coordinator status cannot be read, and recheck
  status after a release race before suppressing a conflict;
- refresh mutable owner status for each different candidate rather than reusing
  an inactive/synthetic cache observation across generations;
- exercise the complete sweep, outage recovery, and more-than-50-row backlog in
  integration tests.

### P1 - Classification accuracy is not release quality

Strict accuracy was 18/27 (66.7%) on conclusive cases. Wrong primary identities:

- Musement -> content/blog instead of booking/experiences marketplace.
- Wecandoo -> local food/hospitality instead of workshop/experiences marketplace.
- Airbnb -> ecommerce specialty retail instead of booking marketplace.
- Naked Wines -> local food/hospitality instead of ecommerce/wine retail.
- Shine -> ecommerce specialty retail instead of finance/SaaS.
- N26 -> content/blog instead of digital bank/finance app.
- Pennylane -> content/blog instead of accounting SaaS.
- IKEA root -> content/blog after sampling only global corporate/newsroom pages instead of a retail surface.

Tiqets was partial: ecommerce is directionally closer than content/SaaS, but the expected identity is ticket/experiences marketplace.

Do not patch one brand at a time. Add structural fixtures for:

- experience/booking marketplaces;
- subscription or member-led ecommerce;
- finance apps with large guide/help surfaces;
- ecommerce roots that redirect into a corporate/global selector surface;
- representative surface selection before primary archetype classification.

### P1 - Correct archetype does not guarantee correct page families

Repeated route-vocabulary errors make otherwise useful evidence misleading:

- Smartbox's "simulateur chute libre" is labeled a calculator.
- Funbooker activity-detail routes are labeled collection pages.
- PayFit French employment guidance is labeled activity/loan pages.
- Papernest mortgage glossary routes containing `activite` are labeled activity pages.
- HelloSafe credit-card insurance is labeled a loan program.
- Castorama garden-project guidance is labeled a location page.
- Marketplace product routes are often reduced to standard pages.

Fix route tokenization and business-context weighting; do not let isolated multilingual tokens override HTML semantics and site archetype.

### P1 - Failure evidence is duplicated or overstated

Examples:

- N26 promotes transient 503 evidence as Fix first and duplicates one failure as a separate failed-page repair.
- Pennylane presents the same two 404s as one broken-page group plus two failed-page repairs.
- Papernest overlaps redirect-destination failure and server-error repairs.
- Mojo Mortgages presents the same lenders URL as both Fix first broken-page and Important verify-failed-page work.
- Meilleurtaux is complete/authoritative while an access-limited group is promoted as Important.

Required behavior:

- deduplicate by normalized URL, terminal response, and remediation family;
- prefer one repair with nested evidence over parallel customer tasks;
- keep single-observation 429/5xx evidence in verification/review unless reproducible or structurally confirmed;
- an access-limited group cannot coexist with complete/non-provisional authority without an explicit explanation of unaffected scope.

### P1 - Durable lifecycle and evidence counters are false

Every completed ScanRun inspected had:

- `completed_at == started_at`;
- `reviewing_at == null`;
- `representative_html_page_count == 0`;
- `usable_html_page_count == 0`;
- evidence quality 100 with reason `representative_html_evidence`.

Source trace:

- `persistDurableScanAuthority` derives a stable authority timestamp from `started_at` and writes it as completion time.
- the staged reviewing write does not set `reviewing_at`;
- frontend ScanRun modeling can also source completion from record creation.

Stable authority hashing and truthful lifecycle timestamps need separate fields. Do not overload `completed_at` to make a proof deterministic.

### P1 - Customer failure copy discards the real reason

The UI shows the same "Something interrupted this scan" message for materially different failures, including:

- scanner rate limit/challenge;
- worker heartbeat loss;
- result persistence failure;
- owner/manual cancellation.

Durable `status_detail` already distinguishes these states. Fifteen sites were valid access-limited controls, but a customer cannot tell that from the page.

Required states:

- access limited/challenged: explain that no authoritative result was saved and suggest retry timing;
- worker stalled: say progress stopped and the run was safely closed;
- save failure: say crawling finished but persistence failed;
- cancelled: say the run was stopped;
- include the scan ID/support reference and a context-appropriate retry action.

### P1 - "Should be handled first" disagrees with the rendered bands

The summary count uses raw scanner severity while visible Fix first/Important/Improve/Review bands use `action_priority`.

Observed contradictions include:

- Tanners: five "handled first"; every actionable card is Improve.
- PayFit: two "handled first"; one Fix first plus three Important.
- HelloSafe: three "handled first"; one Important and no Fix first.
- Mojo Mortgages: eight "handled first"; two Fix first plus two Important.
- Decathlon: two "handled first"; only Improve and Review sections.
- Castorama: eight "handled first"; four Fix first plus three Important.

Use one canonical action-priority model for summary counts, top-action IDs, card bands, ordering, and copy.

### P2 - Scan history is not account-wide despite its labeling

After the 50-site run, `/dashboard` displayed only Castorama. Source shows the page first resolves the active project and then lists up to three scans for that project. The heading and navigation say "Recent scans" and "Dashboard," but there is no project selector or account-wide history view.

This makes earlier scan IDs effectively undiscoverable from the UI even though direct `?scan_id=` URLs work. Either rename the surface to "Recent scans for this website" and expose a project selector, or provide account-wide recent history with per-site grouping.

### P2 - Grammar and count copy need a pluralization pass

Production examples include:

- "FixList found 1 pages and checked 1 representative pages."
- "comparison page pages."
- "1 of 75 guide pages checked are affected."
- a prior title equivalent to "which homepage are the main versions."

All count-bearing UI strings should use shared singular/plural helpers and page-family display names that do not append "page" twice.

## What is working

- All 50 requested sites were admitted sequentially without cross-scan result switching.
- Scan IDs were unique and dashboard detail URLs pinned the correct scan.
- The 150-page hard cap held in every completed result.
- Completed results used the Python scanner and Python review with no observed fallback.
- Access-limited sites did not receive fabricated authoritative FixLists.
- No non-HTML asset URL appeared as a page-level representative or affected-page FixItem in the completed matrix.
- The card layout is visually clean, readable, and generally scannable.
- "Why this is here," "Suggested fix," scope, effort, owner, and expandable evidence are a strong base when the underlying evidence is correct.
- Cambridge Wine and Spendesk demonstrate that a coherent, useful customer result is achievable with the present presentation model.

## Full matrix

Legend: `pass` = clean enough to trust; `mixed` = useful evidence with a material defect; `fail` = no result or result not safe to rely on. Classification `inc.` means access/coverage-inconclusive.

| # | Site | Terminal | Pages | Classification | Class gate | Result | Scan ID |
|---:|---|---|---:|---|---|---|---|
| 1 | GetYourGuide | cancelled | 0 | - | inc. | fail | `6a887be7efd321b0572ab2e7` |
| 2 | Viator | failed | 0 | - | inc. | access control | `6a887eb94667efc0a7e34230` |
| 3 | Musement | complete | 150 | content/blog | fail | mixed | `6a887f162658f82eb9e1d602` |
| 4 | Tiqets | complete | 150 | ecommerce retail | partial | mixed | `6a8880045398fdb71c4fde58` |
| 5 | Klook | failed | 0 | - | inc. | access control | `6a8880ad98fa6f44ca0a9137` |
| 6 | Fever | failed | 0 | - | inc. | access control | `6a88813503e529483ccc26cf` |
| 7 | Wecandoo | complete | 135 | local hospitality | fail | fail | `6a8881947fb057d255e2a8d0` |
| 8 | Smartbox | complete | 150 | ecommerce retail | pass | mixed | `6a88827a264c554d19a18c08` |
| 9 | Funbooker | complete | 150 | booking marketplace | pass | mixed | `6a88832528f4e86d8614d430` |
| 10 | Airbnb | complete | 150 | ecommerce retail | fail | fail | `6a8883c17ecc3561c6554f6d` |
| 11 | Whisky Exchange | failed | 0 | - | inc. | access limited | `6a8885023b9c03c787420fe4` |
| 12 | BBR | complete | 150 | ecommerce retail | pass | mixed | `6a888557e397a535d0aaa818` |
| 13 | Majestic | failed | 0 | - | inc. | access limited | `6a888620d70627b29b70b148` |
| 14 | Laithwaites | failed | 0 | - | inc. | access limited | `6a88867a3f9618f263f2dcc5` |
| 15 | Naked Wines | complete | 150 | local hospitality | fail | fail | `6a8886c4b4f506e7ac518a46` |
| 16 | Cambridge Wine | complete | 150 | ecommerce retail | pass | pass | `6a88873c7b48e4f1d968a0a9` |
| 17 | Vinatis | complete | 150 | ecommerce retail | pass | mixed | `6a8887d18c5a2dc2732c852c` |
| 18 | Millesima | complete | 150 | ecommerce retail | pass | mixed | `6a88884e47cea59803439374` |
| 19 | Tanners | complete | 38 | ecommerce retail | inc. | fail | `6a8888d34070513e44413af5` |
| 20 | Lea & Sandeman | complete | 150 | ecommerce retail | pass | mixed | `6a88898c259c6e83b2413f5f` |
| 21 | Qonto | complete | 150 | SaaS/app | pass | mixed | `6a888a10dbea6e941f346942` |
| 22 | Shine | complete | 150 | ecommerce retail | fail | fail | `6a888ac58b5e0d00b14eec57` |
| 23 | Revolut | failed | 0 | - | inc. | access limited | `6a888b48420d25605e57e33b` |
| 24 | N26 | complete | 150 | content/blog | fail | fail | `6a888b89fbf6acd9ade7f870` |
| 25 | Wise | complete | 150 | SaaS/app | pass | mixed | `6a888c0d350770377e8aef24` |
| 26 | Pennylane | complete | 150 | content/blog | fail | fail | `6a888c8fffeac504faf6e312` |
| 27 | Spendesk | complete | 150 | SaaS/app | pass | pass | `6a888d0e64a313a393055d33` |
| 28 | PayFit | complete | 150 | SaaS/app | pass | mixed | `6a888d9b0e28641a9e280994` |
| 29 | Alan | failed | 0 | - | inc. | fail | `6a888dea77e48877f700595b` |
| 30 | Swan | failed | 0 | - | inc. | fail | `6a8893dbdfaa98d063e23db8` |
| 31 | Pretto | complete | 150 | finance/lead gen | pass | mixed | `6a889401ce20f4eace7e82c3` |
| 32 | Meilleurtaux | complete | 150 | finance/lead gen | pass | fail | `6a8894651100cb2c3afeeab3` |
| 33 | Papernest | complete | 150 | finance/lead gen | pass | mixed | `6a8894d4ab412704a148aba8` |
| 34 | HelloSafe | complete | 150 | finance/lead gen | pass | mixed | `6a8895443f62951433da4d0f` |
| 35 | LesFurets | failed | 0 | - | inc. | fail | `6a8895e8b2927c76d1b6f1d1` |
| 36 | Assurland | complete | 150 | finance/lead gen | pass | mixed | `6a889609ab458986c582d709` |
| 37 | MoneySuperMarket | failed | 0 | - | inc. | fail | `6a88967b8aac30a76a37412e` |
| 38 | Compare the Market | failed | 0 | - | inc. | fail | `6a88969f3d89ff87c8673d8f` |
| 39 | Habito | complete | 1 | finance/lead gen | inc. | fail | `6a8896e65df4e98a1ac12166` |
| 40 | Mojo Mortgages | complete | 150 | finance/lead gen | pass | mixed | `6a889735201ab347357e1a75` |
| 41 | IKEA root | complete | 150 | content/blog | fail | fail | `6a889795707d27e68b72586d` |
| 42 | Leroy Merlin | cancelled | 0 | - | inc. | fail | `6a8898067bb731ec10c95146` |
| 43 | Decathlon | complete | 40 | ecommerce retail | inc. | fail | `6a8898a548b72fe64d28f0fe` |
| 44 | Maisons du Monde | failed | 0 | - | inc. | fail | `6a8899739a671f818fb46153` |
| 45 | Habitat France | failed | 0 | - | inc. | fail | `6a8899947136739b0a8c467b` |
| 46 | John Lewis | failed | 0 | - | inc. | fail | `6a8899ddfda46ed98ccdb308` |
| 47 | Argos | failed | 0 | - | inc. | fail | `6a889a2e4af29a94ed447855` |
| 48 | Fnac | failed | 0 | - | inc. | fail | `6a889a736c35bfb301f56658` |
| 49 | Darty | failed | 0 | - | inc. | fail | `6a889a93953f594579f66ea9` |
| 50 | Castorama | complete | 150 | ecommerce retail | pass | mixed | `6a889ada117364856552b881` |

## Recommended implementation order

1. Make one generated canonical release contract, remove stale literals, and make the active worker the unambiguous monitored surface.
2. Separate authority-proof timestamps from lifecycle timestamps and persist truthful evidence counters.
3. Replace the current severe-under-coverage rule with ratio/default-route-aware authority gating.
4. Partition mixed-family orphan/failure findings before representative selection and assert valid denominators.
5. Deduplicate failure evidence by normalized URL and remediation family.
6. Make summary counts derive from `action_priority` only.
7. Add customer-visible failure-state mapping from durable error/status detail.
8. Add structural classifier fixtures for the eight wrong archetypes and one partial marketplace case.
9. Add multilingual, archetype-aware page-family fixtures for the route-token failures.
10. Provide account-wide history or explicit project selection, then run a shared pluralization/content pass.

## Required acceptance rerun after fixes

Do not rerun all 50 immediately. Run the smallest focused gate first:

- marker/authority: one ordinary complete site plus a deliberate mismatched-marker fixture;
- under-coverage: Tanners, Decathlon, and Habito;
- mixed-family denominator: Wecandoo, Airbnb, N26, Mojo Mortgages, Castorama;
- classification: Musement, Wecandoo, Airbnb, Naked Wines, Shine, N26, Pennylane, localized IKEA retail, Tiqets;
- duplication: N26, Pennylane, Papernest, Mojo Mortgages;
- customer failures: one access challenge, one worker stall, and one persistence failure;
- clean controls: Cambridge Wine and Spendesk.

The focused gate passes only when:

- health/revision/ScanRun/FixList markers are identical;
- limited crawls are provisional and ineligible;
- every displayed ratio satisfies numerator <= denominator;
- no duplicate customer repair exists for the same URL/remediation;
- summary counts equal rendered action bands;
- correct failure reason appears in customer UI;
- no asset target appears;
- clean controls remain clean.

Only then rerun the full 50-site matrix.

## Evidence files

- `results.jsonl` - one structured record per site with scan/FixList IDs and verdict notes.
- `matrix.csv` - original requested matrix and expected business identity.
- `source-trace.md` - repository paths for the reproducible source-level findings.
- `README.md` - audit rubric and baseline.
