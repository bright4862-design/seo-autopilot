# Agent E — Fix Verification

Issue: #326
Integration base: nextgen/integration-20260921

Implement only the Fix Verification lane defined in docs/nextgen/2026-09-21-parallel-engineering-lanes.md.

Branch ownership:
- acceptance criteria contracts
- targeted recheck plans
- PASS/PARTIAL/FAIL/COULD_NOT_VERIFY evaluation
- regression reopen semantics

Forbidden:
- durable authority/persistence/customer projection
- run_scan/global budgets
- public workflow state changes
- release/deploy/admission

Current verified_fixed comparability remains authoritative and may not be weakened.

This file exists to give the lane an auditable branch-local ownership boundary.
