# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B01–B28 semantics in the approved spec control over older paraphrases. Detailed RED/GREEN history remains in dated executable plans under `docs/superpowers/plans/`; this file is the current serialized handoff.

## Release boundary

- Direct `main` refreshed during the current serialized slice remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Later-stage integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` remain historical checkpoints only.
- Do not merge later-stage work to `main`, deploy/publish, promote workers, mutate admission/queues/scheduler, launch a production scan, broaden schema/RLS, rotate secrets, connect fabricated providers, or enable Premium/Grok while the Stage-1 release gate remains open.
- When the single Stage-1 release operator records publication and fresh non-owner acceptance, reconcile this branch onto then-current accepted `main` without reverting the V7 routes or #308 and require fresh exact integrated-head FixList CI before durable customer-path activation.

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

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Fallback-confidence and connected-GSC numeric source evidence are strict finite actual numbers. Durable V7 customer/card/export consumption remains open.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and literal exact producer scan identity. Family similarity, repair-local identity, structured/debug objects, or stringified structured identity cannot establish trust. Durable customer projection remains open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Known numeric zero remains known; malformed numeric evidence fails closed. Durable customer/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source prefers verified impact-4/5 findings with a two-item cap and otherwise one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller-owned wording. Completion-HMAC coverage privacy, authority fail-closed behavior, malformed coverage shape, structured text, malformed numeric evidence, and structured producer identity rejection are GREEN. Fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan or malformed numeric evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Malformed structured coverage state is projected to `unknown` before the signed B23 decision can expose it. Durable customer-visible adjusted-score consumption remains open.
- **B24 partial:** signed handoff-v2 source requires literal trusted exact scan identity and verified B20 root-cause mapping; historical v1 reader compatibility remains preserved; `suppressed_findings` requires literal `operator_authorized is True`. Customer-safe scan/fix/B19-factor projection is positive-allowlisted and type-checked. Structured producer scan identity now fails closed before signed handoff construction. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest serialized slice — exact-scan identity fail-closed

Fresh source inspection found a real B20/B22/B24 identity-authority defect in `scanner-api/app/repair_contract_v2.py`. `_trusted_stage3_scan_id()` passed producer `scan_id` and `scan_run_id` through `_clean_text()`. Matching dictionaries/lists could therefore stringify into identical non-empty text and be accepted as a trusted exact producer scan identity. That malformed trusted value could feed B20 grouping and be serialized in signed B22/B24 source structures.

### RED

Commit `f0d6f217ab338874fc13dd576f40195af06a0fac` added `scanner-api/tests/test_stage3_exact_scan_identity_fail_closed.py`.

FixList CI `35559679611` proved the defect:

- immutable checkout matched the RED commit;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2081 passed, 18 skipped`;
- both failures were exactly the new regressions: structured matching scan IDs were trusted, and B24 source construction serialized that structured identity instead of failing closed;
- the independent lint/typecheck/generated-release-contract/frontend-contract/build job passed;
- corpus/frozen-revision/image steps were skipped after the intentional scanner-suite RED failure.

### GREEN

Implementation commit `08c94082bd731c371bc06946df5b821521aa3861` hardens `_trusted_stage3_scan_id()`:

- both identity fields must be actual strings;
- whitespace normalization happens only after type validation;
- both normalized strings must be non-empty and exactly equal;
- mappings, lists, booleans, numbers and other coercible values produce no trusted identity.

RED→GREEN compare changes exactly one implementation file, 9 additions / 4 deletions. Valid literal exact identities preserve prior behavior.

Exact-head FixList CI `35559929454` passed both jobs on `08c94082bd731c371bc06946df5b821521aa3861`:

- immutable checkout passed;
- root scanner regressions: `115 passed`;
- scanner-api: `2083 passed, 18 skipped`;
- both new exact-scan identity regressions passed;
- labelled Stage-1 synthetic corpus: `14 cases / 55 assertions`, `full_30_site_gate=not_assessed`;
- frozen beta revision: `01ebe8e90df1e6bd`;
- scanner image: `sha256:2f2a1f8d5a35a1ccdba861061c5ad58e42c98152b32ce0e2d44990c5ff30d5b8`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Runtime note: setup requested Node 20 but resolved Node `20.20.2`; exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted the Node-20 action-runtime deprecation warning.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-exact-scan-identity-fail-closed.md`.

## What remains before Stage 3 can be complete

1. Certify this run's final persisted documentation/checkpoint branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20/B23 evidence feeding signed delivery. A skipped/requested/failed automated review is not approval.
3. The separate Stage-1 release operator must record exact-source production publication and fresh non-owner acceptance.
4. Reconcile this integration branch onto then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Prove actual V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview paths, including suppressed/operator privacy and historical-v1 compatibility.
6. Persist exact source SHAs, regressions/failures, CI and independent-review evidence before declaring Stage 3 complete.

Stage 3 is **not complete**. Latest executable GREEN is `08c94082bd731c371bc06946df5b821521aa3861`, FixList CI `35559929454`. The final documentation head still requires its own exact-head CI before being called the stable checkpoint.

## Stage 4 handoff — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at refreshed checkpoint `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. Do not launch duplicate implementations and do not shared-integrate while Stage 3 acceptance remains open.

- **B25 incomplete:** genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures or historical summaries never satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance, live site/six-V7/worker identity proof, rollback proof, or real customer submit -> persistence -> reload/history -> rescan acceptance has been performed.

## Resume instruction

At the next serialized slice, first refresh `AGENTS.md`, `README.md`, the approved spec, `docs/full-blueprint-progress.md`, this handoff, current-main `docs/stage-one-evidence-acceptance.md`, applicable plans, PR #303 comments/reviews and branch heads.

If this run's final persisted docs head is exact-head CI green, keep that as the checkpoint. Refresh independent review state without repeatedly dispatching broken/skipped launchers. Do not bypass the Stage-1 release freeze. Once Stage-1 acceptance is actually recorded, reconcile onto accepted `main` and prove real V7 B19–B24 persistence/customer seams before shared Stage-4 integration.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in this slice.
