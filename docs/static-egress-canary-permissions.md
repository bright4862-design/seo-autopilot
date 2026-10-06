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

Compute writes wait with `{global,region}Operations.wait` and then GET the
resource. The subnet's network reference also requires
[`compute.networks.updatePolicy`](https://docs.cloud.google.com/compute/docs/reference/rest/v1/subnetworks/insert).
These admin permissions are never added to the verifier role.

| Step | Command (script) | Principal | Permissions |
|---|---|---|---|
| Provision | `networks describe/create` | admin | `compute.networks.get`, `compute.networks.create`, `compute.globalOperations.get` |
| | `networks subnets describe/create` | admin | `compute.subnetworks.get`, `compute.subnetworks.create`, `compute.networks.updatePolicy`, `compute.regionOperations.get` |
| | `addresses describe/create` (external, Premium) | admin | `compute.addresses.get`, `compute.addresses.create`, `compute.regionOperations.get` |
| | `routers describe/create` | admin | `compute.routers.get`, `compute.routers.create`, `compute.regionOperations.get` |
| | `routers nats describe/create` (`routers.get` then `routers.patch`) | admin | `compute.routers.get`, `compute.routers.update`, `compute.regionOperations.get` |
| Verify infra | `verify-fixlist-static-egress-canary.sh` | operator | `compute.networks.get`, `compute.subnetworks.get`, `compute.addresses.get`, `compute.routers.get` |
| Stage 0% worker | `build-worker-candidate.sh` | operator | the four reads above, plus the unchanged normal staging set already exercised by run `34876301221`: `run.services.get`, `run.revisions.list/get`, `cloudbuild.builds.create`, source upload, `iam.serviceAccounts.get/actAs` on the build SA |
| | Cloud Build `run deploy --no-traffic --network --subnet` | build SA | `run.services.get/update` on the worker, `iam.serviceAccounts.actAs` on the worker runtime SA |
| | Direct VPC attachment | Cloud Run service agent | same-project subnet use, from its default `roles/run.serviceAgent` |
| Verify outbound IP | `verify-fixlist-static-egress-source-ip.sh` | operator | the four reads; `run.revisions.list/get`, `run.services.get`, `run.jobs.create`, `iam.serviceAccounts.actAs` on the worker runtime SA, `run.jobs.get`, `run.jobs.run`, `run.executions.get`, `logging.logEntries.list` |
| Delete probe job | `run jobs delete` | operator | `run.jobs.delete` |

The human bootstrap additionally needs `serviceusage.services.enable`,
`iam.roles.get/create/update`, `resourcemanager.projects.getIamPolicy/setIamPolicy`,
and permission to read project ancestry. For projects under folders or an
organization, it must read every parent's policy with
`resourcemanager.folders.getIamPolicy` / `resourcemanager.organizations.getIamPolicy`.
An unreadable policy stops the bootstrap before any cloud write; do not broaden
the WIF operator to satisfy this administrator-only preflight.

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
the bootstrap refuses direct grants of those roles on the project, any parent
folder, or its organization, including conditional grants and grants to public
principals. It reads complete policies rather than relying on filtered output.
Group membership and permissions in other pre-existing custom roles require
the administrator's effective-access audit; this preflight does not claim to
resolve group membership or certify every existing grant.

The owner `/provision-static-egress-canary <sha>` command retains its spelling
but invokes only the read-only verifier. Missing resources or denied reads stop
it immediately; it has no create fallback. Only the human bootstrap invokes the
provisioner, whose project, region, resource names and CIDR are fixed.

## Runbook

1. Merge the bootstrap change. In an authorized Cloud Shell, as the existing
   project owner, on a clean checkout of the new `main`. Review the operator's
   effective access, including group membership and existing custom roles,
   first. Use the normal human shell: `GITHUB_ACTIONS=true` is refused so local
   environment variables cannot select the CI source-guard shortcut.

   ```bash
   git checkout main && git pull --ff-only
   SHA="$(git rev-parse HEAD)"
   SOURCE_SHA="$SHA" CONFIRM="BOOTSTRAP-STATIC-EGRESS-CANARY:$SHA" \
     bash scripts/bootstrap-fixlist-static-egress-canary.sh
   ```

   Expect `STATIC_EGRESS_CANARY_READY=1`, `STATIC_EGRESS_IP=<reserved IPv4>` and
   `STATIC_EGRESS_BOOTSTRAP_COMPLETE`.
2. Re-verify the infrastructure under WIF with an owner comment on a PR:
   `/provision-static-egress-canary <current-main-sha>`. A failed describe stops
   verification. Check that the canary exists and the `fixlistStaticEgressVerifier`
   binding has propagated. Do not grant create rights or retry provisioning
   through CI.
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

## Failure and rollback boundary

A failed admin bootstrap can leave the read-only binding or some isolated
canary resources in place. It does not automatically delete resources or undo
IAM. Inspect partial state and rerun the exact-main bootstrap after resolving
the failure, or have the authorized administrator remove only the canary
resources and verifier binding after checking for attached workloads. Keep the
candidate at 0%; ordinary promotion refuses static-egress/Direct-VPC revisions.
No production worker, queue or admission rollback is needed for this bootstrap.
