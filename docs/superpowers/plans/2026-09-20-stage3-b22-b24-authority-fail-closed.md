# Stage 3 B22/B24 authority fail-closed checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved B22/B24 semantics control over older handoff paraphrases.

## Scope

This checkpoint hardens two Stage-3 helper authority boundaries on the serialized integration branch only. It does not alter the frozen V7 durable/customer routes, production admission, worker traffic, schema/RLS, secrets, Premium, or Grok.

## Fresh state before the slice

- Integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303.
- Starting head: `e1670e584e4d2ad30cdb5515fb330c82a8fc87f3`.
- `main`: `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main Stage-1 acceptance record still says exact-source production publication and fresh non-owner acceptance are pending, so no reconciliation/deployment/customer-route mutation was permitted.
- B25 genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`.

## Defects reproduced

### B22 authority qualification fail-open

`select_private_preview()` sanitized coverage text, but it evaluated a caller-supplied `coverage_qualification` before checking `authority_verified`. With `authority_verified=False` and `state=sufficient`, it returned the fixed customer-safe sufficient-coverage message instead of failing closed to no qualification.

### B24 operator suppression truthiness fail-open

`build_handoff_v2()` accepted `operator_authorized` by truthiness. Truthy non-boolean values such as `1`, `"true"`, or `{"authorized": true}` therefore exposed `suppressed_findings`, despite B24 requiring those findings to remain operator/debug-only behind an actual authorization decision.

## RED evidence

Regression commit: `28f58efbd773637bfada09da5b0a99b7fcc03fbc`.

FixList CI run `35528067336` failed in the Python scanner-api step exactly on the four new adversarial cases while the independent lint/typecheck/generated-contract/frontend job passed.

Scanner-api summary at RED: `4 failed, 2042 passed, 18 skipped`.

Failures proved:

1. unverified B22 authority still returned `Coverage was sufficient for the assessed scan scope.`;
2. B24 exposed `suppressed_findings` for `operator_authorized=1`;
3. B24 exposed `suppressed_findings` for `operator_authorized="true"`;
4. B24 exposed `suppressed_findings` for `operator_authorized={"authorized": true}`.

## GREEN implementation

Implementation commit: `4a9e0d4dec048291be7956bb225ab1635af30bbc`.

- B22 now checks `authority_verified is True` before interpreting or projecting any coverage qualification. Failed authority returns `state=not_available`, no findings, and `coverage_qualification=None`.
- B24 now includes `suppressed_findings` only when `operator_authorized is True` literally. Truthy non-boolean values fail closed.
- Existing authenticated B22 selection semantics, fixed safe sufficient-coverage wording, B24 historical-v1 reader behavior, and signed-source integration remain unchanged.

FixList CI run `35528215150` passed both jobs on the exact implementation SHA.

Verification evidence:

- root regression suite: `115 passed`;
- scanner-api suite: `2046 passed, 18 skipped`;
- new authority regression file: `4 passed`;
- labelled Stage-1 synthetic corpus: `14 cases / 55 assertions`, provenance `synthetic`, `full_30_site_gate=not_assessed`;
- frozen revision: `01ebe8e90df1e6bd` matched;
- scanner image: `sha256:124ee33c14e185e89adbb49906941192d7a2f55ffe8356e8ad7d43c121a7d932`;
- lint, typecheck, generated release contracts, frontend contract tests, and frontend production build passed;
- hosted `setup-node` resolved Node `20.20.2`, so this is not exact Node `20.19.5` evidence.

## Requirement state after this slice

- **B22:** authority helper boundary is stricter and proven RED->GREEN. Signed preview source remains partial overall until the required independent review gate and later accepted-main V7 entitlement/persistence/read/reload/history/card/export proof are complete.
- **B24:** operator-only suppression projection is now literal-authorization fail-closed. Signed handoff-v2 source remains partial overall until independent review and the accepted-main durable V7 persistence/customer/operator/export path are proven.
- **B19/B20/B21/B23:** no semantics changed in this slice; existing checkpoints remain authoritative.
- **Stage 3:** remains `in progress`; this checkpoint is not a stage-complete claim.
- **Stage 4:** remains held; B25 real 30-site gate is still `not_assessed`.

## Next serialized action

After this checkpoint is persisted, obtain one fresh independent review of the corrected B22/B24 authority boundaries. Do not count a skipped/failed automated review as approval. Once Stage-1 exact-source publication and fresh non-owner acceptance are recorded, reconcile the integration branch onto the accepted `main` without reverting V7 routes/#308, run fresh integrated-head CI, and only then continue the real V7 B19-B24 persistence/read/reload/history/card/export wiring. Stage-4 work remains gated behind complete Stage-3 applicable acceptance.
