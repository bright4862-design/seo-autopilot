# Stage 2 B13/B14 shared-result and authority checkpoint

Date: 2026-09-20

Integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

## Scope completed

This slice attaches the already-reviewed B13/B14 local-entity and cross-page NAP aggregate to the shared Standard-150 result after the final retained assessed-page set is known.

The integration is deliberately evidence-only:

- `scanner-api/app/indexability_postprocess.py` calls `build_local_entity_scan_evidence(pages)` on the exact retained pages already present in the successful scan result;
- the aggregate is attached as top-level `local_entity_scan_evidence` and inside `technical_audit_summary.local_entity_scan_evidence`;
- `build_authority_review_payload()` already signs the complete technical-audit summary, so the B13/B14 aggregate reaches the authenticated review/authority payload without changing historical attestation serialization for rows that do not contain the new field;
- the full durable completion envelope also signs the exact scanner result;
- this slice creates no local-entity/NAP repair, customer card, score change, request, provider lookup, or second budget;
- the assessed page count and retained page list are unchanged;
- `sitewide_consistency_claim` remains false.

## Behavioral regressions

New file: `scanner-api/tests/test_stage2_local_entity_result_authority.py`.

The regressions prove:

1. two retained pages carrying the same absolute HTTP(S) entity ID and matching NAP produce a bounded B14 `pass` aggregate that is present in both the shared scan result and signed review payload, without producing a customer repair;
2. a verified cross-page phone conflict produces authenticated B14 `fail` evidence while still not being promoted to a customer repair before an explicit product/display contract exists;
3. repeated relative/fragment IDs such as `#store` remain ambiguous and `not_verified` after shared-result attachment rather than becoming false cross-page identity proof.

Existing B13/B14 producer regressions continue to cover malformed JSON-LD, unusable/challenged evidence, optional hours applicability, duplicate same-page identities, distinct entity IDs sharing a phone, and bounded candidate selection.

## Exact verification

Exact executable head: `a1b11251fd88a4fa9311f18f9d37d6784f613b6b`.

FixList CI run: `35488452253` — **SUCCESS** on both jobs.

Verified on that exact SHA:

- immutable checkout matched `a1b11251fd88a4fa9311f18f9d37d6784f613b6b`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,971 passed / 18 intentional skips**;
- new B13/B14 shared-result/authority regressions: **3 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image build: `sha256:6f1d2a471032d26290a04657214a21a7191f234b568db34858f89a53905f1798`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`. This run therefore must not be described as Node `20.19.5` runtime evidence.

## Requirement state after this slice

- **B13:** accepted structured local-entity observations plus bounded retained-scan aggregate are now attached to the shared result/authority path. Generic visible-text/store-form identity and complete Coming Soon status inference remain intentionally unclaimed without explicit provenance.
- **B14:** explicit verified cross-page entity identity and NAP comparison now reach the shared result/authority path. Page-family similarity, matching names/addresses/phones and relative IDs remain insufficient identity proof. No sitewide consistency claim is made.
- **Customer exposure:** none added by this slice. Because no new B13/B14 repair/card/count/score is displayed, there is no customer-output claim to authenticate yet. Any future displayed local-entity/NAP finding must add the full producer → Review → signed authority → persistence → customer/card/handoff/export regression before exposure.

## Invariants checked

- Standard-150 assessed-page set and denominator unchanged;
- no network request or second scheduler introduced;
- robots, DNS/SSRF, redirect, body and deadline boundaries untouched;
- Python Review remains canonical ranking authority;
- exact scan isolation and durable completion signing unchanged;
- historical evidence/signature readers are not rewritten;
- missing/ambiguous identity remains `not_verified`;
- Premium/Grok and production state remain untouched.

## Review state

The implementation has exact-head CI evidence. A fresh independent whole-Stage-2 review is still required before B06–B18 can be declared source-complete. CodeRabbit's existing repository status/comment is not counted as a new review pass unless it actually reviews the current combined head.

## Exact next serialized action

Continue Stage 2 with B17 direct transfer-body byte evidence at the existing hardened fetch boundary. Record only bytes actually measured by the scanner, keep decoded HTML bytes separate, and keep unknown transfer size unknown rather than substituting decoded length or `Content-Length`. Then connect the already-built CrUX/GSC evidence envelopes through an authenticated exact-scan provider seam without creating provider access or weakening disconnected/stale/unavailable states.
