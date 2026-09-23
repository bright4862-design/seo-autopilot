# Blueprint implementation checkpoint

## Current checkpoint — 2026-09-23

The original B01–B28 scanner blueprint is complete through Stages 1–4 and landed in `main`, per the release owner's 2026-09-23 handoff. Stage 4 landed through PR #319 (`dad5722fe787d608289ecb358acd65e87258a0e8`); subsequent production recovery moved the product to V8. Do not rebuild these stages or apply the obsolete Stage-1 freeze below.

Freshly read repository main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`. Current AI integration checkpoint inspected: `8faf869a66316bd7cbe3d749028853748a392944`. Integration-branch implementation is not a production release claim.

The active roadmap and next integration gates are recorded in [AI-layer current checkpoint](ai-layer/2026-09-23-current-checkpoint.md). The approved AI design is [the 2026-09-22 blueprint](superpowers/specs/2026-09-22-ai-layer-architecture-blueprint.md). The single AI Integrator owns shared seams, merges and deployment. Preserve Standard 150, V8, sealed authority and historical results; keep runtime AI/chat disabled.

Production acceptance in the owner's handoff: worker `fixlist-standard150-worker-00095-sn2`; Funbooker scan `6ab2abb3763febb79a7470e4` and rerun `6ab314008da962a9f8c58929` completed and rendered; rerun links to `6ab272fc6dfa7f9faf97a90f`. These live observations were supplied by the release owner, not independently repeated in this documentation run.

## Archived checkpoint — 2026-09-21, superseded

Everything below preserves the historical implementation/test record. Its descriptions of current main, incomplete stages, freezes, resume instructions and release gates are historical, not current instructions. Dated test results apply only to the SHAs originally recorded.

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
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and literal exact producer scan identity. Family similarity or structured/coercible identity cannot establish trust. Stage-3 customer-bound group/member/family/reference identifiers reject structured upstream coercion. Durable customer projection remains open.
- **B21 partial:** signed Review has exact unique affected-page / observation / known-population / displayed-sample counts and ranks all eligible B19 candidates before truncation. Malformed numeric count evidence remains unknown; malformed explicit observation evidence no longer becomes a fabricated zero; real observation lists remain a truthful count fallback; a supplied known population smaller than the exact affected-page union fails closed to unknown; customer-bound displayed IDs reject structured coercion. Durable customer/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source prefers verified impact-4/5 findings with a two-item cap and otherwise one best verified fallback; good-shape requires explicit sufficient coverage and fixed controller wording. Customer private preview requires literal non-empty string requested scan/owner identity and string candidate identity before exact equality. Producer rule/title projection accepts only literal strings with safe fallback instead of stringifying structured/debug values. Fresh independent review and durable exact-owner/exact-scan V7 customer proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence can contribute documented score caps; conflicting/unverified/cross-scan or malformed evidence fails closed and stricter access/sample/incomplete ceilings remain authoritative. Customer-bound root-cause-cap identifiers reject structured coercion. Durable customer-visible adjusted-score consumption remains open.
- **B24 partial:** signed handoff-v2 requires literal trusted exact scan identity and verified B20 root-cause mapping; historical v1 reader compatibility remains preserved; `suppressed_findings` requires literal `operator_authorized is True`. Scan metadata, fix title/ID, family/evidence references and vendor-owner projection fail closed before signing. Contradictory B21 population denominators and malformed B21 observation counts cannot be signed as known values. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Latest serialized slice — B21/B24 observation-count unknown fail-closed

Fresh B21/B24 inspection found an invalid-evidence coercion in `scanner-api/app/stage3_delivery.py`. `summarize_candidate_counts()` strictly rejected malformed explicit `observation_count`, but then always normalized `observations` with `_list()` and used its length. Missing or malformed observation collections therefore became `[]`, allowing invalid explicit evidence to become `0` rather than remain unknown. Because B24 uses the same helper, that fabricated zero could enter the signed customer handoff.

### RED

Commit `913dfd011aced1cd6a348468dcfd357bd316c40a` added `scanner-api/tests/test_stage3_b21_observation_count_unknown.py` with three behavioral regressions:

- malformed explicit observation count without a real observation list must remain `None`;
- structured operator/debug count must remain unknown in B24 handoff-v2 and its private sentinel must not leak;
- a real observation list may still truthfully supply its length when the explicit count is invalid.

FixList CI `35581103845` produced the intended RED. Immutable checkout matched. The separate lint/typecheck/generated-contract/frontend/build job passed. The scanner job passed root scanner regressions and failed at the Python scanner-api step; labelled corpus, frozen-revision and image steps were skipped after the intentional RED failure.

### SOURCE CORRECTION

Implementation commit `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658` changes the fallback so:

- a real list/tuple of observations supplies its actual length;
- explicitly present malformed observation/count evidence remains `None`;
- only the historical case where both fields are entirely absent preserves the prior zero fallback.

RED-to-source compare changes exactly one implementation file: `scanner-api/app/stage3_delivery.py`, 8 additions / 3 deletions. No ranking, URL identity, score, preview, historical reader/signature, network, admission, persistence or release behavior changed.

### GREEN

Exact-source FixList CI `35581439449` passed both jobs on `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`.

Verified steps: immutable checkout; root scanner regressions; full Python scanner-api suite including the new B21/B24 tests; labelled Stage-1 synthetic corpus; frozen beta revision verification; production scanner image build; lint; typecheck; generated release-contract verification; frontend contract tests; and production build. The available GitHub job metadata for this run does not expose trustworthy pytest totals or image digest, so they are not fabricated in this record.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b21-observation-count-unknown-fail-closed.md`.

Prior B22/B24 upstream projection hardening remains certified at stable persisted checkpoint `fc7d9359870efdfa437b2c9c7e38c115c198de00`, exact-head CI `35577485322`; its source GREEN was `dfb9043d3cbf510ec867c68a5cde02c7cea29323`, CI `35577052441`. Earlier B19/B20/B21/B22/B23/B24 fail-closed slices remain in this branch history and their executable plans/regressions remain authoritative.

## What remains before Stage 3 can be complete

1. Certify this run's final persisted plan/ledger branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the current corrected B19–B24 shared authority/privacy boundary. A skipped automatic review or old September 19 submission is not approval.
3. The separate Stage-1 release operator must record exact-source production publication and fresh non-owner acceptance.
4. Reconcile this integration branch onto then-current accepted `main`, preserve V7/#308, and run fresh exact integrated-head CI.
5. Prove actual V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview paths, including suppressed/operator privacy and historical-v1 compatibility.
6. Persist exact source SHAs, regressions/failures, CI and independent-review evidence before declaring Stage 3 complete.

Stage 3 is **not complete**. Latest executable source GREEN is `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`, FixList CI `35581439449`. This handoff update occurs after source certification, so the resulting final persisted documentation head requires its own exact-head CI before being called the stable checkpoint.

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