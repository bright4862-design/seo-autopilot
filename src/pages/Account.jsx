import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadAccess } from "@/lib/access";

export default function Account() {
  const [access, setAccess] = useState(null);
  const [accessLoaded, setAccessLoaded] = useState(false);
  const [accessUnavailable, setAccessUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setAccessUnavailable(false);

    loadAccess()
      .then((nextAccess) => {
        if (!cancelled) setAccess(nextAccess);
      })
      .catch(() => {
        if (!cancelled) setAccessUnavailable(true);
      })
      .finally(() => {
        if (!cancelled) setAccessLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-4 pb-24 sm:px-6">
        <header className="pt-14 sm:pt-16">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Account</p>
          <h1 className="mt-2 text-[28px] font-semibold leading-tight tracking-[-0.035em]">Your FixList access</h1>
          <p className="mt-2 max-w-[56ch] text-[15px] leading-relaxed text-ink-muted">
            Manage your Standard 150 access and review the terms and data practices that apply when you use FixList.
          </p>
        </header>

        <section className="mt-10 rounded-2xl border border-hairline bg-white/60 p-6" aria-labelledby="access-heading">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p id="access-heading" className="text-[12px] font-medium text-ink-faint">Standard 150</p>
              <p className="mt-1 text-[18px] font-semibold tracking-tight">
                {!accessLoaded
                  ? "Checking access…"
                  : accessUnavailable
                    ? "Access status temporarily unavailable"
                    : access?.fullAccess
                      ? "Full access is active"
                      : "No active paid access"}
              </p>
              <p className="mt-2 max-w-[46ch] text-[13.5px] leading-relaxed text-ink-muted">
                Standard 150 reviews up to 150 pages per scan and turns the evidence it finds into a prioritized FixList.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Link
                to="/onboarding"
                className="rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Run a scan
              </Link>
              <Link
                to="/billing"
                className="rounded-full border border-hairline px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-ink/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Billing
              </Link>
            </div>
          </div>
        </section>

        <section className="mt-14" aria-labelledby="terms-heading">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Service terms</p>
          <h2 id="terms-heading" className="mt-2 text-[22px] font-semibold tracking-[-0.025em]">Terms & Conditions</h2>
          <div className="mt-5 space-y-5 text-[14px] leading-relaxed text-ink-muted">
            <p>
              FixList is an automated website and SEO diagnostic service. Standard 150 can inspect up to 150 pages in a scan, so a FixList may represent a bounded sample rather than every page on a larger website.
            </p>
            <p>
              Only submit a website that you own or are authorized to assess. FixList is designed to fetch publicly accessible website content needed for the scan; it is not permission to bypass logins, access controls, robots protections, or other restrictions.
            </p>
            <p>
              Findings and priorities are generated from crawl evidence and are provided for diagnostic and informational use. Some recommendations require human judgment. FixList does not guarantee rankings, traffic, revenue, indexing, or any particular search-engine outcome.
            </p>
            <p>
              Paid access and prices are shown before checkout. Stripe processes the payment. Your continued use of FixList is subject to these terms and to reasonable safeguards needed to protect the service, other customers, and scanned websites.
            </p>
          </div>
        </section>

        <section className="mt-14 border-t border-hairline-soft pt-10" aria-labelledby="privacy-heading">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Privacy notice</p>
          <h2 id="privacy-heading" className="mt-2 text-[22px] font-semibold tracking-[-0.025em]">Privacy & Data</h2>
          <div className="mt-5 space-y-5 text-[14px] leading-relaxed text-ink-muted">
            <p>
              To operate FixList, we process the account information needed to identify your account, submitted website URLs, scan results and history, supporting scan evidence, payment and access status, and limited usage events and technical logs used to operate, secure, and improve the service.
            </p>
            <p>
              During a scan, FixList requests publicly accessible website content from the submitted site so it can analyze the pages it is able to reach. Access-limited or unavailable sites may produce a clear failure or incomplete-coverage state rather than a fabricated result.
            </p>
            <p>
              Payments are handled by Stripe. FixList does not receive or store your full card details. We may receive payment status and transaction-related information needed to activate and support your access.
            </p>
            <p>
              We do not sell your personal information or customer scan data. Service providers may process information only as needed to host, authenticate, secure, process payments for, and operate FixList.
            </p>
            <p>
              Scan history and account information are retained as needed to provide the product, preserve the scans you expect to revisit, prevent abuse, and meet operational or legal obligations. For account and data-removal guidance, use the controls on the <Link to="/billing" className="font-medium text-ink underline decoration-hairline underline-offset-4 hover:decoration-ink">Billing page</Link>.
            </p>
          </div>
        </section>

        <footer className="mt-16 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          These product terms and privacy details describe the FixList service available through this account.
        </footer>
      </div>
    </div>
  );
}
