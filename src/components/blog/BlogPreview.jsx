import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { base44 } from "@/api/base44Client";

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export default function BlogPreview() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadPosts() {
      try {
        const rows = await base44.entities.BlogPost.filter(
          { status: "published" },
          "-published_at",
          3,
        );
        if (active) setPosts(Array.isArray(rows) ? rows : []);
      } catch {
        if (active) setFailed(true);
      } finally {
        if (active) setLoading(false);
      }
    }

    loadPosts();
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="mt-24" aria-labelledby="latest-from-fixlist">
      <div className="flex items-baseline justify-between gap-4">
        <div
          id="latest-from-fixlist"
          className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint"
        >
          Latest from FixList
        </div>
        <Link
          to="/blog"
          className="text-[12px] text-ink-muted transition-colors hover:text-ink"
        >
          View all articles
        </Link>
      </div>

      {loading ? (
        <div className="mt-4 border-b border-hairline-soft pb-4 text-[13px] text-ink-faint">
          Loading articles…
        </div>
      ) : posts.length > 0 ? (
        <div className="mt-2">
          {posts.map((post) => (
            <article key={post.id || post.slug} className="border-b border-hairline-soft py-5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-faint">
                {post.category ? <span>{post.category}</span> : null}
                {post.category && post.published_at ? <span>·</span> : null}
                {post.published_at ? <time>{formatDate(post.published_at)}</time> : null}
              </div>
              <h2 className="mt-2 text-[17px] font-medium leading-snug tracking-tight">
                <Link
                  to={`/blog/${post.slug}`}
                  className="transition-colors hover:text-ink-muted"
                >
                  {post.title}
                </Link>
              </h2>
              {post.excerpt ? (
                <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
                  {post.excerpt}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 border-b border-hairline-soft pb-5">
          <p className="text-[13px] leading-relaxed text-ink-muted">
            {failed
              ? "The latest articles are temporarily unavailable here."
              : "Practical notes on technical SEO, crawl health, and deciding what to fix first."}
          </p>
          <Link
            to="/blog"
            className="mt-3 inline-block text-[13px] font-medium text-ink underline decoration-hairline underline-offset-4"
          >
            Browse the blog
          </Link>
        </div>
      )}
    </section>
  );
}
