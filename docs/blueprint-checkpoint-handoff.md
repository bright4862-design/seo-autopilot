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

Direct authenticated HTTP `/scan` privacy regression `d9061f23edd0a0541b017f42297bf60a9c401560`, CI `35524582769`, proves B10/B11/B13/B15 private sentinels do not survive the serialized response.

## Stage 3 handoff — in progress

Isolated lanes were integrated serially, not merged to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

Current requirement state:

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Durable V7 customer/card/export consumption is open.
- **B20 partial:** verified shared root-cause grouping requires explicit versioned same-cause evidence and trusted enclosing `scan_id == scan_run_id`; family similarity and repair-local identity alone cannot establish trust. Scan-isolation P1 was RED at `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`, fixed through `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` + `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`, with CI `35504200573` and clean follow-up `5749166024`. Durable projection is open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Known numeric zero remains known; unknown composite does not borrow impact. Stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a`, CI `35513093636`, review follow-up `5750062094` clean. Durable customer/card/export proof is open.
- **B22 partial:** signed evidence-led preview source exists, prefers verified impact-4/5 findings with two-item cap, otherwise exactly one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller-owned wording. Arbitrary producer coverage text is excluded from nested preview and completion-HMAC Review. Current malformed-shape correction is GREEN but fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Stable checkpoint `4ee24691f46721ffe8112bb435f278e5dd810721`, CI `35514613656`, focused review `5750230877` clean. Durable customer-visible score consumption remains open.
- **B24 partial:** signed handoff-v2 source requires trusted exact scan identity and verified B20 root-cause mapping; carries family IDs, B19 factors, B21 counts, evidence refs, verification/dependency/vendor metadata and scanner UA; historical v1 reader compatibility remains preserved. `suppressed_findings` now requires literal `operator_authorized is True`; durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest completion-coverage privacy slice

Fresh review identified a real completion-authority fail-open shape: `completion_review_payload()` sanitized mapping-shaped `site_fingerprint.coverage_assessment`, but malformed scalar/list values could survive into the Review HMAC-signed by `build_completion_envelope()`.

### RED

Commit `60f52e8b304f65c89a30436a478ab75047ad3aad` added two adversarial regressions in `scanner-api/tests/test_stage3_completion_review_privacy.py`, one scalar and one list-shaped sentinel.

FixList CI `35534328975` failed those two privacy tests: `2 failed, 2046 passed, 18 skipped`. The same RED run also failed generated Base44 Python review-client/release-contract artifact verification, so it is not described as otherwise green.

An accidental whole-file replacement of `scanner-api/app/scan_job.py` occurred at `dcad8174f3781ef1a012530f6cd98e482e73ed0b`; exact previous content was immediately restored by forward commit `65905f9a30fd731fb466b6c2574cb1eaa2482ded`. No force-push or production mutation occurred.

### GREEN

Implementation commit `7d7dd19e7c77bdc03a93a081e7dab42d23cffd00` keeps the existing positive allowlist for valid mapping-shaped coverage decisions and, when `coverage_assessment` is present but non-mapping, projects it to `{}` before HMAC signing. If the field is absent, it remains absent.

Exact-head FixList CI `35537701598` passed both jobs on `7d7dd19e...`:

- root regressions: `115 passed`;
- scanner-api: `2048 passed, 18 skipped`;
- scalar/list malformed-shape regressions passed;
- Stage-1 synthetic corpus: provenance `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- production scanner image: `sha256:a4118fa8ab73ac94d873e4aa30e4d9c1ef0db13c3ae061da8893b584af38bfc2`;
- lint, typecheck, generated release contracts, frontend contract tests and production build passed.

The generated-client/release-contract failure from the RED run did not reproduce on the GREEN head.

Runtime evidence: Ubuntu 24.04 / Bash; Python 3.12.14; Node was requested as major 20 and resolved to `20.20.2`, so this is not exact Node 20.19.5 evidence. GitHub emitted the action-runtime Node-24 migration warning.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-completion-coverage-shape-fail-closed.md`.

## What remains before Stage 3 can be complete

1. Certify the final persisted documentation/ledger branch head with exact-head FixList CI.
2. Refresh PR #303 comments/reviews and obtain one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary. A skipped/failed automated review is not approval.
3. Stage-1 exact-source publication and fresh non-owner acceptance must be recorded by the separate release operator.
4. Reconcile this integration branch onto the then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Complete the actual V7 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview seams for B19/B21/B22/B23/B24. Prove suppressed/operator-only findings never enter customer output and historical v1 remains readable.
6. Persist exact source SHAs, tests/failures and independent review evidence before declaring Stage 3 complete.

## Stage 4 handoff — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. Do not launch duplicate implementations.

- **B25 incomplete:** genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures or historical summaries never satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source production deployment/live acceptance, live site/six-V7/worker identity proof, rollback proof or real customer submit → persistence → reload/history → rescan acceptance has been performed.

## Resume instruction

First refresh `AGENTS.md`, `README.md`, the approved spec, this handoff, `docs/full-blueprint-progress.md`, current-main `docs/stage-one-evidence-acceptance.md`, applicable executable plans, PR #303 comments/reviews and branch heads.

Then inspect exact-head CI for the persisted documentation head and resolve any real failure inline. If green, refresh independent review state. Do not bypass the Stage-1 release freeze. When Stage-1 acceptance is actually recorded, reconcile onto accepted `main` and prove the real V7 B19–B24 persistence/customer seams before starting shared Stage-4 integration.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in this slice.
