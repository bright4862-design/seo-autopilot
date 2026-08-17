# Standard 150 Deployment Contract

Authoritative mapping of every environment input reachable from the durable
Standard 150 path. Derived by tracing `/scan-job`, `/scan-job-drain`, `scan_job.py`, `run_scan`, the
authority completion path, and the six Base44 customer-release functions. The immutable
release SHA is recorded only after the full gate passes.

**Classification**

| Class | Meaning |
|---|---|
| **required** | The path is broken or insecure without it |
| optional-with-default | Code supplies a working default |
| feature-disabled | Only read by a feature that is off; must stay off |
| unrelated | Not reachable from the Standard 150 path |

**Two variables are never interchangeable:**

- `GROK_PROXY_ENABLED` — read by the **Cloud Run worker** (`scanner-api/app/main.py:52`)
- `GROK_CHAT_ENABLED` — read by the **Base44 `grokChat` function** (`base44/functions/grokChat/index.ts:43`)

Setting `GROK_CHAT_ENABLED` on the Cloud Run service is a no-op and produces
false assurance. The worker template sets `GROK_PROXY_ENABLED` only.

---

## Component A — Cloud Run durable worker (`scanner-api`)

Supplied by `cloudbuild.durable-worker.yaml`.

| Variable | Class | Code reader | Supplier | Missing-value failure mode |
|---|---|---|---|---|
| `BASE44_APP_ID` | **required** | `scan_job.py:42` → `_function_url()` | `--set-env-vars` (`_BASE44_APP_ID`) | **Silent misroute.** URL becomes `<api>/api/apps//functions/<name>`. Control and completion calls hit a malformed path. No clean error. |
| `SCAN_EVIDENCE_SIGNING_KEY` | **required** | `scan_job.py:179,200`, `main.py:488` | `--set-secrets` (`_SIGNING_KEY_SECRET`) | **Silent degradation.** `read_scan_run()` returns `None`; envelopes cannot be signed; authority path stops without raising. |
| `SCANNER_API_KEY` | **unrelated to `/scan-job`** | `main.py:51,62` `require_scanner_api_key()` | not supplied | Guards only the sibling routes `/scan`, `/review`, `/chat`, `/health/auth`. `/scan-job` never calls it. Absent, those siblings fail closed with 401 — the intended state for a single-purpose private worker. |
| `TASKS_INVOKER_SERVICE_ACCOUNT` | **required** | `main.py:379` `require_cloud_tasks_oidc()` | `--set-env-vars` (`_INVOKER_SA`) | Fail-closed: 503 "Worker authentication is not configured." Loud, safe. |
| `BASE44_API_URL` | optional-with-default | `scan_job.py:38` | `--set-env-vars` (`_BASE44_API_URL`) | Defaults to `https://base44.app`. Pinned explicitly so a deploy cannot silently target the public default. |
| `GROK_PROXY_ENABLED` | feature-disabled | `main.py:52` | `--set-env-vars`, hardcoded `false` | Defaults `""` → `False`. Grok is off by default; pinned so a future default change cannot enable it. |
| `FIXLIST_WORKER_SOURCE_SHA` | **required release provenance** | `main.py` health/revision payload | `--set-env-vars` (`_RELEASE_SHA`) | Missing does not change crawl behavior, but the revision is **not promotable** because its deployed bytes cannot be tied to the tested source SHA. |
| `GROK_MODEL_ID`, `GROK_TIMEOUT_SECONDS`, `GROK_MAX_ATTEMPTS`, `VERTEX_LOCATION` | feature-disabled | `grok_chat.py:14-17` | not supplied | Unreachable while `GROK_PROXY_ENABLED` is false. |
| `GCP_PROJECT`, `GOOGLE_CLOUD_PROJECT` | unrelated | `grok_chat.py` (Vertex endpoint) | not supplied | Grok-only. Not on the Standard 150 path. |

### Cloud Run deployment properties (not env vars)

| Property | Required value | Why |
|---|---|---|
| auth | `--no-allow-unauthenticated` | **Load-bearing.** `require_cloud_tasks_oidc()` verifies neither signature nor `aud`; it only compares the `email` claim of a base64-decoded payload. Cloud Run IAM performs the real token validation. On a public service this check is trivially forgeable. |
| runtime identity | `--service-account=<_RUNTIME_SA>` | Otherwise inherits the over-privileged default compute SA. |
| `--timeout` | `480` | Must match `dispatchDeadline: "480s"` in `cloudTasks.js` and outlast crawl, review, signed control reads, and persistence. |
| `--concurrency` | `1` | One durable job per instance. Never raise this: parallel scans must scale horizontally, not share a Python process. |
| `--max-instances` | `40` | Must stay **strictly above** the queue's `maxConcurrentDispatches` so the Cloud Tasks limiter is the single control point for how many scans run at once. If the two were equal, ordinary instance churn would make Cloud Run reject dispatches before the queue throttled, and those 429s would read as scan failures rather than backpressure. `scripts/set-standard150-scan-concurrency.sh` refuses any target above the live ceiling. |
| `--no-traffic` | set | New revision takes 0%; promotion is a separate human decision. |

### Scan capacity — two independent limits

| Limit | Where enforced | Current value |
|---|---|---|
| Membership | `evaluatePaidAccess()` — an active `Access` grant | unbounded; 100+ members supported |
| Concurrent scans, all owners | Cloud Tasks `maxConcurrentDispatches` | ramp target 30 |
| Concurrent scans, one owner | Firestore coordinator, one document per owner | 1 |
| Worker instance ceiling | Cloud Run `--max-instances` | 40 |

Raising throughput means moving the queue and the worker ceiling **together**, in
that order: rebuild and promote the worker first, then raise the queue. The ramp
script enforces the ordering by refusing a queue target the live worker cannot
serve. Rungs are discrete — `1, 3, 5, 10, 20, 30` — so each step is observable
and attributable.

---

## Component B — Base44 dispatcher (`startStandardScanJob`)

Base44-hosted. Supplied through Base44 function environment, **not** Cloud Build.

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_TASKS_QUEUE_PATH` | **required** | `entry.ts` → `enqueueScanJob({queuePath})` | Cloud Tasks REST call targets a malformed queue path; enqueue fails. |
| `SCAN_DRAIN_QUEUE_PATH` | **required and must differ from scan queue** | `entry.ts` → `enqueueScanDrain({queuePath})` | Admission fails closed before dispatch. The delayed watchdog must not share the concurrency-1 scan queue. |
| `SCAN_WORKER_URL` | **required** | `entry.ts` → `audienceForWorkerUrl()` | `new URL("")` throws → `invalid_worker_url`. Fail-closed. |
| `TASKS_INVOKER_SERVICE_ACCOUNT` | **required** | `cloudTasks.js` `oidcToken.serviceAccountEmail` | Cloud Tasks cannot mint an OIDC token; the worker rejects the call. |
| `SCAN_DISPATCH_GATEWAY_URL` | **required for keyless dispatch** | `cloudTasks.js` `createTask()` | Unset selects the key-based route below. Set, it is the only enqueue path. |
| `SCAN_EVIDENCE_SIGNING_KEY` | **required with the gateway** | `cloudTasks.js` `createTaskViaGateway()` | `dispatch_gateway_signing_key_missing`. Fail-closed before any network call. |
| `BETA_SCAN_ADMISSION_ENABLED` | **required; default-off** | `admission.js`, package-local `admissionClient.js` | Any value other than exact `true` refuses new admission. No ScanRun is created. |
| `BETA_COHORT_ALLOWED_USER_IDS` | **retired for scan admission; no longer read** | — | `admission.js` no longer reads it and setting it has no effect on scanning. Entitlement is the invitation: `evaluatePaidAccess()` accepts `stripe_checkout`, `owner_test` and `manual_grant`, each requiring an active grant bound to the caller's own id and email, and `Access` is admin-only for create/update/delete. **`createAccessCheckout` still reads its own separate copy of this variable as a purchase-seat cap** — that is a different gate and is unchanged. |
| `SCAN_ADMISSION_COORDINATOR_URL` | **required when admission is enabled** | package-local `admissionClient.js` | Admission fails closed; no new ScanRun is created or bound. |
| `GCP_SERVICE_ACCOUNT_KEY` | **required only without the gateway** | `cloudTasks.js` `accessToken()` | `tasks_credentials_not_configured`. Distinct from a malformed key, which yields a `tasks_key_*` code, or `tasks_token_mint_failed` when the cause is not recognised. |

### Enqueue route selection

`createTask()` picks exactly one of two routes, and `SCAN_DISPATCH_GATEWAY_URL`
is the switch:

- **Keyless (preferred).** Set `SCAN_DISPATCH_GATEWAY_URL`. The dispatcher
  HMAC-SHA256-signs the canonical `{queue_path, task}` document with
  `SCAN_EVIDENCE_SIGNING_KEY`, sends it to `POST <gateway>/dispatch` as
  `x-fixlist-signature`, and the Cloud Run gateway creates the task using its
  own attached identity through Application Default Credentials. No Google
  private key is ever held by Base44. Org policy
  `constraints/iam.disableServiceAccountKeyCreation` makes this the only
  route that can be provisioned.
- **Key-based (legacy fallback).** Leave `SCAN_DISPATCH_GATEWAY_URL` unset and
  supply `GCP_SERVICE_ACCOUNT_KEY`. Retained for rollback only.

The gateway is a validating proxy, not a general Cloud Tasks relay. It rejects
any document whose `queue_path`, task-name prefix, target URL, HTTP method,
OIDC service account, OIDC audience, or `dispatchDeadline` does not match its
own configuration, so the dispatcher and the gateway must be deployed from the
same contract. `dispatchDeadline` is `480s` on both sides; the Cloud Run
`--timeout` above must stay equal to it.

The gateway's canonical source is `dispatch-gateway/` in this repository,
deployed with `scripts/deploy_dispatch_gateway.sh` (owner-executed). Its
validation surface is pinned by `tests/frontend/dispatchGatewayContract.test.mjs`;
change the gateway, the dispatcher, or that suite only together.

The dispatcher does **not** read `SCANNER_API_URL` or `SCANNER_API_KEY`. It
authenticates the customer, verifies exactly one active paid owner-bound Access
record, creates the delayed attempt-bound watchdog task, creates the immediate
worker task, and returns.

## Component C — authority persistence and customer result projection

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_EVIDENCE_SIGNING_KEY` | **required** | `durableScanWorkerControl/index.ts`, `persistDurableScanAuthority/index.ts`, `getCustomerScanResult/index.ts` | Authority writes fail with `authority_not_configured`; customer result reads return `result_authority_unavailable`. No unverified FixItems are returned. |
| `BETA_SCAN_ADMISSION_ENABLED` | **required for active coordinator release** | package-local `admissionClient.js` | If disabled, terminal persistence stays truthful but the bound Firestore admission is not actively released. Bound admissions intentionally do **not** expire by wall clock, so the reconciliation/backstop path must repair release before the same owner can start another scan. |
| `SCAN_ADMISSION_COORDINATOR_URL` | **required for active coordinator release** | package-local `admissionClient.js` | Terminal persistence stays authoritative; release logs a bounded failure. The periodic reconciliation backstop repairs terminal release without allowing a bound scan to overlap a newer admission. |

The authority functions and result projection hold `asServiceRole` only after
an exact caller/ScanRun ownership check. All six release functions must be
deployed from the same immutable SHA. The result projection independently
checks the active paid entitlement and verifies the persisted HMAC before it
returns FixList or FixItem content.

Admission ownership lives in Firestore through the coordinator.
`BASE44_ATOMIC_UPDATE_MANY_CONFIRMED` is deliberately absent, and the
coordinator claim token is transient rather than persisted to `ScanRun`.

## Component D — Base44 checkout and activation

`createAccessCheckout` and `stripeWebhook` are Base44-hosted. Their Stripe
secrets are supplied through Base44 Secrets, never Cloud Build or browser
configuration.

| Variable or secret | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `STRIPE_SECRET_KEY` | **required secret** | both checkout functions via `base44:runtime` | Stripe session retrieval/creation fails; no entitlement is granted. |
| `STRIPE_WEBHOOK_SECRET` | **required secret** | `stripeWebhook/entry.ts` | Webhook signature verification fails; no entitlement is granted. |
| `BETA_CHECKOUT_ENABLED` | **required switch; secure default is off** | `createAccessCheckout/entry.ts` | Missing or any value other than exact `true` returns `checkout_paused` before Access or Stripe writes. |
| `BETA_CHECKOUT_GENERATION` | **required when checkout is enabled** | `createAccessCheckout/entry.ts` | Missing or malformed values fail closed with `checkout_configuration_invalid`; this generation participates in Stripe idempotency. |
| `BETA_COHORT_ALLOWED_USER_IDS` | **required when checkout is enabled** | `createAccessCheckout/entry.ts` | Must contain 1–25 unique exact Base44 user IDs separated by commas or whitespace. Empty, malformed, or more than 25 IDs fail closed before writes. The list must include every existing active beta owner as well as new invitees. |
| `CHECKOUT_RETURN_ORIGINS` | optional production supplement; **required for preview checkout** | `createAccessCheckout/entry.ts` | Only the fixed production origin remains accepted. Configure `https://preview--rich-rank-pilot-flow.base44.app` when preview checkout is intentionally tested. |
| `CHECKOUT_ALLOW_LOCALHOST` | optional-with-secure-default | `createAccessCheckout/entry.ts` | Defaults to false. Localhost return URLs remain rejected. Never enable in production. |

Return URLs are exact-origin matched. Arbitrary request origins, paths,
credentials, query strings, fragments, and lookalike subdomains are rejected
before any Access write or Stripe call. Pending checkout retries reuse the
stored open session. Checkout never creates Access rows: an operator must
pre-provision exactly one pending, owner-ID-and-email-bound Access record for
each allowlisted customer before enabling the cohort. The hard 25-ID allowlist
is therefore the seat allocator; missing or duplicate Access rows fail before
Stripe. Stripe idempotency is stable on user ID, cohort generation, and prior
session, while webhook replay handling keeps one entitlement grant exact-once.

To pause new purchases without taking existing scans or results offline, set
`BETA_CHECKOUT_ENABLED=false`. Do not delete Access rows or disable the worker
as a purchase-pause mechanism.

---

## Component E — disabled-first deployment controls

Production rollout is intentionally split from source integration. The release tooling requires an exact clean `origin/main` checkout before any mutation.

- `scripts/bootstrap-fixlist-admission-coordinator.sh` is the **one-time owner-only** bootstrap. It creates/normalizes the dedicated `fixlist-admission` Firestore Native database with delete protection, the dedicated coordinator runtime identity, the drain queue, and only the IAM edges required by those resources. It requires `CONFIRM=BOOTSTRAP-ADMISSION-INFRA`.
- `scripts/deploy_admission_coordinator.sh` performs an exact-SHA Cloud Run source deploy with an explicit Cloud Build service account, pinned signing-secret reference and `FIXLIST_COORDINATOR_SOURCE_SHA`.
- `scripts/configure-base44-beta-admission.sh` sets only the coordinator URL, drain queue, exact 1–25-user cohort and both beta switches to **false**. It cannot enable admission or checkout.
- `scripts/deploy-base44-beta-functions.sh` deploys exactly the six release functions named by `scripts/base44_release_manifest.mjs`; it never deploys the site or reconciles entities.
- `scripts/build-worker-candidate.sh` submits the durable worker build with an explicit Cloud Build identity and refuses completion unless the candidate is Ready, `concurrency=1`, `timeout=480`, source-stamped, and at **0% traffic**.

**`base44 entities push` is prohibited in the release path.** It is not used to update `ScanRun`, `FixList`, or `FixItem`. Those three authority schemas must be updated explicitly by name through the Base44 schema API/connector at cutover, then the deployed package/schema inventory is compared byte-for-byte with the candidate.

Both worker and coordinator expose their exact source SHA in health/revision metadata. Source provenance is release evidence; a revision without the expected SHA is not promotable.

## Secret handling

`SCAN_EVIDENCE_SIGNING_KEY` is the **only** secret the durable worker requires.
It is injected with `--set-secrets` by Secret Manager **name** and must never
appear in `--set-env-vars`: that writes plaintext into the service revision and
into build logs. The runtime service account needs
`roles/secretmanager.secretAccessor` on that one secret.

`SCANNER_API_KEY` is deliberately **not** supplied. Evidence:

| Route | App-level guard |
|---|---|
| `POST /scan-job` | `require_cloud_tasks_oidc` only |
| `POST /scan-job-drain` | `require_cloud_tasks_oidc` only |
| `POST /scan` | `require_scanner_api_key` |
| `POST /review` | `require_scanner_api_key` + `require_cloud_tasks_oidc` |
| `POST /chat` | `require_scanner_api_key` |
| `GET /health/auth` | `require_scanner_api_key` |
| `GET /health`, `GET /revision` | none |

The durable path runs the Python review **in-process** — `scan_job.py`
`build_local_review()` imports `run_review` directly — so it never calls the
`/review` HTTP route, and `scan_job.py` contains no reference to
`SCANNER_API_KEY` or `x-scanner-key`. Supplying the key to this worker would
grant it capability it does not need.

Consequence, deliberate: with the key absent, `/scan`, `/review`, `/chat` and
`/health/auth` return 401 on this service. `require_scanner_api_key()` fails
closed on an empty expected key (`main.py:62`), so removing the secret makes
those routes unusable, never open.

## Values this repository cannot supply

Every value below is environment-specific and must be provided explicitly. The
build fails closed if any is empty.

`_WORKER_SERVICE` · `_REGION` · `_IMAGE` · `_RUNTIME_SA` · `_INVOKER_SA` ·
`_BASE44_APP_ID` · `_BASE44_API_URL` · `_SIGNING_KEY_SECRET` ·
`_SIGNING_KEY_VERSION` · `_RELEASE_SHA`, plus the Cloud Tasks queue name.

`_RELEASE_SHA` is the full 40-character lowercase Git commit SHA of the exact,
clean checkout submitted to Cloud Build. A manual `gcloud builds submit` uses a
storage source and does not reliably populate the trigger-only built-in
`$COMMIT_SHA`; a missing built-in can be replaced by an empty string. The
durable build therefore tags, pushes and deploys `${_IMAGE}:${_RELEASE_SHA}`
only. Before submission, `scripts/deployment_preflight.sh` requires
`RELEASE_SHA`, proves that it equals `git rev-parse HEAD`, and requires an empty
`git status --porcelain` result.

### Signing-key version pinning

`_SIGNING_KEY_VERSION` must be a **numeric, ENABLED** Secret Manager version of
`_SIGNING_KEY_SECRET`. **`latest` is prohibited for the immutable release.**

`latest` is resolved when a container instance starts, not when the revision is
deployed. Adding a new secret version would therefore change what an
already-verified revision reads, without any revision change to point at. The
authority seal would begin failing against evidence sealed under the previous
key, and the revision digest — the release's identity proof — would still match.
Pinning one numeric version makes the mounted key part of the frozen artifact.

Verification: `scripts/deployment_preflight.sh` requires `SIGNING_KEY_VERSION`,
rejects a non-numeric value, and refuses an executable `:latest` in the build
artifact. `scripts/post_deploy_verify.sh` requires `EXPECTED_SIGNING_SECRET` and
`EXPECTED_SIGNING_VERSION` and asserts the deployed revision's
`SCAN_EVIDENCE_SIGNING_KEY` reference matches both exactly. Neither script ever
reads or prints a secret payload.

The post-deploy verifier also requires the exact expected image, runtime service
account and invoker service account. It fails closed if the Cloud Run IAM policy
cannot be read or parsed, rejects public `roles/run.invoker` bindings, and
requires `serviceAccount:<EXPECTED_INVOKER_SA>` to hold that role.

Before running it, use the authenticated, pinned Base44 CLI in a clean temporary
checkout to pull the deployed functions, then pass that pull's `base44/functions`
directory as `BASE44_PULLED_FUNCTIONS_DIR` and the same pull's
`base44/entities` directory as `BASE44_PULLED_ENTITIES_DIR`. The verifier hashes
all six required function packages, including each `function.jsonc`, plus the
exact `ScanRun.jsonc`, `FixList.jsonc`, and `FixItem.jsonc` authority schemas.
It fails if any package/schema is missing or differs from the release candidate.
A dashboard name or function-only check is not sufficient.

## Production acceptance gate

The paid beta is a single Standard 150 contract. A release is NO-GO unless one
deployed Funbooker acceptance scan proves all of the following on the exact
candidate SHA/image/fingerprint:

- broad sitemap and DOM-link discovery reports at least 1,200 in-scope URLs;
- exactly 150 pages are fetched and analysed;
- the site is classified as a booking/experiences marketplace;
- the saved ScanRun and FixList are authority-sealed and release-gate eligible;
- Python review is used, no fallback result is substituted, and no FixItem
  targets an asset URL;
- refreshing the exact result route restores the same completed scan.

## Verification

- Pre-deploy: `bash scripts/deployment_preflight.sh`
- Post-deploy, read-only: `bash scripts/post_deploy_verify.sh`
- Full gate: `bash scripts/release_gate.sh`

## Queue reconciliation backstop

Multi-scan beta operation has two independent terminal-recovery paths:

1. Each admitted scan gets a delayed `/scan-job-drain` task on the dedicated
   `fixlist-standard150-drain` queue. Queue wait never counts as crawl runtime;
   the worker stamps `started_at` on actual pickup and the drain waits through
   the full three-delivery Cloud Tasks retry envelope before terminalizing.
2. Cloud Scheduler job `fixlist-standard150-reconcile` invokes the private
   worker route `/scan-reconcile` every five minutes using the exact existing
   `TASKS_INVOKER_SERVICE_ACCOUNT` OIDC identity. The route performs no crawl.
   It sends a parameter-free HMAC-signed `sweep` action to
   `durableScanWorkerControl`, which may only touch server-admitted ScanRuns.

The periodic sweep is deliberately later than the normal drain: queued scans
must exceed 30 minutes and worker-started scans must exceed 35 minutes before
reconciliation may fail them. Terminal server-admitted rows in the recent
release window are also re-released idempotently so a transient coordinator
failure cannot leave an owner admission bound after the scan itself completed.

Bound admission is not released by wall-clock lease expiry. Only an exact
terminal release for the bound `scan_id` frees the owner slot. This prevents a
late Cloud Task from an old scan overlapping a newly admitted scan.

Deployment/verification scripts:

- `scripts/configure-standard150-reconciler.sh` — confirmation-gated Scheduler
  create/update; OIDC audience is the canonical Cloud Run service URL.
- `scripts/verify-standard150-reconciler.sh` — read-only verification of enabled
  state, five-minute schedule, exact `/scan-reconcile` target, POST method,
  service account and OIDC audience.
