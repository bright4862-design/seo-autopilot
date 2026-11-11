# Stage queue operations and the path to one staged-150 owner scan

Status on 11 November 2026, from `main` `c7d71a0272866f03795862bad76cc502a51c46ca`:
code and local tests only. Nothing here was run against live infrastructure.

## Why the stage queue is on the critical path

`/scan-job` runs only the `plan` stage. Every later stage goes through
`fixlist-scan-stages`. That includes every 50-page batch and the finalize step,
whether it comes from the last batch or from the drain watchdog's limited
finalize (`stage_tasks.STAGE_ROUTES`, `enqueue_staged_partial`).

The queue is provisioned PAUSED. While it stays paused, a staged scan plans,
enqueues batch 1 and goes no further. Even its watchdog finalize waits in the
same paused queue. So a staged scan cannot reach a signed result until this
queue is RUNNING.

The existing cutover controls (`cutover-pause` and `cutover-resume`) handle
only the entry and drain queues and the reconciler.

## Tool: `scripts/operate-staged-queue.sh`

Every operation pins the project, region, worker, gateway, bucket, both service
accounts and the stage queue. It refuses any override. Every operation requires
the exact current `main` (`release-source-guard.sh`). It never deletes or purges
tasks, never deletes the queue, and never touches the entry or drain queues,
traffic, IAM, secrets, Base44 or the admission barrier.

| Operation | Confirmation | Preconditions read live | Action |
|---|---|---|---|
| `status` | none | none (read only) | Reports the stage queue state and the task count in every queue. With `STAGED_REVISION`, also runs a full candidate readback plus `verify_staged_scan_infra.py`, using `--task` when a task exists so per-task OIDC is checked. |
| `activate` | `ACTIVATE-STAGED-QUEUE:<sha>:fixlist-scan-stages:<revision>` | See the activation checks below. | `resume`, then the verifier again, which must report RUNNING. |
| `drain-pause` | `DRAIN-PAUSE-STAGED-QUEUE:<sha>:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF` | Queue is RUNNING. Staged intake is off on every addressable worker revision and on the serving gateway. The stage, entry and drain queues are all empty for N consecutive reads. | `pause`. If any task appears afterwards, the tool resumes the queue and fails. |
| `recover` | `RECOVER-STAGED-QUEUE:<sha>:fixlist-scan-stages:BASE44-STAGED-INTAKE-OFF` | Queue is PAUSED. Staged intake is off. | `resume`, so that admitted scans can finish. The tool never pauses during recovery. |

**Activation checks.** `activate` refuses unless all of the following read back
live:

- The queue is PAUSED and holds no tasks. If it holds tasks, use `recover`.
- `STAGED_REVISION` is an addressable revision receiving 0% of traffic.
- That revision runs as the worker service account.
- It declares an exact `FIXLIST_WORKER_SOURCE_SHA`.
- It carries the tag `staged-<source12>`.
- It enqueues to the fixed queue path.
- Its target URL is that tag's own URL.
- Its audience is the canonical service origin.
- Its invoker is the fixed invoker, and it has a workspace bucket.
- Its cohort is empty or lists at most five exact owner IDs, never `*`.
- No other addressable revision admits staged scans.
- `verify_staged_scan_infra.py --expected-queue-state PAUSED` passes.

**Pausing is the dangerous direction.** A paused stage queue strands admitted
scans in the middle of their pipeline. The tool therefore requires new intake
to be off *first*. It then requires all three queues that can create stage
tasks to stay empty (entry for plan, stage for batches, drain for the watchdog
finalize), and only then pauses. If the drain does not finish within
`STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS` (default 900, maximum 3600), the queue is
left RUNNING.

**Base44 can't be checked from here.** GCP cannot read Base44's
`SCAN_PIPELINE_MODE` or `SCAN_STAGED_OWNER_IDS`. The drain and recover
confirmations therefore make the operator attest
`BASE44-STAGED-INTAKE-OFF`. Do that only after Base44 staged intake is off, or
after the admission barrier is verified closed with zero obligations
(`barrier-status`).

**Not wired into the Cloud Operator workflow.** Adding an `operation` choice and
an environment block is a separate, reviewable workflow change. Until then, an
operator with queue pause/resume rights runs the tool at the exact `main`
commit.

```bash
SOURCE_SHA=$(git rev-parse HEAD) OPERATION=status STAGED_REVISION=fixlist-standard150-worker-NNNNN-xxx \
  bash scripts/operate-staged-queue.sh
```

Tests: `python3 -m pytest -q tests/test_operate_staged_queue.py`. These run a
stateful fake `gcloud` and a stub verifier. They are not evidence of live
behavior.

## Fastest verified path to one staged-150 owner scan

Each step is labeled **[code]** (repository work), **[owner/GCP]** (needs an
authorized live action) or **[tool]** (an existing guarded operation).

1. **[owner/GCP]** Finish the partial bootstrap in
   `staged-rollout-blockers-2026-11-11.md`:
   - set the bucket lifecycle and bucket IAM;
   - create the stage queue, pause it, then grant queue IAM;
   - grant the worker `serviceAccountUser` on the invoker.

   Then run `verify-staged-scan-infra`, which must pass with the queue PAUSED.
   The GitHub operator lacks `storage.buckets.update`. It probably also lacks
   `cloudtasks.queues.resume`/`pause` on the new queue; grant that narrowly,
   or have an administrator run this tool.
2. **[owner/GCP]** Confirm the outcome of the V9 publisher run
   [43094215294](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094215294),
   which stopped at device login, and its readiness artifact. Then apply the
   reviewed additive schema, which needs explicit owner authorization.
3. **[code]** Land the explicit worker cohort (PR #411; not duplicated here) and
   the Codex `codex/fable-architecture-completion` fixes the owner considers
   required for 150. Staged 150 does not need the 500 path.
4. **[tool]** Build a worker candidate with `stage_config=inactive` from the
   merged SHA. The current `00104-l79` has no staged configuration. Then tag
   and verify it, and deploy the gateway with the staged contract.
5. **[owner/GCP]** Admission: read a fresh `barrier-status`, resume the drain
   plane (claims stay closed), open an acceptance-only cohort for one owner
   with a budget of one, and enable Base44 V9 staged mode for that exact owner.
6. **[tool, this PR]** `OPERATION=activate` with the exact staged revision.
7. **[tool]** Run `scripts/run-staged-owner-canary.sh` once with
   `EXPECTED_PAGE_CAP=150`.
8. **[tool, this PR]** After the result is verified, turn staged intake off
   (Base44, gateway and worker cohort). Then run `drain-pause`, close admission,
   and restore the gateway.

Steps 1, 2 and 5 are external, owner-authorized actions. No code change
removes them.
