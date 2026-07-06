import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  LayoutDashboard,
  ListChecks,
  MonitorCog,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const DASHBOARD_LAST_SCAN_KEY = "seo_autopilot:last_scan";
const DASHBOARD_HISTORY_KEY = "seo_autopilot:scan_history";

const LEGACY_LAST_SCAN_KEY = "SEO_AUTOPILOT_LAST_SCAN";
const LEGACY_HISTORY_KEY = "SEO_AUTOPILOT_SCAN_HISTORY";

const ACTIVE_SCAN_URL_KEY = "seo_autopilot:active_scan_url";
const ACTIVE_SCAN_STARTED_AT_KEY = "seo_autopilot:active_scan_started_at";
const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";

const STORAGE_KEYS = [
  DASHBOARD_LAST_SCAN_KEY,
  LEGACY_LAST_SCAN_KEY,
  DASHBOARD_HISTORY_KEY,
  LEGACY_HISTORY_KEY,
  ACTIVE_SCAN_URL_KEY,
  ACTIVE_SCAN_STARTED_AT_KEY,
  SCAN_DEBUG_KEY,
];

const CMS_OPTIONS = [
  { value: "wordpress", label: "WordPress" },
  { value: "squarespace", label: "Squarespace" },
  { value: "wix", label: "Wix" },
  { value: "shopify", label: "Shopify" },
  { value: "webflow", label: "Webflow" },
  { value: "framer", label: "Framer" },
  { value: "godaddy", label: "GoDaddy" },
  { value: "joomla", label: "Joomla" },
  { value: "custom", label: "Custom / Not sure" },
];

const PRIORITY_FILTERS = [
  { value: "all", label: "All" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export default function FixList() {
  const navigate = useNavigate();

  const [scanRecord, setScanRecord] = useState(() => readBestScanRecord());
  const [debugData, setDebugData] = useState(() => readScanDebugData());
  const [selectedCms, setSelectedCms] = useState(() =>
    normalizeCmsValue(scanRecord?.cms_platform || "wordpress")
  );
  const [priorityFilter, setPriorityFilter] = useState("all");

  function reloadScan() {
    const nextScan = readBestScanRecord();

    setScanRecord(nextScan);
    setDebugData(readScanDebugData());

    if (nextScan?.cms_platform) {
      setSelectedCms(normalizeCmsValue(nextScan.cms_platform));
    }
  }

  useEffect(() => {
    reloadScan();

    window.addEventListener("seo-autopilot-scan-saved", reloadScan);
    window.addEventListener("storage", reloadScan);

    return () => {
      window.removeEventListener("seo-autopilot-scan-saved", reloadScan);
      window.removeEventListener("storage", reloadScan);
    };
  }, []);

  const recommendations = useMemo(() => {
    return getRecommendations(scanRecord).map(normalizeRecommendation);
  }, [scanRecord]);

  const filteredRecommendations = useMemo(() => {
    if (priorityFilter === "all") return recommendations;

    return recommendations.filter((item) => item.priority === priorityFilter);
  }, [priorityFilter, recommendations]);

  const pages = useMemo(() => getPages(scanRecord), [scanRecord]);

  const healthScore = getHealthScore(scanRecord);
  const highPriorityCount = recommendations.filter((item) =>
    ["critical", "high"].includes(item.priority)
  ).length;
  const needsHelpCount = recommendations.filter((item) => item.needsHelp).length;

  const hasUsefulScan = Boolean(
    scanRecord &&
      (recommendations.length > 0 || pages.length > 0 || healthScore > 0)
  );

  const cmsLabel =
    CMS_OPTIONS.find((item) => item.value === selectedCms)?.label ||
    "Custom / Not sure";

  const summary =
    scanRecord?.customer_summary ||
    scanRecord?.simple_summary ||
    scanRecord?.scan_summary?.plain_english_summary ||
    scanRecord?.site_summary?.plain_english_summary ||
    "";

  const topActions = getTopActions(scanRecord, recommendations);

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          hasUsefulScan={hasUsefulScan}
          onScan={() => navigate("/onboarding")}
        />

        <MetricsGrid
          healthScore={healthScore}
          recommendationsCount={recommendations.length}
          highPriorityCount={highPriorityCount}
          pagesScanned={getPagesScanned(scanRecord, pages)}
          createdAt={scanRecord?.created_at}
          needsHelpCount={needsHelpCount}
          hasUsefulScan={hasUsefulScan}
        />

        <ScanDebugPanel
          debugData={debugData}
          onRefresh={reloadScan}
          onClear={() => {
            clearAllScanData();
            reloadScan();
          }}
        />

        {hasUsefulScan ? (
          <>
            <AiActionPlan
              summary={summary}
              topActions={topActions}
              cmsLabel={cmsLabel}
              healthScore={healthScore}
              pagesScanned={getPagesScanned(scanRecord, pages)}
              recommendationsCount={recommendations.length}
              scanRecord={scanRecord}
            />

            <CmsSelector
              selectedCms={selectedCms}
              onChange={setSelectedCms}
            />

            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-bold text-slate-950">
                    Recommendations
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Review the highest-impact items first. Each card includes
                    plain-English instructions and CMS-specific next steps.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {PRIORITY_FILTERS.map((filter) => (
                    <button
                      key={filter.value}
                      type="button"
                      onClick={() => setPriorityFilter(filter.value)}
                      className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                        priorityFilter === filter.value
                          ? "bg-slate-950 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"
                      }`}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 space-y-4">
                {filteredRecommendations.length > 0 ? (
                  filteredRecommendations.map((recommendation, index) => (
                    <RecommendationCard
                      key={`${recommendation.title}-${index}`}
                      recommendation={recommendation}
                      cms={selectedCms}
                    />
                  ))
                ) : (
                  <EmptyFilteredState />
                )}
              </div>
            </div>
          </>
        ) : (
          <NoScanState onScan={() => navigate("/onboarding")} />
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Header + metrics                                                            */
/* -------------------------------------------------------------------------- */

function PageHeader({ hasUsefulScan, onScan }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-blue-700">
          <LayoutDashboard className="h-4 w-4" />
          Website recommendations
        </div>

        <h1 className="mt-2 text-3xl font-bold text-slate-950">Fix List</h1>

        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          A prioritized list of what to review, prepare, or ask for help with.
        </p>
      </div>

      <Button type="button" onClick={onScan}>
        <Search className="mr-2 h-4 w-4" />
        {hasUsefulScan ? "Run new scan" : "Run a scan"}
      </Button>
    </div>
  );
}

function MetricsGrid({
  healthScore,
  recommendationsCount,
  highPriorityCount,
  pagesScanned,
  createdAt,
  needsHelpCount,
  hasUsefulScan,
}) {
  return (
    <div className="grid gap-4 md:grid-cols-4">
      <MetricCard
        label="Score"
        value={hasUsefulScan && healthScore > 0 ? healthScore : "—"}
        helper={hasUsefulScan ? scoreLabel(healthScore) : "Run a scan"}
        icon={CheckCircle2}
      />

      <MetricCard
        label="Recommendations"
        value={recommendationsCount}
        helper={`${highPriorityCount} high priority`}
        icon={ListChecks}
      />

      <MetricCard
        label="Pages scanned"
        value={pagesScanned}
        helper={createdAt ? formatDate(createdAt) : "No scan yet"}
        icon={FileText}
      />

      <MetricCard
        label="May need help"
        value={needsHelpCount}
        helper="Website setup or cleanup"
        icon={MonitorCog}
      />
    </div>
  );
}

function MetricCard({ label, value, helper, icon: Icon }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{value}</p>
        </div>

        <div className="rounded-2xl bg-slate-100 p-3 text-slate-700">
          <Icon className="h-5 w-5" />
        </div>
      </div>

      <p className="mt-3 text-sm text-slate-500">{helper}</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Debug panel                                                                 */
/* -------------------------------------------------------------------------- */

function ScanDebugPanel({ debugData, onRefresh, onClear }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const summary = useMemo(() => buildDebugSummary(debugData), [debugData]);

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(debugData, null, 2));
      setCopied(true);

      window.setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch (error) {
      console.warn("Could not copy scan debug data.", error);
    }
  }

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-950">
            <Bug className="h-5 w-5" />
            Scan debug
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Use this when the dashboard shows 0 pages, an old scan, or a blocked
            scan.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen((value) => !value)}
          >
            <Bug className="mr-2 h-4 w-4" />
            {open ? "Hide debug" : "Show debug"}
          </Button>

          <Button type="button" variant="outline" onClick={onRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>

          <Button type="button" variant="outline" onClick={copyJson}>
            <Copy className="mr-2 h-4 w-4" />
            {copied ? "Copied" : "Copy JSON"}
          </Button>

          <Button type="button" variant="outline" onClick={onClear}>
            <Trash2 className="mr-2 h-4 w-4" />
            Clear scans
          </Button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <DebugStat label="Status" value={summary.status || "None"} />
        <DebugStat label="Website" value={summary.websiteUrl || "None"} />
        <DebugStat label="Pages" value={summary.pages || "0"} />
        <DebugStat label="Readable" value={summary.readablePages || "0"} />
        <DebugStat label="Blocked" value={summary.blockedPages || "0"} />
        <DebugStat label="Max pages" value={summary.maxPages || "0"} />
        <DebugStat label="Score" value={summary.score || "None"} />
        <DebugStat label="Error" value={summary.error || "None"} />
      </div>

      {open ? (
        <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
          <pre className="max-h-[560px] overflow-auto p-4 text-xs leading-5 text-slate-100">
            {JSON.stringify(debugData, null, 2)}
          </pre>
        </div>
      ) : null}
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

/* -------------------------------------------------------------------------- */
/* AI plan + CMS selector                                                      */
/* -------------------------------------------------------------------------- */

function AiActionPlan({
  summary,
  topActions,
  cmsLabel,
  healthScore,
  pagesScanned,
  recommendationsCount,
  scanRecord,
}) {
  const scanFocus = getScanFocus(scanRecord);

  return (
    <div className="rounded-3xl border border-blue-100 bg-blue-50 p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl bg-white p-3 text-blue-700 shadow-sm">
          <Sparkles className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold text-slate-950">
            AI-guided plan
          </h2>

          <p className="mt-1 text-sm font-semibold text-blue-950">
            Best plan of action
          </p>

          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-700">
            {summary ||
              `Your website health score is ${
                healthScore || "not available"
              }. The scanner reviewed ${pagesScanned} pages and found ${recommendationsCount} recommendations.`}
          </p>

          {scanFocus ? (
            <div className="mt-4 rounded-2xl border border-blue-100 bg-white/70 p-4 text-sm text-slate-700">
              <p className="font-semibold text-slate-950">Scan focus</p>
              <p className="mt-1 leading-6">{scanFocus}</p>
            </div>
          ) : null}

          <div className="mt-5">
            <p className="text-sm font-semibold text-slate-950">
              Selected CMS
            </p>

            <p className="mt-1 text-sm text-slate-600">{cmsLabel}</p>
          </div>

          {topActions.length > 0 ? (
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              {topActions.slice(0, 3).map((action, index) => (
                <div
                  key={`${action.title || action.issue_title || index}`}
                  className="rounded-2xl border border-blue-100 bg-white p-4"
                >
                  <div className="text-sm font-bold text-blue-700">
                    {index + 1}
                  </div>

                  <p className="mt-2 text-sm font-bold text-slate-950">
                    {action.title ||
                      action.issue_title ||
                      action.recommendation ||
                      "Review this item"}
                  </p>

                  <p className="mt-2 text-sm leading-5 text-slate-600">
                    {action.plain_english_explanation ||
                      action.explanation ||
                      action.simple_next_step ||
                      action.recommendation ||
                      "Review the affected pages and make the recommended update."}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CmsSelector({ selectedCms, onChange }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-950">
        Choose your website builder
      </h2>

      <p className="mt-1 text-sm text-slate-500">
        Click the CMS your site uses to see fix instructions written for that
        platform.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {CMS_OPTIONS.map((cms) => (
          <button
            key={cms.value}
            type="button"
            onClick={() => onChange(cms.value)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              selectedCms === cms.value
                ? "bg-slate-950 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"
            }`}
          >
            {cms.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Recommendation cards                                                        */
/* -------------------------------------------------------------------------- */

function RecommendationCard({ recommendation, cms }) {
  const priorityStyles = getPriorityStyles(recommendation.priority);
  const affectedPages = recommendation.affectedPages.slice(0, 6);
  const extraCount = Math.max(0, recommendation.affectedPages.length - 6);
  const cmsSteps = getCmsSteps(cms, recommendation);

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${priorityStyles.badge}`}
            >
              {recommendation.priority}
            </span>

            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              {recommendation.customerCategory}
            </span>

            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                recommendation.needsHelp
                  ? "bg-orange-50 text-orange-700"
                  : "bg-emerald-50 text-emerald-700"
              }`}
            >
              {recommendation.needsHelp ? "may need help" : "can prepare"}
            </span>
          </div>

          <h3 className="mt-4 text-xl font-bold text-slate-950">
            {recommendation.title}
          </h3>

          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
            {recommendation.explanation}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2 rounded-2xl bg-slate-50 px-4 py-3 text-sm font-medium text-slate-600">
          {recommendation.needsHelp ? (
            <MonitorCog className="h-4 w-4" />
          ) : (
            <Wrench className="h-4 w-4" />
          )}
          {recommendation.needsHelp ? "Best for your web person" : "You can prepare this"}
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">Why this matters</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {recommendation.whyItMatters}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">General next steps</p>

          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
            {recommendation.generalSteps.map((step, index) => (
              <li key={`${step}-${index}`}>{step}</li>
            ))}
          </ol>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm font-bold text-slate-950">
          {CMS_OPTIONS.find((item) => item.value === cms)?.label ||
            "Custom / Not sure"}{" "}
          steps
        </p>

        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
          {cmsSteps.map((step, index) => (
            <li key={`${step}-${index}`}>{step}</li>
          ))}
        </ol>
      </div>

      {affectedPages.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">
            Example affected pages
          </p>

          <div className="mt-3 space-y-2">
            {affectedPages.map((page, index) => (
              <AffectedPage key={`${page}-${index}`} page={page} />
            ))}

            {extraCount > 0 ? (
              <p className="text-sm text-slate-500">
                Plus {extraCount} more affected pages.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function AffectedPage({ page }) {
  const label = formatPageLabel(page);

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-950">{label}</p>
        <p className="truncate text-xs text-slate-500">{formatPagePath(page)}</p>
      </div>

      {isFullUrl(page) ? (
        <a
          href={page}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-950"
          aria-label="Open page"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Empty states                                                                */
/* -------------------------------------------------------------------------- */

function NoScanState({ onScan }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-3xl bg-slate-100 text-slate-600">
        <AlertCircle className="h-6 w-6" />
      </div>

      <h2 className="mt-5 text-xl font-bold text-slate-950">
        No recommendations yet.
      </h2>

      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">
        Run a website scan first. Once the scan finishes, your Fix List,
        AI-guided action plan, and CMS instructions will appear here.
      </p>

      <Button type="button" onClick={onScan} className="mt-5">
        <Search className="mr-2 h-4 w-4" />
        Run website scan
      </Button>
    </div>
  );
}

function EmptyFilteredState() {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <p className="text-sm font-medium text-slate-950">
        No recommendations match this filter.
      </p>

      <p className="mt-1 text-sm text-slate-500">
        Choose another priority filter to see more items.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Local storage + debug                                                       */
/* -------------------------------------------------------------------------- */

function readBestScanRecord() {
  const candidates = [];

  const lastScan = safeParseLocalStorage(DASHBOARD_LAST_SCAN_KEY);
  const legacyLastScan = safeParseLocalStorage(LEGACY_LAST_SCAN_KEY);

  if (lastScan) candidates.push(lastScan);
  if (legacyLastScan) candidates.push(legacyLastScan);

  const history = safeParseLocalStorage(DASHBOARD_HISTORY_KEY);
  const legacyHistory = safeParseLocalStorage(LEGACY_HISTORY_KEY);

  if (Array.isArray(history)) candidates.push(...history);
  if (Array.isArray(legacyHistory)) candidates.push(...legacyHistory);

  const validCandidates = candidates
    .filter(Boolean)
    .map(normalizeStoredScanCandidate)
    .filter(isUsefulScanCandidate)
    .sort((a, b) => {
      const aTime = new Date(a.created_at || 0).getTime();
      const bTime = new Date(b.created_at || 0).getTime();

      return bTime - aTime;
    });

  return validCandidates[0] || null;
}

function readScanDebugData() {
  if (typeof window === "undefined") {
    return {
      raw: {},
      parsed: {},
    };
  }

  const raw = {};
  const parsed = {};

  STORAGE_KEYS.forEach((key) => {
    const value = window.localStorage.getItem(key);
    raw[key] = value;

    try {
      parsed[key] = value ? JSON.parse(value) : null;
    } catch {
      parsed[key] = value;
    }
  });

  return {
    read_at: new Date().toISOString(),
    raw,
    parsed,
  };
}

function clearAllScanData() {
  try {
    STORAGE_KEYS.forEach((key) => {
      window.localStorage.removeItem(key);
    });

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not clear scan data.", error);
  }
}

function safeParseLocalStorage(key) {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(key);

    if (!raw) return null;

    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function normalizeStoredScanCandidate(candidate) {
  if (!candidate || typeof candidate !== "object") return null;

  const pages = getPages(candidate);
  const recommendations = getRecommendations(candidate);
  const score = getHealthScore(candidate);

  return {
    ...candidate,
    pages,
    crawled_pages: pages,
    recommendations,
    fixes: recommendations,
    findings: recommendations,
    health_score: score,
    seo_score: score,
  };
}

function isUsefulScanCandidate(candidate) {
  if (!candidate) return false;

  const pages = getPages(candidate);
  const recommendations = getRecommendations(candidate);
  const score = getHealthScore(candidate);

  if (!candidate.website_url && !candidate.raw?.scanner?.website_url) {
    return false;
  }

  return pages.length > 0 || recommendations.length > 0 || score > 0;
}

function buildDebugSummary(debugData) {
  const parsed = debugData?.parsed || {};
  const scanDebug = parsed[SCAN_DEBUG_KEY] || {};
  const lastScan = parsed[DASHBOARD_LAST_SCAN_KEY] || parsed[LEGACY_LAST_SCAN_KEY] || {};

  const scanner =
    scanDebug?.scanner ||
    lastScan?.raw?.scanner ||
    lastScan?.raw_scanner ||
    {};

  return {
    status: scanDebug?.status || scanDebug?.stage || "unknown",
    websiteUrl:
      scanDebug?.website_url ||
      lastScan?.website_url ||
      parsed[ACTIVE_SCAN_URL_KEY] ||
      "",
    pages:
      scanner?.pages_crawled ||
      lastScan?.pages_crawled ||
      lastScan?.pages?.length ||
      lastScan?.crawled_pages?.length ||
      0,
    readablePages:
      scanner?.technical_audit_summary?.readable_pages_checked ||
      lastScan?.technical_audit_summary?.readable_pages_checked ||
      0,
    blockedPages:
      scanner?.technical_audit_summary?.scanner_blocked_pages ||
      lastScan?.technical_audit_summary?.scanner_blocked_pages ||
      0,
    maxPages:
      scanner?.max_pages_effective ||
      lastScan?.raw?.scanner?.max_pages_effective ||
      0,
    score:
      lastScan?.health_score ||
      lastScan?.seo_score ||
      scanner?.health_score ||
      scanner?.seo_score ||
      0,
    error:
      scanDebug?.error ||
      scanner?.error ||
      lastScan?.raw?.scanner?.error ||
      "",
  };
}

/* -------------------------------------------------------------------------- */
/* Data extraction                                                             */
/* -------------------------------------------------------------------------- */

function getRecommendations(record) {
  if (!record) return [];

  return firstArray([
    record.recommendations,
    record.fixes,
    record.findings,
    record.raw_fixes,
    record.grouped_findings,
    record.raw?.recommendations,
    record.raw?.fixes,
    record.raw?.findings,
    record.raw?.scanner?.raw_fixes,
    record.raw?.scanner?.grouped_findings,
    record.raw?.scanner?.recommendations,
    record.raw?.scanner?.fixes,
    record.raw?.ai_review?.cleaned_fixes,
    record.raw?.ai_review?.recommendations,
    record.raw?.ai_review?.fixes,
    record.raw?.ai_review?.findings,
  ]);
}

function getPages(record) {
  if (!record) return [];

  return firstArray([
    record.crawled_pages,
    record.pages,
    record.scanned_pages,
    record.crawl_pages,
    record.raw?.crawled_pages,
    record.raw?.pages,
    record.raw?.scanner?.crawled_pages,
    record.raw?.scanner?.pages,
    record.raw?.scanner?.scanned_pages,
  ]);
}

function getHealthScore(record) {
  if (!record) return 0;

  return getFirstNumber([
    record.health_score,
    record.seo_score,
    record.scan_summary?.health_score,
    record.website_health_report?.score,
    record.raw?.health_score,
    record.raw?.seo_score,
    record.raw?.scanner?.health_score,
    record.raw?.scanner?.seo_score,
    record.raw?.ai_review?.health_score,
    record.raw?.ai_review?.website_health_report?.score,
  ]);
}

function getPagesScanned(record, pages) {
  return getFirstNumber([
    record?.pages_crawled,
    record?.pages_scanned,
    record?.technical_audit_summary?.pages_checked,
    record?.raw?.scanner?.pages_crawled,
    pages?.length,
  ]);
}

function getTopActions(record, recommendations) {
  const explicit = firstArray([
    record?.top_recommended_actions,
    record?.recommended_actions,
    record?.raw?.ai_review?.top_recommended_actions,
    record?.raw?.ai_review?.recommended_actions,
  ]);

  if (explicit.length > 0) return explicit;

  return recommendations.slice(0, 3);
}

function getScanFocus(record) {
  const focus =
    record?.scan_summary?.scan_focus ||
    record?.site_summary?.scan_focus ||
    record?.raw?.scanner?.scan_summary?.scan_focus ||
    {};

  if (focus.explanation) return focus.explanation;

  const prefix =
    record?.crawl_scope?.start_path_prefix ||
    record?.raw?.scanner?.crawl_scope?.start_path_prefix ||
    "";

  if (prefix) {
    return `The scan focused on the ${prefix} section and ignored unrelated sections so the page limit stayed focused.`;
  }

  return "";
}

/* -------------------------------------------------------------------------- */
/* Recommendation normalization                                                */
/* -------------------------------------------------------------------------- */

function normalizeRecommendation(item) {
  const priority = normalizePriority(item?.priority);

  const affectedPages = firstArray([
    item?.affected_pages,
    item?.pages,
    item?.page_urls,
  ]);

  const fallbackPage = item?.page_url || item?.url || "";

  const title =
    item?.title ||
    item?.issue_title ||
    item?.name ||
    item?.category ||
    "Review this recommendation";

  const explanation =
    item?.plain_english_explanation ||
    item?.explanation ||
    item?.description ||
    item?.summary ||
    item?.recommendation ||
    "Review this item and update the affected page where needed.";

  const whyItMatters =
    item?.why_it_matters ||
    item?.impact ||
    "Fixing this can improve how visitors and search engines understand the page.";

  const recommendation =
    item?.simple_next_step ||
    item?.recommended_value ||
    item?.recommendation ||
    item?.suggested_fix ||
    item?.ai_recommendation ||
    "Review the affected page and make the recommended update.";

  const difficulty = String(item?.difficulty || "").toLowerCase();

  const needsHelp =
    item?.requires_developer === true ||
    difficulty.includes("developer") ||
    difficulty.includes("technical") ||
    ["canonical", "redirect", "performance", "scanner_blocked", "js_rendering"].includes(
      item?.category
    );

  return {
    original: item,
    title,
    priority,
    explanation,
    whyItMatters,
    recommendation,
    customerCategory:
      item?.customer_category ||
      friendlyCustomerCategory(item?.category) ||
      "Website improvement",
    affectedPages: unique([
      ...affectedPages.map(String),
      ...(fallbackPage ? [fallbackPage] : []),
    ]),
    needsHelp,
    generalSteps: buildGeneralSteps(item, recommendation, needsHelp),
  };
}

function buildGeneralSteps(item, recommendation, needsHelp) {
  const existing = firstArray([
    item?.general_steps,
    item?.next_steps,
    item?.steps,
    item?.action_steps,
  ]);

  if (existing.length > 0) return existing.map(String).slice(0, 5);

  if (needsHelp) {
    return [
      "Share this finding with your web person.",
      "Ask them to review the technical detail.",
      "Confirm the fix after it is updated.",
    ];
  }

  const category = String(item?.category || "").toLowerCase();

  if (category.includes("meta_title")) {
    return [
      "Review the affected page.",
      "Write one short, specific search title.",
      "Include the main service or page topic.",
    ];
  }

  if (category.includes("meta_description")) {
    return [
      "Review the affected page.",
      "Write one helpful search description.",
      "Explain what the visitor will find on the page.",
    ];
  }

  if (category.includes("thin_content")) {
    return [
      "Review the affected page.",
      "Add more useful service details.",
      "Add common questions, proof points, and a clear next step.",
    ];
  }

  return [
    "Review the affected page.",
    recommendation,
    "Publish the change and run another scan.",
  ];
}

function getCmsSteps(cms, recommendation) {
  const title = recommendation.title || "this issue";
  const category = String(recommendation.original?.category || "").toLowerCase();

  const common = {
    wordpress: [
      "In WordPress, open the affected Page or Post.",
      "Update the SEO title and meta description in Yoast, Rank Math, All in One SEO, or your SEO plugin.",
      "Improve headings, body content, internal links, and image alt text where relevant.",
      "After fixing the page, publish the change and run another scan.",
    ],
    squarespace: [
      "Open the affected page in Squarespace.",
      "Go to Page Settings and review the SEO title, SEO description, URL slug, headings, and image descriptions.",
      "Update the content, save, publish, and run another scan.",
    ],
    wix: [
      "Open the affected page in Wix.",
      "Use SEO Basics to update the title tag, meta description, URL slug, and index settings.",
      "Improve headings, copy, internal links, and image alt text, then publish.",
    ],
    shopify: [
      "Open the affected product, collection, blog post, or page in Shopify.",
      "Edit the search engine listing preview.",
      "Improve copy, headings, internal links, image alt text, and redirects where needed.",
      "Save, publish, and run another scan.",
    ],
    webflow: [
      "Open the affected page or CMS item in Webflow.",
      "Review SEO settings, Open Graph settings, headings, content, alt text, and internal links.",
      "Publish the site and run another scan.",
    ],
    framer: [
      "Open the affected page in Framer.",
      "Review page metadata, headings, content, images, and links.",
      "Publish and run another scan. Ask a developer for redirects or technical template changes.",
    ],
    godaddy: [
      "Open the affected page in GoDaddy Website Builder.",
      "Use the SEO or page settings area to update the title, description, headings, images, and navigation.",
      "Publish the change and run another scan.",
    ],
    joomla: [
      "In Joomla, open the related Article or Menu Item.",
      "Update the Browser Page Title, Meta Description, Alias, headings, article content, and image alt text.",
      "Check Global Configuration for SEF URLs and metadata settings.",
      "Use Joomla Redirects or an SEO extension for redirects, canonicals, schema, or technical cleanup.",
    ],
    custom: [
      "Open the affected page in your website editor.",
      "Update the visible content, title, description, headings, images, or links if your editor allows it.",
      "Send technical items such as redirects, schema, canonicals, JavaScript rendering, or performance to a developer.",
      "Publish the update and run another scan.",
    ],
  };

  if (category.includes("404") || title.toLowerCase().includes("broken")) {
    return {
      ...common,
      wordpress: [
        "In WordPress, go to Pages or Posts and search for the affected URL slug.",
        "If the page should exist, restore it or update its permalink.",
        "If the page is old, create a 301 redirect using a redirect plugin or your SEO plugin.",
        "After fixing or redirecting the page, publish the change and run another scan.",
      ],
      joomla: [
        "In Joomla, check whether the related Article, Category, or Menu Item still exists.",
        "If the page should exist, restore it or correct the menu alias.",
        "If the page moved, add a redirect in Joomla Redirects or your SEO extension.",
        "Clear cache and run another scan.",
      ],
    }[cms] || common.custom;
  }

  return common[cms] || common.custom;
}

/* -------------------------------------------------------------------------- */
/* Formatting                                                                  */
/* -------------------------------------------------------------------------- */

function normalizePriority(priority) {
  const value = String(priority || "").toLowerCase();

  if (["critical", "high", "medium", "low"].includes(value)) return value;

  return "medium";
}

function getPriorityStyles(priority) {
  const styles = {
    critical: {
      badge: "bg-red-100 text-red-700",
    },
    high: {
      badge: "bg-orange-100 text-orange-700",
    },
    medium: {
      badge: "bg-yellow-100 text-yellow-700",
    },
    low: {
      badge: "bg-slate-100 text-slate-600",
    },
  };

  return styles[priority] || styles.medium;
}

function friendlyCustomerCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Website setup",
    schema: "Trust signals",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken page",
    redirect: "Page redirect",
    internal_link: "Internal links",
    performance: "Website performance",
    web_dev: "Website setup",
    scanner_blocked: "Scan coverage",
    js_rendering: "Website setup",
  };

  return map[category] || "Website improvement";
}

function scoreLabel(score) {
  const value = Number(score || 0);

  if (value >= 85) return "Strong";
  if (value >= 70) return "Good start";
  if (value >= 50) return "Needs attention";
  if (value > 0) return "Needs help";

  return "Run a scan";
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "Recent";
  }
}

function formatPageLabel(value) {
  try {
    const parsed = new URL(value);
    const parts = parsed.pathname.split("/").filter(Boolean);

    if (parts.length === 0) return "Homepage";

    return parts
      .slice(-3)
      .join(" / ")
      .replace(/[-_]/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  } catch {
    const cleaned = String(value || "").replace(/^https?:\/\/[^/]+/i, "");

    if (!cleaned || cleaned === "/") return "Homepage";

    return cleaned
      .split("/")
      .filter(Boolean)
      .slice(-3)
      .join(" / ")
      .replace(/[-_]/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
}

function formatPagePath(value) {
  try {
    const parsed = new URL(value);
    return parsed.pathname || "/";
  } catch {
    return String(value || "");
  }
}

function isFullUrl(value) {
  return /^https?:\/\//i.test(String(value || ""));
}

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

function normalizeCmsValue(value) {
  const normalized = String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "_");

  const validValues = CMS_OPTIONS.map((item) => item.value);

  return validValues.includes(normalized) ? normalized : "custom";
}

function firstArray(values) {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }

  return [];
}

function getFirstNumber(values) {
  for (const value of values) {
    const number = Number(value);

    if (Number.isFinite(number) && number > 0) {
      return Math.round(number);
    }
  }

  return 0;
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

function priorityWeight(priority) {
  const map = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };

  return map[String(priority || "medium")] || 2;
}