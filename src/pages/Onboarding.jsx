import React, { useEffect, useMemo, useState } from "react";
import { Bug, Copy, RefreshCw, Trash2 } from "lucide-react";

import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";
import { Button } from "@/components/ui/button";

const STORAGE_KEYS = [
  "seo_autopilot:last_scan",
  "SEO_AUTOPILOT_LAST_SCAN",
  "seo_autopilot:scan_history",
  "SEO_AUTOPILOT_SCAN_HISTORY",
  "seo_autopilot:active_scan_url",
  "seo_autopilot:active_scan_started_at",
];

export default function Onboarding() {
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugData, setDebugData] = useState(() => readDebugData());
  const [copied, setCopied] = useState(false);

  function refreshDebug() {
    setDebugData(readDebugData());
  }

  function clearScanData() {
    try {
      STORAGE_KEYS.forEach((key) => {
        window.localStorage.removeItem(key);
      });

      window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
      refreshDebug();
    } catch (error) {
      console.warn("Could not clear scan debug data.", error);
    }
  }

  async function copyDebugJson() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(debugData, null, 2));
      setCopied(true);

      window.setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch (error) {
      console.warn("Could not copy debug data.", error);
    }
  }

  useEffect(() => {
    function handleRefresh() {
      refreshDebug();
    }

    window.addEventListener("seo-autopilot-scan-saved", handleRefresh);
    window.addEventListener("storage", handleRefresh);

    return () => {
      window.removeEventListener("seo-autopilot-scan-saved", handleRefresh);
      window.removeEventListener("storage", handleRefresh);
    };
  }, []);

  const summary = useMemo(() => {
    const lastScan = debugData.parsed?.["seo_autopilot:last_scan"];
    const legacyLastScan = debugData.parsed?.["SEO_AUTOPILOT_LAST_SCAN"];
    const scan = lastScan || legacyLastScan || null;

    return {
      websiteUrl: scan?.website_url || "",
      businessName: scan?.business_name || "",
      score: scan?.health_score || scan?.seo_score || 0,
      pages:
        scan?.pages_crawled ||
        scan?.pages?.length ||
        scan?.crawled_pages?.length ||
        scan?.scanned_pages?.length ||
        0,
      recommendations:
        scan?.recommendations?.length ||
        scan?.fixes?.length ||
        scan?.findings?.length ||
        0,
      crawlPrefix:
        scan?.crawl_scope?.start_path_prefix ||
        scan?.requested_path_prefix ||
        "",
      createdAt: scan?.created_at || "",
    };
  }, [debugData]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-950">
            Start a review
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            SEO Autopilot scans your website, reviews important pages, looks for
            competitor opportunities when possible, and prepares a simple Fix
            List.
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={() => {
            refreshDebug();
            setDebugOpen((value) => !value);
          }}
          className="shrink-0"
        >
          <Bug className="mr-2 h-4 w-4" />
          {debugOpen ? "Hide debug" : "Show debug"}
        </Button>
      </div>

      {debugOpen ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-950">
                Scan debug
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Use this to check whether the dashboard is showing the newest
                scan or old saved data.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={refreshDebug}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>

              <Button type="button" variant="outline" onClick={copyDebugJson}>
                <Copy className="mr-2 h-4 w-4" />
                {copied ? "Copied" : "Copy JSON"}
              </Button>

              <Button type="button" variant="outline" onClick={clearScanData}>
                <Trash2 className="mr-2 h-4 w-4" />
                Clear scans
              </Button>
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <DebugStat label="Website" value={summary.websiteUrl || "None"} />
            <DebugStat label="Business" value={summary.businessName || "None"} />
            <DebugStat label="Score" value={summary.score || "None"} />
            <DebugStat label="Pages" value={summary.pages || "0"} />
            <DebugStat
              label="Recommendations"
              value={summary.recommendations || "0"}
            />
            <DebugStat
              label="Path prefix"
              value={summary.crawlPrefix || "None"}
            />
          </div>

          {summary.createdAt ? (
            <p className="mt-4 text-xs text-slate-500">
              Last saved scan: {formatDate(summary.createdAt)}
            </p>
          ) : null}

          <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
            <pre className="max-h-[520px] overflow-auto p-4 text-xs leading-5 text-slate-100">
              {JSON.stringify(debugData, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}

      <ScanWebsiteForm />
    </div>
  );
}

function DebugStat({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 break-words text-sm font-semibold text-slate-950">
        {String(value)}
      </div>
    </div>
  );
}

function readDebugData() {
  if (typeof window === "undefined") {
    return {
      raw: {},
      parsed: {},
      parse_errors: {},
    };
  }

  const raw = {};
  const parsed = {};
  const parseErrors = {};

  for (const key of STORAGE_KEYS) {
    try {
      const value = window.localStorage.getItem(key);

      raw[key] = value;

      if (value === null || value === undefined || value === "") {
        parsed[key] = null;
        continue;
      }

      try {
        parsed[key] = JSON.parse(value);
      } catch {
        parsed[key] = value;
      }
    } catch (error) {
      raw[key] = null;
      parsed[key] = null;
      parseErrors[key] = error?.message || "Could not read localStorage key.";
    }
  }

  return {
    read_at: new Date().toISOString(),
    raw,
    parsed,
    parse_errors: parseErrors,
  };
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}import React from "react";
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