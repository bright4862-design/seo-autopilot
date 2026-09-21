# Stage 2 B15 — contextual freshness evidence

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

## Goal

Implement B15 as conservative, evidence-only contextual freshness on the retained assessed-page set. An old year, archive path, or historical article must never become a stale-content defect by itself. A fail requires explicit current-content language and contradictory temporal evidence in a current-scoped visible field.

This slice performs no network I/O, creates no new request budget, adds no repair/card/score change, and does not claim provider data.

## Producer

`scanner-api/app/stage2_freshness_producer.py` adds versioned producer `contextual_freshness_producer_v1_explicit_current_scope`.

Inputs are only already-extracted accepted page fields after the retained page set is fixed:

- title;
- H1;
- meta description;
- path as historical provenance only.

The producer fails closed unless the page passes the existing accepted usable-HTML gate.

Explicit current-content intent is limited to wording such as current/currently/latest/today/this week/month/year/up-to-date. Generic action language such as `apply now` is deliberately excluded because it does not prove that dated content claims to be current.

Dates are bounded and parsed conservatively from ISO dates, English month-year values, and years. Year-only evidence uses 31 December of the observed year so an unknown month is not silently treated as January and made artificially old.

A date is current-scoped only when it occurs in the same visible field as explicit current-content language and that field does not also contain explicit archive/history wording. Mixed `latest/current` plus `archive/historical` wording keeps the date historical, preserving an unknown state instead of manufacturing a stale finding.

Path dates always remain historical scope. `/rates/2022/` cannot make a page fail freshness merely because another field says `Current mortgage rates`.

The producer delegates the final bounded state to the existing `assess_contextual_freshness` contract:

- no current intent -> `not_applicable`;
- current intent but no trustworthy current-scope date -> `not_verified`;
- current intent plus current-scoped date within threshold -> `pass`;
- current intent plus contradictory old current-scoped date -> `fail`.

## Real retained-page seam

`scanner-api/app/content_evidence_findings.py` now calls `enrich_pages_with_contextual_freshness_evidence(pages)` after the B11 retained-link enrichment. `run_scan` already invokes this seam after the final assessed-page cap.

This is evidence-only. `content_evidence_findings` does not emit a B15 customer repair/card or score adjustment. If freshness is later promoted to customer output, it must first be authenticated through Review -> signed authority -> persistence -> customer/card/handoff/export.

## Behavioral regressions

`scanner-api/tests/test_stage2_freshness_producer.py` covers:

- historical old year alone -> not applicable;
- explicit current intent plus old visible current-scoped date -> fail;
- dated path plus current title -> not verified, not fail;
- current visible date -> pass;
- conservative year-only date handling;
- `apply now` not becoming current-content intent;
- explicit archive/history context preventing a false current-scope date;
- unusable/challenged evidence producing no temporal/current claim;
- real `content_evidence_findings` retained-page seam enriching B15 evidence without emitting a repair.

## Verification

Exact executable head: `e286c3c4f0db6b90c60300f804232c5894936c40`.

FixList CI `35484767939` passed both jobs on that exact SHA:

- immutable checkout verified the exact head;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,961 passed / 18 intentional skips**;
- B15 focused suite: **9 passed** as part of the scanner suite;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc21e8f12c5d00cfaa9cdbef78514576141422bc9ee08605e8f2f6affabd74d`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow installed Node `20.20.2`; this is not Node `20.19.5` runtime evidence.

## Status and next boundary

The B15 producer/source evidence seam is implemented and exact-head green. It remains evidence-only, so there is no new displayed field/repair requiring customer downstream proof in this slice.

Stage 2 remains open. Next serialized work is the remaining B13/B14 scan-level summary attachment plus B17 directly measured transfer bytes/optional CrUX states and B18 optional GSC states, followed by final independent review and exact-head CI. Any future customer-visible B15 finding must use the authenticated downstream chain before closure.
