# GEO Scoring Core Implementation Plan

> Execute this isolated core inline with the executing-plans workflow. Runtime integration is a separate dependency-gated delivery.

**Goal:** Produce a tested deterministic readiness aggregator and primary-source architecture research.
**Architecture:** A fixed registry consumes typed per-page observations. Missing observations remain unknown. The core never fetches, extracts content, grants authority or writes customer results.
**Tech stack:** Python standard library and pytest.
**Spec:** ../specs/2026-09-18-geo-readiness-design.md

## Global constraints

- Maximum 150 unique pages; no network or model calls.
- Separate readiness from actual AI visibility and SEO health.
- Fail closed for missing coverage and access-limited scans.
- No modification to scanner-agent files, release contracts or live routes.

## Task 1: Research and arithmetic contract

- [x] Compare Google and OpenAI guidance, the GEO paper, RFC 9309 and W3C PROV against the proposed score.
- [x] Record supported conclusions, product assumptions, competing architectures and source limitations in docs/geo-architecture-research.md.
- [x] Freeze arithmetic: for each check divide counts by its applicable-or-unknown page count; mean across eligible checks per dimension; mean across four dimensions. Coverage equals verified mass; score equals 100 * passed mass / verified mass. A missing dimension prevents scoring. Round display only, with half-up integer rounding. Publish uncertainty bounds 100*passed mass and 100*(passed mass + unknown mass), explicitly not statistical confidence intervals.

## Task 2: Pure evaluator

Create scanner-api/app/geo_readiness.py and scanner-api/tests/test_geo_readiness.py.
Interface: evaluate_geo(page_ids, observations, *, parent_authoritative=False, entry_verified=False, access_limited=False) -> dict.
Observation(page_id, check_id, state, evidence_ref='', reason='') is immutable.

- [x] Write tests: complete pass=100, complete failure=0, one dimension failed=75, missing dimension=null, access_limited=null, duplicate evidence rejected, unknown check rejected, missing evidence rejected, over-cap rejected, order invariance, unknown state handling and N/A coverage.
- [x] Run focused pytest and confirm failure before implementation.
- [x] Implement a fixed 12-check registry, full page/check matrix, validation, gates, counts, coverage and deterministic score.
- [x] Run focused tests, then the scanner suite. Review the diff for runtime imports; none are permitted in this slice.
- [x] Commit only the new core, tests and research/design documents.

## Follow-on boundary

This core accepts classified observations; it does not yet establish their truth. Extraction adapters, finding generation, authenticated snapshot versioning, entitlement projections and UI must pass the design's integration regressions before customer activation. No standalone core result is an authoritative FixList.
