# Lane C — Lighthouse opportunity-unit hardening

Issue: #324  
Draft PR: #331  
Branch: `agent/nextgen-browser-performance-20260921`

## Why this slice exists

The base Lighthouse envelope intentionally keeps a small allowlist of performance opportunities, but a raw Lighthouse audit can expose a generic `numericValue` whose semantic unit varies by audit. A downstream consumer must not infer that a bare numeric value means milliseconds or bytes.

This slice adds a separate, lab-only derived contract that rebuilds opportunity evidence from the raw Lighthouse payload plus already source-bound direct-Lighthouse evidence. It does not alter CrUX field evidence, execute Lighthouse, grant browser budget, call any live provider, or create credentials.

## Contract

`nextgen_lighthouse_opportunity_evidence_v1`:

- accepts only source-bound `nextgen_lighthouse_evidence_v1` lab evidence from `nextgen_lighthouse_bound_provider_v1`;
- requires the raw provider `requestedUrl` / `finalUrl` identities to match the bound Lighthouse provenance;
- rejects credential-bearing HTTP identities;
- trusts `details.overallSavingsMs` and `details.overallSavingsBytes` as explicitly typed savings fields;
- uses a raw `numericValue` only when `numericUnit` explicitly identifies milliseconds or bytes;
- never guesses an absent or unsupported numeric unit;
- preserves a valid Lighthouse audit score even when an ambiguous numeric savings value is excluded;
- excludes audits carrying `errorMessage` or `scoreDisplayMode=error`;
- emits `not_applicable` when none of the bounded opportunity audits are present;
- keeps disconnected/unavailable/rate-limited/provider-error sources as `not_verified` with no retained measurements.

`nextgen_lighthouse_opportunity_integrity_v1` recomputes the derived artifact from the exact raw payload and exact source-bound Lighthouse envelope. Mutated savings, state, provenance, or source material therefore fails closed.

## Deterministic verification

The focused regression file contains 13 tests covering:

1. explicit millisecond/byte savings fields;
2. explicit millisecond numeric fallback;
3. explicit byte numeric fallback;
4. missing-unit non-guessing with score preservation;
5. unsupported-unit fail-closed behavior;
6. errored-audit exclusion without dropping another valid opportunity;
7. truthful `not_applicable` behavior when no allowlisted opportunity exists;
8. non-connected source behavior;
9. field-to-lab laundering rejection;
10. credential-bearing provider identity rejection;
11. raw redirect/provenance mismatch rejection;
12. integrity recomputation/tamper rejection;
13. raw/source input immutability.

Hermetic execution of this exact new source/test pair passed `13/13` and both files passed Python syntax compilation before publication.

## Integrator hook

After `normalize_lighthouse_evidence_bound(...)` returns connected lab evidence and `validate_bound_lighthouse_contract(...).valid` is true, a future serialized integrator may call:

```python
opportunities = normalize_lighthouse_opportunity_evidence(raw_lighthouse_payload, bound_lab)
check = validate_lighthouse_opportunity_contract(raw_lighthouse_payload, bound_lab, opportunities)
```

Only a valid `normalized` artifact should be interpreted as trusted lab opportunity evidence. This contract is evidence only; it must not affect repair/customer scoring directly in the lane branch.

## Ownership and rollback

No shared orchestration, `run_scan`, global budget, worker deployment, authority/persistence/projection, admission, release, production, credential, IAM, or provider-account surface is modified. Rollback is deletion of this helper/test/doc slice; there is no migration or historical reconstruction impact.
