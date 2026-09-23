# GEO v2 authenticated persistence/reload acceptance path

Date: 2026-09-23  
Lane: `agent/ai-geo-readiness-20260923`  
Status: held candidate; no runtime activation

This is the one supported Lane-C handoff path for a future serialized
integrator. It consolidates existing reviewed helpers and adds no new GEO
evaluator, network request, score, threshold, authority primitive, persistence
writer, or customer projection.

## Source that may enter the path

The serialized integrator must first verify the existing V8 authority proof for
the exact parent scan. It must then derive all of the following server-side from
that same authenticated snapshot/source population:

- exact owner, project and scan identity;
- exact normalized domain and scan scope;
- exact retained page identities;
- exact typed GEO observations, including page/check identity, state, evidence
  reference and reason;
- retained named-crawler robots observations and any retained `llms.txt`
  observation;
- exact extraction/evaluator contract versions.

A client candidate, parent `authority_verified` marker, count, ordinary digest,
or caller assertion is not source authentication. If the authenticated source
does not contain the exact retained observations, integration stops with GEO
unavailable and `authority_verified=false`.

## Pre-seal construction

Using only that authenticated source population:

1. Build `geo_readiness_v2_candidate` through
   `build_geo_v8_transport_candidate(...)`. The frozen v1 evaluator remains the
   score and coverage authority.
2. Rebind the candidate to the exact retained page set and optional retained
   robots/`llms.txt` sources.
3. Call `build_geo_v8_transport_observation_binding(...)` with the exact typed
   observation population.
4. Call `serialize_geo_v8_transport_observation_binding(...)` and retain those
   exact canonical bytes. The binding and nested candidate must still say
   `seal_state=unsealed_candidate` and `authority_verified=false`.

The production-shaped acceptance test now runs this complete path for 139 pages
and 1,668 observations: 762 verified cells, 906 unknown cells, 45.6835% overall
coverage, Entity/Support at 0%, `assessment_status=insufficient_evidence`, and
numeric score `null`.

## Authority and persistence boundary

Only the serialized integrator may introduce a new versioned V8 authority
snapshot. Its HMAC must cover the complete observation-binding object/canonical
bytes and the exact parent scan/source identity—not merely the binding digest,
page-set digest, observation count, or coverage totals.

Persist atomically:

- the complete versioned authority snapshot;
- its authority proof and accepted authority version;
- the complete GEO observation binding;
- the exact source scan identity and contract versions needed for historical
  verification.

Do not recompute historical GEO results during reads. Historical snapshots that
do not contain this authenticated GEO block remain readable with GEO authority
unavailable/false.

## Reload acceptance

For the exact saved scan, the authenticated reader must:

1. enforce exact owner/project/scan access;
2. verify the snapshot HMAC and accepted version before reading GEO;
3. recover the complete persisted observation binding and retained source
   population;
4. re-run source, scope, semantic and observation binding validation;
5. call
   `validate_geo_v8_transport_observation_binding_reload_identity(...)` with
   the original canonical pre-seal bytes;
6. reject missing, substituted, reordered-with-changed-content, extra or
   aggregate-equivalent-but-page-different observations;
7. prove the same result through immediate result, reload and history readers.

Ordering alone is non-authoritative and canonicalizes identically. Any changed
page/check state, evidence reference or reason changes the bound bytes.

## Customer and claim gates

This lane does not authorize setting GEO `authority_verified=true` or exposing
v2 to customers. That requires exact integrated tests over the new authenticated
snapshot, persistence and all entitled projections, plus historical
compatibility and release acceptance.

The 80% overall and 50% per-dimension evidence gates remain unchanged. Robots,
`llms.txt`, structured data and access signals remain structural evidence; none
proves provider fetching, indexing, inclusion, ranking, citation, visibility or
traffic.
