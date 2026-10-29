# Extended 500 Lane C: bounded private collector (issue #384)

Status: **private, unreviewed, not wired, not deployed.** Base SHA `002b84c9b6eaef78babec6081df150f31a000b11`.

Files: `scanner-api/app/extended500_private_collector.py`,
`scanner-api/tests/test_extended500_private_collector.py`, this doc.
Nothing imports the module from `main.py`. No route, queue, worker, Base44, Stripe or
Standard 150 change.

**Branch history:** while this slice was in progress, commits `0cf535bd9`, `036f0dc2a` and
`bb703cf04` landed on the lane branch. They add `run_isolated_extended500_collection`, a
default-disabled path that runs `scanner.run_scan` in a *spawned* child process holding a
child-only `extended_500` budget, plus `validate_extended500_collection_result`. That work is
kept verbatim; this slice is layered on top as one combined module and test file, with no
force-push. The two paths complement each other:

- The spawn path reuses all of run_scan. Its budget mutation is process-local, but it inherits
  run_scan's lack of injectable pacing, cross-origin refusal and retained-memory bounds.
- The bounded frontier below adds those controls and fully reconciled counters.

Choosing which path a future worker uses is an integrator decision.

## Why it does not call `run_scan` with a 500 budget

- `scanner.resolve_scan_budget` reads the module-global `SCAN_BUDGETS` and falls back to
  `advanced` (150) for unknown modes. The public `/scan` model (`main.py`, `scan_mode: str`)
  forwards a free string to `run_scan`. Reaching 500 without editing `scanner.py` means
  mutating that shared dict, which concurrent public requests could see. The existing
  proof does this only with `monkeypatch`.
- `run_scan` has no injectable clock, paces only after a 429, follows redirects to any
  public host, has no retained-memory budget, and silently runs `pages = pages[:max_pages]`.

So the collector runs its own bounded frontier through the production per-page path
(`scanner.fetch_and_extract` -> `fetch_with_redirect_evidence` -> `security.safe_get_once`
-> `extract_page`), reusing `load_robots_policy`, `load_sitemap_urls`, `select_balanced_urls`,
`classify_frontier_url`, `final_url_identity`, `merge_duplicate_page_evidence`, the
scan-coverage counters, `allocate_scan_time_budget`, B11
`enrich_pages_from_retained_link_evidence(max_assessed_pages=500)`, the positive page
projector and `build_extended500_evidence_handoff`. `admit_run_scan_result` sends a
run_scan-shaped result through the same fail-closed gate. It catches run_scan's silent slice
because it checks `urls_attempted == page records + final_url_duplicates_deduped`.

## Controls

- One `_HostRequestGuard` sees every request: robots, sitemap, pages and redirect hops. It
  goes through a per-operation `_GuardedClient` that only exposes `stream`/`get`. The guard
  enforces the total request budget, the phase deadline (injected clock) and a minimum
  per-host start interval (injected sleeper). On a 429 the interval widens and Retry-After is
  honoured. A 429 is **never retried**. N consecutive 429s stop the crawl.
- Redirect hops are checked in `request_provider` *before* the request. A hop must stay on the
  seed origin or its www/apex alias, and that origin's robots.txt is checked. The run_scan
  www-alias landing adoption is mirrored.
- The ambient `owner_robots_override` is forced to `False`. When the guard refuses the robots
  read, the result is never treated as "robots unavailable" (which would allow fetching).
- Per-response decoded cap is at most 5 MB. Retained-evidence bytes budget defaults to 64 MiB.
  Discovery inventory is capped at 5000 URLs; over-cap candidates are counted, not stored. The
  `source_pages` list per URL is capped at 50, and `_reachability_links` is trimmed to
  allowed-origin hrefs, which loses nothing for B11.

## Hard failures vs counted exclusions

Hard failures return `success: false` plus `error_code` and **no page arrays**:
- `invalid_request` and `invalid_limits`. Examples: capacity above 500, deadline above the
  120 s `ASYNC_JOB_TIMEOUT_CEILING`, interval below 0.05 s.
- `entry_robots_denied`.
- `deadline_before_minimum_evidence` and `insufficient_evidence`.
- `capacity_exceeded`: a 501st retain attempt in the ledger, or a run_scan result with more
  than 500 records.
- `retained_bytes_budget_exceeded`. It fails rather than truncating, like the handoff's
  8 MiB budget.
- `accounting_mismatch` and `run_scan_result_rejected`.

Counted exclusions are never retained or followed, and the run continues: `robots_denied`
(never fetched), `non_html`, `http_error`, `rate_limited`, `access_blocked`, `fetch_failed`,
`oversized_response`, `cross_origin_redirect`, `unsafe_destination`, `incomplete_html`,
`missing_page_evidence`, `duplicate_final_destination`, `fetch_cut_by_budget`.

Stop reasons are counted, not failures, once minimum evidence exists: `inventory_exhausted`,
`capacity_reached`, `deadline_reached`, `request_budget_exhausted`, `host_rate_limited`.

These identities are verified before success. Per-URL states are cross-checked as well:

```
urls_discovered == pages_retained + sum(excluded) + sum(not_attempted)
urls_attempted  == pages_retained + sum(excluded) - excluded.robots_denied
```

`pages_found` = `urls_discovered` (bounded inventory). `urls_attempted` counts network fetch
attempts only. Unlike run_scan, robots-denied URLs are not counted as attempted. Pre-inventory
filters (`discovery_filtered`) sit outside the identity.

## Performance

**Synthetic only, not a real-site benchmark.** In this container with in-memory
MockTransport, the 510-discovered -> 500-retained test measured about 3.3 s wall time in
`pytest --durations`, including signing and projection. It uses a fake clock, so no pacing
sleep happens. On a real host at the default 0.2 s per-host interval, 500 pages need at least
100 s of request starts alone, which is close to the 120 s ceiling. Fitting 500 real pages in
one job is UNVERIFIED and may need batching (spec section "Worker timeout").

## Proposed shared-file patch (for the integrator, not applied)

This would let `run_scan` itself run a private 500 budget without a global mutation:

```diff
--- a/scanner-api/app/scanner.py
+++ b/scanner-api/app/scanner.py
@@
+from contextvars import ContextVar
+_PRIVATE_EXTENDED500_BUDGET: ContextVar[dict | None] = ContextVar("fixlist_private_ext500_budget", default=None)
@@ def resolve_scan_budget(scan_mode, timeout_seconds=None, *, job_mode=False):
-    base = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
+    private = _PRIVATE_EXTENDED500_BUDGET.get()
+    if job_mode and private is not None and str(scan_mode) == "extended_500":
+        base = private  # set only by extended500_private_collector; never by a request
+    else:
+        base = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
@@ (end of crawl)
-        if len(pages) > max_pages:
-            pages = pages[:max_pages]
+        if len(pages) > max_pages:
+            if _PRIVATE_EXTENDED500_BUDGET.get() is not None:
+                raise ValueError("Extended 500 capacity exceeded")  # fail closed, never slice
+            pages = pages[:max_pages]
```

Each request site would still need a reviewed `request_provider` seam to get per-host pacing
and cross-origin refusal inside run_scan.

## Unverified / blockers

- Real-site timing, peak RSS, 429 behaviour and payload size have not been measured.
- Robots.txt and sitemap fetches use the existing `safe_get`. Their redirects follow any
  public host, which is pre-existing Standard 150 behaviour; their request starts are still
  paced by the guard.
- No caller exists yet. It still needs the worker, pickup-time authorization, reviewed
  persistence and canaries (spec order steps 1, 2, 4 and 5).
- Rollback: delete the three files. Nothing else references them.
