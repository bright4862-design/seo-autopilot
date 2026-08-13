# Standard 150 Deployment Contract

Authoritative mapping of every environment input reachable from the durable
Standard 150 path. Derived by tracing `/scan-job`, `/scan-job-drain`, `scan_job.py`, `run_scan`, the
authority completion path, and the three Base44 durable functions. The immutable
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
| `GROK_MODEL_ID`, `GROK_TIMEOUT_SECONDS`, `GROK_MAX_ATTEMPTS`, `VERTEX_LOCATION` | feature-disabled | `grok_chat.py:14-17` | not supplied | Unreachable while `GROK_PROXY_ENABLED` is false. |
| `GCP_PROJECT`, `GOOGLE_CLOUD_PROJECT` | unrelated | `grok_chat.py` (Vertex endpoint) | not supplied | Grok-only. Not on the Standard 150 path. |

### Cloud Run deployment properties (not env vars)

| Property | Required value | Why |
|---|---|---|
| auth | `--no-allow-unauthenticated` | **Load-bearing.** `require_cloud_tasks_oidc()` verifies neither signature nor `aud`; it only compares the `email` claim of a base64-decoded payload. Cloud Run IAM performs the real token validation. On a public service this check is trivially forgeable. |
| runtime identity | `--service-account=<_RUNTIME_SA>` | Otherwise inherits the over-privileged default compute SA. |
| `--timeout` | `480` | Must match `dispatchDeadline: "480s"` in `cloudTasks.js` and outlast crawl, review, signed control reads, and persistence. |
| `--concurrency` | `1` | One durable job per instance. |
| `--no-traffic` | set | New revision takes 0%; promotion is a separate human decision. |

---

## Component B — Base44 dispatcher (`startStandardScanJob`)

Base44-hosted. Supplied through Base44 function environment, **not** Cloud Build.

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_TASKS_QUEUE_PATH` | **required** | `entry.ts` → `enqueueScanJob({queuePath})` | Cloud Tasks REST call targets a malformed queue path; enqueue fails. |
| `SCAN_WORKER_URL` | **required** | `entry.ts` → `audienceForWorkerUrl()` | `new URL("")` throws → `invalid_worker_url`. Fail-closed. |
| `TASKS_INVOKER_SERVICE_ACCOUNT` | **required** | `cloudTasks.js` `oidcToken.serviceAccountEmail` | Cloud Tasks cannot mint an OIDC token; the worker rejects the call. |
| `SCAN_DISPATCH_GATEWAY_URL` | **required for keyless dispatch** | `cloudTasks.js` `createTask()` | Unset selects the key-based route below. Set, it is the only enqueue path. |
| `SCAN_EVIDENCE_SIGNING_KEY` | **required with the gateway** | `cloudTasks.js` `createTaskViaGateway()` | `dispatch_gateway_signing_key_missing`. Fail-closed before any network call. |
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

## Component C — `durableScanWorkerControl` and `persistDurableScanAuthority`

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_EVIDENCE_SIGNING_KEY` | **required** | both `index.ts` | 503 `authority_not_configured`. Fail-closed: no envelope is trusted without it. |

Both functions hold `asServiceRole`. All three release functions must be deployed
from the same immutable SHA. Completion never reads or writes `Access`; payment
is enforced once, before enqueue.

---

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
