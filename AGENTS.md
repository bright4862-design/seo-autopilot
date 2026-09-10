# AGENTS.md

## Project Context

This is a Base44 app repository. Treat it as user-owned application code, keep changes focused on the user's request, and preserve existing project conventions.

Start with `README.md` for local setup, environment variables, and publish workflow.

## Base44 References

- CLI overview: https://docs.base44.com/developers/references/cli/get-started/overview.md
- Agent skills: https://docs.base44.com/developers/backend/overview/skills.md

If your agent supports Agent Skills, install or update Base44 skills before Base44-specific work:

```bash
npx skills add base44/skills
```

## Key Files

- `src/`: frontend application source.
- `src/api/base44Client.js`: frontend Base44 SDK client.
- `vite.config.js`: Vite config and Base44 Vite plugin setup.
- `.env.local`: local-only environment values; never commit secrets.

## Working Notes

- Use `base44 dev` as the default local development command when you need the local Base44 backend. It can run the backend and frontend together.
- When docs or code mention the frontend being started automatically, that usually means the Base44 project config includes `site.serveCommand`, for example `"serveCommand": "npm run dev"` in `base44/config.jsonc`.
- Use `npm run dev` only for frontend-only work against the hosted Base44 backend.
- Prefer the existing Base44 CLI workflow over adding new npm scripts for Base44-specific tasks.
- Reuse the existing SDK client and Vite plugin patterns before adding new Base44 integration paths.
- Run the relevant checks from `package.json` before finishing code changes.


## FixList Autonomous Operating Contract

This repository may be worked on by autonomous or semi-autonomous AI agents. For FixList release and product work, this section takes precedence over generic agent behavior while preserving the Base44 guidance above.

### Startup protocol

Before editing code, every agent must:

1. Read `agent/STATE.json`.
2. Read `agent/RELEASE_GATES.json`.
3. Read `agent/WORK_QUEUE.json`.
4. Read `agent/AUTONOMY_POLICY.md`.
5. Refresh time-sensitive repository facts from GitHub before relying on them.
6. If working on a PR, verify the exact head SHA before editing or claiming verification.

If recorded state conflicts with the live repository, the live repository wins and the recorded state must be corrected in the same workstream.

### Priority loop

Work in this order:

1. Production safety or customer-data risk.
2. Active release blockers, highest severity first.
3. Patches awaiting verification.
4. CI or review failures on the active release candidate.
5. Release acceptance and same-SHA proof.
6. Post-release regressions.
7. Product reliability and trust weaknesses.
8. Lower-risk product improvements.

Do not create speculative patches when a defect has not been reproduced or strongly evidenced.

### Definition of done

A defect fix is not complete until all applicable items are true:

- defect reproduced or evidence documented;
- root cause identified;
- smallest safe change implemented;
- a regression demonstrates the old failure when practical;
- focused tests pass;
- broad affected suites pass;
- release identity / generated contracts remain consistent;
- remote exact SHA is verified after publication;
- independent review findings are addressed;
- `agent/STATE.json` and `agent/WORK_QUEUE.json` are updated.

If any required item is missing, report the work as incomplete.

### Safety boundaries

Agents may autonomously investigate, read, test, create branches, commit to agent branches, and open draft PRs.

Agents must not autonomously:

- merge to `main`;
- deploy production;
- mutate production billing or pricing;
- delete production customer data;
- enable Grok;
- enable Premium 5,000;
- weaken robots, SSRF, ownership, HMAC, authentication, authorization, idempotency, or resource-safety boundaries;
- change production IAM or secrets.

Those actions require explicit owner approval.

### Release discipline

A green CI run is necessary but not sufficient for GO. A release is GO only when every required gate in `agent/RELEASE_GATES.json` is `passed` for the same immutable release identity.

Any release-candidate SHA movement invalidates prior exact-head verification until rerun.

Unknown integrity versions, incomplete authority evidence, ambiguous ownership, and unverified release identity must fail closed.

### Communication discipline

Do not send routine noise. Surface new P0/P1 findings, release-candidate movement, failed or recovered CI, review findings that change GO/NO-GO, actions requiring owner approval, and material production regressions.

If nothing meaningful changed, continue work or monitoring without manufacturing an update.
