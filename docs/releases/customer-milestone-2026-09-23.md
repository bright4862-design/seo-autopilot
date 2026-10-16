# Customer milestone release candidate

Based on accepted main `c1080d75f7d1aacd748e74009be7a6c15aa40a93`. This is the focused continuation of PR #355, carrying its reviewed deterministic dependencies into a main-based candidate. It does not merge the whole AI integration branch. Grok, chat, runtime models and GEO scoring changes remain outside this release.

## Customer behavior

- A full authoritative saved result can request a separate rescan comparison. Only the current scan ID comes from the browser. The V8 reader selects the previous scan from the service-owned ScanRun relationship and checks ownership, paid access, project, supported release, scope, chronology and both existing authority seals.
- The existing dispatch gateway executes the canonical Python comparator through a bounded, separately signed `/compare` request. Its signed response is bound to the reader's random nonce and both scan IDs. The browser receives only validated presentation fields. No new worker access or IAM permission is introduced.
- Missing page observations cannot establish a fix. Missing current reference identities or duplicate references make the comparison unavailable rather than silently disappearing from totals. Comparison errors leave the independently verified current FixList readable. First scans have no comparison panel.
- Score wording explains the checked-page counts and does not claim overall improvement or regression. “Not matched” is a disjoint current-finding bucket after verified returns are removed; it does not mean a newly introduced problem.
- Role selection changes explanatory copy for supported repairs. Instructions, evidence controls, priority sections and canonical repair order remain intact. The implementation view uses the original authenticated row population. Preview, limited, stale or incomplete populations receive no added guidance.
- Stage-3 degradation is per row. Page normalization preserves its fields, and display decoration happens after planning so it cannot discard the marker that preserves canonical order.

## Packaging and verification

The authority serialization primitives move unchanged into a small pure module and remain reexported from `scan_job.py`. Gateway deployment assembles seven canonical Python modules from the exact committed Git archive. It never ships a maintained duplicate comparison implementation or the full worker application.

Regression coverage includes real V8 persistence and HMAC reconstruction, the actual V8 comparison route, signed gateway request/response tampering and domain isolation, owner/project/paid checks, streaming body bounds, stale browser responses, role changes, instructions/evidence preservation and the actual page ordering pipeline. Normal main-target CI now includes the gateway suite. The final PR records test and exact-head CI results.

## Deployment sequence and remaining acceptance

Production has not been changed by preparing this candidate. Do not report it live until the following are proven:

1. Review and pass CI at the exact candidate head; refresh main and confirm no competing release. Merge through the existing serialized release process.
2. Record the current serving revisions and rollback. Stage the normal private worker candidate from the exact resulting main SHA; verify source, image and frozen component identity. The changed scanner identity helper and seal-module import mean leaving the old worker in service is not a completed exact-source release.
3. Deploy the gateway from that same clean main SHA with `scripts/deploy_dispatch_gateway.sh`; verify its exact serving revision/source and signed comparison response. No schema, key rotation, queue or IAM change is required.
4. Publish the V8 functions and site through the existing Base44 release scripts and owner authentication, verifying content-sensitive function build IDs and public source. Promote the exact staged worker with the recorded rollback as required by the release operator.
5. Run the existing post-deploy source checks and customer acceptance: current result, real rerun comparison, reload/history, role changes, implementation instructions and mobile layout. Reject forged/mismatched pairs and verify unavailable comparison does not hide the current result.

The gateway deployment and Base44 publication workflows require an authenticated owner session. In this work session, the GitHub connector supports source/PR operations but has no workflow-dispatch operation; the release browser is signed out. Local Base44 `whoami` also required owner device authentication. These are deployment-access requirements, not completed acceptance.

The scheduled AI Integrator was temporarily paused while this candidate was assembled. Keep one release owner, and explicitly hand ownership back or resume the scheduled task after the interactive deployment is finished or handed off.

## Owner acceptance follow-up

PR #356 merged as `a9a96faf24ee9a841720981dcfbcee7bf0967a84`. Gateway workflow `35856413571` and Base44 site/functions workflow `35856609911` passed, including serving revision/source and all six V8 runtime identities. Worker `fixlist-standard150-worker-00096-76l` was prepared at zero traffic; it has not been promoted by this interactive release. The previous worker remains the rollback target.

The owner then observed **Comparison unavailable** on a readable saved Funbooker FixList and reported that changing roles had little visible effect. These are failed customer acceptance checks, not a completed release.

The role issue is reproduced: four of the seven actual repairs had no role copy, including the first redirect repair. The follow-up adds deterministic copy for redirect chains, unusable meta descriptions and overwide titles, plus explicit role headings and a selected-role summary. All seven repairs now have role explanations. Source instructions, evidence, ranking and order remain unchanged.

The comparison root cause is still unconfirmed. Both real saved pairs pass the actual V8 reconstruction, Python comparison, signed transport and UI model locally when re-sealed with a synthetic diagnostic key. This proves shape compatibility only; it does not verify the original production HMAC or the live network path. Production snapshots and keys have not been changed or published as test fixtures.

The follow-up preserves fail-closed comparison behavior and adds fixed support references for the failing boundary. Arbitrary exception text, proofs, URLs and payloads are never returned. Missing, inaccessible and invalid previous results share one reference. Successful comparisons and first scans have no failure reference. The existing read-only release diagnostic also reads at most 30 gateway comparison request metadata entries from the previous eight hours; it adds no permissions, triggers or deploy operation.

After the diagnostic/copy patch is published, repeat the saved comparison and inspect its support reference if it still fails. Do not claim the comparison is fixed or promote the worker on source tests alone. Keep the single integrator paused until this release is completed or explicitly handed back. Export evidence omissions and the unrelated H1 impact wording remain separately recorded follow-ups.
