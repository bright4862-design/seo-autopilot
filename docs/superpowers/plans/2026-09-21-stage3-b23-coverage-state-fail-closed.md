# Stage 3 B23 malformed coverage-state fail-closed

Date: 2026-09-21

Authoritative requirement: B23 in `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

## Intent

B23 may apply only explicit verified root-cause score caps, must preserve existing access/sample/incomplete ceilings, and must expose unknown coverage rather than inventing or trusting malformed evidence. This slice hardens the signed Stage-3 health-score decision at the real canonical Review seam; it does not activate customer-visible score replacement or touch production.

## Defect

`scanner-api/app/repair_contract_v2.py::_stage3_coverage_state()` historically uses `_clean_text(...)`. When `site_fingerprint.coverage_assessment.state` is a mapping or list, that helper stringifies the structure. `_build_stage3_health_score_decision()` then passes the stringified value to `apply_root_cause_score_caps()`, and the resulting `stage3_health_score_decision` is attached to the canonical Review. The durable completion envelope HMAC-signs that Review.

Therefore malformed structured coverage evidence could survive as arbitrary text in the authenticated B23 decision instead of remaining unknown. A producer/debug sentinel URL or string embedded in the malformed structure could be retained even though invalid evidence must fail closed.

## RED

Commit: `43546cb8a0655c950e594a61f05167992297c696`

FixList CI: `35556402730`

Added `scanner-api/tests/test_stage3_b23_coverage_state_fail_closed.py` with three behavioral cases at the integrated B23 decision seam:

1. mapping-shaped authoritative coverage state containing a private/debug URL must produce `coverage_state == "unknown"` and the sentinel must not survive;
2. list-shaped authoritative coverage state containing a private sentinel must produce `coverage_state == "unknown"` and the sentinel must not survive;
3. when authoritative assessment state is absent, a valid existing review coverage state such as `limited_coverage` remains preserved.

The lint/typecheck/generated-contract/frontend/build job passed. The scanner job failed at the Python scanner-api step as intended; later corpus/frozen-revision/image steps were skipped by that RED failure. No scanner-api pass-count is recorded here because the workflow metadata available to this run did not expose a trustworthy numeric summary.

## GREEN

Implementation commit: `c1f7ebc04392e413a0181a791459b42fadfcf6a5`

FixList CI: `35556598093`

The correction is deliberately narrow and lives in `scanner-api/app/stage3_delivery.py`:

- added the documented B23 score-coverage vocabulary: `sufficient`, `limited_coverage`, `inventory_unproven`, `access_limited`, and `unknown`;
- added a fail-closed coverage projector that accepts only strings, normalizes case/whitespace, and maps every unknown or malformed value to `unknown`;
- `apply_root_cause_score_caps()` now publishes that bounded state rather than the caller's raw/stringified value;
- valid documented states and the existing explicit root-cause cap calculations remain unchanged.

`compare_commits(43546cb8... -> c1f7ebc0...)` shows exactly one implementation file changed: `scanner-api/app/stage3_delivery.py`, 17 additions and 1 deletion.

Exact-head FixList CI `35556598093` passed both jobs on `c1f7ebc04392e413a0181a791459b42fadfcf6a5`:

- immutable checkout passed;
- root scanner regressions passed;
- full Python scanner-api suite passed, including the new B23 cases;
- labelled Stage-1 synthetic corpus passed;
- frozen beta revision verification passed;
- production scanner image build passed;
- lint, typecheck, generated release-contract verification, frontend contract tests and production build passed.

The workflow metadata exposed success for the complete suite and image build but not a trustworthy scanner-api numeric total or image digest in this run, so neither is fabricated here.

## Invariants / release boundary

This slice does not change the legacy health score shown to customers. It only hardens authenticated Stage-3 decision evidence. Existing access/sample/incomplete ceilings remain inputs to B23 and no malformed coverage value can become a trusted new state.

No merge to `main`, deployment, worker promotion, admission/queue/scheduler mutation, production scan, schema/RLS change, secret change, provider connection, Premium enablement or Grok enablement occurred.

Stage 3 remains incomplete. It still requires a genuinely fresh independent review of the corrected B22/B24 authority/privacy boundary including upstream B19/B20/B23 evidence, separate Stage-1 exact-source publication plus fresh non-owner acceptance, reconciliation onto accepted `main`, exact integrated-head CI, and real V7 producer -> signed authority -> persisted rows -> exact-owner/exact-scan reload/history -> card/export/preview proof.

Stage 4 remains held. B25's genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures are not a substitute.
