# Architecture correction checkpoint, 12 November 2026

Base: `c7d71a0272866f03795862bad76cc502a51c46ca`. Candidate fingerprint:
`118544dcf77d86cf`. This is an offline implementation checkpoint. It does not
record a deployment, accepted release, public reopening, or successful live scan.

## Corrected behavior

- Commercial reserves and quota filling share the feasible 40% section ceiling.
  Existing real section hubs are reserved even when navigation leaves already
  satisfy that section's numerical floor. When the inventory cannot fill the
  budget under the ceiling, existing commercial sampling remains available.
- Synchronous `/scan` refuses `standard_500` before network work. Larger scans
  continue through the server-authorized staged path.
- Cached staged review keeps its aggregate parent/child RSS measurement; finalize
  can raise the peak with a later sample, but never sums unrelated process peaks.
  Missing V9 measurements remain unverified. This is not whole-scan peak proof.
- New V9 shortlists select after signed Stage 3 factors attach, use signed root
  identities, and preserve a real owner action when available. Explicit developer
  restrictions win over effort or contradictory labels. Historical stored
  shortlists reconstruct under their original HMAC bytes.
- The staged schema tool permits only reviewed additive fields and scan-mode
  widening. It preserves live RLS and unrelated schema content, rereads all four
  entities around each named PUT, and refuses rollback with retained staged data,
  active scans, 500 grants, or incomplete row inventories. It grants no access.
- Gateway staging is an explicit owner-canary option. Enabling it requires a
  freshly verified zero-owner gateway from the same source, exact cohort
  confirmation, actual revision environment readback and runtime cohort hash.
  Default deployment clears staging. New rollback baselines verify that hash.

## Offline evidence

| Gate | Current evidence |
|---|---|
| Repository Python | 532 passed |
| Scanner Python | 2,619 passed, 18 skipped |
| Gateway Python | 51 passed |
| Corrected frontend, shortlist, release contracts and schema lane | 81 passed on Node 20.19.5 |
| Gateway deployment/configuration review | Independent review; 113 focused tests passed |
| Schema migration review | Independent review; 26 focused tests passed |
| Lint, type checking, production build | Passed; build retains its existing large-chunk warning |
| Full frontend suite | 2,115 passed; 10 macOS temp-alias fixture failures passed focused reruns with canonical TMPDIR; separate unfinished 500 module is tracked independently |

The original integrated frontend run was not green: it also encountered an unfinished
500-tooling import. The ten canary failures arose from macOS `/var` aliases in test
fixtures; all passed focused reruns with `TMPDIR=/private/tmp`. One initial rerun
exceeded a six-second fixture timeout and passed in isolation. Production guards
were not weakened. CI on the committed source remains required.

The full-engine checkpoint harness compares complete raw results, request order,
review/completion bytes and HMAC for uninterrupted execution versus JSON restore
after planning and every batch. Five synthetic network cases pass, including a
redirect merge across a checkpoint and robots handling. No result fields are
stripped. These fixtures are not captures of live reference sites.

Historical extraction parity is still unestablished: reachable history combines
selection, extraction, frontier and cap changes in one commit. Current checkpoint
parity does not establish equivalence to a missing intermediate historical build.
Universal first-pass coverage by 30% is infeasible when required heads and
navigation pages exceed that cutoff; the feasible 500-page case is tested.

## First staged 150 scan

| Required gate | State |
|---|---|
| Correctness patch and exact-source CI | Local evidence above; review/merge pending |
| Explicit worker owner cohort | Separate [PR #411](https://github.com/bright4862-design/seo-autopilot/pull/411); independently refresh its state |
| Stage queue activation/recovery | Separate [PR #414](https://github.com/bright4862-design/seo-autopilot/pull/414); review and integration pending |
| Base44 V9 owner publication and deployed package readback | Unavailable locally; owner authentication required |
| Additive live schema migration/readback | Tool ready; not applied |
| GCP stage bucket/queue/IAM bootstrap/readback | Historical bootstrap was partial; fresh administrator evidence required |
| Base44 staged cohort runtime visibility/configuration | Separate integration lane; not proved by function publication |
| Exact-source inactive worker, owner gateway route, queue/OIDC and bounded admission | Live verification pending |
| One signed staged-150 result, progress, recovery and customer reopening | Not run |

The first 150 scan can use owner-canary routing with gateway staged validation
off. Enabling 500 is a separate gate. Public admission remains controlled by the
existing release and admission procedures. Refresh all live state; the dated
[bootstrap blocker record](staged-rollout-blockers-2026-11-11.md) is historical.

The entitled-500/corpus runner is a separate workstream. A truthful throttled
limited outcome cannot satisfy a complete-500 gate. Completion payload tolerance,
whole staged-scan memory, four live reference sites and the reviewed 50-site
corpus still need empirical evidence. Phase 7 and the roadmap's future product
extensions remain outside this checkpoint.
