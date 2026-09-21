# Stage 3 B24 signed handoff-v2 source checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved B24 semantics control over older lane/handoff paraphrases.

## Scope

This checkpoint advances B24 only inside the canonical Python Review -> completion-HMAC authority path. It does **not** create or copy a customer route, change V7 persistence, expose suppressed/operator-only findings, deploy production, or bypass the Stage-1 release freeze.

The eventual durable V7 exporter must consume this authenticated source after reconciliation onto the then-current accepted `main`; it must not independently reconstruct Stage-3 decisions from a second code path.

## Fresh release boundary

- `main` refreshed during this slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`.
- Current-main Stage-1 acceptance still records exact-source production publication and fresh non-owner acceptance as pending.
- No production deployment, worker promotion, admission mutation, live scan, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred.

## RED

Commit: `37b73a98e6b54db9c86f0de9eb921ff178a0201a`

Added `scanner-api/tests/test_stage3_b24_signed_handoff_source_integration.py` requiring:

- `stage3_handoff_v2_source` to exist before completion signing when producer `scan_id == scan_run_id`;
- exact producer scan identity and normalized domain in the handoff source;
- the actual FixList scanner user agent;
- B20-verified root-cause identity and family identity;
- B19 priority-factor evidence;
- canonical indexable/affected/count evidence without inventing missing values;
- no `suppressed_findings` or serialized `suppressed_members` in the customer-safe source;
- the completion HMAC to authenticate the exact B24 source;
- mismatched producer scan identity to fail closed by omitting the source.

FixList CI `35515644839` failed in `Run Python scanner-api tests` while the independent lint/typecheck/contracts/frontend job passed. This is the intended semantic RED: the source did not yet exist.

## First implementation and regression correction

Implementation commit: `5eb4b6751019e98f87afc3b329880fbd33e0fdd6`.

`scanner-api/app/repair_contract_v2.py` now:

- imports the existing reviewed B24 serializer rather than creating another contract;
- accepts B20 root-cause identity only from `grouping_state=verified` groups whose group `scan_id` equals the exact trusted enclosing producer identity;
- derives family IDs from the verified B20 family partitions, falling back only to already-stamped canonical family evidence;
- carries existing B21 observation/population counts, B19 priority factors, evidence references, verification/dependency/vendor fields and the real scanner user agent into the B24 serializer;
- calls `build_handoff_v2(..., operator_authorized=False)`, so operator/debug suppressed findings cannot enter the customer-safe source;
- fails the whole source closed if one canonical legacy action would require multiple different verified root-cause IDs in B24's singular `root_cause_id` field rather than guessing;
- attaches the completed source to the Review **before** `build_completion_envelope`, so the existing completion HMAC authenticates it;
- does not create or mutate V7 persistence/customer paths.

CI `35516002420` still failed the new Python regression because the initial fixture expected an indexable count to be derived even though no canonical `indexable_affected` evidence was supplied. The implementation correctly kept missing count evidence unknown instead of coercing it to zero or inferring it from page shape.

The regression was corrected at `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353` to supply the existing canonical count fields explicitly (`affected_*`, `checked_eligible`, `indexable_affected`, `indexable_checked_eligible`) and require the handoff to transport that evidence unchanged.

## GREEN

Executable checkpoint: `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353`

FixList CI: `35516240329` — **passed**.

Verified in that exact-head run:

- root scanner regressions passed;
- full Python scanner-api suite passed, including both new B24 signed-source regressions;
- labelled Stage-1 synthetic corpus passed and remains synthetic only;
- frozen beta revision check passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build passed.

## B24 requirement state after this slice

Implemented/proven at the signed authority source boundary:

- handoff-v2 versioned source;
- exact `scan_id` / `scan_run_id` binding;
- normalized-domain source identity;
- real scanner user agent;
- verified B20 root-cause/family identity without family-similarity substitution;
- canonical unique/observation/population/indexable count transport when those counts are evidenced;
- B19 priority-factor transport;
- evidence-reference, verification-step, dependency/vendor-owner transport through the existing serializer;
- operator-only suppression excluded from the customer-safe source;
- completion HMAC authentication of the exact source;
- fail-closed behavior for missing/mismatched producer identity and ambiguous multi-root-cause legacy actions.

Still open before B24 can be called complete overall:

- fresh independent review of this exact shared integration;
- reconciliation onto the then-current accepted Stage-1 `main`;
- real V7 persistence of the authenticated B24 source fields;
- authenticated customer/operator route consumption with historical-v1 compatibility;
- verified card/export/customer read-back with no suppressed/operator/private leakage;
- end-to-end producer -> signed authority -> persistence -> reload/history/export proof.

## Next action

Request focused independent review of the exact stable B24 integration. If review reports a material issue, reproduce it first, correct minimally and require fresh exact-head FixList CI.

Do not wire or recreate the V7 durable customer path until the single Stage-1 release operator records exact-source production publication and fresh non-owner acceptance, after which this branch must first be reconciled onto accepted `main` with fresh integrated-head CI.
