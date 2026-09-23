# Cloud Run crawler access checkpoint

The owner reported sites blocking the Python worker on Cloud Run. The available evidence does not isolate a single cause. Hosting IP reputation, request cadence and a site's crawler policy are distinct possibilities. Changing language or hosting alone is not a demonstrated fix.

## Confirmed code defect and correction

The initial landing-page rate-limit recovery used a fixed 30-second wait without reading `Retry-After`, and only recognized Cloudflare. The correction recognizes any initial HTTP 429 in the existing durable full-site landing path, parses seconds and HTTP dates using the existing parser, and waits at least the normal cooldown or the site's longer requested wait. If that wait cannot fit the remaining crawl budget, it retains the 429 and stops without retrying or discovering sitemaps. No deadline, retry count, crawl cap or authority gate is expanded.

Regression cases cover Cloudflare, nginx and absent server headers; numeric/date instructions, malformed fallback and waits beyond the budget. Existing later-page adaptive backoff remains intact. This correction does not add a new landing request to focused scans or a global pacer across discovery, redirects and probes.

## Practical access path

1. For one affected scan, inspect retained status, challenge vendor/kind, pressure counters and `Retry-After`. Ask the site owner to match the exact UTC request, path and source IP in their firewall logs. A challenge page with status 200/202 is still unusable evidence.
2. Inspect live Cloud Run egress settings before changing infrastructure. Google documents dynamic outbound addresses by default and stable egress through Direct VPC egress plus Cloud NAT with a reserved address. Route all outbound traffic through the configured VPC/NAT for this to cover the crawler. The repository deployment files alone do not prove the live network configuration.
3. Publish a transparent crawler identity, purpose and actual stable IP list. The existing transparent identity proposal in PR #298 remains unmerged; do not import its obsolete generated V6 release changes. Current scanner identity is `FixListPythonScanner/1.0` inside its compatibility User-Agent string.
4. Have the website owner allow the identified crawler narrowly in their own firewall policy. Prefer a scoped rule over a broad IP allowance that disables unrelated protections. Confirm successful HTML access with a small bounded scan before retrying Standard 150.
5. Use measured site-specific request spacing and lower concurrent requests when logs show rate pressure. The current page worker starts with concurrency eight and adapts after pressure; a shared proactive host pacer across discovery/probes is separate work requiring deadline and coverage tests.

A stable IP enables identification and allowlisting; it does not guarantee admission. Browser rendering may recover JavaScript content after access is permitted, but is not a firewall or CAPTCHA solution. Preserve access-limited outcomes when a site does not allow the crawler. No proxy rotation, browser/Googlebot impersonation, CAPTCHA bypass or robots-policy weakening is part of this work.

## Current operational limits

No live networking change or paid resource has been created. Existing production worker `fixlist-standard150-worker-00095-sn2` is unchanged. The source fix needs the ordinary exact-source worker staging and acceptance gates before it becomes live. No claim is made that blocked sites have recovered.

Official references reviewed 2026-09-23:

- https://docs.cloud.google.com/run/docs/configuring/static-outbound-ip
- https://developers.cloudflare.com/bots/concepts/bot/verified-bots/
- https://developers.cloudflare.com/bots/reference/bot-verification/ip-validation/
- https://developers.cloudflare.com/waf/tools/ip-access-rules/
