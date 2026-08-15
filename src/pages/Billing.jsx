import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import LeadRequestModal from "@/components/billing/LeadRequestModal";
import UnlockAccessButton from "@/components/billing/UnlockAccessButton";
import { loadAccess, UNLOCK_PRICE_LABEL } from "@/lib/access";

const plans = [
  { id: "standard_150", name: "Standard 150 beta", price: "$50 one-time", desc: "Paid lifetime beta access to the production Standard 150 scanner.", features: ["Unlimited Standard 150 scans", "Complete FixList", "Plain-English recommendations"] },
  { id: "rebuild", name: "Website rebuild", price: "$300", desc: "For larger website structure or migration projects.", features: ["Site structure planning", "Safe migration plan", "Post-launch review"] },
  { id: "grok_ai_helper", name: "Grok AI helper", price: "Coming soon", desc: "An AI helper that answers questions about your scan and walks you through each fix.", features: ["Ask about any fix", "Step-by-step guidance", "Grounded in your scan"], comingSoon: true },
  { id: "premium_scanner", name: "Premium 5,000 page scanner", price: "Coming soon", desc: "Deep scans for large websites, up to 5,000 pages per run.", features: ["Up to 5,000 pages", "Full-site coverage", "Priority scan queue"], comingSoon: true },
];

export const ACTIVATION_POLL_MAX_ATTEMPTS = 15;
export const ACTIVATION_POLL_INTERVAL_MS = 2_000;
export const ACTIVATION_POLL_MAX_DURATION_MS = 30_000;
export const ACTIVATION_REQUEST_TIMEOUT_MS = 5_000;

function settleAccessLoad(load, timeoutMs, signal) {
  return new Promise((resolve) => {
    let settled = false;
    let timerId = null;

    const finish = (outcome) => {
      if (settled) return;
      settled = true;
      if (timerId !== null) window.clearTimeout(timerId);
      signal?.removeEventListener("abort", handleAbort);
      resolve(outcome);
    };
    const handleAbort = () => finish({ kind: "cancelled" });

    if (signal?.aborted) {
      handleAbort();
      return;
    }

    signal?.addEventListener("abort", handleAbort, { once: true });
    timerId = window.setTimeout(() => finish({ kind: "timeout" }), timeoutMs);
    Promise.resolve()
      .then(load)
      .then(
        (value) => finish({ kind: "value", value }),
        () => finish({ kind: "error" }),
      );
  });
}

function waitForActivationPoll(delayMs, signal) {
  return new Promise((resolve) => {
    let timerId = null;

    const finish = (continued) => {
      if (timerId !== null) window.clearTimeout(timerId);
      signal?.removeEventListener("abort", handleAbort);
      resolve(continued);
    };
    const handleAbort = () => finish(false);

    if (signal?.aborted) {
      handleAbort();
      return;
    }

    signal?.addEventListener("abort", handleAbort, { once: true });
    timerId = window.setTimeout(() => finish(true), delayMs);
  });
}

export async function pollForActivatedAccess({
  load,
  signal,
  maxAttempts = ACTIVATION_POLL_MAX_ATTEMPTS,
  intervalMs = ACTIVATION_POLL_INTERVAL_MS,
  maxDurationMs = ACTIVATION_POLL_MAX_DURATION_MS,
  requestTimeoutMs = ACTIVATION_REQUEST_TIMEOUT_MS,
}) {
  const startedAt = Date.now();
  let attempts = 0;
  let lastAccess = null;

  while (attempts < maxAttempts) {
    if (signal?.aborted) return { status: "cancelled", access: lastAccess, attempts };

    const remainingMs = maxDurationMs - (Date.now() - startedAt);
    if (remainingMs <= 0) return { status: "timeout", access: lastAccess, attempts };

    const outcome = await settleAccessLoad(
      load,
      Math.min(requestTimeoutMs, remainingMs),
      signal,
    );
    if (outcome.kind === "cancelled") {
      return { status: "cancelled", access: lastAccess, attempts };
    }

    attempts += 1;
    if (outcome.kind === "value") {
      lastAccess = outcome.value;
      if (lastAccess?.fullAccess === true) {
        return { status: "active", access: lastAccess, attempts };
      }
    }

    if (attempts >= maxAttempts) break;
    const waitBudgetMs = maxDurationMs - (Date.now() - startedAt);
    if (waitBudgetMs <= 0) break;
    const continued = await waitForActivationPoll(
      Math.min(intervalMs, waitBudgetMs),
      signal,
    );
    if (!continued) return { status: "cancelled", access: lastAccess, attempts };
  }

  return { status: "timeout", access: lastAccess, attempts };
}

export default function Billing() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnedFromCheckout = searchParams.get("paid") === "1";
  const [currentPlan, setCurrentPlan] = useState("none");
  const [leadModal, setLeadModal] = useState(null);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [access, setAccess] = useState(null);
  const [accessLoaded, setAccessLoaded] = useState(false);
  const [activationStatus, setActivationStatus] = useState(
    returnedFromCheckout ? "checking" : "idle",
  );
  const [activationAttempt, setActivationAttempt] = useState(0);
  const paymentReturnTrackedRef = useRef(false);
  const activationOutcomeTrackedRef = useRef(false);
  const checkoutSuppressed = returnedFromCheckout && access?.fullAccess !== true;
  const activationPending = checkoutSuppressed && activationStatus !== "timeout";

  useEffect(() => {
    if (returnedFromCheckout) return undefined;
    let cancelled = false;
    loadAccess()
      .then((nextAccess) => {
        if (!cancelled) setAccess(nextAccess);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setAccessLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [returnedFromCheckout]);

  useEffect(() => {
    if (!returnedFromCheckout) return undefined;
    if (!paymentReturnTrackedRef.current) {
      paymentReturnTrackedRef.current = true;
      trackEvent("payment_returned", { plan: "standard_150" });
    }
    const controller = new AbortController();
    setActivationStatus("checking");
    setAccessLoaded(false);

    pollForActivatedAccess({ load: loadAccess, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.access) setAccess(result.access);
        setAccessLoaded(true);
        if (result.status === "active") {
          setActivationStatus("active");
          if (!activationOutcomeTrackedRef.current) {
            activationOutcomeTrackedRef.current = true;
            trackEvent("access_activated", { plan: "standard_150", attempts: result.attempts });
          }
          return;
        }
        setActivationStatus("timeout");
        if (!activationOutcomeTrackedRef.current) {
          activationOutcomeTrackedRef.current = true;
          trackEvent("access_activation_delayed", { plan: "standard_150", attempts: result.attempts });
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setAccessLoaded(true);
        setActivationStatus("timeout");
        if (!activationOutcomeTrackedRef.current) {
          activationOutcomeTrackedRef.current = true;
          trackEvent("access_activation_delayed", { plan: "standard_150", attempts: 0 });
        }
      });

    return () => controller.abort();
  }, [activationAttempt, returnedFromCheckout]);

  useEffect(() => {
    trackEvent("billing_viewed");
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) setCurrentPlan(projects[0].subscription_plan || "none");
    };
    load();
  }, []);

  const handleDeleteAccount = () => {
    const confirmed = window.confirm("Delete account requests are permanent. Do you want instructions for deleting your account?");
    if (!confirmed) return;

    trackEvent("delete_account_requested", { page: "billing" });
    setDeleteMessage("To delete your account and personal data, please contact Base44 support from your account settings. This protects your account from accidental deletion.");
  };

  function retryActivation() {
    activationOutcomeTrackedRef.current = false;
    setActivationStatus("checking");
    setActivationAttempt((attempt) => attempt + 1);
  }

  function planAction(plan) {
    const isCurrent = plan.id === currentPlan;
    if (plan.id === "standard_150") {
      if (access?.fullAccess) return <span className="text-[13px] text-good">Active</span>;
      if (checkoutSuppressed) {
        return <span className="text-[13px] text-ink-faint">{activationPending ? "Activating…" : "Activation pending"}</span>;
      }
      return accessLoaded
        ? <UnlockAccessButton />
        : <span className="text-[13px] text-ink-faint">Checking access…</span>;
    }
    if (isCurrent) {
      return <span className="text-[13px] text-ink-faint">Current plan</span>;
    }
    if (plan.comingSoon) {
      return <PillButton onClick={() => setLeadModal({ type: "waitlist", plan: plan.id })}>Join waitlist</PillButton>;
    }
    return (
      <PillButton onClick={() => setLeadModal({ type: "custom_rebuild", plan: plan.id })}>
        Contact us
      </PillButton>
    );
  }

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-4 pb-24 sm:px-6">
        <div className="pt-14 sm:pt-16">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Account</p>
          <h1 className="mt-2 text-[28px] font-semibold leading-tight tracking-[-0.035em]">Billing</h1>
          <p className="mt-2 max-w-[54ch] text-[15px] leading-relaxed text-ink-muted">
            Standard 150 beta access is a one-time payment. Checkout is securely handled by Stripe.
          </p>
        </div>

        <section className="mt-12 border-y border-hairline-soft py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[12px] font-medium text-ink-faint">Current plan</p>
              <p className="mt-1 text-[17px] font-medium tracking-tight">
                {access?.fullAccess
                  ? "Standard 150 beta"
                  : checkoutSuppressed
                    ? "Standard 150 activation pending"
                    : accessLoaded
                      ? "No active access"
                      : "Checking access…"}
              </p>
            </div>
            {access?.fullAccess ? (
              <PillButton solid onClick={() => navigate("/onboarding")}>Run a new scan</PillButton>
            ) : checkoutSuppressed ? (
              <span className="text-[13px] text-ink-faint">{activationPending ? "Activating access…" : "Awaiting confirmation"}</span>
            ) : accessLoaded ? (
              <UnlockAccessButton />
            ) : (
              <span className="text-[13px] text-ink-faint">Checking…</span>
            )}
          </div>
        </section>

        <section className="mt-12 rounded-2xl border border-hairline bg-white/60 p-6">
          {access?.fullAccess ? (
            <>
              <h2 className="text-[18px] font-semibold tracking-tight">Full access is active</h2>
              <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
                You can run unlimited scans and see every result in your FixList.
              </p>
              {returnedFromCheckout ? (
                <div className="mt-5">
                  <PillButton solid onClick={() => navigate("/onboarding")}>Run a new scan</PillButton>
                </div>
              ) : null}
            </>
          ) : checkoutSuppressed ? (
            activationPending ? (
              <>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Payment complete</p>
                <h2 className="mt-2 text-[18px] font-semibold tracking-tight">Activating your access</h2>
                <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted" role="status" aria-live="polite">
                  Stripe has returned you to the app. We&rsquo;re confirming your payment and will unlock Standard 150 automatically.
                </p>
                <div className="mt-5 h-1.5 w-full max-w-[240px] overflow-hidden rounded-full bg-hairline-soft" aria-hidden="true">
                  <div className="h-full w-2/3 animate-pulse rounded-full bg-ink/60" />
                </div>
              </>
            ) : (
              <>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Payment confirmation delayed</p>
                <h2 className="mt-2 text-[18px] font-semibold tracking-tight">Access is taking longer than expected</h2>
                <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted" role="alert">
                  We haven&rsquo;t confirmed your access yet. Retry only checks your existing payment; it never starts another checkout.
                </p>
                <div className="mt-5">
                  <PillButton solid onClick={retryActivation}>Retry activation</PillButton>
                </div>
              </>
            )
          ) : !accessLoaded ? (
            <>
              <h2 className="text-[18px] font-semibold tracking-tight">Checking your access</h2>
              <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted" role="status">
                This should only take a moment.
              </p>
            </>
          ) : (
            <>
              <h2 className="text-[18px] font-semibold tracking-tight">Unlock full access — {UNLOCK_PRICE_LABEL}</h2>
              <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
                A one-time {UNLOCK_PRICE_LABEL} payment unlocks lifetime beta access to unlimited Standard 150 scans and the complete FixList — every fix, every affected page, and all passed checks.
              </p>
              <div className="mt-5">
                <UnlockAccessButton />
              </div>
            </>
          )}
        </section>

        <div className="mt-14 flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Plans</div>
        <div className="mt-2">
          {plans.map((plan) => {
            const isCurrent = plan.id === "standard_150" ? access?.fullAccess === true : plan.id === currentPlan;
            return (
              <div key={plan.id} className="border-b border-hairline-soft py-6">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between sm:gap-8">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <h2 className="text-[16px] font-medium tracking-tight">{plan.name}</h2>
                      {isCurrent ? <span className="text-[12px] font-medium text-good">Current</span> : null}
                      {plan.comingSoon ? <span className="text-[12px] text-ink-faint">Coming soon</span> : null}
                    </div>
                    <p className="mt-1 max-w-[52ch] text-[13.5px] leading-relaxed text-ink-muted">{plan.desc}</p>
                    <p className="mt-2 text-[13px] leading-relaxed text-ink-faint">{plan.features.join(" · ")}</p>
                  </div>
                  <div className="flex shrink-0 items-center justify-between gap-4 sm:block sm:text-right">
                    <p className="text-[15px] font-semibold tabular-nums tracking-tight">{plan.price}</p>
                    <div className="sm:mt-3">{planAction(plan)}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-16 flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Data and account</div>
        <div className="mt-4 max-w-[56ch] text-[14px] leading-relaxed text-ink-muted">
          <p>Need to remove your account and data? Start here and we&rsquo;ll show the safest next step.</p>
          {deleteMessage ? (
            <p className="mt-3 border-l-2 border-crit/40 pl-3 text-[13.5px] leading-relaxed">{deleteMessage}</p>
          ) : null}
          <button
            type="button"
            onClick={handleDeleteAccount}
            className="mt-5 rounded-full border border-hairline px-4 py-1.5 text-[13px] font-medium text-crit transition-colors hover:border-crit/30 hover:bg-crit/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Delete account
          </button>
        </div>

        <footer className="mt-24 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          Standard 150 is the only paid scanner in this beta. Grok and Premium remain unavailable.
        </footer>

        {leadModal && <LeadRequestModal requestType={leadModal.type} selectedPlan={leadModal.plan} onClose={() => setLeadModal(null)} />}
      </div>
    </div>
  );
}

function PillButton({ solid = false, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${
        solid
          ? "bg-ink text-paper transition-opacity hover:opacity-80"
          : "border border-hairline text-ink hover:bg-ink/[0.04]"
      }`}
    >
      {children}
    </button>
  );
}
