# Stage 3 B19 factor-range fail-closed checkpoint

Date: 2026-09-21

Authoritative requirement: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, especially B19, B21, B22 and B24. The approved spec controls over older handoff paraphrases.

## Scope

This serialized slice inspected the already-integrated Stage-3 delivery boundary after the exact-scan identity hardening. No production publication, worker/admission/queue/scheduler mutation, production scan, schema/RLS change, secret rotation, provider fabrication, Premium enablement, Grok enablement, or Stage-4 shared integration was performed.

Fresh source inspection found that `scanner-api/app/stage3_delivery.py` accepted actual numeric values without enforcing B19's documented factor ranges at downstream delivery boundaries. That allowed out-of-range values such as `impact=99`, `reach=1.5`, `page_value=-0.1`, `confidence=2.0`, or `priority_factor_score=42.0` to be treated as trusted B19 evidence by B21/B22/B24 even though the B19 producer's valid domain is bounded: impact 0..5, reach/page-value/confidence 0..1, and the four-factor product 0..5.

Invalid or impossible factor evidence must remain unknown. It must not manufacture a high-impact preview, outrank valid candidates, or enter a customer-safe signed handoff as trusted evidence.

## RED proof

Commit: `fd12cd307987587ac99246bec93914724c9e1f9b`

New regression file: `scanner-api/tests/test_stage3_b19_factor_range_fail_closed.py`

The regressions prove:

1. B22 does not promote an out-of-range `impact=99` / `priority_score=99` candidate as a verified high-impact preview over a valid impact-3 candidate.
2. B24 projects out-of-range B19 factors to unknown (`None`) instead of serializing them as trusted factor evidence.
3. Valid upper boundaries (`impact=5`, unit factors `1.0`, product score `5.0`) remain preserved.

FixList CI: `35563364990`

Observed RED result:

- immutable checkout matched `fd12cd307987587ac99246bec93914724c9e1f9b`;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2084 passed, 18 skipped`;
- the two failures were exactly the two new negative factor-range regressions; the positive boundary regression passed;
- independent lint/typecheck/generated-release-contract/frontend-contract/production-build job passed;
- labelled corpus, frozen-revision and scanner-image steps were skipped after the intentional scanner-suite failure.

## GREEN implementation

Commit: `c8e88394e32421b7706197750da618e105fe2a6b`

RED-to-GREEN compare changes exactly `scanner-api/app/stage3_delivery.py`: 42 additions / 22 deletions.

The correction adds explicit downstream validators for the documented B19 domains and applies them wherever Stage-3 delivery consumes the factors:

- impact: exact non-negative integer in `0..5`;
- reach: finite actual number in `0..1`;
- page value: finite actual number in `0..1`;
- confidence: finite actual number in `0..1`;
- four-factor priority score: finite actual number in `0..5`.

B21 ranking now defers an out-of-range B19 score as unknown rather than ranking on it. B22 high-impact selection and projected impact use the bounded impact scale, and preview priority consumes only a bounded B19 product score. B24's positive-allowlisted B19 projection keeps invalid/out-of-range factor values as `None` while preserving valid boundary values. Historical v1 handoff reading and literal operator-only suppressed finding behavior are unchanged.

FixList CI: `35563424610`

Observed GREEN result:

- both jobs passed on immutable checkout `c8e88394e32421b7706197750da618e105fe2a6b`;
- root scanner regressions: `115 passed`;
- scanner-api: `2086 passed, 18 skipped`;
- all three new factor-range regressions passed;
- labelled Stage-1 corpus remained explicitly synthetic: `14 cases / 55 assertions`, `full_30_site_gate=not_assessed`;
- frozen scanner revision matched `01ebe8e90df1e6bd`;
- production scanner image built as `sha256:dc2f58206b7f754c8d31fafbaf12f27f603c156e3d07456b159f3cd5c2f5ac27`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Runtime note: the workflow requested Node 20 and resolved Node `20.20.2`, not exact Node 20.19.5. Exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted the Node-20 action-runtime deprecation warning.

## Requirement state after this slice

- B19: partial. Four-factor producer and signed Review evidence are implemented and this downstream range boundary is fail-closed; durable V7 customer/card/export consumption remains release-gated.
- B21: partial. Honest counts and rank-before-truncate are implemented; durable persistence/customer proof remains open.
- B22: partial. Verified evidence-led private preview source is implemented and now rejects impossible B19 factor ranges; fresh independent review and durable exact-owner/exact-scan V7 preview proof remain open.
- B24: partial. Customer-safe handoff-v2 positive projection now rejects impossible B19 factor ranges; historical v1 compatibility remains; durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

Stage 3 is not complete. Current review state still contains only older submitted reviews; CodeRabbit's current issue comment says automatic review is skipped for this repository because it has fewer than 10 stars. A skipped review is not independent approval.

## Release boundary / next action

Direct `main` remained `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` at the start of this slice, and current-main Stage-1 acceptance still records exact-source publication plus fresh non-owner acceptance as pending. Do not reconcile, deploy, promote, mutate production admission, or run a production scan from this branch.

After this plan and the authoritative progress/handoff ledgers are persisted, the final documentation/checkpoint branch head itself must receive exact-head FixList CI before it is called the stable serialized checkpoint. Then refresh review and Stage-1 release state. Once Stage-1 acceptance is genuinely recorded, reconcile onto accepted `main`, preserve V7/#308, run exact integrated-head CI, and prove real producer -> signed authority -> persisted rows -> exact-owner/exact-scan reload/history -> card/export/preview seams before shared Stage-4 integration.

The genuine provenance-labelled B25 30-site baseline/candidate gate remains `not_assessed`; this slice does not change that state.
