# FixList admission coordinator

A small Cloud Run service that decides **who is allowed to start a Standard 150
scan**, using Cloud Firestore transactions as the single source of truth.

It exists because admission has to be exactly-once across browser tabs, and the
previous design could not guarantee that.

## Why Firestore

Base44 documents `updateMany(query, data)` and reports matched/updated counts,
but it does not document transactional, compare-and-set or linearizable
semantics strong enough to claim one canonical cross-tab admission. Base44
entity ids are also server-managed, so a caller cannot pre-allocate an identity
and use it as a uniqueness key.

Cloud Firestore transactions are explicitly atomic and provide serializable
isolation under contention. The admission decision therefore lives here, and
nowhere else.

`BASE44_ATOMIC_UPDATE_MANY_CONFIRMED` is deliberately **not introduced** by this
service. Nothing here depends on Base44 update atomicity.

## Why a separate Cloud Run service

Base44 functions have no Google Application Default Credentials, and the org
policy `constraints/iam.disableServiceAccountKeyCreation` forbids minting a
service-account key to give them any. This is the same constraint that put
Cloud Tasks dispatch behind a Cloud Run gateway.

This service reuses that proven shape exactly:

```
Base44 function  --(HMAC-signed request)-->  Cloud Run  --(ADC)-->  Firestore
```

No service-account key exists anywhere in the path.

## Authentication

Timestamped two-step HMAC over the **exact raw request bytes**:

```
key       = HMAC-SHA256(signing_root, "fixlist-admission-coordinator-v1")
signature = HMAC-SHA256(key, timestamp + "\n" + raw_body)
```

Headers: `x-fixlist-timestamp`, `x-fixlist-signature`. Clock skew ±300s.

The derivation label differs from the dispatch gateway's
`fixlist-dispatch-gateway-v1`, so a signature minted for one service can never
authenticate against the other even though both hang off the same signing root.
`tests/frontend/scanAdmissionContract.test.mjs` pins that separation, and pins
the JavaScript signer against digests produced by this Python verifier.

`owner_user_id` arrives in the signed body and is trusted, because only Base44
holds the signing root and Base44 authenticates the customer and verifies paid
entitlement before it signs anything. This service authenticates the *caller*,
not the end user, and performs no entitlement logic of its own — duplicating
that check here would create a second place for it to drift.

## Document shape

One document per owner at `scan_admission/{owner_user_id}`, carrying only
bounded coordination metadata:

| Field | Meaning |
| --- | --- |
| `owner_user_id` | Who holds admission |
| `request_id` | The request key that won |
| `request_fingerprint` | `scan_mode\|url`, to detect a reused request key |
| `claim_token` | Capability that authorizes the bind |
| `scan_id` | Canonical Base44 ScanRun entity id, empty until bound |
| `state` | `claimed` → `bound` → `released` |
| `claimed_at` / `lease_expires_at` / `released_at` | Lease bounds |
| `terminal_status` | How the scan ended |

Scan evidence, review output, HMAC authority proofs, payment state and customer
content **never** enter this document. A test asserts the exact key set.

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /health` | Unauthenticated liveness and config echo |
| `POST /claim` | Win, replay, or be told to wait. Creates nothing. |
| `POST /bind` | Attach the canonical server-created ScanRun id to a claim |
| `POST /release` | Free admission once a scan is terminal |
| `POST /status` | Read-only lease view for the watchdog |

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `SCAN_EVIDENCE_SIGNING_KEY` | — | Required; the service refuses to start without it |
| `ADMISSION_COLLECTION` | `scan_admission` | |
| `ADMISSION_LEASE_SECONDS` | `2400` | Clamped to 60–3600; bound scans remain held until explicit terminal release |
| `ADMISSION_MAX_CLOCK_SKEW_SECONDS` | `300` | |
| `ADMISSION_MAX_BODY_BYTES` | `65536` | |
| `FIRESTORE_PROJECT` / `FIRESTORE_DATABASE` | ADC default | |

## Tests

```bash
cd admission-coordinator
python3 -m unittest test_admission          # 28 tests, no dependencies
python3 -m unittest test_coordinator        # 25 tests, needs Flask
```

`test_admission.py` imports only `admission`, which has no third-party
dependencies, so the entire state machine is provable with a stock interpreter
and no Firestore emulator. `test_coordinator.py` stubs Firestore in-process to
cover the HTTP surface, the HMAC boundary and the transaction wiring.

## Not yet done

The service is deployed only through the confirmation-gated release tooling. The one-time owner bootstrap creates the dedicated runtime identity and named Firestore database; routine exact-SHA deploys use `scripts/deploy_admission_coordinator.sh`. `BETA_SCAN_ADMISSION_ENABLED` remains disabled until the deployed coordinator, Base44 function set, worker candidate, watchdog queue and reconciliation backstop have all passed their release gates.
