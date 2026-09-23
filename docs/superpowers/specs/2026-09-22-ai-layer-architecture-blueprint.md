# FixList AI Layer Architecture Blueprint

Status: approved architecture baseline for the AI layer. This document is additive to the Standard 150/V8 scanner architecture and does not authorize production AI output.

## Non-negotiable invariants

- Standard 150 and current V8 authority/persistence/customer projection behavior remain unchanged.
- AI consumes sealed L2 evidence only. AI never writes, mutates, upgrades, or substitutes L1/L2 truth.
- No model/provider calls, prompt work, customer-visible AI, Premium, deployment, Base44/GCP/admission/IAM/secrets, crawl/scoring/ranking, or authority/persistence/projection changes are part of the Grounding/Evaluation lane.
- Shared V8 wiring is serialized-integrator ownership. Grounding code must expose pure, deterministic interfaces and hand off any shared-seam requirement rather than editing it.
- Existing published evidence identity is authoritative. Reuse `published_evidence_url_key()` / `scan_evidence_origin()`; never create a competing URL normalizer.
- Verification is fail closed. Unknown schema versions, missing sealed evidence, unsupported claims, malformed refs, fabricated URLs/counts/IDs, and deterministic contradictions cannot pass.
- Clause-level redaction is allowed only when the clause/annotation is a structurally independent unit. Otherwise reject the whole annotation or payload.
- AI traces contain only bounded metadata/fingerprints/counters/statuses, never raw customer content, prompts, answer text, URLs, page titles, or evidence snippets.

## Lane A ownership

Lane A owns:

1. H1-0 Grounding Verifier.
2. AI Annotation Envelope and versioned AI schema registry.
3. H1-6 trace primitives.
4. FixBench skeleton plus adversarial attribution and evidence-preservation suites.
5. Grounding-specific fixtures and tests.

Owned implementation surfaces are `scanner-api/app/ai_schemas/**`, `scanner-api/app/grounding_verifier.py`, grounding-specific tests/fixtures, `scripts/fixbench/**`, and narrow additive helpers in `scanner-api/app/observability.py`.

## H1-0 Grounding Verifier

The verifier sits between any future model output and any future customer-visible AI surface. It accepts only versioned envelopes and an EvidenceSet derived from sealed L2 data. The verifier performs no retrieval and no crawl. Verification is deterministic and side-effect free.

Required checks:

- schema/version validation with strict extra-field rejection;
- evidence URL membership using the published evidence URL identity and optional liveness checks against sealed page status evidence;
- numeric provenance: every numeric claim points at an exact sealed source path and exactly matches that value;
- fix references and root-cause references resolve to sealed L2 identities;
- every annotation has non-empty evidence;
- authority/state claims are explicit source-bound scalar claims and match sealed truth exactly;
- deterministic conflict detection rejects contradictory claims against the same source reference;
- malformed or missing seal evidence produces `unavailable`, not a guessed answer.

Verifier result states are exactly:

- `verified`: every annotation passes.
- `redacted`: a multi-annotation payload contains at least one independently safe annotation and one or more invalid independent annotations that can be dropped without rewriting the surviving claims.
- `rejected`: schema invalid, deterministic conflict, a single annotation fails, or structural safety does not permit partial output.
- `unavailable`: sealed L2 evidence required for verification is unavailable or incomplete.

## AI schema registry

### `ai_annotation_v1`

A strict annotation envelope containing:

- `schema_version = "ai_annotation_v1"`
- stable `annotation_id`
- bounded `text`
- non-empty `evidence[]`, each containing an evidence URL and an explicit `require_live` boolean
- zero or more `numeric_claims[]` with `name`, exact scalar `value`, and exact sealed `source_ref`
- zero or more `fix_refs[]`
- zero or more `root_cause_refs[]`
- zero or more `state_claims[]` with `field`, scalar `value`, and exact sealed `source_ref`

Unknown fields are rejected.

### `chat_answer_v1`

A strict answer envelope containing:

- `schema_version = "chat_answer_v1"`
- stable `answer_id`
- non-empty list of `ai_annotation_v1` annotations

Unknown fields are rejected. The answer envelope exists so each independently grounded clause can be verified/redacted without editing prose inside a clause.

## Deterministic EvidenceSet

`build_evidence_set()` consumes a sealed L2 snapshot only. A usable snapshot must carry the existing authority seal markers (`authority_seal_version`, `authority_sealed_at`, `authority_proof`). The builder:

- derives scan origin through the existing evidence-identity helper;
- records published URL identities from known evidence URL fields/lists;
- records live URL identities only when sealed status evidence proves an observed 2xx/3xx response;
- records exact numeric/scalar source paths for provenance checks;
- records fix IDs/fingerprints and root-cause IDs from sealed repair/root-cause collections;
- produces a canonical SHA-256 fingerprint over metadata/ref/value identities used by the verifier.

The EvidenceSet is an evaluation artifact. It does not become authority and is not persisted by this lane.

## H1-6 AI trace primitive

The AI trace shape is metadata-only and may contain: trace version, operation label, verifier result state, schema version, EvidenceSet fingerprint, counts of annotations/rejections, and latency. It must never accept or emit raw prompt, response, page text, evidence snippets, URLs, titles, or customer identifiers beyond an already-approved opaque correlation ID supplied by an integrator.

## FixBench

FixBench is a deterministic offline gate, not a provider benchmark. Initial Grounding/Evaluation suites must include:

- clean controls that verify;
- fabricated but plausible URL attribution;
- fabricated counts with valid-looking source labels;
- fabricated fix IDs;
- fabricated root-cause IDs;
- evidence-liveness failures;
- authority/state claim mismatch;
- deterministic contradiction cases;
- evidence-preservation cases proving valid citations/refs survive transport unchanged;
- structurally safe multi-annotation redaction controls.

The gate passes only when every case reaches its expected fail-closed result. Future model quality metrics may be added separately; they cannot weaken this gate.

## Integration contract

A future serialized integrator may wire sealed V8 L2 snapshots into the EvidenceSet builder and may route future AI envelopes through the verifier. Lane A does not edit those shared seams. The integrator must preserve the verifier's exact fail-closed status and must not reinterpret `rejected`/`unavailable` as usable content.
