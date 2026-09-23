# Lane B — stable rescan baseline policy handoff

Status: pure, non-wired comparison contract. This checkpoint does not edit the
V8 intake/reader, authority snapshot, persistence, customer UI, gateway, scanner,
or production configuration.

## Current mismatch

The current intake selects the first recent `complete` **or `limited`** row with
matching coarse scope and persists its ID. It does not authenticate that row or
compare the exact requested origin. The customer reader is stricter: it requires
the persisted predecessor to be complete, owner/project bound, HMAC verified,
same origin and scope, and sealed earlier than the current result.

That disagreement can persist an unusable predecessor. It must not be repaired by
choosing a different row during a later read: `previous_scan_id` is historical
lineage, not a mutable query hint.

## Pure policy

`scanComparisonBaselinePolicy.js` separates the two operations:

1. `selectComparisonBaselineV1()` is creation-only. It chooses the latest seal
   strictly earlier than a server-owned UTC `selection_cutoff_at` from bounded
   candidates that are complete, already authority-verified,
   same owner/project, and exact same normalized domain, origin, scope kind and
   path prefix. Scan ID breaks an exact timestamp tie deterministically. The
   creation descriptor deliberately does not require a new ScanRun ID because
   the selection happens before that row exists.
2. `preservePersistedComparisonBaselineV1()` is reload-only. It returns the exact
   persisted pointer, or the exact persisted empty/no-baseline decision. It does
   not accept candidates and cannot substitute after deletion or verification
   failure.

`authority_verified=true` is a typed assertion to this pure helper, not an HMAC
check. The serialized integrator must construct candidate descriptors only after
the existing version-aware authority reader has authenticated the exact snapshot.
Raw browser rows, seal-marker presence, hashes, or client assertions are not
eligible inputs.

## Serialized integration acceptance

- Generate one UTC selection cutoff and run selection once, server-side, before
  creating a future ScanRun.
- Persist the returned `previous_scan_id` (including the explicit empty value)
  atomically with that ScanRun.
- On replay/reload, preserve the stored field and never rerun selection.
- If the referenced row is later missing, unreadable, unauthenticated or
  incompatible, return the existing `CMP-PREVIOUS`/`CMP-SCOPE` unavailable state;
  do not fall through to another predecessor.
- Do not rewrite existing ScanRuns or backfill historical pointers.
- Prove create/replay races retain one identical pointer before shared rollout.

## Separate comparison blocker

The authenticated comparison adapter currently supplies `current_pages=[]`.
Therefore the canonical comparator cannot prove a disappeared repair fixed, even
when technical repair identity is stable. A future producer must carry exact
eligible page/rule observations into the authenticated snapshot/adapter; counts,
fingerprints and recommendation rows alone are insufficient. Historical
provisional rows remain unchanged and `could_not_verify`.

## Live diagnostic dependency

No new owner result with a bounded `CMP-*` support reference was available when
this handoff was prepared. Shape reconstruction with a synthetic key does not
identify the live HMAC, reader, gateway, route or network failure. Only a captured
live support reference should decide which shared boundary is investigated next.
