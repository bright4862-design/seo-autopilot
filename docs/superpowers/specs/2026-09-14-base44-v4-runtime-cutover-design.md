# Base44 V4 Runtime Cutover Design

## Goal

Restore LIVE Standard 150 by moving the six active Base44 scanner/customer routes from stuck V3 names to fresh V4 names, while preserving current scanner, authority, admission, history, paid-access, and unpaid-preview behavior byte-for-byte except for route/runtime identity.

## Evidence and rationale

The guarded V3 delete/recreate recovery recognizes the Sep 14 stale runtimes but the public V3 handlers remain stale. A fresh-name canary on exact main `f9f5b68c7f04e194cd31ca697377afa3bf5f36bf` deployed, pulled back byte-identically, and served the exact source SHA. The failure is therefore name-bound to the existing V3 runtime identities, not the release source or Base44 deployment plane generally.

## Architecture

Create `startStandardScanJobV4`, `durableScanWorkerControlV4`, `persistDurableScanAuthorityV4`, `persistLimitedScanResultV4`, `getCustomerScanResultV4`, and `deleteCustomerScanDataV4` as fresh aliases of the current canonical packages. Their executable source must remain identical to the canonical package after normalizing only `BASE44_RUNTIME_ACTIVATION_ID`; their `function.jsonc` names and activation IDs are fresh V4 identities. The route registry becomes generation `v4`, while V3 and V2 remain historical routes.

Frontend and worker call sites move only from V3 names to V4 names. Release manifests, generators, deploy scripts, and verification scripts treat V4 as active. The generator must stamp both V3 and V2 historical aliases so historical packages do not drift.

## Non-goals

No scanner findings, crawling, scoring, robots, SSRF, signing, entitlement, pricing, UI design, Base44 CLI version, Premium 5,000, Grok, or architecture changes. Do not reseal historical rows and do not weaken authority verification.

## Unpaid preview invariant

`getCustomerScanResultV4` must preserve the current verified-preview path: after authority verification, unpaid access returns `previewAccess: true` and `authorityVerified: true`. Its projection must return at most two preview FixItems, and the frontend must continue showing at most two detailed fixes with the shared `$49` unlock CTA. No full FixItem payload may be exposed to the browser for preview access.

## Release acceptance

All V4 route/package parity and call-site tests pass; full CI is green; a new exact-main worker is staged at zero traffic; with admissions still closed, guarded Base44 `site-and-functions` publish proves all six V4 runtimes; only then promote the exact worker, resume queues with claim barrier still closed, run one fresh unpaid Standard 150 acceptance scan, verify teaser/reload/history/no leakage plus paid sanity, and finally reopen claims.
