# Staged large-site scans: deployment and acceptance

The repository implements the plan → sequential 50-page batches → finalize pipeline. Provisioning and rollout remain separate operator actions. The merged worker code is deployed as the authenticated, verified **0%-traffic** candidate `fixlist-standard150-worker-00104-l79` from source `4274ac453e93fe2e161e01c88d31823bd5134795`, through the existing GitHub Cloud Operator's GCP workload identity. Staged infrastructure, V9 publishing, owner-cohort activation and live scan acceptance remain pending. See [the implementation and deployment evidence](implementation-verification.md).

## Local evidence

- `review-baseline-689a7fb.json` records SHA256 hashes for five recorded scanner-fixture → review results, computed from an isolated `git archive` of commit `689a7fb43825f322af70188e7426730552daebd9`. This freezes the review seam, not fetch orchestration or signed completion bytes.
- `review-synthetic-benchmark.json` measures local review at 150, 500 and 1,000 pages in fresh processes, each bounded by 20 seconds. Measurements were about 0.10 / 0.26 / 0.47 seconds and 36–40 MB process peak RSS including review/envelope imports. Synthetic evidence averaged 644–648 JSON bytes per page. The actual completion-envelope builder produced about 974 KB at 500 pages; representative retained evidence may be substantially larger.
- These numbers exclude crawl, raw retained content, final assembly and aggregate parent-plus-review-child memory. The 1,000-page probe characterizes review scaling only; it is not an available scan entitlement. These establish a local smoke benchmark. They do not establish production throughput or the 500-page release gate.

Regenerate from the repository root:

```bash
.venv/bin/python scanner-api/benchmark_review.py --capture-goldens 689a7fb43825f322af70188e7426730552daebd9 --output /tmp/review-baseline.json
.venv/bin/python scanner-api/benchmark_review.py --output /tmp/review-benchmark.json
.venv/bin/python -m pytest -q tests/test_staged_scan_infra.py scanner-api/tests/test_benchmark_review.py scanner-api/tests/test_legacy_review_goldens.py
```

## Prepare infrastructure

Run this on an operator machine with a reviewed GCP identity. All arguments are explicit; the script defaults to printing the commands and configuration without executing `gcloud`.

```bash
python3 scripts/prepare_staged_scan_infra.py \
  --project seo-autopilot-501517 \
  --region europe-west1 \
  --bucket fixlist-scan-workspaces-seo-autopilot-501517 \
  --queue fixlist-scan-stages \
  --worker-sa fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com \
  --invoker-sa fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com \
  --worker-url https://YOUR-WORKER.run.app
```

Review the printed plan, then append `--apply` to execute it. This is a one-time bootstrap: creation fails if resources already exist. After a partial failure, inspect the resources and run only the outstanding reviewed commands; the script does not silently adopt or overwrite existing resources.

The plan creates:

- A private GCS bucket with uniform access, public access prevention, and an unconditional 30-day object deletion policy.
- A stage queue with concurrency 40 across scans, ten delivery attempts, 10–120 second backoff, four maximum doublings and a 1,800-second retry duration. Each scan remains a sequential chain; crawl concurrency stays eight.
- `roles/storage.objectUser` for the worker on this bucket, `roles/cloudtasks.enqueuer` on this stage queue, and `roles/iam.serviceAccountUser` on the invoker account. It adds no project-wide grant.

The existing invoker must already have `roles/run.invoker` on the private worker; the Cloud Tasks service agent must already be able to mint its OIDC token. Preserve the existing entry/drain queues and their identity controls. Queue settings cannot prove per-task identity or deadline: tasks are created by `stage_tasks.py` with a pinned stage URL, the worker origin as OIDC audience, the existing invoker, and a 480-second dispatch deadline.

The draft roadmap's three-attempt stage queue is intentionally increased to ten. A killed worker retains its 450-second stage lease; three deliveries at approximately 0, 10 and 30 seconds could exhaust retries before another worker can claim it. With the pinned backoff policy, retries remain available at approximately 510 seconds even without honoring `Retry-After`. Ordinary failures release their own lease; process death requires this retry window. The existing drain/cleanup queue's retry contract remains unchanged.

The script prints these worker environment values. Apply them through the existing reviewed deployment mechanism while retaining its existing environment and signing secret:

```text
SCAN_WORKSPACE_BUCKET=fixlist-scan-workspaces-seo-autopilot-501517
SCAN_TASKS_PROJECT=seo-autopilot-501517
SCAN_TASKS_LOCATION=europe-west1
SCAN_STAGE_QUEUE=fixlist-scan-stages
SCAN_STAGE_TASKS_QUEUE_PATH=projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages
SCAN_STAGE_TARGET_URL=https://YOUR-WORKER.run.app
SCAN_STAGE_TOKEN_AUDIENCE=https://YOUR-WORKER.run.app
TASKS_INVOKER_SERVICE_ACCOUNT=fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com
```

Cloud Run and Cloud Tasks request deadlines stay at 480 seconds. Each staged HTTP handler has a 420-second outer bound, a 450-second lease and storage/task RPCs with a 20-second timeout and SDK retries disabled. Committed result and isolated review objects are cached separately, so persistence retries can reuse the completed review. A scan has a 600-second overall wall budget and finalizes committed evidence as a limited result when its budget expires. Longer site scans do not justify increasing request deadlines.

## Deploy without enabling customer traffic

1. Deploy and verify the V9 function generation and entity schema through the existing Base44 workflow. Keep V2–V8 available for historical records and in-flight jobs.
2. Deploy the worker containing staged endpoints, the workspace adapter and stage dispatcher. Preserve private invocation, attempt fences, SSRF/robots policy, signing secrets and existing admission controls.
3. Deploy the dispatch gateway that recognizes the staged 500 contract. Workspace deletion uses the existing signed gateway control/drain queue; it is not an unauthenticated direct bucket deletion endpoint.
4. Configure the new bucket and queue variables. Keep `SCAN_PIPELINE_MODE=monolith` until all three runtimes are verified.
5. Use the existing `scripts/post_deploy_verify.sh` release checks for the exact worker revision, traffic target, private IAM, timeout, entry/drain queues and signing configuration. Those checks remain required; the new infrastructure verifier supplements them. Set `VERIFY_STAGED_SCAN_PIPELINE=1` with explicit `SCAN_WORKSPACE_BUCKET`, `SCAN_STAGE_QUEUE` and `SCAN_STAGE_TARGET_URL` to include the new infrastructure verifier in the post-deploy check. Verify the V9 packages using `node scripts/base44_release_manifest.mjs verify --staged`, then compare a fresh deployed pull using its `compare <functions-directory> <entities-directory> --staged` command before enabling V9 frontend routing.

Do not run a deployment command that replaces environment variables without retaining the new stage settings. Existing build manifests use explicit environment lists; include the reviewed stage variables in the candidate deployment configuration.

## Read-only infrastructure verification

Use the same identity/resource arguments as preparation:

```bash
python3 scripts/verify_staged_scan_infra.py \
  --project seo-autopilot-501517 --region europe-west1 \
  --bucket fixlist-scan-workspaces-seo-autopilot-501517 --queue fixlist-scan-stages \
  --worker-sa fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com \
  --invoker-sa fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com \
  --worker-url https://YOUR-WORKER.run.app
```

This checks bucket privacy/lifecycle, explicit resource-scoped IAM and stage queue settings. It does not enqueue anything. Supply `--task EXISTING_TASK_ID` while an owner-test stage task exists to verify its exact URL, OIDC identity/audience and dispatch deadline. Without `--task`, these per-task settings are reported as **unverified**, even when infrastructure checks pass. Successful static verification does not establish that inherited project IAM is least privilege or that the deployed code matches the intended revision.

## Enable an owner cohort

For a tagged 0%-traffic candidate, set `SCAN_STAGE_TARGET_URL` to its tagged
origin and `SCAN_STAGE_TOKEN_AUDIENCE` to the canonical service origin. Pass
`--token-audience https://CANONICAL-SERVICE.run.app` to the preparation and
verification scripts. The target must be a tag belonging to that same service;
a tag URL is not a valid Cloud Run OIDC audience. Keep this mapping in place
while the candidate's stage tasks drain.

Use the **same explicit owner IDs** in Base44, gateway and worker:

```text
SCAN_PIPELINE_MODE=staged
SCAN_STAGED_OWNER_IDS=OWNER_ID_1,OWNER_ID_2
```

Base44 grants `page_cap=500` only from an active server-owned entitlement; the browser cannot select it. Test staged 150 first, then grant the owner-test account 500 through the existing authorized administrative path. Do not set a wildcard cohort. The dispatch gateway independently requires the staged signed contract and matching owner cohort before admitting 500.

Before expanding the cohort, verify:

- The four reference sites finish end to end with `durable_worker_owned: true`; compare 150-page monolith/staged fixtures and the expected signed authority bounds.
- A 500 entitlement yields ten sequential batches, real committed-page progress and at most 500 assessed pages. The legacy `build_authority_review_payload` compatibility helper keeps its 60-page/100-finding sample bounds. Actual durable completion signs the projected retained-page evidence used by review, including all GEO observations; it does not use that compatibility helper. Measure the actual completion payload size at 500. Per-fix affected-page lists remain bounded at 150 with a separate true count.
- Duplicate tasks, killed workers and an enqueue failure after a frontier commit recover without duplicate committed pages or allowance charges. Superseded/cancelled attempts cannot commit or finalize.
- A throttled site with committed evidence finishes `limited`, and the progress denominator comes from `pages_planned`.
- Deleting terminal scan history writes a scan-wide tombstone, drains active leases for 450 seconds, and completes workspace cleanup across every attempt before deleting the customer record; transient cleanup failure remains retryable and does not claim deletion succeeded.
- Review wall time and aggregate worker memory fit the current limits on representative 500-page evidence. Run the 50-site selection/coverage corpus before enabling the 500 tier broadly.

Phase 7 (5,000-page scans), adaptive sampling, weekly monitoring and the separate signed targeted-verification product are future extensions. The 30-day lifecycle must be revisited before introducing a longer-lived monitoring baseline.

## Rollback and recovery

Remove cohort owners or set `SCAN_PIPELINE_MODE=monolith` consistently across Base44/gateway/worker to stop new staged admissions. Do not disable stage endpoints, delete the stage queue, remove V9 functions or delete the bucket while admitted scans remain active. Let them finish or finalize committed evidence through the reconciler, then verify terminal records before removing infrastructure. Existing sealed authority remains immutable.

Watch committed batch count and heartbeat timestamps, enqueue errors, retry counts, workspace generation conflicts, limited-completion reasons and deletion cleanup failures. A stored page object by itself is not proof of a committed batch: only artifacts referenced by the committed frontier belong to the final result. Do not manually assemble or reseal results from orphan objects.
