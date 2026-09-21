# Agent A — Adaptive Crawl

Issue: #322
Integration base: nextgen/integration-20260921

Implement only the Adaptive Crawl lane defined in docs/nextgen/2026-09-21-parallel-engineering-lanes.md.

Branch ownership:
- pure adaptive selection/scoring
- tranche/yield telemetry
- deterministic benchmarks/tests

Forbidden:
- run_scan/global production budgets
- authority/persistence/customer projection
- repair priority/final ranking
- release/deploy/admission

This file exists to give the lane an auditable branch-local ownership boundary.
