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
  { id: "rebuild", name: "Website rebuild", price: "Custom quote", desc: "For larger website structure or migration projects.", features: ["Site structure planning", "SEO-safe migration plan", "Post-launch review"] },
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
      <div className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="mb-8"><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Billing</h1><p className="mt-2 text-base text-slate-500">Plans are coming soon.</p></div>

        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm leading-6 text-slate-600">Payments are not connected yet. You can join the waitlist or request help.</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {plans.map((plan) => {
            const isCurrent = plan.id === currentPlan;
            return (
              <div key={plan.id} className="flex flex-col rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-950">{plan.name}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{plan.desc}</p>
                <p className="mt-5 text-2xl font-semibold text-slate-950">{plan.price}</p>
                <ul className="mt-5 flex-1 space-y-2">
                  {plan.features.map((feature) => <li key={feature} className="text-sm leading-6 text-slate-600">{feature}</li>)}
                </ul>
                {plan.id === "free" ? (
                  <Button className="mt-6 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700" onClick={() => navigate("/crawl-status")}>Run Free Scan</Button>
                ) : isCurrent ? (
                  <Button disabled variant="outline" className="mt-6 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700">Current plan</Button>
                ) : plan.comingSoon ? (
                  <Button variant="outline" className="mt-6 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => setLeadModal({ type: "waitlist", plan: plan.id })}>Join Waitlist</Button>
                ) : (
                  <Button variant="outline" className="mt-6 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => setLeadModal({ type: plan.id === "done_for_you" ? "cleanup" : "custom_rebuild", plan: plan.id })}>{plan.id === "done_for_you" ? "Request Cleanup" : "Contact Us"}</Button>
                )}
              </div>
            );
          })}
        </div>

        {leadModal?.type === "cleanup" && <CleanupRequestModal onClose={() => setLeadModal(null)} />}
        {leadModal && leadModal.type !== "cleanup" && <LeadRequestModal requestType={leadModal.type} selectedPlan={leadModal.plan} onClose={() => setLeadModal(null)} />}
      </div>
    </div>
  );
}