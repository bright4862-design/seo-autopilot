# Staged large-site scans implementation plan

**Goal:** Implement the supplied selection blueprint and phased staged-execution roadmap in the existing repository, with production activation separate from local implementation.

**Architecture:** Preserve the existing monolith entry point and signed authority bounds. Extract a serializable crawler state and sequential batches, with attempt-scoped GCS checkpoints and deterministic Cloud Tasks continuations. V9 functions own new cap/progress contracts; historical result formats remain readable. Release metadata is regenerated across packages; historical readers receive the prior fingerprint in their compatibility registry.

**Tech stack:** Python/FastAPI, GCS, Cloud Tasks, Base44/Deno, React/Vite.

**Specifications:** [Blueprint](../../scanning/fixlist-large-site-scan-blueprint.md), [roadmap](../../scanning/fixlist-staged-scan-architecture-roadmap.md).

## Constraints and decisions

- Default remains 150 pages and eight concurrent fetches. The legacy compatibility payload remains bounded at 60 pages/100 findings; the active durable completion retains the full assessed page population needed by GEO, with authority repairs bounded at 100. Per-fix affected URL lists remain bounded at 150; total counts are separate.
- A customer request never chooses its cap. Only trusted entitlement/ScanRun data admits 500 pages, and only through staged execution.
- Preserve robots/SSRF, attempt/identity fences, terminal immutability, evidence privacy, and existing allowance accounting.
- Use immutable per-execution artifacts referenced by committed frontier state, generation CAS, a bounded stage lease, and replayable next-stage intent. GCS has no append operation.
- Section floors and early coverage guarantees apply when enough distinct URLs and budget exist; report uncovered sections rather than inventing URLs.
- No live GCP configuration or live benchmark claims without access. Infrastructure scripts prepare reviewable deployment commands and runbooks.
- Roadmap Phase 7 and explicitly future product extensions (adaptive stopping, targeted rechecks, weekly watches) remain future work.

## Work and verification

- [x] Establish baseline: run existing Python and frontend tests, benchmark review at 150/500/1000, record offline limits and live-config blockers.
- [x] Selection: deterministic importance, section quotas, pattern spread, lastmod diagnostics, capped inventory. Test synthetic149/499, locale/order independence, tiny/many sections, recognized commercial routes.
- [x] Engine: extract plan/crawl_batch/finalize and JSON state, serialize robots/pacer/wall deadlines, prioritize entry/nav/section heads and re-score observed inlinks. Test restored state against uninterrupted scans and redirect dedup.
- [x] Cap contract: central mode table with trusted execution context, assessed-page guards, signed mode/cap metadata only for V9, privacy allowlists, importance in priority factors. Test default150 rejection and trusted500 acceptance; preserve legacy envelope bytes.
- [x] Base44 V9: entitlement-owned caps, progress, bounded validation/projection, cancellation before workspace deletion. Test cross-owner/attempt rejection and historical compatibility.
- [x] Workspace/stages: storage preconditions, sequential tasks, commit recovery, liveness, stalled partial finalization, V9 completion. Test crashes/duplicates, terminal/superseded fences and wall expiry.
- [x] UI: trusted cap copy/limits, real batch progress, concise first actions and expandable complete list. Test legacy and planned progress plus evidence-only claims.
- [x] Integrate all changes, inspect diff, run complete relevant Python/frontend suites, lint/build, and independent review. Record exact outcomes and remaining deployment gates.

Fresh results and remaining live rollout gates are recorded in [implementation verification](../../scans/implementation-verification.md).
