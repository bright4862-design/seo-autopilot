# FixList Cloud Operator

Keyless Google Cloud operations for the durable Standard 150 release, run
from GitHub Actions instead of Cloud Shell.

The org policy `constraints/iam.disableServiceAccountKeyCreation` blocks
service-account key creation, so there is no key to store and none is
wanted: authentication is Workload Identity Federation, which mints a
short-lived token per run. Nothing in this path creates, stores, or prints
a credential.

## Operations

| Operation | Mutating | Confirmation |
|---|---|---|
| `status` | no | — |
| `verify-iam` | no | — |
| `verify-worker-routes` | no | — |
| `promote-worker` | yes | exact revision name |
| `rollback-worker` | yes | exact revision name |
| `pause-queue` | yes | `PAUSE` |
| `resume-queue` | yes | `RESUME` |
| `activate-beta` | yes | exact revision name |

### Why traffic operations name a revision

`--to-latest` resolves at execution time. If anything deployed between
validation and promotion, it would promote the newer revision instead of the
validated candidate. Every traffic operation therefore requires an explicit
`revision` input, verifies the revision exists, and uses
`--to-revisions=<revision>=100`.

The confirmation string for those operations **is** the revision name, so a
confirmation that is correct for one revision is wrong for every other one.
A stale approval cannot promote whatever happens to be newest.

### `verify-worker-routes`

The durable pipeline sends every Cloud Task to `POST /scan-job` and the
watchdog to `POST /scan-job-drain`. Those routes exist only in builds
containing `scanner-api/app/scan_job.py` — they are **absent from `main`**
and present only on the durable release branches.

A worker built from the wrong source deploys cleanly, serves `/health`, and
404s every task; the watchdog 404s too, so runs never reach a terminal
state. An unauthenticated probe cannot detect this, because Cloud Run IAM
rejects the request before it reaches routing. This operation therefore
reports the running revision's image, whether it is pinned to an immutable
digest, the Cloud Build provenance including `_RELEASE_SHA`, and the
revision's request timeout, then requires a human to confirm the SHA is one
that declares both routes.

Run this **before** `activate-beta`.

### `activate-beta` ordering

1. Promote the named revision.
2. Probe the worker and require 401/403 — the worker is private, so an IAM
   rejection is the healthy answer and proves the service is both reachable
   and not public. Any other result aborts before the queue is touched.
3. Resume the queue.

A failure at step 2 or 3 leaves the safe promoted-and-paused state. Nothing
here publishes Base44; per the release rules, Base44 must already be
published before the queue is resumed, and the operator cannot verify that —
confirm it yourself first.

## One-time setup

Run once, in an authorized Cloud Shell. Creates no keys.

```bash
PROJECT=seo-autopilot-501517
REPO=bright4862-design/seo-autopilot
SA=fixlist-github-operator@$PROJECT.iam.gserviceaccount.com

# 1. Operator service account
gcloud iam service-accounts create fixlist-github-operator --project=$PROJECT

# 2. Resource-scoped grants only — nothing project-wide
gcloud run services add-iam-policy-binding fixlist-standard150-worker \
  --region=europe-west1 --member=serviceAccount:$SA --role=roles/run.developer
gcloud tasks queues add-iam-policy-binding fixlist-standard150 \
  --location=europe-west1 --member=serviceAccount:$SA --role=roles/cloudtasks.queueAdmin
gcloud iam service-accounts add-iam-policy-binding \
  fixlist-standard150-invoker@$PROJECT.iam.gserviceaccount.com \
  --member=serviceAccount:$SA --role=roles/iam.serviceAccountViewer

# 3. WIF pool + provider, pinned to this repository AND main
gcloud iam workload-identity-pools create github --location=global --project=$PROJECT
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --project=$PROJECT --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '$REPO' && assertion.ref == 'refs/heads/main'"

# 4. Allow that identity to impersonate the operator SA
POOL_ID=$(gcloud iam workload-identity-pools describe github \
  --location=global --project=$PROJECT --format='value(name)')
gcloud iam service-accounts add-iam-policy-binding $SA --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$POOL_ID/attribute.repository/$REPO"

# 5. GitHub repository secrets
#    GCP_WIF_PROVIDER            = $POOL_ID/providers/github-actions
#    GCP_OPERATOR_SERVICE_ACCOUNT = $SA
```

### Why the `refs/heads/main` condition matters

`workflow_dispatch` accepts any ref, and `actions/checkout` would take the
operator script from that same ref. Without the condition, anyone able to
push a branch could rewrite the script and run it as the operator service
account. The condition makes authentication itself fail off `main`; the
workflow's own `Refuse to run outside main` guard and its pinned
`ref: refs/heads/main` checkout are defence in depth.

Because authentication is pinned to `main`, this workflow must be **merged
to `main`** before it can run at all.

### Scope of the grants

Traffic-only `update-traffic` does not need `actAs` on the runtime service
account, so the operator holds **no** `serviceAccountUser` anywhere. The two
role grants are on the single service and the single queue, not the project.
A custom role limited to `run.services.get/update` and
`cloudtasks.queues.get/pause/resume` is the further tightening if wanted.
