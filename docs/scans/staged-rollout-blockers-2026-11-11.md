# Live staged rollout: 11 November 2026

Implementation and inactive deployment controls are merged through [PR #409](https://github.com/bright4862-design/seo-autopilot/pull/409), source `bb715e72304eb76bd8d93cda476b535dbb18de67`. CI passed frontend/build checks, scanner regression fixtures and workflow validation.

## Verified live boundary

- The existing worker candidate `fixlist-standard150-worker-00104-l79`, from scanner source `4274ac453e93fe2e161e01c88d31823bd5134795`, passed authenticated runtime identity checks at 0% traffic. It does not have the new staged infrastructure configuration.
- [Admission status run 43094436571](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094436571) observed `closed`, generation `77`, `drain_ready=true`, with zero active claims, bound claims and live reconciliation obligations at 20:13:59 UTC. This is historical evidence; obtain a fresh signed snapshot before later cutover operations.
- [Bootstrap run 43094691713](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094691713) created `gs://fixlist-scan-workspaces-seo-autopilot-501517` with uniform access and public access prevention requested. Its next command failed: `fixlist-github-operator@seo-autopilot-501517.iam.gserviceaccount.com` lacks `storage.buckets.update` on that bucket. The lifecycle update and all later bootstrap steps did not complete. Bucket configuration still needs independent read-back verification.
- [Isolated V9 publisher run 43094215294](https://github.com/bright4862-design/seo-autopilot/actions/runs/43094215294) reached the existing owner device-login step. Publication and the readiness artifact are not established by reaching that step; check its final outcome.
- This rollout did not enable an owner cohort, resume the existing queues, open public claims, publish the site or mark the candidate accepted.

## Complete the partial bootstrap as a GCP administrator

Do not rerun the whole one-time creation script: the bucket now exists. Use an existing authorized administrator identity to complete the remaining resource configuration below. These commands grant runtime access on the selected resources; they do not broaden the GitHub operator's permissions.

```bash
set -euo pipefail

cat > /tmp/fixlist-staged-workspace-lifecycle.json <<'JSON'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}
JSON

gcloud storage buckets update gs://fixlist-scan-workspaces-seo-autopilot-501517 \
  --project=seo-autopilot-501517 \
  --lifecycle-file=/tmp/fixlist-staged-workspace-lifecycle.json

gcloud storage buckets add-iam-policy-binding gs://fixlist-scan-workspaces-seo-autopilot-501517 \
  --project=seo-autopilot-501517 \
  --member=serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com \
  --role=roles/storage.objectUser

gcloud tasks queues create fixlist-scan-stages \
  --project=seo-autopilot-501517 --location=europe-west1 \
  --max-concurrent-dispatches=40 --max-attempts=10 \
  --min-backoff=10s --max-backoff=120s --max-doublings=4 --max-retry-duration=1800s

gcloud tasks queues pause fixlist-scan-stages \
  --project=seo-autopilot-501517 --location=europe-west1

gcloud tasks queues add-iam-policy-binding fixlist-scan-stages \
  --project=seo-autopilot-501517 --location=europe-west1 \
  --member=serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com \
  --role=roles/cloudtasks.enqueuer

gcloud iam service-accounts add-iam-policy-binding \
  fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com \
  --project=seo-autopilot-501517 \
  --member=serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser
```

Stop on any error. If an administrator has already completed a step, inspect that resource rather than recreating it. Keep the stage queue paused until V9 packages, the exact candidate configuration and owner-only admission path have been verified. The existing entry and drain queues remain under the separate controlled-cutover procedure.

Run the read-only `verify-staged-scan-infra` Cloud Operator operation afterward. It may itself need explicit read permissions on the new resources; an administrator can also run `scripts/verify_staged_scan_infra.py` with the resource arguments in the [runbook](staged-scan-runbook.md) and `--expected-queue-state PAUSED`. A successful infrastructure check does not establish deployed V9 bytes, per-task authentication, owner scan acceptance or production readiness.
