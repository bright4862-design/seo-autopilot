# FixList Public Blog + Daily Publisher Design

Date: 2026-09-12
Branch: `feature/public-blog-daily-content-20260912`

## Goal

Add a customer-facing, indexable FixList blog that is reachable from the public landing page and can publish one useful SEO article per day without touching the Standard 150 scan pipeline.

The blog should support organic acquisition and product education. It must feel like a credible editorial surface rather than an automated content dump.

## Scope

### Public experience

- Add a public `/blog` route that lists published articles newest first.
- Add a public `/blog/:slug` route for individual articles.
- Add a visible `Blog` link to the landing-page navigation.
- Keep blog pages accessible without authentication.
- Match the existing FixList public visual language: narrow readable content width, restrained typography, simple navigation, and clear conversion path back to product access.
- Render article title as the single H1 and article Markdown below it.
- Show publication date, category, and optional tags without adding unnecessary UI.
- Only render records where `status = published`.

### Content model

Use a Base44 `BlogPost` entity with public read access and admin-only create/update/delete access.

Fields:

- `title`
- `slug`
- `excerpt`
- `body_markdown`
- `meta_title`
- `meta_description`
- `category`
- `tags`
- `author`
- `status` (`draft`, `published`, `archived`)
- `published_at`
- `generation_key`
- `generation_source` (`manual`, `daily_automation`)

`slug` is treated as the stable public article identifier. The daily publisher checks collisions before creating a post.

### Daily publisher

Add a Base44 backend function `generateDailyBlog` with a daily scheduled automation.

The publisher:

1. Builds a deterministic daily `generation_key` so retries cannot create multiple articles for the same day.
2. Reads recent published titles to reduce repetition.
3. Rotates through a curated evergreen topic set centered on practical technical SEO and website-health problems relevant to FixList customers.
4. Uses Base44's built-in LLM integration to generate a structured article object.
5. Applies a minimum quality gate before publication.
6. Publishes only after the gate passes; otherwise the run fails and publishes nothing.
7. Stores the post as `generation_source = daily_automation`.

Initial editorial constraints:

- Practical, specific, non-clickbait writing.
- No invented studies, statistics, case studies, rankings, quotes, customer outcomes, or named examples.
- No claim that FixList changes customer websites automatically.
- Distinguish confirmed technical issues from recommendations requiring human judgment.
- Light promotion only; the article must stand on its own as useful content.
- No competitor callouts.
- No keyword stuffing.
- No H1 in generated Markdown because the article page owns the H1.
- Target approximately 1,100–1,600 words, with a hard minimum publication gate of 800 words.

The system is not designed to evade AI-detection tools or disguise authorship. The quality strategy is original topic selection, concrete explanations, repetition controls, factual restraint, and editorial consistency.

## Isolation and safety

The blog subsystem must remain independent from the scanner path.

It must not change:

- Standard 150 crawl behavior
- admission controls
- scanner/worker functions
- scan persistence or authority sealing
- robots/SSRF protections
- payment/access logic
- scan-history correctness

Blog failures must not affect customer scanning. A failed daily generation simply results in no article that day.

## Frontend data flow

### Blog index

`/blog` reads published `BlogPost` rows through the existing Base44 frontend client, sorts newest first, and renders compact article cards containing title, excerpt, date, and category.

Expected states:

- loading
- published posts available
- no posts yet
- read failure with a simple customer-facing message

### Blog article

`/blog/:slug` filters `BlogPost` by `slug`, selects the published record, and renders it with `react-markdown`, which is already present in the project dependencies.

Expected states:

- loading
- published post found
- missing/unpublished post -> simple not-found view with link back to `/blog`
- read failure -> non-technical error state

## Metadata

Because the app is a Vite SPA, the first implementation will set document-level metadata client-side on article render:

- `document.title` from `meta_title` or article title
- standard meta description from `meta_description` or excerpt

The implementation should not introduce speculative SSR/prerender architecture in this change. If later SEO evidence shows crawler rendering/indexation is insufficient, static prerendering can be handled as a separate release.

## Landing-page integration

Update the public landing navigation to include `Blog` alongside FAQ and login/access controls. Do not add blog links to authenticated product navigation unless there is a clear customer need.

The landing-page product contract remains unchanged: Standard 150, current access pricing, and existing scan promises stay exactly as certified.

## Testing

Add focused frontend contract coverage for:

- `/blog` public route exists.
- `/blog/:slug` public route exists.
- blog routes are outside `ProtectedRoute`.
- landing page contains a visible `/blog` link.
- public blog surfaces do not mention unreleased Grok/Premium features.
- article rendering filters to `status = published`.

Add function/source contract coverage for:

- daily automation is present and active.
- generation key prevents duplicate daily publication.
- only quality-gated content is created as `published`.
- publisher does not import or invoke scan functions.

Before merge, run:

- `npm run lint`
- `npm run typecheck`
- `npm run test:frontend`
- `npm run build`
- focused tests for the new blog/publisher contracts

## Deployment and release discipline

Do not merge or deploy directly from an unverified feature branch.

Required sequence:

1. finish implementation on the isolated branch;
2. run focused and repository tests;
3. open a PR to `main`;
4. review the diff for scanner/product isolation;
5. merge only after CI is green;
6. deploy through the existing guarded Base44 release process rather than bypassing release provenance;
7. verify production `/blog`, one article page, landing-page navigation, and that Standard 150 remains unaffected.

## Current branch state

Already staged on the isolated branch before this design was finalized:

- `base44/entities/BlogPost.jsonc`
- `base44/functions/generateDailyBlog/entry.ts`
- `base44/functions/generateDailyBlog/function.jsonc`

These files remain subject to implementation review and test changes before merge. No public blog route or landing-page link has been added yet.

## Definition of done

The feature is ready for merge when:

- anonymous visitors can open `/blog` and `/blog/:slug`;
- the landing page links to `/blog`;
- only published posts are visible;
- daily generation is idempotent and fails closed on weak output;
- blog failure cannot break scanning;
- frontend/build tests are green;
- the diff contains no unrelated Standard 150 changes;
- production is verified after the normal guarded deployment flow.
