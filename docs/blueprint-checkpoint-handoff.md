# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B01–B28 semantics in that approved spec control over older paraphrases. Historical implementation details remain in the dated executable plans under `docs/superpowers/plans/`; this file is the current serialized handoff.

## Release boundary

- `main`: `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main `docs/stage-one-evidence-acceptance.md` still says Stage-1 exact-source production publication and fresh non-owner acceptance are pending.
- Later-stage integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge this branch to `main`, deploy/publish, promote workers, mutate admission/queues/scheduler, launch a production scan, change schema/RLS/secrets, or enable Premium/Grok while that Stage-1 release gate remains open.
- When the single Stage-1 release operator records publication and non-owner acceptance, reconcile this branch onto the then-current accepted `main` without reverting the six V7 routes or #308 and require fresh exact integrated-head CI before durable customer-path work.

Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` are historical checkpoints only. No later-stage work on this branch is permission to promote them or reopen admission.

## Stage 2 handoff

B06–B18 are complete for source integration, independent review and exact-head CI at stable corrected checkpoint `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding.

Keep these invariants intact during all later reconciliation:

- one finite shared follow-up budget and Standard-150 assessed cap;
- truthful assessed denominators and unknown states for robots/challenge/429/incomplete/budget/deadline cases;
- exact route/evidence identity and no silent URL normalization collapse;
- robots, DNS/SSRF, redirect, body and deadline protections;
- optional provider evidence disconnected by default and exact-owner/exact-scan controlled when present;
- fail-closed external page/aggregate projection; raw B10 fingerprints, B13/B14 identity/contact observations, B15 freshness details and private B11 link caches remain internal;
- historical signatures/readers remain readable and original signatures are never rewritten.

A direct authenticated HTTP `/scan` privacy regression at `d9061f23edd0a0541b017f42297bf60a9c401560` proved B10/B11/B13/B15 private sentinels do not survive the serialized response; CI `35524582769` passed.

## Stage 3 handoff — in progress

Isolated lanes were integrated serially, not merged to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

Current requirement state:

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Durable V7 customer/card/export consumption is open.
- **B20 partial:** verified shared root-cause grouping requires explicit versioned same-cause evidence and trusted enclosing `scan_id == scan_run_id`; family similarity and repair-local identity alone cannot establish trust. Scan-isolation P1 was RED at `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`, fixed through `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` + `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`, with CI `35504200573` and clean follow-up `5749166024`. Durable projection is open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Known numeric zero remains known; unknown composite does not borrow impact. Stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a`, CI `35513093636`, review follow-up `5750062094` clean. Durable customer/card/export proof is open.
- **B22 partial:** signed evidence-led preview source exists, prefers verified impact-4/5 findings with two-item cap, otherwise exactly one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller-owned wording. Arbitrary producer coverage text is excluded from the nested source and enclosing completion-HMAC Review. Durable exact-owner/exact-scan V7 entitlement/read/card/export proof remains open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Stable checkpoint `4ee24691f46721ffe8112bb435f278e5dd810721`, CI `35514613656`, focused review `5750230877` clean. Durable customer-visible score consumption remains open.
- **B24 partial:** signed handoff-v2 source requires trusted exact scan identity and verified B20 root-cause mapping; carries family IDs, B19 factors, B21 counts, evidence refs, verification/dependency/vendor metadata and scanner UA; historical v1 reader compatibility remains preserved. Durable V7 persistence/read/customer/operator/export proof remains open.

## Latest B22/B24 authority fail-closed slice

Fresh source inspection found two concrete helper-level authority defects and fixed them RED → GREEN without touching the frozen V7 durable/customer paths.

### RED

Commit `28f58efbd773637bfada09da5b0a99b7fcc03fbc` added `scanner-api/tests/test_stage3_authority_fail_closed.py`.

FixList CI `35528067336` failed exactly in scanner-api while the independent lint/typecheck/contracts/frontend job passed. Scanner-api summary: `4 failed, 2042 passed, 18 skipped`.

The failures proved:

1. `select_private_preview()` accepted a caller-provided `coverage_qualification.state=sufficient` before checking `authority_verified`, so an unverified authority still received the fixed sufficient-coverage customer message;
2. `build_handoff_v2()` used truthiness for `operator_authorized`, leaking `suppressed_findings` for invalid truthy non-booleans `1`, `"true"`, and `{"authorized": true}`.

### GREEN

Implementation commit `4a9e0d4dec048291be7956bb225ab1635af30bbc`:

- B22 now returns `state=not_available`, no findings and `coverage_qualification=None` before evaluating any qualification unless `authority_verified is True`.
- B24 now projects `suppressed_findings` only when `operator_authorized is True` literally.

FixList CI `35528215150` passed both jobs on the exact implementation SHA:

- root tests: `115 passed`;
- scanner-api: `2046 passed, 18 skipped`;
- the four new authority regressions passed;
- Stage-1 synthetic corpus: 14 cases / 55 assertions, provenance `synthetic`, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- scanner image `sha256:124ee33c14e185e89adbb49906941192d7a2f55ffe8356e8ad7d43c121a7d932` built;
- lint, typecheck, generated contracts, frontend contracts and production build passed.

Hosted `setup-node` resolved Node `20.20.2`; do not describe this run as exact Node `20.19.5` evidence.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b22-b24-authority-fail-closed.md`.

## What remains before Stage 3 can be complete

1. One fresh independent review of the current corrected B22/B24 shared authority/privacy boundary. A skipped/failed automated review is not approval.
2. Stage-1 exact-source publication and fresh non-owner acceptance must be recorded by the separate release operator.
3. Reconcile this integration branch onto the then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
4. Complete the actual V7 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview seams for B19/B21/B22/B23/B24. Prove suppressed/operator-only findings never enter customer output and historical v1 remains readable.
5. Persist exact source SHAs, tests/failures and independent review evidence before declaring Stage 3 complete.

## Stage 4 handoff — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. Do not launch duplicate implementations.

- **B25 incomplete:** genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures or historical summaries never satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source production deployment/live acceptance, live site/six-V7/worker identity proof, rollback proof or real customer submit → persistence → reload/history → rescan acceptance has been performed.

## Resume instruction

The next serialized owner should first refresh `AGENTS.md`, `README.md`, the approved spec, this handoff, `docs/full-blueprint-progress.md`, current-main `docs/stage-one-evidence-acceptance.md`, applicable executable plans, PR #303 comments/reviews and branch heads.

Then certify the current persisted documentation head with exact-head FixList CI and obtain one fresh independent review of the latest B22/B24 authority corrections. Do not bypass the Stage-1 release freeze. When Stage-1 acceptance is actually recorded, reconcile onto accepted `main` and prove the real V7 B19–B24 persistence/customer seams before starting shared Stage-4 integration.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in the latest slice.
