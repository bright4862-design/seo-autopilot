import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import LeadRequestModal from "@/components/billing/LeadRequestModal";
import CleanupRequestModal from "@/components/billing/CleanupRequestModal";

const plans = [
  { id: "free", name: "Free scan", price: "Free", desc: "Start with a simple website scan.", features: ["Website scan", "Simple FixList", "Plain-English recommendations"] },
  { id: "diy", name: "DIY guidance", price: "$20/month", desc: "Coming soon for owners who want guided monthly reviews.", features: ["Monthly website scan", "Prepared recommendations", "Competitor gaps"], comingSoon: true },
  { id: "growth", name: "Growth", price: "$49/month", desc: "Coming soon for deeper ongoing reviews.", features: ["More pages", "More competitors", "Priority recommendations"], comingSoon: true },
  { id: "done_for_you", name: "Done-for-you cleanup", price: "$500 one-time", desc: "Request help applying approved recommendations.", features: ["Review your scan", "Prepare next steps", "Website cleanup support"] },
  { id: "rebuild", name: "Website rebuild", price: "Custom quote", desc: "For larger website structure or migration projects.", features: ["Site structure planning", "Safe migration plan", "Post-launch review"] },
];

export default function Billing() {
  const navigate = useNavigate();
  const [currentPlan, setCurrentPlan] = useState("free");
  const [leadModal, setLeadModal] = useState(null);
  const [deleteMessage, setDeleteMessage] = useState("");

  useEffect(() => {
    trackEvent("billing_viewed");
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) setCurrentPlan(projects[0].subscription_plan || "free");
    };
    load();
  }, []);

  const handleDeleteAccount = () => {
    const confirmed = window.confirm("Delete account requests are permanent. Do you want instructions for deleting your account?");
    if (!confirmed) return;

    trackEvent("delete_account_requested", { page: "billing" });
    setDeleteMessage("To delete your account and personal data, please contact Base44 support from your account settings. This protects your account from accidental deletion.");
  };

  function planAction(plan) {
    const isCurrent = plan.id === currentPlan;
    if (plan.id === "free") {
      return <PillButton solid onClick={() => navigate("/crawl-status")}>Run free scan</PillButton>;
    }
    if (isCurrent) {
      return <span className="text-[13px] text-ink-faint">Current plan</span>;
    }
    if (plan.comingSoon) {
      return <PillButton onClick={() => setLeadModal({ type: "waitlist", plan: plan.id })}>Join waitlist</PillButton>;
    }
    return (
      <PillButton onClick={() => setLeadModal({ type: plan.id === "done_for_you" ? "cleanup" : "custom_rebuild", plan: plan.id })}>
        {plan.id === "done_for_you" ? "Request help" : "Contact us"}
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
            Choose the level of help you need. Payments are not connected yet, so nothing is charged here.
          </p>
        </div>

        <section className="mt-12 border-y border-hairline-soft py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[12px] font-medium text-ink-faint">Current plan</p>
              <p className="mt-1 text-[17px] font-medium tracking-tight">{plans.find((plan) => plan.id === currentPlan)?.name || "Free scan"}</p>
            </div>
            <PillButton solid onClick={() => navigate("/onboarding")}>Run a new scan</PillButton>
          </div>
        </section>

        <div className="mt-14 flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Plans</div>
        <div className="mt-2">
          {plans.map((plan) => {
            const isCurrent = plan.id === currentPlan;
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
          Plans unlock as FixList leaves beta. Joining a waitlist never charges you.
        </footer>

        {leadModal?.type === "cleanup" && <CleanupRequestModal onClose={() => setLeadModal(null)} />}
        {leadModal && leadModal.type !== "cleanup" && <LeadRequestModal requestType={leadModal.type} selectedPlan={leadModal.plan} onClose={() => setLeadModal(null)} />}
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
