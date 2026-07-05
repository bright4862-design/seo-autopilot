import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { X, Loader2 } from "lucide-react";

const TITLES = {
  waitlist: "Join the waitlist",
  cleanup: "Request cleanup help",
  custom_rebuild: "Ask about a rebuild",
};

export default function LeadRequestModal({ requestType, selectedPlan, onClose }) {
  const [form, setForm] = useState({ name: "", email: "", website_url: "", message: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const prefill = async () => {
      try {
        const user = await base44.auth.me();
        const projects = await base44.entities.BusinessProject.list("-created_date", 1);
        setForm(prev => ({
          ...prev,
          name: prev.name || user.full_name || "",
          email: prev.email || user.email || "",
          website_url: prev.website_url || (projects[0]?.website_url || ""),
        }));
      } catch (e) {}
    };
    prefill();
  }, []);

  const update = (field, value) => setForm(prev => ({ ...prev, [field]: value }));
  const canSubmit = form.name.trim() && form.email.trim();

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const user = await base44.auth.me();
      await base44.entities.LeadRequest.create({
        owner_user_id: user.id,
        name: form.name.trim(),
        email: form.email.trim(),
        website_url: form.website_url.trim(),
        request_type: requestType,
        selected_plan: selectedPlan,
        message: form.message.trim(),
        status: "new",
        created_at: new Date().toISOString(),
      });
      trackEvent(requestType === "waitlist" ? "waitlist_joined" : "contact_submitted", { selected_plan: selectedPlan, request_type: requestType });
      setSuccess(true);
    } catch (e) {
      setError("Something went wrong. Please try again.");
    }
    setSaving(false);
  };

  const inputClass = "mt-2 h-11 rounded-xl border-slate-200 bg-white text-[15px] shadow-none focus-visible:ring-blue-600";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/25 p-4" onClick={onClose}>
      <div className="w-full max-w-md overflow-hidden rounded-3xl bg-white shadow-2xl shadow-slate-950/10" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <h2 className="text-lg font-semibold text-slate-950">{TITLES[requestType]}</h2>
          <button onClick={onClose} className="rounded-full p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><X className="h-4 w-4" /></button>
        </div>

        {success ? (
          <div className="p-8 text-center">
            <p className="text-base font-medium text-slate-950">Thanks — we received your request.</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">We’ll follow up soon.</p>
            <Button onClick={onClose} className="mt-5 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Close</Button>
          </div>
        ) : (
          <div className="space-y-5 p-6">
            <div><Label>Name</Label><Input className={inputClass} value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" /></div>
            <div><Label>Email</Label><Input className={inputClass} type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@example.com" /></div>
            <div><Label>Website address</Label><Input className={inputClass} value={form.website_url} onChange={e => update("website_url", e.target.value)} placeholder="https://yourwebsite.com" /></div>
            <div><Label>Message <span className="font-normal text-slate-400">optional</span></Label><Textarea className="mt-2 rounded-xl border-slate-200 bg-white text-[15px] shadow-none focus-visible:ring-blue-600" value={form.message} onChange={e => update("message", e.target.value)} placeholder="Tell us what you need." rows={3} /></div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button onClick={handleSubmit} disabled={!canSubmit || saving} className="w-full rounded-full bg-blue-600 text-sm font-medium text-white shadow-none hover:bg-blue-700">
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {saving ? "Sending…" : "Send request"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}