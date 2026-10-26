# Standard 150 Capacity Recovery and Extended 500 — Engineering Blueprint

Status: **R1 implementation candidate in isolated branch; R2–R4 design only. No merge, deployment, customer activation, or production acceptance.**
Prepared: 2026-10-26. Baseline: main at `cd9d4ff562d6aad3cc7ecce059fa12f8d4098db2` (verify a fresh exact head before integration).
Owner objective: improve genuine shortfalls below 150 and add a separate safe 500-page offering; never assert 150/500 pages were analyzed if fewer were.

## Scope and invariants

- Existing Standard 150 customer/public admission remains `standard_150`; max **150 unique retained destinations**, never an unconditional fetch target.
- Do not touch canonical page identity, sitemap trust, same-origin/path/market scope, URL trap filtering, robots.txt enforcement, SSRF protections, retry policy, response-boundary capping, scoring, HMAC/authority, persistence, customer entitlements or payment in R1.
- Respect finite shared request budget (`max_pages * 8` currently), scheduler deadline, host pressure and bounded browser rendering. Do not increase concurrency, fetch timeout, sitemap discovery cap or platform deadlines as a shortcut.
- Initial selected sitemap URLs and fetch order must remain identical to existing `balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves` on sites already reaching their page cap.
- Never silently promote an access-limited/inventory-unproven result to sufficient coverage just because more URLs were requested.
- No live customer scan, release merge or worker deployment without exact-source CI, identity and rollback evidence.

## Evidence motivating R1

`scanner-api/app/scanner.py` selects at most `max_pages - 1` initial sitemap candidates, then workers drain the frontier. It deduplicates final URL identity, so a request can consume effort without adding a new retained page. Links discovered from fetched pages can replenish the queue, but **unselected sitemap entries are not presently reintroduced if the frontier exhausts early**. This is a code-level plausible shortfall, not yet a measured diagnosis of any particular site.

`scanner-api/app/sampling.py` v7 intentionally prioritizes commercial hubs, trust and representative leaves. Preserve that ordering. `scanner-api/app/scan_timing.py` owns time reservation; `scanner-api/app/coverage_authority.py` decides the coverage state. A short result can still be legitimate because of deadlines, robots, challenges, distinct URL inventory, path scope, or redirect duplication. Historical Funbooker 139-page evidence alone is not proof of a bug.

## R1 — Disabled-by-default sitemap reserve/backfill

Files: `scanner-api/app/scanner.py`, dedicated `scanner-api/tests/test_sitemap_backfill.py`, this blueprint.

Algorithm:
1. Keep the seed and original `max_pages - 1` balanced selections unchanged.
2. Hold a bounded ordered reserve **from already discovered sitemap URLs not initially selected**, computed only for trusted durable Advanced/Standard-150 jobs with an explicit enable flag. The reserve is local scheduling state, not a new inventory source or new request pool.
3. When the worker queue is empty **and no fetch remains in flight**, under the existing state lock, enqueue the next never-seen, allowed-by-existing-frontier candidate. Do not bypass `enqueue`, robots policy, SSRF, request budget, existing URL identities, rate pacing or deadline. Never prefetch reserve URLs.
4. Stop when unique retained cap reached; no eligible candidates remain; shared claim/queue ceiling reached; or the existing crawl deadline expires. Deduped redirects consume their real requests, not extra free budget.
5. Emit bounded, non-sensitive versioned backfill counters, including attempted-enqueue count and reserve exhaustion, only while enabled. Keep `pages_crawled` defined as retained destinations, `urls_attempted` as attempts; keep initial sitemap selection counts distinct from actual checked pages.
6. Feature flag `FIXLIST_STANDARD150_BACKFILL_ENABLED=true` must be explicitly installed only at a canary deployment; absent/anything else is OFF. Do not activate implicitly on PR merge. Include in release configuration review.

Risks and tests:
- Duplicate final URLs: seed + two aliases collapse; backfill fills one spare slot from a previously unselected sitemap candidate; `urls_attempted` and dedup counters remain correct.
- Initial priority: healthy at-cap scan makes no reserve requests, sample prefix unchanged.
- No sitemap, small genuine sites, malformed/offscope/trap URLs: no fake pages, no bypass.
- robots disallow, 429, timeout, vendor challenges: backfill respects original policy and the deadline; results remain limited when evidence is insufficient.
- Concurrent workers: single cursor under lock; no repeated requests, no starvation/spin loop leading to overcap, no enqueue beyond shared request ceiling.
- Review/authority: additional fetched evidence is real and not assigned to previously unchecked pages.
- CI: targeted tests + preexisting `test_final_url_dedup.py`, commercial sampling/market-wiring, URL normalization/frontier, concurrency, scan response budget, worker completion, coverage authority, evidence/repair contract and frontend builds.

R1 release gate: reproducible one-run production-like diagnostics from multiple real sites showing an actual unused-cap cause; exact-head full scanner/consumer CI; paired OFF/ON deterministic simulations; owner-approved limited canary, production rollback. If no premature exhaustion is reproduced, keep flag off and do not claim improvement.

## R2 — Isolated Extended 500 collection tier (design only)

Introduce explicit internal `extended_500` profile and separate admission/entitlement/queue namespace, not an ambiguous public max_pages parameter. The scanner's `advanced` profile is *not* silently raised from 150.

- Config contract: requested max 500; server-owned effective cap; bounded discovery/request/concurrency/rate limits; time limits based on measured p95/p99 on controlled fixtures (no invented SLA); stop/termination reason first class.
- Larger jobs need worker, Cloud Run/Cloud Tasks, scheduler heartbeat, memory, request/response size, timeout, result projection and cost benchmarks; do not assume increasing page cap is safe.
- Consider staged/adaptive crawl checkpoints or batched evidence processing if single-request performance does not fit bounded worker limits. Persist only authenticated, idempotent state transitions.
- No increase to robots exceptions, private URL reachability, access bypass or retry count.
- Preproduction acceptance: 500 unique in-scope HTML fixture pages counted without duplicate/URL-scope leaks; 499 + 1 redirect/404; 5,000+ sitemap discovery; blocked 429 and slow hosts; canceled/replayed tasks; worker timeout; bounded queues, memory, payload and storage; deterministic priorities with many leaves and few hubs.

## R3 — End-to-end 500 evidence contracts (design only)

Known hardcoded limits to audit before writing an implementation:
- `scanner-api/app/main.py` `SCAN_RESPONSE_PAGE_LIMITS` advanced=150.
- `scanner-api/app/stage2_coverage_evidence.py` rejects >150 page objects.
- `scanner-api/app/scan_job.py`: `build_authority_review_payload` limits review page sample to 60 and findings to 100; coverage of the FULL 500 must not be confused with a 60-page view sample.
- `base44/functions/startStandardScanJobV8/entry.ts` only admits `standard_150`.
- V8/legacy Base44 result/persistence/authority, generated release contracts and frontend exports must be checked individually; do not simply change a shared MAX_PAGES and leave downstream 150-page truncation.
- Define and test `pages_discovered`, `urls_attempted`, `unique_retained`, `usable_html`, `pages_reviewed`, `pages_projected`, `pages_sampled` separately. Model answers must never assert evidence for an unreviewed page.
- Version and authenticate the Extended 500 result; preserve read/replay/rollback of historical Standard 150 snapshots byte-for-byte.

## R4 — Canaries, metrics, promotion and rollback (design only)

1. Owner/fixture-only R1 OFF/ON paired scans on exact same sites and controlled conditions. Record requests, retained unique destinations, usable HTML, failure buckets, stop reason, elapsed, RSS/peak, source SHA/fingerprint. No unconditional 150 target.
2. Once R1 passes, feature-gated Standard 150 canary with no fleet-wide switch and known previous revision.
3. R2–R3: private 500 end-to-end jobs on fixture environments, then explicit authorized customer cohort; compare coverage and failure behavior, *not raw scores across different samples*.
4. Hard rollback: turn flag off / restore prior worker and Base44 release identities; audit no partial signed durable state or abandoned tasks. Treat rollout approval as a separate operator action.

## Immediate integration checklist

- [x] Read current production code paths and identify finite limits.
- [x] Preserve the original B01–B28 accepted stages rather than rebuilding them.
- [ ] R1 code and adversarial tests committed to draft PR.
- [ ] Exact-head repository CI green; raw test results and branch SHA recorded.
- [ ] Confirm release fingerprint/config mirrors and authorized runtime flag propagation.
- [ ] Canary diagnostics and owner approval.
- [ ] 500-page mode and persistence/contracts code.
- [ ] 500-page staging acceptance, then customer canary.

**No percentage or date forecast is asserted without observed CI/performance data.**
