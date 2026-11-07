# Incident 378: V7 candidate verification and owner-canary routing (2026-11-06)

**Status: candidate VERIFIED at 0% traffic / owner-canary route PREPARED, NOT DEPLOYED / NO-GO for promotion or public intake.**

This is an evidence checkpoint and a reviewed design. It is **not** an
acceptance report. Do not use it as `data/beta-crawler-revision.json.acceptance_report`.

## Verified on exact main `624aaf1ae459c49b5f26a0f8a366044c348b79bb`

| Step | Run | Result |
| --- | --- | --- |
| Read-only `status` | [42297539131](https://github.com/bright4862-design/seo-autopilot/actions/runs/42297539131) | success; serving worker logs show only `fixlist-standard150-worker-00097-lvl` handling `/scan-reconcile` |
| `tag-worker-candidate` (`confirm` = exact revision) | [42297737424](https://github.com/bright4862-design/seo-autopilot/actions/runs/42297737424) | `WORKER_CANDIDATE_TAGGED revision=fixlist-standard150-worker-00102-nn7 tag=candidate percent=0` (re-read after tagging) |
| `verify-staged-worker-release` | [42297882493](https://github.com/bright4862-design/seo-autopilot/actions/runs/42297882493) | success; see below |

`verify-staged-worker-release` evidence for `fixlist-standard150-worker-00102-nn7`:

- `TAGGED_ZERO_TRAFFIC_CANDIDATE_OK`, tag URL
  `https://candidate---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app`.
- Image `europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/fixlist-standard150-worker@sha256:22e5b1b8fabf7009f6ab2a2a6efd8c972ba6e0a1adbe0cba7ffb4c7f3f57f8b9`.
- Build `f5f3e6b8-feb5-4aff-ac2f-ee5046b74acf` SUCCESS, `_RELEASE_SHA=624aaf1ae459c49b5f26a0f8a366044c348b79bb`.
- Routes `/scan-job` and `/scan-job-drain` declared; Base44 routes called by
  release source and running image both `durableScanWorkerControlV8
  persistDurableScanAuthorityV8 persistLimitedScanResultV8`.
- `timeoutSeconds: 480` (equals the 480s dispatch deadline).
- Authenticated private `/revision` through the tag URL with the canonical
  service audience: runtime fingerprint `e0eca935c350e590` = recorded
  `e0eca935c350e590`; full release marker map equal; runtime `source_sha`
  `624aaf1ae459c49b5f26a0f8a366044c348b79bb`.
  `PASS: the running worker computes the release identity this commit records.`

Production traffic was not moved. The serving worker remains
`fixlist-standard150-worker-00097-lvl` (v6, `01ebe8e90df1e6bd`), which is
also the rollback target.

## Not verified (blocked)

- **Admission barrier.** `barrier-status`
  ([42298034792](https://github.com/bright4862-design/seo-autopilot/actions/runs/42298034792))
  refused with `barrier_generation_conflict`: the read requires the exact
  current generation and `0` is not it. Nothing was written. The current
  generation was not guessed by trial; the owner must supply it.
- **Base44 production identity.** No read-only Base44 identity operation
  exists on `main` (`verify-base44-functions.sh` runs only inside promotion and
  recovery workflows), and the agent environment cannot reach `base44.app`.
  Deployed V8 build/activation IDs, authority schema, HMAC-key continuity and
  site source identity therefore remain **unverified**.

## Why tagging alone gives no canary

`dispatch-gateway/main.py` pins `SCAN_WORKER_URL` to the serving service and
refuses any other target as `invalid_worker_target`; Base44
`startStandardScanJobV8` builds every task from that same URL. A tagged 0%
revision therefore receives no scans.

## Prepared change (this PR): default-off owner-canary route in the gateway

- New optional gateway environment `SCAN_CANARY_WORKER_ORIGIN` +
  `SCAN_CANARY_OWNER_USER_IDS`. Both or neither; otherwise the gateway refuses
  to start. The origin must be a Cloud Run revision-tag URL of the **same**
  worker service (`canary-<revision suffix>---<worker host>`, https, no path/port/userinfo). The shared `candidate` tag is refused. At
  most five exact owner IDs.
- Every existing validation runs first and is unchanged (queue, name, 480s
  deadline, serving URL, invoker, audience, scan identity, `standard_150`,
  robots policy). Only then is a task whose **signed** job names an
  allowlisted `owner_user_id` re-targeted to the tag URL (scan → `/scan-job`,
  drain watchdog → `/scan-job-drain`). The OIDC audience remains the canonical
  service origin; body, name and invoker are byte-identical. All other owners
  keep the serving worker.
- `/health` reports `canary_worker_origin` and `canary_owner_count` (never the
  IDs).
- `deploy_dispatch_gateway.sh` enables it only when both
  `GATEWAY_CANARY_REVISION` and `GATEWAY_CANARY_OWNER_USER_IDS` are given. The
  origin is never taken from input: it is resolved from Cloud Run with
  `prepare_gateway_canary.sh`: authenticated runtime verification of source SHA,
  fingerprint and full marker map, plus route/build/480s checks, precedes creation
  of a revision-specific `canary-<revision suffix>` tag. Existing conflicting tag
  mappings are refused. The tag is never removed or reused, including after
  canary routing is turned off: already queued drain tasks retain their URL.
  The generic tag operator cannot assign a reserved `canary-` tag.
  `assert_tagged_zero_traffic_worker.py` rechecks its exact 0% revision mapping
  immediately before gateway promotion and after the final health check.
  Env and `/health` are verified to carry exactly that route, or none.
  `--set-env-vars` replaces the environment, so any plain gateway deploy
  removes the canary.
- Gateway deployment first proves the previous 100%-serving revision and its
  live health/source identity as a rollback baseline. It builds with
  `--no-traffic`, then explicitly promotes only its reserved new revision.
  Any failed post-promotion check restores the previous gateway and independently
  verifies its control-plane traffic, Ready state, immutable image/source and
  live health identity. Failed rollback is reported separately, never as success.
- Operator: `deploy-dispatch-gateway` gains `gateway_canary` (default `off`).
  `owner-canary` uses the existing `revision` and `acceptance_owner_user_ids`
  inputs.

Base44 code, worker code, scoring, fingerprints, signing keys and historical
rows are unchanged.

## Required sequence after review and merge (owner-gated, not run)

1. Owner supplies the current barrier generation; run `barrier-status`.
2. Close and drain the barrier (`cutover-pause` / `verify-zero-admission-obligations`).
3. Verify Base44 V8 identity independently (owner session or a reviewed
   read-only operation). Stop on any mismatch.
4. `acceptance-only` with an exact owner cohort bound to the merged source SHA,
   short expiry, total and per-owner claim budget of 1.
5. Re-tag/re-verify the candidate if main moved (a new main SHA needs a
   restaged candidate built from it).
6. `deploy-dispatch-gateway` with `gateway_canary=owner-canary`,
   `revision=<exact tagged 0% candidate>`, `acceptance_owner_user_ids=<owner>`.
7. One bounded owner Standard 150 scan; verify the full journey and signed
   persistence per the recovery runbook. Preserve failures.
8. Plain `deploy-dispatch-gateway` (canary off) and keep the barrier closed
   until the acceptance report, freeze and explicit production GO.

Rollback at any point: plain gateway deploy (removes canary); serving worker
is untouched at `00097-lvl`.

## Two-phase acceptance contract (review required before canary execution)

The currently served customer bundle exposes an empty source-SHA marker. This
is a failed site-source attestation, not a passing final acceptance check.
The ordinary publisher requires a frozen release; these phases resolve that
ordering without bypassing or weakening its guard.

1. **Backend acceptance before publication.** After review of the canary route
   and this contract, attest the exact worker and Base44 runtime packages,
   authority schemas and signing continuity. The deployed ScanRun schema was
   observed missing `comparison_evidence`; reconcile through an explicitly
   authorized closed-barrier schema migration before claiming schema parity.
   Public admission stays closed apart from a short-lived one-owner,
   one-claim acceptance cohort bound to the exact release SHA.
2. **Genuine customer read-back.** Run one bounded owner scan through normal
   admission. Record the request, scan, owner, project, source, candidate and
   FixList identities, page selection/crawl counts, deterministic evidence,
   signed persistence, authenticated read-back, browser reload, historical V6
   readability and terminal admission release. Include delayed drain tasks in
   the drain reconciliation. A failed or incomplete result is not acceptance.
3. **Evidence-backed freeze.** Close and drain admission again and remove new
   canary routing. Keep its revision-specific tag for already queued watchdogs.
   A reviewed report may establish provisional backend acceptance only after
   every preceding backend/customer-read-back check passes. It must explicitly
   state final public site-source acceptance is still pending. Use existing
   freeze tooling and real immutable evidence; do not manufacture a full
   production-readiness claim or change fingerprint literals.
4. **Guarded publication and final acceptance.** The existing frozen-release
   publisher remains mandatory. Verify exact final site SHA on both public
   origins and all six V8 runtime build/activation IDs after publication. Freeze
   changes generated contracts and may change package IDs even with the same
   scanner fingerprint. Recheck signed read-back and browser recovery.
5. **Final worker and promotion.** Restage from the final exact current main SHA
   after merge/freeze; the earlier candidate is not thereby built from that
   newer commit. Authenticate and reverify its complete release identity at 0%,
   retain a fresh closed/drained barrier snapshot and verified rollback target,
   then require explicit production GO and the existing promotion/site guards.
   Reopen public claims only after post-promotion customer acceptance passes.

No change in this contract permits publishing an unaccepted release, replacing
keys, altering historical reports, or treating an empty site marker as verified.
