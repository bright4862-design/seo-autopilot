import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import LeadRequestModal from "@/components/billing/LeadRequestModal";
import CleanupRequestModal from "@/components/billing/CleanupRequestModal";

const plans = [
  { id: "free", name: "Free scan", price: "Free", desc: "Start with a simple website scan.", features: ["Website scan", "Simple Fix List", "Plain-English recommendations"] },
  { id: "diy", name: "DIY guidance", price: "$20/month", desc: "Coming soon for owners who want guided monthly reviews.", features: ["Monthly website scan", "Prepared recommendations", "Competitor gaps"], comingSoon: true },
  { id: "growth", name: "Growth", price: "$49/month", desc: "Coming soon for deeper ongoing reviews.", features: ["More pages", "More competitors", "Priority recommendations"], comingSoon: true },
  { id: "done_for_you", name: "Done-for-you cleanup", price: "$500 one-time", desc: "Request help applying approved recommendations.", features: ["Review your scan", "Prepare next steps", "Website cleanup support"] },
  { id: "rebuild", name: "Website rebuild", price: "Custom quote", desc: "For larger website structure or migration projects.", features: ["Site structure planning", "Safe migration plan", "Post-launch review"] },
];

export default function Billing() {
  const navigate = useNavigate();
  const [currentPlan, setCurrentPlan] = useState("free");
  const [leadModal, setLeadModal] = useState(null);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) setCurrentPlan(projects[0].subscription_plan || "free");
    };
    load();
  }, []);

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8">
          <p className="text-sm font-medium text-blue-600">Plans and help</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Billing</h1>
          <p className="mt-2 text-base leading-7 text-slate-500">Choose a guided plan or request help when you need it.</p>
        </div>

        <section className="mb-7 rounded-3xl border border-slate-200/80 bg-white px-5 py-5 shadow-sm sm:px-6">
          <h2 className="text-base font-semibold text-slate-950">Payments are not connected yet</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">You can join the waitlist or request help. Nothing is charged here.</p>
        </section>

        <div className="space-y-4">
          {plans.map((plan) => {
            const isCurrent = plan.id === currentPlan;
            return (
              <section key={plan.id} className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
                <div className="flex flex-col gap-5 px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-6">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <h2 className="text-base font-semibold text-slate-950">{plan.name}</h2>
                      {isCurrent && <span className="text-xs font-medium text-blue-600">Current plan</span>}
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{plan.desc}</p>
                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      {plan.features.map((feature) => <p key={feature} className="text-sm text-slate-500">{feature}</p>)}
                    </div>
                  </div>
                  <div className="shrink-0 sm:text-right">
                    <p className="text-lg font-semibold text-slate-950">{plan.price}</p>
                    {plan.id === "free" ? (
                      <Button className="mt-4 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700" onClick={() => navigate("/crawl-status")}>Run Free Scan</Button>
                    ) : isCurrent ? (
                      <Button disabled variant="outline" className="mt-4 rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none">Current plan</Button>
                    ) : plan.comingSoon ? (
                      <Button variant="outline" className="mt-4 rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={() => setLeadModal({ type: "waitlist", plan: plan.id })}>Join waitlist</Button>
                    ) : (
                      <Button variant="outline" className="mt-4 rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={() => setLeadModal({ type: plan.id === "done_for_you" ? "cleanup" : "custom_rebuild", plan: plan.id })}>{plan.id === "done_for_you" ? "Request help" : "Contact us"}</Button>
                    )}
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        {leadModal?.type === "cleanup" && <CleanupRequestModal onClose={() => setLeadModal(null)} />}
        {leadModal && leadModal.type !== "cleanup" && <LeadRequestModal requestType={leadModal.type} selectedPlan={leadModal.plan} onClose={() => setLeadModal(null)} />}
      </div>
    </div>
  );
}