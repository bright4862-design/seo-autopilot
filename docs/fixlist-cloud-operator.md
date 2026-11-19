# FixList Cloud Operator

Keyless Google Cloud operations for the durable Standard 150 release, run
from GitHub Actions instead of Cloud Shell.

The organization blocks service-account key creation, so this operator uses
Workload Identity Federation (WIF). Each GitHub Actions run receives a
short-lived Google credential; no long-lived Google key is created, stored,
or printed.


## Operations

This page describes the **current main-branch workflow**, not authorization to
change production. Read-only observations do not establish Standard 150 release
readiness. The workflow itself requires a dispatch from the pinned owner on
`main`; its dispatch form includes a required `confirm` field even when the
selected read-only operation does not consume a promotion confirmation.

| Operation | Mutating | Purpose |
|---|---|---|
| `status` | no | Cloud Run/queue/coordinator status; **not** live release identity proof |
| `verify-iam` | no | Inspect worker IAM |
| `verify-worker-routes` | no | Source/build route provenance; **not** authenticated `/revision` parity |
| `verify-serving-worker-release` | no | Resolve the 100%-serving revision and check its authenticated `/revision` against exact main |
| `verify-staged-worker-release` | no | Check an explicitly tagged, zero-traffic candidate's routes, `/revision` and signed Base44 runtime |
| `barrier-status` | no | Read coordinator barrier state and generation |
| `verify-zero-admission-obligations` | no | Inspect closed/drained obligation evidence |
| `staged-queue-status` | no | Read staged-queue state, not readiness authorization |
| `tag-worker-candidate` | **yes** | Traffic-tag mutation, requires exact revision confirmation |
| `promote-worker` / `rollback-worker` | **yes** | Cloud Run traffic mutation, requires separate approval |
| `cutover-pause` / `cutover-resume` / `open-claim-barrier` / `acceptance-only` | **yes** | Admission-barrier mutations with separate confirmation and generation controls |

The old `pause-queue`, `resume-queue` and `activate-beta` operation names are
**unsupported unsafe operations** in the current shell dispatcher, even though
`activate-beta` remains a legacy workflow choice. Do not use these as runbook
instructions, and do not bypass the guarded admission/drain procedure.

### Why traffic operations name a revision

`--to-latest` resolves at execution time. If anything deployed between
validation and promotion, it could promote a newer revision instead of the
validated candidate. Every traffic operation therefore requires an explicit
revision and uses `--to-revisions=<revision>=100`.

The confirmation string for those operations is the revision name itself, so
a stale confirmation cannot promote a different revision.


### Read-only Standard 150 incident triage: authenticated `/revision`

Incident [#378](https://github.com/bright4862-design/seo-autopilot/issues/378)
records worker/Base44 release-fingerprint drift at signed persistence.
A green source commit, matching function name, working `/health` endpoint,
or a successful `status` call cannot resolve that mismatch.

For an **owner-authorized diagnostic, not a release operation**:

1. In the pinned [FixList Cloud Operator workflow](../.github/workflows/fixlist-cloud-operator.yml)
   on exact `main`, select `verify-serving-worker-release`. Do not select a
   mutating operation and do not change traffic or queues. The workflow's
   prefilled historical `revision` value is **ignored** by this serving-worker
   verifier; it resolves the actual serving revision from Cloud Run at probe
   time.
2. The workflow reads the canonical Cloud Run service URL, mints a short-lived
   invoker ID token for that service's audience, and calls
   `verify_worker_runtime_revision`. Its target must be attributable to the
   **100%-serving revision**; ambiguous traffic or an unaddressable revision
   must remain unverified.
3. The authenticated `GET /revision` comparison checks the worker's runtime
   fingerprint, **complete component-version map**, and nonempty exact source
   SHA against the frozen checked-out candidate contract. Record the
   observed revision and the verifier's verdict without recording token or
   signing-key contents.
4. Treat `FAIL` or `INDETERMINATE` as a **NO-GO**, not as permission to
   edit a Base44 fingerprint literal, loosen signed persistence, rerun the
   failed customer scans, or promote a different revision by guesswork.

`verify-worker-routes` is a narrower source/build provenance diagnostic: it
checks whether durable `POST /scan-job` and `POST /scan-job-drain` routes were
declared, along with the worker build and timeout. It cannot establish which
fingerprint a running container actually computes.

### A staged candidate is different from the public serving revision

`verify-staged-worker-release` checks the specific tagged **0%-traffic**
candidate, using the verified tag URL but the canonical service token
audience. This is a read-only comparison; creating or changing a tag is
a **different, mutating** operation requiring distinct approval.

Even a successful worker `/revision` probe is **necessary, not sufficient**.
The release also needs matching Base44 executing package identities, a
closed/drained admission barrier, exact signing authority, a specifically
approved owner-only Standard 150 canary, durable signed persistence,
independent full-access customer re-open and rollback continuity.
An unmerged draft, candidate fingerprint or editor-preview checkpoint is
not a verified production promotion.

### Activation is not implicit

The current operator shell deliberately rejects `pause-queue`,
`resume-queue` and `activate-beta`. Do not infer that a successful
`verify-worker-routes` or `verify-serving-worker-release` run authorizes
queues, payment checkout, public reopening or customer scans. The separate
barrier-generation and release-approval runbooks govern those mutations.

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


## Release decision boundary

The **read-only** checks above are safe diagnostic prerequisites, not a
substitute for a documented release decision. Before any separately approved
Standard 150 cutover, the operator must establish exact accepted source and
package identities, a Ready/attributable serving worker, the full
fingerprint/component parity, privacy and signing boundaries, a recoverable
rollback, and closed/drained admission obligations.

Only **after distinct explicit approval** may a bounded owner canary be
performed. It must use the Standard 150 entitlement and the exact approved
route; successful completion alone is not enough without the independently
verified signed FixList and authenticated full-access customer read-back.
Public opening and payments are separate decisions, and the post-opening
Stage-4 audit cannot substitute for pre-opening approval.

The required end-to-end customer journey is:

`Browser → Base44 → Cloud Task → Python worker → crawl → review → durable callbacks → persisted FixList → authority proof → exact customer re-open`.

**Incident #378 remains NO-GO until observed production evidence proves that
journey.** Preserve the failed historical ScanRuns as auditable failures.
