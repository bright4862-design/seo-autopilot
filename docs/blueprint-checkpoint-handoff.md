# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B01–B28 semantics in the approved spec control over older paraphrases. Detailed RED/GREEN history remains in dated executable plans under `docs/superpowers/plans/`; this file is the current serialized handoff.

## Release boundary

- `main` refreshed during the current serialized slice remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Later-stage integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` remain historical checkpoints only.
- Do not merge later-stage work to `main`, deploy/publish, promote workers, mutate admission/queues/scheduler, launch a production scan, broaden schema/RLS, rotate secrets, connect fabricated providers, or enable Premium/Grok while the Stage-1 release gate remains open.
- When the single Stage-1 release operator records publication and fresh non-owner acceptance, reconcile this branch onto then-current accepted `main` without reverting the six V7 routes or #308 and require fresh exact integrated-head FixList CI before durable customer-path work.

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

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Fallback-confidence and connected-GSC numeric source evidence are now strict finite actual numbers: strings, booleans, NaN and infinities fail closed. Durable V7 customer/card/export consumption remains open.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and trusted enclosing `scan_id == scan_run_id`; family similarity, repair-local identity, or structured/debug objects cannot establish trust. Durable customer projection remains open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Known numeric zero remains known; malformed numeric evidence fails closed. Durable customer/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source prefers verified impact-4/5 findings with a two-item cap and otherwise one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller-owned wording. Completion-HMAC coverage privacy, authority fail-closed behavior, malformed coverage shape, structured text and malformed numeric evidence are GREEN. Fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan or malformed numeric evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Durable customer-visible adjusted-score consumption remains open.
- **B24 partial:** signed handoff-v2 source requires trusted exact scan identity and verified B20 root-cause mapping; historical v1 reader compatibility remains preserved; `suppressed_findings` requires literal `operator_authorized is True`. Customer-safe scan/fix/B19-factor projection is positive-allowlisted and type-checked. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest serialized slice — B19 numeric source evidence fail-closed

Fresh inspection found two real B19 source-evidence coercion defects in `scanner-api/app/stage3_priority_factors.py`:

1. fallback confidence used `float(confidence)`, so a string such as `"95"` could manufacture `verified` confidence without an explicit verified state;
2. connected GSC normalized page value used `float(...)`, so malformed string `"0.9"` or boolean `True` could become trusted provider evidence and boost page value.

### RED

Commit `f94eeeac974be8afe317437c31d04adc5237ba76` added `scanner-api/tests/test_stage3_b19_numeric_source_fail_closed.py`.

FixList CI `35553020191` proved the defect:

- root regressions: `115 passed`;
- scanner-api: `3 failed, 2075 passed, 18 skipped`;
- all three failures were exactly the new adversarial cases: `"95"` became `verified`, string GSC `"0.9"` produced page value `0.9`, and boolean GSC `True` produced page value `1.0`;
- the separate lint/typecheck/generated-release-contract/frontend-contract/build job passed;
- corpus/frozen/image steps were skipped after the intentional RED scanner-api failure.

### GREEN

Implementation commit `058f46fce08c3aec66fac35a3af18a4607eb30bf` adds a strict finite-number projector at the B19 source-evidence boundary:

- only actual `int`/`float` values are accepted;
- booleans, strings and other non-numeric shapes remain invalid/unknown;
- NaN and infinities remain invalid/unknown;
- fallback confidence uses this projector before trust classification;
- connected GSC normalized page value uses it before the existing 0..1 range validation;
- valid finite numeric evidence and the exact impact × reach × page value × confidence semantics remain unchanged.

The source correction relative to RED changes only `scanner-api/app/stage3_priority_factors.py` (`13` additions, `8` deletions).

Exact-head FixList CI `35553077583` passed both jobs on `058f46fce08c3aec66fac35a3af18a4607eb30bf`:

- immutable checkout matched the exact SHA;
- root regressions: `115 passed`;
- scanner-api: `2078 passed, 18 skipped`, including all three new B19 regressions;
- labelled Stage-1 corpus remained `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- production scanner image `sha256:083616943a94b11c1c66c97db27b81c015801a6fa92494c013f1004f73adc32e`;
- lint, typecheck, generated release-contract verification, frontend contract tests and production build passed.

Runtime evidence: Ubuntu 24.04.5, Python 3.12.14. `setup-node` requested major Node 20 and resolved `20.20.2`, so this is not exact Node 20.19.5 evidence. GitHub emitted the Node-24 action-runtime migration warning.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b19-numeric-source-fail-closed.md`.

The previous B20 explicit-root-cause type correction remains GREEN at `590dc20251952e76f265c76e40d4755299d0b6cc`, CI `35549679233`. The previous B24 customer-safe projection correction remains GREEN at `ef0204b9a7851a53c040b334f99e1e541097d4b3`, CI `35546802039`. Fresh submitted-review state still does not provide a genuinely current independent review of the corrected B22/B24 boundary; an automatic-review skip or stale submission is not approval.

## What remains before Stage 3 can be complete

1. Certify this run's final persisted documentation/ledger branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the corrected B22/B24 shared authority/privacy boundary, including the upstream B19/B20 evidence feeding handoff-v2. A skipped/requested/failed automated review is not approval.
3. The separate Stage-1 release operator must record exact-source production publication and fresh non-owner acceptance.
4. Reconcile this integration branch onto then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Prove actual V7 B19/B21/B22/B23/B24 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview paths, including suppressed/operator privacy and historical-v1 compatibility.
6. Persist exact source SHAs, regressions/failures, CI and independent-review evidence before declaring Stage 3 complete.

Stage 3 is **not complete**. Latest executable GREEN is `058f46fce08c3aec66fac35a3af18a4607eb30bf`, FixList CI `35553077583`. The final documentation head still requires its own exact-head CI before being called the stable checkpoint.

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
