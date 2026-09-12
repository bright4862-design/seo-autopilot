import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";

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

const markdownComponents = {
  h2: ({ children }) => (
    <h2 className="mb-3 mt-10 text-[23px] font-semibold leading-tight tracking-tight">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-8 text-[18px] font-semibold leading-snug tracking-tight">{children}</h3>
  ),
  p: ({ children }) => <p className="my-4 text-[15px] leading-7 text-ink-muted">{children}</p>,
  ul: ({ children }) => <ul className="my-5 list-disc space-y-2 pl-6 text-[15px] leading-7 text-ink-muted">{children}</ul>,
  ol: ({ children }) => <ol className="my-5 list-decimal space-y-2 pl-6 text-[15px] leading-7 text-ink-muted">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="my-6 border-l-2 border-hairline pl-4 text-[15px] leading-7 text-ink-muted">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a href={href} className="font-medium text-ink underline underline-offset-4">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-ink/[0.04] px-1.5 py-0.5 font-mono text-[0.9em] text-ink">{children}</code>
  ),
};

export default function BlogArticle() {
  const { slug } = useParams();
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    async function loadPost() {
      setLoading(true);
      setFailed(false);
      try {
        const rows = await base44.entities.BlogPost.filter(
          { slug, status: "published" },
          "-published_at",
          1,
        );
        if (active) setPost(Array.isArray(rows) ? rows[0] || null : null);
      } catch {
        if (active) setFailed(true);
      } finally {
        if (active) setLoading(false);
      }
    }

    loadPost();
    return () => {
      active = false;
    };
  }, [slug]);

  useEffect(() => {
    if (!post) return undefined;

    const previousTitle = document.title;
    document.title = post.meta_title || `${post.title} | FixList`;

    let descriptionMeta = document.querySelector('meta[name="description"]');
    const createdDescriptionMeta = !descriptionMeta;
    if (!descriptionMeta) {
      descriptionMeta = document.createElement("meta");
      descriptionMeta.setAttribute("name", "description");
      document.head.appendChild(descriptionMeta);
    }
    const previousDescription = descriptionMeta.getAttribute("content");
    descriptionMeta.setAttribute("content", post.meta_description || post.excerpt || "FixList SEO guide");

    return () => {
      document.title = previousTitle;
      if (createdDescriptionMeta) {
        descriptionMeta.remove();
      } else if (previousDescription == null) {
        descriptionMeta.removeAttribute("content");
      } else {
        descriptionMeta.setAttribute("content", previousDescription);
      }
    };
  }, [post]);

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-6 pb-24">
        <nav className="flex items-center justify-between pt-7">
          <Link to="/" className="text-[15px] font-semibold tracking-tight">
            FixList
          </Link>
          <div className="flex items-center gap-5">
            <Link to="/blog" className="text-[13px] text-ink-muted transition-colors hover:text-ink">
              Blog
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

        <main className="mt-16">
          {loading ? (
            <div className="py-12 text-[13px] text-ink-faint">Loading article…</div>
          ) : failed ? (
            <div className="py-12">
              <h1 className="text-[28px] font-semibold tracking-tight">Article temporarily unavailable</h1>
              <p className="mt-4 text-[14px] leading-relaxed text-ink-muted">
                We could not load this article right now. Please try again shortly.
              </p>
              <Link to="/blog" className="mt-6 inline-block text-[13px] font-medium underline underline-offset-4">
                Back to the blog
              </Link>
            </div>
          ) : !post ? (
            <div className="py-12">
              <h1 className="text-[28px] font-semibold tracking-tight">Article not found</h1>
              <p className="mt-4 text-[14px] leading-relaxed text-ink-muted">
                This article may have moved or has not been published.
              </p>
              <Link to="/blog" className="mt-6 inline-block text-[13px] font-medium underline underline-offset-4">
                Browse all articles
              </Link>
            </div>
          ) : (
            <article>
              <Link to="/blog" className="text-[12px] text-ink-muted transition-colors hover:text-ink">
                ← All articles
              </Link>
              <div className="mt-8 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-faint">
                {post.category ? <span>{post.category}</span> : null}
                {post.category && post.published_at ? <span>·</span> : null}
                {post.published_at ? <time>{formatDate(post.published_at)}</time> : null}
              </div>
              <h1 className="mt-4 text-[34px] font-semibold leading-tight tracking-tight sm:text-[40px]">
                {post.title}
              </h1>
              {post.excerpt ? (
                <p className="mt-5 text-[16px] leading-7 text-ink-muted">{post.excerpt}</p>
              ) : null}

              <div className="mt-10 border-t border-hairline-soft pt-2">
                <ReactMarkdown components={markdownComponents}>{post.body_markdown || ""}</ReactMarkdown>
              </div>

              <div className="mt-14 border-t border-hairline-soft pt-6">
                <p className="text-[14px] leading-relaxed text-ink-muted">
                  FixList checks up to 150 pages and turns what it finds into a prioritized, plain-English list of what to fix first.
                </p>
                <Link
                  to="/register"
                  className="mt-5 inline-block rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-paper transition-opacity hover:opacity-80"
                >
                  Get access
                </Link>
              </div>
            </article>
          )}
        </main>
      </div>
    </div>
  );
}
