import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { X, Loader2, CheckCircle2 } from "lucide-react";

const TITLES = {
  waitlist: "Join the Waitlist",
  cleanup: "Request SEO Cleanup",
  custom_rebuild: "Contact Us About a Rebuild",
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
      setSuccess(true);
    } catch (e) {
      setError("Something went wrong. Please try again.");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-bold text-gray-900">{TITLES[requestType]}</h2>
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
            <div>
              <Label>Name</Label>
              <Input className="mt-1.5" value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" />
            </div>
            <div>
              <Label>Email</Label>
              <Input className="mt-1.5" type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <Label>Website URL</Label>
              <Input className="mt-1.5" value={form.website_url} onChange={e => update("website_url", e.target.value)} placeholder="https://yourwebsite.com" />
            </div>
            <div>
              <Label>Message (optional)</Label>
              <Textarea className="mt-1.5" value={form.message} onChange={e => update("message", e.target.value)} placeholder="Tell us a bit about what you need..." rows={3} />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button onClick={handleSubmit} disabled={!canSubmit || saving} className="w-full gradient-primary text-white border-0">
              {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {saving ? "Sending..." : "Send Request"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}