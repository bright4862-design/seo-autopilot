# Matrix Truthfulness and Worker Reliability Design

Date: 2026-09-05
Status: Approved in chat
Base revision: `e0a7cb855e8747a95bdf04118f422b925920541e`

## Objective

Finish the release repair exposed by the stopped production matrix without changing the Standard 150 product boundary. The release must make page accounting understandable and mathematically honest, remove stale grouped-card copy, retain the already-merged URL, vocabulary, and score improvements, and prevent a narrowly observed worker memory failure from leaving a scan in a misleading active state.

Premium 5,000, renderer work, broader subdomain crawling, classifier iteration, and unrelated UI redesign remain out of scope.

## Existing Work to Preserve

PR #252 is already present on the base revision and remains authoritative for:

- making every affected URL safely clickable;
- moving technical vocabulary out of customer headlines;
- replacing classifier terms such as “standard” and “conversion” with recognizable language;
- preventing foreign-subdomain sitemap entries from inflating `pages_found`;
- calibrating the health score so cosmetic breadth cannot make a working site look catastrophically unhealthy.

This work will be regression-tested, not reimplemented.

Uncommitted admission-reconciliation changes in another worktree are user-owned and excluded from this branch.

## Customer Result Truthfulness

### Page accounting

The current heading “Site sections discovered” is inaccurate because the list is deliberately a filtered, ranked set of at most eight follow-up candidates. It must be renamed to “Sections to scan next.” Its description must say that these are suggested folders for separate scans, not a complete inventory.

A separate page-accounting model will explain the whole discovery number. It will use `pages_found` as the authoritative total and present:

- named section counts when persisted evidence supplies them;
- a computed “Homepage and other pages” remainder;
- a final total that always equals `pages_found`.

The model must never silently fabricate negative or overlapping counts. Duplicate representations of the same section, such as market and path-prefix evidence, are merged before counting. Named rows are capped at the authoritative total. Any unrepresented, truncated, root, or otherwise unclassified pages are included in the remainder. If the persisted evidence is internally inconsistent, the UI must state that the section breakdown is partial while still reconciling the displayed arithmetic to the authoritative total.

Focused scans keep their own scoped total and do not imply that the folder breakdown covers the parent site.

### Page labels and links

The root path `/` is displayed as `Homepage (/)` everywhere customer-visible. Page paths continue to resolve through the existing safe `evidenceLink` contract. Link labels remain human-readable while the destination remains the full real URL. Unsafe or unresolvable values remain visible as text rather than becoming dead or misleading links.

### Repair-card grouping and counts

Cards remain grouped around one repair mechanism, with page-family details retained as evidence rather than duplicated as separate primary actions where the repair is genuinely shared.

All customer-visible counts and count-bearing sentences are derived after grouping from the final authoritative `affected_pages`, `page_count`, and family breakdown. A merged card must not preserve a stale first-child sentence such as “1 affected page” when the card now contains several pages.

Grouping must not merge unrelated fixes merely because their titles are similar. Existing repair identity, rule, scope, and evidence-confidence boundaries remain intact.

## Score Presentation and Contract

The already-merged `health_score_v3_cosmetic_capped` algorithm is retained. Cosmetic buckets remain capped, the score floor remains 40, and severe search-visibility failures retain materially greater weight.

This patch adds regression coverage proving that repeated cosmetic findings across template families do not produce a catastrophic score and that blocked or incomplete evidence cannot appear healthy. It does not add an arbitrary display-only bonus or rewrite stored scores.

Customer copy should frame the score as prioritization guidance, not an overall judgment of the business or website.

## Worker Reliability

The production matrix observed one Standard 150 worker exceed the 512 MiB Cloud Run limit by approximately 1–2 MiB. The immediate release-safe correction is to pin the reviewed worker deployment to 1 GiB while retaining concurrency 1, the 480-second timeout, the 150-page hard cap, and the existing maximum-instance boundary.

The worker must continue to avoid unbounded accumulation. Existing response and evidence caps remain mandatory and receive regression/static contract coverage where practical.

Catchable failures continue through the durable worker’s explicit failure-persistence path. A process-level OOM cannot reliably persist its own terminal state, so the signed reconciler remains the fail-closed backstop. This change does not pretend that a killed process can execute cleanup code. Acceptance must prove that a failed job becomes terminal and releases admission within the documented reconciliation window rather than remaining indefinitely active.

The separate uncommitted reconciliation work is not copied into this branch. If it merges into `main` before integration, this branch will rebase and verify compatibility.

## Data Flow

1. Scanner discovery produces `pages_found` and bounded sampling evidence.
2. Durable persistence stores those fields without customer-side reinterpretation.
3. The customer result projection supplies the authoritative result.
4. A pure frontend page-accounting helper normalizes section evidence and computes the remainder.
5. The FixList page renders the exact accounting separately from ranked follow-up scan candidates.
6. Repair cards derive final copy only after grouping and final affected-page calculation.
7. Worker deployment pins 1 GiB memory; existing durable failure/reconciliation paths own terminal truth.

## Error Handling

- Missing section evidence: show the total found and label the breakdown unavailable; never show a misleading partial list as exhaustive.
- Section sum below total: show the exact remainder as “Homepage and other pages.”
- Section sum above total or overlapping: bound named rows, mark the breakdown partial, and reconcile to `pages_found` without claiming exhaustiveness.
- Unsafe URL: render a readable text label, not an anchor.
- Worker exception: persist the existing structured failure when the process is alive.
- Worker termination/OOM: allow task retry and signed reconciliation to produce a truthful terminal state and release admission.

## Verification

Frontend tests must cover:

- Wecandoo-style `5,000` total with named sections plus a remainder summing to exactly `5,000`;
- IKEA-style `1,200` total with only `417` classified pages and an explicit `783` remainder;
- truncated top-prefix data and overlapping market/path evidence;
- `/` rendered as `Homepage (/)` with a safe full URL;
- every affected URL clickable when resolvable;
- grouped cards regenerating count copy from final data;
- customer headlines free of the frozen jargon list;
- existing score-calibration contract markers.

Worker/deployment tests must cover:

- the reviewed deployment declares 1 GiB memory, concurrency 1, and timeout 480;
- the hard 150-page cap and release markers remain unchanged;
- catchable failures persist terminal state;
- reconciliation still terminalizes abandoned work and releases admission.

The full frontend contract suite, lint, typecheck, production build, focused scanner regressions, and complete scanner API suite must pass before release.

## Release Sequence

1. Rebase the isolated branch onto the exact current `origin/main` immediately before final verification.
2. Confirm no user-owned reconciliation changes were overwritten.
3. Merge only after all required CI gates pass.
4. Deploy the worker and scanner from the exact merge SHA without promoting mixed versions.
5. Publish Base44 functions/entities/frontend from the same source identity.
6. Verify live SHA, fingerprint, scanner/review markers, worker memory, concurrency, timeout, and traffic.
7. Run one controlled canary and verify persistence, FixList display, clickable URLs, page accounting, reload/history, and admission release.
8. Run a small focused acceptance set before resuming a broad matrix.

No overall release GO is implied by the code merge alone.
