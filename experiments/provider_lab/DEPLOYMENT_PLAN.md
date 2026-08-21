# Tentative Grok Reasoning Integration Plan

Target window: **Wednesday 2026-08-26 or Thursday 2026-08-27**.

This is a planning document only. It does not authorize deployment or feature enablement.

## Goal

Evaluate and, only if the evidence is strong enough, integrate **Grok 4.20 Reasoning on the existing Vertex transport** without changing Standard 150 authority or scanner behavior.

Hugging Face remains relevant as the host of the existing FixList Space and as a separate future open-model/provider evaluation lane. It is **not** the preferred first production inference dependency because the current Space routes live Grok through scanner `/chat`, and xAI is not currently an HF Inference Provider.

Protected architecture remains unchanged:

- crawl discovery and page selection;
- worker/admission and reconciliation;
- durable ScanRun identity/persistence;
- 150-page enforcement;
- robots and SSRF protections;
- review/repair persistence;
- HMAC/authority seals;
- release-gate eligibility;
- terminal-state ownership.

## Friday 2026-08-21 — refreshed baseline

Required outcomes:

- provider lab rebuilt from exact current `main`;
- authority manifest separated from model-facing evidence;
- repair-v2 and valid legacy authority fixtures covered;
- current compact Base44 provider payload captured;
- current Vertex transport contract captured;
- same-Vertex reasoning candidate modeled as a model-ID-only change;
- recorded output/retry parity covered;
- grounding checks for invented URLs/page counts covered;
- comparison harness uses the same frozen prompt/evidence for baseline and candidate;
- no network-capable candidate code;
- lab remains outside production scanner Docker context;
- exact-head FixList CI green.

## Weekend / Monday 2026-08-24 — fixture expansion and quota readiness

1. Expand sanitized authoritative fixtures across representative FixList cases:
   - redirects/internal links;
   - metadata/content;
   - indexability/robots;
   - canonical/structured-data technical fixes;
   - limited/no-high-confidence cases that must remain honest;
   - follow-up/DIY questions using conversation history.
2. Keep the production prompt contract as the baseline; do not copy the older HF Space prompt.
3. Confirm current project access/quota readiness for `xai/grok-4.20-reasoning` without changing live feature flags.
4. Freeze candidate identity as `vertex-ai / xai/grok-4.20-reasoning` if availability remains proven.
5. Keep all automated tests network-free.

Exit gate: exact candidate identity, prompt/evidence contract, and evaluation fixtures are frozen.

## Tuesday 2026-08-25 — offline comparison gate

Run the same sanitized authoritative fixtures through current non-reasoning and reasoning candidates outside the customer request path.

Record per case:

- authority manifest hash;
- provider evidence hash;
- exact model ID;
- latency;
- success/error class;
- grounded URL/count/finding checks;
- human usefulness score;
- whether reasoning materially improves prioritization/explanation rather than merely producing longer answers.

Reject the candidate if it invents scan evidence, weakens authority language, materially regresses usefulness, creates unacceptable latency/failure behavior, or gives no meaningful product benefit.

Exit gate: reasoning is good enough to justify a production model-selection adapter proposal. If not, Wednesday/Thursday becomes continued lab work rather than deployment.

## Wednesday 2026-08-26 — preferred integration day

Only if all earlier gates pass:

1. Refresh from then-current `main` and run full exact-SHA baseline CI.
2. Create a **separate production adapter PR**; do not make `experiments/provider_lab` a runtime dependency.
3. Extract current Vertex transport behind the smallest model-selection/provider interface necessary.
4. Preserve `xai/grok-4.20-non-reasoning` as the customer-facing default and rollback.
5. Add `xai/grok-4.20-reasoning` only as disabled/shadow-capable model selection.
6. Keep `GROK_CHAT_ENABLED=false`.
7. Keep `GROK_PROXY_ENABLED=false`.
8. Add no new inference provider, no HF token, and no new authority path.
9. Prove candidate failures cannot mutate ScanRun/FixList/FixItem authority or terminal state.
10. Run full Standard 150 security/durability/release regressions.
11. Build the exact production image.

No customer traffic is required on Wednesday.

## Thursday 2026-08-27 — deployment verification / optional internal shadow day

Only if Wednesday integration is fully green:

1. Stage exact candidate at **0% traffic** using the existing owner-only release tooling.
2. Verify image digest, source SHA, Cloud Run revision, Base44 public-release revision, queue state, and rollback revision.
3. Confirm both Grok switches remain OFF.
4. Verify Standard 150 canaries are unaffected.
5. Verify rollback to non-reasoning/off requires no data migration, resealing, or scan replay.
6. If explicitly approved, perform a tightly controlled internal reasoning shadow after the Base44 authority gate; non-reasoning remains user-facing.
7. Do not make reasoning customer-facing on the first deployment day.

## Hard GO gates

All must be true:

- exact candidate SHA has fully green CI;
- provider-lab parity/comparison suite green;
- full Standard 150 regressions green;
- production image built from exact SHA;
- authority validation still precedes any model call;
- both Grok switches proven default-off;
- model selection cannot write authoritative scan state;
- exact rollback path captured and tested;
- no unclassified regression failure;
- exact reasoning model identity and project quota/access readiness recorded;
- offline reasoning quality is at least as grounded as non-reasoning and materially useful.

## Automatic HOLD conditions

Any one of these moves integration/deployment out of the Wednesday/Thursday window:

- current `main` changes protected scanner architecture without fresh certification;
- lab or production adapter touches crawler/worker/admission/persistence/authority code unnecessarily;
- exact-head CI is red or missing;
- reasoning quality is materially below current non-reasoning behavior;
- reasoning adds unacceptable latency/reliability cost without product benefit;
- model identity or access is ambiguous;
- live serving revision or rollback target cannot be proven;
- either Grok kill switch cannot be proven OFF before staging.

## Separate Hugging Face inference lane

Do not combine a new HF Inference Provider with the first reasoning integration. If we later evaluate an HF-hosted open model, it gets its own lab identity, credentials, offline comparison, failure model, and production review.

## Rollback principle

Rollback must be model-only / feature-only:

```text
reasoning shadow -> non-reasoning only -> Grok fully OFF
```

No rollback may require rebuilding scan evidence, mutating FixLists, resealing authority snapshots, or replaying Standard 150 scans.
