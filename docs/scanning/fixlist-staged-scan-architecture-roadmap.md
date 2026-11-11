# FixList — staged scan architecture and implementation roadmap

Companion to `claude/fixlist-large-site-scan-blueprint.md` (audit findings, selection and importance design, UI fit, client value). Based on a read-only audit of `bright4862-design/seo-autopilot` at `689a7fb`. Nothing in the repo or in GCP was changed. All `gcloud` commands below are drafts for you to run; none have been executed.

**Updated 11 Nov 2026:** each phase now lists what clients get from it.

## 1. The honest comparison

Today one Cloud Tasks delivery runs the whole scan (`main.py` `scan_job` → `run_scan`, a 716-line function) with every piece of state in memory. Page count is therefore bounded by one HTTP request, a retry restarts from zero, and the drain/heartbeat/lease constants all have to be retuned whenever the scan gets longer.

| Option | What changes | Ceiling | Verdict |
| --- | --- | --- | --- |
| A. Stretch timeouts | Constants only. Cloud Run request max is 60 min; Cloud Tasks HTTP dispatch max is 30 min | About 30 min per attempt, no resume | Fine for 500. Dead end for 5,000. Drains retuned every time |
| B. Cloud Run Job per scan | New trigger path; monolith stays. Task timeout up to 7 days | Very high | No checkpoint, loses the Cloud Tasks OIDC/attempt model you already hardened |
| **C. Staged pipeline with a durable workspace** | Worker orchestration is rewritten; engine, sealing, Base44 and UI stay | Batch count | **Recommended** |

What stays untouched in C: the ScanRun durable model and attempt fencing, HMAC-sealed authority, the single review engine, robots/SSRF, admission, the 60-page/100-finding signed payload, and the UI.

What C costs: it is a real rewrite of worker orchestration, and this project's incidents have come from rollouts, not designs. If 500 pages is the only goal, A is materially less work. C is worth it if 5,000 is a real target, and it also gives you true progress, resume after failure, re-review without re-crawling, and watchdog timers that no longer depend on scan size.

## 2. Target architecture

```
Base44 startStandardScanJob (V9)
  └─ Cloud Tasks: entry queue (existing) ──► POST /scan-job      = PLAN stage
                                               robots, landing, sitemaps,
                                               homepage links, importance,
                                               selection → plan.json
       ┌───────────────────────────────────────┘
       ▼  Cloud Tasks: stage queue (new), tasks enqueued by the worker
  POST /scan-batch  {scan_id, attempt, batch}   = FETCH stage, 50 URLs
       load plan + frontier → fetch → write pages → CAS frontier
       → progress heartbeat to Base44 → enqueue next batch
       (repeat: 150 = 3 batches, 500 = 10, 5,000 = 100)
       ▼
  POST /scan-finalize {scan_id, attempt}        = ASSEMBLE stage
       load all batches → probes + canonical checks → findings
       → review (isolated process, as now) → seal → Base44 (unchanged)
```

**Workspace** (new GCS bucket, one prefix per attempt: `scans/{scan_id}/a{attempt}/`):

| Object | Content | Write rule |
| --- | --- | --- |
| `plan.json` | Scope, robots snapshot, budget, ordered selection with importance, batch manifest | Create-only (`ifGenerationMatch=0`) |
| `inventory.jsonl.gz` | Every discovered URL with its signals | Create-only |
| `batches/{n}.pages.jsonl.gz` | Page evidence dicts, same shape as today's `pages` items | Create-only |
| `frontier.json` | Seen set, final-URL identity map, discovery graph, pacer state, counters | Compare-and-set on generation |
| `merges.jsonl` | Cross-batch duplicate merges, applied at finalize | Append per batch |
| `result.json.gz`, `review.json.gz` | Assembled result and review output | Create-only |

**Design rules**

1. **Sequential chain, not fan-out.** One batch at a time per scan. The limit is how fast the target site tolerates requests, and the rate-limit pacer needs continuous state. Parallelism stays across scans.
2. **Idempotency by compare-and-set.** A batch commits by updating `frontier.json` with the generation it read. A duplicate delivery loses the CAS and exits 200 without side effects. Next-task names are deterministic (`{scan_id}-a{attempt}-b{n}`) so Cloud Tasks drops duplicates.
3. **Every stage re-checks the fences** already in `scan_job.py`: `identity_matches`, `is_superseded_attempt`, `already_terminal`.
4. **Liveness is per batch.** Each committed batch writes `pages_crawled` and `worker_heartbeat_at`. The watchdog question becomes "no batch committed in N seconds", which is independent of page count.
5. **A stalled scan with evidence finishes as `limited`.** The reconciler enqueues `/scan-finalize` when at least one batch exists, instead of writing a bare failure.
6. **Wall-clock budgets only.** `scan_timing.py` uses `time.monotonic()`, which is meaningless across processes. Budgets move to wall-clock timestamps stored in the plan.

## 3. Roadmap

Each phase ships on its own and has a gate. Phases 1–4 need no new infrastructure. Effort is relative: S, M, L.

| Phase | Effort | New infra | What clients get |
| --- | --- | --- | --- |
| 0. Baselines | S | No | Nothing visible |
| 1. Selection v8 | M | No | Every section of a big site is covered; fixes ordered by pages that matter; honest coverage line; template-level "fix once" estimates |
| 2. Split `run_scan` | M | No | Nothing visible |
| 3. Priority frontier | S–M | No | Throttled or cut-short scans still cover the most important pages |
| 4. One page cap | M | No | Nothing visible (cap stays 150) |
| 5. Staged execution | L | Bucket, queue | Real progress, resume after failure, partial result instead of failure, reliable rescan comparison |
| 6. 500 tier | S | No | 500-page scans; stronger "affects N pages" confidence |

### Phase 0 — Baselines and live-config check (S)

- Confirm deployed values, since the repo and memory disagree in places (max-instances 20 vs 40, queue concurrency):
  ```
  gcloud run services describe fixlist-standard150-worker --region=europe-west1 --project=seo-autopilot-501517 --format="yaml(spec.template.spec.timeoutSeconds,spec.template.spec.containerConcurrency,spec.template.metadata.annotations)"
  gcloud tasks queues describe fixlist-standard150 --location=europe-west1 --project=seo-autopilot-501517
  ```
- Benchmark `review.py` at 150, 500 and 1,000 pages (extend `scanner-api/benchmark.py`); record wall time against the 20 s `LOCAL_REVIEW_WALL_TIMEOUT_SECONDS`.
- Measure average serialized size of one page evidence dict (drives finalize memory and bucket cost).
- Freeze golden outputs for the fixture corpus (`scanner-api/tests/fixtures`) at the current commit.

**Gate:** numbers written down; no code merged.

### Phase 1 — Selection v8: importance and section quotas (M)

Blueprint §3.1–3.2. New `page_importance.py`; `sampling.py` partitions by section with square-root quotas and hash tie-breaks; `sitemap.py` keeps `lastmod`. Feed `importance_score` into the existing four-factor fix priority, and emit per-pattern sample and inventory counts so the review can state template-level estimates (blueprint §3.7).

**Gate:** the synthetic site from the blueprint gets at least 3 pages in every section at both 149 and 499; determinism test; no regression on Funbooker, Pretto, Center Street Lending, Norris Wines.

### Phase 2 — Split `run_scan` in place (M)

No behaviour change. This is the phase that makes everything after it safe.

- Introduce a `ScanState` dataclass holding what are now locals: `queue`, `queued`, `seen`, `final_pages`, `discovery`, `artifacts`, `scope_evidence`, `sampling_evidence`, `sitemap_diagnostics`, coverage counters, `crawl_state`, pacer state, origin/prefix/market hint, robots snapshot.
- Extract three functions: `plan_scan() -> ScanState`, `crawl_batch(state, urls) -> pages`, `finalize_scan(state, pages) -> result`. `run_scan` becomes plan → loop → finalize, still in one process.
- Make `_AdaptiveRateLimitPacer` and the robots policy serializable (`to_dict` / `from_dict`).
- Replace in-place `merge_duplicate_page_evidence` across batches with a recorded merge list applied in `finalize_scan`.
- Add a test flag that JSON round-trips `ScanState` between every batch.

**Gate:** all existing tests pass; fixture outputs identical to the Phase 0 goldens with and without the round-trip flag.

### Phase 3 — Priority frontier and two passes (S–M)

Blueprint §3.3. Heap keyed on `(-importance, url)`; pass 1 is homepage, navigation set and section heads; remaining candidates are re-scored on observed inlinks before pass 2.

**Gate:** truncating a crawl at 30% of budget still contains the homepage, every navigation-set page and every section head.

### Phase 4 — Cap as one server-owned value (M)

Blueprint §3.4. One mode → `page_cap` table; replace the roughly 20 Python literals and raising guards; Base44 V9 function generation whose validators read the cap from the record, bounded by a server maximum; frontend literals and copy read `page_cap`. Cap value remains 150.

**Gate:** signed payload for a fixture scan is byte-identical before and after.

*Shortcut available here:* after Phase 4 you can ship a 500 tier on option A by raising `ASYNC_JOB_TIMEOUT_CEILING`, the worker fuses, Cloud Run `--timeout` and the Tasks dispatch deadline to about 720 s, and retuning heartbeat drain, terminal drain and admission lease (values in blueprint §3.5). I would only do this if revenue needs 500 before Phase 5 is done, because those timers get retuned again afterwards.

### Phase 5 — Workspace and staged execution (L)

Infrastructure (run once; check flags against your gcloud version):

```
PROJECT=seo-autopilot-501517; REGION=europe-west1
WORKER=fixlist-standard150-worker@$PROJECT.iam.gserviceaccount.com
INVOKER=fixlist-standard150-invoker@$PROJECT.iam.gserviceaccount.com
BUCKET=gs://fixlist-scan-workspaces-$PROJECT

gcloud storage buckets create $BUCKET --project=$PROJECT --location=$REGION --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update $BUCKET --lifecycle-file=lifecycle.json   # delete objects after 30 days
gcloud storage buckets add-iam-policy-binding $BUCKET --member=serviceAccount:$WORKER --role=roles/storage.objectUser

gcloud tasks queues create fixlist-scan-stages --project=$PROJECT --location=$REGION --max-concurrent-dispatches=40 --max-attempts=3 --min-backoff=10s --max-backoff=120s
gcloud tasks queues add-iam-policy-binding fixlist-scan-stages --project=$PROJECT --location=$REGION --member=serviceAccount:$WORKER --role=roles/cloudtasks.enqueuer
gcloud iam service-accounts add-iam-policy-binding $INVOKER --project=$PROJECT --member=serviceAccount:$WORKER --role=roles/iam.serviceAccountUser
```

Code:

- `workspace.py`: read/write with generation preconditions; add `google-cloud-storage` to `requirements.txt`.
- `stage_tasks.py`: enqueue to `fixlist-scan-stages` with OIDC as the invoker SA and deterministic task names.
- `main.py`: `/scan-job` runs the plan stage; new `/scan-batch` and `/scan-finalize`, both behind `require_cloud_tasks_oidc`. Per-request budget stays far below 480 s, so Cloud Run and Tasks timeouts do not change.
- `durableScanWorkerControl` V9: `progress` action writing `pages_crawled`, `pages_planned`, `worker_heartbeat_at`.
- Reconciler (`reconcile_stale_scans`): stalled scan with at least one committed batch → enqueue finalize as `limited`.
- `deleteCustomerScanData` V9: also delete the workspace prefix. Without this, customer deletion leaves evidence in GCS.
- Queue contract assertions in `post_deploy_verify.sh` and the gateway boot check learn about the third queue.
- Frontend: `scanProgressModel` uses `pages_planned` as the denominator.
- Flag `SCAN_PIPELINE_MODE = monolith | staged`, routed per owner with the existing canary cohort mechanism.

**Gate:** fixture parity between monolith and staged at 150; kill the worker mid-batch and confirm the redelivery resumes without duplicate pages; deliver the same batch task twice and confirm one commit; owner-test cohort runs the four reference sites end to end with `durable_worker_owned: true`.

### Phase 6 — 500 tier (S)

Mode `standard_500` = 10 batches. Entitlement sets `page_cap`; copy updated; canary cohort first; scan-level wall budget of about 10 minutes, after which the scan finalizes with what it has.

**Gate:** 50-site corpus at 500; throttled sites end as prioritized `limited` results, not failures.

### Phase 7 — Toward 5,000 (not scheduled)

Needs, beyond more batches: sitemap discovery past the 5,000-URL cap, review cost that scales (Phase 0 numbers decide), more finalize memory than 1 Gi, and a decision on whether page-level evidence is shown in the UI or stays in the workspace.

## 4. Risks

| Risk | Mitigation |
| --- | --- |
| Rollout, mixed generations (seen before with Base44/worker drift) | V9 functions deployed and verified before the flag flips; flag is per owner |
| Cross-batch state bugs (dedup, pacer, counters) | Phase 2 JSON round-trip gate catches these before any infrastructure exists |
| Extra latency on small scans from per-batch dispatch and storage reads | Unmeasured. Measure in Phase 5 shadow runs; raise batch size if needed |
| Evidence at rest in a new store | Private bucket, 30-day lifecycle, deletion wired into `deleteCustomerScanData` |
| Worker gains permission to enqueue tasks | Scoped to the stage queue only; target URL pinned in code |
| Template-level estimates read as measured facts | Always shown with the sample count and inventory count behind them (blueprint §3.7) |

## 5. Not verified

- Live GCP configuration; no access from this session.
- Review and memory behaviour above 150 pages.
- That the fixture harness can replay fetches deterministically enough for byte parity; if not, Phase 2 starts by adding a recorded-response fetcher.
- Admission coordinator deployment state (the repo doc says not wired in; `startStandardScanJobV8` imports the client).

## 6. Extensions that turn the plumbing into a product advantage

The staged pipeline is infrastructure. These three build on it and are where FixList could differ from tools that sell "pages crawled". None is validated with customers yet, and I have not checked what competitors ship today.

### 6.1 Adaptive template sampling (after Phase 3; best after Phase 5)

Because the plan can be revised between batches, the scan can stop spending pages where it has learned enough.

- After each batch, group fetched pages by route pattern and compare their findings.
- A pattern whose last N samples agree (start with N = 5) is marked settled; its remaining budget moves to patterns that disagree or have not been sampled.
- Result: a fixed budget describes a much larger site. 150 pages can truthfully report on a 20,000-page templated site as "9 page types, 3 with problems", each with its sample count.
- Constraint: stays deterministic. The stop rule is a fixed threshold on recorded evidence, with no model in the loop.

**Gate:** on the synthetic site and the reference sites, the adaptive plan finds every template-level issue the fixed plan finds, using fewer pages on uniform templates.

### 6.2 Self-checking fix list (Phase 5)

Stored page evidence plus the existing `targeted_fix_verification` modules allow a closed loop.

- Client marks a fix as done; FixList re-fetches only that fix's affected pages (a single batch) and answers "confirmed fixed", "still there" or "fixed on 9 of 12".
- No full rescan, no waiting, and the result is evidence-backed.
- This is the feature a non-technical owner or their web person feels directly: the list checks their work.

**Gate:** verification of one fix completes in a single batch and never changes the sealed result of the original scan; it writes a separate, signed verification record.

### 6.3 Watch the pages that matter (after Phase 5)

The plan already names the homepage, navigation set and section heads (about 15–25 pages).

- Re-fetch only those weekly, compare against stored evidence, and alert on regressions such as a lost title, a new noindex, or a page that started redirecting.
- Cost per check is one small batch, which makes a low monthly price viable alongside the one-time scan.
- Needs a retention decision: the 30-day workspace lifecycle must keep the latest baseline for watched sites.

**Gate:** zero false alerts across two weeks on the four reference sites before any customer sees an alert.

### Suggested order

6.2 first (smallest, most visible, reuses existing modules), then 6.1 (largest effect on big sites), then 6.3 (changes the business model, so it is a pricing decision as much as an engineering one).

## 7. Front end: keep the complexity in the backend

The fixes are complex; the screen should not be. The backend already ranks fixes (four-factor priority) and writes steps, so the front end only has to show less.

**First screen, nothing else above the fold:**

1. One sentence of status: "We checked your 150 most important pages. 3 things are worth fixing first."
2. **Top 3 fixes**, each as one card with five fields only:
   - Plain title ("Your store pages have no description for Google")
   - Why it matters, one line
   - Who does it: You / Your web person
   - Size: "about 400 pages, one template change"
   - One button: **Show me how** (expands the steps) and, for developer fixes, **Send to my web person** (copies a ready-made brief)
3. One link: "See all N fixes", grouped by page type, collapsed by default.

**Rules for picking the top 3 (server-side, deterministic):**

- Highest priority score first, using importance of affected pages.
- At most one fix per root cause or template, so the three are different problems.
- At least one must be doable by the owner if any such fix exists, so there is always a first step they can take today.

**What moves off the first screen:** score breakdowns, coverage tables, passed checks, evidence detail. All stay available under "See all" and in exports.

**Later, with 6.2:** each card gets "I fixed this", which re-checks and answers in plain words.

This is presentation only and can ship before any scanner phase.

## 8. "The build misses a lot": measure before fixing

I have not measured what is being missed, so these are candidate causes from the code, in the order I would check them:

| Candidate cause | Evidence in code | Addressed by |
| --- | --- | --- |
| The page was never scanned | Whole sections get zero pages; homepage links ignored (blueprint F1, F2) | Phase 1, Phase 3 |
| The issue exists on fewer than 3 sampled pages of a type | `GROUP_MIN_AFFECTED = 3` in `scanner.py` gates template grouping | Phase 1 (more samples per pattern), then review the threshold |
| Findings are trimmed before sealing | 60 pages and 100 findings in the signed payload (`scan_job.py:133-134`); whether this drops customer-visible fixes needs tracing | Trace in Phase 0 |
| Content is rendered by JavaScript | Render evidence is informational only | Separate decision |
| No rule exists for the issue | Rule coverage versus Screaming Frog is untested here | Parity harness |

**How to find out which:** pick one reference site, run Screaming Frog on the same 150 URLs FixList scanned, and sort every issue Screaming Frog reports into one of the five rows above. Add this to Phase 0. The split tells you whether to spend effort on selection, thresholds or rules.

## Sources

- [Cloud Run: set task timeout for jobs](https://docs.cloud.google.com/run/docs/configuring/task-timeout)
- [Cloud Run quotas and limits](https://docs.cloud.google.com/run/quotas)
- [Cloud Tasks REST reference: tasks](https://docs.cloud.google.com/tasks/docs/reference/rest/v2beta3/projects.locations.queues.tasks)
