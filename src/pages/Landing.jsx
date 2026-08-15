import React, { useState } from "react";
import { Link } from "react-router-dom";

const faqs = [
  {
    q: "What does FixList do?",
    a: "FixList runs a read-only Standard 150 beta scan of up to 150 pages, then turns the results into plain-English SEO fixes you can understand and act on.",
  },
  {
    q: "Will FixList change my website?",
    a: "No. FixList is read-only. We scan your website, explain what we found, and show you what to fix next. We never log in or change anything on your site.",
  },
  {
    q: "Do I need to know SEO?",
    a: "No. FixList is built for small business owners. It explains what matters, why it matters, and whether you can handle it yourself or may need help.",
  },
  {
    q: "How much is beta access?",
    a: "Beta access is a one-time $50 payment. It includes Standard 150 beta scans, with up to 150 pages checked per scan.",
  },
  {
    q: "How long does a scan take?",
    a: "Most scans take about 2–4 minutes. Larger or slower websites may take longer.",
  },
  {
    q: "What happens after I run my scan?",
    a: "You get a FixList with your website health score, prioritized recommendations, affected pages, and simple next steps.",
  },
];

export default function Landing() {
  const [openFaq, setOpenFaq] = useState(null);

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-6 pb-24">
        <nav className="flex items-center justify-between pt-7">
          <Link to="/" className="text-[15px] font-semibold tracking-tight">
            FixList
          </Link>
          <div className="flex items-center gap-5">
            <a
              href="#faq"
              className="text-[13px] text-ink-muted transition-colors hover:text-ink"
            >
              FAQ
            </a>
            <Link
              to="/login"
              className="text-[13px] text-ink-muted transition-colors hover:text-ink"
            >
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Get beta access
            </Link>
          </div>
        </nav>

        <main>
          <section className="mt-24">
            <p className="text-[13px] text-ink-faint">
              Standard 150 beta · read-only · no site changes
            </p>
            <h1 className="mt-4 text-[32px] font-semibold leading-tight tracking-tight sm:text-[38px]">
              Website scans, turned into simple SEO fixes.
            </h1>
            <p className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-ink-muted">
              Check up to 150 pages, see what needs attention, and get a
              plain-English list of what to fix first — each with where to
              click and who should do it.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/register"
                className="rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Get beta access
              </Link>
              <a
                href="#faq"
                className="rounded-full border border-hairline px-5 py-2.5 text-[13px] font-medium text-ink transition-colors hover:bg-ink/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Questions first
              </a>
            </div>

            <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink-muted">
              <span className="flex items-center gap-2">
                <span className="text-good">✓</span> Up to 150 pages per scan
              </span>
              <span className="flex items-center gap-2">
                <span className="text-good">✓</span> One-time $50 beta access
              </span>
              <span className="flex items-center gap-2">
                <span className="text-good">✓</span> Usually 2–4 minutes
              </span>
            </div>
          </section>

          <section id="faq" className="mt-24">
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
              FAQ
            </div>
            <div className="mt-2">
              {faqs.map((faq, index) => {
                const open = openFaq === index;
                return (
                  <div key={faq.q} className="border-b border-hairline-soft">
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setOpenFaq(open ? null : index)}
                      className="flex w-full items-baseline justify-between gap-4 py-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                    >
                      <span className="text-[15px] font-medium tracking-tight">
                        {faq.q}
                      </span>
                      <span
                        className={`shrink-0 text-[12px] leading-none text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}
                      >
                        ›
                      </span>
                    </button>
                    {open ? (
                      <p className="max-w-[56ch] pb-5 text-[14px] leading-relaxed text-ink-muted">
                        {faq.a}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>
        </main>

        <footer className="mt-24 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          FixList checks up to 150 pages of your site and turns what it finds
          into a short, plain-English list.
        </footer>
      </div>
    </div>
  );
}
