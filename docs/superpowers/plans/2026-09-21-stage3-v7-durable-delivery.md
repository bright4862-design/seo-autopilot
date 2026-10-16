# Stage 3 V7 durable delivery: current-main integration checkpoint

## Authority and ownership

Implement the existing approved B19–B24 requirements in `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. This is not a request to invent a new scanner or redesign its evidence model. The user explicitly asked on 2026-09-21 to finish and publish Stages 2, 3 and 4.

The serialized release-integration candidate is PR #319, branch `agent/full-blueprint-release-integration-20260921`. It starts at `6f7500f72bd32770c71228420b698ef0310e43da`, tree `2fdfa4785820aa9260e9c3072a8abe9eab0005c4`, whose exact parents are:

- current deployed/main `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`;
- preserved PR #303 source `af66e7f5551d6ea3e1a174af24f05143aeef3b10`.

No main merge, force-push, runtime publication or production mutation occurred to construct this candidate. V7 routes and #308's `siteOwnerAttestation: siteOwnership` prerequisite are present. Preserve PR #303 and all lane branches as history; never recreate their implemented features. Refresh remote heads and coordinate with the single existing hourly integrator before writing shared files.

Ruling: the production freeze continues to prohibit moving main or deploying an unaccepted candidate, but it must not prevent OFF-MAIN implementation and tests of the missing V7 delivery seam. Waiting for a live gate before even writing this isolated integration was not required for safety. This ruling does not waive real non-owner acceptance, review, CI, historical compatibility, B25 or B28.

## Fresh verification already executed

Isolated checkout and dependencies only; app source and production were not changed. Environment: Node 20.20.2, Python 3.11.16, Linux/Bash. Do not mislabel this as exact Node 20.19.5 or hosted Python 3.12.

On PR #303 head af66e7f: root 115 passed; scanner-api 2097 passed / 18 skipped; frontend 1479 passed; lint/typecheck/build and generated contracts passed.

On combined commit 6f7500f: root 115 passed; scanner-api 2097 passed / 18 skipped; frontend 1486 passed; lint/typecheck/build and generated contracts passed. The additional frontend tests preserve current-main V7/#308 behavior. Local Docker build was not run. PR #319 must obtain its own exact-head hosted CI.

Commands executed:

```sh
python -m pip install -r scanner-api/requirements.txt
npm ci --no-audit --no-fund
pytest -q tests/
(cd scanner-api && pytest -q tests/)
npm run test:frontend
npm run lint
npm run typecheck
npm run build
node scripts/generate_release_contracts.mjs --check
```

## Reproduced missing customer delivery — not a speculative hardening item

A synthetic two-product fixture using the actual helpers in `scanner-api/tests/test_stage3_b24_signed_handoff_source_integration.py` was passed through real `apply_canonical_repair_contract(..., identity_version='evidence_url_identity_v2_published_route')`, then real V7 `buildAuthoritySnapshot` and `authorityRowsFromSnapshot`.

Observed producer output:

- a canonical repair with `stage3_priority_factors.version=repair_priority_v3_four_factor_v1`, impact 2, reach 1, page_value 1, confidence 1, composite 2;
- `stage3_counts.unique_affected_page_count=2`, displayed sample count 2, known population null;
- `stage3_delivery` with one exact displayed fix ID;
- `stage3_health_score_decision` with base 88, verified root-cause ceiling 72 and adjusted 72, while legacy score remains unchanged;
- `stage3_handoff_v2_source.handoff_version=fixlist_handoff_v2` and the evidence-led preview source.

Observed V7 row output: the Stage 3 priority-factor/count objects were absent; no handoff-v2 source or preview-selection source survived. This demonstrates that producer success and 2097 green scanner tests do not establish B19–B24 customer delivery. Do not report these features as shipped until the entire real path passes.

The relevant seams are:

- producer: `scanner-api/app/repair_contract_v2.py`, `stage3_delivery.py`;
- active writer: `base44/functions/persistDurableScanAuthorityV7/authoritySnapshot.js`, `authorityRows.js`, `entry.ts`;
- active reader: `base44/functions/getCustomerScanResultV7/projection.js`, `entry.ts`;
- historical/chat reconstruction: existing versioned helpers, including `grokChat/authoritySnapshot.js`;
- customer model and exports: `src/lib/repairCardModel.js`, `customerRepairPlan.js`, `scanHandoff.js` and actual UI consumers;
- reusable end-to-end harness: `tests/helpers/assertPublishedEvidenceOutput.mjs` (currently V6-specific; preserve its historical coverage and add the V7 path rather than downgrading routes).

## Execute the vertical slice in this order

1. Add a real executable RED regression using actual Python Review/completion signing and the actual V7 writer, persisted rows, authenticated reader and customer/export consumers. Use the two-product evidence above, a known-zero-vs-unknown >36-candidate case, overlapping affected-page sets and exact owner/scan identities. A failing missing-field assertion is useful RED; an import/setup error is not.
2. Implement bounded positive-allowlisted transport of the already-signed B19/B21 decisions, B20 verified root-cause evidence, B22 preview source, B23 score decision and B24 handoff source. Python remains the only ranking/scoring authority. Do not independently recalculate Stage 3 factors in the browser. Invalid/absent evidence must stay unknown or make the new contract ineligible.
3. Preserve original historical HMAC payloads and reconstruction. Any new authenticated representation needs an explicit version/selection boundary and exact persisted read-back verification; do not inject new fields into historical signatures or trust unsigned top-level markers. Use existing schema capacity where semantically appropriate. If a named schema addition is truly necessary, document its exact fields and server-only security, obtain the applicable release review and never broadly push schemas/RLS.
4. Preserve selection before truncation, exact affected unions, separate observations/population/sample counts and known-zero-versus-unknown semantics through rows and visible output. Prove the customer score agrees with the authenticated B23 decision and that stricter existing incomplete/access ceilings still win. Do not reconstruct missing data from current site state.
5. Wire the real customer card, current scan export and two-finding private preview to the authenticated representation. Prove full customer, unpaid preview, locked/unverified, cross-owner, cross-scan, malformed and tampered cases, plus historical v1 export/reader compatibility. Suppressed/operator-only/private data must never enter customer responses.
6. Run focused then full root/scanner/frontend suites, generated package/contracts checks, lint/typecheck/build, exact integrated-head CI and a fresh independent review. Record exactly which requirements close. Do not call a skipped or old review approval.
7. Integrate the EXISTING Stage 4 lane delta only after applicable Stage 3 seams are proven: `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, draft #317. Its old-base V6 references must not overwrite current V7. Reproduce any own-site serving correction against the actual release; do not infer deployed behavior from source alone.
8. Execute the genuine B25 paired 30-site baseline/candidate gate with traceable captured provenance and independent adjudication. The existing synthetic 14-case/55-assertion corpus remains synthetic. Historical summary counts, invented provider connections or unit fixtures cannot make this gate pass.
9. Only after applicable gates pass: guarded exact-head merge, exact-main CI, source-derived runtime/build contracts, zero-traffic worker staging, matching Base44/site publication, six runtime identities, verified promotion/rollback, bounded real customer acceptance/reload/history/rescan and guarded public reopening. Stop for actual unavailable workflow-dispatch or human browser/device authorization rather than bypassing it.

## Corrected Stage 1 evidence to avoid repeating completed operations

The old Stage 1 acceptance document is stale about deployment: site/six V7 functions and worker `fixlist-standard150-worker-00091-bdr` were already published/promoted on 2ad64dc5. Publication run 35463524680 and promotion run 35463804150 are recorded. Resume run 35531859980 succeeded with public claims closed at generation 71. Acceptance-only run 35582317078 created generation 72, cohort `stage1-v7-ownership-p1-20260921-02`, one total/one per-owner claim.

Scan `6ab0f6acc57f8ecdf24c2aae` completed with 5000 found, 150 checked/retained, score 72, persisted FixList and released admission obligation. It recorded owner/manager robots policy. The user subsequently said, verbatim, `I didnt pick either i think`. Therefore this is not a demonstrated explicit-not-owner regression and cannot establish that #308 failed. Equally it is not the required non-owner acceptance. Do not modify this scan or older scan `6aaed0f4b80965cfac9d093c` to manufacture acceptance. New scan reload/history remains unproven.

Do not repeat publication, promotion, the successful resume, or a redundant status-only loop. For the next authorized live test, first establish the actual current cohort/budget and explicitly capture the normal customer form's not-owner selection. An exhausted one-claim cohort is not authorization for another submission. Keep public claims closed until the required acceptance and trustworthy result gates pass.

## Coordination and unresolved external gate

One CodeRabbit request was posted on PR #303, comment 5758404900, for exact head af66e7f and the B19–B24 authority/privacy source boundary. Request submission is not review completion. Check the response before issuing any duplicate request; a combined-candidate review must identify the actual covered source.

The existing hourly task is the single serialized integrator. Continue from this current-main candidate after the handoff is recorded; do not create a second implementation loop. At each checkpoint persist code, real test results, requirement status and the exact next failing gate. Do not spend later runs re-proving unrelated already-fixed malformed-value cases while the reproduced V7 data-loss seam remains unimplemented.
