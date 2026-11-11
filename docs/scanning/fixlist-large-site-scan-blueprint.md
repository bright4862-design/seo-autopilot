# FixList — large-site scan blueprint (150 now, 500-ready)

Audited read-only against `bright4862-design/seo-autopilot` at `689a7fb` (10 Nov 2026). Nothing was changed. File references are to `scanner-api/app/` unless stated.

**Updated 11 Nov 2026:** §3.5 now follows the staged architecture, §3.7 (what clients get) is new, and §4 points to the phased roadmap in `claude/fixlist-staged-scan-architecture-roadmap.md`.

## Verdict

Fix page selection before raising the cap. On a large site whose URLs don't match the classifier's vocabulary, the current selector spends almost the whole budget on one alphabetical slice of the site, and going from 150 to 500 only buys more of that slice. A 150-page scan with importance-ranked selection will cover a large company better than a 500-page scan with today's selection. The 500 tier then runs on the staged pipeline in the roadmap doc, where 500 pages is ten 50-page batches instead of one long request.

## 1. What the scanner does today

| Step | Behaviour | Where |
| --- | --- | --- |
| Budget | Durable job asks for 210 s, clamped to 120 s. Splits into about 36 s sitemap, 78 s crawl, 6 s response | `scan_job.py:42`, `scanner.py:375`, `scan_timing.py` |
| Discovery | Sitemaps only, up to 5,000 URLs and 40 sitemap files. Only `<loc>` is read; `lastmod` and `priority` are discarded | `scanner.py:145`, `sitemap.py` |
| Selection | One pass, before any page is fetched: `select_balanced_urls` picks 149 sitemap URLs using URL-path regex families | `sampling.py` |
| Queue | Plain FIFO: seed, then the 149 selected URLs, then internal links appended at the tail | `scanner.py` `enqueue` / `worker` |
| Crawl | 8 concurrent fetches, stops at 150 pages or the crawl deadline | `run_scan` |
| After crawl | Up to 150 pages reviewed; 60 pages and 100 findings go into the signed authority payload | `scan_job.py:133-134` |

## 2. Findings, most important first

**F1. Unrecognised sections get zero pages (measured).** I ran the repo's own `select_balanced_urls` + `classify_template` on a synthetic 3,307-URL site: `/solutions` (1,560 URLs), `/insights` (1,040), `/stores` (400), `/products` (300), plus seven top-level pages.

| Budget | /insights | /products | /solutions | /stores | /platform |
| --- | --- | --- | --- | --- | --- |
| 149 | 105 | 38 | **0** | **0** | **0** |
| 499 | 412 | 81 | **0** | **0** | **0** |

Cause: everything the regexes don't recognise falls into the single `standard` family, and candidates are sorted by path (`rank()` returns `(not preferred, signature, url)`), so the fill is alphabetical. `/insights` sorts before `/platform`, `/solutions` and `/stores` and absorbs the budget. Sites with recognised vocabulary (Funbooker-style `/category`, `/city`) do much better; this is the failure mode for enterprise sites with their own naming. Synthetic input, so treat the exact numbers as illustrative and the mechanism as real.

**F2. The homepage's links never influence what gets scanned.** When the sitemap has 149+ URLs, the queue is already full before the homepage is fetched, and internal links land behind it. The single best free signal of importance (what the company links from its own navigation) is only used for broken-link probes. Read from code, not reproduced live.

**F3. No importance score exists before fetch.** Importance is computed only after the crawl, for ranking repairs (`stage3_priority_factors.py`: money 1.0, hub 0.8, blog 0.5, utility 0.1, optional GSC value). Selection uses role buckets and nothing else: no path depth, no parent/child structure, no sitemap `lastmod`, no inlinks.

**F4. Fetch order is not importance order.** If a rate-limited site cuts the crawl short, what was fetched is hub/leaf round-robin, not "most important first". The August 50-site audit shows the cut happens: Tanners 38 of 3,689, Decathlon 40 of 1,374.

**F5. Discovery saturates.** 12 of 50 audit sites reported exactly 5,000 found, i.e. the cap, not the site. Which 5,000 are seen depends on child-sitemap order.

**F6. 150 is a contract, not a constant.** It is enforced in roughly 20 places in Python (several raise on more than 150: `stage2_reachability_provenance.py:14`, `stage2_coverage_evidence.py:32`, `geo_evidence.py:178`, `geo_readiness.py:49`, `stage2_hub_render_evidence.py:213`, `scan_comparison_authority.py:294`), in the Base44 validators (`persistDurableScanAuthorityV8/comparisonEvidence.js`, `getCustomerScanResultV6/V7` geoReadiness and publishedRepairEvidence), in `main.py` `SCAN_RESPONSE_PAGE_LIMITS`, and in the frontend (`ScanWebsiteForm.jsx:620,701,1126`, `FixList.jsx:480`). A 500-page result would be rejected or silently truncated at each one.

**F7. 500 pages does not fit the current time envelope.** Unblocked audit sites reach 150 pages inside the 78 s crawl window, so throughput is at least 1.9 pages/s. At that floor 500 pages needs about 260 s of crawl against 78 s available.

## 3. Blueprint

### 3.1 Importance score (deterministic, no AI, computed for every discovered URL)

New module `page_importance.py`, versioned like the others. All inputs are things the scanner already has or can get for free.

| Signal | Source | Why |
| --- | --- | --- |
| Linked from homepage / main nav | Fetch homepage first, read its links | The company's own statement of what matters |
| Parent of many URLs | Count discovered URLs under each path prefix | Finds hubs like `/solutions` without any vocabulary |
| Path depth | Segments after locale prefix | Shallow pages are usually more important |
| Role prior | Existing `selection_role` / stage3 values | Keeps current commercial knowledge |
| Sitemap `lastmod` recency | Parse it in `sitemap.py`; ignore if every URL has the same value | Maintained pages over abandoned ones |
| Observed inlinks | After the first crawl pass | Corrects the prior with evidence |
| GSC clicks (optional) | Existing `gsc_page_value_v1` evidence | Overrides the estimate when connected |

Suggested starting weights: homepage link 0.30, parent-of-many 0.20, depth 0.15, role 0.20, lastmod 0.05, inlinks 0.10. Calibrate on the 50-site corpus; do not ship weights untested.

### 3.2 Selection: section quotas, then spread

Replace family buckets as the primary partition with **sections** (first path segment after locale; second segment when one section holds more than half the site).

1. **Fixed**: homepage plus up to 5 trust pages (as today).
2. **Navigation set**: URLs linked from the homepage, up to 15% of budget.
3. **Section heads**: every section with at least 2 URLs gets its hub page and a floor of 3 pages.
4. **Section quotas**: remaining budget split by `sqrt(section size)`, weighted by mean importance. Square root stops a 1,500-URL section from starving a 40-URL one.
5. **Within a section**: group by route pattern (existing `route_signature`, with numeric/slug tails collapsed), take the highest-scoring pages per pattern, and break ties by a hash of the URL, never alphabetically.

Same algorithm at 150 and 500; only the budget changes. At 500 the extra pages go to more representatives per template and to small sections, which is what makes "affects N pages" counts trustworthy on a big site.

### 3.3 Crawl: two passes, priority queue

- Replace the list + `queue.pop(0)` with a heap keyed on `(-importance, url)`.
- **Pass 1** (about 10% of budget): homepage, navigation set, section heads. Record their outgoing links.
- **Re-score** the remaining candidates with observed inlinks, then **pass 2** fills the rest in priority order.
- A deadline or rate limit now cuts the least important pages, so a partial scan is still the top of the site.

### 3.4 Cap as one server-owned value

- One table: mode → `page_cap` (`standard_150`: 150, `standard_500`: 500). Every guard in F6 reads it instead of a literal.
- `page_cap` is written on the ScanRun by `startStandardScanJob` from the customer's entitlement. It is never a customer-controlled field, which keeps the "one scan, no size selector" UI contract.
- Add a new function generation (V9) rather than editing V2–V8; historical records stay readable.
- Keep per-fix `affected_pages` capped at 150 and add `affected_page_count` for the true total. This avoids changing the persistence and projection validators for lists.

### 3.5 How 500 runs: staged pipeline

The scan becomes plan → fetch in 50-page batches → finalize, with state kept in a storage bucket between steps. Full design in the roadmap doc, §2.

| Tier | Batches | Per-request budget | Cloud Run / Tasks timeout |
| --- | --- | --- | --- |
| 150 | 3 | Well under 480 s | Unchanged |
| 500 | 10 | Well under 480 s | Unchanged |
| 5,000 (later) | 100 | Well under 480 s | Unchanged |

What this removes: retuning the heartbeat drain, terminal drain and admission lease whenever the scan gets longer. Liveness is judged per committed batch, so those timers no longer depend on page count.

Still needed for 500 regardless of architecture:

- A scan-level wall budget of about 10 minutes, after which the scan finalizes with what it has.
- Sitemap discovery stays capped at 5,000 but reports `inventory_capped: true` when it hits the cap.
- A benchmark of `review.py` at 500 pages against the 20 s local review timeout.
- Crawl concurrency stays at 8 until tested; higher risks more 429s.

Throttled sites (0.5–2.5 s between requests) will not reach 500 inside that budget. They finish as a prioritized partial result, which §3.3 makes meaningful.

**Interim shortcut** (only if 500 must ship before staged execution exists): keep the single-request worker and stretch it.

| Setting | Now | Stretched for 500 |
| --- | --- | --- |
| `ASYNC_JOB_TIMEOUT_CEILING` | 120 s | about 360 s, sitemap share capped at 45 s |
| Worker fuses (crawl + post + completion + terminal) | 330 s | about 570 s |
| Cloud Run `--timeout` and Tasks dispatch deadline | 480 s | 720 s, moved together |
| Heartbeat drain | 900 s | above 720 s plus max backoff |
| Terminal drain | 1,800 s | above 3 attempts × 720 s plus backoff; recheck admission lease |

These values get retuned again when the staged pipeline lands, which is why this is a fallback.

### 3.6 Fitting the current UI

The UI needs no new screens. The existing panels already read the fields this design fills.

| UI element (existing) | Change |
| --- | --- |
| "Pages found" breakdown, "Sections to scan next" | None. They read `path_prefixes_discovered/selected/checked`, which section quotas populate more evenly |
| "Business-critical pages: X of Y chosen" | None; backed by importance tiers instead of regex families |
| Fix order | Feed `importance_score` into the existing four-factor priority as page value when GSC is absent |
| Affected pages inside a fix | Ordered by importance (review already has `ranked_affected`) |
| Page list | Emit `pages` sorted by importance; add `importance_tier` and `selection_reason` per page. Both must be added to the `page_output_privacy.py` allowlist or they are stripped |
| Progress while scanning | `scanProgressModel` uses `pages_planned` as the denominator once batches report progress |
| Literals | `FixList.jsx:480` `> 150` → `> page_cap`; the `.slice(0, 150)` calls in `ScanWebsiteForm.jsx`; copy at `FixList.jsx:748,790`, `Account.jsx`, `Landing.jsx`, `Billing.jsx` should read the cap from the record |

Plain-English reasons for the customer: "Linked from your homepage", "Main page of a section", "Example of a repeated page type".

### 3.7 What clients get

More pages alone does not help a non-technical owner; a longer list is worse. These are the client-visible gains, with what each depends on.

| Client sees | Depends on | Roadmap phase |
| --- | --- | --- |
| Fixes ordered by the pages that matter: "this affects your homepage and three pages linked from it" | Importance score feeding fix priority | 1 |
| One coverage line: "We checked your 150 most important pages out of 5,000, across all 14 sections" | Section quotas, `inventory_capped` | 1 |
| "Fix this once in the template; it likely repairs about 1,560 pages" | Several samples per route pattern plus inventory counts per pattern | 1, stronger at 6 |
| A useful list even when the site throttles the scan | Priority-ordered fetch, finalize as `limited` | 3, 5 |
| Real progress and "you can close this tab" | Per-batch progress writes | 5 |
| Reliable "fixed / still there / new" on rescan, and cheap re-checks of one fix | Stored page evidence in the workspace | 5 |
| A short first screen: "do these five first", the rest grouped by template | Presentation only; no scanner dependency | Any time |

Rule for the template estimate: always show the evidence behind it, for example "seen on 12 of 12 sampled pages of this type; about 1,560 pages of this type were found". It is an extrapolation and must be labelled as one.

## 4. Order of work

The phased plan, gates, draft commands and risks are in `claude/fixlist-staged-scan-architecture-roadmap.md`. In short:

0. Baselines and live-config check.
1. Selection v8: importance and section quotas (§3.1, §3.2). Biggest gain, no infrastructure.
2. Split `run_scan` into plan, batch and finalize functions in place, no behaviour change.
3. Priority frontier and two passes (§3.3).
4. Cap as one server-owned value, still 150 (§3.4), with the UI literals (§3.6).
5. Workspace and staged execution (§3.5).
6. 500 tier.

## 5. Acceptance tests

- Synthetic site from F1: every section with 2+ URLs gets at least 3 pages at both budgets; no section exceeds 40%.
- Shuffling sitemap order or renaming sections alphabetically does not change which sections are covered.
- Same input twice gives the identical selection (determinism).
- Truncating the crawl at 30% of budget still contains homepage, all navigation-set pages and all section heads.
- 50-site corpus: sections never selected drops versus v7; no regression on Funbooker, Pretto, Center Street Lending, Norris Wines.
- With cap parametrised at 150, signed payloads are byte-identical to today's for a fixture scan.

## 6. Not verified

- F2 and F4 are from reading the code; I did not run a live crawl.
- No GCP access from this session, so the deployed timeout, queue and drain values are taken from the repo, not from live config.
- The August audit data predates sampling v7; current completion rates may differ.
- Whether the UI page list shows more than the 60-page signed sample was not traced end to end.
- Review cost at 500 pages is unmeasured.
