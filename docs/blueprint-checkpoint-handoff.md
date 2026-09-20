# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B01–B28 semantics in the approved spec control over older paraphrases. Detailed RED/GREEN history remains in the dated executable plans under `docs/superpowers/plans/`; this file is the current serialized handoff.

## Release boundary

- `main` was refreshed during the current serialized slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Later-stage integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` are historical checkpoints only.
- Do not merge later-stage work to `main`, deploy/publish, promote workers, mutate admission/queues/scheduler, launch a production scan, broaden schema/RLS, rotate secrets, connect fabricated providers, or enable Premium/Grok while the Stage-1 release gate remains open.
- When the single Stage-1 release operator records publication and fresh non-owner acceptance, reconcile this branch onto the then-current accepted `main` without reverting the six V7 routes or #308 and require fresh exact integrated-head FixList CI before durable customer-path work.

## Stage 2 handoff

B06–B18 are complete for implementation, independent review and exact-head CI at corrected checkpoint `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This does not imply production release completion.

Preserve these invariants during later reconciliation:

- one finite shared follow-up request budget and Standard-150 assessed cap;
- truthful assessed denominators and unknown states for robots/challenge/429/incomplete/budget/deadline cases;
- exact route/evidence identity and no silent URL-normalization collapse;
- robots, DNS/SSRF, redirect, body and deadline protections;
- optional provider evidence disconnected by default and exact-owner/exact-scan controlled when present;
- fail-closed external page/aggregate projection; raw B10 fingerprints, B13/B14 identity/contact observations, B15 freshness details and private B11 link caches stay internal;
- original historical signatures remain unchanged and historical readers stay compatible.

Direct authenticated HTTP `/scan` privacy regression `d9061f23edd0a0541b017f42297bf60a9c401560`, CI `35524582769`, proves B10/B11/B13/B15 private sentinels do not survive the serialized response.

## Stage 3 handoff — in progress

Existing isolated lanes were integrated serially, not merged to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

Current requirement state:

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Durable V7 customer/card/export consumption remains open.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence and trusted enclosing `scan_id == scan_run_id`; family similarity and repair-local identity alone cannot establish trust. Scan-isolation correction is review-clean; durable customer projection remains open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Known numeric zero remains known and explicit unknown priority does not borrow impact. Durable customer/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source exists, prefers verified impact-4/5 findings with a two-item cap and otherwise one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller-owned wording. Completion-HMAC coverage privacy, authority fail-closed behavior, malformed coverage-shape handling, and now final preview-field type hygiene are GREEN. Fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Durable customer-visible adjusted-score consumption remains open.
- **B24 partial:** signed handoff-v2 source requires trusted exact scan identity and verified B20 root-cause mapping; historical v1 reader compatibility remains preserved. `suppressed_findings` requires literal `operator_authorized is True`; durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest serialized slice — B22 preview projection type hygiene

Source inspection found that `_preview_projection()` was a positive **key** whitelist but not a positive **type** whitelist: `rule_id`, `title`, and `evidence_summary` were copied with `candidate.get(...)`. A malformed producer/review object could therefore carry structured dict/list private/debug data through those allowed keys into the signed/customer preview.

### RED

Commit `b58478e456bc67bef293d8d84223e896201891bc` added `scanner-api/tests/test_stage3_preview_projection_privacy.py`.

FixList CI `35540737270` proved the defect:

- scanner-api: `1 failed, 2049 passed, 18 skipped`;
- the failing diff showed sentinel-bearing dict/list values for `rule_id`, `title`, and `evidence_summary` crossed the projection unchanged;
- root regressions: `115 passed`;
- the separate lint/typecheck/generated-release-contract/frontend-contract/build job passed.

The companion positive regression preserves valid string fields and known numeric priority `0.0` behavior.

### GREEN

Implementation commit `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5` adds `_preview_text()` and routes all three customer text fields through it. Only actual strings survive; structured/non-string producer values fail closed to `None`. It does not broaden preview eligibility, entitlement, authority, scan/owner identity, schema, or persistence.

Exact-head FixList CI `35541044424` passed both jobs on `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`:

- root regressions: `115 passed`;
- scanner-api: `2050 passed, 18 skipped`;
- both new preview type/privacy regressions passed;
- labelled Stage-1 corpus remained `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- production scanner image `sha256:deef044ec3e1a2c025d3e741bbed5d78bda57d5ceb8bd9d7199bd32efa65e37a`;
- lint, typecheck, generated release-contract verification, frontend contract tests and production build passed.

Runtime evidence: Ubuntu 24.04.5, Python 3.12.14. `setup-node` requested major Node 20 and resolved `20.20.2`, so this is not exact Node 20.19.5 evidence. GitHub emitted the Node-24 action-runtime migration warning.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b22-preview-projection-type-fail-closed.md`.

The current CodeRabbit PR summary says automatic review is skipped for this repository. That status is not a genuinely fresh independent review and does not close the B22/B24 review gate.

## What remains before Stage 3 can be complete

1. Certify the final persisted documentation/ledger branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the corrected B22/B24 shared authority/privacy boundary. A skipped/requested/failed automated review is not approval.
3. The separate Stage-1 release operator must record exact-source production publication and fresh non-owner acceptance.
4. Reconcile this integration branch onto then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Prove actual V7 B19/B21/B22/B23/B24 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview paths, including suppressed/operator privacy and historical-v1 compatibility.
6. Persist exact source SHAs, regressions/failures, CI and independent-review evidence before declaring Stage 3 complete.

Stage 3 is **not complete**. Latest executable GREEN is `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`, FixList CI `35541044424`.

## Stage 4 handoff — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. Do not launch duplicate implementations and do not shared-integrate while Stage 3 acceptance remains open.

- **B25 incomplete:** genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures or historical summaries never satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance, live site/six-V7/worker identity proof, rollback proof, or real customer submit → persistence → reload/history → rescan acceptance has been performed.

## Resume instruction

At the next serialized slice, first refresh `AGENTS.md`, `README.md`, the approved spec, `docs/full-blueprint-progress.md`, this handoff, current-main `docs/stage-one-evidence-acceptance.md`, applicable plans, PR #303 comments/reviews and branch heads.

If this run's final persisted docs head is exact-head CI green, keep that as the checkpoint. Refresh independent review state without repeatedly dispatching broken/skipped launchers. Do not bypass the Stage-1 release freeze. Once Stage-1 acceptance is actually recorded, reconcile onto accepted `main` and prove real V7 B19–B24 persistence/customer seams before shared Stage-4 integration.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in this slice.
