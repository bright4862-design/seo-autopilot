# Standard 150 Deployment Contract

Authoritative mapping of every environment input reachable from the durable
Standard 150 path. Derived by tracing `/scan-job`, `scan_job.py`, `run_scan`, the
authority completion path, and the three Base44 durable functions at commit
`0059cb44b3b051011674df16c343eddabb1c3fd2`.

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
| `--timeout` | `300` | Must match `dispatchDeadline: "300s"` in `cloudTasks.js`. |
| `--concurrency` | `1` | One durable job per instance. |
| `--no-traffic` | set | New revision takes 0%; promotion is a separate human decision. |

---

## Component B — Base44 dispatcher (`startStandardScanJob`)

Base44-hosted. Supplied through Base44 function environment, **not** Cloud Build.

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_TASKS_QUEUE_PATH` | **required** | `entry.ts` → `enqueueScanJob({queuePath})` | Cloud Tasks REST call targets a malformed queue path; enqueue fails. |
| `SCAN_WORKER_URL` | **required** | `entry.ts` → `audienceForWorkerUrl()` | `new URL("")` throws → `invalid_worker_url`. Fail-closed. |
| `TASKS_INVOKER_SERVICE_ACCOUNT` | **required** | `cloudTasks.js:74` `oidcToken.serviceAccountEmail` | Cloud Tasks cannot mint an OIDC token; the worker rejects the call. |
| `GCP_SERVICE_ACCOUNT_KEY` | **required** | `cloudTasks.js` `accessToken()` | `tasks_credentials_not_configured`. Distinct from a malformed key, which yields `tasks_token_mint_failed`. |
| `SCAN_EVIDENCE_SIGNING_KEY` | **required** | `entry.ts` attestation | Results cannot be attested. |
| `SCANNER_API_URL` (aliases `PYTHON_SCANNER_API_URL`, `PYTHON_SCANNER_URL`, `SCANNER_URL`, `CLOUD_API`) | **required** | `scannerApiUrl()` | `url_not_configured`. |
| `SCANNER_API_KEY` (alias `PYTHON_SCANNER_API_KEY`) | **required** | `scannerApiKey()` | `key_not_configured`. |

> The multiple URL/key aliases are legacy compatibility. The dispatcher accepts
> the first non-empty match; prefer `SCANNER_API_URL` / `SCANNER_API_KEY`.

## Component C — `durableScanWorkerControl` and `persistDurableScanAuthority`

| Variable | Class | Code reader | Missing-value failure mode |
|---|---|---|---|
| `SCAN_EVIDENCE_SIGNING_KEY` | **required** | both `index.ts` | 503 `authority_not_configured`. Fail-closed: no envelope is trusted without it. |

Both functions hold `asServiceRole`. Both must be deployed for the durable path
to reach a terminal state; only `startStandardScanJob` is currently live.

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
`_BASE44_APP_ID` · `_BASE44_API_URL` · `_SIGNING_KEY_SECRET`, plus the Cloud
Tasks queue name.

## Verification

- Pre-deploy: `bash scripts/deployment_preflight.sh`
- Post-deploy, read-only: `bash scripts/post_deploy_verify.sh`
- Full gate: `bash scripts/release_gate.sh`
