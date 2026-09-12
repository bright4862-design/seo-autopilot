import { createClientFromRequest } from "npm:@base44/sdk@0.8.48";

const TOPIC_THEMES = [
  "how to prioritize technical SEO fixes after an audit",
  "crawlability problems that keep useful pages out of search",
  "redirect chains, loops, and redirects to the wrong destination",
  "canonical tags and choosing the official version of a page",
  "internal linking problems that hide important pages",
  "XML sitemap health and what a sitemap can and cannot fix",
  "indexability checks for small-business websites",
  "duplicate titles and title-tag cleanup",
  "meta descriptions: when they matter and when they do not",
  "404 pages, broken internal links, and practical cleanup",
  "robots.txt mistakes and safe crawl-control decisions",
  "multi-location SEO architecture for local businesses",
  "duplicate or overlapping service pages",
  "image alt text: accessibility first, SEO second",
  "SEO checks after a website redesign or migration",
  "how to read an SEO health score without chasing vanity metrics",
  "what to verify before changing a page because of an SEO tool",
  "thin pages versus genuinely useful concise pages",
  "template-level SEO problems versus one-off page problems",
  "JavaScript-heavy websites and crawl/indexation checks",
  "how to separate confirmed SEO problems from recommendations",
  "website audit evidence: what counts as proof before making a fix",
  "how small businesses can work through an SEO fix list",
  "when a technical SEO issue needs a developer versus a marketer",
];

function slugify(value: string) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 90);
}

function wordCount(value: string) {
  return String(value || "").trim().split(/\s+/).filter(Boolean).length;
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const now = new Date();
    const dayKey = now.toISOString().slice(0, 10);
    const generationKey = `daily:${dayKey}`;

    const existingForDay = await base44.asServiceRole.entities.BlogPost.filter(
      { generation_key: generationKey },
      "-published_at",
      1,
    );
    if (existingForDay.length > 0) {
      return Response.json({
        success: true,
        skipped: true,
        reason: "already_published_for_day",
        post_id: existingForDay[0].id,
        slug: existingForDay[0].slug,
      });
    }

    const recentPosts = await base44.asServiceRole.entities.BlogPost.filter(
      { status: "published" },
      "-published_at",
      60,
    );
    const recentTitles = recentPosts
      .map((post: any) => String(post?.title || "").trim())
      .filter(Boolean)
      .slice(0, 30);

    const dayNumber = Math.floor(now.getTime() / 86_400_000);
    const theme = TOPIC_THEMES[dayNumber % TOPIC_THEMES.length];

    const article = await base44.integrations.Core.InvokeLLM({
      prompt: `Write one high-quality evergreen article for the FixList blog.

Audience: small-business owners, marketers, and operators who know they need SEO help but do not want a giant technical audit.
Theme for today: ${theme}

FixList product facts you may state:
- FixList is a read-only website health tool.
- Standard 150 checks up to 150 pages per scan.
- It turns findings into a prioritized, plain-English list of what to fix first.
- FixList should never be described as changing a customer's website automatically.

Editorial rules:
- Be practical, specific, calm, and useful.
- Explain what is wrong, why it matters, how to verify it, and what to do next.
- Distinguish confirmed technical problems from recommendations that require human judgment.
- Do not invent statistics, studies, case studies, customer results, rankings, quotes, or named examples.
- Do not claim a Google rule, ranking factor, or industry benchmark unless it is common stable knowledge and can be explained without a number.
- Do not keyword-stuff or write filler.
- Do not mention competitors.
- Do not use clickbait.
- Do not include an H1 in the Markdown body; the page renders the article title as H1.
- Use H2/H3 headings, short paragraphs, bullets where useful, and a concise conclusion.
- Keep promotional language light. A short final paragraph may explain how FixList helps.
- Aim for 1,100 to 1,600 words.

Avoid duplicating these recent FixList article titles:
${recentTitles.length ? recentTitles.map((title: string) => `- ${title}`).join("\n") : "- none yet"}

Return only the requested structured fields.`,
      response_json_schema: {
        type: "object",
        required: [
          "title",
          "excerpt",
          "body_markdown",
          "meta_title",
          "meta_description",
          "category",
          "tags",
        ],
        properties: {
          title: { type: "string" },
          excerpt: { type: "string" },
          body_markdown: { type: "string" },
          meta_title: { type: "string" },
          meta_description: { type: "string" },
          category: { type: "string" },
          tags: { type: "array", items: { type: "string" } },
        },
      },
    });

    const title = String(article?.title || "").trim();
    const excerpt = String(article?.excerpt || "").trim();
    const bodyMarkdown = String(article?.body_markdown || "").trim();
    const metaTitle = String(article?.meta_title || title).trim();
    const metaDescription = String(article?.meta_description || excerpt).trim();
    const category = String(article?.category || "Technical SEO").trim();
    const tags = Array.isArray(article?.tags)
      ? article.tags.map((tag: unknown) => String(tag || "").trim()).filter(Boolean).slice(0, 6)
      : [];

    if (!title || !excerpt || !bodyMarkdown || wordCount(bodyMarkdown) < 800) {
      return Response.json(
        {
          success: false,
          error_code: "generated_article_failed_quality_gate",
          error: "The generated article did not meet the minimum publication quality gate.",
        },
        { status: 422 },
      );
    }

    let slug = slugify(title);
    if (!slug) slug = `seo-guide-${dayKey}`;
    const slugCollision = await base44.asServiceRole.entities.BlogPost.filter(
      { slug },
      "-published_at",
      1,
    );
    if (slugCollision.length > 0) slug = `${slug}-${dayKey}`;

    const created = await base44.asServiceRole.entities.BlogPost.create({
      title: title.slice(0, 120),
      slug,
      excerpt: excerpt.slice(0, 320),
      body_markdown: bodyMarkdown,
      meta_title: metaTitle.slice(0, 70),
      meta_description: metaDescription.slice(0, 160),
      category: category.slice(0, 80),
      tags,
      author: "FixList",
      status: "published",
      published_at: now.toISOString(),
      generation_key: generationKey,
      generation_source: "daily_automation",
    });

    return Response.json({
      success: true,
      skipped: false,
      post_id: created.id,
      slug: created.slug,
      title: created.title,
    });
  } catch (error) {
    console.error("generateDailyBlog failed", error);
    return Response.json(
      {
        success: false,
        error_code: "daily_blog_generation_failed",
        error: "Daily blog generation failed.",
      },
      { status: 500 },
    );
  }
});
