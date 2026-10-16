# Stage 3 B22 preview projection type fail-closed checkpoint

Date: 2026-09-21 (Europe/Paris local date)

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. This checkpoint records one serialized B22 privacy correction on PR #303; it does not close Stage 3 or authorize production changes.

## Scope

Requirement B22 permits an evidence-led private preview only from verified, authenticated evidence. The customer-safe preview projection was already a positive key whitelist, but `scanner-api/app/stage3_delivery.py::_preview_projection()` returned `rule_id`, `title`, and `evidence_summary` without validating their value types. A malformed producer/review object could therefore place structured dict/list data, including private/debug strings or URLs, inside those allowed keys and carry it into the signed/customer preview.

## RED proof

Commit: `b58478e456bc67bef293d8d84223e896201891bc`

FixList CI: `35540737270`

Added `scanner-api/tests/test_stage3_preview_projection_privacy.py` with two behaviors:

- structured dict/list values for `rule_id`, `title`, and `evidence_summary` containing a distinctive private sentinel must fail closed instead of reaching the preview;
- normal customer-safe string values, including a known numeric priority score of `0.0`, must remain unchanged.

The scanner regression job failed exactly the new privacy behavior: `1 failed, 2049 passed, 18 skipped`. The failing diff showed the sentinel-bearing dict/list values were returned unchanged. Root regressions were `115 passed`. The separate lint/typecheck/generated-contract/frontend-contract/build job passed.

## GREEN correction

Implementation commit: `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`

FixList CI: `35541044424`

`_preview_projection()` now routes the three customer text fields through `_preview_text()`. Only actual strings survive. Structured/non-string producer values project to `None`; impact keeps the existing bounded integer behavior. This is a minimal boundary correction and does not broaden preview eligibility, entitlement, authority, scan/owner identity, schema, or persistence.

Exact-head CI passed both jobs on `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`:

- immutable checkout matched the implementation SHA;
- root regressions: `115 passed`;
- scanner-api: `2050 passed, 18 skipped`;
- both new preview type/privacy regressions passed;
- labelled Stage-1 corpus remained explicitly `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd` matched;
- production scanner image built as `sha256:deef044ec3e1a2c025d3e741bbed5d78bda57d5ceb8bd9d7199bd32efa65e37a`;
- lint, typecheck, generated release-contract verification, frontend contract tests and production build passed.

Runner evidence: Ubuntu 24.04.5, Python 3.12.14. `setup-node` requested Node 20 but resolved Node `20.20.2`; this is not exact Node 20.19.5 evidence. GitHub also emitted its Node-24 action-runtime migration warning.

## Release / acceptance boundary

`main` was refreshed during this slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`. Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.

Therefore this slice did not merge to `main`, deploy/publish, promote a worker, mutate admission/queues/scheduler, submit a production scan, change schema/RLS/secrets, connect providers, or enable Premium/Grok.

## Requirement status after this correction

- B22 remains **partial**: the signed evidence-led preview source and its type/privacy boundary are GREEN, but a genuinely fresh independent review of the corrected shared B22/B24 boundary is still required, and the real accepted-main exact-owner/exact-scan persistence/read/reload/history/card/export/preview seam remains release-gated.
- B24 remains **partial** for the same fresh-review and durable-route gates; suppressed/operator-only findings remain customer-private and require literal operator authorization.
- Stage 3 remains **in progress**.
- Stage 4 remains **held**.
- B25's genuine provenance-labelled 30-site baseline/candidate gate remains **not assessed**; the synthetic 14-case corpus is not a substitute.

The current CodeRabbit PR summary says automatic review is skipped for this repository; a skipped review is not independent approval.

## Next serialized action

1. Persist this RED/GREEN evidence in `docs/full-blueprint-progress.md`, `docs/blueprint-checkpoint-handoff.md`, and PR #303.
2. Certify the resulting final persisted branch head with exact-head FixList CI.
3. Keep the V7 durable/customer path and Stage 4 untouched while Stage-1 publication/non-owner acceptance remains open.
4. Require one genuinely fresh independent review of the corrected B22/B24 boundary; do not treat the skipped CodeRabbit run as approval.
5. After the separate Stage-1 operator closes the release gate, reconcile this branch onto the accepted `main`, preserve V7/#308, rerun exact integrated-head CI, then prove real B19–B24 persistence/read/reload/history/card/export/preview behavior before shared Stage-4 integration.
