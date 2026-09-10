# Owner-Managed Robots and WAF Design

## Goal

Let a customer self-attest that they own or manage a website before their first Standard 150 scan. Owner-managed scans may ignore `robots.txt` directives for FixList's own crawler only, while all other safety, evidence, admission, persistence, and release boundaries remain unchanged.

## Customer flow

The Standard 150 form asks: **Do you own or manage this website?**

The canonical stored values are:

- `owner_or_manager`
- `not_owner`

The answer is persisted on the owned `BusinessProject`. Browser storage may cache the answer for immediate UI continuity, but it is not authoritative for server admission.

If the answer is `owner_or_manager`, the canonical Standard 150 request carries:

- `respect_robots_txt: false`
- `owner_attested_robots_override: true`

If the answer is `not_owner`, or no durable owner attestation exists, the request carries:

- `respect_robots_txt: true`
- `owner_attested_robots_override: false`

A non-owner may not obtain the robots override merely by modifying browser request fields. `startStandardScanJobV3` must resolve the owned project and derive/validate the policy from `BusinessProject.site_owner_attestation`.

## Robots semantics

The override changes only whether FixList's crawler obeys `robots.txt` disallow directives. It does not change what the site actually declares.

The scanner must preserve two concepts:

1. **Directive evidence** — what `robots.txt` says for FixList and Googlebot.
2. **Applied FixList crawl policy** — whether FixList enforced those directives for this owner-attested run.

Googlebot/indexability evidence always reflects the real directives. An owner override must never make a page look indexable if the site's robots rules block Googlebot.

Use an identifiable FixList user agent. Do not impersonate Googlebot or a browser. Owner-managed scans use conservative concurrency.

## WAF and rate-limit behavior

Owner attestation does not authorize WAF or bot-protection evasion. FixList must not bypass CAPTCHAs, authentication, IP reputation systems, Cloudflare/Akamai/DataDome challenges, private-network protections, or SSRF controls.

Existing bounded retry/backoff behavior for `429` and `503` may be used; do not introduce unbounded retries or increase the Standard 150 page cap.

If structured scan evidence resolves to `access_limited` and the site is owner-managed, the customer presentation should say:

- **Title:** `Your site's security service is blocking FixList.`
- **Next step:** `Temporarily allow FixList in your firewall/bot protection, then Rescan.`

Ownership must change only the presentation of genuine `access_limited` results. Save failures, worker stalls, thin coverage, deadlines, cancellation, and missing results retain their existing explanations.

## Data and authority

`BusinessProject.site_owner_attestation` is the durable source of truth. The browser may persist the answer per normalized domain for pre-submit UX, but server-side admission may not trust browser-only ownership fields.

`ScanRun` must persist the applied robots policy (`respect_robots_txt` and `owner_attested_robots_override`) so retries, Cloud Tasks delivery, history, and authority checks can verify the same policy that was admitted.

Policy fields are part of request identity for a durable attempt. A task whose robots policy disagrees with the stored scan must fail closed as an identity mismatch rather than silently changing policy.

## Scope boundaries

This change is Standard 150 only.

Do not change:

- the 150-page cap;
- robots behavior for non-owners;
- `/en/`, `/fr/`, or other focused path behavior;
- subdomain crawling rules;
- SSRF/private-network protections;
- authentication/WAF bypass behavior;
- authority signing or historical FixList integrity;
- admission concurrency/lease controls;
- Premium 5,000;
- Grok;
- release workflows except where generated release contracts must be refreshed after code changes.

## Testing requirements

Regression coverage must prove:

1. owner-managed project -> server-admitted `respect_robots_txt=false` + explicit owner marker;
2. non-owner/default -> `respect_robots_txt=true`;
3. forged browser override without durable owner attestation is rejected;
4. policy survives Base44 -> gateway -> worker -> persisted result;
5. Googlebot/indexability evidence still reflects actual robots directives during an owner override;
6. owner override does not alter WAF/access-limited classification;
7. owner-specific WAF copy is shown only for `access_limited`;
8. persistence/reload/rescan retain the project answer;
9. current Standard 150 caps, focused-path handling, subdomain behavior, admission, and authority contracts remain green.

## Release gate

No merge or deployment until the reconstructed integration branch is based on current `main`, the diff is reviewed for scope, exact-head FixList CI is green, CodeRabbit review is clean or findings are resolved, exact-main CI is green after merge, and the exact merged SHA is used for Base44 publication and the worker candidate. Production acceptance must include owner-managed scans against previously robots-limited sites plus a WAF-limited site to prove the distinction.