# Unresolved Template Placeholder Evidence — Implementation Plan

**Goal:** Detect strong, visibly rendered unresolved template placeholders on customer-facing commercial pages and surface them as bounded developer repairs, without changing Standard 150 crawl behavior, score mechanics, authority, or persistence contracts.

**Base:** `5a8022495e79eb6a229878643b076a924ac4048a`

## Safety constraints

- Use only visible HTML text already extracted from successfully fetched pages.
- Do not inspect scripts, styles, JSON, source templates, or hidden runtime state.
- Do not flag bare `XX` or a single bare `gvar` by itself.
- Treat `gvar+`, strongly delimited variable syntax, and action-copy such as `Visit our XX page` as strong signals.
- Exclude guide/article, route-boundary, archive, and location-landing surfaces from the new generic repair. Location pages stay owned by the existing location-template rule to avoid duplicate repairs.
- Group only inside one observed page-template family. Do not claim that different families share one implementation fix.
- Mark `shared_repair_confirmed` false: family similarity is pattern evidence, not proof of one shared component.
- No crawler topology, request budget, robots/SSRF, admission, scoring, authority, or release-path changes.

## TDD sequence

1. Add extraction tests for strong placeholder signatures (`gvar+`, approved delimited variables, contextual `Visit our XX page`).
2. Add negative tests for ordinary `XX`, a single literal `gvar`, article/code examples, and existing location-template ownership.
3. Add review test proving affected commercial pages are grouped by template family, with bounded evidence and no cross-family shared-fix claim.
4. Confirm the tests fail on the current main branch for the intended missing detector/repair.
5. Implement the smallest detector in `scanner-api/app/location_template_content.py`, expose bounded page evidence from `extract.py`, and add the new raw repair builder to `review.py`.
6. Add customer vocabulary/suggestion mapping only if the existing generic fallback is not clear enough; test before changing.
7. Run focused scanner tests, then full FixList CI. No deploy from this branch.

## Acceptance

A Center Street-like homepage containing `gvar+` and `Visit our XX page`, and loan pages containing the same strong placeholder leakage, produce confirmed, bounded developer repairs by template family. A guide showing placeholder syntax as documentation, a page containing bare `XX`, or one literal `gvar` does not create a customer repair.
