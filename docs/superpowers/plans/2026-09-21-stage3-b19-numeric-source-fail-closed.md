# Stage 3 B19 numeric source evidence fail-closed checkpoint

Date: 2026-09-21

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B19 semantics in the approved spec control over older paraphrases: priority evidence is impact × reach × page value × confidence, optional connected-provider evidence must be valid evidence, and missing/invalid evidence remains unknown rather than being manufactured by coercion.

## Preconditions refreshed

Before this slice the serialized integration branch was `agent/full-blueprint-stage2-coverage-b06-20260919` at certified head `d6a7e6a338b705a8bf34f0529534adaf4c70b47f`; exact-head FixList CI `35549862013` passed.

Fresh repository state was read from `AGENTS.md`, `README.md`, the approved blueprint spec, `docs/full-blueprint-progress.md`, `docs/blueprint-checkpoint-handoff.md`, current-main `docs/stage-one-evidence-acceptance.md`, applicable Stage-3 plans, PR #303 comments/reviews, and branch heads. Direct `main` remained `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`. Current-main Stage-1 acceptance still records exact-source production publication and fresh non-owner acceptance as pending, so no later-stage merge/deploy/worker/admission/scan action is authorized.

Fresh submitted-review state still contains only older reviews and does not provide a genuinely fresh independent review of the current B22/B24 shared authority/privacy boundary. This slice did not substitute another broken/skipped reviewer dispatch for implementation.

## Defect

`scanner-api/app/stage3_priority_factors.py` had two B19 numeric-source coercion paths:

1. `_verification_class()` fell back to `float(confidence)`, allowing a numeric string such as `"95"` to manufacture `verified` confidence when no explicit verification/evidence state existed.
2. `_valid_gsc_page_value()` used `float(normalized_page_value)`, allowing string `"0.9"` and boolean `True` to become trusted connected GSC page-value evidence and increase the B19 page-value factor.

That violated the approved fail-closed evidence semantics. Provider connection metadata alone must not make malformed numeric evidence valid, and malformed fallback confidence must not create higher trust.

## RED

Commit `f94eeeac974be8afe317437c31d04adc5237ba76` added `scanner-api/tests/test_stage3_b19_numeric_source_fail_closed.py` with three adversarial regressions:

- numeric-string fallback confidence cannot manufacture `verified` evidence;
- string-valued connected GSC normalized page value cannot boost the page-value factor;
- boolean connected GSC normalized page value cannot boost the page-value factor.

FixList CI `35553020191` failed in the scanner-api step exactly as intended:

- root regressions: `115 passed`;
- scanner-api: `3 failed, 2075 passed, 18 skipped`;
- all three failures were the new B19 regressions: `"95"` was classified `verified`, `"0.9"` produced page value `0.9`, and `True` produced page value `1.0`;
- the separate lint/typecheck/generated-release-contract/frontend-contract/build job passed;
- corpus/frozen/image steps were skipped after the intentional scanner-api failure.

## GREEN

Implementation commit `058f46fce08c3aec66fac35a3af18a4607eb30bf` changes only `scanner-api/app/stage3_priority_factors.py` relative to the RED head (`13` additions, `8` deletions):

- adds `_finite_number()` at the B19 source-evidence boundary;
- accepts only actual `int`/`float` values;
- rejects booleans, strings and other non-numeric shapes;
- rejects NaN and infinities;
- fallback confidence uses the strict finite-number projector before trust classification;
- connected GSC normalized page value uses the same strict finite-number projector before range validation;
- valid finite numeric evidence and existing B19 factor semantics remain unchanged.

Exact-head FixList CI `35553077583` passed both jobs on `058f46fce08c3aec66fac35a3af18a4607eb30bf`:

- immutable checkout matched the exact SHA;
- root regressions: `115 passed`;
- scanner-api: `2078 passed, 18 skipped`, including all three new B19 regressions;
- labelled Stage-1 corpus remained `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- production scanner image: `sha256:083616943a94b11c1c66c97db27b81c015801a6fa92494c013f1004f73adc32e`;
- lint, typecheck, generated release-contract verification, frontend contract tests and production build passed.

Runtime evidence: Ubuntu 24.04.5, Python 3.12.14. `setup-node` requested major Node 20 and resolved `20.20.2`, so this is not exact Node 20.19.5 evidence. GitHub also emitted the Node-24 action-runtime migration warning for actions targeting Node 20.

## Requirement state

- **B19 remains partial.** The signed Review now also fails closed malformed fallback-confidence and connected-GSC numeric source evidence before the exact four-factor calculation. Durable V7 FixItem/customer/card/export consumption is still release-gated.
- **B20–B24 remain partial** at their previously certified corrected boundaries; no semantics were weakened by this slice.
- A fresh independent review of the corrected B22/B24 shared authority/privacy boundary, including upstream B20/B19 evidence feeding handoff-v2, remains required before Stage 3 can be recorded complete.
- The separate Stage-1 operator must still record exact-source production publication plus fresh non-owner acceptance before this branch may be reconciled onto accepted `main` and real V7 persistence/customer seams can be completed.
- Stage 4 remains held. The genuine provenance-labelled B25 30-site baseline/candidate gate remains `not_assessed`; the synthetic corpus does not satisfy it.

No production deployment, `main` merge, worker/admission/queue mutation, production scan, provider connection, schema/RLS broadening, secret rotation, Premium enablement or Grok enablement occurred in this slice.
