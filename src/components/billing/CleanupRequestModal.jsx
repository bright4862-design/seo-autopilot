import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { X, Loader2 } from "lucide-react";

const HELP_OPTIONS = [
  "Help me review prepared recommendations",
  "Help me decide what to approve",
  "Help me improve website content",
  "Help me with larger website improvements",
  "I want a custom quote",
];

export default function CleanupRequestModal({ onClose }) {
  const [form, setForm] = useState({ name: "", email: "", business_name: "", website_url: "", message: "" });
  const [project, setProject] = useState(null);
  const [scanSummary, setScanSummary] = useState(null);
  const [selectedOptions, setSelectedOptions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const prefill = async () => {
      try {
        const user = await base44.auth.me();
        const projects = await base44.entities.BusinessProject.list("-created_date", 1);
        const proj = projects[0] || null;
        setProject(proj);
        setForm(prev => ({
          ...prev,
          name: user.full_name || "",
          email: user.email || "",
          business_name: proj?.business_name || "",
          website_url: proj?.website_url || "",
        }));
        if (proj) {
          const issues = await base44.entities.SeoIssue.filter({ project_id: proj.id });
          setScanSummary({
            health_score: proj.seo_score || 0,
            prepared_fixes: issues.filter(i => i.status === "auto_fixed").length,
            needs_approval: issues.filter(i => i.status === "needs_approval").length,
            needs_developer: issues.filter(i => i.status === "needs_developer").length,
          });
        }
      } catch (e) {}
    };
    prefill();
  }, []);

  const update = (field, value) => setForm(prev => ({ ...prev, [field]: value }));
  const toggleOption = (option) => setSelectedOptions(prev => prev.includes(option) ? prev.filter(o => o !== option) : [...prev, option]);
  const canSubmit = form.name.trim() && form.email.trim();

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const user = await base44.auth.me();
      await base44.entities.LeadRequest.create({
        owner_user_id: user.id,
        project_id: project?.id || "",
        name: form.name.trim(),
        email: form.email.trim(),
        business_name: form.business_name.trim(),
        website_url: form.website_url.trim(),
        request_type: "cleanup",
        selected_plan: "$500 Cleanup",
        message: form.message.trim(),
        scan_summary: scanSummary || undefined,
        selected_help_options: selectedOptions,
        status: "new",
        created_at: new Date().toISOString(),
      });
      setSuccess(true);
    } catch (e) {
      setError("Something went wrong. Please try again.");
    }
    setSaving(false);
  };

  const inputClass = "mt-2 h-11 rounded-xl border-slate-200 bg-white text-[15px] shadow-none focus-visible:ring-blue-600";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/25 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white shadow-2xl shadow-slate-950/10" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-100 bg-white px-6 py-5">
          <h2 className="text-lg font-semibold text-slate-950">Request done-for-you help</h2>
          <button onClick={onClose} className="rounded-full p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><X className="h-4 w-4" /></button>
        </div>

        {success ? (
          <div className="p-8 text-center">
            <p className="text-base font-medium text-slate-950">Thanks — we received your request.</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">We’ll review your scan and follow up soon.</p>
            <Button onClick={onClose} className="mt-5 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Close</Button>
          </div>
        ) : (
          <div className="space-y-5 p-6">
            {scanSummary && (
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/70">
                <div className="border-b border-slate-200/70 px-4 py-3"><p className="text-sm font-medium text-slate-950">Latest scan</p></div>
                <div className="grid grid-cols-2 divide-x divide-y divide-slate-200/70 text-center sm:grid-cols-4 sm:divide-y-0">
                  <div className="p-3"><p className="text-lg font-semibold text-slate-950">{scanSummary.health_score}</p><p className="text-xs text-slate-500">Score</p></div>
                  <div className="p-3"><p className="text-lg font-semibold text-slate-950">{scanSummary.prepared_fixes}</p><p className="text-xs text-slate-500">Prepared</p></div>
                  <div className="p-3"><p className="text-lg font-semibold text-slate-950">{scanSummary.needs_approval}</p><p className="text-xs text-slate-500">Review</p></div>
                  <div className="p-3"><p className="text-lg font-semibold text-slate-950">{scanSummary.needs_developer}</p><p className="text-xs text-slate-500">Help</p></div>
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div><Label>Name</Label><Input className={inputClass} value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" /></div>
              <div><Label>Email</Label><Input className={inputClass} type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@example.com" /></div>
              <div><Label>Business name</Label><Input className={inputClass} value={form.business_name} onChange={e => update("business_name", e.target.value)} placeholder="Your business" /></div>
              <div><Label>Website address</Label><Input className={inputClass} value={form.website_url} onChange={e => update("website_url", e.target.value)} placeholder="https://yourwebsite.com" /></div>
            </div>

            <div>
              <Label>What would you like help with?</Label>
              <div className="mt-3 space-y-3">
                {HELP_OPTIONS.map(option => (
                  <label key={option} className="flex cursor-pointer items-center gap-3 text-sm text-slate-700">
                    <Checkbox checked={selectedOptions.includes(option)} onCheckedChange={() => toggleOption(option)} />
                    {option}
                  </label>
                ))}
              </div>
            </div>

            <div><Label>Message <span className="font-normal text-slate-400">optional</span></Label><Textarea className="mt-2 rounded-xl border-slate-200 bg-white text-[15px] shadow-none focus-visible:ring-blue-600" value={form.message} onChange={e => update("message", e.target.value)} placeholder="Anything else we should know?" rows={3} /></div>

            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button onClick={handleSubmit} disabled={!canSubmit || saving} className="w-full rounded-full bg-blue-600 text-sm font-medium text-white shadow-none hover:bg-blue-700">
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {saving ? "Sending…" : "Send request"}
            </Button>
            <p className="text-center text-xs leading-5 text-slate-400">We’ll review your scan and reply by email. Nothing is changed on your website until you approve it.</p>
          </div>
        )}
      </div>
    </div>
  );
}