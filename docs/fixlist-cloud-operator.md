# FixList Cloud Operator

Keyless Google Cloud operations for the durable Standard 150 release, run
from GitHub Actions instead of Cloud Shell.

The organization blocks service-account key creation, so this operator uses
Workload Identity Federation (WIF). Each GitHub Actions run receives a
short-lived Google credential; no long-lived Google key is created, stored,
or printed.

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

### Bounded public Standard 150 rollout

Use `open-claim-barrier` from a verified closed and drained generation after
the accepted source and exact V9 launcher are published. Supply the cohort ID,
release ID, ordinary customer owner IDs, expiry in epoch seconds, total and
per-owner claim limits, and the launcher build ID from
`data/generated-staged-v9-routes.json`. The limits are five owners, ten total
claims and 24 hours. The confirmation is
`OPEN-PUBLIC-150-COHORT:<source-sha>:<closed-generation>:<cohort-id>:<launcher-build-id>`.
The scope and the open transition commit together. The signed response binds
the deployed source, launcher, cohort, account-set digest, expiry and budgets.
The named 500 pilot's start and hold snapshots carry the public 150 state
and claim usage when a bounded cohort is configured. A public 150 hold
snapshot also records the named 500 state when present.

Use `hold-public-150` with the current open generation and exact cohort ID.
The confirmation is `HOLD-PUBLIC-150-COHORT:<source-sha>:<open-generation>:<cohort-id>`.
The hold stops new Standard 150 claims, keeps already admitted attempts
recoverable, and leaves the named 500 pilot and saved reports available.
An expired or spent cohort also stops new claims in its tier. The ordinary
`OPEN-STANDARD150-CLAIMS` confirmation continues to work with empty cohort
inputs.

The scoped open admits ordinary paid customers through the published staged
Standard 150 launcher and treats named Standard 500 launches separately.
Broad entitled 500 launches stay paused while this cohort is configured.
Before replacing the pinned launcher or downgrading the coordinator, close the
global barrier on a version that can read the scoped state and verify the drain.
This keeps admitted retries on their original launcher until they settle.

### Why traffic operations name a revision

`--to-latest` resolves at execution time. If anything deployed between
validation and promotion, it could promote a newer revision instead of the
validated candidate. Every traffic operation therefore requires an explicit
revision and uses `--to-revisions=<revision>=100`.

The confirmation string for those operations is the revision name itself, so
a stale confirmation cannot promote a different revision.

### `verify-worker-routes`

The durable pipeline sends Cloud Tasks to `POST /scan-job` and the watchdog to
`POST /scan-job-drain`. Both routes and `scanner-api/app/scan_job.py` are now
present on `main` as of the durable Standard 150 merge. A previously deployed
worker can still have been built from older source, so source readiness alone
does not prove the running revision serves those routes.

Because the worker is private, unauthenticated HTTP probes are rejected by
Cloud Run IAM before application routing. `verify-worker-routes` therefore
reports the running revision, image identity, Cloud Build provenance including
`_RELEASE_SHA`, and request timeout. A human must confirm that the reported
release SHA is a commit that declares both durable routes.

Run this before `activate-beta`.

### `activate-beta` ordering

1. Promote the explicitly named revision.
2. Probe the private worker and require an IAM rejection (`401` or `403`).
3. Resume the queue only if the promotion and privacy probe succeed.

A failure leaves the queue paused. The operator does not publish Base44; the
Base44 durable backend must already be published before the queue is resumed.

## One-time WIF setup

Use the repository script from an authorized Cloud Shell:

```bash
git clone https://github.com/bright4862-design/seo-autopilot.git
cd seo-autopilot
git checkout main
bash scripts/bootstrap-fixlist-cloud-operator-wif.sh
```

The bootstrap is idempotent and creates no service-account keys. It creates or
verifies:

- operator service account `fixlist-github-operator@seo-autopilot-501517.iam.gserviceaccount.com`
- WIF pool `github`
- provider `github-actions`
- immutable GitHub repository ID `1291460209`
- immutable GitHub owner ID `300628670`
- exact allowed ref `refs/heads/main`
- exact allowed workflow `bright4862-design/seo-autopilot/.github/workflows/fixlist-cloud-operator.yml@refs/heads/main`
- `roles/iam.workloadIdentityUser` only for that repository identity
- `roles/run.developer` on `fixlist-standard150-worker`
- `roles/cloudtasks.queueAdmin` on `fixlist-standard150`
- `roles/iam.serviceAccountViewer` on the existing Tasks invoker service account
- project-level `roles/cloudbuild.builds.viewer`, required only so
  `verify-worker-routes` can read Cloud Build provenance

The operator has no network-create rights. The static-egress canary network is
provisioned once by an admin; the operator only gets a read-only verifier role
(`scripts/bootstrap-fixlist-static-egress-canary.sh`). See
[static-egress-canary-permissions.md](static-egress-canary-permissions.md).

The WIF provider resource name and operator service-account email are identifiers,
not secrets. They are pinned directly in `.github/workflows/fixlist-cloud-operator.yml`;
no GitHub repository secrets are required for them.

### Why immutable IDs, main, and the exact workflow matter

GitHub's OIDC `repository_id` and `repository_owner_id` claims are immutable
numeric identifiers. The provider also checks `ref` and `workflow_ref`. Google
therefore accepts the operator identity only when the token comes from this
repository, this owner, `refs/heads/main`, and the exact Cloud Operator workflow
file on main.

This prevents another workflow on the same repository and branch from borrowing
the operator service account merely because it also has `id-token: write`.
The workflow's explicit ref guard and pinned source provide defense in depth.

## Release sequence

After the one-time WIF setup:

1. Run `verify-worker-routes` against the current worker revision.
2. If provenance does not map to a commit containing both durable routes,
   rebuild/deploy the worker from the exact approved `main` release SHA before
   any queue activation.
3. Deploy and verify the keyless dispatch gateway from canonical
   `dispatch-gateway/` source.
4. Publish the audited Base44 durable backend and configure
   `SCAN_DISPATCH_GATEWAY_URL`.
5. Run a controlled dispatch probe and verify the exact Cloud Task and worker
   request.
6. Run one fresh customer Funbooker scan end to end.

Standard 150 is restored only after the real customer flow completes:

`Browser → Base44 → Cloud Task → Python worker → crawl → review → durable callbacks → persisted FixList → authority proof → exact browser result`.
