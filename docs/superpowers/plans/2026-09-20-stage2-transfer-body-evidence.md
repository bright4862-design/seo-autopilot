# Stage 2 B17 direct transfer-body evidence checkpoint

Date: 2026-09-20

Integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

## Scope completed

This slice closes the direct-measurement portion of B17 without inventing transfer size from decoded HTML or server-declared headers.

The hardened bounded fetch path now counts the raw response-body bytes actually yielded by `httpx` `aiter_raw()` before gzip/deflate content decoding. The measurement is carried through an internal scanner-only response header into accepted page evidence.

Semantics are deliberately narrow:

- `transfer_bytes` means response-body payload bytes observed before HTTP content decoding;
- it does **not** claim HTTP headers, TLS overhead or chunk framing;
- decoded HTML bytes remain a separate value;
- inline script/style bytes remain separate values;
- `Content-Length` is never used as a fallback measurement;
- missing measurement remains `unknown`, not zero;
- an actually measured empty body may truthfully be known zero.

Remote sites cannot spoof FixList's measurement. The bounded fetcher removes any upstream `x-fixlist-transfer-body-bytes` header and overwrites it only after reading the body itself. That internal scalar is forwarded only to the extraction seam and is excluded from persisted access-block vendor-header evidence.

Only accepted `usable_html` pages receive measured B17 transfer evidence. Challenge, rate-limit, failed, non-HTML or incomplete responses do not become page-weight evidence even if transport bytes were observed while classifying the response.

No new request, scheduler, crawl budget, decoded-body limit or site expansion is introduced.

## Behavioral regressions

New file: `scanner-api/tests/test_stage2_transfer_body_evidence.py`.

The regressions prove:

1. a gzip response records the observed compressed/raw body length rather than decoded HTML length, remote `Content-Length`, or a spoofed internal header;
2. the security boundary overwrites a remote attempt to set FixList's internal measurement and the internal scalar is not persisted as access-block header evidence;
3. a 429/access-limited page leaves B17 transfer evidence unknown;
4. a measured zero and an unknown measurement remain distinct, and `Content-Length: 0` alone cannot establish a measurement.

## Exact verification

Exact executable head: `b915e3846aa2a94da7acbe0b59be7e22c4b3051d`.

FixList CI run: `35489000795` — **SUCCESS** on both jobs.

Verified on that exact SHA:

- immutable checkout matched `b915e3846aa2a94da7acbe0b59be7e22c4b3051d`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,975 passed / 18 intentional skips**;
- new direct B17 transfer-body regressions: **4 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:bc538561b94c77e14cc25bd85f541bae9d4bd1f72b7619f8a1ad664862031063`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The project Node setup resolved `20.20.2`. This run must not be described as Node `20.19.5` runtime evidence. GitHub's hosted actions also emit their own Node deprecation/runtime warning; that does not change the explicitly installed project Node version above.

## Requirement state after this slice

- **B17 direct byte evidence:** implemented and exact-head green. Transfer-body, decoded HTML, inline script and inline style evidence remain distinct.
- **B17 CrUX:** the pure fail-closed connected-provider envelope already exists, but shared exact-scan result/authority attachment remains open. No CrUX account/access is created by this work.
- **B18 GSC:** the pure fail-closed exact-retained-URL envelope already exists, but shared exact-scan result/authority attachment remains open. No GSC account/access is created by this work.
- **Customer exposure:** this slice does not add a new repair/card/score/priority. If transfer/provider evidence is later displayed, the authenticated producer → Review → authority → persistence → customer/card/handoff/export chain must be added before exposure.

## Hard invariants checked

- Standard-150 assessed-page set and denominator unchanged;
- one finite Stage-2 request pool only;
- existing DNS/SSRF/redirect/robots/body/deadline boundaries retained;
- decoded-body ceiling remains authoritative;
- no `Content-Length` trust introduced;
- access-limited/incomplete evidence remains unknown;
- Python Review ranking authority unchanged;
- historical signatures/readers are not rewritten;
- no deployment, provider connection, schema/secret mutation or production action occurred.

## Exact next serialized action

Attach the existing optional CrUX/GSC envelopes to the shared scan result only after exact durable `scan_id` identity is known. With no owner-authorized provider payload, emit explicit unavailable/disconnected state rather than fabricating data. Keep provider input out of browser/task request contracts unless a separately authenticated server-owned provider source exists. Persist the resulting envelope through the existing signed result/authority path, then require fresh independent review and exact-head CI before Stage 3 integration.
