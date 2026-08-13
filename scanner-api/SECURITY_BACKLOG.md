# Security backlog — scanner-api

Tracked hardening items. Turn each into a GitHub issue when ready.

---

## SSRF: pin validated IP + Host header to close DNS-rebinding window

**Status:** CLOSED — implemented in `app/security.py`, covered by `tests/test_security_dns_pinning.py` and `tests/frontend/scannerSsrfGuard.test.mjs`.

### Original finding (historical)

The Python scanner resolved a host during `is_public_http_url()`, validated that
all resolved IPs were public, then httpx resolved again during the fetch. That
left a DNS-rebinding / TOCTOU window where a hostile DNS server could return a
public IP during validation and a private/link-local IP during the actual fetch.

Before accepting arbitrary public URLs at scale, `safe_get()` had to:

- resolve the hostname once
- validate the chosen IP
- connect to the validated IP
- send the original `Host` header
- preserve HTTPS/SNI considerations
- revalidate every redirect hop the same way

### Resolution

Every required change shipped. `resolve_public_http_url()` performs one
`getaddrinfo` snapshot and rejects the whole hop unless **every** answer is
public, so a private address cannot hide among public A/AAAA records. The socket
connects to `connect_url` (the validated numeric IP) while the `Host` header and
TLS SNI keep the original hostname, so certificate verification still runs
against the requested public host. `Connection: close` prevents a numeric-IP
pool from being reused across virtual hosts. `safe_get()` walks redirects itself
with `follow_redirects=False` on the client and re-resolves and re-validates
every hop, bounded by `DEFAULT_MAX_REDIRECTS`. `_is_public_ip()` keeps an
explicit deny list beyond `is_global`, which has historically classified
multicast as global.

Every crawl-path module — `scanner`, `sitemap`, `robots_policy`,
`trust_discovery`, `canonical_validation`, `redirect_validation` — fetches only
through `safe_get`/`safe_get_once`. The remaining `httpx.AsyncClient` uses in
`main.py` and `grok_chat.py` target Base44 and the Grok API, which are fixed
operator-configured endpoints rather than customer input, and are correctly
outside this guard.

The earlier note said this did not block the first controlled deploy because
those ran against a fixed benchmark set. That reasoning no longer applies: the
paid beta accepts arbitrary customer-submitted domains, which is exactly the
condition this item required to be closed first. It is closed.
