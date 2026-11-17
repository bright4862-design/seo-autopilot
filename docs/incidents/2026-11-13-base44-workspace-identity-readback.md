# Incident #378 — read-only Base44 workspace identity versus canonical GitHub main (2026-11-13)

**Classification:** source/workspace divergence observed, **not** deployed runtime attestation, incident recovery, or release approval. No production change was made.

## The falsifiable question

Does the connected **Getfixlist** Base44 app's main working source carry the same Standard 150 release identity as canonical GitHub `main`? A source match would still not prove what is published; a mismatch is a concrete reason not to infer runtime convergence from the checked-in tree.

## Independent readbacks

On **2026-11-13**, a read-only Base44 app listing identified the Getfixlist app and its published URL `https://getfixlist.base44.app`. Read-only Base44 `read_file` on the app's main working tree and GitHub `fetch_file` on exact `main@029639a0b4e8cb229baecb8b7f6f8195f5280e83` returned:

| Evidence | Base44 main *workspace source* | GitHub exact `main` |
| --- | --- | --- |
| `data/beta-crawler-revision.json` status | `candidate`, no accepted commit | `candidate`, no accepted commit |
| Manifest fingerprint | `e0eca935c350e590` | `118544dcf77d86cf` |
| Sampling marker | `balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves` | `balanced_sitemap_buckets_v9_feasible_ceiling_hub_reservations` |
| `persistDurableScanAuthorityV8/entry.ts` fingerprint | `e0eca935c350e590` | `118544dcf77d86cf` |
| `getCustomerScanResultV8/entry.ts` fingerprint | `e0eca935c350e590` | `118544dcf77d86cf` |
| V8 persistence `generatedBuildId.js` | `cb8feb5da4a2358a9f291f7cb2c18ae70fc5d8e748f67306ac96bfefecce07d8` | `47056943651359145be9db0db2fd2a7f4c3629868a4f3adf39d664598784c64d` |
| V8 reader `generatedBuildId.js` | `19be03c6cf96a48df72623a469b87837b1962248c9972c9e16df609dd92f0b26` | `ee086ea73bf02328079f0455cf85ac5a8d1c09d87dfef1f128500cf731c66e8e` |
| `persistDurableScanAuthorityV9/entry.ts` | File not found | Exists, marker `118544dcf77d86cf` |

The connected Base44 workspace's V8 `generatedReleaseContract.js` also declares `RELEASE_FINGERPRINT = "e0eca935c350e590"`, matching its entry source. This is coherent **workspace v7 source** but not canonical main v9 source.

Source permalinks: [canonical manifest](https://github.com/bright4862-design/seo-autopilot/blob/029639a0b4e8cb229baecb8b7f6f8195f5280e83/data/beta-crawler-revision.json), [GitHub V8 persistence entry](https://github.com/bright4862-design/seo-autopilot/blob/029639a0b4e8cb229baecb8b7f6f8195f5280e83/base44/functions/persistDurableScanAuthorityV8/entry.ts), [GitHub V9 persistence entry](https://github.com/bright4862-design/seo-autopilot/blob/029639a0b4e8cb229baecb8b7f6f8195f5280e83/base44/functions/persistDurableScanAuthorityV9/entry.ts).

## What this does *not* establish

The Base44 `read_file` operation reads the app's **working source**, not independently authenticated **published function bytes**. The platform's read-only `GET /api/apps/{app_id}/backend-functions` is documented to return deployed functions, but this connector invocation returned `{"truncated":true}`; no deployed package identity could be extracted. Reading the public URL proves it is registered as published, not the actual function version. It would be incorrect to label the workspace fingerprint as a fresh verified production deployment.

Historical release evidence in [incident #378](https://github.com/bright4862-design/seo-autopilot/issues/378) identifies a separately authenticated **serving** worker at `01ebe8e90df1e6bd` (v6) and last-reported **published** V8 persistence at `e0eca935c350e590` (v7). Neither is proof that today's deployed Base44 runtime has been rechecked. The Nov 12 GCP `BILLING_DISABLED` errors also require a fresh owner-authorized status read after billing recovery.

## Consequence and next discriminating test

**Baseline assumption falsified:** “GitHub main and Base44 working source carry the same latest release fingerprint.” They do not. This is compatible with an intentionally unpublished candidate and must not be treated as an accidental deployment or cause to sync/publish blindly.

Before any Standard 150 release candidate is accepted, obtain **published** Base44 V8/V9 package/build IDs and fingerprint with an owner-authenticated readback independent of the working files, then compare with the exact chosen worker's authenticated `/revision` and accepted manifest. A changed editor file or matching build script alone is insufficient. If the platform cannot supply that receipt, report **INDETERMINATE**, not a match. Resolve billing first for signed queue/barrier verification, then proceed only through separate owner-authorized staged canary, signed persistence, customer read-back and rollback gates.

This investigation made **no** Base44 edits, deployment, GitHub main changes, queue/traffic change, schema/secret/Stripe operation or customer scan. Historical failed ScanRuns are untouched. Standard 150 retains its 150-page cap; Grok/chat, Extended 500 and Premium 5,000 remain disabled.
