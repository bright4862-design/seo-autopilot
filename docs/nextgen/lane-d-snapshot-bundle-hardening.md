# Lane D — connected-evidence snapshot bundle hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Issue: #325  
Draft PR: #332

> **Historical slice note:** this file records the snapshot-bundle boundary as it was introduced and later extended. The authoritative final validation sequence, exact-head pytest/`py_compile` commands, and current focused-test total live in `docs/nextgen/lane-d-evidence-connectors.md`.

## Purpose

Lane D validates individual `connected_evidence_v1` envelopes through a series of pure fail-closed boundaries. This slice introduced a lane-local boundary for the *set* of optional connected evidence attached to one logical scan/enrichment snapshot.

The contract is `connected_evidence_snapshot_bundle_v1` in `scanner-api/app/connected_evidence_bundle_contract.py`. It performs no network I/O, OAuth/account mutation, persistence, authority, scoring, customer projection, release, deployment, admission, or production work.

## What it proves now

`validate_connected_evidence_snapshot_bundle(...)`:

- is bounded to 64 evidence items;
- requires each item to pass the current full Lane-D single-envelope chain: generic envelope, registered provider/source identity, provider record semantics, sample/coverage semantics, provider property/source scope, and logical record identity;
- rejects non-object members and unsupported provider/source profiles;
- canonicalizes provider source identities before comparing snapshot identities;
- rejects duplicate GSC Search Analytics observations for the same canonical property + dimensions + period/observation identity;
- rejects duplicate URL Inspection observations for the same canonical property + inspected URL within one logical snapshot;
- rejects duplicate Bing AI Performance observations for the same canonical site/window even when a local export file is renamed;
- rejects duplicate GA4 AI-referral observations for the same canonical property/window, including `properties/<id>` versus bare numeric aliases;
- rejects one canonical source scope being represented as both observed (`verified`/`stale`) and unavailable (`not_connected`/`not_supported`/`not_verified`/`provider_error`) inside one logical snapshot;
- leaves distinct observation windows separate and does not merge, sum, rank, persist, or choose a winner.

The deterministic helpers `connected_evidence_snapshot_identity(...)` and `connected_evidence_source_scope_identity(...)` are integrity identities, not authority/signatures. Import filenames are excluded so copying or renaming the same exported evidence cannot create a second logical observation.

## Why this is needed

The single-envelope validators prove that each individual evidence object is truthful. Without a bundle boundary, a later caller could still attach the same valid observation twice and accidentally double-count it, or attach contradictory availability states for the same source scope and leave caller order to determine which one wins. This boundary fails closed before any later serialized integration can make that mistake.

A snapshot bundle is *not* historical time-series storage. Repeated observations over time belong in the serialized persistence/history design, which remains integrator-owned and is not modified here.

## Historical slice verification

`scanner-api/tests/test_connected_evidence_bundle_contract.py` contains the deterministic bundle regressions. The suite has been expanded as later Lane-D boundaries were composed into the bundle. Historical slice counts are not the current integration gate.

For the authoritative exact-head pytest/`py_compile` gate and current focused-test count, use `docs/nextgen/lane-d-evidence-connectors.md` only.

## Current integration handoff

The serialized integrator should treat `validate_connected_evidence_snapshot_bundle(...)` as the **final Lane-D guard for one logical enrichment snapshot**:

1. normalize/import each already-authorized provider payload using the registered Lane-D adapter;
2. validate the complete logical enrichment set once with `validate_connected_evidence_snapshot_bundle(...)`;
3. only then attach the optional connected evidence, preserving provenance and coverage;
4. keep connected evidence separate from canonical crawl authority and preserve Standard 150 behavior when absent.

Do not use this helper to write persistence/history, compute repair priority, score customers, merge evidence windows, alter `run_scan`, modify Base44 schema, deploy, or touch production; those remain serialized-integrator responsibilities or are explicitly outside this lane.
