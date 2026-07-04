import React, { useState } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Globe, Users, Loader2, Trash2 } from "lucide-react";

export default function UrlSubmissionPanel({ project, onWebsiteAdded, onCompetitorAdded }) {
  const [mode, setMode] = useState("website");
  const [websiteName, setWebsiteName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [competitorName, setCompetitorName] = useState("");
  const [competitorUrl, setCompetitorUrl] = useState("");
  const [competitorNotes, setCompetitorNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const normalizeUrl = (url) => {
    if (!/^https?:\/\//i.test(url)) return "https://" + url;
    return url;
  };

  const handleAddWebsite = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      const created = await base44.entities.BusinessProject.create({
        business_name: websiteName,
        website_url: normalizeUrl(websiteUrl),
        status: "active",
      });
      setWebsiteName("");
      setWebsiteUrl("");
      setSuccess("Website added. Switch projects to start scanning it.");
      onWebsiteAdded && onWebsiteAdded(created);
    } catch (err) {
      setError(err.message || "Failed to add website");
    } finally {
      setLoading(false);
    }
  };

  const handleAddCompetitor = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!project) {
      setError("Set up your website first before adding competitors.");
      return;
    }
    setLoading(true);
    try {
      const created = await base44.entities.Competitor.create({
        project_id: project.id,
        name: competitorName || competitorUrl,
        website_url: normalizeUrl(competitorUrl),
        notes: competitorNotes,
      });
      setCompetitorName("");
      setCompetitorUrl("");
      setCompetitorNotes("");
      setSuccess("Competitor added.");
      onCompetitorAdded && onCompetitorAdded(created);
    } catch (err) {
      setError(err.message || "Failed to add competitor");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6">
      <div className="flex gap-2 mb-5 p-1 bg-gray-100 rounded-lg w-fit">
        <button
          type="button"
          onClick={() => { setMode("website"); setError(""); setSuccess(""); }}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${mode === "website" ? "bg-white text-blue-600 shadow-sm" : "text-gray-500"}`}
        >
          <Globe className="w-4 h-4" /> New Website
        </button>
        <button
          type="button"
          onClick={() => { setMode("competitor"); setError(""); setSuccess(""); }}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${mode === "competitor" ? "bg-white text-blue-600 shadow-sm" : "text-gray-500"}`}
        >
          <Users className="w-4 h-4" /> Competitor
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-green-50 text-green-700 text-sm">{success}</div>
      )}

      {mode === "website" ? (
        <form onSubmit={handleAddWebsite} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="web-name">Business Name</Label>
              <Input id="web-name" placeholder="Acme Plumbing" value={websiteName} onChange={(e) => setWebsiteName(e.target.value)} className="h-11" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="web-url">Website URL</Label>
              <Input id="web-url" placeholder="example.com" value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} className="h-11" required />
            </div>
          </div>
          <Button type="submit" disabled={loading} className="gradient-primary text-white border-0">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
            Add Website
          </Button>
        </form>
      ) : (
        <form onSubmit={handleAddCompetitor} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="comp-name">Competitor Name</Label>
              <Input id="comp-name" placeholder="Rival Co" value={competitorName} onChange={(e) => setCompetitorName(e.target.value)} className="h-11" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="comp-url">Website URL</Label>
              <Input id="comp-url" placeholder="competitor.com" value={competitorUrl} onChange={(e) => setCompetitorUrl(e.target.value)} className="h-11" required />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="comp-notes">Notes (optional)</Label>
            <Input id="comp-notes" placeholder="What do they do well?" value={competitorNotes} onChange={(e) => setCompetitorNotes(e.target.value)} className="h-11" />
          </div>
          <Button type="submit" disabled={loading} className="gradient-primary text-white border-0">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
            Add Competitor
          </Button>
        </form>
      )}
    </div>
  );
}