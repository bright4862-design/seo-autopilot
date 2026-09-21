# Stage 2 B13/B14 — local entity and cross-page NAP evidence

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

## Scope

This slice implements conservative B13 local-entity completeness/status evidence and B14 provenance-bearing cross-page NAP evidence without adding a new fetch path, request budget, customer repair, score adjustment or sitewide consistency claim.

The implementation consumes only accepted Standard-150 HTML and already-retained discovery provenance. Entity identity is never inferred from matching names, phones, addresses, page families, forms, sitemap membership or visible text.

## Current producer contract

`scanner-api/app/stage2_local_entity_producer.py` emits bounded observations under:

- `local_entity_producer_v1_jsonld_explicit_identity`;
- `local_entity_context_provenance_v1`.

Accepted JSON-LD LocalBusiness/Store-family observations can retain explicitly present:

- name;
- address;
- phone;
- regular hours;
- schema type;
- JSON-LD entity ID;
- optional holiday-hours/photos/sameAs/parent-entity presence;
- contextual open/closed/Coming Soon evidence;
- explicit form/store-finder/sitemap provenance.

Malformed, oversized or unusable HTML remains unverified. Optional holiday hours/photos/sameAs/parent fields are not universal requirements.

## Contextual status rules

Status is admitted only from bounded explicit provenance:

1. explicit structured fields (`businessStatus`, `openingStatus`, `status`) when the value maps unambiguously to `coming_soon`, `open` or `closed`;
2. otherwise a conservative accepted title/H1 phrase such as `Coming Soon`, `Opening Soon`, `Now Open`, `Temporarily Closed` or `Permanently Closed`.

Arbitrary body text does not establish business status. For example, `Customer support is closed Sundays` cannot mark a location closed.

Hours applicability follows the status rather than inventing a defect:

- explicit regular hours -> applicable;
- verified Coming Soon/closed -> missing regular hours are not a defect;
- verified open -> regular hours are applicable;
- unknown status and no hours -> applicability stays unknown.

## B14 entity identity and source provenance

Cross-page identity remains deliberately stricter than NAP similarity:

- only an explicit absolute HTTP(S) JSON-LD `@id` is currently verified for cross-page entity identity;
- relative/fragment IDs remain unverified without trusted document-base resolution;
- matching names, addresses, phone numbers or page-family similarity never prove identity;
- the same verified ID must appear on at least two distinct page URLs before NAP consistency can pass/fail;
- same-page duplicates/conflicts cannot become cross-page proof;
- distinct explicit IDs remain separate even with a shared phone;
- `sitewide_consistency_claim` remains false.

Additional source provenance is recorded without changing those identity rules:

- `form_explicit_entity_id` only when a form/subtree carries the exact already-verified absolute entity ID in an explicit entity/location/store ID attribute or field;
- `store_finder_explicit_entity_id` only when an explicit store-finder/locator marker and the exact already-verified entity ID occur together;
- `sitemap_reference` only from the retained page's actual `discovered_from` provenance at scan aggregation time.

Form/store-finder/sitemap context never promotes an observation that lacks the verified structured entity ID. This avoids turning matching NAP strings or generic locator markup into identity proof.

## Shared result / authority behavior

`build_local_entity_scan_evidence(pages)` aggregates only retained Standard-150 pages, capped at 20 selected observations while preserving eligible/truncation counts. `indexability_postprocess.py` attaches the aggregate to the shared scan result and `technical_audit_summary`, so the existing authority payload authenticates it.

The evidence is still internal/evidence-only. This slice does not create a B13/B14 repair, customer card, export row, score change or preview surface. Therefore no customer output has been invented simply to satisfy a test.

## Behavioral regressions

Existing B13/B14 tests continue to cover structured completeness, cross-page same-ID pass/fail, relative/no-ID fail-closed behavior, same-page duplicate protection, malformed/unusable HTML and bounded sampling.

`scanner-api/tests/test_stage2_local_entity_explicit_provenance.py` adds six adversarial regressions for:

1. explicit machine Coming Soon status making absent regular hours contextual rather than defective;
2. accepted title/H1 Coming Soon status;
3. incidental body `closed` wording not becoming location status;
4. exact form-ID provenance plus retained sitemap discovery provenance;
5. exact store-finder ID matching, with mismatched IDs ignored;
6. form/sitemap context never promoting missing structured entity identity.

## Verification

Exact executable head: `e906ef69c7b7deab3a1014c702b4f3af1453c54c`.

FixList CI `35490908086` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- root scanner regression step passed;
- full `scanner-api` suite passed, including the six new explicit-provenance regressions; relative to the prior 1,978-test checkpoint this adds six tests (1,984 passed / 18 intentional skips);
- labelled Stage-1 synthetic corpus passed and remains explicitly synthetic; the genuine 30-site gate remains `not_assessed`;
- frozen scanner revision check passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

The workflow environment continues to resolve Node 20.20.x rather than serving as Node 20.19.5 runtime evidence.

## Remaining B13/B14 limits

This slice intentionally does not infer identity from generic visible text, generic form values or locator page shape. A store-finder/form can contribute identity only through an exact explicit machine ID already tied to the structured entity. Sitemap membership is provenance, not proof that two NAP records are one entity.

No live third-party location feed or external provider is required or claimed.

## Next serialized action

Treat B13/B14 source provenance as implemented pending whole-Stage-2 independent review. Stay on Stage 2: perform a fresh independent review of the combined B06–B18 source shape, reproduce and fix any material finding with behavioral regressions, then require fresh exact-head CI. Do not start shared Stage-3 integration until that review/CI gate is actually satisfied.
