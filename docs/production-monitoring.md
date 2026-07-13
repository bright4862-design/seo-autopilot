# Production monitoring (Phase 4)

The scanner API emits one structured JSON log line per lifecycle event on
stdout (`app/observability.py`). Cloud Run ingests these automatically: the
`severity` field becomes the log level and everything else lands in
`jsonPayload`, so all monitoring below is built from log-based metrics — no
agent or metrics library needed.

## Events

| Event | Severity | Key fields |
| --- | --- | --- |
| `scan_started` | INFO | `website_host`, `scan_mode`, `scanner_version`, `beta_revision_fingerprint` |
| `scan_completed` | INFO | `duration_ms`, `success`, `pages_crawled`, `pages_found`, `rate_limited_pages`, `server_error_pages`, `failed_pages` |
| `review_started` | INFO | `website_host`, `review_version`, `beta_revision_fingerprint` |
| `review_completed` | INFO | `duration_ms`, `scan_status`, `health_score`, `score_is_provisional`, `finding_count` |
| `request_failed` | ERROR | `error_id`, `error_code`, `error_type`, `error_detail`, `duration_ms` |

Version tracking: every started/completed event carries `scanner_version` or
`review_version` plus `beta_revision_fingerprint`, so any metric can be split
by revision to catch regressions after a deploy.

## Customer-safe errors and admin visibility

When an endpoint crashes, the customer receives only:

```json
{ "success": false, "error_code": "internal_error", "error": "<safe message>", "error_id": "a1b2c3d4e5f6" }
```

The full exception detail is logged in the `request_failed` event under the
same `error_id`. To investigate a customer report:

```bash
gcloud logging read 'jsonPayload.error_id="a1b2c3d4e5f6"' --limit 5
```

Failed customer scans are also durable: `ScanRun` rows with `status="failed"`
record `error_code`/`error_message` per scan (see docs/durable-scan-model.md),
which gives the admin view of who was affected.

## Log-based metrics

Create once per project (adjust `SERVICE` to the Cloud Run service name):

```bash
SERVICE=fixlist-scanner
BASE='resource.type="cloud_run_revision" resource.labels.service_name="'$SERVICE'"'

# Scan failure rate: request crashes...
gcloud logging metrics create scan_request_failed \
  --description="Scanner API requests that returned a customer-safe error" \
  --log-filter="$BASE jsonPayload.event=\"request_failed\""

# ...and unsuccessful scans that returned cleanly.
gcloud logging metrics create scan_unsuccessful \
  --description="Scans that completed with success=false" \
  --log-filter="$BASE jsonPayload.event=\"scan_completed\" jsonPayload.success=false"

# Scan duration distribution (p50/p95/p99 in dashboards).
gcloud logging metrics create scan_duration_ms \
  --description="Scan duration distribution" \
  --log-filter="$BASE jsonPayload.event=\"scan_completed\"" \
  --bucket-name="" \
  --value-extractor='EXTRACT(jsonPayload.duration_ms)' \
  --bucket-options=exponential-buckets,num-finite-buckets=20,growth-factor=1.5,scale=1000

# Rate-limit pressure: scans that hit HTTP 429s while crawling.
gcloud logging metrics create scan_rate_limited \
  --description="Scans with at least one rate-limited page" \
  --log-filter="$BASE jsonPayload.event=\"scan_completed\" jsonPayload.rate_limited_pages>0"
```

## Alerts

Recommended alert policies (Cloud Monitoring → Alerting, or `gcloud alpha
monitoring policies create`):

| Alert | Condition | Suggested threshold |
| --- | --- | --- |
| Scan failure rate | `scan_request_failed` + `scan_unsuccessful` vs `scan_started` count | > 20% over 30 min |
| Scan latency | `scan_duration_ms` p95 | > 120 s over 30 min |
| Rate-limit spike | `scan_rate_limited` count | > 5 in 1 h |
| Service down | Cloud Run built-in `request_count` 5xx ratio | > 5% over 10 min |
| No traffic | `scan_started` count | == 0 for 24 h (beta only, informational) |

## Cost monitoring

Cloud Run cost follows request time. Two habits cover the beta:

1. A budget alert on the project (Billing → Budgets) at the expected monthly
   spend; scans are the dominant cost, and `scan_duration_ms` × scan count
   approximates billable container time.
2. Watch `scan_duration_ms` p95 — a duration regression is a cost regression.

## Verifying after a deploy

```bash
# Confirm the deployed revision matches the frozen beta record.
curl -s https://$SCANNER_HOST/revision | python -m json.tool
python scanner-api/scripts/freeze_beta_revision.py --check

# Confirm structured logs are flowing.
gcloud logging read "$BASE jsonPayload.event=\"scan_completed\"" --limit 3
```
