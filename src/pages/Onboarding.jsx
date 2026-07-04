import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Zap, ArrowRight, ArrowLeft, Building2, Globe, MapPin, Briefcase, Users, Wrench, Search } from "lucide-react";

const STEPS = [
  { title: "Your Business", icon: Building2, desc: "Tell us about your business" },
  { title: "Website", icon: Globe, desc: "Where should we start scanning?" },
  { title: "Location", icon: MapPin, desc: "Where do you serve customers?" },
  { title: "Services", icon: Briefcase, desc: "What do you offer?" },
  { title: "Competitors", icon: Users, desc: "Who are you competing with?" },
  { title: "Platform", icon: Wrench, desc: "What platform is your site built on?" },
  { title: "Start Scan", icon: Search, desc: "Ready to find SEO opportunities" },
];

const CMS_OPTIONS = ["WordPress", "Shopify", "Wix", "Webflow", "Squarespace", "Custom", "Unknown"];

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState({
    business_name: "",
    website_url: "",
    business_type: "",
    city: "",
    service_area: "",
    main_services: "",
    cms_platform: "",
    competitors: [{ name: "", url: "" }, { name: "", url: "" }, { name: "", url: "" }],
  });

  const update = (field, value) => setData(prev => ({ ...prev, [field]: value }));
  const updateCompetitor = (idx, field, value) => {
    const comps = [...data.competitors];
    comps[idx] = { ...comps[idx], [field]: value };
    setData(prev => ({ ...prev, competitors: comps }));
  };

  const handleFinish = async () => {
    setSaving(true);
    const project = await base44.entities.BusinessProject.create({
      business_name: data.business_name,
      website_url: data.website_url,
      business_type: data.business_type,
      city: data.city,
      service_area: data.service_area,
      main_services: data.main_services,
      cms_platform: data.cms_platform || "Unknown",
      status: "active",
      seo_score: 0,
      subscription_plan: "free",
    });

    for (const comp of data.competitors) {
      if (comp.url.trim()) {
        await base44.entities.Competitor.create({
          project_id: project.id,
          name: comp.name || comp.url,
          website_url: comp.url,
        });
      }
    }

    // Create initial crawl job
    await base44.entities.CrawlJob.create({
      project_id: project.id,
      status: "queued",
      crawl_type: "full",
    });

    navigate("/crawl-status");
  };

  const canNext = () => {
    if (step === 0) return data.business_name.trim().length > 0;
    if (step === 1) return data.website_url.trim().length > 0;
    if (step === 2) return data.city.trim().length > 0;
    return true;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex flex-col">
      <div className="p-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-lg tracking-tight">SEO Autopilot</span>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-lg">
          {/* Progress */}
          <div className="flex items-center gap-1 mb-8">
            {STEPS.map((_, i) => (
              <div key={i} className={`h-1.5 flex-1 rounded-full transition-colors ${i <= step ? "bg-blue-600" : "bg-gray-200"}`} />
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 shadow-xl shadow-gray-100/50 p-8">
            <div className="flex items-center gap-3 mb-6">
              {React.createElement(STEPS[step].icon, { className: "w-5 h-5 text-blue-600" })}
              <div>
                <h2 className="font-bold text-lg">{STEPS[step].title}</h2>
                <p className="text-sm text-gray-500">{STEPS[step].desc}</p>
              </div>
            </div>

            {step === 0 && (
              <div className="space-y-4">
                <div>
                  <Label>Business Name</Label>
                  <Input placeholder="e.g. Sunshine Plumbing & Heating" value={data.business_name} onChange={e => update("business_name", e.target.value)} className="mt-1.5" />
                </div>
                <div>
                  <Label>Business Type</Label>
                  <Input placeholder="e.g. Plumber, Dentist, Restaurant" value={data.business_type} onChange={e => update("business_type", e.target.value)} className="mt-1.5" />
                </div>
              </div>
            )}

            {step === 1 && (
              <div>
                <Label>Website URL</Label>
                <Input placeholder="https://yourwebsite.com" value={data.website_url} onChange={e => update("website_url", e.target.value)} className="mt-1.5" />
                <p className="text-xs text-gray-400 mt-2">We'll crawl this site to find SEO opportunities.</p>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <div>
                  <Label>City</Label>
                  <Input placeholder="e.g. Denver" value={data.city} onChange={e => update("city", e.target.value)} className="mt-1.5" />
                </div>
                <div>
                  <Label>Service Area</Label>
                  <Input placeholder="e.g. Denver Metro Area, Front Range" value={data.service_area} onChange={e => update("service_area", e.target.value)} className="mt-1.5" />
                </div>
              </div>
            )}

            {step === 3 && (
              <div>
                <Label>Main Services (comma separated)</Label>
                <Input placeholder="e.g. Emergency plumbing, water heater installation, HVAC repair" value={data.main_services} onChange={e => update("main_services", e.target.value)} className="mt-1.5" />
              </div>
            )}

            {step === 4 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">Add up to 3 competitors you'd like us to benchmark against. Skip if you're not sure — we'll suggest some later.</p>
                {data.competitors.map((comp, i) => (
                  <div key={i} className="grid grid-cols-2 gap-3">
                    <Input placeholder={`Competitor ${i + 1} name`} value={comp.name} onChange={e => updateCompetitor(i, "name", e.target.value)} />
                    <Input placeholder="https://competitor.com" value={comp.url} onChange={e => updateCompetitor(i, "url", e.target.value)} />
                  </div>
                ))}
              </div>
            )}

            {step === 5 && (
              <div>
                <Label>What platform is your website built on?</Label>
                <Select value={data.cms_platform} onValueChange={v => update("cms_platform", v)}>
                  <SelectTrigger className="mt-1.5"><SelectValue placeholder="Select your platform" /></SelectTrigger>
                  <SelectContent>
                    {CMS_OPTIONS.map(opt => (
                      <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-400 mt-2">This helps us tailor recommendations. Not sure? Pick "Unknown".</p>
              </div>
            )}

            {step === 6 && (
              <div className="text-center py-4">
                <div className="w-16 h-16 rounded-2xl gradient-primary flex items-center justify-center mx-auto mb-4">
                  <Search className="w-8 h-8 text-white" />
                </div>
                <h3 className="font-bold text-lg mb-2">Ready to scan {data.website_url || "your site"}!</h3>
                <p className="text-sm text-gray-500 mb-4">We'll crawl your website, analyze every page, and generate personalized SEO recommendations.</p>
                <div className="bg-blue-50 rounded-xl p-4 text-left space-y-2 text-sm">
                  <p className="font-medium text-blue-900">What happens next:</p>
                  <p className="text-blue-700">✓ We crawl all your pages</p>
                  <p className="text-blue-700">✓ Check titles, descriptions, and links</p>
                  <p className="text-blue-700">✓ Find broken pages and redirects</p>
                  <p className="text-blue-700">✓ Benchmark against competitors</p>
                  <p className="text-blue-700">✓ Generate AI recommendations</p>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between mt-8">
              <Button variant="ghost" disabled={step === 0} onClick={() => setStep(s => s - 1)}>
                <ArrowLeft className="w-4 h-4 mr-1" /> Back
              </Button>
              {step < 6 ? (
                <Button onClick={() => setStep(s => s + 1)} disabled={!canNext()} className="gradient-primary text-white border-0">
                  Continue <ArrowRight className="w-4 h-4 ml-1" />
                </Button>
              ) : (
                <Button onClick={handleFinish} disabled={saving} className="gradient-primary text-white border-0">
                  {saving ? "Starting..." : "Start My Scan"} <Search className="w-4 h-4 ml-1" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}