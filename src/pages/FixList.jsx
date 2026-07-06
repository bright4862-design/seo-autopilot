import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  Bug,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  ListChecks,
  MonitorCog,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  BUCKETS,
  BUCKET_ORDER,
  getCategoryLabel,
  getFirstStep,
  getIssueBucket,
  getScoreBand,
} from "@/lib/friendlyLabels";

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

const BAND_STYLES = {
  green: "bg-emerald-50 text-emerald-700",
  blue: "bg-blue-50 text-blue-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-rose-50 text-rose-700",
};

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
  const pagesScanned = getPagesScanned(scanRecord, pages);

  const counts = useMemo(() => {
    return recommendations.reduce(
      (acc, item) => {
        acc[item.bucket] += 1;
        return acc;
      },
      { needs_approval: 0, auto_fixed: 0, needs_developer: 0 }
    );
  }, [recommendations]);

  const categoryCounts = useMemo(() => {
    const map = new Map();

    recommendations.forEach((item) => {
      const key = item.category || "other";
      map.set(key, Number(map.get(key) || 0) + 1);
    });

    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [recommendations]);

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
    <div className="min-h-screen bg-[#F7F8FA] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          hasUsefulScan={hasUsefulScan}
          onScan={() => navigate("/onboarding")}
        />

        {hasUsefulScan ? (
          <>
            <NextStepCard counts={counts} onReview={() => scrollToRecommendations()} />

            <div className="grid gap-6 xl:grid-cols-3">
              <WebsiteHealthCard
                healthScore={healthScore}
                pagesScanned={pagesScanned}
                createdAt={scanRecord?.created_at}
              />

              <BucketOverview counts={counts} />
            </div>

            <PlainEnglishFindings categoryCounts={categoryCounts} />

            <ScanDebugPanel
              debugData={debugData}
              onRefresh={reloadScan}
              onClear={() => {
                clearAllScanData();
                reloadScan();
              }}
            />

            <AiActionPlan
              summary={summary}
              topActions={topActions}
              cmsLabel={cmsLabel}
              healthScore={healthScore}
              pagesScanned={pagesScanned}
              recommendationsCount={recommendations.length}
              scanRecord={scanRecord}
            />

            <CmsSelector selectedCms={selectedCms} onChange={setSelectedCms} />

            <div
              id="recommendations"
              className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-bold text-slate-950">
                    Recommendations
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Start with the quickest decisions first. Every card explains what it means, why it matters, and what to do next.
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
          <>
            <NoScanState onScan={() => navigate("/onboarding")} />
            <ScanDebugPanel
              debugData={debugData}
              onRefresh={reloadScan}
              onClear={() => {
                clearAllScanData();
                reloadScan();
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}

function scrollToRecommendations() {
  const element = document.getElementById("recommendations");
  if (element) element.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* -------------------------------------------------------------------------- */
/* Header + plain-English dashboard                                            */
/* -------------------------------------------------------------------------- */

function PageHeader({ hasUsefulScan, onScan }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-blue-700">
          <ListChecks className="h-4 w-4" />
          Website recommendations
        </div>

        <h1 className="mt-2 text-3xl font-bold text-slate-950">Fix List</h1>

        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Plain-English improvements grouped by what needs your attention, what is prepared, and what may need help.
        </p>
      </div>

      <Button type="button" onClick={onScan} variant={hasUsefulScan ? "outline" : "default"}>
        <Search className="mr-2 h-4 w-4" />
        {hasUsefulScan ? "Scan Website again" : "Scan Website"}
      </Button>
    </div>
  );
}

function NextStepCard({ counts, onReview }) {
  const firstStep = getFirstStep(counts);
  const activeBucket = BUCKET_ORDER.find((key) => Number(counts[key] || 0) > 0);
  const bucket = activeBucket ? BUCKETS[activeBucket] : null;

  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm sm:p-7">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-600">Your next step</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            {firstStep}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {bucket
              ? bucket.subtitle
              : "Run a fresh scan any time to check for new opportunities."}
          </p>
        </div>

        <Button
          type="button"
          onClick={onReview}
          className="shrink-0 rounded-full bg-blue-600 px-6 text-sm font-medium text-white shadow-none hover:bg-blue-700"
        >
          {bucket?.cta || "Review recommendations"}
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </section>
  );
}

function WebsiteHealthCard({ healthScore, pagesScanned, createdAt }) {
  const hasScore = Number(healthScore || 0) > 0;
  const band = hasScore ? getScoreBand(Number(healthScore)) : null;

  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold text-slate-950">Website health</h2>

      {hasScore ? (
        <div className="mt-4 space-y-4">
          <div>
            <div className="text-5xl font-bold tracking-tight text-slate-950">
              {healthScore}
            </div>
            {band ? (
              <span className={`mt-3 inline-flex rounded-full px-3 py-1 text-xs font-medium ${BAND_STYLES[band.tone]}`}>
                {band.label}
              </span>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <MiniStat label="Pages checked" value={pagesScanned} icon={FileText} />
            <MiniStat label="Last scan" value={createdAt ? formatDate(createdAt) : "Recent"} icon={CheckCircle2} />
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Run your first scan to get your score.
        </p>
      )}
    </section>
  );
}

function MiniStat({ label, value, icon: Icon }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-2 text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function BucketOverview({ counts }) {
  return (
    <div className="flex flex-col gap-4 xl:col-span-2">
      {BUCKET_ORDER.map((key) => {
        const bucket = BUCKETS[key];
        const count = Number(counts[key] || 0);

        return (
          <div
            key={key}
            className="group flex items-center justify-between gap-4 rounded-3xl border border-slate-200/80 bg-white px-6 py-5 shadow-sm"
          >
            <div>
              <p className="text-base font-semibold text-slate-950">
                {bucket.title}
              </p>
              <p className="mt-1 text-sm text-slate-500">
                {count > 0 ? bucket.subtitle : bucket.empty}
              </p>
            </div>
            <span className="text-2xl font-semibold text-slate-950">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

function PlainEnglishFindings({ categoryCounts }) {
  if (categoryCounts.length === 0) return null;

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <h2 className="text-base font-semibold text-slate-950">
          What we found, in plain English
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          No jargon — just what each recommendation means for the business.
        </p>
      </div>
      <div className="divide-y divide-slate-100">
        {categoryCounts.slice(0, 8).map(([category, count]) => {
          const label = getCategoryLabel(category);
          return (
            <div
              key={category}
              className="flex items-start justify-between gap-4 px-5 py-4 sm:px-6"
            >
              <div>
                <p className="text-sm font-medium text-slate-950">
                  {label.title}
                </p>
                {label.why ? (
                  <p className="mt-1 text-sm text-slate-500">{label.why}</p>
                ) : null}
              </div>
              <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </section>
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
      window.setTimeout(() => setCopied(false), 1500);
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
            Use this when the dashboard shows 0 pages, an old scan, or a blocked scan.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => setOpen((value) => !value)}>
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
          <h2 className="text-lg font-bold text-slate-950">Plain-English plan</h2>
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
            <p className="text-sm font-semibold text-slate-950">Selected CMS</p>
            <p className="mt-1 text-sm text-slate-600">{cmsLabel}</p>
          </div>

          {topActions.length > 0 ? (
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              {topActions.slice(0, 3).map((action, index) => (
                <div key={`${action.title || action.issue_title || index}`} className="rounded-2xl border border-blue-100 bg-white p-4">
                  <div className="text-sm font-bold text-blue-700">{index + 1}</div>
                  <p className="mt-2 text-sm font-bold text-slate-950">
                    {action.title || action.issue_title || action.recommendation || "Review this item"}
                  </p>
                  <p className="mt-2 text-sm leading-5 text-slate-600">
                    {action.plain_english_explanation || action.explanation || action.simple_next_step || action.recommendation || "Review the affected pages and make the recommended update."}
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
      <h2 className="text-lg font-bold text-slate-950">Choose your website builder</h2>
      <p className="mt-1 text-sm text-slate-500">
        Click the CMS your site uses to see instructions written for that platform.
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
  const bucket = BUCKETS[recommendation.bucket];

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${priorityStyles.badge}`}>
              {getPriorityLabel(recommendation.priority)}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              {recommendation.customerCategory}
            </span>
            <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              {bucket?.title || "Your turn"}
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
          {recommendation.needsHelp ? <MonitorCog className="h-4 w-4" /> : <Wrench className="h-4 w-4" />}
          {recommendation.needsHelp ? "Best for your web person" : "Quick review"}
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
          <p className="text-sm font-bold text-slate-950">What to do next</p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
            {recommendation.generalSteps.map((step, index) => (
              <li key={`${step}-${index}`}>{step}</li>
            ))}
          </ol>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm font-bold text-slate-950">
          {CMS_OPTIONS.find((item) => item.value === cms)?.label || "Custom / Not sure"} steps
        </p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
          {cmsSteps.map((step, index) => (
            <li key={`${step}-${index}`}>{step}</li>
          ))}
        </ol>
      </div>

      {affectedPages.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">Example affected pages</p>
          <div className="mt-3 space-y-2">
            {affectedPages.map((page, index) => (
              <AffectedPage key={`${page}-${index}`} page={page} />
            ))}
            {extraCount > 0 ? (
              <p className="text-sm text-slate-500">Plus {extraCount} more affected pages.</p>
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
        <a href={page} target="_blank" rel="noreferrer" className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-950" aria-label="Open page">
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
      <h2 className="mt-5 text-xl font-bold text-slate-950">No recommendations yet.</h2>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">
        Run a website scan first. Once the scan finishes, your Fix List, plain-English action plan, and CMS instructions will appear here.
      </p>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
        Run your first scan to get your score.
      </p>
      <Button type="button" onClick={onScan} className="mt-5">
        <Search className="mr-2 h-4 w-4" />
        Scan Website
      </Button>
    </div>
  );
}

function EmptyFilteredState() {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <p className="text-sm font-medium text-slate-950">No recommendations match this filter.</p>
      <p className="mt-1 text-sm text-slate-500">Choose another priority filter to see more items.</p>
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
    .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());

  return validCandidates[0] || null;
}

function readScanDebugData() {
  if (typeof window === "undefined") return { raw: {}, parsed: {} };

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

  return { read_at: new Date().toISOString(), raw, parsed };
}

function clearAllScanData() {
  try {
    STORAGE_KEYS.forEach((key) => window.localStorage.removeItem(key));
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not clear scan data.", error);
  }
}

function safeParseLocalStorage(key) {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
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
  if (!candidate.website_url && !candidate.raw?.scanner?.website_url) return false;
  return pages.length > 0 || recommendations.length > 0 || score > 0;
}

function buildDebugSummary(debugData) {
  const parsed = debugData?.parsed || {};
  const scanDebug = parsed[SCAN_DEBUG_KEY] || {};
  const lastScan = parsed[DASHBOARD_LAST_SCAN_KEY] || parsed[LEGACY_LAST_SCAN_KEY] || {};
  const scanner = scanDebug?.scanner || lastScan?.raw?.scanner || lastScan?.raw_scanner || {};

  return {
    status: scanDebug?.status || scanDebug?.stage || "unknown",
    websiteUrl: scanDebug?.website_url || lastScan?.website_url || parsed[ACTIVE_SCAN_URL_KEY] || "",
    pages: scanner?.pages_crawled || lastScan?.pages_crawled || lastScan?.pages?.length || lastScan?.crawled_pages?.length || 0,
    readablePages: scanner?.technical_audit_summary?.readable_pages_checked || lastScan?.technical_audit_summary?.readable_pages_checked || 0,
    blockedPages: scanner?.technical_audit_summary?.scanner_blocked_pages || lastScan?.technical_audit_summary?.scanner_blocked_pages || 0,
    maxPages: scanner?.max_pages_effective || lastScan?.raw?.scanner?.max_pages_effective || 0,
    score: lastScan?.health_score || lastScan?.seo_score || scanner?.health_score || scanner?.seo_score || 0,
    error: scanDebug?.error || scanner?.error || lastScan?.raw?.scanner?.error || "",
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
  return explicit.length > 0 ? explicit : recommendations.slice(0, 3);
}

function getScanFocus(record) {
  const focus = record?.scan_summary?.scan_focus || record?.site_summary?.scan_focus || record?.raw?.scanner?.scan_summary?.scan_focus || {};
  if (focus.explanation) return focus.explanation;
  const prefix = record?.crawl_scope?.start_path_prefix || record?.raw?.scanner?.crawl_scope?.start_path_prefix || "";
  if (prefix) return `The scan focused on the ${prefix} section and ignored unrelated sections so the page limit stayed focused.`;
  return "";
}

/* -------------------------------------------------------------------------- */
/* Recommendation normalization                                                */
/* -------------------------------------------------------------------------- */

function normalizeRecommendation(item) {
  const priority = normalizePriority(item?.priority);
  const category = String(item?.category || "other").toLowerCase();
  const categoryLabel = getCategoryLabel(category);
  const bucket = getIssueBucket(item || {});

  const affectedPages = firstArray([item?.affected_pages, item?.pages, item?.page_urls]);
  const fallbackPage = item?.page_url || item?.url || "";

  const sourceTitle = item?.title || item?.issue_title || item?.name || "";
  const title = categoryLabel.title || sourceTitle || "Review this recommendation";

  const explanation =
    item?.plain_english_explanation ||
    categoryLabel.why ||
    item?.explanation ||
    item?.description ||
    item?.summary ||
    item?.recommendation ||
    "Review this item and update the affected page where needed.";

  const whyItMatters =
    categoryLabel.why ||
    item?.why_it_matters ||
    item?.impact ||
    "Fixing this can improve how visitors and search engines understand the page.";

  const recommendation =
    item?.simple_next_step ||
    categoryLabel.what ||
    item?.recommended_value ||
    item?.recommendation ||
    item?.suggested_fix ||
    item?.ai_recommendation ||
    "Review the affected page and make the recommended update.";

  const needsHelp = bucket === "needs_developer";

  return {
    original: item,
    category,
    title,
    priority,
    bucket,
    explanation,
    whyItMatters,
    recommendation,
    customerCategory: categoryLabel.title || "Website improvement",
    affectedPages: unique([
      ...affectedPages.map(String),
      ...(fallbackPage ? [fallbackPage] : []),
    ]),
    needsHelp,
    generalSteps: buildGeneralSteps(item, recommendation, needsHelp),
  };
}

function buildGeneralSteps(item, recommendation, needsHelp) {
  const existing = firstArray([item?.general_steps, item?.next_steps, item?.steps, item?.action_steps]);
  if (existing.length > 0) return existing.map(String).slice(0, 5);

  if (needsHelp) {
    return [
      "Share this recommendation with your web person.",
      "Ask them to review the technical detail.",
      "Run another scan after the update is published.",
    ];
  }

  const category = String(item?.category || "").toLowerCase();
  if (category.includes("meta_title")) {
    return ["Review the affected page.", "Write one short, specific Google result title.", "Include the main service or page topic."];
  }
  if (category.includes("meta_description")) {
    return ["Review the affected page.", "Write one helpful Google result description.", "Explain what the visitor will find on the page."];
  }
  if (category.includes("thin_content")) {
    return ["Review the affected page.", "Add more useful service details.", "Add common questions, proof points, and a clear next step."];
  }

  return ["Review the affected page.", recommendation, "Publish the change and run another scan."];
}

function getCmsSteps(cms, recommendation) {
  const category = String(recommendation.original?.category || "").toLowerCase();
  const common = {
    wordpress: [
      "In WordPress, open the affected Page or Post.",
      "Update the visible content, Google result title, Google result description, headings, links, and image descriptions where relevant.",
      "After fixing the page, publish the change and run another scan.",
    ],
    squarespace: [
      "Open the affected page in Squarespace.",
      "Review page settings, Google result title, Google result description, URL slug, headings, and image descriptions.",
      "Update the content, save, publish, and run another scan.",
    ],
    wix: [
      "Open the affected page in Wix.",
      "Use SEO Basics to update the Google result title, description, URL slug, and visibility settings.",
      "Improve headings, copy, internal links, and image descriptions, then publish.",
    ],
    shopify: [
      "Open the affected product, collection, blog post, or page in Shopify.",
      "Edit the search engine listing preview.",
      "Improve copy, headings, internal links, image descriptions, and page forwarding where needed.",
      "Save, publish, and run another scan.",
    ],
    webflow: [
      "Open the affected page or CMS item in Webflow.",
      "Review page settings, social sharing fields, headings, content, image descriptions, and internal links.",
      "Publish the site and run another scan.",
    ],
    framer: [
      "Open the affected page in Framer.",
      "Review page settings, headings, content, images, and links.",
      "Publish and run another scan. Ask a developer for page forwarding or technical template changes.",
    ],
    godaddy: [
      "Open the affected page in GoDaddy Website Builder.",
      "Use the page settings area to update the title, description, headings, images, and navigation.",
      "Publish the change and run another scan.",
    ],
    joomla: [
      "In Joomla, open the related Article or Menu Item.",
      "Update the Browser Page Title, Google result description, Alias, headings, article content, and image descriptions.",
      "Check Global Configuration for search-friendly URL and site details.",
      "Use Joomla Redirects or an SEO extension for page forwarding, duplicate page settings, business details for Google, or technical cleanup.",
    ],
    custom: [
      "Open the affected page in your website editor.",
      "Update the visible content, title, description, headings, images, or links if your editor allows it.",
      "Send technical items such as page forwarding, duplicate page settings, business details for Google, JavaScript rendering, or performance to a developer.",
      "Publish the update and run another scan.",
    ],
  };

  if (category.includes("404")) {
    return {
      ...common,
      wordpress: [
        "In WordPress, go to Pages or Posts and search for the affected URL slug.",
        "If the page should exist, restore it or update its permalink.",
        "If the page is old, create a page forwarding rule using a redirect plugin or your SEO plugin.",
        "After fixing or forwarding the page, publish the change and run another scan.",
      ],
      joomla: [
        "In Joomla, check whether the related Article, Category, or Menu Item still exists.",
        "If the page should exist, restore it or correct the menu alias.",
        "If the page moved, add page forwarding in Joomla Redirects or your SEO extension.",
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
    critical: { badge: "bg-red-100 text-red-700" },
    high: { badge: "bg-orange-100 text-orange-700" },
    medium: { badge: "bg-yellow-100 text-yellow-700" },
    low: { badge: "bg-slate-100 text-slate-600" },
  };
  return styles[priority] || styles.medium;
}

function getPriorityLabel(priority) {
  if (priority === "critical" || priority === "high") return "High impact";
  if (priority === "medium") return "Medium impact";
  return "Lower impact";
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return "Recent";
  }
}

function formatPageLabel(value) {
  try {
    const parsed = new URL(value);
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length === 0) return "Homepage";
    return parts.slice(-3).join(" / ").replace(/[-_]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  } catch {
    const cleaned = String(value || "").replace(/^https?:\/\/[^/]+/i, "");
    if (!cleaned || cleaned === "/") return "Homepage";
    return cleaned.split("/").filter(Boolean).slice(-3).join(" / ").replace(/[-_]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
  const normalized = String(value || "").toLowerCase().replace(/\s+/g, "_");
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
    if (Number.isFinite(number) && number > 0) return Math.round(number);
  }
  return 0;
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)));
}
