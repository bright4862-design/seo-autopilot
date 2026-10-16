# Controlled static-egress access comparisons

This owner-only operation compares one fixed website through two isolated Cloud
Run jobs. Both jobs use the same immutable Standard 150 candidate image, runtime
service account, CPU, memory, scanner user agent and diagnostic settings. The
treatment difference is default networking versus the fixed Direct VPC
all-traffic network and its one reserved NAT IP. Each job proves its source IP
before requesting the website; the static profile must match the reserved IP.

This is a controlled scanner diagnostic. It does not invoke the durable customer
route, create a ScanRun, persist findings, change admission or queues, or move
production traffic. A completed pair does not establish better access, a finished
customer scan, or permission to promote the candidate.

## Source and candidate prerequisites

The comparison source must be independently reviewed and merged through the
normal repository process. Preparing this operation does not authorize merging
it. After a merge, stage a new static candidate from that exact current main SHA;
the previously staged candidate has a different source identity and cannot be
used by this gate.

1. Verify the fixed infrastructure through the existing read-only owner command
   `/provision-static-egress-canary <40-character-current-main-sha>`.
2. Stage that exact source with
   `/stage-static-egress-worker <40-character-current-main-sha>`.
3. Verify the staged candidate's source IP with
   `/verify-static-egress-source-ip <40-character-current-main-sha>`.
4. Check the candidate is Ready, private, bound to the fixed Direct VPC network,
   and allocated 0% traffic. The original serving allocation must remain stable.

All operations are fixed to project `seo-autopilot-501517`, region
`europe-west1`, and service `fixlist-standard150-worker`. Comparison jobs use the
existing GitHub WIF operator without new IAM grants or service-account keys.
Neither temporary job receives production environment values or secrets.

## One exact owner command per pair

On a repository pull request, `bright4862-design` posts the complete command:

```text
/compare-static-egress-access <40-character-current-main-sha> <alias>
```

Only the seven aliases below are accepted. Each names one exact canonical HTTPS
origin. A caller cannot supply a URL, change the user agent, enable a robots
override, choose resources, or add job flags.

| Alias | Fixed target |
| --- | --- |
| `winamax` | `https://www.winamax.fr/` |
| `ratp` | `https://www.ratp.fr/` |
| `viator` | `https://www.viator.com/` |
| `klook` | `https://www.klook.com/` |
| `fever` | `https://feverup.com/` |
| `ironwood` | `https://ironwoodcrecapital.com/` |
| `funbooker` | `https://www.funbooker.com/` |

The command must exactly match the owner, event SHA and checked-out main. The
workflow refreshes the explicit main ref and requires a clean checkout before
cloud authentication. Superseded queued events fail. It resolves a Ready 0%
static candidate carrying the same source SHA and passes its exact revision to
the comparison runner. The runner independently validates identity, image,
networking, runtime and serving allocation before cloud writes.

Each command runs the default and static profile sequentially for one site. Wait
for the pair and required cleanup before the next target. Seven completed pairs,
including the Funbooker control, are required to populate the matrix. Keep the
same source SHA and candidate revision across the matrix; if source or candidate
changes, the previous pairs belong to a different comparison.

## Request boundaries

The injected diagnostic invokes the image's `app.scanner.run_scan` with the
durable route's `scan_mode="advanced"`, `job_mode=True` and timeout argument 210.
The scanner's existing async ceiling clamps that argument to 120 seconds, and
the diagnostic retains the durable route's 135-second outer crawl fuse. The
150-page cap, scanner extraction and existing evidence classifications remain
in force. Browser rendering and post-crawl customer persistence are absent.

A process-local guard tightens the scanner's request boundary without modifying
production scanner modules. Every HTTP hop—including the native landing fetch,
robots reloads, sitemap roots and children, redirects, canonical validation and
coverage probes—must remain on the one fixed canonical origin. Other origins,
including apex/www aliases, are refused. An origin redirect can therefore make
a pair inconclusive even when a normal customer scan could follow it.

Robots permission must be known and explicitly allow the request. Missing robots
files retain the scanner's normal 404/410 behavior; unavailable or access-limited
robots fail closed. Explicit Disallow rules are enforced, owner overrides are
disabled, and later policy reloads cannot reopen unknown or forbidden requests.
The guard keeps the original public-DNS pinning, TLS verification, bounded
decoded-body reader and redirect limits. Proxy inheritance and custom certificate
configuration are refused.

The guard serializes HTTP hops, applies at least a 0.5-second interval plus any
larger parsed robots Crawl-delay or Request-rate, and bounds total hops at 200.
A 429 or Retry-After response stops further website requests for that profile;
the required wait is not shortened to obtain another result. The whole probe has
a 190-second fuse inside a 210-second single-task job with zero retries. These
extra restrictions can reduce coverage and are identical across both profiles.

## Evidence, cleanup and interpretation

The runner creates unique temporary jobs and never replaces or reuses an
existing job. It validates actual job configuration, binds log reads to the exact
job and execution, checks serving allocation before and after each job, and
requires verified deletion. Job creation or execution is not automatically
retried. If creation has an ambiguous outcome, cleanup requires proof that this
invocation owns the job. Preserve a failure and investigate its named resources
before a fresh command; do not turn an uncertain run into a success by retrying.

Only `/tmp/fixlist-static-egress-comparison.json` is uploaded as the sanitized
artifact. It contains fixed identities and bounded aggregate observations, such
as source IP, robots state, usable HTML, access limits, request counts and
cleanup results. Raw page bodies, fetched URLs, headers, cookies, tokens,
production records and arbitrary cloud error output must not be published.

The status context is `fixlist/static-egress-comparison-<alias>`. Success means
the pair diagnostic and its required cleanup completed. It does not mean the
static IP improved access. Robots denial or unknown policy is legitimate
diagnostic evidence, never permission to bypass the policy. Missing evidence,
source-IP mismatch, uncertain cleanup or concurrent traffic movement blocks a
completion claim.

Review the seven paired artifacts together. Compare usable HTML and verified
access-limit evidence with request counts, timeouts, robots decisions and the
Funbooker control. A single pass remains sensitive to timing and server policy
changes. Do not infer durable access or customer acceptance from aggregate
counts. Any production adoption requires a separate accepted-egress promotion
decision; the ordinary worker promotion path remains closed to Direct VPC/static
candidates.
