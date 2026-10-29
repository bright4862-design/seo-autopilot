# Extended 500 Lane B: authorization at worker pickup (issue #383)

Status: **IMPLEMENTED and TESTED offline only. Not wired, deployed or enabled.**
Baseline: `002b84c9b6eaef78babec6081df150f31a000b11` (draft PR #377 head).

## Files

- `scanner-api/app/extended500_pickup_authorization.py`: pure decisions plus async gatherers that read through injected ports
- `scanner-api/tests/test_extended500_pickup_authorization.py`: 115 offline cases
- `docs/extended500/lane-b-pickup-auth.md`: this handoff

## Why the 120-second grant is not enough, and what happens when it has expired

The issuer gives the grant a 120 s lifetime (`issuer.js`). The coordinator copies the grant verbatim into the
task body (`service.py` `enqueue()`). The queue is created PAUSED with `--max-concurrent-dispatches=1`
(`provision-queue.sh`). `core.py` says a delayed task "remains executable until a verified exact terminal
release". The README and spec both ask for a fresh read at pickup instead of relying on issuance.

How this lane handles the grant:

- **The grant is used only for integrity.** The signature must verify under the Extended 500 admission key. The shape and the version, audience and mode must match exactly. Every identity field in the task must be equal in both type and value to the signed field.
- **An expired grant is allowed when the fresh reads authorize the scan.** It is reported as `grant_expired` and recorded in the binding as `grant_expired_at_pickup`. This is grounded in the core.py statement above. Rejecting delayed tasks would wedge paid owner slots, because nothing expires a slot lease.
- **Some grants are always refused.** Refused grants include: a tampered or mis-shaped grant, a grant for a different purpose or mode, a grant issued in the future, a window longer than 300 s, and a body older than 31 days. The 31-day limit is Cloud Tasks' maximum task retention. This repository does not verify that limit.
- **The grant is not bound to the receipt time.** An issuer retry after the Cloud Tasks name tombstone expires can legitimately create a newer grant for the same receipt. Binding the two times would refuse that task and wedge the slot.

## Authority order (all fresh, service-owned)

1. **Precheck.** This step makes no reads. The task must have the exact `enqueue()` shape, so a client cannot add a paid flag, plan or access field. The grant is then verified.
2. **ScanRun.** It is read by task `scan_id`, which is the only lookup key the task body supplies. These must match: mode `extended_500`, owner, project, request, idempotency key, `scan_id` and `id`. A newer attempt means **skip `superseded_attempt`**. An attempt ahead of the run is denied. A terminal run is a skip. A `crawling` or `reviewing` run is a skip, because it is a duplicate. Only `queued` is accepted.
3. **Target checks on the ScanRun.** These must match: normalized URL, a public host, `normalized_domain`, the path prefix and the robots pair. A strict `admission_access_id` is required, as in the ScanRun draft.
4. **BusinessProject.** It is read by the ScanRun project id. The owner and the host must match. `subscription_plan` and `status` are customer-writable and never consulted.
5. **Owner User and Access.** The User is read by the ScanRun owner. Access is filtered by owner and by that user's email, the same union `handler.js` uses. Duplicates are removed only when the rows are identical. Two reads that disagree about the same access id produce `access_read_conflict`.
   - Exactly one active, `stripe_checkout`, `extended500_lifetime` row is required, with matching app, email and owner.
   - Each refusal has its own code: revoked, pending, refunded (or a refund marker), owner_test, manual, checkout_pending, Standard 150 only, a duplicate, or another owner's row.
6. **Slot and receipt.** The receipt id, fingerprint and task name are recomputed the same way as `core.py`, with byte-for-byte parity tested.
   - The fingerprint includes the fresh `access.id`, so a replaced Access row is refused.
   - The Cloud Tasks queue and task-name headers must match the receipt.
   - A released receipt is a skip.
   - The slot must point at this receipt, in the same active state.
   - An existing `pickup_claim` is **skip `already_picked_up`**. This covers duplicate deliveries and replays.

Outcomes: `authorized` / `skip` / `deny` / `retry`. Only `retry` should be answered with a 5xx. `execution_enabled` is always `False`.

## Atomic claim and revalidation

- **`decide_extended500_pickup_claim`** is a pure transaction body.
  - It writes an extra `pickup_claim` field to both the slot and the receipt, and leaves `state` unchanged.
  - `core.decide_dispatch_state` and `core.decide_release` copy the whole document forward, so they keep the marker. This is tested. `core.py` needs no change to stay correct.
  - If the same executor retries after an unknown outcome, the call is idempotent.
  - In the tested serialized fake, exactly 1 of 8 concurrent deliveries wins.
- **`claim_extended500_pickup`** treats a port exception, or a result object that the port did not get from `decide`, as `claim_outcome_unknown`. The caller then retries with the same execution id.
- **`revalidate_extended500_pickup`** re-reads every source using keys from the binding. It returns `abort` for:
  - revocation, a refund or a manual regrant
  - a rebound Access row
  - a superseded or terminal run
  - a transferred owner or project
  - a released reservation
  - a lost claim
  It returns `unavailable` on read failure. Only `continue` permits the next side effect.

Recommended worker sequence: authorize, claim, revalidate, crawl, revalidate before every persist step.

## UNVERIFIED (needs real infrastructure)

- **Port adaptors do not exist.** No adaptor yet proves that its reads use the Base44 service role, or that the coordinator reads are live Firestore rather than a cache. The `authority` label is only what the adaptor declares. The gatherer stamps `fetched_at` itself.
- **The User read is unproven.** This design assumes Base44 service-role `User.get(owner_user_id)` returns `email`. That has not been checked.
- **Cloud Run IAM for a future `/scan-job-extended500` route.**
  - The existing `require_cloud_tasks_oidc` does not verify the token signature or audience.
  - It compares the token with `TASKS_INVOKER_SERVICE_ACCOUNT`, the **Standard 150** invoker, and not with `EXTENDED500_INVOKER_SERVICE_ACCOUNT`.
  - The existing `/scan-job-extended500-preflight` route has the same issue.
- **Delivery headers may be forgeable.** It is unverified whether `X-CloudTasks-*` headers can be forged by a caller that gets past IAM.
- **Firestore transactions under contention.** Serializability and retry behaviour for the pickup claim are not proven. Only a lock-serialized fake is tested.
- **Clock skew** between Base44 and the worker. The precheck allows no future skew.

## Remaining blockers

- **Missing reads for the worker:**
  - There is no Base44 function for worker-side service-role reads of BusinessProject, User and Access. Today `read_scan_run` reuses the Standard 150 `durableScanWorkerControlV8` and its key.
  - There is no worker path to the coordinator's Firestore.
- **A denied or refused pickup leaves the owner slot reserved.** Nothing issues a verified terminal release yet, and there is no reconciler for a crashed claimed execution. Pickup never takes over an existing claim.
- **Missing 500 work:** no 500 start/heartbeat write, no route, no crawler integration, and no reviewed persistence.

## Proposed shared-file patches (for the integrator, not applied)

1. `extended500-admission/core.py`: stop re-enqueueing a replay after pickup.

```diff
@@ def decide_reservation(
         if receipt.get("state") not in ACTIVE_STATES:
             raise AdmissionRefused("receipt_state_invalid")
+        if receipt.get("pickup_claim") is not None:
+            return {"outcome": "picked_up_replay", "receipt_id": rid, "task_name": name}
```

   `service.py` `/reserve` would then return 409 `picked_up_replay` without calling `enqueue()`.

2. `scanner-api/app/main.py`: a future route behind a default-OFF flag. It needs a separate invoker check:

```diff
+def require_extended500_tasks_oidc(authorization):
+    # same as require_cloud_tasks_oidc but compares EXTENDED500_INVOKER_SERVICE_ACCOUNT;
+    # still relies on private Cloud Run IAM for signature/audience.
```

   Handler order: OIDC check, then `delivery_from_cloud_tasks_headers`, then `authorize_extended500_pickup`, then a 200 response for skip/deny, a 503 for retry, and a claim only on authorized.

3. Coordinator: keep Firestore access inside the coordinator. Add HMAC- and IAM-protected `/pickup-claim` and `/pickup-status` endpoints that implement `Extended500PickupClaimPort` and the slot/receipt read ports. Do not grant the worker datastore access, because that cannot be scoped to individual collections.

## Rollback

Delete the three files above. Nothing imports the module, and no route, schema, workflow or manifest changed.

## Explicit non-changes

Nothing was deployed or published to Base44, GCP, Stripe or any queue. No payment, customer scan or Standard 150 change was made, and `main` was not touched. Schema/RLS, workflows and fingerprints are unchanged.
