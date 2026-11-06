# Incident 378: Standard 150 v7 controlled recovery (2026-11-06)

**Status: STAGED / UNACCEPTED / NO-GO FOR PUBLIC INTAKE OR PROMOTION.**

This is an evidence checkpoint, **not** an acceptance report. Do not use this
document as `data/beta-crawler-revision.json.acceptance_report`. Do not
rewrite failed scans or accept the historical v6 fingerprint as new write
authority.

## Observed system

- Current `main` at staging: `d22e531f642016e0471bde0a62ac022738338948`.
- Canonical Standard 150 commercial sampler v7 fingerprint:
  `e0eca935c350e590`. Its record is still `status: candidate`, with
  `git_commit: ""` and `acceptance_report: ""`.
- Serving worker before staging: `fixlist-standard150-worker-00097-lvl`
  (100% traffic), source SHA
  `15525082a712ec341f2830e6a8f39db7325e4397`, v6 fingerprint
  `01ebe8e90df1e6bd`. Authenticated /revision comparison failed
  ([workflow 42043280697](https://github.com/bright4862-design/seo-autopilot/actions/runs/42043280697)).
- Routes and timeout for that worker passed
  ([workflow 42237743081](https://github.com/bright4862-design/seo-autopilot/actions/runs/42237743081)).
- Base44 `ScanRun` records on October 27 (two) and November 6 (one) failed at
  persistence with `expected_e0eca935c350e590__received_01ebe8e90df1e6bd`.
  The November 6 worker reported 150 crawled but the failed persisted record
  holds only failed-row default counts and no authority proof. Admission
  released. Previous signed v6 records remain auditable.
- Base44 checkpoint `6ad255faa671146eae179549` for v7 source was
  last deployed 2026-10-27. Deployed function *bytes* and current site
  source SHA must still be independently attested; a checkpoint alone does
  not prove live package identity.

## Completed 2026-11-06 staging evidence

The exact-owner `/stage-worker-candidate` command on draft PR #398 triggered
[workflow 42241936102](https://github.com/bright4862-design/seo-autopilot/actions/runs/42241936102).
Cloud Build `72de3e37-4df9-4e69-a032-f6e1099d0c6c` succeeded.
The job reported:

- `WORKER_CANDIDATE_READY=fixlist-standard150-worker-00101-zh2`
- `WORKER_CANDIDATE_SOURCE_SHA=d22e531f642016e0471bde0a62ac022738338948`
- `WORKER_CANDIDATE_EGRESS_MODE=none`
- `Candidate traffic verified at 0%.`

Source CI on that exact staging SHA passed both jobs
([workflow 42239130251](https://github.com/bright4862-design/seo-autopilot/actions/runs/42239130251)).

**Not yet observed:** authenticated `/revision` on this newly staged
revision, its marker-set comparison to the v7 record, live Base44
package/build ID equality, a signed v7 canary, and customer result read-back.

## Safe next verification after review/merge of PR #398

The PR adds two explicit owner-only GitHub Actions choices to
`.github/workflows/fixlist-cloud-operator.yml`. Neither is available on
`main` until the PR is reviewed and merged.

1. **Restage from the exact new main SHA.** Merging changes the source SHA;
   the already-built `00101-zh2` cannot be claimed as built from that new
   source. Reuse the existing `build-worker-candidate` operation with exact
   SHA confirmation. Record the new ready revision and prove it receives 0%.
2. **`tag-worker-candidate`**: choose that exact 0%-traffic revision and
   enter the exact revision string in `confirm`. This is a **metadata
   mutation** to the Cloud Run service's `candidate` tag; it does not
   intentionally move traffic, and the operator verifies 0% before/after.
   Do not run it without owner authorization.
3. **`verify-staged-worker-release`**: choose the same exact revision.
   This step is read-only: it refuses untagged, ambiguous, mismatched or
   traffic-serving revisions; it probes the tagged private `/revision`
   using the service audience, compares all release markers, fingerprint
   and immutable source SHA, then verifies build provenance, Base44 route
   generation and the 480-second timeout.
4. Verify Base44 V8 function-package build IDs, authority schemas, HMAC-key
   continuity and the exact source identity of the public site separately.
   If any differ, stop and plan an isolated/closed-barrier cutover. A
   successful worker probe does **not** prove Base44's deployed bytes.
5. Read current admission barrier generation and obligations with the
   read-only operator. Before any production-facing mutation, arrange
   an exact-generation, drained, closed/acceptance-only owner cohort with
   explicit rollback and no outstanding public claims.
6. **Separate acceptance mechanism required:** prove how an owner canary is
   routed to the exact v7 worker while public intake remains closed.
   The existing customer Cloud Tasks route targets the serving service;
   merely tagging a 0%-candidate does not route ordinary scans to it.
   Do not infer an isolated canary exists from a green `/revision` check.
7. Execute one approved, bounded Standard 150 owner canary only after
   that routing/authority design is verified. Record exact scan/request/
   project/owner/source, selected and crawled page counts, classification,
   persisted authority or limited-result integrity proof, canonical FixList
   identity, customer read-back, reload recovery and released admission.
   If it fails, preserve the failure evidence and stop.
8. Only then author a dated **genuine live acceptance report** with the
   accepted source SHA. Update/freeze the canonical release record using the
   repository's freeze tooling, re-run the exact release gates, and prepare
   the reviewed guarded production cutover. Do not change the fingerprint
   literal or signing key to make a failure disappear.

**Release guards:** Draft PR #398 additionally refuses unaccepted source
records before new worker traffic promotion, Base44 scanner-function publish,
and Base44 site publish. It explicitly preserves rollback. These guards are
necessary but not themselves proof of customer acceptance.

## Prohibitions

Do not promote `00101-zh2` solely because it is Ready. Do not call
`/promote-staged-worker` before acceptance and an exact drained barrier.
Do not resume public intake while production worker v6 and Base44 v7 disagree.
Do not merge PR #397 into this recovery or activate Extended 500. Keep
Grok/chat/runtime AI OFF. Preserve historical signed evidence and failed rows.
