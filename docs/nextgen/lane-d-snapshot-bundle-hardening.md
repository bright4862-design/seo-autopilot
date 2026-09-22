# Lane D — connected-evidence snapshot bundle hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Issue: #325  
Draft PR: #332

## Purpose

Lane D already validates one `connected_evidence_v1` envelope through four fail-closed pure boundaries: generic envelope integrity, registered source identity, provider-specific record semantics, and sample/coverage accounting. This slice adds a fifth lane-local boundary for the *set* of optional connected evidence attached to one logical scan/enrichment snapshot.

The new contract is `connected_evidence_snapshot_bundle_v1` in `scanner-api/app/connected_evidence_bundle_contract.py`. It performs no network I/O, OAuth/account mutation, persistence, authority, scoring, customer projection, release, deployment, admission, or production work.

## What it proves

`validate_connected_evidence_snapshot_bundle(...)`:

- is bounded to 64 evidence items;
- requires each item to pass the full existing coverage validator, which composes the prior generic/source/record/coverage boundaries;
- rejects non-object members and unsupported provider/source profiles;
- rejects duplicate GSC Search Analytics observations for the same property + dimensions + period/observation identity;
- rejects conflicting duplicate unavailable GSC states for the same property scope;
- rejects duplicate URL Inspection observations for the same property + inspected URL within one logical snapshot;
- rejects duplicate Bing AI Performance observations for the same site/window even when a local export file was renamed;
- rejects duplicate GA4 AI-referral observations for the same property/window;
- leaves distinct observation windows separate and does not merge, sum, rank, persist, or choose a winner.

The deterministic helper `connected_evidence_snapshot_identity(...)` is intentionally an integrity identity, not an authority/signature. Import filenames are excluded so copying or renaming the same exported evidence cannot create a second logical observation.

## Why this is needed

The single-envelope validators prove that each individual evidence object is truthful. Without a bundle boundary, a later caller could still attach the same valid observation twice and accidentally double-count it, or attach contradictory unavailable states for the same source scope and leave caller order to determine which one wins. This slice fails closed before any later serialized integration can make that mistake.

A snapshot bundle is *not* historical time-series storage. Repeated observations over time belong in the serialized persistence/history design, which remains integrator-owned and is not modified here.

## Tests

`scanner-api/tests/test_connected_evidence_bundle_contract.py` adds 13 focused regressions covering:

- empty bundle preservation;
- sequence and item bounds;
- non-object members;
- composition through the existing coverage boundary;
- duplicate GSC observed identity;
- distinct GSC periods;
- contradictory unavailable GSC states;
- duplicate URL Inspection identity;
- Bing import filename exclusion;
- duplicate GA4 property/window identity;
- deterministic/non-mutating identity generation;
- fail-closed behavior when the upstream composed validator rejects an envelope.

A hermetic slice harness with a stubbed upstream coverage validator passed 8/8 direct contract scenarios. This is slice evidence only. The full exact-head repository suite remains the integration gate.

## Integration handoff

The serialized integrator should treat the bundle contract as the final lane-D guard for a single enrichment snapshot:

1. normalize/import each provider payload using the registered Lane-D adapter;
2. validate the complete set once with `validate_connected_evidence_snapshot_bundle(...)`;
3. only then attach the optional connected evidence, preserving provenance and coverage;
4. keep connected evidence separate from canonical crawl authority and preserve Standard 150 behavior when absent.

Do not use this helper to write persistence/history, compute repair priority, score customers, merge evidence windows, or alter `run_scan`; those remain serialized-integrator responsibilities.
