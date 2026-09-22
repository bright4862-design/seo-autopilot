# Agent A — Adaptive Crawl

Issue: #322
Integration base: nextgen/integration-20260921

Implement only the Adaptive Crawl lane defined in docs/nextgen/2026-09-21-parallel-engineering-lanes.md.

Branch ownership:
- pure adaptive selection/scoring
- tranche/yield telemetry
- deterministic benchmarks/tests
- engineering-only Smart-500-vs-blind-1000 acceptance tooling

Forbidden:
- run_scan/global production budgets
- authority/persistence/customer projection
- repair priority/final ranking
- release/deploy/admission

Current checkpoint notes:
- `lane-a-adaptive-crawl-handoff.md` contains the integration hook and rollback contract;
- `lane-a-smart-500-shadow-acceptance.md` supplements it with the latest shadow-corpus acceptance helper and current focused-test inventory.

This file exists to give the lane an auditable branch-local ownership boundary.
