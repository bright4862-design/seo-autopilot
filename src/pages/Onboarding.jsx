import React from "react";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";

export default function Onboarding() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-950">Start a review</h1>
        <p className="mt-2 text-sm text-slate-600">
          SEO Autopilot scans your website, reviews important pages, looks for
          competitor opportunities when possible, and prepares a simple Fix List.
        </p>
      </div>

      <ScanWebsiteForm />
    </div>
  );
}