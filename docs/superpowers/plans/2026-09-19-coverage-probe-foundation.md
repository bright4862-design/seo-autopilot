# Stage 2 coverage probe foundation

Status: B06 source slice implemented and CI-verified on `agent/full-blueprint-stage2-coverage-b06-20260919`; not merged/deployed/live. This resumes the approved full-scanner blueprint; it does not reopen Stage 1 or authorize a different release path.

## Slice owned here

Implement the shared finite follow-up request pool required by B06–B18, then use it for B06 unsampled same-site internal-link integrity. The assessed-page cap stays unchanged. Probe requests use the existing DNS/SSRF/body/redirect/robots path and are diagnostic evidence, not extra assessed pages.

Acceptance for this slice:

1. One scheduler owns a declared per-mode probe allowance and the crawler's existing finite `max_pages * 8` request ceiling.
2. Actual repeated request identities are reused instead of charged/fetched twice; redirect hops spend the same pool.
3. Unsampled same-site internal links retain target, source page and link text provenance.
4. Verified HTTP 404/410 targets outside the assessed sample create an existing authenticated broken-page repair without changing the assessed-page count.
5. Robots blocks, challenges, transport failure, deadline exhaustion and request-budget exhaustion stay `not_verified`; exhaustion never becomes a pass.
6. New B06 coverage repairs are non-scoring until Stage 3's root-cause caps and four-factor priority are implemented.
7. A real Python producer → local review → authority writer → persisted rows → verified customer output regression proves the repair survives the current signed path.

## Next dependency order

After this checkpoint, extend the same scheduler rather than creating new pools: B07 active soft-404 probes, B09 sitemap integrity targets and B16 URL variants. B08 destination meaning should reuse redirect evidence. Then proceed through B10–B18 and only afterward Stage 3 decision semantics.


## Verification checkpoint

Code checkpoint `d88b5b89a870b9f502f46da654eab9c831945c40` passed FixList CI run 35450285277: 1,806 scanner tests passed with 18 intentional skips; 1,479 frontend tests passed; lint, typecheck, generated-contract checks, labelled Stage-1 corpus verification, frozen revision, frontend build and production scanner-image build passed.

The required producer-to-customer regression passes with `affected_observed=1`, `affected_eligible=0` for an unsampled verified 404. Wrong evidence versions and unverified states remain at zero observed evidence. This establishes B06 source acceptance only; it is not merge/deployment/live acceptance.

Next: B07 active soft-404 probes on this same scheduler.
