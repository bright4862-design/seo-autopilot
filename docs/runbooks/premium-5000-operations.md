# Premium 5,000 operations runbook

**Release status: NOT READY TO ENABLE**

This runbook applies only to the isolated Premium 5,000 coordinator and worker. It does not authorize deployment, queue creation, customer traffic, or a third-party crawl.

## Immutable safety controls

- `PREMIUM_5000_ENABLED=false`
- `PREMIUM_5000_KILL_SWITCH=true`
- global active concurrency is exactly `1`
- per-tenant active concurrency is exactly `1`
- queue max concurrent dispatches is exactly `1`
- worker container concurrency is exactly `1`
- Standard 150 routes, cap, image, service and persistence contract remain unchanged
- robots.txt is respected; there is no bypass mode
- no Meilleurtaux or other third-party crawl without explicit later benchmark authorization

A startup mismatch in any immutable control must fail closed before a task is accepted.

## Before any infrastructure review

1. Confirm the branch contains the verified Phase 1 transfer, owner/project isolation correction and durable Slices 1–3.
2. Confirm Premium code is not imported or mounted by the Standard application assembly.
3. Run focused Premium tests, the complete unchanged Standard suite, compilation and secret scanning.
4. Confirm all release identities use immutable Git SHAs and image digests.
5. Confirm the proposed queue and worker use dedicated identities and do not target the Standard service.
6. Confirm no public invoker binding and no primitive Owner/Editor role.

## Emergency kill switch

1. Set `PREMIUM_5000_KILL_SWITCH=true` in the Premium runtime configuration.
2. Pause the dedicated `premium-5000-batches` queue.
3. Leave queued tasks intact; correctness must not depend on deleting them.
4. Verify delivered tasks fail closed against canonical Firestore state.
5. Run the reconciliation query and record affected scan IDs and release identities.
6. Do not alter Standard 150.

## Queue pause and resume

Pause when queue age grows unexpectedly, leases repeatedly expire, cancellation latency exceeds the contract, OIDC verification fails, or any Standard regression appears.

Resume is prohibited until the root cause is documented, the exact candidate passes tests, stale leases are reconciled, and Product plus Security approve. Resuming the queue does not enable customer access.

## Stuck-job recovery

For each nonterminal scan:

1. Load canonical scan, batch, lease, cancellation, deadline and release identity.
2. If the deadline passed, finalize honestly as `timed_out` or `partial` and release controls once.
3. If a lease expired within retry budget, create/reuse the deterministic task and increment attempt transactionally.
4. If retry budget is exhausted, finalize as `failed` or `partial`; never mark complete.
5. If a batch committed but enqueue metadata is missing, enqueue the deterministic next task.
6. If a control document points to a terminal or missing job, repair it only through the guarded reconciliation transaction and emit a high-severity audit event.
7. Never hand-edit counters or terminal state directly in the console.

## Cancellation

Cancellation sets canonical `cancel_requested_at` and increments `state_version`. Workers check cancellation before every fetch and redirect. Already-collected safe evidence may be committed, but no new fetch starts after cancellation. Queue deletion is optional cleanup, never the correctness mechanism.

## Rollback

1. Keep the kill switch on and pause the queue.
2. Restore the last reviewed immutable Premium image digest only.
3. Do not roll back or redeploy Standard 150 as part of a Premium rollback.
4. Verify Firestore schema compatibility before starting any prior worker image.
5. Run reconciliation in dry-run mode, review proposed changes, then execute only approved repairs.
6. Record rollback image digest, Git SHA, reason, affected scans and outcome.

## Security incident

- Pause the Premium queue and keep the kill switch on.
- Revoke the compromised Premium identity or token path without changing Standard identities.
- Preserve tenant-safe logs and immutable evidence hashes.
- Search for OIDC audience/issuer failures, SSRF blocks, cross-owner access attempts and unexpected public IAM bindings.
- Do not return stack traces, raw tokens, page bodies, cookies or authorization headers to clients.

## Standard isolation verification

The release gate fails if Premium changes any Standard handler, 150-page cap, route, UI release path, Cloud Run resource contract, dependency set or persistence behavior. Run the full Standard suite with Premium disabled and simulate Premium repository, queue and worker failures; Standard `/scan` must remain available and unchanged.

## Benchmark ladder (later authorization only)

No benchmark is authorized by this runbook. After deployment, security and recovery gates pass, Product may separately authorize controlled stages: `150 -> 500 -> 1,000 -> 5,000`. Each stage needs explicit target approval, robots compliance, cost/latency evidence, cancellation proof and an honest complete/partial outcome.

## PM coordination template

- Branch and exact SHA:
- Slice delivered:
- Files and hashes:
- Focused tests:
- Full Standard tests:
- Security findings:
- Premium enabled: no
- Kill switch: on
- Infrastructure applied: no
- Third-party crawl: no
- Blockers:
- Next isolated slice:
