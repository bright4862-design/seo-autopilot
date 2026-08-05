import React from "react";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";

// The New Scan page. Layout lives in the form itself (a centred 640px column);
// the old scanner-minimal.css overrode it with positional selectors such as
// `form > div:first-child > div:first-child`, which is what stripped the input
// borders and left the orphaned selection-card thumb behind.
export default function Onboarding() {
  return (
    <div className="mx-auto w-full max-w-[640px] px-4 py-12 sm:px-6 sm:py-16">
      <ScanWebsiteForm />
    </div>
  );
}
