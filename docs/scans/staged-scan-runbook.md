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

Review the printed plan, then append `--apply` to execute it. This is a one-time bootstrap: creation fails if resources already exist. After a partial failure, inspect the resources and run only the outstanding reviewed commands; the script does not silently adopt or overwrite existing resources. The new stage queue is paused immediately after creation, before granting enqueue access; provisioning does not activate it.

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

1. Use the Base44 Release Publish workflow's `staged-v9-candidate` target, confirmed with `PUBLISH-BASE44-STAGED-V9:<exact-main-sha>`. It authenticates the configured owner through the existing ephemeral device login and publishes the six exact V9 packages under the names in `data/generated-staged-v9-routes.json`. The workflow checks complete package bytes and exact live build and activation IDs through both the authenticated SDK and external HTTP. The staged preview and the worker use those same names. Any package change generates a new name. A release may reuse a name only when its deployed package already matches byte for byte. Apply the reviewed additive entity schema separately before a real staged scan.
2. Deploy the worker containing staged endpoints, the workspace adapter and stage dispatcher. Preserve private invocation, attempt fences, SSRF/robots policy, signing secrets and existing admission controls.
3. Deploy the dispatch gateway that recognizes the staged 500 contract. Workspace deletion uses the existing signed gateway control/drain queue; it is not an unauthenticated direct bucket deletion endpoint.
4. Configure the new bucket and queue variables. Keep `SCAN_PIPELINE_MODE=monolith` until all three runtimes are verified.
5. Use the existing `scripts/post_deploy_verify.sh` release checks for the exact worker revision, traffic target, private IAM, timeout, entry/drain queues and signing configuration. Set `VERIFY_STAGED_SCAN_PIPELINE=1` with explicit `SCAN_WORKSPACE_BUCKET`, `SCAN_STAGE_QUEUE` and `SCAN_STAGE_TARGET_URL` to include the stage infrastructure checks. Run `verify-staged-worker-release` to prove all three signed POST routes from the exact deployed worker before opening the pilot window.

Do not run a deployment command that replaces environment variables without retaining the new stage settings. Existing build manifests use explicit environment lists; include the reviewed stage variables in the candidate deployment configuration.

The Cloud Operator has bounded `prepare-staged-scan-infra` and read-only `verify-staged-scan-infra` operations for the fixed FixList bucket, stage queue and service accounts. Provisioning requires `PREPARE-STAGED-SCAN-INFRA:<exact-main-sha>` and finishes by verifying a **paused** stage queue. It does not grant the operator broader permissions; an actual IAM denial requires an administrator to complete that narrowly scoped bootstrap.

For `build-worker-candidate`, set the `stage_config` workflow input to `inactive` to add the explicit bucket/queue settings without an owner cohort. The destination uses a source-bound tag `staged-<first-12-source-sha-characters>`, with the full source SHA and configuration verified against the revision. An existing tag cannot be rebound. OIDC keeps the canonical service audience. Mode `off` preserves the legacy candidate build. Inactive candidates remain at 0% traffic, use `SCAN_PIPELINE_MODE=monolith`, and have an empty staged owner list. The presence of the workspace bucket selects V9 control calls even in monolith mode; do not promote this configuration before the V9 release and live acceptance checks pass.

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

**Worker cohort build.** Run `build-worker-candidate` with
`stage_config=owner-canary` and `acceptance_owner_user_ids=<one exact owner
ID>`. Set `worker_cohort_confirm=STAGE-WORKER-OWNER-CANARY:<exact-main-sha>:<sorted-cohort-sha256>`.
The hash uses the gateway's definition: SHA-256 of the JSON array of sorted
owner IDs, with no spaces. The build:

- creates one 0%-traffic revision with the reviewed inactive environment,
  except `SCAN_PIPELINE_MODE=staged` and `SCAN_STAGED_OWNER_IDS=<owner>`;
- keeps `FIXLIST_STAGED_CONFIG_SHA256` as the **inactive-equivalent** digest,
  computed over the reviewed inactive environment, so a cohort cannot hide a
  change to any other staged setting;
- creates the immutable `staged-<sha12>` tag on that revision.

It refuses:

- more than one owner, a wildcard or the legacy `SCAN_PIPELINE_OWNER_IDS`;
- a mode override;
- a confirmation bound to another source or owner.

The tag can never be rebound, so do **not** build an `inactive` baseline from
the same source first. Build the owner-canary candidate once, from the exact
`main` you will activate from. Stage-queue activation stays a separate
barrier-gated operation (`staged-queue-activate`).

**Tagging runs in the wrapper, bound to the built image.**
`build-worker-candidate.sh` refuses before any cloud call unless `python3`,
`gcloud` and `git` are on `PATH`. Cloud Build no longer has a tag step,
because the unpinned Cloud SDK image stopped shipping `python3` (build
`7e3157ff` deployed its revision, then failed to tag it).

The wrapper then:

- reads the final build record (`--format=json --suppress-logs`) and requires
  `SUCCESS` with exactly one `sha256:` digest for `<image>:<source-sha>`;
- selects the single Ready revision of that source whose
  `status.imageDigest` is `<image>@<that digest>`;
- only then creates the `staged-<sha12>` tag through
  `staged_candidate_cloudbuild.py tag --revision=<it> --image-ref=<image@digest>`.
  The helper re-checks the same revision and digest, refuses an existing tag,
  and checks that the serving split and every other tag are unchanged.

A missing, malformed or mismatched digest, a failed build or two matching
revisions leave every tag untouched. The output reports
`WORKER_CANDIDATE_BUILD_ID` and `WORKER_CANDIDATE_IMAGE_DIGEST`. If tagging
fails after a deploy, the revision stays untagged at 0% traffic. Rebuild from
the repaired exact `main` rather than tagging it by hand.

Use the **same explicit owner IDs** in Base44, gateway and worker:

```text
SCAN_PIPELINE_MODE=staged
SCAN_STAGED_OWNER_IDS=OWNER_ID_1,OWNER_ID_2
```

Base44 grants `page_cap=500` only from an active server-owned entitlement; the browser cannot select it. Test staged 150 first, then grant the owner-test account 500 through the existing authorized administrative path. Do not set a wildcard cohort. The dispatch gateway independently requires the staged signed contract and matching owner cohort before admitting 500.

`scripts/run-staged-owner-canary.sh` submits one explicitly confirmed staged-150 request through the authenticated pinned CLI. Supply the exact source SHA, expected administrator owner ID, an existing matching project and target URL, `EXPECTED_PAGE_CAP=150`, a stable request ID and a new acceptance-output path. Its confirmation binds that source, owner, project and request ID. It verifies the authenticated user, project and existing active entitlement before starting, and never creates a project or grant. Reuse the request ID after a lost response. The filtered report requires verified authority, the current release fingerprint, staged batch progress, duration and measured memory; absent evidence prevents an acceptance claim. This canary does not configure a cohort, open public claims or freeze a production release.

An approved administrator can prepare the other approved administrator's exact cohort for a controlled browser startup scan. Use `prepare-owner` with the authenticated `STAGED_OPERATOR_USER_ID`, the exact `STAGED_OWNER_USER_ID` signed in to the scanner, and `STAGED_COHORT_TARGET_ROLE=admin`. A regular customer pilot uses a separate normal-role account.

Before expanding the cohort, verify:

- The four reference sites finish end to end with `durable_worker_owned: true`; compare 150-page monolith/staged fixtures and the expected signed authority bounds.
- A 500 entitlement yields ten sequential batches, real committed-page progress and at most 500 assessed pages. The legacy `build_authority_review_payload` compatibility helper keeps its 60-page/100-finding sample bounds. Actual durable completion signs the projected retained-page evidence used by review, including all GEO observations; it does not use that compatibility helper. Measure the actual completion payload size at 500. Per-fix affected-page lists remain bounded at 150 with a separate true count.
- Duplicate tasks, killed workers and an enqueue failure after a frontier commit recover without duplicate committed pages or allowance charges. Superseded/cancelled attempts cannot commit or finalize.
- A throttled site with committed evidence finishes `limited`, and the progress denominator comes from `pages_planned`.
- Deleting terminal scan history writes a scan-wide tombstone, drains active leases for 450 seconds, and completes workspace cleanup across every attempt before deleting the customer record; transient cleanup failure remains retryable and does not claim deletion succeeded.
- Review wall time and aggregate worker memory fit the current limits on representative 500-page evidence. Run the 50-site selection/coverage corpus before enabling the 500 tier broadly.

After the reviewed 500-cap corpus reaches terminal outcomes, run the read-only verification from the exact source checkout with full Git history and read access to its private GCS workspace. Put the scanner's Python environment first on `PATH` and use a new output path outside the checkout.

```sh
node scripts/run-staged-scan-corpus.mjs --verify-completed \
  --manifest /absolute/reviewed-corpus.json \
  --evidence-dir /absolute/private-corpus-journal \
  --output /absolute/corpus-verification.json
```

The verifier matches each saved plan to its scan attempt and verified receipt. It replays v7 and current selection at the same 150-page cap against each frozen inventory. It requires fewer omitted sections overall and preserves every section v7 selected on Funbooker, Pretto, Center Street Lending, and Norris Wines. The current 500-page selection is also compared against the signed selection readback for complete results. For throttled results, the signed limitation and priority order, completion receipt, and matched saved plan provide the evidence.

Review a corpus with sitemap inventories on all 50 sites so each can contribute to the coverage comparison. A crawl based on internal links can still produce a valid scan. If it has no sitemap inventory, preserve its terminal result and report the corpus comparison as unverified. Include a throttling case where the crawl can capture its sitemap inventory before the throttle forces a limited result.

Phase 7 (5,000-page scans), adaptive sampling, weekly monitoring and the separate signed targeted-verification product are future extensions. The 30-day lifecycle must be revisited before introducing a longer-lived monitoring baseline.

## Paid rollout

Rehearse the V9 route manifest with intake closed before switching the public site to V9. The publisher verifies the new V9 routes and keeps V8 available for earlier clients and in-flight results. Establish the ordinary-customer pilot on the exact V9 build before enabling the paid scope.

After draining all three queues and verifying the staged-capable canonical worker, use gateway configuration `paid` for staged 150. The gateway verifies the closed barrier and exact serving revision before promoting. Use `OPERATION=prepare-paid` in `scripts/operate-base44-staged-runtime.sh` with the exact merged `SOURCE_SHA`, approved `STAGED_OPERATOR_USER_ID`, serving `STAGED_GATEWAY_REVISION`, and `STAGED_PAID_PAGE_CAP=150`. Confirm with `PREPARE-BASE44-STAGED-PAID:<source>:<gateway-revision>:150`. The command checks the gateway that V9 actually uses, proves Base44 intake is closed before setting the paid scope, and reads both runtimes back. `OPERATION=status-paid` performs the same final checks without changing settings.

A named non-administrator pilot can exercise 500 with an approved, active 500-page grant. Verify the full scan and saved result on the existing staged pilot path. If an approved site lacks enough pages, `scanner-api/scripts/export_staged_500_fixture.py` prepares a 640-page synthetic site with a sitemap and robots file. It takes the controlled host's final HTTPS `--origin` and a new absolute `--output` directory. Host those files on the approved test origin to prove full-cap execution. The representative site corpus measures coverage and quality separately.

Once the 500 corpus and production checks pass, `paid-500` enables already-entitled 500 launches. Run `prepare-paid` for cap 500 after the gateway verifies its matching flag. New requests from a verified 500 holder receive a clear pause response if the 500 tier is disabled. Existing grants and in-flight attempts keep their original cap.

## Rollback and recovery

Close staged intake to stop new admissions. Keep the stage endpoints, queue, V9 functions and workspace available for attempts that already own a staged contract. Wait for the admission barrier and entry, stage, and drain queues to clear before changing the serving worker or removing its source tag. Existing sealed authority remains immutable.

When rolling back paid settings, run the Base44 operator's `disable` operation, then use `OPERATION=status-off` to verify that the exact V9 launcher sees both paid switches off and intake closed. Keep intake closed if that readback fails.

The periodic Scheduler calls the canonical service. Before opening normal staged intake, verify the promoted stage-capable worker with `scripts/verify-standard150-reconciler.sh`. Set `RECONCILER_EXPECTED_SOURCE_SHA` and `RECONCILER_EXPECTED_STAGED_CONFIG_SHA256` to the reviewed build values, with the same `TASKS_INVOKER_SERVICE_ACCOUNT` used by the Scheduler. The verifier checks that the canonical service and source-bound tag resolve to the same revision and that the Scheduler uses the canonical OIDC audience.

For a stalled attempt with committed batches, the watchdog records one replacement finalization task. A finished crawl reuses its saved result and review. An interrupted crawl finalizes its committed pages as limited. The watchdog retries finalization for 30 minutes, lets any outstanding save drain, then verifies the exact attempt's terminal state before acknowledging a timeout.

Watch committed batch count and heartbeat timestamps, enqueue errors, retry counts, workspace generation conflicts, limited-completion reasons and deletion cleanup failures. A stored page object by itself is not proof of a committed batch: only artifacts referenced by the committed frontier belong to the final result. Do not manually assemble or reseal results from orphan objects.
