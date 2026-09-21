# Agent D — Evidence Connectors

Issue: #325
Integration base: nextgen/integration-20260921

Implement only the Evidence Connectors lane defined in docs/nextgen/2026-09-21-parallel-engineering-lanes.md.

Branch ownership:
- provider-neutral evidence schema
- GSC Search Analytics normalization
- URL Inspection normalization
- Bing AI Performance import normalization
- GA4 AI-assistant evidence normalization
- explicit unavailable/not-connected states

Forbidden:
- OAuth/account changes
- Base44 schema
- authority/persistence/projection
- run_scan
- release/deploy/admission

Do not invent undocumented Google Generative AI API endpoints.
