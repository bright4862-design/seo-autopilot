# FixList owner-authorized crawler compatibility research

Date: 2026-09-13

Status: research only. No production integration, deployment, request-profile change, traffic shift, or scanner activation is authorized by this document.

## Objective

Create a compatibility path for customer-owned websites that limit the current identifiable FixList Python crawler, while preserving the Standard 150 safety contract: robots policy, SSRF/public-IP validation, same-origin boundaries, crawl limits, authority integrity, historical ScanRun correctness, and truthful limited/failure states.

The preferred outcome is not generic anti-bot evasion. It is an identifiable FixList crawler that a verified owner can deliberately permit through their security stack.

## Current coordination boundary

Codex owns the isolated first-hop observer on `codex/access-observer-20260913`. The Astra research branch must not duplicate `access_diagnostics.py`, its scanner/security observation seams, their tests, or the research probe.

Until that observer reports exact first-hop evidence, Ironwood CRE Capital and the other real-site matrix rows remain root-cause unproven.

## Recommended compatibility hierarchy

1. **Standard identifiable crawler** — current FixList identity and transport remain the default.
2. **Owner-side exception** — when a site's security product supports a narrow exception, the owner allows authenticated/identifiable FixList traffic without weakening unrelated protections.
3. **Verified crawler identity** — pursue provider-supported bot verification, preferably cryptographic verification rather than user-agent-only trust.
4. **Static egress allowlisting** — use only if FixList can publish a stable, limited scanner IP set and the owner's WAF supports IP-based exceptions.
5. **Fail clearly** — if the site cannot safely permit the crawler, return a truthful access-limited state rather than impersonating a browser or fabricating coverage.

## Cloudflare findings

### Bot Fight Mode

Cloudflare documents that Bot Fight Mode runs outside the Ruleset Engine and cannot be skipped by WAF custom `Skip`, `Bypass`, or `Allow` rules. Cloudflare recommends Super Bot Fight Mode when a customer needs configurable exceptions.

Source:
- https://developers.cloudflare.com/bots/get-started/bot-fight-mode/
- https://developers.cloudflare.com/waf/custom-rules/skip/

Implication for FixList: do not promise a generic custom-rule bypass for customers on Bot Fight Mode. The product should identify the protection layer first and give plan/capability-aware guidance.

### Super Bot Fight Mode and WAF managed rules

Cloudflare documents that custom `Skip` rules can bypass selected Ruleset Engine phases, including Super Bot Fight Mode, rate limiting, and Managed Rules. A FixList owner exception should therefore be narrow: exact FixList identity evidence, only the required security phase(s), and only the customer's scan target where possible.

Source:
- https://developers.cloudflare.com/waf/custom-rules/skip/options/
- https://developers.cloudflare.com/bots/get-started/super-bot-fight-mode/

### Verified Bots and Web Bot Auth

Cloudflare's current Verified Bots requirements favor deterministic, honest identity. Supported verification approaches include Web Bot Auth request signatures, a published stable IP list plus stable user agent, or reverse DNS. Cloudflare's Web Bot Auth flow uses Ed25519 request signing and a public key directory.

Source:
- https://developers.cloudflare.com/bots/concepts/bot/verified-bots/
- https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/
- https://developers.cloudflare.com/bots/reference/bot-verification/ip-validation/

Long-term recommendation: evaluate Web Bot Auth for FixList before adopting user-agent impersonation or a broad allowlist. It preserves a stable `FixListPythonScanner` identity while giving Cloudflare a cryptographic signal that the request actually came from FixList.

## AWS WAF findings

AWS WAF Bot Control marks common verifiable bots as verified. AWS documents an explicit allow rule that matches its verified-bot label after the Bot Control managed rule group. AWS WAF also supports reusable IP sets for owner-managed rules.

Source:
- https://docs.aws.amazon.com/waf/latest/developerguide/waf-bot-control-example-allow-verified-bots.html
- https://docs.aws.amazon.com/waf/latest/developerguide/waf-ip-set-managing.html

Implication for FixList: before FixList has provider-level verified-bot status, IP-based owner allowlisting is plausible only if FixList can publish stable egress addresses. User-agent alone is not a strong authentication boundary.

## Stable Cloud Run egress dependency

Google Cloud documents that Cloud Run uses a dynamic outbound IP pool by default. To provide static outbound addresses, route all service egress through a VPC using Direct VPC egress (recommended) or a Serverless VPC Access connector, then through Cloud NAT configured with reserved static IP address(es).

Source:
- https://docs.cloud.google.com/run/docs/configuring/static-outbound-ip

This must **not** be retrofitted onto the restored production worker as an experiment. If stable egress is pursued, first build it as a separate zero-traffic compatibility service or isolated research service and prove:

- existing SSRF/public-IP validation is unchanged;
- DNS pinning and redirect validation are unchanged;
- response bodies and evidence are identical on normal control sites;
- the new network path does not change timeouts, retries, or page caps;
- the static egress addresses are dedicated to FixList scanner traffic and can be published safely;
- rollback requires no production worker mutation.

## Proposed future identity package

A production-grade identifiable FixList crawler should eventually publish:

- stable user agent and product name;
- public crawler-information page;
- contact/security address;
- robots/crawl-rate commitments;
- verification method (prefer Web Bot Auth if accepted by target providers);
- if needed, a small stable egress IP list with change policy;
- explicit owner instructions for narrow WAF exceptions.

None of those items authorizes changing the current crawler transport yet.

## Evidence required before compatibility transport work

For each blocked real site, the observer should establish enough evidence to distinguish at least:

- robots restriction;
- HTTP 401/403/407 access denial;
- HTTP 429 rate limiting;
- TCP connect failure;
- TLS handshake failure;
- response timeout;
- challenge/WAF response evidence;
- identity-sensitive outcome from a controlled comparison;
- unknown/inconclusive failure.

`crawler_identity_sensitive` must remain unavailable unless robots are confirmed allowed for the exact request, the FixList request is actually denied, and the controlled comparison succeeds.

## Explicit non-goals

Do not build or recommend as the default path:

- browser impersonation;
- CAPTCHA solving or challenge bypass;
- rotating residential/datacenter proxies;
- stealth TLS fingerprint evasion;
- ignoring robots.txt without the existing authorized policy;
- raising crawl caps or concurrency to force access;
- weakening SSRF, redirect, authority, persistence, or historical-result boundaries.

## Next gates

1. Codex publishes the observer slice and exact normalized fields.
2. Review observer semantics against `access_compatibility_policy.py` and the frozen matrix.
3. Populate Ironwood plus controls with exact observer evidence; do not infer missing stages from saved counters.
4. Decide whether the dominant blocker class needs owner-side WAF instructions, stable egress, provider verification, or no transport change at all.
5. Only after explicit approval: build the smallest compatibility candidate on a separate service/flag, then run blocked and normal control matrices.
