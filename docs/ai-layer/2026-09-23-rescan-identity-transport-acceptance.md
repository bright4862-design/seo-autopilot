# H1-1 identity transport acceptance

Source: AI integration `776e964b23b81a4759a590969ce981789a30d6d7`.
Scope: additive acceptance tests only; no production/shared implementation changes.

## Finding

The real canonical Python producer and completion HMAC, V8 authority snapshot, persisted JSON rows, V8 customer authority reconstruction and existing Python comparator preserve explicitly supplied technical identity in a synthetic signed vector. The same pipeline preserves a provisional identity when those source fields are absent. Transport alone does not supply stable identity.

The new acceptance test covers:

1. Stable identity fields/fingerprint survive canonical producer -> signed completion -> V8 snapshot -> JSON rows -> reconstructed authenticated snapshot.
2. Provisional identity remains provisional through the identical path.
3. A stable reloaded repair remains `still_detected` when its finding ID changes.
4. Provisional repair absence or matching fingerprint continuity remains `could_not_verify`, never `verified_fixed`.
5. Tampering any of the six persisted identity fields makes the original V8 seal fail verification.

The fixture starts from the existing synthetic Stage-3 completion helper. Its provisional variant removes the technical fields BEFORE canonicalization/signing. The test uses real production modules and comparator, not semantic substitutes. No live customer payload, network, credential or stored row is used. Test-only HMAC secret is the existing public fixture value.

## What this resolves and does not resolve

This supplies executable evidence that the tested transport path can retain stable identity; rewriting V8 transport to manufacture identity is not justified by these results. `build_repair_identity()` requires an explicit technical rule, implementation surface and remediation family. A verified root-cause group alone is not a substitute for that contract.

The reported Funbooker production rows remain provisional. These synthetic tests do not prove that the historical producer supplied stable fields or establish a historical root cause. The integrator must inspect an authenticated original producer snapshot to distinguish absent source identity from any production-specific transport difference. Do not upgrade/reseal history, infer identity from text/category/template similarity, or weaken comparison eligibility.

## Next serialized step

Wire customer comparison using authenticated previous/current snapshots and preserve unknown states even if stable source evidence is unavailable. Stable identity is required for verified-fixed claims, not for displaying truthful before/after sample context. If a source enhancement is needed for future scans, first specify the rule-specific technical evidence that proves the repair surface and action family; keep old scans incomparable.

Only the existing integrator should modify shared producer, authority, persistence or customer wiring. This acceptance branch intentionally owns only new test/helper files and this handoff.

## Fresh checks

- `node --test tests/frontend/rescanIdentityV8TransportAcceptance.test.mjs`: 5 passed.
- New V8 tests plus existing `stage3V7DurableDelivery.test.mjs`: 14 passed.
- Python helper compile and `git diff --check`: passed.
- No full CI/review, merge, deployment, customer AI enablement or live acceptance claimed.
