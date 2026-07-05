import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { X, Loader2, CheckCircle2 } from "lucide-react";

const HELP_OPTIONS = [
  "Help me review prepared fixes",
  "Help me approve technical recommendations",
  "Help me improve website content",
  "Help me fix developer recommendations",
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
  const toggleOption = (option) =>
    setSelectedOptions(prev => prev.includes(option) ? prev.filter(o => o !== option) : [...prev, option]);
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

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 sticky top-0 bg-white rounded-t-2xl">
          <h2 className="font-bold text-gray-900">Request Done-for-You Help</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100"><X className="w-4 h-4" /></button>
        </div>

        {success ? (
          <div className="p-8 text-center">
            <CheckCircle2 className="w-10 h-10 text-green-500 mx-auto mb-3" />
            <p className="font-medium text-gray-800 mb-1">Thanks — we received your request and will follow up soon.</p>
            <Button onClick={onClose} className="mt-4 gradient-primary text-white border-0">Close</Button>
          </div>
        ) : (
          <div className="p-6 space-y-4">
            {scanSummary && (
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                <p className="text-xs font-medium text-blue-900 uppercase tracking-wider mb-2">Your latest scan</p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div>
                    <p className="text-lg font-bold text-blue-700">{scanSummary.health_score}</p>
                    <p className="text-[11px] text-gray-500">Health score</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-green-600">{scanSummary.prepared_fixes}</p>
                    <p className="text-[11px] text-gray-500">Prepared</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-amber-600">{scanSummary.needs_approval}</p>
                    <p className="text-[11px] text-gray-500">Needs approval</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-purple-600">{scanSummary.needs_developer}</p>
                    <p className="text-[11px] text-gray-500">Needs developer</p>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Name</Label>
                <Input className="mt-1.5" value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" />
              </div>
              <div>
                <Label>Email</Label>
                <Input className="mt-1.5" type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@example.com" />
              </div>
              <div>
                <Label>Business name</Label>
                <Input className="mt-1.5" value={form.business_name} onChange={e => update("business_name", e.target.value)} placeholder="Your business" />
              </div>
              <div>
                <Label>Website URL</Label>
                <Input className="mt-1.5" value={form.website_url} onChange={e => update("website_url", e.target.value)} placeholder="https://yourwebsite.com" />
              </div>
            </div>

            <div>
              <Label>What would you like help with?</Label>
              <div className="mt-2 space-y-2">
                {HELP_OPTIONS.map(option => (
                  <label key={option} className="flex items-center gap-2.5 text-sm text-gray-700 cursor-pointer">
                    <Checkbox
                      checked={selectedOptions.includes(option)}
                      onCheckedChange={() => toggleOption(option)}
                    />
                    {option}
                  </label>
                ))}
              </div>
            </div>

            <div>
              <Label>Message (optional)</Label>
              <Textarea className="mt-1.5" value={form.message} onChange={e => update("message", e.target.value)} placeholder="Anything else we should know?" rows={3} />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button onClick={handleSubmit} disabled={!canSubmit || saving} className="w-full gradient-primary text-white border-0">
              {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {saving ? "Sending..." : "Send Request"}
            </Button>
            <p className="text-xs text-gray-400 text-center">We'll review your scan results and reply by email. Nothing is changed on your website until you approve it.</p>
          </div>
        )}
      </div>
    </div>
  );
}