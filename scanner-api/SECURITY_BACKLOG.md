# Security backlog — scanner-api

Tracked hardening items. Turn each into a GitHub issue when ready.

---

## SSRF: pin validated IP + Host header to close DNS-rebinding window

**Status:** open — not required before controlled test deploys against known benchmark sites.

The Python scanner currently resolves a host during `is_public_http_url()`, validates
that all resolved IPs are public, then httpx resolves again during the fetch. That
leaves a DNS-rebinding / TOCTOU window where a hostile DNS server could return a
public IP during validation and a private/link-local IP during the actual fetch.

Before accepting arbitrary public URLs at scale, change `safe_get()` to:

- resolve the hostname once
- validate the chosen IP
- connect to the validated IP
- send the original `Host` header
- preserve HTTPS/SNI considerations
- revalidate every redirect hop the same way

This does not block the first controlled test deploy, because those run against a
fixed set of known-good benchmark sites (Pretto, Meilleurtaux, Funbooker,
Center Street).
