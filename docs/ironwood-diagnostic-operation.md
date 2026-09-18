# Isolated Ironwood access diagnostic

This tooling can be merged independently of the crawler identity candidate. It
does not change the release fingerprint, scanner code, Base44 routes or live
traffic. Merging the operator workflow also triggers its existing read-only
release-status job; it does not deploy a worker.

## Operation

Use **FixList Cloud Operator**, branch **main**, after this diagnostic-only PR
passes CI/review and is merged. Do not dispatch from the identity PR branch.

| Input | Value |
|---|---|
| operation | `diagnose-ironwood-access` |
| revision | Exact revision currently serving 100% of the worker traffic |
| confirm | `ironwood-diagnostic:<revision>:<exact-main-SHA>` |
| barrier_generation | `0` (unused by this operation) |
| barrier_prior_mode | `open` (unused; no assertion about live barrier state) |
| change_ticket | `FIXLIST-IRONWOOD-DIAGNOSTIC-20260918` |
| reason | `Bounded isolated Ironwood UA comparison; no live cutover` |

The September 18 baseline revision is `fixlist-standard150-worker-00086-qpm`.
The diagnostic re-reads traffic and refuses if the named revision is no longer
the sole 100% target. Main's exact SHA must be supplied after merge; the PR head
SHA is not a valid replacement. Leave acceptance inputs empty.

## Safety and resources

The existing keyless operator creates one uniquely named Cloud Run job:
`fixlist-ironwood-diag-<workflow-run-id>-<attempt>`. It uses the resolved serving
worker image digest, not a tag, in `seo-autopilot-501517/europe-west1`. It uses
the revision's existing runtime service account but copies **no environment
variables, secrets, volumes or application commands**. It runs a fixed Python
probe through that image's existing DNS-pinned security helper and HTTP client.
The probe never invokes customer scan, admission, authority or persistence APIs.

One task, parallelism one, zero task retries, 180-second task deadline, 1 CPU,
512 MiB. At most seven fixed HTTPS requests to `ironwoodcrecapital.com`: each
UA on root, robots and sitemap, then one production-UA root repeat only if the
first baseline returned unchallenged 200. Requests have a five-second gap and
15-second outer timeout. No redirect or CAPTCHA target is fetched. Cookies are
not replayed; 429 or a network/security refusal stops the matrix. No automatic
job retry occurs; manually re-running a workflow is a new diagnostic and should
not be used to repeatedly hit a blocked site.

Supported worker networking: default egress or an explicit same-project regional
VPC connector with recognized egress mode. Direct VPC interfaces, gen1, sidecars,
volumes, proxies or custom CA env settings cause refusal rather than guessed
equivalence. These cases need separate assessment, not weakened validation.

The script never changes IAM or enables APIs. Missing jobs-create/execute/delete,
service-account-use, revision-read or logging-read permissions are blockers.
The uniquely named job is deleted after execution, including on execution
failure. If creation times out or cleanup fails, report the exact job name from
`profile.json` for operator inspection; do not retry or delete a broad prefix.
Workflow cancellation can interrupt cleanup. Any surviving task still has the
180-second deadline. Job deletion removes execution metadata; sanitized evidence
is retained in the workflow artifact for seven days, and Cloud Logging follows
the project's existing retention policy.

## Evidence and limits

The artifact contains `profile.json`, `observations.json` and `result.json` when
those stages complete. It records the worker digest/source, diagnostic source,
runtime versions and code hashes, UTC/request order, each UA, status, allowlisted
headers, decoded byte length, challenge classification and redacted redirect/
meta-refresh destination. No response bodies, cookies, tokens, query strings or
production secret values are retained. An absent completion row is a failed
diagnostic, not evidence that a site is accessible.

This is a **separate Cloud Run job**, not the live worker process. Shared image
and network configuration do not prove the same outbound IP. Source-IP
equivalence remains explicitly false/unverified; provider request logs are
needed to distinguish reputation/policy from UA effects confidently. There is
no IP-echo request to an additional domain. The test deliberately controls cadence
and cookies, so it does not reproduce the full production scan's request history.

A green workflow means the diagnostic completed and its evidence was collected;
it does not mean Ironwood passed a scan or authorize promotion. Both profiles can
be challenged and still produce a valid diagnostic. Inspect the results before
deciding whether any identity change is justified. RATP/Winamax/Viator and GEO
remain outside this operation.

Cloud Run job flags follow Google's [create](https://cloud.google.com/sdk/gcloud/reference/run/jobs/create)
and [execute](https://cloud.google.com/sdk/gcloud/reference/run/jobs/execute) interfaces.
