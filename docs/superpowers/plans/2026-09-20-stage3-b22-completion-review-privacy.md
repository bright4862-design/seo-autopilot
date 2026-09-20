# Stage 3 B22 completion-Review privacy correction

Date: 2026-09-20

Authoritative requirement: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, B22, plus the blueprint-wide authenticated displayed-field and preview-privacy invariants.

## Fresh independent finding

Fresh CodeRabbit follow-up on PR #303, issue comment `5750887385`, found a material P1 privacy defect after the earlier B22 preview-source correction. The nested `stage3_private_preview_source` had stopped copying arbitrary `coverage_assessment.text`, but `apply_canonical_repair_contract()` still retained the original `site_fingerprint.coverage_assessment` object in the enclosing Review. `build_completion_envelope()` then HMAC-signed that complete Review. A producer/debug coverage string could therefore bypass the safe B22 projection and survive in the signed authority envelope beside it.

The review also statically confirmed the existing B22/B24 exact-scan, verified-finding, operator/suppression and entitlement-source controls; it did not execute repository tests.

## RED proof

Commit `db6432fcf7258e64736d7a3eabeadd28e4cb907f` strengthened `test_b22_coverage_qualification_never_copies_untrusted_review_text` to serialize the entire signed Review and the entire completion envelope, not only the nested preview source. The fixture inserts `PRIVATE-COVERAGE-SENTINEL` and `https://private.example/internal?token=debug` into `site_fingerprint.coverage_assessment.text`.

FixList CI `35521744377` failed exactly in the Python scanner-api regression step:

- 115 root tests passed;
- scanner-api: 1 failed / 2040 passed / 18 skipped;
- the sole failure showed the private sentinel and URL still present in `envelope["review"]["site_fingerprint"]["coverage_assessment"]["text"]`;
- lint, typecheck, generated-contract checks, frontend contracts and frontend build passed independently.

This is executable RED evidence for the authority-boundary leak.

## Correction

Commit `4d1575d92c6a3092661bcd290b7d8ef4ae883066` adds `completion_review_payload()` at the common completion-HMAC boundary.

The completion Review now positive-allowlists the current scanner-owned structured coverage-decision fields:

- `coverage_authority_version`
- `state`
- `reasons`
- `authoritative`
- `score_is_provisional`
- `release_gate_eligible`
- `inventory`
- `inventory_proof`
- `thresholds`

Arbitrary `text` and every unknown/future coverage-assessment field fail closed before HMAC signing. The helper copies the Review/fingerprint containers rather than mutating the producer Review. The existing limited-result path is unchanged because it already constructs its own explicit structured payload. B22's customer-intended coverage qualification remains fixed controller-owned wording and is not reconstructed from producer prose.

## GREEN proof

Exact executable FixList CI `35522106799` passed both jobs on `4d1575d92c6a3092661bcd290b7d8ef4ae883066`:

- 115 root tests passed;
- scanner-api: 2041 passed / 18 skipped;
- B22 signed-preview integration: 5 passed;
- synthetic Stage-1 corpus: 14 cases / 55 assertions, provenance `synthetic`, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- scanner image built as `sha256:2f630706c1a594fe2d1ec22858e05bc74625bf5113bfc67052e275576748e592`;
- lint, typecheck, generated release contracts, frontend contracts and frontend build passed.

Environment evidence: Ubuntu 24.04.5, Python 3.12.14. The workflow requests Node 20 but `actions/setup-node` resolved Node 20.20.2; action runtimes emit the Node-24 migration warning, so this is not represented as exact Node 20.19.5 evidence.

## Requirement state

- B22 signed preview-source semantics remain GREEN at the executable boundary: exact trusted producer identity, exact verified findings, preferred verified impact-4/5 set with existing two-item cap, exactly one best verified fallback otherwise, allowlisted finding projection, fixed safe good-shape wording only under explicit sufficient coverage, and signed non-entitlement marker.
- B22 completion-Review privacy is now RED -> GREEN: raw/free-form coverage prose and unknown future assessment fields cannot cross the full signed completion Review through `coverage_assessment`.
- B22 remains **partial**, not complete, because the real V7 exact-owner/exact-scan entitlement, persistence/read/reload/history/preview/card/export path is still Stage-1-release-gated.
- B24 remains **partial** pending a clean fresh combined follow-up review and real V7 persistence/read/customer/operator/export proof, including historical-v1 compatibility.
- B25 genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`.

## Release boundary / next action

`main` was refreshed and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`. Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source publication and fresh non-owner production acceptance as pending. No deployment, publication, worker/admission mutation, production scan, schema/RLS/secret change, Premium enablement or Grok enablement is authorized by this checkpoint.

Persist this correction into the authoritative progress/handoff records and PR #303, run exact-head CI on that persisted stable head, then request one fresh independent CodeRabbit review of the corrected combined B22/B24 signed authority/privacy surface. Do not count the request as a review pass. After Stage-1 acceptance is actually recorded, reconcile onto accepted `main`, preserve V7/#308, run fresh integrated-head CI, then prove the durable customer path with RED -> GREEN persistence/read/reload/history/card/export/preview tests before closing Stage 3.
