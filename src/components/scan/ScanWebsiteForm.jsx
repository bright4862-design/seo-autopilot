import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Search, Globe, Building2, Loader2 } from "lucide-react";

export default function ScanWebsiteForm({ project, competitors = [], saving, onScan }) {
  const [businessName, setBusinessName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [competitorUrls, setCompetitorUrls] = useState(["", "", ""]);

  useEffect(() => {
    if (project) {
      setBusinessName(project.business_name || "");
      setWebsiteUrl(project.website_url || "");
    }
  }, [project]);

  useEffect(() => {
    if (competitors.length > 0) {
      setCompetitorUrls([0, 1, 2].map(i => competitors[i]?.website_url || ""));
    }
  }, [competitors]);

  const canSubmit = businessName.trim().length > 0 && websiteUrl.trim().length > 0 && !saving;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 space-y-4">
      <div>
        <Label>Business name</Label>
        <div className="relative mt-1.5">
          <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input placeholder="e.g. Norris Wine" value={businessName} onChange={e => setBusinessName(e.target.value)} className="pl-9" />
        </div>
      </div>
      <div>
        <Label>Website URL</Label>
        <div className="relative mt-1.5">
          <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input placeholder="https://yourwebsite.com" value={websiteUrl} onChange={e => setWebsiteUrl(e.target.value)} className="pl-9" />
        </div>
      </div>
      <div>
        <Label>Competitor websites <span className="text-gray-400 font-normal">(optional)</span></Label>
        <div className="space-y-2 mt-1.5">
          {competitorUrls.map((url, i) => (
            <Input
              key={i}
              placeholder={`Competitor ${i + 1}`}
              value={url}
              onChange={e => setCompetitorUrls(prev => prev.map((v, idx) => (idx === i ? e.target.value : v)))}
            />
          ))}
        </div>
      </div>
      <Button
        onClick={() => onScan({ business_name: businessName.trim(), website_url: websiteUrl.trim(), competitor_urls: competitorUrls })}
        disabled={!canSubmit}
        className="w-full gradient-primary text-white border-0 h-11"
      >
        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
        {saving ? "Scanning..." : "Scan Website"}
      </Button>
    </div>
  );
}