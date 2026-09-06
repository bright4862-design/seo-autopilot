# Worker Memory Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the observed Standard 150 worker OOM and prove failed work reaches a truthful terminal state without interfering with another agent’s reconciliation patch.

**Architecture:** Pin the durable Cloud Run worker to 1 GiB in the exact-source deployment manifest while retaining concurrency 1, timeout 480 seconds, and the 150-page cap. Verify catchable failure persistence and signed reconciliation as separate existing backstops rather than claiming an OOM-killed process can clean itself up.

**Tech Stack:** Google Cloud Build/Cloud Run YAML, Base44 durable worker control, Node contract tests, Python worker tests.

**Spec:** `docs/superpowers/specs/2026-09-05-matrix-truthfulness-and-worker-reliability-design.md`

## Global Constraints

- Worker memory must be exactly `1Gi` for this release.
- Worker concurrency remains `1` and timeout remains `480` seconds.
- The Standard 150 crawl cap and all frozen release markers remain unchanged.
- Do not copy or overwrite uncommitted reconciliation edits from another worktree.
- Do not promote or publish production while source identities are mixed.

---

### Task 1: Pin Worker Memory in the Reviewed Deployment

**Files:**
- Modify: `cloudbuild.durable-worker.yaml`
- Create: `tests/frontend/workerMemoryDeploymentContract.test.mjs`

**Interfaces:**
- Consumes: the exact-source Cloud Build worker deployment step.
- Produces: a Cloud Run candidate with 1 GiB memory, concurrency 1, and timeout 480.

- [ ] **Step 1: Write the failing deployment contract test**

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const manifest = readFileSync("cloudbuild.durable-worker.yaml", "utf8");

test("the Standard 150 worker has bounded release resources", () => {
  assert.match(manifest, /--memory=1Gi/);
  assert.match(manifest, /--concurrency=1/);
  assert.match(manifest, /--timeout=480/);
  assert.match(manifest, /--no-traffic/);
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `node --test tests/frontend/workerMemoryDeploymentContract.test.mjs`
Expected: FAIL because the manifest does not declare memory.

- [ ] **Step 3: Add the memory pin**

Add `--memory=1Gi` to the `deploy-private-worker` arguments beside `--timeout=480` and `--concurrency=1`.

- [ ] **Step 4: Run the test and commit**

Run: `node --test tests/frontend/workerMemoryDeploymentContract.test.mjs`
Expected: PASS.

```bash
git add cloudbuild.durable-worker.yaml tests/frontend/workerMemoryDeploymentContract.test.mjs
git commit -m "fix(worker): pin Standard 150 memory to one GiB"
```

### Task 2: Prove Terminal Failure Ownership

**Files:**
- Modify: `tests/frontend/scanReconciliationContract.test.mjs`
- Modify only if tests fail: `base44/functions/durableScanWorkerControlV2/entry.ts`
- Modify only if tests fail: `base44/functions/durableScanWorkerControlV2/reconciliation.js`
- Modify only if tests fail: `scanner-api/app/scan_job.py`

**Interfaces:**
- Consumes: the existing worker failure persistence and signed reconciliation flow.
- Produces: regression evidence that catchable failures are immediately terminal and abandoned attempts are terminalized by the reconciler.

- [ ] **Step 1: Add exact contract assertions**

```js
test("the worker persists catchable failures and verifies the saved terminal row", () => {
  assert.match(controlV2, /status:\s*"failed"/);
  assert.match(controlV2, /worker_failure_persistence_failed/);
  assert.match(controlV2, /releaseAdmission/);
});

test("an abandoned heartbeat is terminalized by signed reconciliation", () => {
  const result = reconciliationDecision({
    ...serverAdmittedScan,
    status: "crawling",
    worker_heartbeat_at: "2026-09-06T00:00:00.000Z",
  }, Date.parse("2026-09-06T00:16:00.000Z"));
  assert.equal(result.action, "fail");
  assert.equal(result.error_code, "worker_heartbeat_timeout");
});
```

- [ ] **Step 2: Run focused reliability tests**

Run: `node --test tests/frontend/scanReconciliationContract.test.mjs tests/frontend/workerMemoryDeploymentContract.test.mjs`
Expected: PASS on current V2 behavior. If RED exposes a real gap, make the smallest change in the listed V2 files; do not transplant the separate legacy reconciliation branch.

- [ ] **Step 3: Run Python durable-job tests**

Run: `python -m pytest scanner-api/tests -q -k 'scan_job or durable or worker'`
Expected: PASS.

- [ ] **Step 4: Commit only if the task changed tests or runtime**

```bash
git add tests/frontend/scanReconciliationContract.test.mjs base44/functions/durableScanWorkerControlV2 scanner-api/app/scan_job.py
git commit -m "test(worker): prove terminal failure recovery"
```

### Task 3: Integration and Release Proof

**Files:**
- Modify only if a verification failure demonstrates a defect in files already listed above.

**Interfaces:**
- Consumes: customer-result branch commits and worker memory commit.
- Produces: one exact candidate eligible for CI and controlled production canary testing.

- [ ] **Step 1: Refresh `origin/main` and inspect concurrent changes**

Run: `git fetch origin main && git log --oneline --left-right HEAD...origin/main`
Expected: review any new reconciliation merge before rebasing; never discard or overwrite it.

- [ ] **Step 2: Rebase and rerun focused contracts**

Run: `git rebase origin/main`
Then: `node --test tests/frontend/workerMemoryDeploymentContract.test.mjs tests/frontend/scanReconciliationContract.test.mjs tests/frontend/pageAccounting.test.mjs`
Expected: PASS.

- [ ] **Step 3: Run full local gates**

Run: `pnpm lint && pnpm typecheck && pnpm test:frontend && pnpm build`
Then: `python -m pytest scanner-api/tests -q`
Expected: all commands exit 0.

- [ ] **Step 4: Verify release scope**

Run: `git diff --check && git status --short && git diff --stat origin/main...HEAD`
Expected: only the approved customer-result truthfulness, worker memory, regression tests, spec, and plans.

- [ ] **Step 5: Prepare the exact deployment handoff**

Record the final candidate SHA. Build/deploy/publish from that exact SHA, verify live Base44 and worker identity before traffic changes, then run one controlled canary. The canary must prove crawl `<=150`, terminal persistence, FixList creation, reconciled page accounting, clickable URLs, customer copy, score version, reload/history, and released admission.
