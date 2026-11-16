# Staged Base44 runtime readback and first-150 route activation gates

**PREPARED — no live mutation.** Independent coordination document, 12 November 2026. Source baseline: `main` `c7d71a0272866f03795862bad76cc502a51c46ca`. This document does **not** authorize or apply Base44 secrets, schemas, function deployment, site publishing, admission changes, GCP IAM or queue operations. It does not certify a production scan.

## Verified state (read-only)

- The isolated V9 publisher [run 43094215294](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094215294) ended **failure** after the Base44 owner device-login step failed. Its V9 function deployment and artifact upload steps were skipped.
- GCP bootstrap [run 43094691713](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094691713) ended **failure** after the workspace bucket was created; the operator lacked `storage.buckets.update` for its lifecycle. No later successful bootstrap is established by the inspected GitHub action history. The actual bucket/queue/IAM state still requires authenticated GCP readback.
- The connected Base44 app `6a498732ec779dfaaeab0e53` reported sandbox version `624aaf1ae459c49b5f26a0f8a366044c348b79bb`. Its live `ScanRun` schema does **not** include `page_cap`, `pipeline_mode`, `pages_planned` or `last_committed_batch`; its `Access` schema did not expose `page_cap`. Fresh schema application/readback is still pending.
- Base44's secret-name inventory included `BETA_SCAN_INTAKE_ENABLED`, `BETA_SCAN_ADMISSION_ENABLED` and the existing gateway/coordinator paths, but **not** `SCAN_PIPELINE_MODE` or `SCAN_STAGED_OWNER_IDS`. The Base44 secrets API exposes **names only**, never values. Neither an installed name nor a code default proves the runtime value.
- The existing `base44/functions/fixlistRuntimeActivationProbe/entry.ts` returns a hardcoded historical probe identity; it does not report staged configuration or verify V9 build bytes.
- Production site routing still belongs to a separate release gate. An authenticated owner canary may invoke the isolated V9 functions directly without publishing the public site.

These observations have different scopes: a Base44 sandbox/version is not necessarily production-published function bytes; a stored secret name is not an environment value; a successful Cloud Run revision health check is not a signed scan.

## Smallest safe runtime-visibility lane (PROPOSED)

Implement on a separate branch without changing legacy V8 packages or publishing anything. The **authoritative** data source must be the *deployed V9 execution runtime* that processes the scan, not local Git files, client requests or a standalone static probe.

1. **Authenticated owner-only readback.** Provide a narrowly scoped read-only diagnostics operation invoked only by the expected administrative owner, checked server-side before any data is returned. It reports the app/function identity, build ID, release fingerprint, configuration state (`monolith` or `staged`), and whether an **exact supplied owner ID** belongs to the staged cohort. Return `owner_match: boolean`, a bounded cohort count and a closed-set status, never the full owner list or secret values. Reject wildcard owners and unexpected runtime modes.
2. **Observe the real values.** The readback must query the same `Deno.env.get('SCAN_PIPELINE_MODE')` and `Deno.env.get('SCAN_STAGED_OWNER_IDS')` source that `startStandardScanJobV9/scanLimits.js` uses. Validate companion functions' behavior on a *real* V9 ScanRun after publication; don't infer that all function generations/instances share configuration from one probe.
3. **Bind identities.** Use a fresh pull/manifest to match V9 package digests and runtime `generatedBuildId` values; match the observed worker source SHA, revision/tag, `FIXLIST_STAGED_CONFIG_SHA256`, stage target and canonical OIDC audience; verify the gateway's **serving revision** and staged configuration separately. A local `SOURCE_SHA` string does not prove deployed source. Missing/mismatched identities mean **UNVERIFIED**, not PASS.
4. **Read back disable before pausing.** To stop **new** scans, prove Base44 intake is blocked for the specific owner (or a fresh coordinator admission barrier has closed), and prove the gateway cannot admit new staged claims. Do not require removing the in-flight worker's tagged endpoint/cohort until admitted stages have finalized and their durable frontiers are terminal. Configuration changes must be checked through fresh runtime readback, not an operator-supplied confirmation string alone.
5. **Time-bound evidence.** Persist only a non-secret artifact: observed timestamp, source/package/config identities, exact app ID, expected owner-match boolean, admission barrier generation/mode, gateway serving revision, task queue state and signed ScanRun outcome when it exists. No access tokens, signing keys, owner lists, raw customer HTML or personal emails in logs/artifacts.

### Acceptance matrix for configuration tooling

| Test | Expected outcome |
| --- | --- |
| No staged flags present; invalid mode; wildcard cohort | Default closed, reported explicitly |
| Staged cohort contains the owner; exact V9 runtime and matching release | Readback reports bounded owner membership without exposing list |
| Same config but wrong/unknown logged-in principal | 403/closed, no environment or IDs leaked |
| One V9 function or gateway differs from the pinned release/configuration | **BLOCKED**, no acceptance |
| Secret name exists, value unavailable to the reviewer | **UNVERIFIED**, not treated as OFF/ON proof |
| Disabling new intake with previously admitted stages | New claims blocked; existing exact attempt continues on pinned stage endpoint |
| Queue task listing empty but a committed frontier awaits enqueue, or active ScanRun remains | Stage-queue drain/pause **refused** |
| Paused queue holds an admitted batch/finalize | Recovery possible after new-admission gate is closed, without deleting/moving the original tagged revision |
| Stale source/config artifact from earlier release | Refused even when fingerprint shape is valid |

## Minimal first staged-150 owner canary sequence

**Code gates (not live action):**

1. Merge and verify explicit worker owner cohort (PR #411), guarded queue operations (PR #414 after review blockers), and the bounded scanner/V9 fixes from the integration branch. Run the affected suites at their **exact integrated** source SHA. Keep public V8/monolith the default.
2. Finish additive `ScanRun`/`Access` schema tooling; isolated V9 publication/readback; staged worker candidate build/tag; gateway off-baseline/serving revision attestation; Base44 runtime configuration probe and disable-readback. Avoid claiming deployment from a local code pass.

**Owner/GCP requirements:**

3. An authorized GCP administrator completes only the remaining staged bucket lifecycle, resource-scoped IAM, paused stage queue and task/OIDC checks. Verify exact resources from live GCP. This cannot be inferred from CI.
4. Base44 owner completes the device authentication required for isolated V9 package publication, applies the independently reviewed additive schema, reads back the exact deployed six function packages, and configures the required staged flags through the authorized platform path. Keep customer intake closed throughout preparation.

**Controlled single scan (live action; later authorization/execution):**

5. Read fresh coordinator barrier and queue state; stage queue must be **RUNNING with proven routing and retry policy before** opening an owner-only, one-claim admission cohort. Keep the existing public claim barrier closed. Do not release an owner scan to an intentionally paused stage queue.
6. Bind the exact owner, project, URL, request ID, source SHA and release/configuration identities; run **one** V9 staged-150 canary through the authenticated owner path. Retain `request_id` for idempotent retry after a lost acknowledgement.
7. Require terminal `complete` with signed authority and correct identity (or a separately evaluated evidence-backed `limited`, which does **not** establish complete-150 acceptance), committed batches, progress, duration, worker memory, and both persisted and customer-reader release identity. Check durable frontend projection and evidence scope; an HTTP 200 alone is insufficient.
8. Disable **new** staged intake and verify this from Base44/coordinator and gateway; preserve the pinned stage worker/tag for any in-flight attempts. Reconcile all nonterminal ScanRuns, workspace frontiers, future enqueues, admission-release obligations and cleanup. Only then consider a guarded stage-queue pause; retain ability to recover stranded tasks.

## Separate later production V9/site route activation

The first staged-150 owner canary should **not** depend on publishing the public site. Once the one-scan evidence is verified, prepare a separate source-bound site-routing change that exposes V9 only to the authorized cohort and retains historical V8 reader compatibility. Require frontend route-to-function contract verification, accepted-release records, owner/project isolation, paywall/entitlement enforcement, reload recovery, signing and customer rendering. Expand or reopen public intake only after the accepted cutover gates; no wildcard cohort and no automatic upgrade from 150 to 500.

## Boundaries

- PR #414's `drain-pause` currently proves only GCP-read stage/entry/drain task lists and an operator **assertion** about Base44; those are insufficient to prove that committed but not enqueued frontier work cannot be stranded. It also requires disabling tagged worker mode for `recover`, which can block recovery of precisely the active attempt still pinned there.
- The fixed-source activation guard verifies the candidate's `FIXLIST_WORKER_SOURCE_SHA` **format** and self-consistent tag but does not compare it to the confirmed operator `SOURCE_SHA`.
- No live GCP readback, Base44 runtime flag values or customer-level staged scan has been established in this document.

**Status: PREPARED contract only.** Implementers should not merge this as evidence of an operable configuration lane.