# Stage 3 B21–B24 isolated lane handoff — 2026-09-19

Branch: `agent/stage3-b21-b24-delivery-20260919`

Base checkpoint: Stage-2 PR #303 head `b05fe3993422357959c7755a2eda47a2e635943f`.

This lane is intentionally isolated from unfinished Stage-2 integration and from the B19/B20 ranking/root-cause lane. It owns only pure Stage-3 delivery contracts and their behavioral regressions. It does **not** edit `run_scan`, the shared coverage scheduler, B08/B09/B16 modules, `repair_priority.py`, authority/persistence writers, current customer projection code, deployment, `main`, or live data.

## Implemented contracts

### B21 — honest counts and ranking before truncation

`scanner-api/app/stage3_delivery.py`

- Builds the exact deduplicated affected-page union from affected pages, grouped affected pages and observation URLs without URL normalization. Case/slash/query spelling is therefore not collapsed by this layer.
- Keeps unique affected-page count, observation count, known population and displayed sample count separate.
- Missing known population stays `None`; it is never inferred from the observed sample.
- Examples are sampled only after the exact union is known, with explicit `examples_partial` and omitted-count diagnostics.
- Eligible candidates are ranked in Python before applying the legacy presentation cap. The helper consumes B19's future Python-owned numeric rank/score and does not create a competing ranking model.
- Deterministic fallback ordering exists only for integration inputs that do not yet carry B19 ranking fields.

### B22 — evidence-led private preview

- Requires top-level authority verification plus per-finding `authority_verified`, `preview_allowed` and `evidence_state=verified`.
- Requires exact `scan_id` and owner identity match, preventing cross-scan/cross-customer leakage.
- Prefers individually verified impact-4/5 findings, otherwise the best remaining verified finding.
- Projects a strict whitelist (`rule_id`, title, impact, bounded evidence summary) rather than returning the raw finding, affected-page list, suppressed findings or internal fields.
- A good-shape message is emitted only when an explicit sufficient-coverage qualification and text are supplied. Limited/unknown coverage never becomes a clean-site claim.

### B23 — explicit verified root-cause score caps

- Accepts the existing access/sample/incomplete ceiling as an independent input and preserves it.
- Applies only explicit 0–100 caps from root causes whose verification state is exactly `verified` and which carry a stable root-cause ID.
- Deduplicates score caps by root-cause ID so overlapping SEO/GEO/rule observations cannot apply a root cause twice.
- Heuristic, unverified, missing-ID and missing/invalid-cap rows are retained in ignored diagnostics and cannot silently alter health score.
- Unknown coverage is exposed as state; it does not manufacture a penalty.

### B24 — compatible handoff-v2 contract

- New v2 builder is separate from the historical v1 exporter, so existing v1 bytes/signatures are untouched in this lane.
- Exports scan identity, user agent, root-cause/family identities, published/request/final URL provenance, honest affected/observation/population/example counts, example truncation, four-factor priority payload, evidence references, verification steps, dependency and vendor/owner responsibility metadata supplied by the caller.
- Suppressed findings/reasons are omitted from customer handoff and included only when the caller has explicit operator authorization.
- Compatibility reader returns missing-version / explicit-v1 payloads unchanged and deep-copied; unknown explicit versions fail closed.

The serialized integrator must map the v2 helper onto the repository's existing JavaScript `fixlist.scan_handoff.v1` exporter and authenticated canonical report after B19/B20 and Stage 2 are stable. This lane deliberately does not change the existing customer exporter by itself.

## Behavioral regression coverage

`scanner-api/tests/test_stage3_delivery_contracts.py` adds 11 focused tests covering:

1. more than ten exact affected URLs with sample truncation;
2. deduplicated union across overlapping groups/observations;
3. ranking all candidates before the legacy 36-item presentation cap;
4. strict preview-field whitelist;
5. unverified/tampered/cross-scan/cross-owner preview rejection;
6. qualified good-shape messaging only with sufficient coverage;
7. verified explicit root-cause cap application while heuristic/unverified caps are ignored;
8. unknown coverage preserving existing ceilings without invented penalties;
9. v2 root-cause/family/provenance/count/priority/evidence/dependency metadata;
10. operator-only suppressed findings;
11. unchanged v1 read shape and fail-closed unknown handoff versions.

## Verification

Exact code/test head before this documentation commit: `fba0bdc8054b34afde411e8916c8901f78f76beb`.

FixList CI run: https://github.com/bright4862-design/seo-autopilot/actions/runs/35463363227 — **SUCCESS**.

Fresh CI evidence on that exact code/test head:

- immutable checkout matched `fba0bdc8054b34afde411e8916c8901f78f76beb`;
- root scanner regression step: passed;
- full Python `scanner-api` test step, including all 11 B21–B24 regressions: passed;
- labelled Stage-1 synthetic corpus verification: passed;
- frozen revision verification: passed;
- production scanner-image build: passed;
- lint: passed;
- typecheck: passed;
- generated release contracts: current;
- frontend contract tests: passed;
- frontend production build: passed.

CodeRabbit independent review was requested on draft PR #315 but the service reported its review limit had been reached. That is recorded as **review unavailable**, not an independent-review pass.

## Shared integration steps still required

These steps intentionally remain with the serialized Stages 2–4 integration owner:

1. Finish and verify Stage 2 first; do not wire this lane onto moving Stage-2 authority/customer contracts.
2. Integrate B19/B20 ranking/root-cause outputs and pass their authenticated Python-owned priority rank/factors/root-cause IDs into these helpers.
3. Authenticate every new displayed B21–B24 count/priority/root-cause/handoff field in the canonical authority snapshot before projecting it to customers.
4. Apply `prepare_ranked_candidates` before the existing review/presentation cap, not after the current 36-item truncation seam.
5. Feed B22 only canonical verified findings already allowed by existing entitlement/preview policy; do not use this helper as a bypass around current access gates.
6. Feed B23 the existing access/sample/incomplete score ceiling and only B20 root causes that are authenticated and explicitly verified.
7. Add the handoff-v2 JavaScript/customer integration beside the existing `fixlist.scan_handoff.v1` path. Historical v1 output/read behavior must remain byte-compatible; new v2 fields must come only from verified canonical authority.
8. Ensure handoff v2 carries the canonical indexable count as well as affected/observation counts when the B19/B20/authenticated integration shape is finalized; this isolated helper currently preserves the supplied known population rather than inventing indexability.
9. Add real verified canonical report → persisted rows → customer/card/preview/handoff/export regressions for the integrated fields.
10. Run combined exact-head CI and independent review on the integrated Stage-3 state before marking B21–B24 source-complete.

## Requirement status

- **B21:** pure count/rank-before-truncate contract + behavioral regressions implemented and CI-verified; shared review/presentation wiring remains open.
- **B22:** private preview selection/redaction contract + regressions implemented and CI-verified; authenticated customer preview integration remains open.
- **B23:** root-cause cap contract + regressions implemented and CI-verified; B20 authenticated root-cause and existing score-ceiling integration remain open.
- **B24:** v2 serializer/compatible-reader contract + regressions implemented and CI-verified; canonical authority + current JavaScript exporter/customer integration and canonical indexable-count wiring remain open.

**Lane status: integration-ready, not source-complete.**

No merge, deployment, live scan, provider connection, schema mutation or customer-data write is claimed by this lane.