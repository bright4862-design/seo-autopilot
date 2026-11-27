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
| `verify-serving-worker-release` | no | — |
| `verify-staged-worker-release` | no | — (exact tagged candidate revision input) |
| `barrier-status` | no | — |
| `verify-zero-admission-obligations` | no | exact source and barrier generation |
| Guarded owner-comment promotion (not direct dispatch) | yes | exact main SHA, revision, immutable image digest, closed barrier generation |
| `rollback-worker` | yes | exact revision name (separate authorized recovery) |

This is a selected operations list, not permission to execute any mutation.
Direct `promote-worker` dispatch is refused; the legacy `pause-queue`,
`resume-queue` and `activate-beta` operations are unsupported. Use the
signed cutover and claim-barrier procedures in the staged scan runbook only
with separate authorization. Incident [#378](https://github.com/bright4862-design/seo-autopilot/issues/378)
keeps Standard 150 public admission on hold pending release acceptance.
The 500 procedures below describe future capabilities, not approval to enable them.

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
Eligible Standard 500 launches require their own active rollout.
Before replacing the pinned launcher or downgrading the coordinator, close the
global barrier on a version that can read the scoped state and verify the drain.
This keeps admitted retries on their original launcher until they settle.

### Eligible Standard 500 rollout and hold

After both tier checks, the named 500 pilot, and the approved real-site QA are
recorded, prepare the accepted paid 500 gateway and Base44 settings during the
closed and drained cutover. The gateway's 500 capability stays enabled during
later scoped holds. On Base44, keep the older 500 setting disabled and verify
the current launcher's paid-500 readback. Open or restore the approved scoped
Standard 150 policy before starting the eligible 500 rollout.

Use `start-eligible-500` with the exact public source, open generation,
rollout ID, release ID, expiry, claim budgets, and current V9 launcher build.
Leave the owner roster empty. The launcher checks each customer's active
500-page grant and sends the typed claim. The confirmation is
`START-ELIGIBLE-500:<source-sha>:<open-generation>:<rollout-id>:<launcher-build-id>`.
Record the signed snapshot ID and verify new customer launches at both caps
and the reopening of their saved reports.

Use `hold-eligible-500` with the latest signed open generation and
`HOLD-ELIGIBLE-500:<source-sha>:<open-generation>:<rollout-id>`. Read back the
signed held state and surviving Standard 150 policy. Verify that a fresh 500
claim is refused, a previously admitted 500 attempt can finish, and approved
150 customers can still launch and reopen reports. Preserve the current
worker, gateway, and grant settings during the scoped hold.

If main has advanced beyond the serving coordinator, run the hold locally
with the authenticated operator credentials and a clean checkout of the
merged source that the coordinator and policy still report. The hold checks
that exact source and the current generation without requiring a new deploy.

### Why traffic operations name a revision

`--to-latest` resolves at execution time. If anything deployed between
validation and promotion, it could promote a newer revision instead of the
validated candidate. Every traffic operation therefore requires an explicit
revision and uses `--to-revisions=<revision>=100`.

The guarded promotion path binds approval to the exact main SHA, named
revision, immutable image digest and closed barrier generation. Its owner
comment format is `/promote-staged-worker <sha> <revision> <sha256:digest> <closed-barrier-generation>`.
This is syntax documentation, not an executable approval. Do not post the
command until all preconditions are met and the owner separately approves the
transition. A SHA-only comment or a revision name alone is insufficient.

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

The standalone workflow chooses the single 100%-serving revision from a
reconciled, Ready service, ignoring the generic prefilled revision input. It
fails closed on split traffic or a changed serving revision. Route provenance
does not prove executing-process release identity: independently run
`verify-serving-worker-release` for authenticated serving `/revision`, or
`verify-staged-worker-release` against the exact tagged zero-traffic candidate.
The staged check does not create or reassign a tag.

### Guarded promotion and rollback

The owner-comment path checks accepted source, the approved image/revision,
candidate runtime identity, published Base44 source and executing function
identities, and the signed closed-and-drained admission generation. The
post-promotion checks require reconciled Ready traffic, a private worker,
matching authenticated serving identity and unchanged queue state. A failure
attempts guarded restoration of the previous revision and verifies its
read-back; a concurrent ownership conflict must not be overwritten. This is
not an atomic conditional traffic update.

Promotion does not publish Base44, reopen admissions or resume queues.
A verified traffic transition alone is not a successful customer scan.
Keep the admission and queue controls unchanged until the separately
authorized acceptance and recovery steps are complete.

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

## Standard 150 incident recovery sequence

Follow the [staged scan runbook](scans/staged-scan-runbook.md) for the exact
candidate and owner-canary procedures. This checklist is not authorization
to deploy, publish, change traffic or run a scan.

1. Read the serving worker routes and authenticated runtime identity, signed
   admission state, and executing Base44 identities. Keep unknown evidence
   unknown; a route check or a green CI result cannot substitute for it.
2. Select a coherent release source and verify the tagged zero-traffic
   candidate, immutable image digest, full component map and Base44 package
   identity. Preserve the verified prior serving identity and recovery plan.
3. Obtain the required owner-only acceptance evidence using the bounded
   acceptance path in the runbook and the existing authorized account and
   project. Verify the signed complete or correctly limited result, durable
   persistence, customer reader reopening and terminal admission release.
   Do not substitute an ordinary customer retry or open public claims.
4. Record the exact-source acceptance evidence before requesting guarded
   production promotion. Recheck the signed closed-and-drained barrier and
   all runtime identities at the approved transition.
5. After separately authorized promotion, verify the resulting serving
   identity and customer journey under bounded owner-only controls. Keep
   public admission closed until the release and rollback evidence pass and
   the owner explicitly authorizes any queue or admission transition.

Standard 150 is restored only after the real customer flow completes:

`Browser → Base44 → Cloud Task → Python worker → crawl → review → durable callbacks → persisted FixList → authority proof → exact browser result`.

Do not change canonical fingerprints or signing predicates to make a
mismatched release pass. Grok, runtime AI, Extended 500 and Premium 5,000
remain outside this recovery.
