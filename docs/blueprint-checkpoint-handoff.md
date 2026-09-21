# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B01–B28 semantics in the approved spec control over older paraphrases. Detailed RED/GREEN history remains in dated executable plans under `docs/superpowers/plans/`; this file is the current serialized handoff.

## Release boundary

- Direct `main` refreshed during this 2026-09-21 serialized work remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending; no accepted Stage-1 production deployment is recorded.
- Later-stage integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` remain historical checkpoints only.
- Do not merge later-stage work to `main`, deploy/publish, promote workers, mutate admission/queues/scheduler, launch a production scan, broaden schema/RLS, rotate secrets, connect fabricated providers, or enable Premium/Grok while the Stage-1 release gate remains open.
- When the single Stage-1 release operator records publication and fresh non-owner acceptance, reconcile this branch onto then-current accepted `main` without reverting V7 routes or #308 and require fresh exact integrated-head FixList CI before durable customer-path activation.

## Stage 2 handoff

B06–B18 are complete for implementation, independent review and exact-head CI at corrected checkpoint `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This does not imply production release completion.

Preserve during later reconciliation: one finite shared follow-up request budget; Standard-150 assessed cap; truthful assessed denominators; unknown states for robots/challenge/429/incomplete/budget/deadline; exact route/evidence identity; robots/DNS/SSRF/redirect/body/deadline protections; optional providers disconnected by default; fail-closed external projection; original historical signatures and readers. Direct authenticated HTTP `/scan` privacy regression `d9061f23edd0a0541b017f42297bf60a9c401560`, CI `35524582769`, proves B10/B11/B13/B15 private sentinels do not survive the serialized response.

## Stage 3 handoff — in progress

Existing isolated lanes were integrated serially, not merged to `main`: B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`; B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`; combined lane CI `35501672504` passed.

Current requirement state:

- **B19 partial:** signed canonical Review uses exact impact × reach × page value × confidence with versioned explanations and truthful unknowns; repair leverage is not a factor. Numeric source evidence and downstream factor domains are fail-closed. Durable V7 customer/card/export consumption remains open.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and literal exact producer scan identity. Family similarity or structured/coercible identity cannot establish trust. Stage-3 customer-bound group/member/family/reference identifiers now reject structured upstream coercion. Durable customer projection remains open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Malformed numeric count evidence remains unknown; a supplied known population smaller than the exact affected-page union fails closed to unknown; customer-bound displayed IDs reject structured coercion. Durable customer/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source prefers verified impact-4/5 findings with a two-item cap and otherwise one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller wording. Customer private preview requires literal non-empty string requested scan/owner identity and string candidate identity before exact equality. Producer rule/title projection now accepts only literal strings with safe fallback instead of stringifying structured/debug values. Fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan or malformed evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Customer-bound root-cause-cap identifiers reject structured coercion. Durable customer-visible adjusted-score consumption remains open.
- **B24 partial:** signed handoff-v2 requires literal trusted exact scan identity and verified B20 root-cause mapping; historical v1 reader compatibility remains preserved; `suppressed_findings` requires literal `operator_authorized is True`. Scan metadata, fix title/ID, family/evidence references and vendor-owner projection fail closed before signing rather than accepting upstream stringification. Contradictory B21 population denominators cannot be signed as known. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest serialized slice — B22/B24 upstream signed-projection coercion fail-closed

Fresh producer-to-authority inspection found the strict B22/B24 serializers could be bypassed one layer earlier because `scanner-api/app/repair_contract_v2.py` reused the legacy coercive `_clean_text()` helper at the Stage-3 trust seam. A dict/list/debug object could become non-empty plain text before the downstream serializer applied its type checks.

### RED

Commit `8800fa6f72caf814024b965b5c3eb5c59b5515db` added signed-source integration regressions in `scanner-api/tests/test_stage3_b24_signed_handoff_source_integration.py`.

FixList CI `35576295545` reproduced two concrete defects:

- immutable checkout matched the RED SHA;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2092 passed, 18 skipped`;
- structured `scan_result.normalized_domain` was stringified into the B24 signed customer handoff instead of becoming unknown;
- structured `issue_title` / `evidence_refs` were stringified before B22/B24 projection, allowing producer/debug structure to become customer text;
- lint, typecheck, generated release contracts, frontend contracts and production build passed;
- corpus/frozen-revision/image steps were skipped after the intentional scanner-suite RED failure.

### SOURCE CORRECTION

Implementation commit `5708b1b6b7fd661c7343d574ca08e785e3ba32f7` adds Stage-3-specific literal-string projection helpers in `scanner-api/app/repair_contract_v2.py`. It does not globally alter legacy `_clean_text()` behavior.

The strict projection is used for:

- exact B20 group/member identity consumed by B24;
- root-cause and repair-surface identifiers;
- B22 rule/title fallback;
- B24 rule/title/vendor owner, family/evidence references and scan metadata;
- B21 customer-bound displayed IDs;
- B23 root-cause-cap identifiers.

Structured/non-string values fail closed while valid literal strings retain the prior fallback order. RED-to-source-correction compare changes exactly one implementation file: `scanner-api/app/repair_contract_v2.py`, 46 additions / 27 deletions.

FixList CI `35576782551` confirmed the two reproduced customer-source leaks were corrected, but retained one failing assertion because the new regression incorrectly required the *entire signed internal Review* to omit the private sentinel. The internal canonical Review deliberately retains richer producer/review evidence; B22/B24 constrain the customer projections inside that signed Review. That run therefore ended `1 failed, 2093 passed, 18 skipped` with root tests `115 passed`, while lint/typecheck/generated-contract/frontend/build passed. Corpus/frozen/image steps were skipped after the scanner-suite failure.

### GREEN

Test-scope correction commit `dfb9043d3cbf510ec867c68a5cde02c7cea29323` keeps the no-leak assertion on the two actual signed customer projections after `build_completion_envelope()` rather than redefining unrelated internal Review fields as customer-safe.

Exact-source FixList CI `35577052441` passed both jobs on that exact SHA:

- immutable checkout matched `dfb9043d3cbf510ec867c68a5cde02c7cea29323`;
- root scanner regressions: `115 passed`;
- scanner-api: `2094 passed, 18 skipped`;
- all new B22/B24 signed-projection coercion regressions passed;
- labelled Stage-1 corpus remained explicitly synthetic: `14 cases / 55 assertions`, `full_30_site_gate=not_assessed`;
- frozen beta revision matched `01ebe8e90df1e6bd`;
- scanner image: `sha256:4e9407eba4ede42737012e22c730905ffa2dfe1dd9e06a5fbefe7f29eeead33e`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build all passed.

Runtime note: setup requested Node 20 but resolved Node `20.20.2`; exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted the Node-20 action-runtime deprecation warning.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b22-b24-upstream-projection-coercion-fail-closed.md`.

Prior B22 exact-owner/exact-scan identity hardening remains certified at `4ef7fb44a1bdb614d7bea764aa121dfac355f61c`, CI `35571774891`. Earlier B19/B20/B21/B23/B24 fail-closed slices remain in this branch history and their executable plans/regressions remain authoritative.

## What remains before Stage 3 can be complete

1. Certify this run's final persisted plan/ledger branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20/B21/B23 evidence feeding signed delivery. A skipped automatic review is not approval.
3. The separate Stage-1 release operator must record exact-source production publication and fresh non-owner acceptance.
4. Reconcile this integration branch onto then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Prove actual V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview paths, including suppressed/operator privacy and historical-v1 compatibility.
6. Persist exact source SHAs, regressions/failures, CI and independent-review evidence before declaring Stage 3 complete.

Stage 3 is **not complete**. Latest executable source GREEN is `dfb9043d3cbf510ec867c68a5cde02c7cea29323`, FixList CI `35577052441`. This handoff update occurs after source certification, so the resulting final persisted documentation head requires its own exact-head CI before being called the stable checkpoint.

## Stage 4 handoff — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at checkpoint `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. Do not launch duplicate implementations and do not shared-integrate while Stage 3 acceptance remains open.

- **B25 incomplete:** genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures or historical summaries never satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance, live site/six-V7/worker identity proof, rollback proof, or real customer submit -> persistence -> reload/history -> rescan acceptance has been performed.

## Resume instruction

At the next serialized slice, first refresh `AGENTS.md`, `README.md`, the approved spec, `docs/full-blueprint-progress.md`, this handoff, current-main `docs/stage-one-evidence-acceptance.md`, applicable plans, PR #303 comments/reviews and branch heads.

If this run's final persisted docs head is exact-head CI green, keep that as the checkpoint. Refresh independent review state without repeatedly dispatching broken/skipped launchers. Do not bypass the Stage-1 release freeze. Once Stage-1 acceptance is actually recorded, reconcile onto accepted `main` and prove real V7 B19–B24 persistence/customer seams before shared Stage-4 integration.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in this slice.