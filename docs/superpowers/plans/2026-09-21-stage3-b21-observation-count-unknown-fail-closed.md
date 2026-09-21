# Stage 3 B21 observation-count unknown fail-closed

## Authority and scope

Authoritative requirement source: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, especially B21 and B24. B21 requires distinct truthful observation/population/sample counts, and the blueprint invariant requires missing or invalid evidence to remain unknown. B24 must not sign fabricated counts into the customer handoff.

This slice is implementation-only on `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303. It does not merge to `main`, deploy, promote a worker, mutate admission/queues/scheduler, run a production scan, alter schema/RLS/secrets, or enable Premium/Grok.

## Reproduction

RED test commit: `913dfd011aced1cd6a348468dcfd357bd316c40a`.

New regressions in `scanner-api/tests/test_stage3_b21_observation_count_unknown.py` exercise the real B21 helper and B24 handoff serializer:

1. an explicit malformed `observation_count` with no actual observation list must remain `None`, not become zero;
2. a structured operator/debug observation count must not become a signed zero in handoff-v2 and must not leak its sentinel;
3. when explicit count evidence is invalid but a real observation list exists, the list length remains a truthful fallback.

FixList CI `35581103845` produced the intended RED. Immutable checkout matched the RED SHA. The independent lint/typecheck/generated-contract/frontend/build job passed. The scanner job passed root scanner regressions and failed at the Python scanner-api test step; corpus/frozen-revision/image steps were skipped after that intentional RED failure.

## Defect

`stage3_delivery.summarize_candidate_counts()` previously attempted strict numeric validation first, but then always normalized `candidate.get("observations")` through `_list()` and took its length. `_list()` returns an empty list for a missing or malformed value. As a result, malformed explicit count evidence such as a string or mapping could silently become `0` when no real observation list was present.

That violated B21's truthful count semantics and the blueprint's fail-closed unknown rule. Because B24 calls the same count helper, the fabricated zero could also enter the signed customer handoff.

## Implementation

Source correction commit: `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`.

The fallback now distinguishes three states:

- a real list/tuple of observations supplies its actual length;
- explicitly present but malformed observation/count evidence remains `None`;
- only the historical case where both fields are completely absent preserves the legacy zero fallback.

No URL identity, ranking, score, preview, historical signature, persistence, network, admission, or release behavior changed. RED-to-source compare changes only `scanner-api/app/stage3_delivery.py`, 8 additions / 3 deletions.

## Verification

Exact-source FixList CI `35581439449` passed both jobs on `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`.

Verified steps include immutable checkout; root scanner regressions; the full Python scanner-api suite including the new B21/B24 regressions; labelled Stage-1 synthetic corpus; frozen beta revision verification; production scanner image build; lint; typecheck; generated release contracts; frontend contract tests; and production build. The GitHub job metadata available to this serialized owner does not expose trustworthy pytest totals or the image digest for this run, so this checkpoint does not invent them.

## Requirement state after this slice

- **B21 remains partial:** malformed explicit observation-count evidence no longer turns into a fabricated zero; a real observation list can still provide the count. Durable V7 persistence/card/export proof remains open.
- **B24 remains partial:** the shared handoff-v2 count projection now preserves this B21 unknown state. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.
- **B19/B20/B22/B23 remain partial:** unchanged by this narrow count-truthfulness correction.
- **Stage 3 is not complete. Stage 4 remains held. B25's genuine provenance-labelled 30-site gate remains `not_assessed`.**

## Remaining serialized gates

1. Persist this RED/GREEN checkpoint in `docs/full-blueprint-progress.md`, `docs/blueprint-checkpoint-handoff.md`, and PR #303, then certify the final persisted branch head with exact-head FixList CI.
2. Obtain one genuinely fresh independent review of the current B19–B24 signed authority/privacy boundary; an old or skipped automatic review is not approval.
3. Keep the Stage-1 release freeze intact until the separate release operator records exact-source publication and fresh non-owner acceptance.
4. After that gate closes, reconcile onto the then-current accepted `main` without reverting V7/#308, run fresh integrated-head CI, and prove real producer → signed authority → persisted rows → exact-owner/exact-scan reload/history → card/export/preview seams.
5. Only after Stage 3 applicable acceptance should the existing Stage-4 lane be shared-integrated and the genuine B25 30-site and B28 live gates be executed.
