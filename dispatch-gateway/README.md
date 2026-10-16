# FixList dispatch gateway

Keyless Cloud Tasks enqueue gateway for the durable Standard 150 pipeline.

The org policy `constraints/iam.disableServiceAccountKeyCreation` blocks
minting the JSON key the Base44 dispatcher's legacy route needs, so Base44
cannot hold a long-lived Google credential. This service closes that gap:
Base44 HMAC-SHA256-signs the `{queue_path, task}` dispatch document with
`SCAN_EVIDENCE_SIGNING_KEY` and POSTs it to `/dispatch`; the gateway
validates the document against its own configuration and creates the Cloud
Task using its **attached service identity** through Application Default
Credentials. No Google private key exists anywhere in the path.

This directory is the canonical gateway source. The Cloud Shell bootstrap block that
first deployed the gateway wrote an identical `main.py` to `/tmp`; any change
must be made here and redeployed from here, never by editing a pasted copy.

## Read-only rescan comparison

`POST /compare` runs the existing canonical Python comparison library over two
sealed snapshots. The Base44 result reader owns user authentication, paid access,
and the service-owned previous-scan lookup. Browser input may select only the
current scan; it never supplies the previous scan, evidence, or owner identity.
The gateway independently verifies both historic result seals and the asserted
owner/project/scope/lineage pair before calling `compare_repair_runs`.

Requests use the `scan_comparison_request_v1` contract with a 32-character
lowercase hexadecimal nonce. `x-fixlist-timestamp` is an integer Unix timestamp
within 300 seconds of gateway time. The request key is HMAC-SHA256 of
`fixlist-scan-comparison-request-v1` using the existing signing root; the request
signature covers `timestamp + "\n" + raw_body`. This domain is distinct from
dispatch and response signatures.

Successful responses contain only `payload` and `proof`. The payload binds
`scan_comparison_response_v1`, the request nonce, exact current and previous scan
IDs, customer presentation, gateway source SHA, and integer `generated_at`.
The response key uses the domain `fixlist-scan-comparison-response-v1`; the proof
covers the canonical stable serialization of that payload. The Base44 reader
must verify the proof, nonce, IDs, and freshness before projecting presentation.
Snapshots, result proofs, lineage artifacts, and signing material are never
returned in this response or customer projection. Responses to rejected requests
contain bounded error codes only.

Comparison requests have a 4,100,000-byte limit, enough for two separately
bounded authority snapshots. `/dispatch` retains its smaller 256 KiB limit,
including chunked bodies. Fresh duplicate comparison requests are safe to repeat:
the operation performs no entity writes, URL requests, or task creation. Response
nonce verification prevents reuse for a different reader request. Comparison
failure must leave the current saved FixList available.

The deployment script creates a minimal build context from the exact release
commit with this gateway and seven canonical modules from `scanner-api/app`.
The comparator is not copied into a second maintained implementation. Its seal
primitives are shared with the worker through `authority_seal.py`; their historic
serialization remains unchanged. The comparison route needs no new IAM grants,
service account key, worker route, or runtime model access.

## Contract

The gateway is a validating proxy, not a general Cloud Tasks relay. It
rejects any document that does not match, in order:

| Check | Rejection |
|---|---|
| HMAC of raw body with `SCAN_EVIDENCE_SIGNING_KEY` | `invalid_signature` 401 |
| `queue_path` equals `SCAN_TASKS_QUEUE_PATH` | `invalid_queue` 400 |
| task name prefix `<queue>/tasks/standard150-` | `invalid_task_name` 400 |
| target URL is exactly the worker `/scan-job` or `/scan-job-drain` | `invalid_worker_target` 400 |
| method POST | `invalid_method` 400 |
| OIDC service account equals `TASKS_INVOKER_SERVICE_ACCOUNT` | `invalid_invoker` 400 |
| OIDC audience equals the worker origin | `invalid_audience` 400 |
| `dispatchDeadline` exactly `480s` | `invalid_dispatch_deadline` 400 |
| base64 body decodes to JSON with a `scan_id` | `invalid_task_body` / `missing_scan_id` 400 |
| `scan_mode` absent or `standard_150` | `invalid_scan_mode` 400 |

Response mapping the Base44 dispatcher relies on:

- Cloud Tasks 409 (task already exists) → 200 `{deduplicated: true}` — the
  deterministic task name makes retries idempotent.
- Cloud Tasks 5xx → 502 (dispatcher treats the outcome as unknown and does
  NOT terminalize the run).
- Cloud Tasks other 4xx → 403 (definite failure, safe to terminalize).

The dispatcher side of this contract is
`base44/functions/startStandardScanJob/cloudTasks.js`
(`createTaskViaGateway`), and both sides are pinned by
`tests/frontend/dispatchGatewayContract.test.mjs`, which mirrors the table
above and re-runs it against what the dispatcher actually signs. Change
either side only together with that suite.

## Environment

| Variable | Meaning |
|---|---|
| `SCAN_TASKS_QUEUE_PATH` | Full Cloud Tasks queue path the gateway may enqueue to |
| `SCAN_WORKER_URL` | Exact worker `/scan-job` URL (trailing `/` stripped at startup) |
| `TASKS_INVOKER_SERVICE_ACCOUNT` | The only OIDC identity tasks may be minted as |
| `SCAN_EVIDENCE_SIGNING_KEY` | Secret Manager-mounted HMAC key; never an env-var literal |

Base44's `SCAN_WORKER_URL` must match the gateway's byte for byte — the
contract suite proves even a trailing slash is rejected loudly.

## Deployment

`scripts/deploy_dispatch_gateway.sh` deploys from this directory with the
same minimal IAM the bootstrap block granted:

- dispatcher SA → `roles/cloudtasks.enqueuer` (project; queue-scoped is the
  tightening follow-up)
- dispatcher SA → `roles/iam.serviceAccountUser` on the invoker SA only
- dispatcher SA → `roles/secretmanager.secretAccessor` on the signing secret only

The service itself runs `--allow-unauthenticated`: the HMAC is the
application-level gate. That makes `SCAN_EVIDENCE_SIGNING_KEY` the sole
credential able to enqueue work, and it is shared with the authority-seal
path — a separate dispatch-only key is a known post-beta follow-up.
