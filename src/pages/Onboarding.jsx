import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Zap, Search, Globe, Building2, Loader2 } from "lucide-react";

export default function Onboarding() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState({ business_name: "", website_url: "" });
  const [competitorUrls, setCompetitorUrls] = useState(["", "", ""]);

  const update = (field, value) => setData(prev => ({ ...prev, [field]: value }));
  const updateCompetitor = (i, value) => setCompetitorUrls(prev => prev.map((v, idx) => (idx === i ? value : v)));
  const canSubmit = data.business_name.trim().length > 0 && data.website_url.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      const user = await base44.auth.me();
      const project = await base44.entities.BusinessProject.create({
        business_name: data.business_name.trim(),
        website_url: data.website_url.trim(),
        status: "active",
        seo_score: 0,
        subscription_plan: "free",
        cms_platform: "Unknown",
        owner_user_id: user.id,
      });
      await base44.entities.CrawlJob.create({
        project_id: project.id,
        status: "queued",
        crawl_type: "full",
        owner_user_id: user.id,
      });
      const compUrls = competitorUrls.map(u => u.trim()).filter(Boolean);
      if (compUrls.length > 0) {
        await base44.entities.Competitor.bulkCreate(compUrls.map(url => {
          let name = url;
          try { name = new URL(/^https?:\/\//i.test(url) ? url : "https://" + url).hostname.replace(/^www\./, ""); } catch (e) {}
          return { project_id: project.id, website_url: url, name, owner_user_id: user.id };
        }));
      }
      navigate("/crawl-status?autostart=1");
    } catch (e) {
      console.error("Failed to start scan", e);
      setSaving(false);
    }
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
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl border border-gray-100 shadow-xl shadow-gray-100/50 p-8">
            <div className="text-center mb-6">
              <div className="w-14 h-14 rounded-2xl gradient-primary flex items-center justify-center mx-auto mb-4">
                <Search className="w-7 h-7 text-white" />
              </div>
              <h1 className="font-bold text-xl">Let's scan your website</h1>
              <p className="text-sm text-gray-500 mt-1">
                Enter your business and website — we'll find simple SEO fixes in minutes.
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <Label>Business name</Label>
                <div className="relative mt-1.5">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <Input
                    placeholder="e.g. Sunshine Plumbing"
                    value={data.business_name}
                    onChange={e => update("business_name", e.target.value)}
                    className="pl-9"
                  />
                </div>
              </div>
              <div>
                <Label>Website URL</Label>
                <div className="relative mt-1.5">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <Input
                    placeholder="https://yourwebsite.com"
                    value={data.website_url}
                    onChange={e => update("website_url", e.target.value)}
                    className="pl-9"
                  />
                </div>
                <p className="text-xs text-gray-400 mt-2">We'll crawl this site to find easy SEO wins.</p>
              </div>
              <div>
                <Label>Competitor websites <span className="text-gray-400 font-normal">(optional)</span></Label>
                <div className="space-y-2 mt-1.5">
                  {competitorUrls.map((url, i) => (
                    <Input
                      key={i}
                      placeholder={`Competitor website ${i + 1}`}
                      value={url}
                      onChange={e => updateCompetitor(i, e.target.value)}
                    />
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">We'll compare your site against them in plain English.</p>
              </div>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!canSubmit || saving}
              className="w-full mt-6 gradient-primary text-white border-0 h-11"
            >
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
              {saving ? "Starting scan..." : "Scan My Website"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}