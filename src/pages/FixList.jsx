import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Copy, Download, ExternalLink } from "lucide-react";

import { isRateLimitFinding, shouldUseLegacyRateLimitPresentation } from "@/lib/reviewContract";
import { getScanRunWithFixList, listAccountScanRuns } from "@/lib/scanRuns";
import { customerRecoveryFailure } from "@/lib/scanRuns";
import { ACTIVE_SCAN_RUN_STATUSES } from "@/lib/scanRunIdentity";
import { UNLOCK_PRICE_LABEL } from "@/lib/access";
import UnlockAccessButton from "@/components/billing/UnlockAccessButton";
import { CUSTOMER_BOUNDARY_EVENT } from "@/lib/customerBrowserCache";
import ScoreRing from "@/components/fixlist/ScoreRing";
import RecentScanRow from "@/components/fixlist/RecentScanRow";
import RepairWorkSurface from "@/components/fixlist/RepairWorkSurface";
import ExplicitPassedChecks from "@/components/fixlist/ExplicitPassedChecks";
import SuggestedFix from "@/components/fixlist/SuggestedFix";
import { deleteScanRun } from "@/lib/scanHistory";
import { prepareCustomerFixes, priorityBucket } from "@/lib/fixRanking";
import { buildRepairWorkSurfacePresentation } from "@/lib/repairWorkSurfacePresentation";
import { applyCustomerVocabulary, customerHealthLabel, customerPriorityLabel, customerScopeRelationshipLabel } from "@/lib/fixVocabulary";
import { repairSuggestion } from "@/lib/repairSuggestions";
import { buildRepairCards } from "@/lib/repairCardModel";
import { evidenceLink } from "@/lib/evidenceUrl";
import { samplingDisclosure } from "@/lib/samplingDisclosure";
import { displayPathPrefix, focusedPathSections, focusedSectionOnboardingPath } from "@/lib/focusedScanScope";

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

export const FAILURE_STATE_PRESENTATION_VERSION = "failure_state_presentation_v1_durable_reason";
export const PRIORITY_SUMMARY_VERSION = "priority_summary_v1_action_band_consistent";
export const COUNT_COPY_VERSION = "count_copy_v2_agreeing_verbs";

const CUSTOMER_RECOVERY_COPY = Object.freeze({
  unauthorized: {
    title: "Sign in again to open this scan",
    detail: "Your session could not be confirmed. Sign in again, then reopen the saved scan from your account.",
    action: "login",
  },
  not_found: {
    title: "Scan not found",
    detail: "This scan does not exist or is not available to this signed-in account. No other scan has been substituted.",
    action: "history",
  },
  access_conflict: {
    title: "We couldn't confirm this account's access",
    detail: "Your saved scan has not been replaced or removed. Contact support and include the reference below so the access record can be checked.",
    action: "support",
  },
  unavailable: {
    title: "This saved scan is temporarily unavailable",
    detail: "We couldn't reach the saved result service. Your scan has not been removed; try loading it again.",
    action: "retry",
  },
  release_mismatch: {
    title: "Your result is waiting for an app update",
    detail: "The scan finished, but the result service and this app are on different release versions. Your scan is saved; try loading it again after the update completes.",
    action: "retry",
  },
  authority_invalid: {
    title: "We couldn't verify this saved result",
    detail: "The result did not match its server verification seal, so no fix details are being shown. Contact support and include the reference below.",
    action: "support",
  },
  not_authoritative: {
    title: "This scan has no verified result",
    detail: "The scan did not produce a result that passed the release checks, so no fix details are being shown. You can run a fresh scan.",
    action: "new_scan",
  },
  load_failed: {
    title: "We couldn't load this saved scan",
    detail: "An unexpected error interrupted the read. Your saved scan has not been replaced; try loading it again.",
    action: "retry",
  },
});

/**
 * The same failure kind describes two different things depending on what was
 * being read: one saved scan, or the account's whole saved-scan history. Only
 * the button label varied by target before, so a history read that failed for
 * the entire account told the customer "your saved scan has not been replaced"
 * -- singular, about a record they had not asked for -- above a button offering
 * to retry loading saved scans, plural.
 *
 * Only the kinds a history read can actually produce are overridden.
 * getCustomerScanResult's list actions raise unauthorized and
 * result_load_failed, and transport failures classify as unavailable. Anything
 * else falls back to the single-scan wording rather than inventing copy for a
 * state that cannot be reached.
 */
const CUSTOMER_RECOVERY_HISTORY_COPY = Object.freeze({
  unauthorized: {
    title: "Sign in again to see your saved scans",
    detail: "Your session could not be confirmed. Sign in again to load the scans saved to your account.",
    action: "login",
  },
  unavailable: {
    title: "Your saved scans are temporarily unavailable",
    detail: "We couldn't reach the saved result service. None of your scans have been removed; try loading them again.",
    action: "retry",
  },
  load_failed: {
    title: "We couldn't load your saved scans",
    detail: "An unexpected error interrupted the read. Your saved scans have not been changed; try loading them again.",
    action: "retry",
  },
});

export function resolveRecoveryCopy(kind, target) {
  if (target !== "history") return CUSTOMER_RECOVERY_COPY[kind] || CUSTOMER_RECOVERY_COPY.load_failed;
  // A known kind with no history override keeps its own accurate meaning; only
  // an unrecognized one falls through, and it must land on the account-wide
  // catch-all rather than back on the singular copy this exists to avoid.
  return CUSTOMER_RECOVERY_HISTORY_COPY[kind]
    || CUSTOMER_RECOVERY_COPY[kind]
    || CUSTOMER_RECOVERY_HISTORY_COPY.load_failed;
}

export default function FixList() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedScanId = searchParams.get("scan_id") || "";
  const [scanRecord, setScanRecord] = useState(null);
  const [requestedScanState, setRequestedScanState] = useState(requestedScanId ? "loading" : "idle");
  const [requestedScanFailure, setRequestedScanFailure] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);
  // Survive effect re-runs: a poll re-runs the effect, so "have we already
  // loaded this exact scan?" cannot live in the effect's own scope.
  const loadedScanIdRef = useRef("");
  const pollTimerRef = useRef(0);
  const [selectedCms, setSelectedCms] = useState("custom");
  const [recentScans, setRecentScans] = useState([]);
  const [recentScansState, setRecentScansState] = useState(requestedScanId ? "idle" : "loading");
  const [recentScansFailure, setRecentScansFailure] = useState(null);
  const [historyReloadToken, setHistoryReloadToken] = useState(0);
  const [deletingScanId, setDeletingScanId] = useState("");
  useEffect(() => {
    let cancelled = false;

    // A background reread must never blank the view. Polling used to call
    // applyRecord(null) on every tick, so an active scan visibly alternated
    // between its real status and "Loading this scan…" with a "no scan" debug
    // footer every 2.5 seconds. The record is now cleared only when the scan
    // being viewed actually changes, when there is no scan id, or when the
    // customer/auth boundary is cleared.
    const isBackgroundRead = loadedScanIdRef.current === requestedScanId && Boolean(requestedScanId);

    function applyRecord(next) {
      if (cancelled) return;
      setScanRecord(next);
      if (next?.cms_platform) setSelectedCms(normalizeCmsValue(next.cms_platform));
    }

    function clearRecord() {
      if (cancelled) return;
      loadedScanIdRef.current = "";
      setScanRecord(null);
    }

    async function loadRequestedScan() {
      if (!requestedScanId) {
        clearRecord();
        setRequestedScanFailure(null);
        setRequestedScanState("idle");
        return;
      }
      // "Loading this scan…" is an initial-load state only.
      if (!isBackgroundRead) {
        clearRecord();
        setRequestedScanFailure(null);
        setRequestedScanState("loading");
      }

      const durableBundle = await getScanRunWithFixList(requestedScanId);
      if (cancelled) return;
      // Never substitute another scan for the one that was requested.
      const isExactScan = String(durableBundle?.run?.id || "") === String(requestedScanId);
      if (durableBundle?.ok === true && durableBundle?.run && isExactScan) {
        loadedScanIdRef.current = requestedScanId;
        applyRecord(normalizeDurableScanBundle(durableBundle));
        setRequestedScanFailure(null);
        setRequestedScanState("loaded");
        // Polling stops as soon as the run reaches a terminal state.
        if (ACTIVE_SCAN_RUN_STATUSES.has(String(durableBundle.run.status || ""))) {
          pollTimerRef.current = window.setTimeout(() => {
            if (!cancelled) setReloadToken((value) => value + 1);
          }, 2500);
        }
        return;
      }

      const failure = durableBundle?.ok === false
        ? durableBundle
        : customerRecoveryFailure({ error_code: "result_load_failed" }, `result:${requestedScanId}`);

      // A transient read error during polling must not erase the last exact,
      // proof-verified record. Keep it visible, explain the refresh failure,
      // and retry. Integrity, access, auth, and not-found failures clear it.
      if (
        isBackgroundRead
        && loadedScanIdRef.current === requestedScanId
        && failure.retryable === true
      ) {
        setRequestedScanFailure(failure);
        setRequestedScanState("loaded");
        pollTimerRef.current = window.setTimeout(() => {
          if (!cancelled) setReloadToken((value) => value + 1);
        }, 2500);
        return;
      }
      clearRecord();
      setRequestedScanFailure(failure);
      setRequestedScanState(failure.kind);
    }

    function clearProtectedView(event) {
      const reason = String(event?.detail?.reason || "");
      window.clearTimeout(pollTimerRef.current);
      if (!requestedScanId) {
        loadedScanIdRef.current = "";
        setScanRecord(null);
        setRequestedScanFailure(null);
        setRequestedScanState("idle");
        return;
      }

      // Only a real authentication boundary is allowed to declare the current
      // protected view unavailable without another server read. Project/cache
      // changes are not evidence that this exact ScanRun disappeared: reload
      // the requested scan_id and let getCustomerScanResult enforce ownership.
      if (["auth_expired", "session_cleared", "logout"].includes(reason)) {
        cancelled = true;
        loadedScanIdRef.current = "";
        setScanRecord(null);
        const failure = customerRecoveryFailure({ error_code: "unauthorized" }, `result:${requestedScanId}`);
        setRequestedScanFailure(failure);
        setRequestedScanState(failure.kind);
        return;
      }

      // Account switches clear any previously rendered protected data before
      // re-reading. Same-owner project/cache changes may keep the last exact
      // record visible while the new server-authorized read is in flight.
      if (reason === "account_switch") {
        loadedScanIdRef.current = "";
        setScanRecord(null);
        setRequestedScanState("loading");
      }
      setRequestedScanFailure(null);
      setReloadToken((value) => value + 1);
    }

    loadRequestedScan();
    window.addEventListener(CUSTOMER_BOUNDARY_EVENT, clearProtectedView);
    return () => {
      cancelled = true;
      window.clearTimeout(pollTimerRef.current);
      window.removeEventListener(CUSTOMER_BOUNDARY_EVENT, clearProtectedView);
    };
  }, [requestedScanId, reloadToken]);

  useEffect(() => {
    let cancelled = false;

    if (requestedScanId) {
      setRecentScans([]);
      setRecentScansFailure(null);
      setRecentScansState("idle");
      return undefined;
    }

    async function loadRecentScans() {
      setRecentScansFailure(null);
      setRecentScansState("loading");
      try {
        const historyResult = await listAccountScanRuns(20);
        if (cancelled) return;
        if (historyResult?.ok !== true) {
          const failure = historyResult?.ok === false
            ? historyResult
            : customerRecoveryFailure({ error_code: "result_load_failed" }, "history:account");
          setRecentScans([]);
          setRecentScansFailure(failure);
          setRecentScansState(failure.kind);
          return;
        }
        setRecentScans((historyResult.runs || []).map(toRecentScanSummary).filter(Boolean));
        setRecentScansFailure(null);
        setRecentScansState("loaded");
      } catch (error) {
        if (cancelled) return;
        const failure = customerRecoveryFailure(error, "history:account");
        console.warn("Saved scan history read failed.", failure.kind, failure.support_reference);
        setRecentScans([]);
        setRecentScansFailure(failure);
        setRecentScansState(failure.kind);
      }
    }

    function clearRecentScans(event) {
      cancelled = true;
      setRecentScans([]);
      const reason = String(event?.detail?.reason || "");
      if (["auth_expired", "session_cleared"].includes(reason)) {
        const failure = customerRecoveryFailure({ error_code: "unauthorized" }, "history:session");
        setRecentScansFailure(failure);
        setRecentScansState(failure.kind);
        return;
      }
      setRecentScansFailure(null);
      setRecentScansState("idle");
    }

    loadRecentScans();
    window.addEventListener(CUSTOMER_BOUNDARY_EVENT, clearRecentScans);
    return () => {
      cancelled = true;
      window.removeEventListener(CUSTOMER_BOUNDARY_EVENT, clearRecentScans);
    };
  }, [requestedScanId, historyReloadToken]);

  const recommendations = useMemo(() => prepareCustomerFixes(
    mergeMetaDescriptionRecommendations(
      getRecommendations(scanRecord).map((item) => normalizeRecommendation(item, scanRecord)),
    ).map(applyCustomerVocabulary),
  ), [scanRecord]);
  const pages = useMemo(() => getPages(scanRecord), [scanRecord]);
  const healthScore = getHealthScore(scanRecord);
  const scoreUnavailable = isHealthScoreUnavailable(scanRecord);
  const pagesScanned = getPagesScanned(scanRecord, pages);
  const pagesFound = getPagesFound(scanRecord);
  const locked = scanRecord?.customer_access === "locked";
  // An authoritative result and a verified limited result are both readable;
  // only the first is authoritative. Keeping them as two conditions rather than
  // relaxing one is what stops a provisional scan from being read as complete.
  const hasAuthoritativeScan = Boolean(
    scanRecord
    && scanRecord.authority_verified === true
    && scanRecord.status === "complete"
    && scanRecord.release_gate_eligible === true
    && scanRecord.is_authoritative === true
    && scanRecord.score_is_provisional !== true
    && scanRecord.evidence_quality_blocking !== true
  );
  const hasVerifiedLimitedScan = Boolean(
    scanRecord
    && scanRecord.result_integrity_verified === true
    && scanRecord.status === "limited"
    && scanRecord.release_gate_eligible !== true
    && scanRecord.authority_verified !== true
    && (scanRecord.recommendations?.length || 0) > 0
  );
  const hasUsefulScan = hasAuthoritativeScan || hasVerifiedLimitedScan;
  const noHighConfidenceFindings = isNoHighConfidenceFindings(scanRecord, recommendations);
  const nextBestStep = getNextBestStep(scanRecord, noHighConfidenceFindings);
  const websiteKey = websiteKeyOf(scanRecord);
  const websiteHost = safeHostname(scanRecord?.website_url) || websiteKey || "";

  // Until customer workflow state has a durable, authorized mutation path,
  // every saved recommendation remains part of the reloadable work surface.
  const active = recommendations;
  const repairWorkSurface = buildRepairWorkSurfacePresentation({
    snapshotItems: recommendations,
    visibleItems: active,
    scan: scanRecord,
    initialFixFirstLimit: 3,
  });
  const repairPresentation = repairWorkSurface.presentation;
  const customerRepairCards = useMemo(
    () => repairPresentation.canonical === true ? buildRepairCards(active) : [],
    [active, repairPresentation.canonical],
  );
  const displayedRepairCount = repairPresentation.canonical === true ? customerRepairCards.length : active.length;
  const legacyActive = repairPresentation.canonical || repairPresentation.unsupported ? [] : repairPresentation.legacyItems;
  const topPriorities = legacyActive.slice(0, 3);
  const remaining = legacyActive.slice(3);
  const moreImportant = remaining.filter((item) => priorityBucket(item.priority) === "fix_first");
  const improveNext = remaining.filter((item) => priorityBucket(item.priority) === "improve_next");
  const worthChecking = remaining.filter((item) => priorityBucket(item.priority) === "worth_checking");
  const shownTopPriorities = topPriorities;
  const limitationNote = getLimitationNote(scanRecord);
  const summaryItems = repairPresentation.canonical === true ? customerRepairCards : recommendations;
  const summary = hasUsefulScan ? getBestSummary(scanRecord, pagesScanned, pagesFound, summaryItems) : "";
  const sampleCoverage = hasUsefulScan ? samplingDisclosure(scanRecord) : null;
  const focusedSections = useMemo(
    () => hasAuthoritativeScan
      && !String(scanRecord?.scope_type || "").trim()
      && !String(scanRecord?.path_prefix || scanRecord?.requested_path_prefix || "").trim()
      ? focusedPathSections(scanRecord)
      : [],
    [hasAuthoritativeScan, scanRecord],
  );

  function retryRequestedScan() {
    setRequestedScanFailure(null);
    if (!scanRecord) setRequestedScanState("loading");
    setReloadToken((value) => value + 1);
  }

  async function handleDeleteScan(projectId, scanId) {
    setDeletingScanId(scanId);
    const result = await deleteScanRun(projectId, scanId);
    setDeletingScanId("");
    if (result.ok) setRecentScans((scans) => scans.filter((scan) => scan.id !== scanId));
  }

  function retryRecentScans() {
    setRecentScansFailure(null);
    setRecentScansState("loading");
    setHistoryReloadToken((value) => value + 1);
  }

  function handleRecoveryAction(action, target) {
    if (action === "retry") {
      if (target === "history") retryRecentScans();
      else retryRequestedScan();
      return;
    }
    if (action === "login") {
      navigate("/login", { replace: true });
      return;
    }
    if (action === "history") {
      navigate("/dashboard", { replace: true });
      return;
    }
    if (action === "new_scan") navigate("/onboarding");
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

        {requestedScanId && scanRecord && requestedScanFailure?.retryable === true ? (
          <CustomerRecoveryNotice failure={requestedScanFailure} onRetry={retryRequestedScan} />
        ) : null}

        {!requestedScanId ? (
          <RecentScansState
            scans={recentScans}
            state={recentScansState}
            failure={recentScansFailure}
            onAction={(action) => handleRecoveryAction(action, "history")}
            onScan={() => navigate("/onboarding")}
            onDelete={handleDeleteScan}
            deletingScanId={deletingScanId}
          />
        ) : requestedScanState === "loading" && !scanRecord ? (
          <RequestedScanState title="Loading this scan…" detail="FixList is reopening the exact saved scan from your account." />
        ) : requestedScanFailure && !scanRecord ? (
          <CustomerRecoveryState
            failure={requestedScanFailure}
            target="scan"
            onAction={(action) => handleRecoveryAction(action, "scan")}
          />
        ) : locked ? (
          <LockedResultState />
        ) : scanRecord && !hasUsefulScan ? (
          <RequestedScanState
            title={getDurableScanStateTitle(scanRecord)}
            detail={getDurableScanStateDetail(scanRecord)}
            reference={scanRecord.scan_id || scanRecord.id}
          />
        ) : hasUsefulScan ? (
          <>
            <p className="mt-16 text-[13px] text-ink-faint tabular-nums">
              Scanned {scanRecord?.created_at ? formatDate(scanRecord.created_at) : "recently"}
              {pagesFound > 0 ? ` · ${formatCount(pagesFound)} pages found` : ""}
              {pagesScanned > 0 ? ` · ${formatCount(pagesScanned)} checked` : ""}
            </p>

            <div className="mt-4 flex items-center gap-7">
              <ScoreRing score={healthScore} unavailable={scoreUnavailable} />
              <div>
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
                  {customerHealthLabel(healthScore, { unavailable: scoreUnavailable, noHighConfidenceFindings })}
                </h1>
                <p className="mt-1.5 text-[15px] text-ink-muted tabular-nums">
                  {getHeroSub({ noHighConfidenceFindings, nextBestStep, activeCount: displayedRepairCount })}
                </p>
              </div>
            </div>

            {summary ? (
              <p className="mt-8 max-w-[56ch] text-[14px] leading-relaxed text-ink-muted">{summary}</p>
            ) : null}

            {sampleCoverage ? (
              <details className="mt-5 max-w-[60ch] rounded-xl border border-hairline-soft bg-white/35 px-4 py-3">
                <summary className="cursor-pointer text-[12.5px] font-medium text-ink-muted underline decoration-hairline underline-offset-4">
                  What this representative sample covered
                </summary>
                <div className="mt-3 space-y-2 text-[12.5px] leading-relaxed text-ink-faint">
                  <p>
                    Route patterns: <span className="font-medium text-ink-muted">{sampleCoverage.routesSampled} of {sampleCoverage.routesDiscovered}</span>
                    {sampleCoverage.localeVariantsCollapsed > 0
                      ? ` · ${formatCount(sampleCoverage.localeVariantsCollapsed)} translated duplicate${sampleCoverage.localeVariantsCollapsed === 1 ? "" : "s"} collapsed for sampling`
                      : ""}
                  </p>
                  {sampleCoverage.identityDiscovered > 0 ? (
                    <p>
                      Business-critical pages: <span className="font-medium text-ink-muted">{sampleCoverage.identitySampled} of {sampleCoverage.identityDiscovered}</span> sampled.
                    </p>
                  ) : null}
                  {sampleCoverage.marketSummary ? <p>{sampleCoverage.marketSummary}</p> : null}
                  {sampleCoverage.familySummary ? <p>{sampleCoverage.familySummary}</p> : null}
                  {sampleCoverage.unsampledSummary ? (
                    <p className="text-ink-muted">{sampleCoverage.unsampledSummary}</p>
                  ) : null}
                  <p>This is a representative 150-page sample unless FixList covered the full discovered inventory.</p>
                </div>
              </details>
            ) : null}

            {focusedSections.length > 0 ? (
              <section className="mt-6 max-w-[60ch] rounded-2xl border border-hairline-soft bg-white/45 px-5 py-5" aria-labelledby="site-sections-discovered">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 id="site-sections-discovered" className="text-[17px] font-semibold tracking-tight text-ink">
                    Site sections discovered
                  </h2>
                  <span className="text-[11px] uppercase tracking-[0.08em] text-ink-faint">Optional</span>
                </div>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
                  This site is larger than one Standard 150 scan. You can give an underrepresented folder its own separate 150-page scan without mixing it into this FixList.
                </p>
                <div className="mt-4 divide-y divide-hairline-soft">
                  {focusedSections.map((section) => {
                    const coveragePercent = Math.round(section.coverage * 100);
                    const target = focusedSectionOnboardingPath(scanRecord?.scan_id || scanRecord?.id, section);
                    return (
                      <div key={section.requested_path_prefix} className="flex flex-col gap-3 py-4 first:pt-1 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                            <span className="text-[13px] font-medium text-ink">{section.label}</span>
                            <span className="break-all text-[12px] text-ink-faint">{displayPathPrefix(section.requested_path_prefix)}</span>
                          </div>
                          <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">
                            {formatCount(section.discovered)} discovered · {formatCount(section.sampled)} sampled · {coveragePercent}% represented
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => target && navigate(target)}
                          disabled={!target}
                          className="shrink-0 self-start rounded-full border border-hairline px-3.5 py-2 text-[12px] font-medium text-ink transition-colors hover:bg-ink/[0.035] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          Scan this section separately
                        </button>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
                  Focused scans stay on this exact website origin and inside the selected folder. Subdomain scanning is not enabled in this release.
                </p>
              </section>
            ) : null}

            {limitationNote ? (
              <p className="mt-6 border-l-2 border-warnink/40 pl-3 text-[13.5px] leading-relaxed text-ink-muted">{limitationNote}</p>
            ) : null}

            {repairPresentation.unsupported ? (
              <div className="mt-12 rounded-2xl border border-hairline-soft bg-white/40 px-5 py-6">
                <h2 className="text-[20px] font-semibold tracking-tight">We can&rsquo;t safely display this saved FixList</h2>
                <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
                  This saved scan uses a repair format this interface does not understand. No browser-ranked substitute is being shown. Run a fresh scan to create a compatible FixList.
                </p>
              </div>
            ) : repairPresentation.canonical === true ? (
              <CustomerRepairList cards={customerRepairCards} />
            ) : (
              <RepairWorkSurface
                {...repairWorkSurface}
                renderRow={({ item, suggestion }) => (
                  <FixRow
                    key={item.id}
                    item={item}
                    suggestion={suggestion}
                    cms={selectedCms}
                    embedded
                  />
                )}
              />
            )}

            {repairPresentation.legacySections?.length === 0 && shownTopPriorities.length > 0 ? (
              <>
                <SectionEyebrow label="Your priorities" count={shownTopPriorities.length} />
                <div className="mt-2">
                  {shownTopPriorities.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} />
                  ))}
                </div>
              </>
            ) : null}

            {repairPresentation.legacySections?.length === 0 && moreImportant.length > 0 ? (
              <>
                <SectionEyebrow label="More important fixes" count={moreImportant.length} />
                <div className="mt-2">
                  {moreImportant.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} />
                  ))}
                </div>
              </>
            ) : null}

            {repairPresentation.legacySections?.length === 0 && improveNext.length > 0 ? (
              <>
                <SectionEyebrow label="Improve next" count={improveNext.length} />
                <div className="mt-2">
                  {improveNext.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} />
                  ))}
                </div>
              </>
            ) : null}

            {repairPresentation.legacySections?.length === 0 && worthChecking.length > 0 ? (
              <>
                <SectionEyebrow label="Worth checking" count={worthChecking.length} />
                <div className="mt-2">
                  {worthChecking.map((item) => (
                    <FixRow key={item.id} item={item} cms={selectedCms} />
                  ))}
                </div>
              </>
            ) : null}

            <ExplicitPassedChecks scan={scanRecord} />

            {active.length > 0 && repairPresentation.canonical !== true ? <CmsPicker selectedCms={selectedCms} onChange={setSelectedCms} /> : null}
          </>
        ) : (
          <NoScanState onScan={() => navigate("/onboarding")} />
        )}

        <footer className="mt-24 border-t border-hairline-soft pt-5 text-[12px] leading-relaxed text-ink-faint">
          {hasUsefulScan
            ? `FixList checked ${pagesScanned} pages of your site this scan. Some checks depend on how your site behaves for Google over time, so a perfect score isn't the goal — a shorter list is.`
            : "FixList checks the most important pages of your site and turns what it finds into a short, plain-English list."}
        </footer>
      </div>
    </div>
  );
}

const CUSTOMER_REPAIR_SECTIONS = Object.freeze([
  { key: "fix_first", label: "Fix first", help: "Start here." },
  { key: "important", label: "Important", help: "Significant repairs to tackle next." },
  { key: "improve", label: "Improve next", help: "Useful improvements after the important work." },
  { key: "review", label: "Worth checking", help: "Lower-priority items to review when ready." },
]);

function customerRepairSectionKey(card = {}) {
  const key = priorityBucket(card);
  return CUSTOMER_REPAIR_SECTIONS.some((section) => section.key === key) ? key : "review";
}

function customerEvidenceClassLabel(value = "") {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "confirmed_problem") return "Confirmed problem";
  if (normalized === "improvement") return "Improvement";
  if (normalized === "recommendation") return "Recommendation";
  return "";
}

function CustomerRepairList({ cards = [] }) {
  const list = Array.isArray(cards) ? cards.filter(Boolean) : [];
  if (list.length === 0) return null;

  const sections = CUSTOMER_REPAIR_SECTIONS
    .map((section) => ({
      ...section,
      cards: list.filter((card) => customerRepairSectionKey(card) === section.key),
    }))
    .filter((section) => section.cards.length > 0);

  return (
    <div className="mt-10 sm:mt-12" aria-labelledby="customer-fixlist-heading">
      <div className="mb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="customer-fixlist-heading" className="text-[20px] font-semibold tracking-tight text-ink">
            Your FixList
          </h2>
          <span className="shrink-0 text-[12px] tabular-nums text-ink-faint">
            {list.length} remaining
          </span>
        </div>
        <p className="mt-1.5 max-w-[52ch] text-[12px] leading-relaxed text-ink-faint">
          Work through these actions in order. Open the evidence only when you need the affected URLs or technical detail.
        </p>
      </div>

      {sections.map((section) => (
        <section key={section.key} className="mt-10 first:mt-0 sm:mt-12" aria-labelledby={`customer-repair-section-${section.key}`}>
          <div className="flex items-baseline justify-between gap-4">
            <h3 id={`customer-repair-section-${section.key}`} className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
              {section.label}
            </h3>
            <span className="text-[11px] tabular-nums text-ink-faint">
              {section.cards.length} {section.cards.length === 1 ? "repair" : "repairs"}
            </span>
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">{section.help}</p>
          <div className="mt-1.5">
            {section.cards.map((card, index) => (
              <CustomerRepairCard key={card.evidence?.mergedFromFixIds?.join("|") || `${section.key}-${index}`} card={card} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function CustomerRepairCard({ card = {} }) {
  const pages = Array.isArray(card?.evidence?.affectedPages) ? card.evidence.affectedPages.filter(Boolean) : [];
  const reportedCount = Math.max(Number(card?.evidence?.pageCount || 0), pages.length);
  const evidenceLabel = customerEvidenceClassLabel(card.evidenceClass);

  return (
    <article className="border-b border-hairline-soft py-6 first:pt-5">
      <div className="flex flex-wrap items-start justify-between gap-x-5 gap-y-2">
        <div className="min-w-0 flex-1">
          <h4 className="text-[17px] font-medium leading-snug tracking-tight text-ink">{card.title}</h4>
          <p className="mt-1 text-[12px] font-medium text-ink-faint">
            {card.customerCategory}
            {evidenceLabel ? ` · ${evidenceLabel}` : ""}
          </p>
        </div>
        {reportedCount > 0 ? (
          <span className="shrink-0 text-[12px] tabular-nums text-ink-faint">
            {reportedCount} {reportedCount === 1 ? "page" : "pages"}
          </span>
        ) : null}
      </div>

      <dl className="mt-5 space-y-4">
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Why it matters</dt>
          <dd className="mt-1 max-w-[58ch] text-[14px] leading-relaxed text-ink-muted">{card.whyItMatters}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Where</dt>
          <dd className="mt-1 max-w-[58ch] text-[14px] leading-relaxed text-ink-muted">{card.where}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">What to change</dt>
          <dd className="mt-1 max-w-[58ch] text-[14px] leading-relaxed text-ink">{card.whatToChange}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-faint">
        <span><span className="font-medium text-ink-muted">Who:</span> {card.who}</span>
        {card.effort ? <span><span className="font-medium text-ink-muted">Effort:</span> {card.effort}</span> : null}
      </div>

      <details className="mt-4 max-w-[60ch]">
        <summary className="cursor-pointer text-[12.5px] font-medium text-ink-muted underline decoration-hairline underline-offset-4">
          View affected URLs &amp; evidence
        </summary>
        <div className="mt-3 rounded-lg border border-hairline-soft bg-white/40 px-3 py-3">
          {card.technicalLabel ? (
            <p className="text-[12px] leading-relaxed text-ink-faint">
              Check: <span className="text-ink-muted">{card.technicalLabel}</span>
            </p>
          ) : null}
          {reportedCount > 0 ? (
            <p className={`${card.technicalLabel ? "mt-1.5 " : ""}text-[12px] leading-relaxed text-ink-faint`}>
              {reportedCount} affected {reportedCount === 1 ? "page" : "pages"}.
              {pages.length < reportedCount
                ? ` This saved result contains ${pages.length} of those URLs in its evidence list.`
                : ""}
            </p>
          ) : null}
          {pages.length > 0 ? (
            <ul className="mt-3 max-h-64 space-y-1.5 overflow-y-auto pr-1 text-[12px] text-ink-muted">
              {pages.map((page) => (
                <li key={page} className="break-all">{page}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-faint">
              No affected URL list was persisted for this repair.
            </p>
          )}
        </div>
      </details>
    </article>
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

function RequestedScanState({ title, detail, reference = "" }) {
  return (
    <div className="mt-16 rounded-2xl border border-hairline-soft bg-white p-6">
      <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">{detail}</p>
      {reference ? <p className="mt-4 text-[12px] text-ink-faint">Scan reference: <span className="font-mono tabular-nums">{reference}</span></p> : null}
    </div>
  );
}

function CustomerRecoveryState({ failure, target, onAction }) {
  const copy = resolveRecoveryCopy(failure?.kind, target);
  const actionLabel = recoveryActionLabel(copy.action, target);
  return (
    <div className="mt-16 rounded-2xl border border-hairline-soft bg-white p-6">
      <h1 className="text-[22px] font-semibold tracking-tight">{copy.title}</h1>
      <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">{copy.detail}</p>
      {actionLabel ? (
        <button
          type="button"
          onClick={() => onAction(copy.action)}
          className="mt-5 rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-paper transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          {actionLabel}
        </button>
      ) : null}
      {failure?.support_reference ? (
        <p className="mt-4 text-[12px] text-ink-faint">
          Support reference: <span className="font-mono tabular-nums">{failure.support_reference}</span>
        </p>
      ) : null}
    </div>
  );
}

function CustomerRecoveryNotice({ failure, onRetry }) {
  const copy = CUSTOMER_RECOVERY_COPY[failure?.kind] || CUSTOMER_RECOVERY_COPY.load_failed;
  return (
    <div className="mt-6 rounded-xl border border-hairline-soft bg-white px-4 py-3" role="status">
      <p className="text-[13px] font-medium text-ink">{copy.title}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-ink-muted">
        The last verified result remains visible. Support reference: <span className="font-mono tabular-nums">{failure.support_reference}</span>
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 text-[12px] font-medium text-ink underline decoration-hairline underline-offset-4 hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        Retry loading this scan
      </button>
    </div>
  );
}

function recoveryActionLabel(action, target) {
  if (action === "retry") return target === "history" ? "Retry loading saved scans" : "Retry loading this scan";
  if (action === "login") return "Sign in again";
  if (action === "history") return "View saved scans";
  if (action === "new_scan") return "Run a fresh scan";
  return "";
}

function RecentScansState({ scans, state, failure, onAction, onScan, onDelete, deletingScanId }) {
  if (state === "loading") {
    return <RequestedScanState title="Loading your scans…" detail="FixList is checking your account for saved scans." />;
  }

  if (failure) return <CustomerRecoveryState failure={failure} target="history" onAction={onAction} />;

  if (scans.length === 0) return <NoScanState onScan={onScan} />;

  return (
    <section className="mt-16" aria-labelledby="recent-scans-heading">
      <h1 id="recent-scans-heading" className="text-[26px] font-semibold leading-tight tracking-tight">Recent scans</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
        Reopen a saved scan to see its current status or verified FixList.
      </p>
      <div className="mt-6 overflow-hidden rounded-2xl border border-hairline-soft bg-white">
        {orderRecentScansWithChildren(scans).map((scan) => (
          <RecentScanRow
            key={scan.id}
            scan={scan}
            status={getRecentScanStatus(scan.status)}
            occurredLabel={scan.occurredAt ? formatDate(scan.occurredAt) : "Date unavailable"}
            deleting={deletingScanId === scan.id}
            onDelete={onDelete}
            child={Boolean(scan.parent_scan_id)}
          />
        ))}
      </div>
      <p className="mt-3 text-[12px] text-ink-faint">
        Showing up to 20 recent scans across your websites. You can delete a finished scan from this list.
      </p>
    </section>
  );
}

function toRecentScanSummary(run = {}) {
  const id = String(run.id || "").trim();
  if (!id) return null;
  const scopeType = String(run.scope_type || "").trim();
  const pathPrefix = String(run.requested_path_prefix || run.path_prefix || "").trim();
  return {
    id: id,
    project_id: String(run.project_id || ""),
    website: safeHostname(run.website_url || run.submitted_url || run.final_url) || "Website scan",
    status: String(run.status || "").trim().toLowerCase(),
    scope_type: scopeType,
    parent_scan_id: String(run.parent_scan_id || "").trim(),
    requested_path_prefix: pathPrefix,
    scopeLabel: scopeType === "path_prefix" && pathPrefix ? `Focused · ${displayPathPrefix(pathPrefix)}` : "",
    occurredAt: run.queued_at || run.created_date || run.created_at || run.started_at || run.reviewing_at || run.completed_at || "",
  };
}

function orderRecentScansWithChildren(scans = []) {
  const rows = Array.isArray(scans) ? scans.filter(Boolean) : [];
  const byId = new Map(rows.map((scan) => [scan.id, scan]));
  const children = new Map();
  for (const scan of rows) {
    const parentId = String(scan.parent_scan_id || "").trim();
    if (!parentId || !byId.has(parentId)) continue;
    if (!children.has(parentId)) children.set(parentId, []);
    children.get(parentId).push(scan);
  }
  for (const list of children.values()) {
    list.sort((a, b) => Date.parse(b.occurredAt || 0) - Date.parse(a.occurredAt || 0));
  }
  const emitted = new Set();
  const output = [];
  for (const scan of rows) {
    if (emitted.has(scan.id) || (scan.parent_scan_id && byId.has(scan.parent_scan_id))) continue;
    output.push(scan);
    emitted.add(scan.id);
    for (const child of children.get(scan.id) || []) {
      output.push(child);
      emitted.add(child.id);
    }
  }
  for (const scan of rows) {
    if (!emitted.has(scan.id)) output.push(scan);
  }
  return output;
}

function getRecentScanStatus(status) {
  if (status === "queued") return { label: "Queued", active: true };
  if (status === "crawling") return { label: "Scanning", active: true };
  if (status === "reviewing") return { label: "Preparing FixList", active: true };
  if (status === "complete") return { label: "Completed", active: false };
  if (status === "failed") return { label: "Failed", active: false };
  if (status === "limited") return { label: "Limited", active: false };
  if (status === "cancelled") return { label: "Cancelled", active: false };
  return { label: "Saved", active: false };
}

function LockedResultState() {
  return (
    <div className="mt-16 rounded-2xl border border-hairline-soft bg-white p-6">
      <h1 className="text-[22px] font-semibold tracking-tight">Your saved result is locked</h1>
      <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
        Activate Standard 150 beta access for {UNLOCK_PRICE_LABEL} to open verified fixes and run scans. Result details stay on the server until access is confirmed.
      </p>
      <div className="mt-5">
        <UnlockAccessButton />
      </div>
    </div>
  );
}

function FixRow({ item, cms, embedded = false, suggestion: suppliedSuggestion }) {
  const [open, setOpen] = useState(embedded);
  // The presentation seam already computed this for canonical rows. Legacy rows
  // reach the same deterministic suggestion here rather than going without one.
  const suggestion = useMemo(
    () => suppliedSuggestion || repairSuggestion(item),
    [suppliedSuggestion, item],
  );
  const [showAllPages, setShowAllPages] = useState(false);
  const [copied, setCopied] = useState(false);
  const severe = item.priority === "critical" || item.priority === "high";
  const cmsSteps = getCmsSteps(cms, item);
  const evidenceItems = buildEvidenceItems(item).slice(0, 4);
  const availableCount = item.affectedPages.length;
  const reportedCount = Math.max(Number(item.pageCount || 0), availableCount);
  const shownPages = showAllPages ? item.affectedPages : item.affectedPages.slice(0, 8);
  const extraCount = Math.max(0, availableCount - shownPages.length);

  async function copyAffectedUrls() {
    try {
      const text = item.affectedPages.map((page) => toAbsolutePageUrl(page, item.websiteUrl)).join("\n");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.warn("Could not copy affected URLs.", error);
    }
  }

  function downloadAffectedUrls() {
    const rows = item.affectedPages.map((page) => [
      toAbsolutePageUrl(page, item.websiteUrl),
      item.title,
      item.rule,
      item.priority,
      item.templateFamily,
    ]);
    const csv = [
      ["affected_url", "finding", "rule", "priority", "template_family"],
      ...rows,
    ].map((row) => row.map(csvCell).join(",")).join("\n");
    const host = safeHostname(item.websiteUrl) || "website";
    const rule = String(item.rule || "finding").replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
    downloadTextFile(csv, `fixlist-${host}-${rule || "finding"}-urls.csv`, "text/csv;charset=utf-8");
  }

  return (
    <div className={embedded ? "border-b-0" : "border-b border-hairline-soft"}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={embedded ? "hidden" : "flex w-full items-start gap-3.5 py-5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"}
      >
        <span className={`mt-[7px] h-[7px] w-[7px] shrink-0 rounded-full ${severe ? "bg-crit" : "bg-warnink"}`} />
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-medium tracking-tight">{item.title}</span>
          <span className="mt-1 block text-[12px] font-medium text-ink-faint">
            {customerPriorityLabel(item.priority)} · {item.customerCategory}
            {reportedCount > 0 ? ` · ${reportedCount} ${reportedCount === 1 ? "page" : "pages"}` : ""}
          </span>
          <span className="mt-1 block text-[13.5px] text-ink-muted">{clampText(item.explanation, 140)}</span>
        </span>
        <span className="mt-0.5 flex shrink-0 items-center gap-3">
          <span className="hidden text-[12px] text-ink-faint sm:block">{item.needsHelp ? "Web developer" : "You"}</span>
          <span className={`text-[12px] leading-none text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        </span>
      </button>

      {open ? (
        <div className={embedded ? "pb-1 text-[14px] text-ink-muted" : "pb-6 pl-[21px] text-[14px] text-ink-muted"}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Why this matters</div>
          <p className="mt-1 max-w-[56ch]">{item.whyItMatters}</p>

          {evidenceItems.length > 0 ? (
            <details className="mt-5 max-w-[60ch] rounded-lg border border-hairline-soft px-3 py-2.5">
              <summary className="cursor-pointer text-[12.5px] font-medium text-ink-muted">Technical details</summary>
              <p className="mt-2 text-[12.5px] leading-relaxed text-ink-faint">
                {evidenceItems.map((entry) => `${entry.label}: ${entry.value}`).join(" · ")}
              </p>
            </details>
          ) : null}

          {item.groupingExplanation ? (
            <>
              <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Why these pages are grouped</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">{item.groupingExplanation}</p>
            </>
          ) : null}

          {embedded ? (
            suggestion.bestApproach ? (
              <>
                <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">How to approach it</div>
                <p className="mt-1 max-w-[56ch] text-[13.5px] leading-relaxed">{suggestion.bestApproach}</p>
              </>
            ) : null
          ) : (
            <SuggestedFix suggestion={suggestion} />
          )}

          {cmsSteps.length > 0 ? (
            <>
              <div className="mt-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">What to do</div>
              <details className="mt-2 max-w-[60ch]">
                <summary className="cursor-pointer text-[13px] font-medium text-ink-muted underline decoration-hairline underline-offset-4">Step-by-step instructions</summary>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-ink">
                  {cmsSteps.map((step, index) => <li key={`${step}-${index}`} className="pl-1 leading-relaxed">{step}</li>)}
                </ol>
              </details>
            </>
          ) : null}

          {reportedCount > 0 ? (
            <>
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
                  Affected pages <span className="font-normal tabular-nums">{availableCount}{reportedCount > availableCount ? ` of ${reportedCount}` : ""}</span>
                </div>
                {availableCount > 0 ? (
                  <div className="flex flex-wrap items-center gap-3 text-[12px]">
                    <button type="button" onClick={copyAffectedUrls} className="flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink">
                      <Copy className="h-3.5 w-3.5" />
                      {copied ? "Copied" : "Copy page list"}
                    </button>
                    <button type="button" onClick={downloadAffectedUrls} className="flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink">
                      <Download className="h-3.5 w-3.5" />
                      Download CSV
                    </button>
                  </div>
                ) : null}
              </div>

              {reportedCount > availableCount ? (
                <p className="mt-2 max-w-[60ch] rounded-md bg-warnink/[0.07] px-3 py-2 text-[12.5px] leading-relaxed text-ink-muted">
                  This saved result contains {availableCount} of {reportedCount} affected pages. Run a fresh scan after the update is published to capture the complete list.
                </p>
              ) : null}

              {item.excludedEvidenceCount > 0 ? (
                <p className="mt-2 max-w-[60ch] text-[12.5px] text-ink-faint">
                  {item.excludedEvidenceCount} non-HTML or system URL{item.excludedEvidenceCount === 1 ? " was" : "s were"} excluded from this customer-facing list.
                </p>
              ) : null}

              {shownPages.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {shownPages.map((page, index) => (
                    <AffectedPage key={`${page}-${index}`} page={page} websiteUrl={item.websiteUrl} index={index} />
                  ))}
                  {extraCount > 0 ? (
                    <button type="button" onClick={() => setShowAllPages(true)} className="mt-1 text-[13px] font-medium text-ink underline decoration-hairline underline-offset-4">
                      Show all {availableCount} pages
                    </button>
                  ) : null}
                  {showAllPages && availableCount > 8 ? (
                    <button type="button" onClick={() => setShowAllPages(false)} className="mt-1 text-[13px] text-ink-muted underline decoration-hairline underline-offset-4">
                      Show fewer pages
                    </button>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : null}

        </div>
      ) : null}
    </div>
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

function AffectedPage({ page, websiteUrl, index }) {
  // One shared contract decides how a page reads and whether it may be a link,
  // so a card, a modal and an export cannot describe the same page differently.
  const link = evidenceLink(page, websiteUrl);
  const host = formatPageLabel(link.href || page);
  const showHost = link.isLinkable && cleanString(host) !== cleanString(link.label);

  return (
    <div className="flex items-start gap-2 rounded-md border border-hairline-soft px-2.5 py-2 text-[13px] tabular-nums">
      <span className="mt-0.5 w-5 shrink-0 text-right text-[11px] text-ink-faint">{index + 1}</span>
      <div className="min-w-0 flex-1">
        {link.isLinkable ? (
          // The label itself is the link: the audit found evidence rendered as
          // plain text with only a small icon to click.
          <a
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            title={link.title}
            aria-label={link.linkName}
            className="block truncate font-medium text-ink underline decoration-hairline underline-offset-4 transition-colors hover:text-ink"
          >
            {link.label}
          </a>
        ) : (
          <p className="truncate font-medium text-ink" title={link.title}>{link.label}</p>
        )}
        {showHost ? <p className="break-all text-ink-faint">{host}</p> : null}
      </div>
      {link.isLinkable ? (
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          title={link.title}
          className="shrink-0 p-1 text-ink-faint transition-colors hover:text-ink"
          aria-label={link.linkName}
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </div>
  );
}

function normalizeAffectedPageList(values) {
  return unique((values || []).map(String).filter(isUsableAffectedPageUrl));
}

function isUsableAffectedPageUrl(value) {
  const raw = String(value || "").trim();
  if (!raw || /^(?:mailto|tel|javascript|data):/i.test(raw)) return false;
  let pathname = raw;
  try {
    pathname = new URL(raw, "https://fixlist.invalid").pathname || "/";
  } catch {}
  if (/^\/cdn-cgi\//i.test(pathname)) return false;
  if (/\.(?:avif|bmp|css|csv|doc|docx|eot|gif|ico|jpe?g|js|json|map|mjs|mp3|mp4|mpeg|mov|ogg|otf|pdf|png|ppt|pptx|svg|tiff?|ttf|wav|webm|webp|woff2?|xls|xlsx|xml|zip)$/i.test(pathname)) return false;
  return raw.startsWith("/") || /^https?:\/\//i.test(raw);
}

function toAbsolutePageUrl(page, websiteUrl) {
  const raw = String(page || "").trim();
  if (!raw) return "";
  if (isFullUrl(raw)) return raw;
  try {
    return new URL(raw, websiteUrl || "https://fixlist.invalid").toString();
  } catch {
    return raw;
  }
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function downloadTextFile(content, filename, type) {
  const blob = new Blob([content], { type });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function getHeroSub({ noHighConfidenceFindings, nextBestStep, activeCount }) {
  if (noHighConfidenceFindings && activeCount === 0) {
    return nextBestStep || "No high-confidence issues were found in the pages we checked.";
  }
  const word = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"][activeCount] || activeCount;
  return `${word} fix${activeCount === 1 ? "" : "es"} to work through — start at the top.`;
}

function getLimitationNote(record) {
  if (isHealthScoreUnavailable(record)) return "We couldn't verify enough usable pages to calculate a reliable score. The access item below describes the scan limitation, not a confirmed on-page SEO defect.";
  const limitation = cleanString(record?.limitation);
  if (limitation) return limitation;
  if (record?.score_is_provisional === true) return "Scan coverage was limited, so this score is provisional. Fix what's below, then scan again for a fuller picture.";
  return "";
}

function websiteKeyOf(record) {
  const key = cleanString(record?.website_key);
  if (key) return key;
  return safeHostname(record?.website_url) || "";
}

function normalizeRecommendation(item = {}, scanRecord = {}) {
  const legacyBlocked429 = shouldUseLegacyRateLimitPresentation(scanRecord, item);
  const evidence = legacyBlocked429 ? extractRecommendationEvidence(item, scanRecord) : {};
  const priority = legacyBlocked429 ? blockedPriority(item, evidence) : normalizePriority(item.priority);
  const category = String(item.category || "other").toLowerCase();
  const rawAffectedPages = unique(firstArray([item.affected_pages, item.pages, item.page_urls]).map(String));
  const fallbackPage = item.page_url || item.url || rawAffectedPages[0] || "";
  const combinedPages = unique([...rawAffectedPages, ...(fallbackPage ? [String(fallbackPage)] : [])]);
  const affectedPages = normalizeAffectedPageList(combinedPages);
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
    rule: cleanString(item.rule || item.issue_type),
    category,
    priority,
    bucket,
    customerCategory,
    title,
    explanation,
    whyItMatters,
    recommendation,
    affectedPages,
    sourcePages: normalizeAffectedPageList(firstArray([item.source_pages, item.evidence?.source_pages])),
    pageCount: Math.max(Number(item.page_count || 0), affectedPages.length),
    excludedEvidenceCount: Math.max(0, combinedPages.length - affectedPages.length),
    websiteUrl: cleanString(scanRecord?.website_url || scanRecord?.raw?.scanner?.website_url),
    templateFamily: cleanString(item.page_template_family),
    currentValue: legacyBlocked429 ? "HTTP 429 — crawler was rate-limited or blocked" : cleanString(item.current_value || item.current || item.detected_value),
    pageType: legacyBlocked429 && evidence.scopeRelationship === "sibling_sous_dossier" ? "Related site section" : cleanString(item.page_type || item.page_value_label || item.business_importance),
    defectClass: legacyBlocked429 ? "Rate-limit / crawler access" : cleanString(item.primary_defect_class || item.meta_regeneration_gate),
    pageValueLabel: legacyBlocked429 ? evidence.businessValueLabel : cleanString(item.page_value_label),
    businessImportance: legacyBlocked429 ? evidence.businessImportance : cleanString(item.business_importance),
    metaGate: cleanString(item.meta_regeneration_gate),
    scopeRelationship: legacyBlocked429 ? evidence.scopeRelationship : cleanString(item.scope_relationship),
    pageScope: cleanString(item.page_scope),
    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    metadataStateCounts: normalizeMetadataStateCounts(item.metadata_state_counts),
    combinedRules: firstArray([item.combined_rules]).map(String),
    groupingExplanation: cleanString(item.grouping_explanation),
    needsHelp,
    estimatedTime: cleanString(item.estimated_time || item.time_estimate),
    confidenceScore: Number(item.confidence_score || 0),
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),
  };
}

const META_DESCRIPTION_GAP_RULES = new Set(["missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable"]);
const META_DESCRIPTION_STATE_BY_RULE = {
  missing_meta_description: "missing",
  empty_meta_description: "empty",
  malformed_meta_description: "malformed",
};

function hasVersionedRepairContract(item = {}) {
  const persisted = item?.original && typeof item.original === "object" ? item.original : item;
  return Boolean(
    cleanString(persisted?.repair_contract_version || persisted?.repairContractVersion)
      || cleanString(persisted?.repair_snapshot_contract_version || persisted?.repairSnapshotContractVersion),
  );
}

function hasExplicitSharedRepairConfirmation(item = {}) {
  const persisted = item?.original && typeof item.original === "object" ? item.original : item;
  const context = persisted?.priority_context || persisted?.priorityContext || {};
  return persisted?.shared_repair_confirmed === true
    || persisted?.sharedRepairConfirmed === true
    || context?.shared_repair_confirmed === true;
}

function normalizeMetadataStateCounts(value = {}) {
  const input = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(input.missing || 0)),
    empty: Math.max(0, Number(input.empty || input.present_empty || 0)),
    malformed: Math.max(0, Number(input.malformed || 0)),
  };
}

function metadataStateCountsForRecommendation(item = {}) {
  const existing = normalizeMetadataStateCounts(item.metadataStateCounts);
  if (existing.missing + existing.empty + existing.malformed > 0) return existing;
  const state = META_DESCRIPTION_STATE_BY_RULE[String(item.rule || "").toLowerCase()];
  if (!state) return existing;
  const count = Math.max(Number(item.pageCount || 0), item.affectedPages?.length || 0, 1);
  return { ...existing, [state]: count };
}

function addMetadataStateCounts(left = {}, right = {}) {
  const a = normalizeMetadataStateCounts(left);
  const b = normalizeMetadataStateCounts(right);
  return { missing: a.missing + b.missing, empty: a.empty + b.empty, malformed: a.malformed + b.malformed };
}

function metadataStateCountTotal(value = {}) {
  const counts = normalizeMetadataStateCounts(value);
  return counts.missing + counts.empty + counts.malformed;
}

function strongestPriority(left, right) {
  const rank = { critical: 4, high: 3, medium: 2, low: 1 };
  const a = normalizePriority(left);
  const b = normalizePriority(right);
  return (rank[b] || 0) > (rank[a] || 0) ? b : a;
}

function metaDescriptionFamilyLabel(family) {
  return String(family || "template").replace(/^activity_detail$/, "activity/detail").replace(/_/g, " ");
}

function metaDescriptionCopy(family) {
  const label = metaDescriptionFamilyLabel(family);
  return {
    title: `Add usable meta descriptions to ${label} pages`,
    explanation: "Some pages are missing the meta-description tag, while others output a blank or invalid value. Because these pages use the same page pattern, fix the shared template rather than editing every URL one by one.",
    why: "Meta descriptions often appear beneath page titles in search results. When one is missing or blank, search engines must create their own snippet from page content. That snippet may be less specific or persuasive, giving the site less control over how each page is presented and potentially reducing qualified clicks. Fixing the shared template improves many pages at once.",
    recommendation: "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
    grouping: `All affected URLs use the ${label} page pattern. One template correction may resolve the problem across the entire group.`,
  };
}

function mergeMetaDescriptionRecommendations(items = []) {
  const output = [];
  const groups = new Map();
  for (const item of items) {
    // Versioned repair snapshots already carry server-owned identity, grouping,
    // and canonical order. Legacy meta-description synthesis must never re-key
    // or merge those rows before the repair-contract gate sees them.
    if (hasVersionedRepairContract(item) || !META_DESCRIPTION_GAP_RULES.has(String(item.rule || "").toLowerCase())) {
      output.push(item);
      continue;
    }
    const family = item.templateFamily || "template";
    const key = `meta_description_unusable|${family}`;
    const copy = metaDescriptionCopy(family);
    const found = groups.get(key);
    if (!found) {
      const counts = metadataStateCountsForRecommendation(item);
      const merged = {
        ...item,
        id: stableId(key),
        rule: "meta_description_unusable",
        title: copy.title,
        explanation: copy.explanation,
        whyItMatters: copy.why,
        recommendation: copy.recommendation,
        groupingExplanation: copy.grouping,
        metadataStateCounts: counts,
        combinedRules: unique([...(item.combinedRules || []), item.rule].filter(Boolean)),
        pageCount: Math.max(item.affectedPages.length, metadataStateCountTotal(counts)),
      };
      groups.set(key, { index: output.length, item: merged });
      output.push(merged);
      continue;
    }
    const merged = found.item;
    merged.affectedPages = unique([...merged.affectedPages, ...item.affectedPages]);
    merged.sourcePages = unique([...merged.sourcePages, ...item.sourcePages]);
    merged.priority = strongestPriority(merged.priority, item.priority);
    merged.metadataStateCounts = addMetadataStateCounts(merged.metadataStateCounts, metadataStateCountsForRecommendation(item));
    merged.combinedRules = unique([...merged.combinedRules, ...(item.combinedRules || []), item.rule].filter(Boolean));
    merged.pageCount = Math.max(merged.affectedPages.length, metadataStateCountTotal(merged.metadataStateCounts));
    merged.needsHelp = merged.needsHelp || item.needsHelp;
    output[found.index] = merged;
  }
  return output;
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
    ? "Related section on the same parent domain"
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
  if (evidence.scopeRelationship === "sibling_sous_dossier") return "Check rate limiting on a related site section";
  if (evidence.affectedCount > 1) return "Check pages blocked by rate limiting";
  return "Check this HTTP 429 scan block";
}

function build429Explanation(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "The scanner hit HTTP 429 on a path under the same parent domain but outside the selected site section. This usually means a shared server, CDN, firewall, or bot-protection layer rate-limited the crawler.";
  }
  return "The page returned HTTP 429 during the scan. That usually means the server, CDN, firewall, or bot-protection layer rate-limited the crawler. Verify whether normal users and legitimate search crawlers can load it before treating it as a confirmed broken customer page.";
}

function build429Why(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "This is useful same-parent-domain access evidence, but it should not be described as part of the selected customer journey unless the crawl scope or source-page evidence proves it belongs there.";
  }
  return "Rate limiting can hide pages from crawlers if configured too aggressively. But a 429 is not the same as a confirmed broken page, so the next step is to verify crawler and user access rather than rewrite the page.";
}

function build429Recommendation(evidence) {
  if (evidence.scopeRelationship === "sibling_sous_dossier") {
    return "Ask your web person to review rate-limit and bot-protection rules for the parent domain and confirm whether this related site section should be part of the selected scan scope.";
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
      "Confirm whether this related site section should be included in the current scan scope or treated as parent-domain evidence only.",
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
  if (existing.length > 0) return existing.map(String).slice(0, 6);
  if (needsHelp) return ["Share this item and its affected-URL export with your web person.", "Ask them to apply the rule-specific change across every affected URL.", "Publish the fix and run FixList again."];

  const category = String(item.category || "").toLowerCase();
  if (category === "meta_title") return ["Open the affected page in your CMS.", "Write a shorter title that names the specific page, service, product, or tool.", "Put the most important phrase near the beginning and keep the brand at the end.", "Publish and run FixList again."];
  if (category === "meta_description") return ["Open the affected page's SEO settings.", "Write one concise description that says what the visitor can do on this page.", "Mention the main benefit or next step, not generic marketing copy.", "Publish and run FixList again."];
  if (category === "schema") return ["Choose the right schema type for the page, such as Organization, LocalBusiness, Product, FAQ, or Breadcrumb.", "Add the schema through your CMS, SEO plugin, theme, or developer.", "Validate the page with a structured data checker."];
  if (category === "canonical") return ["Open the affected page or template.", "Set the canonical URL to the clean official version of the page.", "Check that duplicate, filter, and tracking URLs point back to the official version."];
  return ["Open the affected page or shared template.", recommendation, "Publish the change and run FixList again."];
}

function getCmsSteps(cms, recommendation) {
  if (isBlocked429(recommendation.original)) {
    return [
      "Do not edit page copy first. This is a server, CDN, firewall, or bot-protection check.",
      "Use Copy all or Download CSV under Affected URLs and send the complete list to your web person.",
      "Ask them to check access logs for HTTP 429 or challenge responses on those URLs.",
      "Confirm whether Googlebot and normal users can access the pages, adjust rules only when legitimate access is blocked, then rescan.",
    ];
  }

  const specificSteps = getRuleSpecificSteps(recommendation);
  if (specificSteps.length > 0) return [getCmsOpeningStep(cms, recommendation), ...specificSteps].slice(0, 6);

  const existing = Array.isArray(recommendation.generalSteps) ? recommendation.generalSteps.filter(Boolean) : [];
  if (existing.length > 0) return [getCmsOpeningStep(cms, recommendation), ...existing].slice(0, 6);
  return [getCmsOpeningStep(cms, recommendation), recommendation.recommendation, "Publish the update and run FixList again to verify the issue is gone."];
}

function getRuleSpecificSteps(recommendation) {
  const rule = String(recommendation.rule || recommendation.original?.rule || "").toLowerCase();
  const category = String(recommendation.category || recommendation.original?.category || "").toLowerCase();

  if (rule === "internal_link_redirect") return [
    "Use Copy all or Download CSV under Affected URLs so none of the flagged links are missed.",
    "Search your CMS, navigation, templates, and codebase for each old URL and replace it with the final destination URL shown by the redirect evidence.",
    "Publish the changes, clear any site or CDN cache, and test a representative URL from each affected page family.",
    "Run FixList again; the internal-link redirect count should fall to zero.",
  ];
  if (rule === "sitemap_redirect") return [
    "Export the complete affected-URL list below.",
    "Replace every redirecting sitemap entry with the final 200-status canonical URL; do not leave the old URL in the XML sitemap.",
    "Regenerate the sitemap, open it directly to confirm the old URLs are gone, and resubmit it in Google Search Console.",
    "Run FixList again to verify no sitemap entries redirect.",
  ];
  if (rule === "sitemap_canonicalized_url") return [
    "Export the affected URLs below and identify the canonical destination for each one.",
    "Remove each non-preferred URL from the sitemap and add only its final self-canonical, indexable URL.",
    "Regenerate and resubmit the sitemap, then verify a sample in page source and Google Search Console.",
    "Run FixList again to confirm the conflict is resolved.",
  ];
  if (rule === "sitemap_indexability_conflict") return [
    "Export the full affected-URL list below.",
    "For each URL, choose one outcome: remove it from the sitemap if it should stay noindexed or blocked, or make it crawlable and indexable if it should rank.",
    "Regenerate the sitemap and confirm it contains only preferred, indexable URLs.",
    "Run FixList again to verify the sitemap and indexability settings agree.",
  ];
  if (rule === "redirect_chain") return [
    "Export the complete URL list and inspect the redirect path for each affected URL.",
    "Change the first redirect, internal links, and sitemap entries to point directly to the final destination, removing intermediate hops.",
    "Clear caches and verify each affected URL reaches the final page in no more than one redirect.",
    "Run FixList again to confirm the chains are gone.",
  ];
  if (rule === "redirect_destination_noindex") return [
    "Export every affected URL and review the destination page for each redirect.",
    "If the destination should rank, remove its noindex directive. If it should not rank, redirect to a relevant indexable page or remove the source link or sitemap entry.",
    "Verify the final destination returns 200, is crawlable, and has the intended indexability setting.",
    "Run FixList again to confirm the conflicting redirects are resolved.",
  ];
  if (/redirect_destination_(?:failed|blocked)/.test(rule)) return [
    "Export the full affected-URL list and test each redirect destination directly.",
    "Restore the intended destination or update the redirect to the closest relevant live, crawlable page.",
    "Update internal links and sitemap entries so they also point directly to the working destination.",
    "Run FixList again after deployment to verify every destination is available.",
  ];
  if (/broken|404|410/.test(rule) || category === "404_error") return [
    "Export the affected URLs and decide whether each page should be restored, redirected, or removed.",
    "Restore pages that should exist; otherwise add a 301 redirect to the closest relevant live page.",
    "Update or remove every internal link and sitemap entry that still references the broken URL.",
    "Test the URLs directly, then run FixList again.",
  ];
  if (/canonical/.test(rule) || category === "canonical") return [
    "Use the URL list below to identify whether this is one shared-template problem or a small number of page-specific settings.",
    "Add or correct one self-referencing canonical tag per public page using its clean final URL.",
    "Inspect rendered page source on representative URLs from every affected family and confirm exactly one correct canonical is present.",
    "Publish and run FixList again.",
  ];
  if (/missing_meta_description|empty_meta_description|malformed_meta_description|meta_description_unusable/.test(rule) || category === "meta_description") return [
    "Use the status breakdown and URL export below to confirm which page groups are missing the tag, outputting an empty value, or using invalid markup.",
    "In the shared <head> metadata template, identify the source field used for each page's description, such as a dedicated SEO field, activity summary, category, or database value.",
    "Output exactly one non-empty, page-specific, plain-text meta description. When the dedicated SEO field is blank, build a reliable fallback from the page title or activity name, category, location, and main benefit.",
    "Strip HTML, placeholder text, line breaks, and repeated whitespace, and make sure the description appears in the initial server-rendered page source.",
    "Check a representative URL from each reported status, publish the change, and run FixList again.",
  ];
  if (/title/.test(rule) || category === "meta_title") return [
    "Export the affected URLs and group pages that share the same title template.",
    "Update the page field or shared title template so each indexable page has a specific title describing its topic or offer.",
    "Check representative page source from each family and confirm the title is unique, clear, and not cut off.",
    "Publish and run FixList again.",
  ];
  if (/image_alt|missing_alt|alt_text/.test(rule) || category === "image_alt_text" || category === "alt_text") return [
    "Export the affected URLs and open one representative page from each page family.",
    "Update the CMS image field or shared image component so meaningful images receive short, specific alt text; keep decorative images empty.",
    "Verify several affected pages in rendered HTML to confirm the template change applied consistently.",
    "Publish and run FixList again.",
  ];
  if (/missing_h1|multiple_h1/.test(rule) || category === "thin_content") return [
    "Open a representative affected page and locate the shared heading field or template.",
    rule.includes("multiple") ? "Keep the main page title as the only H1 and change supporting headings to H2 or H3 without changing their visual style." : "Add one clear H1 that describes the page's main topic; keep supporting sections as H2 or H3.",
    "Check representative pages from every affected family, publish the change, and run FixList again.",
  ];
  if (/schema/.test(rule) || category === "schema") return [
    "Choose the schema type that matches the page, such as Organization, LocalBusiness, Product, FAQ, or BreadcrumbList.",
    "Implement it in the shared template, CMS plugin, or page settings using values that are visible and accurate on the page.",
    "Validate representative affected URLs with a structured-data testing tool, fix errors, then publish and rescan.",
  ];
  return [];
}

function getCmsOpeningStep(cms, recommendation) {
  const repeated = Number(recommendation.pageCount || 0) > 1 || ["family", "cross_cutting", "sitewide"].includes(recommendation.pageScope);
  const label = CMS_OPTIONS.find((option) => option.value === cms)?.label || "your website editor";
  if (recommendation.needsHelp) return `Open ${label} with your web person and ${repeated ? "locate the shared template, navigation, sitemap, or routing rule behind this group" : "locate the setting or code responsible for this URL"}.`;
  return `Open ${label} and ${repeated ? "locate the shared template or collection used by these pages" : "open the affected page's SEO or content settings"}.`;
}

function buildEvidenceItems(recommendation) {
  const items = [];
  const metadataBreakdown = formatMetadataStateBreakdown(recommendation.metadataStateCounts);
  if (metadataBreakdown) items.push({ label: "Description status", value: metadataBreakdown });
  if (recommendation.pageScope) items.push({ label: "Scope", value: humanize(recommendation.pageScope) });
  else if (recommendation.scopeRelationship) items.push({
    label: "Scope",
    value: customerScopeRelationshipLabel(recommendation.scopeRelationship),
  });
  if (recommendation.evidenceStatus) items.push({ label: "Evidence", value: humanize(recommendation.evidenceStatus) });
  if (recommendation.pageType) items.push({ label: "Page type", value: humanize(recommendation.pageType) });
  if (recommendation.pageValueLabel) items.push({ label: "Business value", value: recommendation.pageValueLabel });
  if (recommendation.defectClass) items.push({ label: "Issue type", value: humanize(recommendation.defectClass) });
  if (recommendation.metaGate) items.push({ label: "Meta gate", value: humanize(recommendation.metaGate) });
  if (recommendation.currentValue) items.push({ label: "Current value", value: clampText(recommendation.currentValue, 180) });
  return items.slice(0, 6);
}

function formatMetadataStateBreakdown(value = {}) {
  const counts = normalizeMetadataStateCounts(value);
  return [
    counts.missing > 0 ? `${counts.missing} missing` : "",
    counts.empty > 0 ? `${counts.empty} empty` : "",
    counts.malformed > 0 ? `${counts.malformed} malformed` : "",
  ].filter(Boolean).join(" · ");
}

// Converts a durable {run, fixList, fixItems} bundle into the flat record
// shape this page reads from.
function normalizeDurableScanBundle(bundle = {}) {
  const run = bundle.run || {};
  const fixList = bundle.fixList || {};
  return {
    ...run,
    id: run.id || bundle.scan_id || "",
    scan_id: run.scan_id || run.id || bundle.scan_id || "",
    fix_list_id: fixList.id || run.fix_list_id || "",
    customer_access: bundle.access || "locked",
    authority_verified: bundle.authority_verified === true,
    result_integrity_verified: bundle.result_integrity_verified === true,
    is_authoritative: fixList.is_authoritative === true,
    health_score: run.health_score ?? fixList.health_score ?? null,
    health_grade: run.health_grade || fixList.health_grade || "",
    scan_status: run.scan_status || fixList.scan_status || "",
    score_is_provisional: run.score_is_provisional === true || fixList.score_is_provisional === true,
    no_high_confidence_findings: run.no_high_confidence_findings === true || fixList.no_high_confidence_findings === true,
    created_at: run.completed_at || run.created_date || run.queued_at || "",
    recommendations: Array.isArray(bundle.fixItems) ? bundle.fixItems : [],
  };
}

function durableFailureKind(record = {}) {
  const evidence = `${record.error_code || ""} ${record.status_detail || ""}`.toLowerCase();
  if (/429|rate.?limit|challenge|bot.?protection|access.?limit|scanner.?blocked/.test(evidence)) return "access_limited";
  if (/heartbeat|stalled|orphaned|vanished|no_terminal|progress stopped/.test(evidence)) return "worker_stalled";
  if (/persist|save.?fail|authority.?write|result.?write/.test(evidence)) return "save_failed";
  return "interrupted";
}

function getDurableScanStateTitle(record = {}) {
  const status = String(record.status || "");
  if (["queued", "crawling", "reviewing"].includes(status)) return "This scan is still running";
  if (status === "limited") return "This scan finished with limited evidence";
  if (status === "failed" && durableFailureKind(record) === "access_limited") return "The website limited this scan's access";
  if (status === "failed" && durableFailureKind(record) === "worker_stalled") return "This scan stopped making progress";
  if (status === "failed" && durableFailureKind(record) === "save_failed") return "The result could not be saved";
  if (status === "failed") return "This scan didn't finish";
  if (status === "cancelled") return "This scan was cancelled";
  return "No results saved for this scan";
}

function getDurableScanStateDetail(record = {}) {
  const status = String(record.status || "");
  if (["queued", "crawling", "reviewing"].includes(status)) {
    return "FixList is still working. This page refreshes automatically and will show your saved result as soon as it is ready.";
  }
  if (status === "limited") {
    return "FixList couldn't verify enough representative page evidence to publish a reliable result. Run a fresh scan when you're ready to try again.";
  }
  if (status === "failed") {
    const kind = durableFailureKind(record);
    if (kind === "access_limited") return "The website returned a rate limit, challenge, or access block before FixList could collect enough evidence. No authoritative result was saved. Wait a while before retrying; if it repeats, ask your web person to review CDN, firewall, and bot-protection logs.";
    if (kind === "worker_stalled") return "Progress stopped and FixList safely closed the run. No partial result was promoted. You can retry the scan; if it happens again, include the scan reference when contacting support.";
    if (kind === "save_failed") return "Crawling finished, but FixList could not persist the verified result. Do not rely on a partial browser result; retry once and include the scan reference if saving fails again.";
    return "Something interrupted this scan before results could be saved. Run a fresh scan to get a complete FixList.";
  }
  if (status === "cancelled") {
    return "This scan was stopped before it finished, so no results were saved. Run a fresh scan when you're ready.";
  }
  return "This scan finished without any saved results to show. Run a fresh scan to get an up-to-date FixList.";
}

function getRecommendations(record) {
  return firstArray([record?.recommendations, record?.fixes, record?.findings, record?.cleaned_fixes, record?.raw_fixes, record?.issues]);
}

function getPages(record) {
  return firstArray([record?.crawled_pages, record?.pages, record?.scanned_pages, record?.raw?.scanner?.pages_preview]);
}



function isHealthScoreUnavailable(record) {
  const status = cleanString(
    record?.health_score_status
      || record?.website_health_report?.health_score_status
      || record?.scan_summary?.health_score_status,
  );
  if (status === "insufficient_evidence") return true;
  return record?.health_score === null && record?.seo_score === null;
}

function getHealthScore(record) {
  if (isHealthScoreUnavailable(record)) return null;
  const candidates = [
    record?.health_score,
    record?.seo_score,
    record?.website_health_report?.health_score,
    record?.scan_summary?.health_score,
    record?.scan_summary?.score,
  ];
  const raw = candidates.find((value) => value !== null && value !== undefined && value !== "");
  const score = Number(raw);
  return Number.isFinite(score) ? Math.round(score) : null;
}

function getPagesScanned(record, pages) {
  const count = Number(record?.pages_crawled || record?.pages_scanned || record?.pages_checked || record?.scan_summary?.pages_scanned || record?.technical_audit_summary?.pages_crawled || pages.length || 0);
  return Number.isFinite(count) ? count : 0;
}

function getPagesFound(record) {
  const count = Number(record?.pages_found || record?.scan_summary?.pages_found || record?.technical_audit_summary?.pages_found || 0);
  return Number.isFinite(count) ? count : 0;
}

function isNoHighConfidenceFindings(record, recommendations = []) {
  const scanStatus = String(record?.scan_status || "");
  if (["incomplete_evidence", "inconclusive_insufficient_evidence", "blocked_or_incomplete"].includes(scanStatus)) return false;
  return record?.no_high_confidence_findings === true
    || record?.review_confidence_state === "no_high_confidence_findings"
    || scanStatus === "complete_no_high_confidence_findings"
    || recommendations.length === 0;
}

function getNextBestStep(record, noHighConfidenceFindings) {
  return cleanString(record?.website_health_report?.next_best_step || record?.next_best_step)
    || (noHighConfidenceFindings ? "No high-confidence issues were found in the scanned sample — consider a deeper crawl or manual review of money pages." : "");
}

function getBestSummary(record, pagesScanned, pagesFound, recommendations = []) {
  const issueCount = recommendations.length;
  if (isHealthScoreUnavailable(record)) {
    return `FixList could not check enough usable pages to calculate a reliable score. It kept ${issueCount || 0} item${issueCount === 1 ? "" : "s"} for you to review.`;
  }
  // The summary must count the same canonical action bands the customer sees.
  // Raw scanner severity is evidence context, not the work-queue order.
  const fixFirstCount = recommendations.filter((item) => priorityBucket(item) === "fix_first").length;
  const groupedCount = recommendations.filter(hasExplicitSharedRepairConfirmation).length;
  const pagesLabel = (count, qualifier = "") => `${formatCount(count)}${qualifier ? ` ${qualifier}` : ""} ${Number(count) === 1 ? "page" : "pages"}`;
  const coverage = pagesFound > 0
    ? `FixList found ${pagesLabel(pagesFound)} and checked ${pagesLabel(pagesScanned, "representative")}.`
    : `FixList checked ${pagesLabel(pagesScanned, "representative")}.`;
  const priorities = fixFirstCount > 0
    ? ` It found ${issueCount} improvement${issueCount === 1 ? "" : "s"}; ${fixFirstCount} ${fixFirstCount === 1 ? "is" : "are"} in Fix first.`
    : ` It found ${issueCount} improvement${issueCount === 1 ? "" : "s"} to work through.`;
  const grouping = groupedCount > 0 ? " Several affect shared page patterns, so one change can improve many pages at once." : "";
  return `${coverage}${priorities}${grouping}`;
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

function formatCount(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString() : "0";
}

function formatDate(value) {
  try {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return "Recent";
  }
}
