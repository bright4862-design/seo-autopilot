# Stage 3 — completion coverage-shape fail-closed checkpoint

Date: 2026-09-20
Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`
PR: #303
Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`

## Scope

This slice addresses the fresh B22 completion-authority privacy finding in `scanner-api/app/scan_job.py`: `completion_review_payload()` positive-allowlisted mapping-shaped `site_fingerprint.coverage_assessment`, but a malformed non-mapping value could survive unchanged into the Review signed by `build_completion_envelope()`.

The correction is intentionally narrow. It does not touch the frozen V7 durable/customer routes, production, admission, workers, schema/RLS, secrets, Premium, or Grok.

## RED evidence

Regression commit: `60f52e8b304f65c89a30436a478ab75047ad3aad`.

Two adversarial regressions in `scanner-api/tests/test_stage3_completion_review_privacy.py` inject distinctive private sentinel URLs through malformed coverage assessments:

- scalar `coverage_assessment`;
- list-shaped `coverage_assessment`.

FixList CI `35534328975` failed the scanner-api suite exactly on those two assertions: `2 failed, 2046 passed, 18 skipped`. The same RED run also failed the separate generated Base44 Python review-client/release-contract artifact verification, so that run is not represented as otherwise green.

An accidental whole-file edit of `scanner-api/app/scan_job.py` occurred at `dcad8174f3781ef1a012530f6cd98e482e73ed0b`; the exact previous blob was restored immediately in the forward commit `65905f9a30fd731fb466b6c2574cb1eaa2482ded`. No force-push, deployment, or production mutation occurred.

## GREEN implementation

Implementation commit: `7d7dd19e7c77bdc03a93a081e7dab42d23cffd00`.

`completion_review_payload()` now preserves the existing positive allowlist for mapping-shaped coverage decisions and fails closed when the field is present with any non-mapping shape:

```python
if isinstance(assessment, dict):
    projected_fingerprint["coverage_assessment"] = {
        key: assessment[key]
        for key in _COMPLETION_COVERAGE_ASSESSMENT_FIELDS
        if key in assessment
    }
elif "coverage_assessment" in fingerprint:
    projected_fingerprint["coverage_assessment"] = {}
```

Semantics:

- valid mappings keep only scanner-owned allowlisted fields;
- malformed scalar/list/future non-mapping values become `{}` before HMAC signing;
- an absent `coverage_assessment` remains absent;
- no arbitrary producer/debug text can survive through the malformed-shape path.

## Exact-head verification

FixList CI `35537701598` checked out exact SHA `7d7dd19e7c77bdc03a93a081e7dab42d23cffd00` and passed both jobs.

Scanner regression job:

- root regressions: `115 passed`;
- scanner-api: `2048 passed, 18 skipped`;
- the scalar/list malformed-shape privacy regressions passed;
- Stage-1 corpus: provenance `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen beta revision `01ebe8e90df1e6bd` matched live code;
- production scanner image built: `sha256:a4118fa8ab73ac94d873e4aa30e4d9c1ef0db13c3ae061da8893b584af38bfc2`.

Independent lint/typecheck/contracts/frontend job also passed, including generated release-contract verification. The separate generated-client artifact failure seen on RED CI `35534328975` therefore did not persist on the corrected exact head.

Runtime evidence: Ubuntu 24.04 / Bash; Python 3.12.14. `actions/setup-node@v4` requested Node 20 but resolved Node `20.20.2`; this is not exact Node 20.19.5 evidence. GitHub Actions also emitted the Node-24 action-runtime migration warning.

## Requirement status

- B22 completion-authority privacy: implementation and behavioral regression GREEN for malformed coverage-assessment shapes.
- B24 is unchanged by this slice.
- Stage 3 remains **in progress**. A fresh independent review of the latest corrected shared B22/B24 boundary is still required, and the real V7 persistence/read/reload/history/card/export/preview seams remain release-gated.
- B25 genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`.

## Release boundary / next action

`main` and `docs/stage-one-evidence-acceptance.md` must be refreshed before any subsequent shared/durable slice. Until the single Stage-1 release operator records exact-source publication and fresh non-owner acceptance, do not reconcile onto `main`, deploy/publish, promote a worker, mutate admission/queues/scheduler, submit a production scan, touch schema/RLS/secrets, or enable Premium/Grok.

After this plan plus the authoritative ledgers are persisted, certify the resulting final documentation head with exact-head FixList CI. Then refresh PR #303 comments/reviews for a genuinely independent current-head review; a skipped/failed review is not approval.
