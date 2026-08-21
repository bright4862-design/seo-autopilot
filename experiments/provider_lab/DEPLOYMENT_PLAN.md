# Tentative Grok Provider Integration Plan

Target window: **Wednesday 2026-08-26 or Thursday 2026-08-27**.

This is a planning document only. It does not authorize deployment or feature enablement.

## Goal

Introduce provider abstraction and, if offline evidence is strong enough, a Hugging Face candidate without changing Standard 150 authority or scanner behavior.

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

- provider lab rebuilt from current `main`;
- authority manifest separated from model-facing evidence;
- repair-v2 and valid legacy authority fixtures covered;
- current compact Base44 provider payload captured;
- current Vertex transport contract captured;
- no network-capable HF code;
- lab remains outside production scanner Docker context.

## Weekend / Monday 2026-08-24 — parity and candidate selection

1. Add recorded Vertex success/error fixtures.
2. Reproduce current output extraction and retry/error classification in the lab.
3. Add grounding assertions for URLs/counts/findings.
4. Select an exact HF model **and exact inference provider**.
5. Add HF request/response contract behind a lab-only fake transport first.
6. Do not add secrets to the repository.

Exit gate: Vertex parity green and candidate identity frozen.

## Tuesday 2026-08-25 — offline comparison gate

Run sanitized authoritative fixtures through the candidate outside the customer request path.

Record per case:

- authority manifest hash;
- provider evidence hash;
- provider name;
- exact model ID;
- latency;
- success/error class;
- grounded URL/count/finding checks;
- human usefulness score.

Reject the candidate if it invents scan evidence, weakens authority language, materially regresses usefulness, or has unstable failures.

Exit gate: candidate is good enough to justify a production adapter proposal. If not, Wednesday/Thursday becomes continued lab work rather than deployment.

## Wednesday 2026-08-26 — preferred integration day

Only if all earlier gates pass:

1. Refresh from then-current `main` and run full exact-SHA baseline CI.
2. Create a **separate production adapter PR**; do not merge the provider lab package into runtime.
3. Extract current Vertex transport behind the smallest provider interface.
4. Keep Vertex as the default provider.
5. Keep `GROK_CHAT_ENABLED=false`.
6. Keep `GROK_PROXY_ENABLED=false`.
7. Add HF only as disabled/shadow-capable adapter code.
8. Prove provider failures cannot mutate ScanRun/FixList/FixItem authority.
9. Run full Standard 150 security/durability/release regressions.
10. Build the exact production image.

No customer traffic is required on Wednesday.

## Thursday 2026-08-27 — deployment verification / optional shadow day

Only if Wednesday integration is fully green:

1. Stage exact candidate at **0% traffic**.
2. Verify image digest, source SHA, Cloud Run revision, Base44 public-release revision, queue state, and rollback revision.
3. Confirm both Grok switches remain OFF.
4. Verify existing Standard 150 canaries are unaffected.
5. Verify rollback to the prior Vertex-only/off configuration requires no data migration, resealing, or scan replay.
6. If an explicitly approved internal shadow is enabled later, route only already-authoritative Grok requests after the Base44 authority gate; Vertex remains user-facing.

Do not make HF customer-facing on the first deployment day.

## Hard GO gates

All must be true:

- exact candidate SHA has fully green CI;
- provider lab parity suite green;
- full Standard 150 regressions green;
- production image built from exact SHA;
- authority validation still precedes any provider call;
- both Grok switches proven default-off;
- no provider can write authoritative scan state;
- exact rollback path captured and tested;
- no unclassified regression failure;
- exact HF model/provider identity recorded.

## Automatic HOLD conditions

Any one of these moves integration/deployment out of the Wednesday/Thursday window:

- current `main` changes protected scanner architecture without fresh certification;
- provider lab or production adapter touches crawler/worker/admission/persistence/authority code unnecessarily;
- exact-head CI is red or missing;
- HF candidate quality is materially below current Vertex behavior;
- model/provider identity is ambiguous;
- secrets/IAM cannot be isolated to the provider adapter;
- live serving revision or rollback target cannot be proven;
- either Grok kill switch cannot be proven OFF before staging.

## Rollback principle

Rollback must be provider-only:

```text
HF candidate/shadow -> Vertex-only -> Grok fully OFF
```

No rollback may require rebuilding scan evidence, mutating FixLists, resealing authority snapshots, or replaying Standard 150 scans.
