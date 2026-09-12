import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { base44 } from "@/api/base44Client";

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export default function Blog() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "FixList Blog — Practical SEO and website health guides";

    let active = true;
    async function loadPosts() {
      try {
        const rows = await base44.entities.BlogPost.filter(
          { status: "published" },
          "-published_at",
          50,
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
      document.title = previousTitle;
    };
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-6 pb-24">
        <nav className="flex items-center justify-between pt-7">
          <Link to="/" className="text-[15px] font-semibold tracking-tight">
            FixList
          </Link>
          <div className="flex items-center gap-5">
            <Link to="/" className="text-[13px] text-ink-muted transition-colors hover:text-ink">
              Home
            </Link>
            <Link to="/login" className="text-[13px] text-ink-muted transition-colors hover:text-ink">
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Get access
            </Link>
          </div>
        </nav>

        <main className="mt-20">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
            FixList Blog
          </p>
          <h1 className="mt-4 text-[32px] font-semibold leading-tight tracking-tight sm:text-[38px]">
            Practical SEO fixes, explained clearly.
          </h1>
          <p className="mt-4 max-w-[54ch] text-[15px] leading-relaxed text-ink-muted">
            Guides for understanding website health, verifying SEO problems, and deciding what is actually worth fixing first.
          </p>

          {loading ? (
            <div className="mt-12 border-t border-hairline-soft py-6 text-[13px] text-ink-faint">
              Loading articles…
            </div>
          ) : failed ? (
            <div className="mt-12 border-t border-hairline-soft py-6">
              <p className="text-[14px] leading-relaxed text-ink-muted">
                The blog is temporarily unavailable. Please try again shortly.
              </p>
              <Link to="/" className="mt-4 inline-block text-[13px] font-medium underline underline-offset-4">
                Back to FixList
              </Link>
            </div>
          ) : posts.length === 0 ? (
            <div className="mt-12 border-t border-hairline-soft py-6">
              <p className="text-[14px] leading-relaxed text-ink-muted">
                No articles have been published yet. Check back soon.
              </p>
            </div>
          ) : (
            <div className="mt-12 border-t border-hairline-soft">
              {posts.map((post) => (
                <article key={post.id || post.slug} className="border-b border-hairline-soft py-7">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-faint">
                    {post.category ? <span>{post.category}</span> : null}
                    {post.category && post.published_at ? <span>·</span> : null}
                    {post.published_at ? <time>{formatDate(post.published_at)}</time> : null}
                  </div>
                  <h2 className="mt-2 text-[20px] font-medium leading-snug tracking-tight">
                    <Link
                      to={`/blog/${post.slug}`}
                      className="transition-colors hover:text-ink-muted"
                    >
                      {post.title}
                    </Link>
                  </h2>
                  {post.excerpt ? (
                    <p className="mt-3 text-[14px] leading-relaxed text-ink-muted">
                      {post.excerpt}
                    </p>
                  ) : null}
                  <Link
                    to={`/blog/${post.slug}`}
                    className="mt-4 inline-block text-[13px] font-medium text-ink"
                  >
                    Read article →
                  </Link>
                </article>
              ))}
            </div>
          )}
        </main>

        <footer className="mt-20 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          FixList turns website scan findings into a prioritized, plain-English list of what to fix first.
        </footer>
      </div>
    </div>
  );
}
