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
traffic, IAM, secrets, Base44, worker revisions or tags, or the admission
barrier. It only *reads* the barrier, through the existing
`fixlist-cloud-operator.sh barrier-status`, which verifies the coordinator's
HMAC-signed snapshot.

| Operation | Confirmation | Preconditions read live | Action |
|---|---|---|---|
| `status` | none | none (read only) | Reports the stage queue state and the task count in every queue. With `STAGED_REVISION`, also runs a full candidate readback plus `verify_staged_scan_infra.py`, using `--task` when a task exists so per-task OIDC is checked. |
| `activate` | `ACTIVATE-STAGED-QUEUE:<sha>:fixlist-scan-stages:<revision>` | See the activation checks below. | `resume`, then the verifier again, which must report RUNNING. If that second verification fails, the tool prints `STAGED_QUEUE_PARTIAL_ACTIVATION observed_state=… tasks=…` and exits 3. It does not pause blindly. |
| `drain-pause` | `DRAIN-PAUSE-STAGED-QUEUE:<sha>:fixlist-scan-stages:<generation>`, with `BARRIER_EXPECTED_GENERATION=<generation>` | Queue is RUNNING. The signed barrier is `closed` at that generation, with `drain_ready=true` and `active`, `bound` and `live_reconciliation` all 0. The stage, entry and drain queues are all empty for N consecutive reads. The barrier is then read again. | `pause`, then the barrier and all three queues are read again. If anything changed, the tool resumes the queue and fails (`STAGED_QUEUE_PAUSE_COMPENSATED`). On success it prints `STAGED_QUEUE_PAUSE_PROOF generation=… snapshot=…`. |
| `recover` | `RECOVER-STAGED-QUEUE:<sha>:fixlist-scan-stages:<generation>`, with `BARRIER_EXPECTED_GENERATION=<generation>` | Queue is PAUSED. The signed barrier is `closed` at that generation; outstanding obligations are allowed. Every pending task passes the per-task identity check below. The verifier passes with the queue PAUSED. | `resume`, so that admitted scans can finish. The tool never pauses during recovery. |

**Activation checks.** `activate` refuses unless all of the following read back
live:

- The queue is PAUSED and holds no tasks. If it holds tasks, use `recover`.
- `STAGED_REVISION` is an addressable revision receiving 0% of traffic.
- That revision runs as the worker service account.
- Its `FIXLIST_WORKER_SOURCE_SHA` equals the confirmed `SOURCE_SHA`, which is
  the exact `main` the tool runs from. A valid candidate tagged for another
  commit is refused, so build the candidate from the `main` you will activate
  from.
- Its `FIXLIST_STAGED_CONFIG_SHA256` equals the digest the tool recomputes
  (`staged_candidate_cloudbuild.digest_for`) over the reviewed inactive
  environment for that source, project, region, bucket, queue and origin.
- Every staged key except the two cohort keys (`SCAN_PIPELINE_MODE` and
  `SCAN_STAGED_OWNER_IDS`) still equals that reviewed build.
- It carries the tag `staged-<source12>`.
- It enqueues to the fixed queue path.
- Its target URL is that tag's own URL.
- Its audience is the canonical service origin.
- Its invoker is the fixed invoker, and it has a workspace bucket.
- Its cohort is empty or lists at most five exact owner IDs, never `*`.
- No other addressable revision admits staged scans.
- `verify_staged_scan_infra.py --expected-queue-state PAUSED` passes.

**Pausing is the dangerous direction.** A paused stage queue strands admitted
scans in the middle of their pipeline. Empty task lists cannot prove that every
scan is finished, because a frontier can be committed before its next task is
enqueued. The tool therefore relies on the coordinator's admission barrier:

- `closed` means no new claim can be admitted from any entry point, Base44
  included.
- The coordinator releases an admission only at a terminal status (`complete`,
  `limited`, `failed` or `cancelled`). So zero `active`, `bound` and
  `live_reconciliation` obligations mean every admitted scan is terminal.

`drain-pause` requires that proof, then all three queues that can create stage
tasks to stay empty (entry for plan, stage for batches, drain for the watchdog
finalize), then the same proof again. Only then does it pause. Afterwards it
revalidates everything, and resumes on any change. If the drain does not finish
within `STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS` (default 900, maximum 3600), the
queue is left RUNNING. Every barrier read is bound to the confirmed
generation, so a barrier reopened and closed again in between is refused.

**Recovery needs only closed admissions.** A stranded scan keeps its pinned,
source-tagged worker revision. That revision may still list the owner in its
cohort, and `/scan-batch` and `/scan-finalize` drain regardless of the cohort.
So `recover` checks neither worker intake nor tags. It requires only a closed
barrier at the confirmed generation, then resumes the queue.

**Every recovered task is verified before resume.** `recover` lists the
complete task inventory and describes every task. It refuses if any of these
hold:

- the listing reached the 1,000-task limit and may be truncated;
- a task can't be read, or the described set differs from the listing;
- any single task fails the checks below.

Each task is checked against its *own* pinned tag, not today's candidate,
because a stranded scan may belong to an earlier verified tag:

- its URL host is `staged-<source12>---<canonical host>`;
- that tag is still addressable and resolves to that URL;
- the tagged revision runs as the worker service account and was built from
  the source the tag names;
- the task passes the existing `verify_staged_scan_infra.validate_task`: POST
  to `/scan-batch` or `/scan-finalize`, the fixed invoker OIDC identity, the
  canonical audience and a 480s deadline.

One bad task refuses the whole recovery, with no mutation. An empty queue stays
recoverable, because a committed frontier may not yet have enqueued its next
task, and the tool reports `verified=0 … per-task identity unverified`.

The barrier read needs the same inputs as the operator's `barrier-status`: an
operator identity token for the coordinator, and optionally `CHANGE_TICKET` and
`CUTOVER_REASON` (defaults are supplied). If the signed snapshot cannot be
verified, the tool refuses.

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
6. **[tool, this PR]** `OPERATION=activate` with the exact staged revision,
   from the same `main` the candidate was built from.
7. **[tool]** Run `scripts/run-staged-owner-canary.sh` once with
   `EXPECTED_PAGE_CAP=150`.
8. **[tool, this PR]** After the result is verified, close the admission
   barrier and read its generation with `barrier-status`. Once it reports zero
   obligations, run `drain-pause` at that generation. Then turn staged intake
   off (Base44, gateway and worker cohort) and restore the gateway. If a scan
   is ever stranded in a paused queue, close admission and run `recover` at
   that generation.

Steps 1, 2 and 5 are external, owner-authorized actions. No code change
removes them.
