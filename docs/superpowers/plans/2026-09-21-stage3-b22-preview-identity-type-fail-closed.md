# Stage 3 B22 private-preview identity type fail-closed

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved B22 semantics control: the private preview is evidence-led, individually verified, entitlement/owner protected, exact-scan scoped, and must not expose hidden/operator findings. Missing or invalid evidence remains unknown/fails closed.

## Scope

This serialized slice hardens only the B22 customer-facing private-preview identity boundary. It does not change producer URL identity, normalize scan IDs, change entitlement semantics, write production state, alter Stage-1 release state, or integrate Stage 4.

Fresh inspection of `scanner-api/app/stage3_delivery.py::_preview_eligible()` found that candidate `scan_id` / `owner_id` and requested identities were compared with raw Python equality. Matching structured values (for example a dict or list present on both sides) could therefore satisfy the exact-owner/exact-scan check and expose an otherwise verified finding through `select_private_preview()`. Structured producer/debug identity is not a valid customer authority identity.

## RED

Commit: `1b3f5ae219a733f8b9642761c0ef75d89f4ef65e`

Added `scanner-api/tests/test_stage3_b22_preview_identity_type_fail_closed.py` with:

- a matching structured scan identity containing a private sentinel, which must not authorize preview;
- a matching structured owner identity containing a private sentinel, which must not authorize preview;
- a positive control proving literal exact non-empty string scan/owner identity still authorizes an otherwise eligible verified finding.

FixList CI: `35571403257`

- immutable checkout matched the RED commit;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2090 passed, 18 skipped`;
- the two failures were exactly the two new malformed-identity negatives, both returning `findings` instead of `not_available`;
- the literal exact-string positive control passed;
- lint, typecheck, generated release contracts, frontend contracts and build passed;
- corpus/frozen-revision/image steps were skipped after the intentional scanner-suite RED failure.

## GREEN

Implementation commit: `4ef7fb44a1bdb614d7bea764aa121dfac355f61c`

`_preview_eligible()` now requires:

- requested `scan_id` to be an actual non-empty string;
- requested `owner_id` to be an actual non-empty string;
- candidate `scan_id` and `owner_id` to be actual strings;
- literal exact equality after type validation;
- existing literal `authority_verified is True`, `preview_allowed is True`, and `evidence_state == "verified"` gates remain unchanged.

No string coercion or identity normalization was introduced. Structured/list/dict/bool/numeric values fail closed. RED→GREEN compare changes exactly `scanner-api/app/stage3_delivery.py`: 10 additions / 2 deletions.

Exact-source FixList CI: `35571774891`, both jobs passed.

- root scanner regressions: `115 passed`;
- scanner-api: `2092 passed, 18 skipped`;
- all three new B22 identity regressions passed;
- labelled Stage-1 corpus remains explicitly synthetic: `14 cases / 55 assertions`, `full_30_site_gate=not_assessed`;
- frozen beta revision: `01ebe8e90df1e6bd`;
- scanner image: `sha256:a52ecebf7b90fdd6793ecf106444052d5d65737ca21a443c28e51f4a109d28a0`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Runtime note: workflow setup requested Node 20 but resolved Node `20.20.2`; exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted its Node-20 action-runtime deprecation warning.

## Requirement state

- **B22 remains partial, not complete.** This slice closes the structured exact-owner/exact-scan type-confusion path at the customer private-preview selector. The existing signed evidence-led source and projection/privacy regressions remain intact.
- A genuinely fresh independent review of the latest corrected B22/B24 authority/privacy boundary is still required.
- Durable real V7 producer -> signed authority -> persisted rows -> exact-owner/exact-scan reload/history -> customer preview/card/export proof remains release-gated.
- Stage-1 exact-source production publication and fresh non-owner acceptance are still separate prerequisites before reconciliation to accepted `main`.
- Stage 4 remains held; B25's genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`.

## Release boundary

Direct `main` remains the separately frozen Stage-1 line until refreshed otherwise; no merge/deploy, worker/admission/queue/scheduler mutation, production scan/rebuild, schema/RLS broadening, secret rotation, provider fabrication, Premium enablement or Grok enablement is authorized by this checkpoint.

## Next action

Persist this slice in `docs/full-blueprint-progress.md`, `docs/blueprint-checkpoint-handoff.md`, and PR #303; then require exact-head FixList CI on the resulting final documentation/checkpoint SHA before calling it the stable serialized checkpoint. Refresh review and Stage-1 acceptance state without dispatching duplicate/broken agents.