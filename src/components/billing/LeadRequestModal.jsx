import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { X } from "lucide-react";

const TITLES = {
  waitlist: "Join the waitlist",
  cleanup: "Request cleanup help",
  custom_rebuild: "Ask about a rebuild",
};

// Opens over Billing, so it uses that page's paper/ink palette and pill
// buttons rather than the template's blue-and-slate card styling.
const FIELD_CLASS =
  "mt-2 w-full rounded-xl border border-hairline bg-white/60 px-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-faint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink";
const LABEL_CLASS = "text-[13px] font-medium text-ink";

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={TITLES[requestType]}
        className="w-full max-w-md overflow-hidden rounded-2xl border border-hairline bg-paper text-ink shadow-xl shadow-ink/10"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-hairline-soft px-6 py-5">
          <h2 className="text-[17px] font-semibold tracking-tight">{TITLES[requestType]}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-2 text-ink-faint transition-colors hover:bg-ink/[0.04] hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {success ? (
          <div className="px-6 py-8 text-center">
            <p className="text-[15px] font-medium">Thanks — we received your request.</p>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">We&rsquo;ll follow up soon.</p>
            <button
              type="button"
              onClick={onClose}
              className="mt-6 rounded-full bg-ink px-5 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Close
            </button>
          </div>
        ) : (
          <div className="space-y-5 p-6">
            <div>
              <label className={LABEL_CLASS} htmlFor="lead-name">Name</label>
              <input id="lead-name" className={FIELD_CLASS} value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="lead-email">Email</label>
              <input id="lead-email" className={FIELD_CLASS} type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="lead-website">Website address</label>
              <input id="lead-website" className={FIELD_CLASS} value={form.website_url} onChange={e => update("website_url", e.target.value)} placeholder="https://yourwebsite.com" />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="lead-message">
                Message <span className="font-normal text-ink-faint">optional</span>
              </label>
              <textarea id="lead-message" className={FIELD_CLASS} value={form.message} onChange={e => update("message", e.target.value)} placeholder="Tell us what you need." rows={3} />
            </div>
            {error && <p className="text-[13.5px] text-crit" role="alert">{error}</p>}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit || saving}
              className="w-full rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40"
            >
              {saving ? "Sending…" : "Send request"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
