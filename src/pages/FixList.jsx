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

const CATEGORY_LABELS = {
  "404_error": "Broken page",
  broken_page: "Broken page",
  blocked_page: "Scan coverage",
  blocked_page_429: "Scan coverage",
  scanner_blocked: "Scan coverage",
  meta_title: "Search title",
  meta_description: "Search description",
  duplicate_content: "Duplicate search text",
  canonical: "Canonical / duplicate page setting",
  schema: "Trust signals",
  thin_content: "Page content",
  web_dev: "Website setup",
  image_alt_text: "Images",
  alt_text: "Images",
  internal_link: "Internal links",
  performance: "Performance",
  performance_hint: "Performance",
  js_rendering: "JavaScript rendering",
  indexability: "Indexability",
  social_metadata: "Social sharing",
};

const BUCKETS = {
  needs_approval: {
    title: "Your turn",
    subtitle: "Quick decisions you or your team can review.",
    cta: "Review now",
  },
  auto_fixed: {
    title: "Prepared for you",
    subtitle: "Suggested improvements prepared for review.",
    cta: "See prepared fixes",
  },
  needs_developer: {
    title: "Get help",
    subtitle: "Technical fixes to send to your web person.",
    cta: "See technical tasks",
  },
};

const BUCKET_ORDER = ["needs_approval", "auto_fixed", "needs_developer"];
const ENERGY_PATH_HINTS = ["energie", "énergie", "electricite", "électricité", "gaz", "fournisseur", "kwh", "tarif"];
const CREDIT_PATH_HINTS = ["rachat-de-credits", "rachat-de-credit", "credit", "crédit", "credits", "crédits", "pret", "prêt", "emprunt"];

export default function FixList() {
  const navigate = useNavigate();
  const [scanRecord, setScanRecord] = useState(() => readBestScanRecord());
  const [debugData, setDebugData] = useState(() => readScanDebugData());
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [selectedCms, setSelectedCms] = useState(() => normalizeCmsValue(scanRecord?.cms_platform || "custom"));

  function reloadScan() {
    const next = readBestScanRecord();
    setScanRecord(next);
    setDebugData(readScanDebugData());
    if (next?.cms_platform) setSelectedCms(normalizeCmsValue(next.cms_platform));
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

  const recommendations = useMemo(() => getRecommendations(scanRecord).map((item) => normalizeRecommendation(item, scanRecord)), [scanRecord]);
  const filteredRecommendations = useMemo(() => {
    if (priorityFilter === "all") return recommendations;
    return recommendations.filter((item) => item.priority === priorityFilter);
  }, [priorityFilter, recommendations]);

  const pages = useMemo(() => getPages(scanRecord), [scanRecord]);
  const healthScore = getHealthScore(scanRecord);
  const pagesScanned = getPagesScanned(scanRecord, pages);
  const hasUsefulScan = Boolean(scanRecord && (recommendations.length > 0 || pages.length > 0 || healthScore > 0));
  const cmsLabel = CMS_OPTIONS.find((cms) => cms.value === selectedCms)?.label || "Custom / Not sure";
  const topActions = getTopActions(scanRecord, recommendations);
  const counts = countBuckets(recommendations);
  const summary = getBestSummary(scanRecord, healthScore, pagesScanned, recommendations.length);

  return (
    <div className="min-h-screen bg-[#F7F8FA] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader hasUsefulScan={hasUsefulScan} onScan={() => navigate("/onboarding")} />

        {hasUsefulScan ? (
          <>
            <NextStepCard counts={counts} onReview={() => scrollToRecommendations()} />

            <div className="grid gap-6 xl:grid-cols-3">
              <WebsiteHealthCard healthScore={healthScore} pagesScanned={pagesScanned} createdAt={scanRecord?.created_at} />
              <BucketOverview counts={counts} />
            </div>

            <AiActionPlan summary={summary} topActions={topActions} cmsLabel={cmsLabel} />

            <ScanDebugPanel debugData={debugData} onRefresh={reloadScan} onClear={() => { clearAllScanData(); reloadScan(); }} />

            <CmsSelector selectedCms={selectedCms} onChange={setSelectedCms} />

            <section id="recommendations" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-bold text-slate-950">Your FixList</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Each card uses scan evidence first: affected page, current value, business importance, route scope, and AI steps.
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
                    <RecommendationCard key={`${recommendation.id}-${index}`} recommendation={recommendation} cms={selectedCms} />
                  ))
                ) : (
                  <EmptyFilteredState />
                )}
              </div>
            </section>
          </>
        ) : (
          <>
            <NoScanState onScan={() => navigate("/onboarding")} />
            <ScanDebugPanel debugData={debugData} onRefresh={reloadScan} onClear={() => { clearAllScanData(); reloadScan(); }} />
          </>
        )}
      </div>
    </div>
  );
}

function PageHeader({ hasUsefulScan, onScan }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-indigo-700">
          <ListChecks className="h-4 w-4" />
          Plain-English SEO fixes
        </div>
        <h1 className="mt-2 text-3xl font-bold text-slate-950">FixList</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Prioritized recommendations based on page type, business value, route scope, and what the scanner actually found.
        </p>
      </div>
      <Button type="button" onClick={onScan} variant={hasUsefulScan ? "outline" : "default"}>
        <Search className="mr-2 h-4 w-4" />
        {hasUsefulScan ? "Run new scan" : "Run my scan"}
      </Button>
    </div>
  );
}

function NextStepCard({ counts, onReview }) {
  const activeBucket = BUCKET_ORDER.find((key) => Number(counts[key] || 0) > 0);
  const bucket = activeBucket ? BUCKETS[activeBucket] : null;
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm sm:p-7">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-indigo-600">Your next step</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            {bucket ? `Start with ${bucket.title}` : "Your scan has recommendations ready."}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {bucket?.subtitle || "Review the highest-impact items first."}
          </p>
        </div>
        <Button type="button" onClick={onReview} className="shrink-0 rounded-full bg-indigo-600 px-6 text-sm font-medium text-white shadow-none hover:bg-indigo-700">
          {bucket?.cta || "Review recommendations"}
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </section>
  );
}

function WebsiteHealthCard({ healthScore, pagesScanned, createdAt }) {
  const band = getScoreBand(healthScore);
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold text-slate-950">Website health</h2>
      <div className="mt-4 space-y-4">
        <div>
          <div className="text-5xl font-bold tracking-tight text-slate-950">{healthScore || "—"}</div>
          <span className={`mt-3 inline-flex rounded-full px-3 py-1 text-xs font-medium ${band.className}`}>{band.label}</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <MiniStat label="Pages checked" value={pagesScanned || 0} icon={FileText} />
          <MiniStat label="Last scan" value={createdAt ? formatDate(createdAt) : "Recent"} icon={CheckCircle2} />
        </div>
      </div>
    </section>
  );
}

function MiniStat({ label, value, icon: Icon }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        <Icon className="h-4 w-4" />
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
          <div key={key} className="flex items-center justify-between gap-4 rounded-3xl border border-slate-200/80 bg-white px-6 py-5 shadow-sm">
            <div>
              <p className="text-base font-semibold text-slate-950">{bucket.title}</p>
              <p className="mt-1 text-sm text-slate-500">{bucket.subtitle}</p>
            </div>
            <span className="text-2xl font-semibold text-slate-950">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

function AiActionPlan({ summary, topActions, cmsLabel }) {
  return (
    <section className="rounded-3xl border border-indigo-100 bg-indigo-50 p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl bg-white p-3 text-indigo-700 shadow-sm"><Sparkles className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold text-slate-950">Plain-English plan</h2>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-700">{summary}</p>
          <p className="mt-4 text-sm text-slate-600">Selected CMS: <span className="font-semibold text-slate-950">{cmsLabel}</span></p>
          {topActions.length > 0 ? (
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              {topActions.slice(0, 3).map((action, index) => (
                <div key={`${action.title || index}`} className="rounded-2xl border border-indigo-100 bg-white p-4">
                  <div className="text-sm font-bold text-indigo-700">{index + 1}</div>
                  <p className="mt-2 text-sm font-bold text-slate-950">{action.title || action.issue_title || "Review this item"}</p>
                  <p className="mt-2 text-sm leading-5 text-slate-600">{action.reason || action.why_it_matters || action.plain_english_summary || "Review the affected pages and make the recommended update."}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function CmsSelector({ selectedCms, onChange }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-950">Choose your website builder</h2>
      <p className="mt-1 text-sm text-slate-500">Switch the instruction style without rerunning the scan.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {CMS_OPTIONS.map((cms) => (
          <button key={cms.value} type="button" onClick={() => onChange(cms.value)} className={`rounded-full px-4 py-2 text-sm font-medium transition ${selectedCms === cms.value ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"}`}>
            {cms.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function RecommendationCard({ recommendation, cms }) {
  const priorityStyles = getPriorityStyles(recommendation.priority);
  const bucket = BUCKETS[recommendation.bucket] || BUCKETS.needs_approval;
  const affectedPages = recommendation.affectedPages.slice(0, 6);
  const extraCount = Math.max(0, recommendation.affectedPages.length - affectedPages.length);
  const cmsSteps = getCmsSteps(cms, recommendation);
  const evidenceItems = buildEvidenceItems(recommendation);

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${priorityStyles.badge}`}>{getPriorityLabel(recommendation.priority)}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">{recommendation.customerCategory}</span>
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">{bucket.title}</span>
            {recommendation.scopeRelationship ? <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">{humanize(recommendation.scopeRelationship)}</span> : null}
          </div>
          <h3 className="mt-4 text-xl font-bold text-slate-950">{recommendation.title}</h3>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">{recommendation.explanation}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2 rounded-2xl bg-slate-50 px-4 py-3 text-sm font-medium text-slate-600">
          {recommendation.needsHelp ? <MonitorCog className="h-4 w-4" /> : <Wrench className="h-4 w-4" />}
          {recommendation.needsHelp ? "Best for your web person" : "Quick review"}
        </div>
      </div>

      {evidenceItems.length > 0 ? (
        <div className="mt-5 rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4">
          <p className="text-sm font-bold text-slate-950">What FixList noticed</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {evidenceItems.map((item) => (
              <div key={item.label} className="rounded-xl bg-white px-3 py-2 text-sm">
                <span className="font-semibold text-slate-950">{item.label}: </span>
                <span className="text-slate-600">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">Why this matters</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{recommendation.whyItMatters}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">What to do next</p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
            {recommendation.generalSteps.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}
          </ol>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm font-bold text-slate-950">{CMS_OPTIONS.find((item) => item.value === cms)?.label || "Custom / Not sure"} steps</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-600">
          {cmsSteps.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}
        </ol>
      </div>

      {affectedPages.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-bold text-slate-950">Example affected pages</p>
          <div className="mt-3 space-y-2">
            {affectedPages.map((page, index) => <AffectedPage key={`${page}-${index}`} page={page} />)}
            {extraCount > 0 ? <p className="text-sm text-slate-500">Plus {extraCount} more affected pages.</p> : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function AffectedPage({ page }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-950">{formatPageLabel(page)}</p>
        <p className="truncate text-xs text-slate-500">{formatPagePath(page)}</p>
      </div>
      {isFullUrl(page) ? (
        <a href={page} target="_blank" rel="noreferrer" className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-950" aria-label="Open page"><ExternalLink className="h-4 w-4" /></a>
      ) : null}
    </div>
  );
}

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
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-950"><Bug className="h-5 w-5" /> Scan debug</h2>
          <p className="mt-1 text-sm text-slate-500">Use this to confirm the scan saved and which logic ran.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => setOpen((value) => !value)}><Bug className="mr-2 h-4 w-4" />{open ? "Hide debug" : "Show debug"}</Button>
          <Button type="button" variant="outline" onClick={onRefresh}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
          <Button type="button" variant="outline" onClick={copyJson}><Copy className="mr-2 h-4 w-4" />{copied ? "Copied" : "Copy JSON"}</Button>
          <Button type="button" variant="outline" onClick={onClear}><Trash2 className="mr-2 h-4 w-4" />Clear scans</Button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <DebugStat label="Status" value={summary.status || "None"} />
        <DebugStat label="Website" value={summary.websiteUrl || "None"} />
        <DebugStat label="Pages" value={summary.pages || "0"} />
        <DebugStat label="Score" value={summary.score || "None"} />
      </div>

      {open ? (
        <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
          <pre className="max-h-[560px] overflow-auto p-4 text-xs leading-5 text-slate-100">{JSON.stringify(debugData, null, 2)}</pre>
        </div>
      ) : null}
    </section>
  );
}

function DebugStat({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 break-words text-sm font-semibold text-slate-950">{String(value)}</div>
    </div>
  );
}

function NoScanState({ onScan }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-3xl bg-slate-100 text-slate-600"><AlertCircle className="h-6 w-6" /></div>
      <h2 className="mt-5 text-xl font-bold text-slate-950">No FixList yet.</h2>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">Run a website scan first. Once it finishes, your plain-English action plan will appear here.</p>
      <Button type="button" onClick={onScan} className="mt-5"><Search className="mr-2 h-4 w-4" />Run my scan</Button>
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

function normalizeRecommendation(item = {}, scanRecord = {}) {
  const evidence = extractRecommendationEvidence(item, scanRecord);
  const blocked429 = isBlocked429(item);
  const priority = blocked429 ? blockedPriority(item, evidence) : normalizePriority(item.priority);
  const category = String(item.category || "other").toLowerCase();
  const affectedPages = firstArray([item.affected_pages, item.pages, item.page_urls]);
  const fallbackPage = item.page_url || item.url || affectedPages[0] || "";
  const bucket = blocked429 ? "needs_developer" : getIssueBucket(item);
  const customerCategory = blocked429 ? "Scan coverage" : item.customer_category || CATEGORY_LABELS[category] || humanize(category || "Website improvement");
  const title = blocked429 ? build429Title(evidence) : cleanString(item.issue_title || item.title || item.name) || buildSpecificTitle(item);
  const explanation = blocked429 ? build429Explanation(evidence) : cleanString(item.plain_english_explanation || item.plain_english_summary || item.explanation || item.description || item.summary || item.recommendation) || buildSpecificExplanation(item);
  const whyItMatters = blocked429 ? build429Why(evidence) : cleanString(item.why_it_matters || item.impact || item.reason) || buildSpecificWhy(item);
  const recommendation = blocked429 ? build429Recommendation(evidence) : cleanString(item.simple_next_step || item.recommended_value || item.recommendation || item.suggested_fix || item.ai_recommendation) || "Review the affected page and make the recommended update.";
  const needsHelp = bucket === "needs_developer";

  return {
    id: item.id || item.fix_id || stableId(`${fallbackPage}|${category}|${title}`),
    original: item,
    category,
    priority,
    bucket,
    customerCategory,
    title,
    explanation,
    whyItMatters,
    recommendation,
    affectedPages: unique([...affectedPages.map(String), ...(fallbackPage ? [fallbackPage] : [])]),
    currentValue: blocked429 ? "HTTP 429 — crawler was rate-limited or blocked" : cleanString(item.current_value || item.current || item.detected_value),
    pageType: blocked429 && evidence.scopeRelationship === "sibling_sous_dossier" ? "Sibling sous-dossier" : cleanString(item.page_type || item.page_value_label || item.business_importance),
    defectClass: blocked429 ? "Rate-limit / crawler access" : cleanString(item.primary_defect_class || item.meta_regeneration_gate),
    pageValueLabel: blocked429 ? evidence.businessValueLabel : cleanString(item.page_value_label),
    businessImportance: blocked429 ? evidence.businessImportance : cleanString(item.business_importance),
    metaGate: cleanString(item.meta_regeneration_gate),
    scopeRelationship: evidence.scopeRelationship,
    needsHelp,
    generalSteps: blocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),
  };
}

function extractRecommendationEvidence(item = {}, scanRecord = {}) {
  const affectedPages = firstArray([item.affected_pages, item.pages, item.page_urls]);
  const pageUrl = item.page_url || item.url || affectedPages[0] || "";
  const allPages = unique([...affectedPages, ...(pageUrl ? [pageUrl] : [])].map(String));
  const scanUrl = scanRecord?.website_url || scanRecord?.raw?.scanner?.website_url || scanRecord?.debug?.website_url || "";
  const scopeRelationship = classifyScopeRelationship({ scanUrl, pageUrl, affectedPages: allPages });
  const path = firstPath(allPages);
  const statusCode = getFirstNumber([item.status_code, item.current_status_code, item.http_status, item.evidence?.status_code]);
  const sourcePages = firstArray([item.source_pages, item.evidence?.source_pages]);
  const affectedCount = allPages.length;
  const businessValueLabel = scopeRelationship === "sibling_sous_dossier"
    ? "Same parent brand, different business vertical"
    : isEnergyPath(path) || isImportantBusinessPath(path)
      ? "Potentially important path"
      : "Standard page";
  const businessImportance = scopeRelationship === "sibling_sous_dossier"
    ? "same_parent_sibling_sous_dossier"
    : isEnergyPath(path) || isImportantBusinessPath(path)
      ? "potentially_important"
      : "standard";
  return { affectedPages: allPages, scanUrl, pageUrl, path, statusCode, sourcePages, affectedCount, scopeRelationship, businessValueLabel, businessImportance };
}

function isBlocked429(item = {}) {
  const text = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.current_value || ""} ${item.fetch_error || ""} ${item.recommended_value || ""}`.toLowerCase();
  const status = getFirstNumber([item.status_code, item.current_status_code, item.http_status, item.evidence?.status_code]);
  return status === 429 || text.includes("429") || text.includes("rate limit") || text.includes("rate-limit") || text.includes("too many requests") || text.includes("bot protection");
}

function build429Title(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") return "Check Meilleurtaux rate limiting on sibling sous-dossiers";
  if (evidence.affectedCount > 1) return "Check pages blocked by rate limiting";
  return "Check this HTTP 429 scan block";
}

function build429Explanation(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "The scanner hit HTTP 429 on a Meilleurtaux parent-domain path that appears to be a sibling sous-dossier, such as credit or loan content, rather than the selected energy section. This usually means the broader Meilleurtaux server, CDN, firewall, or bot-protection layer rate-limited the crawler.";
  }
  return "The page returned HTTP 429 during the scan. That usually means the server, CDN, firewall, or bot-protection layer rate-limited the crawler. Verify whether normal users and legitimate search crawlers can load it before treating it as a confirmed broken customer page.";
}

function build429Why(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "This is useful parent-domain evidence, but it should not be described as a primary energy-comparison customer page unless the selected crawl scope or source-page evidence proves it belongs to that journey.";
  }
  return "Rate limiting can hide pages from crawlers if configured too aggressively. But a 429 is not the same as a confirmed broken page, so the next step is to verify crawler and user access rather than rewrite the page.";
}

function build429Recommendation(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "Ask your web person to review rate-limit and bot-protection rules for the Meilleurtaux parent domain and confirm whether this sibling sous-dossier should be part of the selected scan scope.";
  }
  return "Ask your web person to check server, CDN, firewall, and bot-protection logs for this URL and confirm whether Googlebot and normal users can access it.";
}

function build429Steps(evidence) {
  const base = [
    "Send the affected URL or URL group to your web person.",
    "Check server, CDN, firewall, and bot-protection logs for HTTP 429 responses.",
    "Confirm whether Googlebot and normal users can load the page without being rate-limited.",
  ];
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return [
      ...base,
      "Confirm whether this sibling sous-dossier should be included in the current scan scope or treated as parent-domain evidence only.",
      "Adjust rate-limit rules only if legitimate crawlers or users are being blocked.",
    ];
  }
  return [...base, "Adjust rate-limit rules if legitimate crawlers are blocked, then run FixList again."];
}

function blockedPriority(item, evidence) {
  const original = normalizePriority(item.priority);
  if (evidence.affectedCount >= 3) return original === "low" ? "medium" : original;
  if (evidence.scopeRelationship === "sibling_sous_dossier") return original === "critical" || original === "high" ? "medium" : original;
  if (evidence.businessImportance === "potentially_important") return original === "low" ? "medium" : original;
  return original === "critical" || original === "high" ? "medium" : original;
}

function classifyScopeRelationship({ scanUrl, pageUrl, affectedPages }) {
  const scanHost = safeHostname(scanUrl);
  const pageHost = safeHostname(pageUrl || affectedPages?.[0] || "") || scanHost;
  const scanRoot = rootDomain(scanHost);
  const pageRoot = rootDomain(pageHost);
  const pathText = [pageUrl, ...(affectedPages || [])].join(" ").toLowerCase();
  const scanText = String(scanUrl || "").toLowerCase();
  const sameParent = scanRoot && pageRoot && scanRoot === pageRoot;

  if (sameParent && isEnergyPath(scanText) && isCreditPath(pathText) && !isEnergyPath(pathText)) return "sibling_sous_dossier";
  if (sameParent && scanHost && pageHost && scanHost !== pageHost) return "same_parent_domain";
  return "";
}

function isEnergyPath(value) {
  const text = String(value || "").toLowerCase();
  return ENERGY_PATH_HINTS.some((hint) => text.includes(hint));
}

function isCreditPath(value) {
  const text = String(value || "").toLowerCase();
  return CREDIT_PATH_HINTS.some((hint) => text.includes(hint));
}

function isImportantBusinessPath(value) {
  const text = String(value || "").toLowerCase();
  return /devis|quote|simulation|simulateur|calcul|calculator|comparateur|pricing|tarif|contact|checkout|booking|reservation|product|produit|collection|category|fournisseur/.test(text);
}

function firstPath(values) {
  const value = Array.isArray(values) ? values.find(Boolean) : values;
  try {
    if (/^https?:\/\//i.test(String(value || ""))) return new URL(value).pathname || "/";
  } catch {}
  return String(value || "");
}

function buildSpecificTitle(item = {}) {
  const category = String(item.category || "").toLowerCase();
  const rule = String(item.rule || "").toLowerCase();
  if (rule.includes("long_title") || category === "meta_title") return "Improve this page's Google title";
  if (rule.includes("description") || category === "meta_description") return "Improve this page's Google description";
  if (rule.includes("schema") || category === "schema") return "Add business details for Google";
  if (rule.includes("canonical") || category === "canonical") return "Confirm the official version of this page";
  if (rule.includes("image_alt")) return "Add helpful image descriptions";
  if (rule.includes("h1") || category === "thin_content") return "Clarify the page content";
  return "Review this recommendation";
}

function buildSpecificExplanation(item = {}) {
  const current = cleanString(item.current_value || item.current);
  const page = firstArray([item.affected_pages])[0] || item.page_url || "this page";
  const category = String(item.category || "").toLowerCase();
  if (category === "meta_title") return current ? `The current Google title is: “${clampText(current, 160)}”. It may be too long or unclear for the page shown below.` : "This page's Google title needs a clearer, shorter version.";
  if (category === "meta_description") return current ? `The current Google description is: “${clampText(current, 180)}”. It may be too long, missing, or not clear enough for search results.` : "This page needs a clearer Google result description.";
  if (category === "schema") return `The page ${page} is missing structured business details that help Google understand the organization, service, product, or FAQ content.`;
  if (category === "canonical") return `The page ${page} does not clearly declare its official URL, which can cause duplicate-page confusion.`;
  return "FixList found this issue in the scan evidence for the affected page below.";
}

function buildSpecificWhy(item = {}) {
  const pageType = cleanString(item.page_type || item.page_value_label || item.business_importance);
  const category = String(item.category || "").toLowerCase();
  if (category === "meta_title") return pageType ? `This matters because this is a ${humanize(pageType)}. The Google title should make the page topic and offer clear before people click.` : "A better title can improve clarity in Google results and help visitors choose the right page.";
  if (category === "meta_description") return pageType ? `This matters because this is a ${humanize(pageType)}. The description should explain the value of the page and set the right expectation before the click.` : "A better description can improve how useful and trustworthy the result looks in Google.";
  if (category === "schema") return "Structured data can help Google understand who the business is, what it offers, and whether the page is trustworthy.";
  if (category === "canonical") return "Canonical settings help Google know which URL should get credit instead of splitting signals across duplicate versions.";
  return "Fixing this can improve how visitors and search engines understand the page.";
}

function buildGeneralSteps(item = {}, recommendation, needsHelp) {
  const existing = firstArray([item.what_to_do_steps, item.what_to_do, item.fix_steps, item.general_steps, item.next_steps, item.steps, item.action_steps]);
  if (existing.length > 0) return existing.map(String).slice(0, 5);
  if (needsHelp) return ["Share this item with your web person.", "Ask them to review the affected URL and scan evidence.", "Publish the fix and run FixList again."];

  const category = String(item.category || "").toLowerCase();
  if (category === "meta_title") return ["Open the affected page in your CMS.", "Write a shorter title that names the specific page, service, product, or tool.", "Put the most important phrase near the beginning and keep the brand at the end.", "Publish and run FixList again."];
  if (category === "meta_description") return ["Open the affected page's SEO settings.", "Write one concise description that says what the visitor can do on this page.", "Mention the main benefit or next step, not generic marketing copy.", "Publish and run FixList again."];
  if (category === "schema") return ["Choose the right schema type for the page, such as Organization, LocalBusiness, Product, FAQ, or Breadcrumb.", "Add the schema through your CMS, SEO plugin, theme, or developer.", "Validate the page with a structured data checker."];
  if (category === "canonical") return ["Open the affected page or template.", "Set the canonical URL to the clean official version of the page.", "Check that duplicate/filter/tracking URLs point back to the official version."];
  return ["Review the affected page.", recommendation, "Publish the change and run FixList again."];
}

function getCmsSteps(cms, recommendation) {
  if (isBlocked429(recommendation.original)) {
    return [
      "Do not edit page copy first. This is a server/CDN/firewall access check.",
      "Send the affected URL(s) and HTTP 429 evidence to your web person.",
      "Ask them to check rate-limit, bot-protection, CDN, firewall, and server logs.",
      "Confirm whether Googlebot and normal users can access the page, then rescan.",
    ];
  }

  const category = String(recommendation.original?.category || "").toLowerCase();
  const title = category === "meta_title";
  const description = category === "meta_description";
  const schema = category === "schema";
  const canonical = category === "canonical";

  if (cms === "shopify") {
    if (title || description) return ["In Shopify, open the affected product, collection, page, or blog post.", "Scroll to Search engine listing and click Edit.", title ? "Rewrite the Page title so it is specific and not cut off." : "Rewrite the Meta description so it explains the product, collection, or page clearly.", "Save and run FixList again."];
    return ["Open the affected item in Shopify.", "Update the content, theme, image alt text, redirects, or structured data as needed.", "Save and run FixList again."];
  }

  if (cms === "wordpress") {
    if (title || description) return ["In WordPress, open the affected Page or Post.", "Open your SEO plugin panel, such as Yoast or Rank Math.", title ? "Edit the SEO title using the page's specific topic and offer." : "Edit the meta description using a concise benefit and next step.", "Update, publish, and run FixList again."];
    if (schema || canonical) return ["Open the page in WordPress or your SEO plugin.", canonical ? "Set the canonical URL to the official clean URL." : "Add the correct schema type through your SEO plugin or theme.", "Save, clear cache, and run FixList again."];
  }

  if (cms === "joomla") {
    if (title || description) return ["In Joomla, open the related Article or Menu Item.", title ? "Update the Browser Page Title with a shorter page-specific title." : "Update the Meta Description with a concise page-specific description.", "Save, clear cache if needed, and run FixList again."];
    return ["In Joomla, open the Article, Menu Item, template, or SEO extension connected to this page.", "Apply the recommended content, canonical, schema, redirect, or image update.", "Save, clear cache, and run FixList again."];
  }

  return ["Open the affected page in your website editor or SEO settings.", title || description ? "Update the page-specific Google title or description using the scan evidence above." : "Apply the recommended content, setup, image, schema, redirect, or technical fix.", "Publish the update and run FixList again."];
}

function buildEvidenceItems(recommendation) {
  const items = [];
  if (recommendation.scopeRelationship) items.push({ label: "Scope", value: humanize(recommendation.scopeRelationship) });
  if (recommendation.pageType) items.push({ label: "Page type", value: humanize(recommendation.pageType) });
  if (recommendation.pageValueLabel) items.push({ label: "Business value", value: recommendation.pageValueLabel });
  if (recommendation.defectClass) items.push({ label: "Issue type", value: humanize(recommendation.defectClass) });
  if (recommendation.metaGate) items.push({ label: "Meta gate", value: humanize(recommendation.metaGate) });
  if (recommendation.currentValue) items.push({ label: "Current value", value: clampText(recommendation.currentValue, 180) });
  return items.slice(0, 6);
}

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

  const valid = candidates.filter(Boolean).map(normalizeStoredScanCandidate).filter(isUsefulScanCandidate).sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
  return valid[0] || null;
}

function normalizeStoredScanCandidate(candidate) {
  if (!candidate || typeof candidate !== "object") return null;
  const pages = getPages(candidate);
  const recommendations = getRecommendations(candidate);
  const score = getHealthScore(candidate);
  return { ...candidate, pages, crawled_pages: pages, recommendations, fixes: recommendations, findings: recommendations, health_score: score, seo_score: score };
}

function isUsefulScanCandidate(candidate) {
  if (!candidate) return false;
  return Boolean(candidate.website_url || candidate.raw?.scanner?.website_url) && (getPages(candidate).length > 0 || getRecommendations(candidate).length > 0 || getHealthScore(candidate) > 0);
}

function readScanDebugData() {
  if (typeof window === "undefined") return { raw: {}, parsed: {} };
  const raw = {};
  const parsed = {};
  STORAGE_KEYS.forEach((key) => {
    const value = window.localStorage.getItem(key);
    raw[key] = value;
    try { parsed[key] = value ? JSON.parse(value) : null; } catch { parsed[key] = value; }
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

function getRecommendations(record) {
  return firstArray([record?.recommendations, record?.fixes, record?.findings, record?.cleaned_fixes, record?.raw_fixes, record?.issues]);
}

function getPages(record) {
  return firstArray([record?.crawled_pages, record?.pages, record?.scanned_pages, record?.raw?.scanner?.pages_preview]);
}

function getTopActions(record, normalizedRecommendations) {
  const actions = firstArray([record?.top_recommended_actions, record?.recommended_actions]);
  if (actions.length > 0) return actions.slice(0, 5).map((action) => sanitizeTopAction(action, normalizedRecommendations));
  return normalizedRecommendations.slice(0, 5).map((item) => ({ title: item.title, reason: item.whyItMatters, priority: item.priority }));
}

function sanitizeTopAction(action = {}, normalizedRecommendations = []) {
  const match = normalizedRecommendations.find((item) => item.id === action.fix_id || item.original?.fix_id === action.fix_id || item.original?.id === action.fix_id);
  if (match && isBlocked429(match.original)) return { title: match.title, reason: match.whyItMatters, priority: match.priority };
  return action;
}

function getHealthScore(record) {
  const score = Number(record?.health_score || record?.seo_score || record?.website_health_report?.health_score || record?.scan_summary?.health_score || record?.scan_summary?.score || 0);
  return Number.isFinite(score) ? Math.round(score) : 0;
}

function getPagesScanned(record, pages) {
  const count = Number(record?.pages_crawled || record?.pages_scanned || record?.pages_checked || record?.scan_summary?.pages_scanned || record?.technical_audit_summary?.pages_crawled || pages.length || 0);
  return Number.isFinite(count) ? count : 0;
}

function getBestSummary(record, healthScore, pagesScanned, issueCount) {
  const summary = cleanString(record?.customer_summary || record?.simple_summary || record?.website_health_report?.overall_explanation || record?.scan_summary?.plain_english_summary || record?.scan_summary?.summary);
  if (summary) return normalizeCoverageSummary(summary, pagesScanned);
  const label = getScoreBand(healthScore).label;
  return `Your website health is ${label.toLowerCase()} with a score of ${healthScore || 0}/100. FixList reviewed ${pagesScanned || 0} pages and found ${issueCount || 0} recommendations. Start with the highest-impact items first.`;
}

function countBuckets(recommendations) {
  return recommendations.reduce((acc, item) => {
    acc[item.bucket] = Number(acc[item.bucket] || 0) + 1;
    return acc;
  }, { needs_approval: 0, auto_fixed: 0, needs_developer: 0 });
}

function getIssueBucket(item = {}) {
  const owner = String(item.who_can_do_this || item.owner || "").toLowerCase();
  const status = String(item.status || "").toLowerCase();
  const difficulty = String(item.difficulty || "").toLowerCase();
  const text = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.recommended_value || ""} ${item.why_it_matters || ""}`.toLowerCase();
  if (owner.includes("web") || owner.includes("developer") || difficulty === "developer" || status === "needs_developer") return "needs_developer";
  if (/429|server|firewall|bot protection|cloudflare|rate.limit|crawlable html|javascript|rendering|schema|canonical|redirect|robots|noindex|indexability/.test(text)) return "needs_developer";
  if (status === "auto_fixed" || item.can_auto_fix) return "auto_fixed";
  return "needs_approval";
}

function normalizePriority(value) {
  const priority = String(value || "").toLowerCase();
  if (["critical", "high", "medium", "low"].includes(priority)) return priority;
  return "medium";
}

function getPriorityLabel(priority) {
  if (priority === "critical") return "Critical";
  if (priority === "high") return "High";
  if (priority === "low") return "Low";
  return "Medium";
}

function getPriorityStyles(priority) {
  if (priority === "critical") return { badge: "bg-red-50 text-red-700" };
  if (priority === "high") return { badge: "bg-orange-50 text-orange-700" };
  if (priority === "low") return { badge: "bg-slate-100 text-slate-600" };
  return { badge: "bg-amber-50 text-amber-700" };
}

function getScoreBand(score) {
  const number = Number(score || 0);
  if (number >= 90) return { label: "Excellent", className: "bg-emerald-50 text-emerald-700" };
  if (number >= 75) return { label: "Good", className: "bg-emerald-50 text-emerald-700" };
  if (number >= 55) return { label: "Fair", className: "bg-amber-50 text-amber-700" };
  return { label: "Needs work", className: "bg-red-50 text-red-700" };
}

function formatPageLabel(page) {
  try {
    const url = new URL(page);
    return url.hostname;
  } catch {
    return String(page || "Page").replace(/^https?:\/\//, "");
  }
}

function formatPagePath(page) {
  try {
    const url = new URL(page);
    return `${url.pathname}${url.search}` || "/";
  } catch {
    return String(page || "");
  }
}

function isFullUrl(value) {
  return /^https?:\/\//i.test(String(value || ""));
}

function normalizeCmsValue(value) {
  const normalized = String(value || "custom").toLowerCase();
  return CMS_OPTIONS.some((item) => item.value === normalized) ? normalized : "custom";
}

function firstArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

function unique(values) {
  return Array.from(new Set((values || []).filter((value) => value !== undefined && value !== null && String(value).trim() !== "")));
}

function cleanString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function clampText(value, max) {
  const text = String(value || "").trim();
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`;
}

function getFirstNumber(values) {
  for (const value of values || []) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return 0;
}

function humanize(value) {
  return String(value || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().replace(/^\w/, (char) => char.toUpperCase());
}

function normalizeCoverageSummary(summary, pagesCrawled) {
  const text = String(summary || "");
  const count = Number(pagesCrawled || 0);
  if (!count || !text) return text;
  return text.replace(/The scanner reviewed\s+\d+\s+pages/gi, `The scanner reviewed ${count} pages`).replace(/scanner reviewed\s+\d+\s+pages/gi, `scanner reviewed ${count} pages`);
}

function safeHostname(value) {
  try {
    return new URL(String(value || "")).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function rootDomain(hostname) {
  const host = String(hostname || "").replace(/^www\./, "").toLowerCase();
  const parts = host.split(".").filter(Boolean);
  if (parts.length <= 2) return host;
  return parts.slice(-2).join(".");
}

function stableId(input) {
  let hash = 0;
  const value = String(input || "");
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return `finding_${Math.abs(hash)}`;
}

function buildDebugSummary(debugData = {}) {
  const parsed = debugData.parsed || {};
  const debug = parsed[SCAN_DEBUG_KEY] || {};
  const lastScan = parsed[DASHBOARD_LAST_SCAN_KEY] || parsed[LEGACY_LAST_SCAN_KEY] || debug.final_record || {};
  return {
    status: debug.status || debug.stage || "saved",
    websiteUrl: lastScan.website_url || debug.website_url || parsed[ACTIVE_SCAN_URL_KEY] || "",
    pages: lastScan.pages_crawled || debug.final_record?.pages_crawled || debug.scanner?.pages_crawled || 0,
    score: lastScan.health_score || debug.final_record?.health_score || debug.ai_review?.health_score || debug.scanner?.health_score || "",
  };
}

function scrollToRecommendations() {
  const element = document.getElementById("recommendations");
  if (element) element.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatDate(value) {
  try {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return "Recent";
  }
}
