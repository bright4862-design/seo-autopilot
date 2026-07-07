# FixList Python Scanner API

Parallel Python scanner service for FixList.

This service is added beside the current Base44 scanner. It does not switch production traffic by itself.

## Purpose

The Python scanner gives us a testable crawler engine for large scoped sections such as Pretto, Meilleurtaux, Funbooker, and Center Street Lending.

## Local development

Install the dependencies from `requirements.txt`, then run the FastAPI app from this folder with Uvicorn.

The service exposes:

- `GET /health`
- `POST /scan`

## Contract

The `/scan` endpoint returns the same broad shape expected by the existing app:

- `success`
- `scanner_version`
- `pages_crawled`
- `pages_found`
- `pages`
- `crawled_pages`
- `raw_findings`
- `grouped_findings`
- `findings`
- `recommendations`
- `verified_failed_pages`
- `suspicious_url_artifacts`
- `verified_failed_page_count`
- `suspicious_url_artifact_count`
- `technical_audit_summary`

Artifact evidence is capped at 50 so suspicious URLs cannot dominate the report.

## Production plan

Deploy this as a container service, then replace the current Base44 scanner with a thin wrapper after fixture scans beat the current Deno scanner.
