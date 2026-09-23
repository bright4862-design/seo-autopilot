# Offline grounding gate

Run the entire checked-in corpus from the repository root:

```sh
python scripts/fixbench/run_grounding.py --all
```

A nonzero exit means at least one status, rejection reason, evidence-preservation
expectation, or deterministic-rendering expectation failed. Unknown fixture
versions and empty suites fail closed. This is an offline safety gate; it does
not measure model quality or authorize customer AI.

## Accepted content contract

`ai_annotation_v2` and `chat_answer_v2` contain only typed evidence references,
exact source-path/value pairs, and repair/root-cause references. They have no
free-text slot, template, title, claim name, or caller-supplied field label.
Grounding verifies those declarations before producing literal, deterministic
`rendered_annotations`. That rendering reports values at their exact source
paths. It does not infer that a repair was applied, explain business impact, or
turn citations into support for arbitrary prose. Render it as plain text.
Only `rendered_annotations` is the supported prose output: `verified_payload`
preserves opaque caller annotation IDs and original URL fragments for transport
fidelity, and those fields must not be displayed as trusted narrative.

The original v1 schemas remain parseable for version diagnosis, but the verifier
rejects their unconstrained prose with `unconstrained_text_unsupported`, even
when all declared references are valid. A rejected or unavailable result has no
verified payload or rendered content. V2 answers may drop a bad independent
annotation; conflicting declarations reject the whole answer. Duplicate
annotation identifiers are invalid.

The constrained output is an offline foundation, not completed generative
explanation or chat functionality. A future narrative schema needs independently
verifiable claim semantics before its prose can be considered verified. Do not
reintroduce acceptance by scanning text for a few suspicious words or numbers.

## Evidence boundary

`build_evidence_set()` accepts a **caller-authenticated sealed L2 snapshot**.
It checks required seal-marker shape but does not possess a signing key and does
not authenticate the HMAC. The serialized integrator must authenticate the
snapshot before passing it here; arbitrary JSON from a client is never trusted.
`EvidenceSet` is not an authority seal or a persistence record.

Collection membership is anchored to explicit paths: top-level/review evidence
collections and the three recognized Stage-3 handoff placements. A collection
name encountered under diagnostics, metadata, an unrelated wrapper, or a nested
record cannot establish membership. Only direct records are read; nested arrays
are ignored. Nested URL evidence follows explicit evidence containers, and
nested root-cause evidence must satisfy the existing producer validator,
producer identity and handoff-member binding. Scalar claims are drawn from
explicit scan decisions and supported record fields, not an unrestricted tree
walk. Unknown producer layouts remain unavailable for citation until a reviewed
adapter and regression fixture are added.

The builder reuses published URL identity, preserves submitted references in the
verified payload, copies values into immutable lookup maps, and does not mutate
L1/L2 inputs. Duplicate and conflicting repair/root definitions remain fail
closed. The renderer uses canonical evidence URL identity and does not emit
arbitrary fragment text as prose.

## Trace contract and remaining work

`app.ai_trace.ai_trace()` is a pure metadata-only trace constructor. It accepts
only bounded status/schema/operation labels, fingerprints and counters. It does
not emit a log or accept raw prompt, response, URL, page text or evidence content.
No runtime imports, model calls, chat wiring, scoring, authority, persistence,
release flags or customer UI are changed by this gate.

This corpus covers attribution, provenance, liveness, root identity, producer
binding, exact path boundaries, unconstrained prose rejection, transport
preservation and independent redaction. Broader FixBench work (model quality,
role usefulness, actual provider budgets, live retrieval and production adapter
acceptance) is not completed by this deterministic suite.
