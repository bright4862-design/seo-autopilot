# Stage 2 output privacy hardening checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303.

## Fresh independent whole-stage finding

The fresh combined B06–B18 CodeRabbit review identified one material P1 boundary defect in executable checkpoint `e906ef69c7b7deab3a1014c702b4f3af1453c54c`: B10 deterministic main-content fingerprint intermediates and B13 normalized local-entity observations remained on the page dictionaries forwarded by the synchronous HTTP result and durable authority path.

The affected producer fields included B10 `main_text`, `main_text_signature` and related representation/count/source/verification metadata, plus B13/B14 `local_entity_observations` carrying explicit entity identity/contact evidence. B15 contextual-freshness producer evidence was included in the same fail-closed projection because it also has no approved customer/persistence contract. The review correctly treated deterministic shingles as candidate-membership-testable evidence rather than secret content.

## Correction

The correction is deliberately after all current Stage-2 scan-level aggregation but before the common synchronous/durable external boundary:

- `scanner-api/app/page_output_privacy.py` defines the producer-only page deny-list and projects every recognized page-array alias without mutating the producer input.
- `scanner-api/app/render_evidence_quality.py` now invokes that projection on every result path after B13/B14 aggregation has consumed the accepted retained-page observations.
- B10 intermediate shingle/signature fields, B13/B14 raw observations/location context, B15 per-page contextual-freshness evidence and the defensive B11 `_reachability_links` cache are removed before synchronous output and before durable authority handling.
- The B13/B14 scan-level aggregate is retained only as a reduced non-content state/count summary. Exact page URLs, entity IDs and accepted-heading status provenance are removed from the aggregate before the external boundary; NAP inconsistency rows retain affected field names/count/provenance but not the entity key.
- Ordinary page fields needed by existing Review/customer contracts, including exact page URL/title/status and measured transfer-byte evidence, remain intact.
- No new request, provider connection, customer repair/card/export surface, schema change or score change is introduced.

Implementation commits in this correction series:

- `d18400d98824063168e0d1a99990123af7d93de3` — initial fail-closed page-output projection;
- `1c2312ea737010b73bd8650ff07c1321745617dd` — common post-crawl boundary integration;
- `7953edf8eb2f9e0cb9237d77755656c45a81df28` — reduce B13/B14 aggregate to non-content output;
- `e42151d4f10007f4f1660de4a2bbda927a4696eb` — four behavioral privacy/authority regressions.

## Behavioral regressions

`scanner-api/tests/test_stage2_output_privacy.py` injects distinctive sentinels for:

- B10 shingle/signature evidence and source text;
- an absolute local-entity ID;
- a unique branch/location name, address, phone and hours;
- B15 current-intent evidence;
- the private B11 reachability cache.

The tests prove:

1. the common post-crawl projection removes producer-only fields while leaving the original producer object intact;
2. `enforce_scan_response_page_budget` cannot republish those fields/values;
3. `build_authority_review_payload` cannot republish them in sampled authority pages;
4. both signed completion and limited-result envelopes contain only projected page evidence, with all distinctive private sentinels absent.

## Exact-head verification

Exact executable head: `e42151d4f10007f4f1660de4a2bbda927a4696eb`.

FixList CI `35493637000` — **SUCCESS** on both jobs.

Observed CI environment/evidence:

- Ubuntu 24.04.5;
- Python 3.12.14;
- the persisted-customer Node setup resolved Node **20.20.2** (do not describe this run as Node 20.19.5 evidence);
- immutable checkout verified exact SHA `e42151d4f10007f4f1660de4a2bbda927a4696eb`;
- root scanner regressions: **115 passed**;
- full `scanner-api`: **1,988 passed / 18 intentional skips** (2,006 collected);
- focused output-privacy regressions: **4 passed**;
- labelled Stage-1 corpus: `provenance=synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:ace9b08b88ea3c29faecc00cc0c9567deb9687cc90f1c503723bcd73f80a86dc`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

## Remaining gate

The material P1 is reproduced, corrected and exact-head CI green. Stage 2 is **not yet recorded complete** until a fresh independent follow-up review verifies the corrected current source and no new material B06–B18 finding remains. If that review reports another material issue, reproduce it with a behavioral regression and correct it before Stage-3 shared integration.

Stage 3 remains held. Stage 4 remains isolated; the genuine provenance-labelled 30-site baseline/candidate gate is still `not_assessed`. No production, `main`, admission, worker, provider, schema/secret or customer-data state was changed by this correction.
