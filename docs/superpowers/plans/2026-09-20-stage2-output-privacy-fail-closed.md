# Stage 2 output privacy fail-closed checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Scope: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`. This checkpoint remains off `main` and authorizes no deployment, admission, worker, provider, schema, secret, or production-scan change.

## Defect reproduced

The prior Stage-2 privacy correction removed the known B10/B13/B14/B15 page intermediates and reduced the currently known B13/B14 scan aggregate. A fresh source inspection found that `project_local_entity_scan_evidence()` still forwarded unknown future top-level aggregate keys and unknown future `nap_consistency` keys by default. That was not genuinely fail-closed: a later producer/debug addition containing exact page URLs, entity IDs, raw observations, headings, or similar private evidence could silently cross the HTTP/authority/persistence boundary without being added to a deny-list.

RED regression commit: `661b9e2121c6f49bd50dedc64bdce1c73cf54b6b`.

FixList CI `35495870104` failed specifically in the `Run Python scanner-api tests` step while the independent lint/typecheck/contracts/frontend-build job passed. The new regression injects future-shaped sensitive fields at aggregate, NAP and inconsistency levels and requires exact entity/page/text sentinels to be absent from the external projection.

## Correction

Executable fix commit: `fda78e9aa4fe823e2067837041f3cba538712f3b`.

`scanner-api/app/page_output_privacy.py` now uses positive allowlists for:

- the B13/B14 aggregate top-level version/count/truncation fields;
- B13 completeness rows;
- the B14 NAP summary;
- B14 inconsistency rows.

Unknown future producer/debug fields are dropped by default. The approved current non-content state/count surface remains available. The page-level projection and the common post-crawl placement are unchanged.

`scanner-api/tests/test_stage2_output_privacy_fail_closed.py` contains two adversarial regressions proving that future top-level, NAP and inconsistency identity/content additions cannot become external output merely because the producer learns a new field.

## Verification

FixList CI `35495894222` passed both jobs on exact executable SHA `fda78e9aa4fe823e2067837041f3cba538712f3b`:

- immutable checkout: passed;
- root scanner regressions: passed;
- full Python `scanner-api` suite, including the two new fail-closed projection regressions: passed;
- labelled Stage-1 synthetic corpus: passed and remains synthetic rather than the genuine B25 30-site gate;
- frozen beta revision verification: passed;
- production scanner-image build: passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

No production operation was performed.

## Stage 2 state

B06–B18 source integration remains at the final independent-review gate. This hardening does not change customer-visible B13/B14 semantics; it strengthens the privacy boundary so unknown future fields fail closed.

A fresh independent review must examine the corrected current head. Any new material finding still requires a reproducing behavioral regression, minimal correction, and fresh exact-head FixList CI before Stage 2 can be recorded complete or Stage 3 shared integration can begin.

## Next action

After the documentation checkpoint is stable and exact-head CI is green, request one fresh independent review of the current PR #303 head. Do not begin shared B19–B24 integration until that review actually reports no unresolved material Stage-2 issue.
