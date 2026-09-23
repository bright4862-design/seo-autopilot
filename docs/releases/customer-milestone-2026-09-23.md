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
