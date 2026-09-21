# Agent C — Browser / Performance

Issue: #324
Integration base: nextgen/integration-20260921

Implement only the Browser / Performance lane defined in docs/nextgen/2026-09-21-parallel-engineering-lanes.md.

Branch ownership:
- CrUX/PSI evidence adapters
- representative sampling
- Lighthouse normalization
- raw/rendered critical-content parity evidence

Forbidden:
- run_scan/global budgets
- worker deployment config
- repair priority/customer scoring
- authority/persistence/projection
- release/deploy/admission

No live provider calls or credentials in deterministic tests.
