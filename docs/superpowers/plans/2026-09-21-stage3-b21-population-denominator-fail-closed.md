# Stage 3 B21 population-denominator fail-closed checkpoint

Date: 2026-09-21

Authoritative requirements: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, especially B21 and B24. The approved spec controls over older handoff paraphrases.

## Scope

This serialized slice inspected the already-integrated B21 count projection and B24 customer handoff boundary. No production publication, deployment, worker/admission/queue/scheduler mutation, production scan, schema/RLS change, secret rotation, fabricated provider connection, Premium/Grok enablement, or Stage-4 shared integration was performed.

B21 requires honest, distinct unique-affected-page, observation, population and sample counts. Fresh inspection found `summarize_candidate_counts()` accepted any non-negative `known_population_count`, including a denominator smaller than the exact unique affected-page union. That can produce impossible evidence such as 2 confirmed unique affected pages with a known population of 1, and `_handoff_fix()` would carry that impossible denominator into the B24 customer handoff.

Invalid or internally inconsistent evidence must remain unknown. A known population cannot be smaller than its confirmed affected-page numerator.

## RED proof

Commit: `3d4b15d1ba486bb97283c528001ca007b3094a04`

New regression file: `scanner-api/tests/test_stage3_b21_population_truthfulness.py`

The regressions prove:

1. a `known_population_count` smaller than the exact unique affected-page union fails closed to `None`;
2. the impossible denominator is not serialized into B24 customer handoff counts;
3. a valid known population equal to the exact affected-page union remains known.

FixList CI: `35567099549`

Observed RED result:

- immutable checkout matched `3d4b15d1ba486bb97283c528001ca007b3094a04`;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2087 passed, 18 skipped`;
- both failures were exactly the two new negative B21/B24 denominator regressions; the positive equal-population regression passed;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed;
- labelled corpus, frozen-revision and scanner-image steps were skipped after the intentional scanner-suite RED failure.

## GREEN implementation

Commit: `ebd83739b49da4a7aabd3fef3c171da23cdd8dd8`

RED-to-GREEN compare changes exactly `scanner-api/app/stage3_delivery.py`: 6 additions / 0 deletions.

The correction preserves the existing non-coercive non-negative integer validator, then checks the candidate's exact affected-page union. If a supplied known population is smaller than that union, the population becomes `None`. This keeps the contradictory denominator unknown instead of signing an impossible ratio. Because B24 handoff construction uses the same `summarize_candidate_counts()` helper, the customer handoff inherits the fail-closed result without a second denominator implementation.

Valid equal/larger known populations remain unchanged. Observation counts, displayed sample counts, rank-before-truncate behavior, preview selection, score caps, historical-v1 handoff reading and operator-only suppressed findings are unchanged.

FixList CI: `35567449548`

Observed GREEN result:

- both jobs passed on immutable checkout `ebd83739b49da4a7aabd3fef3c171da23cdd8dd8`;
- root scanner regressions: `115 passed`;
- scanner-api: `2089 passed, 18 skipped`;
- all three new B21 population regressions passed;
- labelled Stage-1 corpus remained explicitly synthetic: `14 cases / 55 assertions`, `full_30_site_gate=not_assessed`;
- frozen scanner revision matched `01ebe8e90df1e6bd`;
- production scanner image built as `sha256:04782550e621a58e28d9c59be13a9efed5e14d566149f2b28fa500f28e03aeb3`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Runtime note: the workflow requested Node 20 and resolved Node `20.20.2`, not exact Node 20.19.5. Exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted the Node-20 action-runtime deprecation warning.

## Requirement state after this slice

- B21 remains partial overall: exact unions precede sampling, all eligible B19 candidates rank before truncation, numeric count evidence is non-coercive, and an impossible known-population denominator now fails closed. Durable V7 persistence/card/export proof remains release-gated.
- B24 remains partial overall: customer handoff-v2 now cannot sign an internally impossible B21 population denominator; historical v1 compatibility remains preserved. Durable V7 persistence/read/customer/operator/export proof and a genuinely fresh independent review remain open.

Stage 3 is not complete. Current review state still lacks a genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary and upstream evidence feeding signed delivery.

## Release boundary / next action

Direct `main` remained `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` at the start of this slice, and current-main Stage-1 acceptance still records exact-source production publication plus fresh non-owner acceptance as pending. Do not reconcile, merge, deploy, promote, mutate production admission, or run a production scan from this branch.

After this plan and the authoritative progress/handoff ledgers are persisted, the final documentation/checkpoint branch head itself must receive exact-head FixList CI before it is called the stable serialized checkpoint. Then refresh PR review and Stage-1 release state. Once Stage-1 acceptance is genuinely recorded, reconcile onto accepted `main`, preserve V7/#308, run exact integrated-head CI, and prove the real producer -> signed authority -> persisted rows -> exact-owner/exact-scan reload/history -> card/export/preview seams before shared Stage-4 integration.

The genuine provenance-labelled B25 30-site baseline/candidate gate remains `not_assessed`; this slice does not change that state.
