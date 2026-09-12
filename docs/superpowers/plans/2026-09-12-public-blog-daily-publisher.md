# FixList Public Blog + Daily Publisher Implementation Plan

Date: 2026-09-12
Branch: `feature/public-blog-daily-content-20260912`
Design: `docs/superpowers/specs/2026-09-12-public-blog-daily-publisher-design.md`

## Objective

Add a public FixList blog without touching Standard 150 behavior. The landing page shown by the user will expose the blog in two places: a visible `Blog` link in the top navigation and a compact `Latest from FixList` section immediately before the FAQ. Full public routes `/blog` and `/blog/:slug` will show all published posts and individual articles.

## Task 1 — Pin the public-blog contract first

Create `tests/frontend/publicBlogSurface.test.mjs` before adding frontend implementation.

The test must fail on the current branch and assert:

- `src/App.jsx` imports public `Blog` and `BlogArticle` pages.
- `/blog` and `/blog/:slug` routes exist in the public-pages block, before `ProtectedRoute`.
- `src/pages/Landing.jsx` contains a visible `to="/blog"` nav link.
- Landing renders a `BlogPreview` component before the FAQ section.
- `BlogPreview` queries only `status: "published"` posts and limits the landing preview to three.
- `Blog.jsx` queries published posts and links each article to `/blog/<slug>`.
- `BlogArticle.jsx` filters by both `slug` and `status: "published"` and renders Markdown.
- public blog surfaces do not advertise unreleased Grok/Premium features.
- the daily publisher contains its daily generation key, minimum-quality gate, and published-only create path and contains no imports/invocations of scanner functions.

Commit the failing contract by itself.

## Task 2 — Add the public routes and landing-page integration

Create:

- `src/components/blog/BlogPreview.jsx`
- `src/pages/Blog.jsx`
- `src/pages/BlogArticle.jsx`

Modify:

- `src/App.jsx`
- `src/pages/Landing.jsx`

Implementation details:

### Landing page

- Add `Blog` to the top navigation between FAQ and Log in.
- Add `<BlogPreview />` immediately before `<section id="faq">`.
- Preserve the current hero, pricing/access copy, FAQ, width, typography, and Standard 150 contract.
- `BlogPreview` fetches the latest three `BlogPost` records with `status: "published"`, newest first.
- If posts exist, render date/category, title, excerpt, and article links plus `View all articles`.
- If there are no posts, render a restrained `Latest from FixList` section with a `Browse the blog` link so the landing-page navigation remains useful.
- If the read fails, do not surface technical errors and do not break the landing page; render only the blog heading/link or fail quietly.

### `/blog`

- Public, no auth guard.
- Read published BlogPost rows newest first.
- Match the existing narrow FixList public aesthetic.
- Include FixList home link, Log in, and Get access.
- Render loading, empty, normal, and friendly failure states.
- Link every article using its stored slug.

### `/blog/:slug`

- Public, no auth guard.
- Filter `BlogPost` using `{ slug, status: "published" }` and limit one.
- Render exactly one H1 from `title`.
- Render `body_markdown` with the already-installed `react-markdown` dependency.
- Add readable Markdown styling with local Tailwind classes/component overrides; do not add a new styling dependency.
- Show publication date/category and a back-to-blog link.
- Missing/unpublished post gets a simple not-found state, never dashboard redirect.
- Set `document.title` and the standard meta-description tag from the post while mounted, restoring prior values on cleanup.

Commit these frontend changes after the contract exists.

## Task 3 — Validate and tighten the daily publisher

Review the already-staged files:

- `base44/entities/BlogPost.jsonc`
- `base44/functions/generateDailyBlog/entry.ts`
- `base44/functions/generateDailyBlog/function.jsonc`

Keep:

- public read/admin write entity policy;
- one deterministic `daily:YYYY-MM-DD` generation key;
- recent-title repetition guard;
- structured generation;
- 800-word minimum hard publication gate;
- no invented statistics, studies, rankings, quotes, case studies, or customer outcomes;
- no competitor callouts or keyword stuffing;
- one active daily schedule;
- failure = no publication.

Add or adjust only what tests prove is missing. Do not import scan code or share scanner state.

## Task 4 — Prove branch quality

Open a draft PR to `main` once the red test commit exists so CI records the expected failure. After implementation, use the same PR and require current-head green evidence.

Required checks before merge:

- frontend contract suite;
- lint;
- typecheck;
- Vite production build;
- repository CI relevant to changed files;
- compare branch against main and confirm no scanner, worker, admission, persistence, robots/SSRF, payment, or access-contract code changed.

Review the PR patch after CI, not just individual files.

## Task 5 — Merge and guarded Base44 release

Only after CI is green:

1. merge the PR through the normal GitHub path;
2. re-read exact `main` SHA;
3. use the existing guarded Base44 release workflow for the exact main SHA; do not write directly to the live Base44 sandbox as a shortcut;
4. if release tooling requires owner device authorization or a release confirmation token, stop at that gate and request the user's explicit action rather than bypassing it;
5. verify production landing page shows Blog in the nav and `Latest from FixList` before FAQ;
6. verify `/blog` anonymously;
7. verify one `/blog/:slug` article anonymously;
8. verify login/register and Standard 150 entry still work;
9. verify daily BlogPost automation/config is active.

## Definition of done

- Blog is visibly integrated into the exact public landing page the user showed.
- Anonymous visitors can reach `/blog` and article pages.
- Landing-page blog failures cannot break the core sales page.
- Only published posts are exposed.
- Daily publishing is idempotent and quality-gated.
- Scanner/product behavior is untouched.
- CI/build are green on the exact merge candidate.
- Production deployment is tied to the exact merged SHA and verified.
