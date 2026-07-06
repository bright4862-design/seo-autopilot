import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, ChevronDown, ShieldCheck, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";

const faqs = [
  {
    q: "What does FixList do?",
    a: "FixList scans your website and turns the results into plain-English SEO fixes you can understand and act on.",
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
    q: "How long does a scan take?",
    a: "Most first scans take 1–2 minutes. Bigger websites may take a little longer depending on scan size.",
  },
  {
    q: "What happens after I run my scan?",
    a: "You get a FixList with your website health score, prioritized recommendations, affected pages, and simple next steps.",
  },
];

export default function Landing() {
  const [openFaq, setOpenFaq] = useState(null);

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <nav className="fixed inset-x-0 top-0 z-50 border-b border-slate-100 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-sm shadow-indigo-200">
              <Zap className="h-4 w-4" />
            </div>
            <span className="text-xl font-bold tracking-tight">FixList</span>
          </Link>

          <div className="flex items-center gap-3 text-sm font-medium">
            <a href="#faq" className="hidden text-slate-600 transition hover:text-slate-950 sm:inline-flex">
              FAQ
            </a>
            <Link to="/register">
              <Button size="sm" className="bg-indigo-600 text-white hover:bg-indigo-700">
                Run my scan
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      <main>
        <section className="px-4 pb-20 pt-32 sm:pb-24 sm:pt-36">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700">
              <ShieldCheck className="h-3.5 w-3.5" />
              Read-only website scan
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight text-slate-950 sm:text-6xl">
              FixList turns website scans into simple SEO fixes.
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-500">
              Scan your site, see what needs attention, and get a plain-English list of what to fix first.
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link to="/register" className="w-full sm:w-auto">
                <Button size="lg" className="h-12 w-full bg-indigo-600 px-8 text-base text-white hover:bg-indigo-700 sm:w-auto">
                  Run my scan
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <a href="#faq" className="inline-flex h-12 items-center justify-center rounded-xl border border-slate-200 px-8 text-base font-semibold text-slate-700 transition hover:bg-slate-50 hover:text-slate-950">
                FAQ
              </a>
            </div>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-sm text-slate-500">
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                Free scan included
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                No credit card needed
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                Results in minutes
              </span>
            </div>
          </div>
        </section>

        <section id="faq" className="border-t border-slate-100 bg-slate-50 px-4 py-20">
          <div className="mx-auto max-w-3xl">
            <div className="text-center">
              <p className="text-sm font-semibold text-indigo-600">FAQ</p>
              <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
                Questions before you run your scan?
              </h2>
            </div>

            <div className="mt-10 space-y-3">
              {faqs.map((faq, index) => {
                const open = openFaq === index;

                return (
                  <div key={faq.q} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <button
                      type="button"
                      onClick={() => setOpenFaq(open ? null : index)}
                      className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
                    >
                      <span className="font-semibold text-slate-950">{faq.q}</span>
                      <ChevronDown className={`h-5 w-5 shrink-0 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
                    </button>

                    {open ? (
                      <div className="px-5 pb-5 text-sm leading-6 text-slate-600">
                        {faq.a}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
