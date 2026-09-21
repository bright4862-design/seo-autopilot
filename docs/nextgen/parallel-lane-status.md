# NextGen parallel lane status — 2026-09-21

Integration branch: `nextgen/integration-20260921`
Integration tracker: #327

| Lane | Issue | Branch | Draft PR | Status at launch |
| --- | --- | --- | --- | --- |
| A Adaptive Crawl | #322 | `agent/nextgen-adaptive-crawl-20260921` | #328 | Claude Code running |
| B Semantic Graph | #323 | `agent/nextgen-semantic-graph-20260921` | #329 | Claude Code running |
| C Browser / Performance | #324 | `agent/nextgen-browser-performance-20260921` | #331 | Claude Code running |
| D Evidence Connectors | #325 | `agent/nextgen-evidence-connectors-20260921` | #332 | Claude Code running |
| E Fix Verification | #326 | `agent/nextgen-fix-verification-20260921` | #330 | Claude Code running |

## Governance

- No lane merges directly to main.
- No lane may deploy/publish or mutate production.
- Shared integration surfaces remain serialized under #327.
- The current B01–B28 release remains authoritative and independent.
- Integration begins only after lane tests and review.
- Feature exposure remains shadow/owner-only until next-gen acceptance gates exist.

## Integration order

A → B → C → D → E, with full relevant regression checks after each transplant.

This status file is coordination evidence only; it does not claim any lane is complete or accepted.
