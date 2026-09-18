# Transparent crawler identity candidate

## Scope and production baseline

Production handoff: source `b5bce85967d23ddc97654e613eab9644a539f480`,
fingerprint `9e4901da590017e1`, worker `00086-qpm`, rollback `00083-9h7`.
These are handoff values, not permission to skip fresh checks before deployment.
Ironwood scan `6aad8e93889fea01729a2b32` failed with `scan_access_limited`;
no authoritative FixList was saved. That failure behavior is correct.

Candidate fingerprint: `46cda16461fb1e1d`. This candidate is NOT accepted.
It changes the HTTP identity to `FixListBot/1.0 (+https://getfixlist.com/crawler)`
and provides the associated public information page. Both the new robots token
and the legacy scanner token must permit a request by default. This deliberately
retains legacy restrictions, including wildcard restrictions selected for that
token. Owner-attested override and Googlebot indexability checks are unchanged.

No GEO module, V7 routes, rendering, proxy, TLS, connection, concurrency,
authority, page-cap, or challenge-solving changes are included. Generated
release contracts/build IDs propagate the new fingerprint through existing V6
routes; historical valid production results remain readable under their seals.

## Evidence and limits

Earlier sequential Base44 sandbox observations showed the old UA receiving 403
responses (75,193 bytes) on root, robots and sitemap. The transparent candidate
received root 200 (120,253 bytes), robots 200 (123 bytes), and a sitemap redirect
to `/wp-sitemap.xml`. curl and Node showed the same direction of difference.
These are summarized diagnostic observations, not retained raw response fixtures.
The source IP was not verified constant across the comparisons. They support
testing a UA hypothesis; they do not isolate the production trigger.

A separate local proxy-backed observation challenged both UAs with HTTP 202,
`sg-captcha: challenge`, and a SiteGround CAPTCHA meta refresh. That environment
is not the GCP worker and must not be represented as GCP or residential evidence.
Raw production response headers were not retained on the failed ScanRun.

Consequently IP reputation, UA, headers, TLS/client behavior, cadence and
site-specific policy remain competing or interacting causes. No improvement
for RATP, Winamax, Viator or other vendors has been established.

## Required controlled comparison

Run only through an authorized diagnostic execution path. Record the exact
image/source, runtime, HTTP library version, network configuration and UTC time.
A Cloud Shell request is not proof of Cloud Run worker egress equivalence.
Use provider request logs or another approved source measurement to verify
whether the compared requests actually share a source IP. Do not extract
service credentials or change IAM, traffic, admission or the queue to run this.

1. Start with the actual production HTTP client and security path: DNS pinning,
   Host/SNI behavior, redirect validation and bounded response handling intact.
2. Use one request at a time with a fixed gentle gap. Compare root `/`,
   `/robots.txt`, and `/sitemap.xml`, changing only the User-Agent between the
   production string and the candidate string. Record the order; repeat the root
   baseline after the comparison to detect time-dependent blocking.
3. Record status, safe response headers (`sg-captcha`, `cf-mitigated`, `server`,
   `x-robots-tag`, `location`, `content-type`, `retry-after`), response byte count,
   challenge classification, and redirect/meta-refresh target without following
   a CAPTCHA route. Do not log cookies, tokens or unrelated account data.
4. Stop on explicit rate limiting; do not retry into challenges. A blocked
   profile is a completed diagnostic observation, not a reason to evade it.
5. Compare the same profiles on a consenting operator's ordinary desktop network
   if available. Do not use residential proxies or impersonate a browser/bot.
6. Test alternate ordinary headers or clients only as separately recorded
   one-variable experiments if the first comparison leaves the cause unclear.

Successful HTML must pass the existing evidence gate. A status 200, redirected
SPA shell, or apparent browser success is not enough to accept a scan.

## Release gates

- Fresh local regression suites and exact-SHA GitHub CI, including image build.
- Review completed; no unresolved material review issues.
- Actual worker-network comparison, with confounders explicitly recorded.
- Public crawler page checked after publication, not merely an HTTP 200 probe.
- Exact Base44 and worker source alignment, controlled authoritative acceptance,
  old-result reads and access-limited failures verified before normal promotion.

The current operator is restricted to exact main and has no generic crawl-probe
operation. Do not relax those controls or merge solely to obtain credentials.
If an authorized equivalent diagnostic environment is unavailable, keep the PR
unmerged and request GCP diagnostic access/direction from the owner.
