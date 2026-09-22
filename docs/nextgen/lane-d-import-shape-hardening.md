# Lane D — import-shape ambiguity hardening

Issue: #325  
Draft PR: #332  
Lane: `agent/nextgen-evidence-connectors-20260921`

## Purpose

Bing AI Performance and GA4 evidence may arrive as CSV rows or Excel-derived dictionaries. The low-level normalizers intentionally accept multiple provider/export header aliases, but a dictionary can contain more than one alias for the same semantic field. Without a preflight boundary, mapping/header order can silently decide which value wins.

This slice adds `connected_evidence_import_shape_v1`, a pure pre-normalization contract for the manual/aggregate import paths. It performs no network I/O, OAuth/account mutation, credential creation, Base44 change, persistence, scoring, projection, `run_scan` change, release, deployment, admission, or production mutation.

## Contract

`validate_connected_evidence_import_rows(...)`:

- supports the registered Bing AI Performance and GA4 AI-assistant-referral import profiles only;
- preserves accepted row mappings unchanged;
- preserves unrelated extra export columns instead of pretending they are evidence fields;
- rejects empty normalized headers;
- rejects collisions where two registered headers normalize to the same token;
- rejects underscore-insensitive collisions because the existing tolerant lookup also treats those spellings as aliases;
- rejects conflicting non-empty values carried by two aliases for the same semantic field;
- allows equivalent duplicate alias values rather than treating harmless duplicate export columns as different evidence;
- keeps the existing global `MAX_IMPORT_ROWS` ceiling authoritative and does not allow a caller to raise it.

Strict entrypoints now wrap the existing provider normalizers:

- `normalize_bing_ai_performance_import_rows(...)`
- `normalize_bing_ai_performance_import_csv(...)`
- `normalize_ga4_ai_referral_import_rows(...)`
- `normalize_ga4_ai_referral_import_csv(...)`

The existing provider normalizers remain pure low-level translators. Future serialized integration should prefer the strict import entrypoints for manually supplied/Excel-derived Bing and GA4 rows, then continue through the existing full connected-evidence validation stack.

## Examples

Rejected as ambiguous:

- Bing: `Citation Count=1` plus `total_citations=2`;
- Bing: `citation_count=1` plus `citationcount=2`;
- GA4: `session_source=chatgpt.com` plus `source=perplexity.ai`;
- GA4: `ai_assistant=chatgpt` plus `assistant=perplexity`.

Accepted:

- equivalent aliases carrying the same logical value;
- unrelated provider/export columns that are not consumed by the registered normalizer.

## Verification

Focused candidate verification in the available hermetic Python package:

- `PYTHONPATH=. pytest -q tests/test_connected_evidence_import_contract.py` → **13 passed**;
- `python -m py_compile app/connected_evidence_import_contract.py tests/test_connected_evidence_import_contract.py` → passed.

The hermetic package used a stub only for the already-existing low-level `connected_evidence` adapter dependency; the new import-shape logic itself was executed directly. Two wrapper tests also exercised preflight-before-delegation behavior. Exact repository-native certification remains required before integration readiness.

The new focused suite increases the expected Lane-D inventory from 223 to **236 tests**.

## Ownership / rollback

Files introduced by this slice:

- `scanner-api/app/connected_evidence_import_contract.py`
- `scanner-api/tests/test_connected_evidence_import_contract.py`
- `docs/nextgen/lane-d-import-shape-hardening.md`

Rollback is lane-local: omit these files from serialized integration. No production state, credentials, schema, durable authority, customer data, release surface, or deployment requires reversal.
