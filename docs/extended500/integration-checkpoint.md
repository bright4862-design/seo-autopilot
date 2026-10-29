# Extended 500 integration checkpoint — 2026-10-29

Integration base: `agent/extended500-collector-proof-20261026` at `002b84c9b6eaef78babec6081df150f31a000b11` (draft PR #377, not merged; its last CI run, on 2026-10-28, was green).

The status words below mean only these things:
- IMPLEMENTED: the code exists.
- TESTED: offline tests pass locally.
- VERIFIED: proven against real Stripe, Base44 or GCP.
- DEPLOYED: running in production.
- BLOCKED: cannot proceed without a decision or a dependency.

**Nothing in this checkpoint is VERIFIED or DEPLOYED.** GitHub CI (`ci.yml`) runs only on PRs to `main`. So none of the lane PRs below has CI on its own head, and every "TESTED" result is from local runs that the integrator repeated by hand.

## Lanes

| Lane | Issue | Draft PR | Head SHA | Status | Integrator re-run on that head |
| --- | --- | --- | --- | --- | --- |
| A: atomic ScanRun seed | #382 | #389 | `358d5b5f45dee70703ad491d21087479b1db2681` | IMPLEMENTED, TESTED | `pytest tests/test_extended500_*.py`: 151 passed |
| B: pickup authorization | #383 | #391 | `9414cfd196577907e15f175f27982c7bd9a10577` | IMPLEMENTED, TESTED | 196 passed |
| C: 500-page collector | #384 | #390 | `f183f0007d287fd5ea8505be86cf125698412c20` | IMPLEMENTED, TESTED | 145 passed |
| D: reviewed authority | #385 | #393 | `f6f4f14e516857d8c060ad334d95d14fc43f14a4` | IMPLEMENTED; not re-run by integrator | — |
| D (alternative) | #385 | none (branch `agent/ext500-d-reviewed-authority-alt-20261029`) | `edd68bc7ca3ab8df3af95b5f1b6e87acdd7f0d02` | IMPLEMENTED, TESTED | 189 Python passed; 57/57 Node |
| E: QA gates | #386 | #392 | `0efa5850286fceb3385c246367bf6e7fe752f07e` | IMPLEMENTED, TESTED | 172 passed, 12 strict-xfail (RED); Node 35 pass, 7 todo (RED) |
| Payments (integrator) | #387 | #388 | `c7c093da3c66f919fb972b7785cfb344d37f54c6` | IMPLEMENTED, TESTED | 29/29 new tests; frontend 2028/2028; lint, typecheck, contracts and build clean |

Every lane diff adds new lane-owned files only. No lane edits any integrator-owned shared file (`service.py`, `main.py`, `startStandardScanJobV8/`, `base44/entities/`, `.github/workflows/`, `data/beta-crawler-revision.json`).

### Concurrent owner-account work (not created by this session)
- Lanes B, C, D and E already had commits from the owner account before the lane agents pushed:
  - B: `fac2fab02`..`b69456ce2`, replaced by the agent's superset. Comparison is not verified.
  - C: `0cf535bd9`..`bb703cf04`, kept, with the agent's collector added alongside.
  - D: `54d4e0ce2`..`f6f4f14e5`, kept. The agent's version went to the alt branch instead.
  - E: `fefe61a14`, `9dc5e3a8b`, kept verbatim.
- Draft PR #394 (`integration/ext500-lifecycle-20261029` at `2a0c67ffd`) and the `agent/ext500-*-ci-validation-20261029` branches exist. The integrator has not reviewed them.

## Decisions needed from the owner
1. Lane D: keep #393, use `edd68bc`, or merge the two.
2. Lane C: choose which collector path the worker uses. The options are the spawn-isolated `run_scan` child, or the bounded private frontier with pacing, a redirect guard and a memory budget.
3. Upgrade policy for Standard 150 holders. Today they are refused Extended 500 checkout (`standard150_upgrade_policy_pending`).
4. The test-mode price for staging. The live price `price_1UVtse4DcTLS57kiivKSCXKC` is pinned, and it and its product stay inactive.

## Cutover blockers (BLOCKED)
- **Standard 150 coexistence.** E's RED cases 10 and 11 reproduce two failures:
  - The Standard 150 `stripeWebhook` returns 400 on a non-150 plan, which causes endless Stripe retries.
  - `findOwnedAccess` and `paidAccessRecord` treat a second plan's row as a conflict, so a 150 buyer who also holds a 500 row loses access.
  - These must be fixed before any Extended 500 Access row is written.
- **The Standard 150 path accepts `extended_500` ScanRuns.** The `/scan-job` identity check, the completion signers and the V8 persistence all do (E's RED cases 1, 2 and 13). The patches need the Standard 150 release process.
- **Worker invoker check.** `require_cloud_tasks_oidc` does not verify the token signature or audience, and it checks the Standard 150 service account (B, unverified).
- **Frontend.** `src/lib/access.js` recognises only `standard150_lifetime`.
- **Missing pieces:**
  - the terminal-release issuer (owner slots can never be freed)
  - the `/scan-job-extended500` worker route
  - real Base44 and Firestore port adapters
  - Base44 500 persistence
  - the customer result view
- **Infrastructure proof.** Still unproven: Firestore contention, Cloud Tasks dedup, IAM/OIDC, and real-site timing (500 pages at 0.2 s per host is ≥100 s against the 120 s job ceiling).
- Standard 150 incident #378 is not treated as resolved.

## Deployment readiness
Nothing is ready to deploy.
- Both Extended 500 payment packages return 503 until explicit environment switches are set. Those switches must stay unset until the worker and the customer result flow work.
- `base44 deploy` would upload them, because discovery is by `entry.ts`.
- No Stripe object was created or changed.

## Recommended next action
1. The owner settles decisions 1–4.
2. Land the Standard 150 coexistence fixes (webhook 200-ignore for other plans; plan-scoped access lookups) through the Standard 150 release process.
3. Integrate in this order:
   - A → B → C → D → E
   - then payments
   - then frontend recognition
   - then staging with a test-mode price
4. Run CI on the combined head through a PR to `main` that is kept unmerged.
