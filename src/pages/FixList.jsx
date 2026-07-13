import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bug, Copy, ExternalLink, RefreshCw, Trash2 } from "lucide-react";

import { isRateLimitFinding, shouldUseLegacyRateLimitPresentation } from "@/lib/reviewContract";
import { trackEvent } from "@/lib/analytics";
import ScoreRing from "@/components/fixlist/ScoreRing";

const DASHBOARD_LAST_SCAN_KEY = "seo_autopilot:last_scan";
const DASHBOARD_HISTORY_KEY = "seo_autopilot:scan_history";
const LEGACY_LAST_SCAN_KEY = "SEO_AUTOPILOT_LAST_SCAN";
const LEGACY_HISTORY_KEY = "SEO_AUTOPILOT_SCAN_HISTORY";
const ACTIVE_SCAN_URL_KEY = "seo_autopilot:active_scan_url";
const ACTIVE_SCAN_STARTED_AT_KEY = "seo_autopilot:active_scan_started_at";
const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";
const DONE_FIXES_KEY = "seo_autopilot:done_fixes";

const STORAGE_KEYS = [
  DASHBOARD_LAST_SCAN_KEY,
  LEGACY_LAST_SCAN_KEY,
  DASHBOARD_HISTORY_KEY,
  LEGACY_HISTORY_KEY,
  ACTIVE_SCAN_URL_KEY,
  ACTIVE_SCAN_STARTED_AT_KEY,
  SCAN_DEBUG_KEY,
  DONE_FIXES_KEY,
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

const ENERGY_PATH_HINTS = ["energie", "énergie", "electricite", "électricité", "gaz", "fournisseur", "kwh", "tarif"];
const CREDIT_PATH_HINTS = ["rachat-de-credits", "rachat-de-credit", "credit", "crédit", "credits", "crédits", "pret", "prêt", "emprunt"];

// Checks the scanner actually runs; a check "passes" when no finding in the
// scanned sample carries its category. Copy is deliberately sample-scoped —
// the contract forbids claiming the whole site is perfect.
const PASSED_CHECK_DEFINITIONS = [
  { categories: ["404_error", "broken_page"], label: "No broken pages found in the pages we checked" },
  { categories: ["meta_title"], label: "Search titles look good on the pages we checked" },
  { categories: ["meta_description"], label: "Search descriptions look good on the pages we checked" },
  { categories: ["canonical"], label: "Canonical settings look right on the pages we checked" },
  { categories: ["image_alt_text", "alt_text"], label: "Images have text descriptions on the pages we checked" },
  { categories: ["schema"], label: "No missing trust signals on the pages we checked" },
  { categories: ["duplicate_content"], label: "No duplicate search text found in the pages we checked" },
  { categories: ["internal_link"], label: "No internal link problems found in the pages we checked" },
  { categories: ["indexability"], label: "Google can index the pages we checked" },
];

export default function FixList() {
  const navigate = useNavigate();
  const [scanRecord, setScanRecord] = useState(() => readBestScanRecord());
  const [debugData, setDebugData] = useState(() => readScanDebugData());
  const [selectedCms, setSelectedCms] = useState(() => normalizeCmsValue(scanRecord?.cms_platform || "custom"));
  const [doneIds, setDoneIds] = useState(() => readDoneFixIds(websiteKeyOf(scanRecord)));

  function reloadScan() {
    const next = readBestScanRecord();
    setScanRecord(next);
    setDebugData(readScanDebugData());
    setDoneIds(readDoneFixIds(websiteKeyOf(next)));
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
  const pages = useMemo(() => getPages(scanRecord), [scanRecord]);
  const healthScore = getHealthScore(scanRecord);
  const pagesScanned = getPagesScanned(scanRecord, pages);
  const hasUsefulScan = Boolean(scanRecord && (recommendations.length > 0 || pages.length > 0 || healthScore > 0));
  const noHighConfidenceFindings = isNoHighConfidenceFindings(scanRecord, recommendations);
  const nextBestStep = getNextBestStep(scanRecord, noHighConfidenceFindings);
  const websiteKey = websiteKeyOf(scanRecord);
  const websiteHost = safeHostname(scanRecord?.website_url) || websiteKey || "";

  const active = recommendations.filter((item) => !doneIds.includes(item.id));
  const doneItems = recommendations.filter((item) => doneIds.includes(item.id));
  const fixNow = active.filter((item) => item.priority === "critical" || item.priority === "high");
  const later = active.filter((item) => item.priority !== "critical" && item.priority !== "high");
  const passedChecks = hasUsefulScan ? buildPassedChecks(recommendations) : [];
  const limitationNote = getLimitationNote(scanRecord);
  const summary = hasUsefulScan ? getBestSummary(scanRecord, healthScore, pagesScanned, recommendations.length) : "";
  const healthGrade = hasUsefulScan ? getHealthGrade(scanRecord, healthScore, noHighConfidenceFindings) : "";

  function markDone(item) {
    const next = [...doneIds, item.id];
    setDoneIds(next);
    writeDoneFixIds(websiteKey, next);
    trackEvent("recommendation_marked_reviewed", { fix_id: item.id, category: item.category });
  }

  function undoDone(item) {
    const next = doneIds.filter((id) => id !== item.id);
    setDoneIds(next);
    writeDoneFixIds(websiteKey, next);
  }

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[680px] px-6 pb-24">
        <div className="flex items-center justify-between pt-7">
          <div className="text-[15px] font-medium tracking-tight text-ink-muted">{websiteHost || ""}</div>
          <button
            type="button"
            onClick={() => navigate("/onboarding")}
            className="rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            {hasUsefulScan ? "Scan again" : "Run a scan"}
          </button>
        </div>

        {hasUsefulScan ? (
          <>
            <p className="mt-16 text-[13px] text-ink-faint tabular-nums">
              Scanned {scanRecord?.created_at ? formatDate(scanRecord.created_at) : "recently"} · {pagesScanned} pages checked
              {passedChecks.length > 0 ? ` · ${passedChecks.length} checks passed` : ""}
            </p>

            <div className="mt-4 flex items-center gap-7">
              <ScoreRing score={healthScore} />
              <div>
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
                  {getHeroHeadline({ healthScore, noHighConfidenceFindings, activeCount: active.length, doneCount: doneItems.length })}
                </h1>
                <p className="mt-1.5 text-[15px] text-ink-muted tabular-nums">
                  {getHeroSub({ noHighConfidenceFindings, nextBestStep, activeCount: active.length, doneCount: doneItems.length })}
                </p>
                {healthGrade ? <p className="mt-1 text-[13px] text-ink-faint">{healthGrade}</p> : null}
              </div>
            </div>

            {summary ? (
              <p className="mt-8 max-w-[56ch] text-[14px] leading-relaxed text-ink-muted">{summary}</p>
            ) : null}

            {limitationNote ? (
              <p className="mt-6 border-l-2 border-warnink/40 pl-3 text-[13.5px] leading-relaxed text-ink-muted">{limitationNote}</p>
            ) : null}

            {fixNow.length > 0 ? (
              <>
                <SectionEyebrow label="Fix now" count={fixNow.length} />
                <div className="mt-2">
                  {fixNow.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} onDone={() => markDone(item)} />
                  ))}
                </div>
              </>
            ) : null}

            {later.length > 0 ? (
              <>
                <SectionEyebrow label="When you have time" count={later.length} />
                <div className="mt-2">
                  {later.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} onDone={() => markDone(item)} />
                  ))}
                </div>
              </>
            ) : null}

            {active.length === 0 && doneItems.length > 0 ? (
              <div className="mt-16 py-10">
                <h2 className="text-[22px] font-semibold tracking-tight">All clear.</h2>
                <p className="mt-2 max-w-[48ch] text-ink-muted">
                  Every fix is marked done. Scan again once the changes are live and we&rsquo;ll confirm them.
                </p>
              </div>
            ) : null}

            {active.length === 0 && doneItems.length === 0 && noHighConfidenceFindings ? (
              <div className="mt-16 py-4">
                <h2 className="text-[22px] font-semibold tracking-tight">Nothing to fix in this sample.</h2>
                <p className="mt-2 max-w-[48ch] text-ink-muted">
                  {nextBestStep || "No high-confidence issues were found in the pages we checked."}
                </p>
              </div>
            ) : null}

            {passedChecks.length > 0 ? <PassedChecks checks={passedChecks} /> : null}

            {doneItems.length > 0 ? (
              <>
                <SectionEyebrow label="Done" count={doneItems.length} />
                <div className="mt-2">
                  {doneItems.map((item) => (
                    <div key={item.id} className="flex items-baseline justify-between border-b border-hairline-soft py-3.5 text-[14px] text-ink-faint">
                      <span className="line-through">{item.title}</span>
                      <button
                        type="button"
                        onClick={() => undoDone(item)}
                        className="shrink-0 pl-4 text-[13px] text-ink-muted transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                      >
                        Undo
                      </button>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {active.length > 0 ? <CmsPicker selectedCms={selectedCms} onChange={setSelectedCms} /> : null}
          </>
        ) : (
          <NoScanState onScan={() => navigate("/onboarding")} />
        )}

        <ScanDebugPanel debugData={debugData} onRefresh={reloadScan} onClear={() => { clearAllScanData(); reloadScan(); }} />

        <footer className="mt-24 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          {hasUsefulScan
            ? `FixList checked ${pagesScanned} pages of your site this scan. Some checks depend on how your site behaves for Google over time, so a perfect score isn't the goal — a shorter list is.`
            : "FixList checks the most important pages of your site and turns what it finds into a short, plain-English list."}
        </footer>
      </div>
    </div>
  );
}

function SectionEyebrow({ label, count }) {
  return (
    <div className="mt-16 flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
      {label}
      {typeof count === "number" ? <span className="font-normal tabular-nums">{count}</span> : null}
    </div>
  );
}

function FixRow({ item, cms, onDone }) {
  const [open, setOpen] = useState(false);
  const severe = item.priority === "critical" || item.priority === "high";
  const cmsSteps = getCmsSteps(cms, item);
  const evidenceItems = buildEvidenceItems(item).slice(0, 3);
  const shownPages = item.affectedPages.slice(0, 4);
  const extraCount = Math.max(0, item.affectedPages.length - shownPages.length);

  return (
    <div className="border-b border-hairline-soft">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-3.5 py-5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <span className={`mt-[7px] h-[7px] w-[7px] shrink-0 rounded-full ${severe ? "bg-crit" : "bg-warnink"}`} />
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-medium tracking-tight">{item.title}</span>
          <span className="mt-0.5 block text-[13.5px] text-ink-muted">{clampText(item.explanation, 110)}</span>
        </span>
        <span className="mt-0.5 flex shrink-0 items-center gap-3">
          <span className="hidden text-[12px] text-ink-faint sm:block">{item.needsHelp ? "Developer" : "You"}</span>
          <span className={`text-[12px] leading-none text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        </span>
      </button>

      {open ? (
        <div className="pb-6 pl-[21px] text-[14px] text-ink-muted">
          <p className="max-w-[56ch]">{item.whyItMatters}</p>

          {evidenceItems.length > 0 ? (
            <>
              <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Evidence</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">
                {evidenceItems.map((entry) => `${entry.label}: ${entry.value}`).join(" · ")}
              </p>
            </>
          ) : null}

          <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Where</div>
          <ol className="mt-1 max-w-[56ch] list-decimal space-y-1 pl-4 text-ink">
            {cmsSteps.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}
          </ol>

          {shownPages.length > 0 ? (
            <>
              <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Pages</div>
              <div className="mt-1 space-y-1">
                {shownPages.map((page, index) => <AffectedPage key={`${page}-${index}`} page={page} />)}
                {extraCount > 0 ? <p className="text-[13px] text-ink-faint tabular-nums">+{extraCount} more</p> : null}
              </div>
            </>
          ) : null}

          <button
            type="button"
            onClick={onDone}
            className="mt-5 rounded-full border border-hairline px-4 py-1.5 text-[13px] font-medium text-ink transition-colors hover:border-good/25 hover:bg-good/[0.07] hover:text-good focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Mark as done
          </button>
        </div>
      ) : null}
    </div>
  );
}

function PassedChecks({ checks }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SectionEyebrow label="Already good" />
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="py-3.5 text-[13.5px] text-ink-muted transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        {checks.length} checks passed — {open ? "hide them" : "show them"}
      </button>
      {open ? (
        <div>
          {checks.map((check) => (
            <div key={check} className="flex gap-3.5 py-2.5 text-[14px] text-ink-muted">
              <span className="mt-px text-[13px] text-good">✓</span>
              {check}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

function CmsPicker({ selectedCms, onChange }) {
  return (
    <div className="mt-16 flex items-center gap-3 text-[13.5px] text-ink-muted">
      <label htmlFor="cms-picker">Instructions written for</label>
      <select
        id="cms-picker"
        value={selectedCms}
        onChange={(event) => onChange(event.target.value)}
        className="cursor-pointer rounded-full border border-hairline bg-transparent px-3 py-1.5 text-[13px] font-medium text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        {CMS_OPTIONS.map((cmsOption) => (
          <option key={cmsOption.value} value={cmsOption.value}>{cmsOption.label}</option>
        ))}
      </select>
    </div>
  );
}

function NoScanState({ onScan }) {
  return (
    <div className="mt-24">
      <h1 className="text-[26px] font-semibold leading-tight tracking-tight">No FixList yet.</h1>
      <p className="mt-2 max-w-[48ch] text-[15px] text-ink-muted">
        Run a scan and we&rsquo;ll turn what we find into a short, plain-English list of fixes — each with where to click and who should do it.
      </p>
      <button
        type="button"
        onClick={onScan}
        className="mt-6 rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        Run my scan
      </button>
    </div>
  );
}

function AffectedPage({ page }) {
  const label = formatPageLabel(page);
  const path = formatPagePath(page);
  const showPath = cleanString(path) !== cleanString(label);

  return (
    <div className="flex items-center gap-2 text-[13px] tabular-nums">
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{label}</p>
        {showPath ? <p className="truncate text-ink-faint">{path}</p> : null}
      </div>
      {isFullUrl(page) ? (
        <a href={page} target="_blank" rel="noreferrer" className="shrink-0 p-1 text-ink-faint transition-colors hover:text-ink" aria-label="Open page">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
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
    <section className="mt-16 border-t border-hairline-soft pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px] text-ink-faint">
        <button type="button" onClick={() => setOpen((value) => !value)} className="flex items-center gap-1.5 transition-colors hover:text-ink">
          <Bug className="h-3.5 w-3.5" />
          {open ? "Hide scan details" : "Scan details"}
        </button>
        <button type="button" onClick={onRefresh} className="flex items-center gap-1.5 transition-colors hover:text-ink">
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
        <button type="button" onClick={copyJson} className="flex items-center gap-1.5 transition-colors hover:text-ink">
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy JSON"}
        </button>
        <button type="button" onClick={onClear} className="flex items-center gap-1.5 transition-colors hover:text-crit">
          <Trash2 className="h-3.5 w-3.5" />
          Clear scans
        </button>
        <span className="tabular-nums">
          {summary.status || "no scan"}{summary.pages ? ` · ${summary.pages} pages` : ""}{summary.score ? ` · score ${summary.score}` : ""}
        </span>
      </div>

      {open ? (
        <pre className="mt-4 max-h-[480px] overflow-auto rounded-lg border border-hairline bg-ink p-4 text-xs leading-5 text-paper">{JSON.stringify(debugData, null, 2)}</pre>
      ) : null}
    </section>
  );
}

function getHeroHeadline({ healthScore, noHighConfidenceFindings, activeCount, doneCount }) {
  if (noHighConfidenceFindings && activeCount === 0 && doneCount === 0) return "Nothing to fix in this sample.";
  if (activeCount === 0 && doneCount > 0) return "Nothing left on the list.";
  if (healthScore >= 85) return "Great shape overall.";
  if (healthScore >= 70) return "Good shape overall.";
  if (healthScore >= 50) return "Getting there.";
  return "Room to improve.";
}

function getHeroSub({ noHighConfidenceFindings, nextBestStep, activeCount, doneCount }) {
  if (noHighConfidenceFindings && activeCount === 0 && doneCount === 0) {
    return nextBestStep || "No high-confidence issues were found in the pages we checked.";
  }
  if (activeCount === 0 && doneCount > 0) return "Score will settle after your next scan.";
  const word = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"][activeCount] || activeCount;
  return `${word} fix${activeCount === 1 ? "" : "es"} to work through — start at the top.`;
}

function getLimitationNote(record) {
  const limitation = cleanString(record?.limitation);
  if (limitation) return limitation;
  if (record?.score_is_provisional === true) return "Scan coverage was limited, so this score is provisional. Fix what's below, then scan again for a fuller picture.";
  return "";
}

function buildPassedChecks(recommendations) {
  const present = new Set(recommendations.map((item) => String(item.category || "").toLowerCase()));
  return PASSED_CHECK_DEFINITIONS
    .filter((check) => check.categories.every((category) => !present.has(category)))
    .map((check) => check.label);
}

function websiteKeyOf(record) {
  const key = cleanString(record?.website_key);
  if (key) return key;
  return safeHostname(record?.website_url) || "";
}

function readDoneFixIds(websiteKey) {
  if (!websiteKey) return [];
  const stored = safeParseLocalStorage(DONE_FIXES_KEY);
  const list = stored && typeof stored === "object" ? stored[websiteKey] : null;
  return Array.isArray(list) ? list.map(String) : [];
}

function writeDoneFixIds(websiteKey, ids) {
  if (!websiteKey || typeof window === "undefined") return;
  try {
    const stored = safeParseLocalStorage(DONE_FIXES_KEY) || {};
    stored[websiteKey] = Array.from(new Set(ids.map(String)));
    window.localStorage.setItem(DONE_FIXES_KEY, JSON.stringify(stored));
  } catch (error) {
    console.warn("Could not save done fixes.", error);
  }
}

function normalizeRecommendation(item = {}, scanRecord = {}) {
  const legacyBlocked429 = shouldUseLegacyRateLimitPresentation(scanRecord, item);
  const evidence = legacyBlocked429 ? extractRecommendationEvidence(item, scanRecord) : {};
  const priority = legacyBlocked429 ? blockedPriority(item, evidence) : normalizePriority(item.priority);
  const category = String(item.category || "other").toLowerCase();
  const affectedPages = firstArray([item.affected_pages, item.pages, item.page_urls]);
  const fallbackPage = item.page_url || item.url || affectedPages[0] || "";
  const bucket = legacyBlocked429 ? "needs_developer" : getIssueBucket(item);
  const customerCategory = legacyBlocked429 ? "Scan coverage" : item.customer_category || CATEGORY_LABELS[category] || humanize(category || "Website improvement");
  const title = legacyBlocked429 ? build429Title(evidence) : cleanString(item.issue_title || item.title || item.name) || buildSpecificTitle(item);
  const explanation = legacyBlocked429 ? build429Explanation(evidence) : cleanString(item.plain_english_explanation || item.plain_english_summary || item.explanation || item.description || item.summary || item.recommendation) || buildSpecificExplanation(item);
  const whyItMatters = legacyBlocked429 ? build429Why(evidence) : cleanString(item.why_it_matters || item.impact || item.reason) || buildSpecificWhy(item);
  const recommendation = legacyBlocked429 ? build429Recommendation(evidence) : cleanString(item.simple_next_step || item.recommended_value || item.recommendation || item.suggested_fix || item.ai_recommendation) || "Review the affected page and make the recommended update.";
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
    currentValue: legacyBlocked429 ? "HTTP 429 — crawler was rate-limited or blocked" : cleanString(item.current_value || item.current || item.detected_value),
    pageType: legacyBlocked429 && evidence.scopeRelationship === "sibling_sous_dossier" ? "Sibling sous-dossier" : cleanString(item.page_type || item.page_value_label || item.business_importance),
    defectClass: legacyBlocked429 ? "Rate-limit / crawler access" : cleanString(item.primary_defect_class || item.meta_regeneration_gate),
    pageValueLabel: legacyBlocked429 ? evidence.businessValueLabel : cleanString(item.page_value_label),
    businessImportance: legacyBlocked429 ? evidence.businessImportance : cleanString(item.business_importance),
    metaGate: cleanString(item.meta_regeneration_gate),
    scopeRelationship: legacyBlocked429 ? evidence.scopeRelationship : cleanString(item.scope_relationship),
    pageScope: cleanString(item.page_scope),
    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    needsHelp,
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),
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
  return isRateLimitFinding(item);
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
  if (recommendation.pageScope) items.push({ label: "Scope", value: humanize(recommendation.pageScope) });
  else if (recommendation.scopeRelationship) items.push({ label: "Scope", value: humanize(recommendation.scopeRelationship) });
  if (recommendation.evidenceStatus) items.push({ label: "Evidence", value: humanize(recommendation.evidenceStatus) });
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



function getHealthScore(record) {
  const score = Number(record?.health_score || record?.seo_score || record?.website_health_report?.health_score || record?.scan_summary?.health_score || record?.scan_summary?.score || 0);
  return Number.isFinite(score) ? Math.round(score) : 0;
}

function getPagesScanned(record, pages) {
  const count = Number(record?.pages_crawled || record?.pages_scanned || record?.pages_checked || record?.scan_summary?.pages_scanned || record?.technical_audit_summary?.pages_crawled || pages.length || 0);
  return Number.isFinite(count) ? count : 0;
}

function isNoHighConfidenceFindings(record, recommendations = []) {
  const scanStatus = String(record?.scan_status || "");
  if (["incomplete_evidence", "blocked_or_incomplete"].includes(scanStatus)) return false;
  return record?.no_high_confidence_findings === true
    || record?.review_confidence_state === "no_high_confidence_findings"
    || scanStatus === "complete_no_high_confidence_findings"
    || recommendations.length === 0;
}

function getHealthGrade(record, healthScore, noHighConfidenceFindings) {
  return cleanString(record?.website_health_report?.health_grade || record?.health_grade)
    || (noHighConfidenceFindings ? "No issues found in sample" : getScoreBand(healthScore).label);
}

function getNextBestStep(record, noHighConfidenceFindings) {
  return cleanString(record?.website_health_report?.next_best_step || record?.next_best_step)
    || (noHighConfidenceFindings ? "No high-confidence issues were found in the scanned sample — consider a deeper crawl or manual review of money pages." : "");
}

function getBestSummary(record, healthScore, pagesScanned, issueCount) {
  const summary = cleanString(record?.customer_summary || record?.simple_summary || record?.website_health_report?.overall_explanation || record?.scan_summary?.plain_english_summary || record?.scan_summary?.summary);
  if (summary) return normalizeCoverageSummary(summary, pagesScanned);
  const label = getScoreBand(healthScore).label;
  return `Your website health is ${label.toLowerCase()} with a score of ${healthScore || 0}/100. FixList reviewed ${pagesScanned || 0} pages and found ${issueCount || 0} recommendations. Start with the highest-impact items first.`;
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


function formatDate(value) {
  try {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return "Recent";
  }
}
