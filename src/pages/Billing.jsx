import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Zap, Star } from "lucide-react";

const plans = [
  {
    id: "free", name: "Free Scan", price: "Free", period: "",
    desc: "See what's wrong with your site",
    features: ["One-time homepage scan", "Top 5 issues found", "Competitor teaser", "Basic SEO score"],
    limit: "Limited to homepage"
  },
  {
    id: "diy", name: "DIY SEO Autopilot", price: "$20", period: "/month",
    desc: "Fix SEO issues yourself with AI guidance",
    features: ["Monthly full-site crawl", "Up to 250 pages", "Up to 25 JS-rendered pages", "AI meta titles & descriptions", "404 detection", "Redirect recommendations", "Canonical & sitemap checks", "3 competitor benchmarks", "Monthly SEO report"],
    popular: true,
    comingSoon: true
  },
  {
    id: "growth", name: "Growth", price: "$49", period: "/month",
    desc: "More pages, more competitors, more insights",
    features: ["Weekly crawl", "Up to 1,000 pages", "Up to 100 JS-rendered pages", "5 competitor benchmarks", "Priority AI recommendations", "Google Search Console (coming soon)", "Everything in DIY"],
    comingSoon: true
  },
  {
    id: "done_for_you", name: "Done-for-You SEO Cleanup", price: "$500", period: " one-time",
    desc: "We implement the approved fixes for you",
    features: ["Expert implements approved easy fixes", "Redirect map cleanup", "Metadata updates applied", "Sitemap & canonical review", "Developer handoff notes", "Priority email support"]
  },
  {
    id: "rebuild", name: "Website Rebuild / SEO Migration", price: "Custom", period: " quote",
    desc: "Full site restructure with SEO preservation",
    features: ["Site structure planning", "SEO-safe migration strategy", "Complete redirect strategy", "New content recommendations", "Technical SEO setup", "Post-launch monitoring"]
  },
];

export default function Billing() {
  const navigate = useNavigate();
  const [currentPlan, setCurrentPlan] = useState("free");

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) setCurrentPlan(projects[0].subscription_plan || "free");
    };
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Billing & Plans</h1>
        <p className="text-sm text-gray-500 mt-1">Choose the plan that fits your business needs</p>
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <Zap className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-blue-800 leading-relaxed">
          Plans are coming soon. For now, you can run a free scan and request help manually.
        </p>
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
        {plans.map(plan => {
          const isCurrent = plan.id === currentPlan;
          return (
            <div key={plan.id} className={`bg-white rounded-2xl border p-6 flex flex-col relative ${plan.popular ? "border-blue-200 shadow-lg shadow-blue-50 ring-2 ring-blue-100" : "border-gray-100"}`}>
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center gap-1 bg-blue-600 text-white text-xs font-semibold px-3 py-1 rounded-full">
                    <Star className="w-3 h-3" /> Most Popular
                  </span>
                </div>
              )}
              <h3 className="font-bold text-lg text-gray-900">{plan.name}</h3>
              <p className="text-sm text-gray-500 mb-4">{plan.desc}</p>
              <div className="mb-6">
                <span className="text-3xl font-extrabold text-gray-900">{plan.price}</span>
                <span className="text-sm text-gray-400">{plan.period}</span>
              </div>
              <ul className="space-y-2.5 flex-1 mb-6">
                {plan.features.map(f => (
                  <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                    <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              {plan.id === "free" ? (
                <Button className="w-full gradient-primary text-white border-0" onClick={() => navigate("/crawl-status")}>
                  Run Free Scan
                </Button>
              ) : isCurrent ? (
                <Button disabled variant="outline" className="w-full">Current Plan</Button>
              ) : plan.comingSoon ? (
                <Button disabled variant="outline" className="w-full">Join Waitlist</Button>
              ) : (
                <Button variant="outline" className="w-full">
                  {plan.id === "done_for_you" ? "Request Cleanup" : "Contact Us"}
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}