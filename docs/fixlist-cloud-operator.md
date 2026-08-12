# FixList Cloud Operator

This workflow replaces repeated manual Google Cloud Console / Cloud Shell work with a narrow GitHub Actions operator for the Standard 150 beta.

## Scope

The operator is hard-coded to:

- project: `seo-autopilot-501517`
- region: `europe-west1`
- Cloud Run service: `fixlist-standard150-worker`
- Cloud Tasks queue: `fixlist-standard150`

It does not accept arbitrary project, service, queue, URL, shell command, or IAM principal inputs.

## Operations

Read-only:

- `status`
- `verify-iam`

Mutating operations require an exact confirmation word:

- `promote-worker` → `PROMOTE`
- `pause-queue` → `PAUSE`
- `resume-queue` → `RESUME`
- `activate-beta` → `ACTIVATE`

`activate-beta` always promotes the latest Ready Cloud Run revision before resuming the queue. If traffic promotion fails, queue resume is never attempted.

## Authentication

Use Google Workload Identity Federation from GitHub Actions rather than a long-lived Google service-account key.

The workflow expects these GitHub repository secrets:

- `GCP_WIF_PROVIDER`
- `GCP_OPERATOR_SERVICE_ACCOUNT`

Recommended operator service account:

`fixlist-github-cloud-operator@seo-autopilot-501517.iam.gserviceaccount.com`

Grant the operator only the permissions required for this workflow:

- `roles/run.admin` on `fixlist-standard150-worker`
- `roles/cloudtasks.queueAdmin` on `fixlist-standard150`

The Workload Identity provider should restrict admission to the exact GitHub repository `bright4862-design/seo-autopilot`, and the operator service account should grant `roles/iam.workloadIdentityUser` only to that repository principal.

## Running it

In GitHub:

1. Open **Actions**.
2. Select **FixList Cloud Operator**.
3. Choose **Run workflow**.
4. Select the operation.
5. For a mutation, enter the required confirmation word exactly.

For the current beta activation, do not use `activate-beta` until the durable Base44 backend has been published and its Cloud Tasks dispatcher secrets are configured.
