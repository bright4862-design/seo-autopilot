import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";

export default function ScanWebsiteForm({ project, competitors = [], saving, onScan }) {
  const [businessName, setBusinessName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [keywords, setKeywords] = useState("");
  const [competitorUrls, setCompetitorUrls] = useState(["", "", ""]);

  useEffect(() => {
    if (project) {
      setBusinessName(project.business_name || "");
      setWebsiteUrl(project.website_url || "");
      setKeywords((project.important_keywords || []).join(", "));
    }
  }, [project]);

  useEffect(() => {
    if (competitors.length > 0) {
      setCompetitorUrls([0, 1, 2].map((index) => competitors[index]?.website_url || ""));
    }
  }, [competitors]);

  const canSubmit = businessName.trim().length > 0 && websiteUrl.trim().length > 0 && !saving;
  const hasCompetitorInput = keywords.trim().length > 0 || competitorUrls.some((url) => url.trim().length > 0);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    onScan({
      business_name: businessName.trim(),
      website_url: websiteUrl.trim(),
      important_keywords: keywords.split(",").map((keyword) => keyword.trim()).filter(Boolean),
      competitor_urls: competitorUrls,
    });
  };

  const inputClass = "mt-2 h-11 rounded-xl border-slate-200 bg-white text-[15px] shadow-none focus-visible:ring-blue-600";

  return (
    <form onSubmit={handleSubmit} className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="divide-y divide-slate-100">
        <div className="p-5 sm:p-6">
          <Label htmlFor="business-name" className="text-sm font-medium text-slate-900">Business name</Label>
          <Input id="business-name" placeholder="e.g. Norris Wine" value={businessName} onChange={(event) => setBusinessName(event.target.value)} className={inputClass} />
        </div>
        <div className="p-5 sm:p-6">
          <Label htmlFor="website-url" className="text-sm font-medium text-slate-900">Website address</Label>
          <Input id="website-url" placeholder="https://yourwebsite.com" value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} className={inputClass} />
        </div>
        <div className="p-5 sm:p-6">
          <Label htmlFor="keywords" className="text-sm font-medium text-slate-900">Words customers might search for <span className="font-normal text-slate-400">optional</span></Label>
          <Input id="keywords" placeholder="wine tasting, local wine shop, organic wine" value={keywords} onChange={(event) => setKeywords(event.target.value)} className={inputClass} />
        </div>
        <div className="p-5 sm:p-6">
          <Label className="text-sm font-medium text-slate-900">Competitor pages <span className="font-normal text-slate-400">optional</span></Label>
          <p className="mt-1 text-sm leading-6 text-slate-500">Add pages you want to compare against.</p>
          <p className="mt-1 text-sm leading-6 text-slate-500">After your scan, we’ll compare these pages and show gaps in your Fix List.</p>
          {hasCompetitorInput && <Link to="/competitors" className="mt-2 inline-block text-sm font-medium text-blue-600 hover:text-blue-700">View competitor gaps</Link>}
          <div className="mt-3 grid gap-2">
            {competitorUrls.map((url, index) => (
              <Input key={index} placeholder={`Competitor page ${index + 1}`} value={url} onChange={(event) => setCompetitorUrls((prev) => prev.map((value, itemIndex) => itemIndex === index ? event.target.value : value))} className={inputClass} />
            ))}
          </div>
        </div>
      </div>
      <div className="flex justify-end bg-slate-50/70 px-5 py-4 sm:px-6">
        <Button type="submit" disabled={!canSubmit} className="h-11 rounded-full bg-blue-600 px-6 text-sm font-medium text-white shadow-none hover:bg-blue-700">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {saving ? "Scanning…" : "Start scan"}
        </Button>
      </div>
    </form>
  );
}