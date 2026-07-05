import React, { useEffect, useState } from "react";
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

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="grid gap-5">
        <div>
          <Label htmlFor="business-name" className="text-sm font-medium text-slate-700">Business name</Label>
          <Input id="business-name" placeholder="e.g. Norris Wine" value={businessName} onChange={(event) => setBusinessName(event.target.value)} className="mt-2 h-11 rounded-xl border-slate-200 bg-white" />
        </div>
        <div>
          <Label htmlFor="website-url" className="text-sm font-medium text-slate-700">Website URL</Label>
          <Input id="website-url" placeholder="https://yourwebsite.com" value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} className="mt-2 h-11 rounded-xl border-slate-200 bg-white" />
        </div>
        <div>
          <Label htmlFor="keywords" className="text-sm font-medium text-slate-700">Important keywords <span className="font-normal text-slate-400">optional</span></Label>
          <Input id="keywords" placeholder="wine tasting, local wine shop, organic wine" value={keywords} onChange={(event) => setKeywords(event.target.value)} className="mt-2 h-11 rounded-xl border-slate-200 bg-white" />
        </div>
        <div>
          <Label className="text-sm font-medium text-slate-700">Competitor pages <span className="font-normal text-slate-400">optional</span></Label>
          <div className="mt-2 grid gap-2">
            {competitorUrls.map((url, index) => (
              <Input key={index} placeholder={`Competitor page ${index + 1}`} value={url} onChange={(event) => setCompetitorUrls((prev) => prev.map((value, itemIndex) => itemIndex === index ? event.target.value : value))} className="h-11 rounded-xl border-slate-200 bg-white" />
            ))}
          </div>
        </div>
        <Button type="submit" disabled={!canSubmit} className="h-11 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {saving ? "Scanning…" : "Start Scan"}
        </Button>
      </div>
    </form>
  );
}