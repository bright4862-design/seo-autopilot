# Staged scan implementation verification

Implemented against `689a7fb43825f322af70188e7426730552daebd9` on 11 November 2026. Candidate fingerprint: `1470ccb6398a7f4f`.

## Local checks

| Check | Result |
| --- | --- |
| Scanner: `cd scanner-api && ../.venv/bin/python -m pytest -q` | 2,575 passed, 18 skipped |
| Repository: `.venv/bin/python -m pytest -q tests` | 481 passed |
| Gateway: `cd dispatch-gateway && ../.venv/bin/python -m pytest -q test_gateway.py` | 51 passed |
| Frontend: Node 20.19.5, `node --test tests/frontend/*.test.mjs`, with the Python venv on PATH | 2,032 passed |
| `npm run lint`, `npm run typecheck`, `npm run build` | Passed |
| Revision freeze, generated contracts, staged Base44 package manifest and `git diff --check` | Passed |

The frontend suite uses the repository's CI Node version. The environment's Node 24 has two pre-existing IDNA fixture differences, also reproduced from an unchanged archive of the base commit.

## Architecture evidence

- The real engine completes a 500-page fixture in ten committed batches, retains 500 unique pages, and ignores a duplicate finalize delivery. Its actual isolated review runs under the unchanged 20-second ceiling. The resulting V9 authority snapshot survives writer rows, customer-reader reconstruction and HMAC verification.
- The expanded fixture exposed repeated page/identity indexing in review. Reusing review-scoped indexes and a bounded cache of pure origin normalization reduced actual 500-page isolated review to 10.56 seconds, with 116.7 MB measured peak review-child memory. This excludes the worker parent's concurrent memory and is not a production-site benchmark.
- Full 150-page review output remained byte-identical across the indexing optimization (2,726,969 bytes compared). Five archived review fixtures also retain their recorded hashes.
- Recovery checks cover artifacts written before frontier commit, failures before/after task enqueue, duplicate deliveries, lease expiry, superseded/terminal attempts, progress replay, cached review reuse and deletion across attempts.
- The stage queue uses ten attempts rather than the draft's three, so retries outlast a crashed worker's 450-second lease. Controlled failures release their own lease. The existing drain queue handles asynchronous deletion after the tombstone's drain period.
- V9-only transport compaction removes identical aliases without truncating the assessed page population. The representative completion fixture shrank from 12,380,935 to 7,172,726 compact JSON bytes; authority snapshots before and after compaction compare equal. Full result and review objects remain in the workspace.
- The blueprint's 60-page/100-finding statement describes the compatibility payload helper, not the active durable producer envelope. The implementation preserves that distinction and keeps authority repairs capped at 100 and affected URL samples at 150.

## Merged candidate deployment

The implementation and tagged-candidate authentication fix merged in [PR #406](https://github.com/bright4862-design/seo-autopilot/pull/406) and [PR #407](https://github.com/bright4862-design/seo-autopilot/pull/407). The deployed source is `4274ac453e93fe2e161e01c88d31823bd5134795`.

On 11 November 2026, the existing GitHub Cloud Operator authenticated through GCP workload identity and completed:

| Operation | Evidence |
| --- | --- |
| Build and deploy exact merged source | [Run 43089277776](https://github.com/bright4862-design/seo-autopilot/actions/runs/43089277776): revision `fixlist-standard150-worker-00104-l79` ready, concurrency 1, timeout 480 seconds, traffic 0% |
| Tag exact revision without moving traffic | [Run 43089863245](https://github.com/bright4862-design/seo-autopilot/actions/runs/43089863245): `candidate` tag resolves to that revision, traffic remains 0% |
| Authenticated runtime and route verification | [Run 43090015295](https://github.com/bright4862-design/seo-autopilot/actions/runs/43090015295): tagged zero-traffic check, runtime release identity, exact source SHA, routes and timeout passed |
| Post-deployment live status | [Run 43090150954](https://github.com/bright4862-design/seo-autopilot/actions/runs/43090150954): existing revision `fixlist-standard150-worker-00097-lvl` still receives 100% traffic; entry and drain queues remain paused |

This deploys the worker code as an isolated candidate. It does not enable the staged pipeline, publish the V9 functions or frontend, or establish end-to-end scan acceptance. The Base44 connector confirms an active GitHub connection; its current app sandbox remains at `624aaf1ae459c49b5f26a0f8a366044c348b79bb`, with V8 scanner packages and no V9 scanner packages in that source tree. Sandbox source is not proof of published function bytes.

## Rollout gates still pending

The stage bucket was created during the live bootstrap, but GCP denied the lifecycle update before the later queue and runtime-IAM steps completed. V9 publication still requires successful owner authentication and live package verification. No frontend was published or owner cohort enabled during this rollout. The existing production promotion check returns `PROMOTION_RECORD_BLOCKED: release_not_accepted_candidate`; the candidate release record is deliberately unchanged. [Live bootstrap evidence and remaining administrator commands](staged-rollout-blockers-2026-11-11.md) record the exact boundary.

The ordinary V8/site publishers require an accepted release record. The isolated V9 publishing path deploys and freshly compares only the six candidate packages, without changing the public site, V8 functions or the global source stamp. New bounded Cloud Operator operations provision/verify the fixed stage infrastructure, and the candidate build supports explicit inactive staged configuration at 0% traffic. Their complete live execution and a signed owner canary remain pending. The actual bootstrap denial confirms the GitHub operator lacks the bucket-update permission needed for this setup; subsequent resource permissions remain unverified.

Base44 request-size tolerance for representative completions, aggregate worker memory, the four live reference sites, the 50-site corpus and throttled production sites remain unverified. V8/monolith stays the default. Follow [the rollout runbook](staged-scan-runbook.md) for infrastructure, package verification, staged 150 first, then the entitled 500 cohort. Preserve the currently paused entry and drain queues until the existing controlled-cutover checks authorize resuming them.

Phase 7 and the roadmap's explicitly future product extensions remain outside this implementation.

## Inactive rollout control verification

The rollout follow-up adds isolated V9 publishing/read-back, bounded stage infrastructure operations, explicit inactive candidate configuration and an authenticated one-scan owner canary. Fresh local checks pass: 2,070 frontend tests on Node 20.19.5, 513 repository Python tests, lint, type checking, production build, generated contracts and the staged package manifest. Independent review found no blocker in the inactive deployment controls. These local checks do not establish live provisioning, V9 deployment or scan acceptance.

The full run exposed an existing timing-sensitive checkout test fixture. An unchanged `620cde6` archive reproduced its failure; under the same deterministic schedule, the old fake Stripe response fails because it omits requested expanded price data. The corrected fake supplies that data and preserves the concurrent-request convergence assertions. Production checkout code is unchanged.
