# FixList Python Scanner API

Parallel Python scanner service for FixList.

This service is added beside the current Base44 scanner. It does not switch production traffic by itself.

## Purpose

The Python scanner gives us a testable crawler engine for large scoped sections such as Pretto, Meilleurtaux, Funbooker, and Center Street Lending.

## Local development

Install the dependencies from `requirements.txt`, then run the FastAPI app from this folder with Uvicorn.

The service exposes:

- `GET /health` — includes `beta_revision_fingerprint`
- `GET /revision` — live beta-revision fingerprint + component versions
- `POST /scan`
- `POST /review`

## Observability

Every `/scan` and `/review` request emits structured JSON lifecycle events on
stdout (`app/observability.py`): started/completed with duration, coverage,
rate-limit counters, and version + beta-revision tracking, plus customer-safe
error envelopes with a correlated `error_id`. Cloud Run ingests these as
structured logs; the log-based metrics and alert policies are defined in
`docs/production-monitoring.md`.

## Beta acceptance and freeze

Phase 1 of the roadmap closes with three steps: deploy, run acceptance scans,
and record the frozen beta revision. Two tools support the last two:

### Post-deploy acceptance scans

`scripts/run_beta_acceptance_scans.py` runs the Shopify / Signal / Basecamp
acceptance scans (from `data/beta-acceptance-manifest.jsonl`) and checks each
result against the crawler contract. Point it at the deployed scanner:

```bash
python scripts/run_beta_acceptance_scans.py \
  --scanner-url https://scanner.example.run.app \
  --api-key "$SCANNER_API_KEY" \
  --report-output ../docs/beta-acceptance.md
```

Use `--in-process` for a local dry run without a deployed URL (this does not
prove a deployed revision is healthy). Exit code is `0` only when every site
completes and passes the contract; the JSON summary reports
`freeze_recommendation`.

### Record / verify the frozen revision

`data/beta-crawler-revision.json` records the frozen beta: the git commit plus
the exact scanner/review version constants. After acceptance passes:

```bash
python scripts/freeze_beta_revision.py \
  --git-commit "$(git rev-parse HEAD)" \
  --acceptance-report docs/beta-acceptance.md \
  --note "frozen after acceptance"
```

Verify the running code still matches the recorded freeze (CI runs this):

```bash
python scripts/freeze_beta_revision.py --check
```

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
