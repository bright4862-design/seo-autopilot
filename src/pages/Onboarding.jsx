import React from "react";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";

// The New Scan page. Layout lives in the form itself (the same centred 680px
// paper-and-ink column the landing page and dashboard header use); the old
// scanner-minimal.css overrode it with positional selectors such as
// `form > div:first-child > div:first-child`, which is what stripped the input
// borders and left the orphaned selection-card thumb behind.
export default function Onboarding() {
  return <ScanWebsiteForm />;
}