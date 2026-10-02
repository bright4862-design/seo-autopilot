# Static-egress canary: permissions and one-time bootstrap

Owner-only path for the Standard 150 one-IP static-egress canary:
`provision → verify infra → stage 0% worker → verify outbound IP → controlled website tests`.

## Why `/provision-static-egress-canary` failed

Run `36479649259` (job `109121865442`) on exact main
`02d74644bbe71a46285981bfbff27fe3a1dbee47` authenticated through WIF as
`fixlist-github-operator`. It failed at the first mutation:

```
Required 'compute.networks.create' permission for
'projects/seo-autopilot-501517/global/networks/fixlist-scanner-egress'
```

No repository bootstrap grants that identity any `compute.*` permission. Its
roles are Cloud Run, Cloud Build, Cloud Tasks and narrow IAM bindings (see
`bootstrap-fixlist-cloud-operator-wif.sh`, `bootstrap-fixlist-dispatch-gateway.sh`
and `bootstrap-fixlist-admission-coordinator.sh`). The provisioner's preceding
`networks describe ... || create` cannot tell "not found" from "forbidden", so
the first visible error was the create. Nothing was created.

## Principals

| Principal | Acts in |
|---|---|
| `fixlist-github-operator@…` (WIF) | every owner-comment workflow job |
| `919035207432-compute@developer.gserviceaccount.com` | Cloud Build steps, including `gcloud run deploy` of the 0% revision |
| `fixlist-standard150-worker@…` | runtime identity of the worker and the probe job |
| Cloud Run service agent `service-919035207432@serverless-robot-prod…` | attaches Direct VPC interfaces to the subnet |

## Minimum permissions, per command actually executed

API methods were read from the installed gcloud SDK. Compute writes wait with
`{global,region}Operations.wait` and then GET the resource.

| Step | Command (script) | Principal | Permissions |
|---|---|---|---|
| Provision | `networks describe/create` | admin | `compute.networks.get`, `compute.networks.create`, `compute.globalOperations.get` |
| | `networks subnets describe/create` | admin | `compute.subnetworks.get`, `compute.subnetworks.create`, `compute.regionOperations.get` |
| | `addresses describe/create` (external, Premium) | admin | `compute.addresses.get`, `compute.addresses.create`, `compute.regionOperations.get` |
| | `routers describe/create` | admin | `compute.routers.get`, `compute.routers.create`, `compute.regionOperations.get` |
| | `routers nats describe/create` (`routers.get` then `routers.patch`) | admin | `compute.routers.get`, `compute.routers.update`, `compute.regionOperations.get` |
| Verify infra | `verify-fixlist-static-egress-canary.sh` | operator | `compute.networks.get`, `compute.subnetworks.get`, `compute.addresses.get`, `compute.routers.get` |
| Stage 0% worker | `build-worker-candidate.sh` | operator | the four reads above, plus the unchanged normal staging set already exercised by run `34876301221`: `run.services.get`, `run.revisions.list/get`, `cloudbuild.builds.create`, source upload, `iam.serviceAccounts.get/actAs` on the build SA |
| | Cloud Build `run deploy --no-traffic --network --subnet` | build SA | `run.services.get/update` on the worker, `iam.serviceAccounts.actAs` on the worker runtime SA |
| | Direct VPC attachment | Cloud Run service agent | same-project subnet use, from its default `roles/run.serviceAgent` |
| Verify outbound IP | `verify-fixlist-static-egress-source-ip.sh` | operator | the four reads; `run.revisions.list/get`, `run.services.get`, `run.jobs.create`, `iam.serviceAccounts.actAs` on the worker runtime SA, `run.jobs.get`, `run.jobs.run`, `run.executions.get`, `logging.logEntries.list` |
| Delete probe job | `run jobs delete` | operator | `run.jobs.delete` |

Already proven for `fixlist-github-operator` in production:

- 0% staging (Cloud Build, deploy, revision reads): run `34876301221`
  staged `fixlist-standard150-worker-00079-pp2`.
- Cloud Run Job create, execute `--wait`, exact-execution log read and delete
  with the worker runtime SA: Ironwood diagnostic run `35397753613`.
- Cloud Logging reads: read-only diagnostic in run `36478701624`.

Not yet held: the four `compute.*.get` reads. Not yet proven: Direct VPC
attachment by the service agent. That attachment is first exercised at 0%
staging, where a failure leaves no customer impact.

## Decision: one-time admin provisioning, read-only operator

| | Custom create role on the operator | Admin provisions once (chosen) |
|---|---|---|
| New standing operator rights | create networks, subnets, external IPs and routers, and update **every** router/NAT in the project | four metadata `get` permissions |
| Scoping | networks, addresses and routers have no resource-level IAM, so project-wide | same, read-only |
| Human action still required | yes, to create and grant the role | yes, to run one script |
| Completeness provable before use | no: create-time checks on referenced resources cannot be confirmed without trial runs | yes: an existing admin already holds them |

Either path needs a human admin once, so giving the CI identity permanent
network-mutation rights for a one-time action adds risk and saves nothing. The
operator does not receive Owner, Editor, Compute Admin or Network Admin, and
the bootstrap refuses to run if it already holds one of them.

Once the resources exist, the provisioner's guarded creates are skipped. The
owner `/provision-static-egress-canary <sha>` command then performs only
describes and verification, so it becomes a WIF re-verification.

## Runbook

1. Merge the bootstrap change. In an authorized Cloud Shell, as the existing
   project owner, on a clean checkout of the new `main`:

   ```bash
   git checkout main && git pull --ff-only
   SHA="$(git rev-parse HEAD)"
   SOURCE_SHA="$SHA" CONFIRM="BOOTSTRAP-STATIC-EGRESS-CANARY:$SHA" \
     bash scripts/bootstrap-fixlist-static-egress-canary.sh
   ```

   Expect `STATIC_EGRESS_CANARY_READY=1`, `STATIC_EGRESS_IP=<reserved IPv4>` and
   `STATIC_EGRESS_BOOTSTRAP_COMPLETE`.
2. Re-verify the infrastructure under WIF with an owner comment on a PR:
   `/provision-static-egress-canary <current-main-sha>`. If this again reports
   `compute.networks.create`, the operator's read grant is missing or has not
   propagated yet. The describe failed with 403 and the provisioner fell through
   to create. Check the `fixlistStaticEgressVerifier` binding. Do not grant
   create rights.
3. `/stage-static-egress-worker <current-main-sha>`. This passes when the status
   `fixlist/static-egress-candidate-stage` is `success`, the revision has 0% traffic,
   and the network, subnet and `all-traffic` annotations are present.
4. `/verify-static-egress-source-ip <current-main-sha>`. This passes when the status
   `fixlist/static-egress-source-ip` is `success` and the observed IP equals the
   reserved IP. The temporary job is deleted.
5. Controlled website tests need a separately reviewed, owner-only path that
   targets the 0% revision. Ordinary promotion still refuses Direct VPC
   candidates, and no such path exists yet.

Every command binds to the current `main` SHA. If `main` moves, use the new SHA.
