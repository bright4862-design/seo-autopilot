# GEO Integration Implementation Plan

> Execute with superpowers:subagent-driven-development, one implementation owner at a time; retain task review gates.

**Goal:** Deliver evidence-backed GEO readiness through the existing Standard 150 authority and customer result path, with blueprint regressions required before release.
**Architecture:** Accepted HTML -> bounded observations -> pure aggregation -> authenticated snapshot -> entitlement-aware customer presentation. Older snapshots remain byte-compatible.
**Tech Stack:** Python/pytest, Base44 JavaScript/Node tests, React/Vite.
**Spec:** ../specs/2026-09-18-geo-readiness-design.md

## Global constraints

No additional requests, no UA impersonation, no changes to Standard 150 cap, V6 routes, SSRF, ownership rules, admission or authority eligibility. Null is not zero. Blueprint live counts are hypotheses. No production release until prerequisite scanner corrections and exact-SHA gates pass. Reattached PDF SHA256: c76efed66f373e2455c326b2804a8148489509f8625f84377b9f21bef4f1f6f9 (identical to earlier upload).

### Task 1: Evidence adapter and deterministic findings

Files: create scanner-api/app/geo_evidence.py and scanner-api/tests/test_geo_evidence.py; modify extract.py and robots_policy.py only for additive bounded GEO evidence. Do not change established SEO extraction yet.

Interface: `extract_geo_evidence(html, page) -> dict` returns versioned bounded raw-HTML observations, without fetching or mutating page. `assess_geo_pages(pages, *, parent_authoritative=False, entry_verified=False, access_limited=False) -> dict` returns the existing evaluate_geo output plus evidence_adapter_version, observations and findings. It must cap pages at 150, use deterministic bounded evidence IDs, and reject duplicates and malformed inputs. Per observation: page_id, check_id, state, evidence_ref, reason. Findings group failed checks, keep unique page IDs, bounded samples and explicit actions; do not create extra SEO fixes.

- [x] Test challenge/202/truncation/render uncertainty -> no content passes or failures; all unknown -> null; duplicate/over-cap rejection; no input mutation; deterministic ordering; training opt-out ignored; absent schema not failed; historical dates not penalized; code/script template examples ignored; utility noindex excluded only on explicit evidence; missing applicability unknown.
- [x] Build only checks that retained evidence proves. Unknown is mandatory when semantics or applicability cannot be determined. Check labels must describe structural evidence, never claim factual accuracy or predicted citation. Add extraction only after shared page gate acceptance and retain raw/rendered origin.
- [x] Add OAI-SearchBot directive observation to existing robots policy annotation, with no additional fetch and no ownership override.
- [x] Run focused tests and scanner regression suite; commit and report exact result schema to coordinator before downstream work.

Example acceptance:
```python
result = assess_geo_pages([], parent_authoritative=True, entry_verified=False, access_limited=True)
assert result['score'] is None
assert result['assessment_status'] == 'access_limited'
assert result['findings'] == []
```

### Task 2: Runtime and sealed result compatibility

Files: review.py, authoritySnapshot.js active copies, relevant entity schemas, projection.js and contract tests. Read repository propagation scripts first.

- [x] Attach `geo_readiness` after the current review authority inputs are computed, deriving entry verification from accepted entry evidence. Preserve SEO when GEO computation fails only with a validated explicit null/error envelope.
- [x] Version the internal snapshot payload independently from V6 function route names. Add strict bounded GEO validation and include it in row reconstruction and HMAC. Preserve all earlier snapshot reconstruction exactly; absent historical GEO displays not_assessed.
- [x] Test old seal verification, new score/coverage/evidence tampering rejection, malformed producer rejection, persistence readback, previews and reloads. Projection returns only allowed summary fields to preview users; never exposes findings via an unrestricted nested object.

### Task 3: Customer presentation

Files: actual Standard 150 FixList presentation, scan handoff, one reusable GEO component and helper; frontend tests. Reports.jsx is an unrelated connector screen and stays unchanged.

- [x] Show separate GEO readiness score with assessed pages, coverage, bounds, experimental methodology and clear non-citation wording. All null/error/blocked/historical states neutral. Do not duplicate repairs or leak evidence to preview users.
- [x] Test zero vs null, historical absence, invalid shapes and sample/coverage labeling; run frontend suite and production build.

### Task 4: Blueprint P0 corrections and rollout

Files: scanner-api/app/scanner.py, sitemap.py, extract.py, review_calibration.py, focused Python tests, docs/geo-blueprint-release-checklist.md. Existing release workflows/scripts remain unchanged unless a defect is proven.

- [x] Preserve published non-seed paths/slashes; preserve sitemap host/scheme and exclude out-of-effective-origin entries with existing scope counts; distinguish missing alt attributes from empty/whitespace alt. Keep scope, robots, SSRF, cap, final-response dedupe and real redirect findings. Test actual outbound paths and both false-positive and real-redirect cases before release. No general priority rewrite or new requests.

```python
missing_alt = sum(1 for img in images if not img.has_attr("alt"))
# enqueue uses normalize_published_request_url(url) for every source.
# Sitemap eligibility uses exact effective origin, without host/scheme rewriting.
```

- [x] Map each blueprint requirement to implemented evidence or explicit deferred scope. Preserve published requests; distinguish absent/empty alt; verified target failures, template placeholders, sitemap/noindex conflicts, exact counts and meaningful priority require tests, not supplied live counts. Coordinate with existing scanner work through repository state; do not overwrite external changes.
- [ ] Review full branch, run affected suites and release contract generation/checks. Publish exact reviewed tree via existing GitHub path, wait CI, merge only ready work, then use existing stage/publish/promote flow and verify source SHA/fingerprint/rollback. If an actual access or prerequisite gate blocks rollout, report it specifically and preserve the validated implementation.
