import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Copy,
  Download,
  FileJson,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { base44 } from "@/api/base44Client";
import { ensureScanProject } from "@/lib/activeProject";
import { normalizeActionPriority, normalizeFindingEvidence, normalizeReviewEvidenceState, normalizeReviewScope, selectFinalReviewFixes } from "@/lib/reviewContract";
import { mergePersistedScanRunRecord } from "@/lib/persistedScanRecord";
import { RELEASE_AUTHORITY_CONTRACT, buildAuthorityMarkers, buildDiagnosticAuthorityMarkers, buildScanRunFields } from "@/lib/scanRunModel";
import { createScanRequestId, normalizedScanDomain, scanReleaseIdentity } from "@/lib/scanRunIdentity";
import { beginScanRun, cancelScanRun, completeScanRun, failScanRun, markScanRunReviewing, recoverOrphanedScanRuns } from "@/lib/scanRuns";
import { UNLOCK_PRICE_LABEL, loadAccess, recordScanUsed } from "@/lib/access";
import {
  CUSTOMER_BOUNDARY_EVENT,
  clearCustomerAuthBoundary,
  readCustomerActiveProject,
} from "@/lib/customerBrowserCache";

const STANDARD_SCANNER_FUNCTION = "runStandard150Scan";
const AI_REVIEW_FUNCTION = "aiReviewScan";

// Standard 150 is the only customer scan. There is no scan-size selector and no
// customer-controlled scanner budget. The gateway owns the Python compatibility
// translation, so the frontend never sends "advanced" as the customer mode.
const STANDARD_SCAN_MODE = "standard_150";
const STANDARD_SCAN_BUDGET = Object.freeze({ max_pages: 150, max_browser_render_attempts: 1, crawl_timeout_ms: 90000 });

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

const LOW_VALUE_PAGE_PATTERNS = ["/actualites", "/news", "/blog", "/archive", "/archives", "/tag/", "/tags/", "/author/", "/feed", "/rss", "?tag=", "&tag="];
const LEGAL_PAGE_RE = /(mentions-legales|mentions_legales|politique-de-confidentialite|privacy-policy|privacy_policy|conditions-generales|conditions-generales-de-vente|legal-notice|terms-of-service|terms-and-conditions|terms-of-use|privacy|impressum)|(?:^|\/)(?:cgu|cgv|legal|terms|mentions|privacite)(?:\/|$)/i;
const ROUTE_BOUNDARY_RE = /\/(?:login|signin|sign-in|register|signup|sign-up|account|mon-compte|dashboard|cart|panier|checkout|billing|admin|wp-admin)(?=[/?#\s]|$)/i;
const WORDPRESS_AUTHOR_ARCHIVE_RE = /^\/author\/[^/?#]+(?:\/page\/\d+)?\/?$/i;
const isRouteBoundaryPath = (value = "") => { const path = String(value || "").split("?")[0].split("#")[0]; return !WORDPRESS_AUTHOR_ARCHIVE_RE.test(path) && ROUTE_BOUNDARY_RE.test(path); };
const MONEY_PAGE_PATTERNS = ["devis", "quote", "pricing", "tarif", "contact", "booking", "reservation", "checkout", "ticket", "voucher", "pass", "show", "listing", "product", "produit", "collection", "category", "simulation", "simulateur", "calcul", "calculator", "comparateur", "demo", "signup", "energie", "énergie", "electricite", "électricité", "gaz", "fournisseur"];
const TEMPLATE_RULES = new Set(["client_rendering", "js_rendering", "canonical_missing", "canonical_to_other_url", "schema", "missing_h1", "image_alt_text", "missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable", "route_boundary_candidate_indexable", "internal_route_indexable"]);

export default function ScanWebsiteForm({ project = null, saving = false }) {
  const navigate = useNavigate();
  const [websiteUrl, setWebsiteUrl] = useState(project?.website_url || "");
  const [businessName, setBusinessName] = useState(project?.business_name || "");
  const [cmsPlatform, setCmsPlatform] = useState(normalizeCmsValue(project?.cms_platform || "custom"));
  const [keywordsText, setKeywordsText] = useState(Array.isArray(project?.important_keywords) ? project.important_keywords.join("\n") : "");
  const scanMode = STANDARD_SCAN_MODE;
  const [optionalOpen, setOptionalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeStep, setActiveStep] = useState("");
  const [error, setError] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugData, setDebugData] = useState(() => emptyRuntimeDebug());
  const debugDataRef = useRef(debugData);
  const submitLockRef = useRef(false);
  const requestEpochRef = useRef(0);
  const [debugCopied, setDebugCopied] = useState(false);
  const [debugCompressed, setDebugCompressed] = useState(true);

  const isLoading = submitting || saving;
  const cleanedKeywords = useMemo(() => splitLines(keywordsText), [keywordsText]);
  const selectedCms = CMS_OPTIONS.find((item) => item.value === cmsPlatform);
  const displayedDebugData = debugCompressed ? compressDebugData(debugData) : debugData;
  const displayedDebugText = JSON.stringify(displayedDebugData, null, debugCompressed ? 0 : 2);

  function recordDebug(data) {
    const next = runtimeDebug(data);
    debugDataRef.current = next;
    setDebugData(next);
  }

  function refreshDebugData() {
    setDebugData(debugDataRef.current);
  }

  function clearDebugScanData() {
    const next = emptyRuntimeDebug();
    debugDataRef.current = next;
    setDebugData(next);
  }

  useEffect(() => {
    function invalidatePendingRequest() {
      requestEpochRef.current += 1;
      submitLockRef.current = false;
      setSubmitting(false);
      setActiveStep("");
      clearDebugScanData();
    }
    window.addEventListener(CUSTOMER_BOUNDARY_EVENT, invalidatePendingRequest);
    // Close abandoned runs as soon as the customer reaches the scan form,
    // rather than waiting for their next submission. A row past the orphan
    // threshold has no owner left to finish it.
    recoverOrphanedScanRuns({ projectId: project?.id || "" }).catch(() => {});
    return () => {
      requestEpochRef.current += 1;
      submitLockRef.current = false;
      window.removeEventListener(CUSTOMER_BOUNDARY_EVENT, invalidatePendingRequest);
    };
  }, []);

  async function copyDebugData(compact = debugCompressed) {
    try {
      const snapshot = debugDataRef.current;
      const payload = compact ? compressDebugData(snapshot) : snapshot;
      await navigator.clipboard.writeText(JSON.stringify(payload, null, compact ? 0 : 2));
      setDebugCopied(true);
      window.setTimeout(() => setDebugCopied(false), 1500);
    } catch (copyError) {
      console.warn("Could not copy debug data.", copyError);
    }
  }

  function downloadDebugData(compact = true) {
    const snapshot = debugDataRef.current;
    const payload = compact ? compressDebugData(snapshot) : snapshot;
    const website = snapshot?.parsed?.runtime?.website_url || websiteUrl || "fixlist";
    const host = safeHostname(website) || "fixlist";
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const blob = new Blob([JSON.stringify(payload, null, compact ? 0 : 2)], { type: "application/json;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `fixlist-debug-${compact ? "compact" : "full"}-${host}-${timestamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitLockRef.current || saving) return;
    let requestEpoch = requestEpochRef.current;
    setError("");
    const submittedUrl = String(websiteUrl || "").trim();
    const normalizedUrl = normalizeWebsiteUrl(websiteUrl);
    const requestedPathPrefix = getRequestedPathPrefix(normalizedUrl);
    const trimmedBusinessName = businessName.trim();
    const cmsName = selectedCms?.label || "Custom / Not sure";
    if (!normalizedUrl) { setError("Enter a valid website URL."); return; }
    if (!trimmedBusinessName) { setError("Enter the business or website name."); return; }

    // Access gate runs before any durable scan identity is created, so a blocked
    // customer never consumes a request_id or leaves a queued ScanRun behind.
    const access = await loadAccess();
    if (!access.canScan) {
      setError(`You've used your free test scan. Unlock full access for ${UNLOCK_PRICE_LABEL} on the Billing page to run more scans and see every result.`);
      return;
    }
    submitLockRef.current = true;

    let scanData = null;
    let aiData = null;
    let mergedFinal = null;
    let scanRunHandle = null;
    let sessionIdentity = null;
    const requestId = createScanRequestId();
    const idempotencyKey = requestId;
    let scanId = "";
    const identityDebug = () => ({
      request_id: scanRunHandle?.request_id || requestId,
      idempotency_key: scanRunHandle?.idempotency_key || idempotencyKey,
      scan_id: scanRunHandle?.id || scanId,
      scan_run_id: scanRunHandle?.id || scanId,
      submitted_url: submittedUrl,
      normalized_domain: normalizedScanDomain(normalizedUrl),
    });
    setSubmitting(true);

    try {
      const { user: scanOwner, project: scanProject } = await ensureScanProject({
        projectId: project?.id,
        websiteUrl: normalizedUrl,
        businessName: trimmedBusinessName,
        cmsPlatform,
        importantKeywords: cleanedKeywords,
      });
      submitLockRef.current = true;
      requestEpoch = requestEpochRef.current + 1;
      requestEpochRef.current = requestEpoch;
      scanRunHandle = await beginScanRun({
        projectId: scanProject.id,
        websiteUrl: normalizedUrl,
        submittedUrl,
        pathPrefix: requestedPathPrefix,
        scanMode,
        scanSource: "scan_website_page",
        requestId,
        idempotencyKey,
      });
      scanId = scanRunHandle.id;
      sessionIdentity = {
        ownerId: scanOwner.id,
        projectId: scanProject.id,
        requestId,
        scanId,
        normalizedDomain: normalizedScanDomain(normalizedUrl),
        canonicalMode: scanMode,
        releaseIdentity: RELEASE_AUTHORITY_CONTRACT.betaRevisionFingerprint,
      };
      await assertCurrentScanSession(sessionIdentity, requestEpoch, requestEpochRef);
      recordDebug({ ...identityDebug(), status: "running", stage: "scan_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix });
      refreshDebugData();

      if (scanRunHandle.replayed) {
        recordDebug({ ...identityDebug(), status: scanRunHandle.status, stage: scanRunHandle.replay_reason, website_url: normalizedUrl, scan_mode: scanMode });
        refreshDebugData();
        navigate(`/dashboard?scan_id=${encodeURIComponent(scanId)}`);
        return;
      }

      const safeScanBudget = STANDARD_SCAN_BUDGET;
      setActiveStep("Reading your pages");
      const scanPayload = {
        website_url: normalizedUrl,
        requested_start_url: normalizedUrl,
        crawl_path_prefix: requestedPathPrefix,
        strict_path_prefix: true,
        clear_previous_scan: true,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        important_keywords: cleanedKeywords,
        competitor_urls: [],
        scan_mode: scanMode,
        enable_screaming_frog_lite: true,
        force_internal_crawl: true,
        respect_robots_txt: true,
        max_pages: safeScanBudget.max_pages,
        max_competitors: 0,
        max_browser_render_attempts: safeScanBudget.max_browser_render_attempts,
        crawl_timeout_ms: safeScanBudget.crawl_timeout_ms,
        source: "scan_website_page",
        requested_at: new Date().toISOString(),
        request_id: requestId,
        idempotency_key: idempotencyKey,
        scan_id: scanId,
        scan_run_id: scanId,
        submitted_url: submittedUrl,
        normalized_domain: normalizedScanDomain(normalizedUrl),
        require_python_scanner: true,
        allow_deno_fallback: false,
      };
      recordDebug({ ...identityDebug(), status: "running", stage: "scanner_request_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, payload_summary: { max_pages: scanPayload.max_pages, max_competitors: 0, max_browser_render_attempts: scanPayload.max_browser_render_attempts, crawl_timeout_ms: scanPayload.crawl_timeout_ms, keyword_count: scanPayload.important_keywords.length, respect_robots_txt: scanPayload.respect_robots_txt } });
      refreshDebugData();

      logScanBoundary("scanner_function_start", identityDebug(), { function_name: STANDARD_SCANNER_FUNCTION });
      const scannerResponse = await callBase44Function(STANDARD_SCANNER_FUNCTION, scanPayload);
      logScanBoundary("scanner_function_response", identityDebug(), { function_name: STANDARD_SCANNER_FUNCTION });
      await assertCurrentScanSession(sessionIdentity, requestEpoch, requestEpochRef);
      scanData = normalizeFunctionResponse(scannerResponse);
      assertServerScanIdentity(scanData, identityDebug());
      recordDebug({ ...identityDebug(), status: "running", stage: "scanner_complete", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData) });
      refreshDebugData();
      if (scanData?.success === false || scanData?.error) throw new Error(scanData.error || "Website scan failed.");

      setActiveStep("Checking SEO issues");
      markScanRunReviewing(scanRunHandle).catch((reviewingError) => {
        clearCustomerAuthBoundary(reviewingError);
      });
      try {
        const aiPayload = buildAiReviewPayload({ scanData, businessName: trimmedBusinessName, websiteUrl: normalizedUrl, cmsPlatform, cmsName, cleanedKeywords, scanMode, requestedPathPrefix, ...identityDebug() });
        recordDebug({ ...identityDebug(), status: "running", stage: "ai_review_request_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_payload_summary: { pages_crawled: aiPayload.scan_coverage?.pages_crawled || aiPayload.authoritative_scan?.pages_crawled || 0, pages_found: aiPayload.scan_coverage?.pages_found || aiPayload.authoritative_scan?.pages_found || 0, sampled_pages_sent_to_ai: aiPayload.scan_coverage?.sampled_pages_sent_to_ai || aiPayload.crawled_pages?.length || aiPayload.authoritative_scan?.crawled_pages?.length || 0, raw_fixes_count: aiPayload.raw_fixes?.length || getRecommendations(aiPayload.authoritative_scan).length, crawl_policy_source: aiPayload.crawl_policy_source || aiPayload.authoritative_scan?.crawl_policy_source || "", url_evidence_preserved: Boolean(aiPayload.url_evidence_summary || aiPayload.authoritative_scan?.url_evidence_summary), business_priority_rules_enabled: true, coverage_instruction_enabled: true } });
        refreshDebugData();
        setActiveStep("Writing your FixList");
        logScanBoundary("review_function_start", identityDebug(), { function_name: AI_REVIEW_FUNCTION });
        const aiResponse = await callBase44Function(AI_REVIEW_FUNCTION, aiPayload);
        logScanBoundary("review_function_response", identityDebug(), { function_name: AI_REVIEW_FUNCTION });
        await assertCurrentScanSession(sessionIdentity, requestEpoch, requestEpochRef);
        aiData = { ...normalizeFunctionResponse(aiResponse), ...identityDebug() };
        recordDebug({ ...identityDebug(), status: "running", stage: "ai_review_complete", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) });
        refreshDebugData();
      } catch (aiError) {
        if (
          aiError?.code === "stale_customer_session"
          || clearCustomerAuthBoundary(aiError)
        ) throw aiError;
        console.warn("AI review was skipped or failed.", aiError);
        aiData = { success: false, ...identityDebug(), error: aiError?.message || String(aiError) };
        recordDebug({ ...identityDebug(), status: "running", stage: "ai_review_failed_but_continuing", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), ai_error: aiError?.message || String(aiError) });
        refreshDebugData();
      }

      setActiveStep("Saving your FixList");
      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, submittedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, requestId, idempotencyKey, scanId, scanRunId: scanId });
      const reviewAttestation = aiData?.authority_review_attestation;
      const usingAuthorityPersistence = Boolean(reviewAttestation);
      if (aiData?.release_gate_eligible === true && !usingAuthorityPersistence) {
        throw Object.assign(new Error("The review finished, but its server authority attestation was missing."), {
          code: "scan_authority_attestation_missing",
          scan_record: { ...mergedFinal, release_gate_eligible: false, is_authoritative: false },
        });
      }
      logScanBoundary("persistence_start", identityDebug(), { authority_persistence: usingAuthorityPersistence });
      const durableRecord = usingAuthorityPersistence
        ? mergedFinal
        : { ...mergedFinal, release_gate_eligible: false, is_authoritative: false };
      const completion = usingAuthorityPersistence
        ? normalizeFunctionResponse(await callBase44Function("persistScanAuthority", {
          scan_id: scanId,
          attestation: reviewAttestation,
        }).catch((persistenceError) => {
          if (clearCustomerAuthBoundary(persistenceError)) throw persistenceError;
          return null;
        }))
        : await completeScanRun(scanRunHandle, durableRecord).catch((persistenceError) => {
          if (clearCustomerAuthBoundary(persistenceError)) throw persistenceError;
          return null;
        });
      logScanBoundary("persistence_response", identityDebug(), { persisted: Boolean(completion?.scanRun) });
      await assertCurrentScanSession(sessionIdentity, requestEpoch, requestEpochRef);
      if (!completion?.scanRun) throw Object.assign(new Error("The scan finished, but its durable FixList record could not be saved."), { code: "scan_persistence_failed", scan_record: durableRecord });
      if (usingAuthorityPersistence) {
        const proof = String(completion.scanRun.authority_proof || "").trim().toLowerCase();
        const sealed = /^[a-f0-9]{64}$/.test(proof)
          && Boolean(completion.scanRun.authority_seal_version)
          && Boolean(completion.scanRun.authority_sealed_at)
          && completion.scanRun.release_gate_eligible === true
          && Boolean(completion.fixListId);
        if (!sealed) {
          throw Object.assign(new Error("The scan finished, but its server authority seal was not saved."), {
            code: "scan_authority_persistence_failed",
            scan_record: durableRecord,
          });
        }
      }
      if (completion?.scanRun) {
        mergedFinal = mergePersistedScanRunRecord(
          mergedFinal,
          completion.scanRun,
          completion.fixListId,
        );
      } else if (completion?.fixListId) {
        mergedFinal = { ...mergedFinal, fix_list_id: completion.fixListId };
      }
      // Only a durably persisted scan consumes the customer's allowance.
      await recordScanUsed().catch(() => {});
      recordDebug({ ...identityDebug(), status: "saved", stage: "dashboard_saved", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), final_record: slimScanRecord(mergedFinal), compact_debug_available: true, download_available: true });
      refreshDebugData();
      // Navigation happens only after a durable terminal result exists.
      logScanBoundary("browser_navigation", identityDebug(), { status: "complete" });
      navigate(`/dashboard?scan=complete&scan_id=${encodeURIComponent(scanId)}`);
    } catch (err) {
      // Every attempt must reach a terminal state. This branch used to return
      // without writing one, which is exactly what left ScanRun rows stuck at
      // "crawling" with zero pages and no error -- the permanent "still
      // running" screen. The request is abandoned for UI purposes, but the
      // durable row is still closed truthfully as cancelled before returning.
      const abandoned = err?.code === "stale_customer_session"
        || requestEpochRef.current !== requestEpoch
        || clearCustomerAuthBoundary(err);
      if (abandoned) {
        logScanBoundary("scan_abandoned", identityDebug(), { reason: err?.code || err?.name || "session_changed" });
        await cancelScanRun(scanRunHandle, err).catch(() => {});
        return;
      }
      console.error("Website scan failed.", err);
      if (err && typeof err === "object" && !err.scan_record) err.scanData = mergedFinal || scanData || {};
      const failure = await failScanRun(scanRunHandle, err).catch(() => null);
      const failureRecord = failure?.scanRun || { ...identityDebug(), status: "failed", error_code: err?.code || err?.name || "scan_failed", error_message: err?.message || String(err) };
      recordDebug({ ...identityDebug(), status: "failed", stage: "scan_failed", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, error: err?.message || String(err), scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), final_record: slimScanRecord(mergedFinal || failureRecord), compact_debug_available: true, download_available: true });
      refreshDebugData();
      setError(err?.message || "The website scan failed. Try again or check the backend function logs.");
    } finally {
      if (requestEpochRef.current === requestEpoch) {
        submitLockRef.current = false;
        setActiveStep("");
        setSubmitting(false);
      }
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-indigo-50 p-3 text-indigo-600"><Search className="h-6 w-6" /></div>
            <div>
              <p className="text-sm font-medium text-slate-500">FixList scan</p>
              <h2 className="mt-1 text-2xl font-bold text-slate-950">Create your FixList</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Enter a website URL and we’ll turn the scan into a plain-English list of what to fix, what matters most, and what may need a developer.</p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600"><ShieldCheck className="h-3.5 w-3.5 text-indigo-600" />Read-only scan — FixList never logs in or changes your website.</div>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={() => { refreshDebugData(); setDebugOpen((value) => !value); }} className="shrink-0"><Bug className="mr-2 h-4 w-4" />{debugOpen ? "Hide debug" : "Show debug"}</Button>
        </div>

        {debugOpen ? (
          <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-bold text-slate-950">Scan debug</h3>
                <p className="mt-1 text-xs text-slate-500">Compact mode limits runtime previews so the JSON is small enough to share. No customer scan data is read from browser storage.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={refreshDebugData}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
                <Button type="button" variant="outline" onClick={() => setDebugCompressed((value) => !value)}><FileJson className="mr-2 h-4 w-4" />{debugCompressed ? "Show full" : "Compress"}</Button>
                <Button type="button" variant="outline" onClick={() => copyDebugData(debugCompressed)}><Copy className="mr-2 h-4 w-4" />{debugCopied ? "Copied" : debugCompressed ? "Copy compact" : "Copy full"}</Button>
                <Button type="button" variant="outline" onClick={() => downloadDebugData(true)}><Download className="mr-2 h-4 w-4" />Download compact</Button>
                <Button type="button" variant="outline" onClick={() => downloadDebugData(false)}><Download className="mr-2 h-4 w-4" />Download full</Button>
                <Button type="button" variant="outline" onClick={clearDebugScanData}><Trash2 className="mr-2 h-4 w-4" />Clear scans</Button>
              </div>
            </div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words p-4 text-xs leading-5 text-slate-100">{displayedDebugText}</pre>
            </div>
          </div>
        ) : null}

        <div className="mt-6 grid gap-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <div><label className="text-sm font-medium text-slate-700">Website URL</label><Input value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} placeholder="https://www.example.com/" disabled={isLoading} className="mt-2" /></div>
            <div><label className="text-sm font-medium text-slate-700">Business or website name</label><Input value={businessName} onChange={(event) => setBusinessName(event.target.value)} placeholder="Example Business" disabled={isLoading} className="mt-2" /></div>
          </div>

          <div className="rounded-2xl border border-indigo-500 bg-indigo-50 p-4 ring-2 ring-indigo-100">
            <div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-indigo-600" /><span className="font-semibold text-slate-950">Standard · 150</span></div>
            <p className="mt-2 text-xs leading-5 text-slate-600">A complete, prioritized scan of up to 150 pages.</p>
          </div>

          <button type="button" onClick={() => setOptionalOpen((value) => !value)} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-100">{optionalOpen ? "Hide optional settings" : "Optional: personalize your FixList"}</button>

          {optionalOpen ? (
            <div className="grid gap-5 rounded-3xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-2">
              <div>
                <label className="text-sm font-medium text-slate-700">CMS / website builder</label>
                <select value={cmsPlatform} onChange={(event) => setCmsPlatform(event.target.value)} disabled={isLoading} className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-950 shadow-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50">
                  {CMS_OPTIONS.map((cms) => <option key={cms.value} value={cms.value}>{cms.label}</option>)}
                </select>
                <p className="mt-1 text-xs text-slate-500">We’ll tailor every fix to your CMS — where to click and what to change.</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Important keywords</label>
                <textarea value={keywordsText} onChange={(event) => setKeywordsText(event.target.value)} placeholder={"local service\nbest product\nnear me"} disabled={isLoading} rows={4} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50" />
                <p className="mt-1 text-xs text-slate-500">Optional. We’ll check whether your pages clearly target these searches.</p>
              </div>
            </div>
          ) : null}
        </div>

        {error ? <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><div className="flex items-start gap-2"><AlertCircle className="mt-0.5 h-4 w-4" /><span>{error}</span></div></div> : null}
        {isLoading ? <div className="mt-6 rounded-2xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-950"><div className="flex items-center gap-3"><Loader2 className="h-4 w-4 animate-spin" /><span>{activeStep || "Running scan..."}</span></div></div> : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button type="submit" disabled={isLoading} className="bg-indigo-600 text-white hover:bg-indigo-700">{isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Building FixList...</> : <><Search className="mr-2 h-4 w-4" />Create FixList</>}</Button>
          <p className="text-xs text-slate-500">Standard scans up to 150 pages. Premium large-site scans will be enabled after production benchmarking.</p>
        </div>
      </form>
    </div>
  );
}

function buildAiReviewPayload({ scanData, businessName, websiteUrl, cmsPlatform, cmsName, cleanedKeywords, scanMode, requestedPathPrefix, request_id, idempotency_key, scan_id, scan_run_id, submitted_url, normalized_domain }) {
  const crawledPages = getPages(scanData).slice(0, 150);
  const rawFixes = getRecommendations(scanData).slice(0, 140);
  const pagesCrawled = getFirstNumber([scanData?.pages_crawled, scanData?.pages_scanned, scanData?.technical_audit_summary?.pages_crawled, crawledPages.length]);
  const pagesFound = getFirstNumber([scanData?.pages_found, scanData?.pages_discovered, scanData?.technical_audit_summary?.pages_found, pagesCrawled, crawledPages.length]);
  const scanCoverage = { pages_crawled: pagesCrawled, pages_found: pagesFound, sampled_pages_sent_to_ai: crawledPages.length, sampled_findings_sent_to_ai: rawFixes.length, sample_limit: 150 };
  if (scanData?.authority_scan_attestation && scanData?.authority_review_payload) {
    return {
      // Send only the server-signed bounded review envelope. Reposting the full
      // 150-page browser result can exceed the Base44 function request boundary.
      authoritative_scan: {
        authority_review_payload: scanData.authority_review_payload,
        authority_scan_attestation: scanData.authority_scan_attestation,
        authority_attestation_status: scanData.authority_attestation_status || "server_attested",
      },
      client_context: {
        business_name: businessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        important_keywords: cleanedKeywords,
        requested_path_prefix: requestedPathPrefix || "",
        coverage_instruction: "Use the server-attested scan page counts. Do not describe a sample sent to review as the total scan size.",
        ai_review_goal: "Create a customer-friendly FixList that prioritizes business-important pages first. Preserve URL evidence, group template-level problems, and do not treat suspicious crawler artifacts as confirmed broken links.",
        cms_instruction: buildCmsInstruction(cmsPlatform),
        business_priority_instruction: {
          rule: "Prioritize by business importance, not just technical severity.",
          requested_path_prefix: requestedPathPrefix || "",
        },
        output_requirements: {
          keep_language_simple: true,
          group_similar_issues: true,
          preserve_url_evidence_fields: true,
          use_scan_coverage_for_page_counts: true,
        },
      },
    };
  }
  return {
    request_id,
    idempotency_key,
    scan_id,
    scan_run_id,
    submitted_url,
    normalized_domain,
    business_name: businessName,
    website_url: websiteUrl,
    cms_platform: cmsPlatform,
    cms_name: cmsName,
    important_keywords: cleanedKeywords,
    scan_mode: scanMode,
    scan_coverage: scanCoverage,
    coverage_instruction: "Use scan_coverage.pages_crawled as the number of pages reviewed by the scanner. Do not describe sampled_pages_sent_to_ai as the total scan size.",
    ai_review_goal: "Create a customer-friendly FixList that prioritizes business-important pages first. Preserve URL evidence, group template-level problems, and do not treat suspicious crawler artifacts as confirmed broken links.",
    cms_instruction: buildCmsInstruction(cmsPlatform),
    business_priority_instruction: {
      rule: "Prioritize by business importance, not just technical severity.",
      high_priority_pages: ["homepage or scanned section landing page", "booking, checkout, product, listing, category, quote, calculator, comparison, pricing, contact, supplier, tariff, and trust pages", "pages with verified crawler provenance"],
      low_priority_pages: ["old news posts", "month/year archive pages", "blog archives", "tag/archive/feed/pagination pages", "suspicious encoded URLs without source-page proof"],
      evidence_rule: "Use discovered_from, source_pages, link_text_samples, url_confidence, url_evidence_summary, verified_failed_pages, and suspicious_url_artifacts before calling a URL broken.",
      grouping_rule: "Group repeated client rendering, schema, H1, meta, image-alt, 404, 410, 429, and template issues.",
      ownership_rule: "SSR, JavaScript rendering, schema templates, canonicals, redirects, firewall/bot protection, server errors, route boundaries, noindex/indexability, and crawlability belong to your_web_person.",
      requested_path_prefix: requestedPathPrefix || "",
    },
    output_requirements: { keep_language_simple: true, group_similar_issues: true, create_top_priorities: true, include_developer_flags_only_when_needed: true, explain_scan_focus: true, prioritize_money_pages_first: true, demote_low_value_archive_pages: true, preserve_url_evidence_fields: true, do_not_overwrite_developer_owner_with_you: true, use_scan_coverage_for_page_counts: true },
    crawled_pages: crawledPages,
    raw_fixes: rawFixes,
    competitor_results: [],
    discovered_competitors: [],
    crawl_policy: scanData?.crawl_policy || scanData?.technical_audit_summary?.crawl_policy || {},
    crawl_policy_source: scanData?.crawl_policy_source || scanData?.technical_audit_summary?.crawl_policy?.source || "",
    url_evidence_summary: scanData?.url_evidence_summary || scanData?.technical_audit_summary?.url_evidence_summary || {},
    verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, scanData?.technical_audit_summary?.verified_failed_pages]),
    suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, scanData?.technical_audit_summary?.suspicious_url_artifacts]),
    important_page_patterns: unique([requestedPathPrefix || "", ...MONEY_PAGE_PATTERNS]).slice(0, 60),
    deprioritized_page_patterns: unique([...LOW_VALUE_PAGE_PATTERNS, "suspicious encoded URLs", "crawler artifacts", "tag/archive/feed/pagination"]).slice(0, 50),
    crawl_warnings: firstArray([scanData?.crawl_warnings]),
    technical_audit_summary: scanData?.technical_audit_summary || {},
    scan_summary: scanData?.scan_summary || scanData?.site_summary || {},
  };
}

function mergeScanAndAiReview({ scanData, aiData, websiteUrl, submittedUrl, businessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, requestId, idempotencyKey, scanId, scanRunId }) {
  const pages = getPages(scanData).slice(0, 150).map(slimPage);
  const scannerFixes = getRecommendations(scanData);
  const aiFixes = getRecommendations(aiData);
  const reviewEvidenceState = normalizeReviewEvidenceState(aiData);
  const finalFixes = selectFinalReviewFixes({
    aiData,
    aiFixes,
    scannerFixes,
    slimFix,
    groupAndSortFixes,
    requestedPathPrefix,
  });
  const healthScoreStatus = aiData?.health_score_status || aiData?.website_health_report?.health_score_status || aiData?.scan_summary?.health_score_status || scanData?.health_score_status || scanData?.scan_summary?.health_score_status || "available";
  const healthScore = healthScoreStatus === "insufficient_evidence" ? null : getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.score, scanData?.scan_summary?.health_score]);
  const reviewIsLimited = ["incomplete_evidence", "inconclusive_insufficient_evidence", "blocked_or_incomplete"].includes(reviewEvidenceState.scan_status);
  const noHighConfidenceFindings = aiData?.no_high_confidence_findings === true || (finalFixes.length === 0 && !reviewIsLimited);
  const healthGrade = aiData?.website_health_report?.health_grade || aiData?.health_grade || (noHighConfidenceFindings ? "No issues found in sample" : scoreLabel(healthScore));
  const nextBestStep = aiData?.website_health_report?.next_best_step || aiData?.next_best_step || (noHighConfidenceFindings ? "No high-confidence issues were found in this scanned sample. Consider a deeper crawl or manually reviewing key money pages." : "");
  const reviewLimitations = firstArray([aiData?.website_health_report?.limitations]);
  const limitation = aiData?.limitation || reviewLimitations[reviewLimitations.length - 1] || "";
  const pagesCrawled = getFirstNumber([scanData?.pages_crawled, scanData?.pages_scanned, scanData?.technical_audit_summary?.pages_crawled, pages.length]);
  const pagesFound = getFirstNumber([scanData?.pages_found, scanData?.pages_discovered, scanData?.technical_audit_summary?.pages_found, pagesCrawled, pages.length]);
  const crawlPolicy = scanData?.crawl_policy || scanData?.technical_audit_summary?.crawl_policy || {};
  const technicalSummary = slimTechnicalSummary(scanData?.technical_audit_summary || {}, scanData);
  const summaryText = normalizeCoverageSummary(aiData?.customer_summary || aiData?.plain_english_summary || aiData?.summary || aiData?.website_health_report?.overall_explanation || scanData?.scan_summary?.plain_english_summary || buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName }), pagesCrawled);
  const siteFingerprint = normalizeSiteFingerprint(aiData?.site_fingerprint || aiData?.scan_summary?.site_fingerprint || {}, pages);
  const authorityMarkers = buildAuthorityMarkers(scanData, aiData);
  const finalUrl = normalizeWebsiteUrl(scanData?.final_url || scanData?.resolved_start_url || pages[0]?.final_url || scanData?.normalized_url || scanData?.website_url || websiteUrl);
  const releaseIdentity = scanReleaseIdentity({
    ...scanData,
    ...authorityMarkers,
    scanner_wrapper_version: scanData?.scanner_wrapper_version || scanData?.wrapper_version || scanData?.version || "",
  });
  const mergedRecord = {
    id: scanId || createScanId(),
    scan_id: scanId || "",
    scan_run_id: scanRunId || "",
    request_id: requestId || scanData?.request_id || "",
    idempotency_key: idempotencyKey || scanData?.idempotency_key || requestId || "",
    created_at: new Date().toISOString(),
    website_url: websiteUrl,
    submitted_url: submittedUrl || websiteUrl,
    final_url: finalUrl || websiteUrl,
    normalized_domain: normalizedScanDomain(finalUrl || websiteUrl),
    respect_robots_txt: true,
    website_key: normalizeWebsiteKey(websiteUrl),
    requested_path_prefix: requestedPathPrefix || "",
    business_name: businessName,
    cms_platform: cmsPlatform,
    cms_name: cmsName,
    scan_mode: scanMode,
    ...authorityMarkers,
    ...releaseIdentity,
    health_score: healthScore,
    seo_score: healthScore,
    health_score_status: healthScoreStatus,
    usable_page_count: getFirstNumber([aiData?.usable_page_count, aiData?.website_health_report?.usable_page_count, aiData?.scan_summary?.usable_page_count, scanData?.usable_page_count, scanData?.scan_summary?.usable_page_count]),
    pages_crawled: pagesCrawled || pages.length || 0,
    pages_found: pagesFound || pages.length || 0,
    customer_summary: summaryText,
    simple_summary: summaryText,
    cms_action_plan: noHighConfidenceFindings ? "No high-confidence fixes were found in the scanned sample. Consider a deeper crawl or a manual review of important business pages." : (aiData?.cms_action_plan || aiData?.cms_plan || aiData?.implementation_plan || buildCmsActionPlan(cmsPlatform, cmsName, finalFixes)),
    review_polish_version: aiData?.review_polish_version || "",
    group_dedup_version: aiData?.group_dedup_version || "",
    scoring_model: aiData?.scoring_model || aiData?.site_fingerprint?.scoring_model || "",
    sampling_version: scanData?.sampling_version || "",
    sampling_evidence: scanData?.sampling_evidence || {},
    ai_provider: aiData?.ai_provider || aiData?.provider || aiData?.debug?.provider || "",
    ai_review_backend: aiData?.ai_review_backend || "",
    python_review_fallback_used: Boolean(aiData?.python_review_fallback_used),
    // Scanner-stage eligibility is provisional because review authority markers do not exist yet.
    // Preserve only an explicit Python Review rejection, then validate the completed record below.
    release_gate_eligible: aiData?.release_gate_eligible === true && Boolean(aiData?.authority_review_attestation),
    no_high_confidence_findings: noHighConfidenceFindings,
    review_confidence_state: reviewEvidenceState.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),
    score_is_provisional: reviewEvidenceState.score_is_provisional,
    access_evidence_state: reviewEvidenceState.access_evidence_state,
    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",
    scan_status: reviewEvidenceState.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),
    next_best_step: nextBestStep,
    limitation,
    health_grade: healthGrade,
    top_recommended_actions: buildTopActions({ finalFixes }).map(slimAction),
    recommendations: finalFixes,
    fixes: finalFixes,
    findings: finalFixes,
    crawled_pages: pages,
    pages,
    scanned_pages: pages,
    scan_summary: slimScanSummary(aiData?.scan_summary || scanData?.scan_summary || {}, healthScore, pagesCrawled, finalFixes, scanData, summaryText),
    site_summary: slimScanSummary(scanData?.site_summary || scanData?.scan_summary || {}, healthScore, pagesCrawled, finalFixes, scanData, summaryText),
    technical_audit_summary: technicalSummary,
    website_health_report: slimHealthReport(aiData?.website_health_report || scanData?.website_health_report || {}, summaryText, healthScore),
    positive_findings: firstArray([aiData?.positive_findings, scanData?.positive_findings, scanData?.site_summary?.positives]).slice(0, 8).map(String),
    health_explanation: aiData?.health_explanation || scanData?.health_explanation || "",
    crawl_policy: crawlPolicy,
    crawl_policy_source: scanData?.crawl_policy_source || crawlPolicy?.source || technicalSummary.crawl_policy_source || "",
    url_evidence_summary: scanData?.url_evidence_summary || technicalSummary.url_evidence_summary || {},
    verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, technicalSummary.verified_failed_pages]),
    suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, technicalSummary.suspicious_url_artifacts]),
    crawl_scope: scanData?.crawl_scope || {},
    sitemap_priority_summary: scanData?.sitemap_priority_summary || {},
    important_page_patterns: firstArray([scanData?.important_page_patterns, aiData?.important_page_patterns]).slice(0, 30),
    deprioritized_page_patterns: unique([...firstArray([scanData?.deprioritized_page_patterns, aiData?.deprioritized_page_patterns]), ...LOW_VALUE_PAGE_PATTERNS]).slice(0, 40),
    recommended_followup_scans: firstArray([scanData?.recommended_followup_scans, aiData?.recommended_followup_scans]).slice(0, 10),
    site_fingerprint: siteFingerprint,
    archetype_playbook: aiData?.archetype_playbook || {},
    competitor_result: {},
    competitor_results: [],
    competitor_opportunities: [],
    crawl_warnings: firstArray([scanData?.crawl_warnings, aiData?.crawl_warnings]).slice(0, 10),
    debug: {
      request_id: requestId || "",
      idempotency_key: idempotencyKey || requestId || "",
      scan_id: scanId || "",
      scan_run_id: scanRunId || scanId || "",
      scanner_function: STANDARD_SCANNER_FUNCTION,
      ai_function: AI_REVIEW_FUNCTION,
      screaming_frog_lite_enabled: true,
      scanner_success: scanData?.success !== false,
      ai_success: aiData?.success === true,
      ai_provider: aiData?.provider || aiData?.ai_provider || aiData?.debug?.provider || "",
      review_version: aiData?.review_version || aiData?.ai_review_version || "",
      beta_revision_fingerprint: aiData?.beta_revision_fingerprint || scanData?.beta_revision_fingerprint || "",
      review_polish_version: aiData?.review_polish_version || "",
    group_dedup_version: aiData?.group_dedup_version || "",
    scoring_model: aiData?.scoring_model || aiData?.site_fingerprint?.scoring_model || "",
    sampling_version: scanData?.sampling_version || "",
    sampling_evidence: scanData?.sampling_evidence || {},
    ai_review_backend: aiData?.ai_review_backend || "",
    python_review_fallback_used: Boolean(aiData?.python_review_fallback_used),
    no_high_confidence_findings: noHighConfidenceFindings,
    review_confidence_state: reviewEvidenceState.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),
    score_is_provisional: reviewEvidenceState.score_is_provisional,
    access_evidence_state: reviewEvidenceState.access_evidence_state,
    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",
    scan_status: reviewEvidenceState.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),
    next_best_step: nextBestStep,
    limitation,
    health_grade: healthGrade,
      cms_platform: cmsPlatform,
      requested_path_prefix: requestedPathPrefix || "",
      scanner_version: scanData?.version || scanData?.scanner_version || technicalSummary.scanner_version || "",
      ai_scoring_model: aiData?.site_fingerprint?.scoring_model || aiData?.scoring_model || "",
      archetype_label: siteFingerprint?.archetype_label || siteFingerprint?.vertical_label || "",
      crawl_policy_source: scanData?.crawl_policy_source || crawlPolicy?.source || "",
      verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, technicalSummary.verified_failed_pages]),
      suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, technicalSummary.suspicious_url_artifacts]),
      saved_as_slim_record: true,
      evidence_fields_preserved: true,
      template_grouping_enabled: true,
      compact_debug_enabled: true,
      download_json_enabled: true,
      scan_coverage_pages_crawled: pagesCrawled,
      scan_coverage_pages_found: pagesFound,
    },
    raw: { scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) },
  };
  return {
    ...mergedRecord,
    release_gate_eligible: buildScanRunFields(mergedRecord).release_gate_eligible,
  };
}

function compressDebugData(snapshot = {}) {
  const debug = snapshot?.parsed?.runtime || {};
  return {
    compressed: true,
    read_at: snapshot?.read_at || new Date().toISOString(),
    storage: "memory_only",
    debug: compressDebugRecord(debug),
  };
}

function compressDebugRecord(debug = {}) {
  if (!debug || typeof debug !== "object") return null;
  return {
    request_id: debug.request_id || "",
    idempotency_key: debug.idempotency_key || "",
    scan_id: debug.scan_id || debug.scan_run_id || "",
    scan_run_id: debug.scan_run_id || debug.scan_id || "",
    status: debug.status || "",
    stage: debug.stage || "",
    updated_at: debug.updated_at || "",
    website_url: debug.website_url || "",
    business_name: debug.business_name || "",
    scan_mode: debug.scan_mode || "",
    requested_path_prefix: debug.requested_path_prefix || "",
    error: debug.error || "",
    ai_error: debug.ai_error || "",
    payload_summary: debug.payload_summary || null,
    ai_payload_summary: debug.ai_payload_summary || null,
    scanner: debug.scanner || null,
    ai_review: debug.ai_review || null,
    final_record: compressScanRecord(debug.final_record),
  };
}

function compressScanRecord(record = {}) {
  if (!record || typeof record !== "object") return null;
  const recommendations = getRecommendations(record).slice(0, 24).map((fix) => ({
    id: fix.fix_id || fix.id || "",
    rule: fix.rule || "",
    category: fix.category || "",
    title: fix.title || fix.issue_title || "",
    priority: fix.priority || "",
    who_can_do_this: fix.who_can_do_this || "",
    difficulty: fix.difficulty || "",
    status: fix.status || "",
    business_importance: fix.business_importance || "",
    page_url: fix.page_url || fix.affected_pages?.[0] || "",
    affected_pages_count: firstArray([fix.affected_pages]).length,
    affected_pages_preview: firstArray([fix.affected_pages]).slice(0, 8),
    reason: clampText(fix.why_it_matters || fix.reason || fix.plain_english_explanation || "", 260),
  }));
  const pages = getPages(record).slice(0, 35).map((page) => ({
    url: page.url || page.final_url || "",
    status_code: page.status_code || 0,
    title: clampText(page.title || "", 120),
    h1: clampText(page.h1 || "", 120),
    indexable: page.indexable !== false,
    in_sitemap: Boolean(page.in_sitemap),
    page_template_family: page.page_template_family || "",
    estimated_page_intent: page.estimated_page_intent || "",
    route_boundary_candidate: Boolean(page.route_boundary_candidate),
    url_confidence: page.url_confidence || "",
  }));
  return {
    ...buildDiagnosticAuthorityMarkers(record),
    request_id: record.request_id || "",
    idempotency_key: record.idempotency_key || record.request_id || "",
    scan_id: record.scan_id || record.scan_run_id || record.id || "",
    scan_run_id: record.scan_run_id || record.scan_id || record.id || "",
    submitted_url: record.submitted_url || record.website_url || "",
    final_url: record.final_url || record.website_url || "",
    normalized_domain: record.normalized_domain || normalizedScanDomain(record.final_url || record.website_url),
    scanner_wrapper_version: record.scanner_wrapper_version || "",
    release_id: record.release_id || "",
    sampling_version: record.sampling_version || "",
    sampling_evidence: record.sampling_evidence || {},
    crawl_timing: record.crawl_timing || record.technical_audit_summary?.crawl_timing || {},
    id: record.id || "",
    created_at: record.created_at || "",
    website_url: record.website_url || "",
    business_name: record.business_name || "",
    scan_mode: record.scan_mode || "",
    health_score: record.health_score || record.seo_score || 0,
    pages_crawled: record.pages_crawled || 0,
    pages_found: record.pages_found || 0,
    customer_summary: clampText(record.customer_summary || record.simple_summary || record.scan_summary?.plain_english_summary || "", 1200),
    no_high_confidence_findings: record.no_high_confidence_findings === true,
    review_confidence_state: record.review_confidence_state || "",
    zero_fix_confidence_version: record.zero_fix_confidence_version || "",
    scan_status: record.scan_status || "",
    next_best_step: record.next_best_step || record.website_health_report?.next_best_step || "",
    limitation: record.limitation || "",
    health_grade: record.health_grade || record.website_health_report?.health_grade || "",
    crawl_policy_source: record.crawl_policy_source || record.crawl_policy?.source || record.technical_audit_summary?.crawl_policy_source || "",
    verified_failed_pages: getFirstNumber([record.verified_failed_pages, record.scan_summary?.verified_failed_pages, record.technical_audit_summary?.verified_failed_pages]),
    suspicious_url_artifacts: getFirstNumber([record.suspicious_url_artifacts, record.scan_summary?.suspicious_url_artifacts, record.technical_audit_summary?.suspicious_url_artifacts]),
    site_fingerprint: record.site_fingerprint || record.scan_summary?.site_fingerprint || {},
    archetype_playbook: record.archetype_playbook || {},
    url_evidence_summary: record.url_evidence_summary || record.technical_audit_summary?.url_evidence_summary || {},
    technical_audit_summary: record.technical_audit_summary ? {
      scanner_version: record.technical_audit_summary.scanner_version || "",
      pages_crawled: record.technical_audit_summary.pages_crawled || 0,
      pages_found: record.technical_audit_summary.pages_found || 0,
      verified_failed_pages: record.technical_audit_summary.verified_failed_pages || 0,
      suspicious_url_artifacts: record.technical_audit_summary.suspicious_url_artifacts || 0,
      route_boundary_candidates_crawled: record.technical_audit_summary.route_boundary_candidates_crawled || 0,
      crawl_timing: record.technical_audit_summary.crawl_timing || record.crawl_timing || {},
      crawl_policy_source: record.technical_audit_summary.crawl_policy_source || record.technical_audit_summary.crawl_policy?.source || "",
    } : null,
    debug: record.debug || {},
    top_recommended_actions: getRecommendations(record).slice(0, 5).map(fixToAction).map(slimAction),
    recommendations_count: getRecommendations(record).length,
    recommendations_preview: recommendations,
    pages_preview_count: pages.length,
    pages_preview: pages,
  };
}

async function callBase44Function(functionName, payload) {
  const timeoutMs = functionName === STANDARD_SCANNER_FUNCTION ? Number(payload?.crawl_timeout_ms || 30000) + 15000 : 70000;
  return await Promise.race([
    callBase44FunctionWithoutTimeout(functionName, payload),
    new Promise((_, reject) => window.setTimeout(() => reject(new Error(`${functionName} did not return within ${Math.round(timeoutMs / 1000)} seconds. The scan may have timed out before saving results.`)), timeoutMs)),
  ]);
}

async function callBase44FunctionWithoutTimeout(functionName, payload) {
  if (base44?.functions?.invoke) return await base44.functions.invoke(functionName, payload);
  if (typeof base44?.functions?.[functionName] === "function") return await base44.functions[functionName](payload);
  throw new Error(`${functionName} failed. No supported Base44 function caller was found.`);
}

function normalizeFunctionResponse(response) {
  if (!response) return {};
  if (response.data?.data) return response.data.data;
  if (response.data?.result) return response.data.result;
  if (response.data) return response.data;
  if (response.result?.data) return response.result.data;
  if (response.result) return response.result;
  if (response.body) return response.body;
  return response;
}

function assertServerScanIdentity(response, expected) {
  for (const field of ["request_id", "idempotency_key", "scan_id", "scan_run_id"]) {
    if (String(response?.[field] || "") !== String(expected?.[field] || "")) {
      throw new Error("The scanner response did not match this durable scan request.");
    }
  }
}

function emptyRuntimeDebug() {
  return { read_at: new Date().toISOString(), raw: {}, parsed: { runtime: null } };
}

function runtimeDebug(data) {
  return {
    read_at: new Date().toISOString(),
    raw: {},
    parsed: { runtime: { ...data, updated_at: new Date().toISOString() } },
  };
}

async function assertCurrentScanSession(identity, epoch, epochRef) {
  const stale = () => Object.assign(new Error("The signed-in customer or project changed while this request was active."), { code: "stale_customer_session" });
  if (!identity || epochRef.current !== epoch) throw stale();
  const currentUser = await base44.auth.me();
  // The signed-in owner is server authority and a mismatch always aborts.
  if (String(currentUser?.id || "") !== String(identity.ownerId || "")) throw stale();
  // The active-project pointer is only a browser cache. Private-mode storage,
  // an evicted key, or a boundary event that cleared caches all read back as
  // "" -- which is not evidence that the customer switched project, and must
  // never abandon a durable scan the server still owns. Only a pointer that
  // actively names a different project proves a real switch.
  const activeProjectId = readCustomerActiveProject(currentUser.id);
  if (activeProjectId && activeProjectId !== String(identity.projectId || "")) throw stale();
}

// Boundary instrumentation. Identity only -- never payloads, evidence,
// attestations, proofs, or tokens.
function logScanBoundary(boundary, identity, extra = {}) {
  console.info("[fixlist.scan]", {
    boundary,
    request_id: identity?.request_id || "",
    scan_id: identity?.scan_id || "",
    at: new Date().toISOString(),
    ...extra,
  });
}

function buildCmsInstruction(cmsPlatform) {
  const instructions = {
    wordpress: "Tailor fixes for WordPress. Mention SEO plugins such as Yoast, Rank Math, or All in One SEO when useful.",
    squarespace: "Tailor fixes for Squarespace. Explain steps using page settings, SEO tab, image settings, redirects, and navigation settings.",
    wix: "Tailor fixes for Wix. Explain steps using Wix SEO settings, page SEO basics, URL slugs, headings, alt text, redirects, and structured data tools.",
    shopify: "Tailor fixes for Shopify. Explain steps for products, collections, pages, theme editor, navigation, image alt text, URL redirects, and SEO fields.",
    webflow: "Tailor fixes for Webflow. Explain steps using page settings, CMS collections, SEO settings, redirects, alt text, and publishing.",
    framer: "Tailor fixes for Framer. Explain steps using page settings, metadata, headings, components, images, and publishing.",
    godaddy: "Tailor fixes for GoDaddy Website Builder. Explain simple steps using page settings, SEO tools, headings, images, and navigation.",
    joomla: "Tailor fixes for Joomla. Explain steps using Articles, Menus, Global Configuration, Metadata Options, SEF URLs, redirects, extensions, templates, headings, image alt text, and structured data extensions where useful.",
    custom: "Tailor fixes for a custom or unknown CMS. Explain which changes can be made by a site editor and which likely need a developer.",
  };
  return instructions[cmsPlatform] || instructions.custom;
}

function buildCmsActionPlan(cmsPlatform, cmsName, fixes) {
  const count = Array.isArray(fixes) ? fixes.length : 0;
  if (count === 0) return "No high-confidence fixes were found in the scanned sample. Consider a deeper crawl or a manual review of important business pages.";
  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first, then handle the easier cleanup tasks.`;
  const developerNote = fixes.some((fix) => fix.requires_developer) ? " Some items should go to your web person because they involve rendering, schema, canonicals, redirects, route boundaries, or server/crawl setup." : "";
  return `${intro} There are ${count} recommendations ready for review.${developerNote}`;
}

function slimScannerData(scanner = {}) {
  if (!scanner) return null;
  return { request_id: scanner.request_id || "", idempotency_key: scanner.idempotency_key || scanner.request_id || "", scan_id: scanner.scan_id || scanner.scan_run_id || "", scan_run_id: scanner.scan_run_id || scanner.scan_id || "", submitted_url: scanner.submitted_url || scanner.website_url || "", final_url: scanner.final_url || scanner.website_url || "", normalized_domain: scanner.normalized_domain || normalizedScanDomain(scanner.final_url || scanner.website_url), release_id: scanner.release_id || "", success: scanner.success, version: scanner.version || scanner.scanner_version, beta_revision_fingerprint: scanner.beta_revision_fingerprint || "", sampling_version: scanner.sampling_version || "", sampling_evidence: scanner.sampling_evidence || {}, website_url: scanner.website_url, scan_mode: scanner.scan_mode, pages_found: scanner.pages_found, pages_crawled: scanner.pages_crawled, queued_remaining: scanner.queued_remaining, health_score: scanner.health_score, seo_score: scanner.seo_score, crawl_policy_source: scanner.crawl_policy_source || scanner.crawl_policy?.source || scanner.technical_audit_summary?.crawl_policy?.source || "", crawl_policy: scanner.crawl_policy || scanner.technical_audit_summary?.crawl_policy || {}, url_evidence_summary: scanner.url_evidence_summary || scanner.technical_audit_summary?.url_evidence_summary || {}, verified_failed_pages: getFirstNumber([scanner.verified_failed_pages, scanner.scan_summary?.verified_failed_pages, scanner.technical_audit_summary?.verified_failed_pages]), suspicious_url_artifacts: getFirstNumber([scanner.suspicious_url_artifacts, scanner.scan_summary?.suspicious_url_artifacts, scanner.technical_audit_summary?.suspicious_url_artifacts]), technical_audit_summary: slimTechnicalSummary(scanner.technical_audit_summary || {}, scanner), crawl_warnings: firstArray([scanner.crawl_warnings]).slice(0, 10), recommendations_count: getRecommendations(scanner).length, pages_preview: getPages(scanner).slice(0, 12).map(slimPage), recommendations_preview: getRecommendations(scanner).slice(0, 18).map(slimFix) };
}

function slimAiData(ai = {}) {
  if (!ai) return null;
  const recommendations = getRecommendations(ai);
  return {
    request_id: ai.request_id || "",
    idempotency_key: ai.idempotency_key || ai.request_id || "",
    scan_id: ai.scan_id || ai.scan_run_id || "",
    scan_run_id: ai.scan_run_id || ai.scan_id || "",
    success: ai.success,
    ai_provider: ai.ai_provider || ai.provider || ai.debug?.provider || "",
    ai_review_backend: ai.ai_review_backend || "",
    python_review_fallback_used: Boolean(ai.python_review_fallback_used),
    release_gate_eligible: ai.release_gate_eligible === true,
    review_version: ai.review_version || ai.ai_review_version || "",
    review_evidence_calibration_version: ai.review_evidence_calibration_version || "",
    beta_revision_fingerprint: ai.beta_revision_fingerprint || "",
    archetype_classifier_version: ai.archetype_classifier_version || ai.site_fingerprint?.classification?.classifier_version || "",
    review_polish_version: ai.review_polish_version || "",
    group_dedup_version: ai.group_dedup_version || "",
    scoring_model: ai.scoring_model || ai.site_fingerprint?.scoring_model || "",
    no_high_confidence_findings: ai.no_high_confidence_findings === true,
    zero_fix_confidence_version: ai.zero_fix_confidence_version || "",
    scan_status: ai.scan_status || "",
    review_confidence_state: ai.review_confidence_state || ai.website_health_report?.review_confidence_state || "",
    score_is_provisional: Boolean(ai.score_is_provisional ?? ai.website_health_report?.score_is_provisional),
    access_evidence_state: ai.access_evidence_state || ai.website_health_report?.access_evidence_state || "",
    next_best_step: ai.next_best_step || ai.website_health_report?.next_best_step || "",
    limitation: ai.limitation || "",
    health_grade: ai.health_grade || ai.website_health_report?.health_grade || "",
    ai_review_warning: ai.ai_review_warning || "",
    health_score: ai.health_score || ai.seo_score || ai.website_health_report?.health_score || ai.website_health_report?.score || 0,
    customer_summary: ai.customer_summary || ai.plain_english_summary || ai.summary || ai.website_health_report?.overall_explanation || "",
    website_health_report: slimHealthReport(ai.website_health_report || {}),
    site_fingerprint: ai.site_fingerprint || ai.scan_summary?.site_fingerprint || {},
    archetype_playbook: ai.archetype_playbook || {},
    top_recommended_actions: recommendations.slice(0, 5).map(fixToAction).map(slimAction),
    recommendations_count: recommendations.length,
    recommendations_preview: recommendations.slice(0, 18).map(slimFix),
    ai_rewrites_applied: ai.ai_rewrites_applied || 0,
  };
}

function slimScanRecord(record = {}) {
  if (!record) return null;
  const recommendations = getRecommendations(record);
  const pages = getPages(record);
  return { ...record, sampling_version: record.sampling_version || "", sampling_evidence: record.sampling_evidence || {}, id: record.id || `scan_${Date.now()}`, created_at: record.created_at || new Date().toISOString(), website_url: record.website_url || "", website_key: record.website_key || normalizeWebsiteKey(record.website_url || ""), recommendations: recommendations.slice(0, 120).map(slimFix), fixes: recommendations.slice(0, 120).map(slimFix), findings: recommendations.slice(0, 120).map(slimFix), crawled_pages: pages.slice(0, 150).map(slimPage), pages: pages.slice(0, 150).map(slimPage), scanned_pages: pages.slice(0, 150).map(slimPage), top_recommended_actions: recommendations.slice(0, 5).map(fixToAction).map(slimAction), debug: { ...(record.debug || {}), compact_debug_enabled: true, download_json_enabled: true } };
}

function slimFix(fix = {}) {
  const affectedPages = firstArray([fix.affected_pages, fix.pages, fix.page_urls]);
  const fallbackPage = fix.page_url || fix.url || affectedPages[0] || "";
  const rule = fix.rule || fix.issue_type || "";
  const category = fix.category || inferCategory(rule, fix);
  const id = fix.id || fix.fix_id || fix.fingerprint || stableId(`${fallbackPage}|${category}|${fix.title || fix.issue_title}`);
  // Python review owns classification and workflow fields when it supplies them.
  // Only infer an owner for legacy/scanner-only findings that omit the contract.
  const hasAuthoritativeOwner = cleanString(fix.who_can_do_this) !== "";
  const hasAuthoritativeDeveloperFlag = typeof fix.requires_developer === "boolean";
  const inferredDeveloperOwned = needsDeveloperOwner({ ...fix, rule, category });
  const requiresDeveloper = hasAuthoritativeDeveloperFlag
    ? fix.requires_developer
    : (hasAuthoritativeOwner ? normalizeOwner(fix.who_can_do_this) === "your_web_person" : inferredDeveloperOwned);
  const title = cleanString(fix.title || fix.issue_title) || defaultTitle(category);
  const reviewScope = normalizeReviewScope(fix, classifyTemplateFamily(fallbackPage));
  const findingEvidence = normalizeFindingEvidence(fix);
  return { id, fix_id: fix.fix_id || id, rule, category, customer_category: isImageAltTextIssue({ ...fix, rule, category }) ? "Images" : fix.customer_category || friendlyCustomerCategory(category), priority: normalizePriority(fix.priority), difficulty: fix.difficulty || (requiresDeveloper ? "developer" : "easy"), status: fix.status || (requiresDeveloper ? "needs_developer" : fix.can_auto_fix ? "auto_fixed" : "needs_approval"), issue_title: title, title, plain_english_explanation: cleanString(fix.plain_english_explanation || fix.explanation || fix.summary || fix.description) || "This recommendation was found during the website scan.", plain_english_summary: cleanString(fix.plain_english_summary || fix.plain_english_explanation || fix.explanation || ""), why_it_matters: cleanString(fix.why_it_matters || fix.why || fix.impact) || "Improving this can help visitors and search engines understand the website more clearly.", recommendation: cleanString(fix.recommendation || fix.ai_recommendation || fix.recommended_value || fix.suggested_fix) || "Review this recommendation.", recommended_value: cleanString(fix.recommended_value || fix.recommendation || fix.ai_recommendation || fix.suggested_fix) || "Review this recommendation.", simple_next_step: cleanString(fix.simple_next_step || fix.next_step || fix.recommended_value || fix.recommendation) || "Review this item and update the affected page.", page_url: fallbackPage, affected_pages: unique([...(affectedPages || []), ...(fallbackPage ? [fallbackPage] : [])].map(String)).slice(0, 150), source_pages: firstArray([fix.source_pages]).slice(0, 30), link_text_samples: firstArray([fix.link_text_samples]).slice(0, 20), url_confidence: fix.url_confidence || "", url_suspicion_reasons: firstArray([fix.url_suspicion_reasons]).slice(0, 8), current_value: clampText(fix.current_value || fix.current || "", 260), can_auto_fix: Boolean(fix.can_auto_fix), requires_approval: typeof fix.requires_approval === "boolean" ? fix.requires_approval : !requiresDeveloper, requires_developer: requiresDeveloper, who_can_do_this: hasAuthoritativeOwner ? normalizeOwner(fix.who_can_do_this) : (requiresDeveloper ? "your_web_person" : "you"), what_to_do: firstArray([fix.what_to_do, fix.what_to_do_steps, fix.fix_steps, fix.steps]).slice(0, 5).map(String), what_to_do_steps: firstArray([fix.what_to_do_steps, fix.what_to_do, fix.fix_steps, fix.steps]).slice(0, 5).map(String), estimated_time: fix.estimated_time || fix.time_estimate || "", time_estimate: fix.time_estimate || fix.estimated_time || "", confidence_score: typeof fix.confidence_score === "number" ? fix.confidence_score : 90, source: fix.source || "", evidence_status: findingEvidence.evidence_status, verification_state: findingEvidence.verification_state, limitation_code: findingEvidence.limitation_code, status_codes: firstArray([fix.status_codes]).map(Number).filter(Boolean), business_importance: fix.business_importance || "standard", is_low_value_page: typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : isLowValuePage(fallbackPage), is_important_business_page: typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : isImportantBusinessPage(fallbackPage), page_type: fix.page_type || "", page_scope: reviewScope.page_scope, page_template_family: reviewScope.page_template_family, family_breakdown: fix.family_breakdown && typeof fix.family_breakdown === "object" ? fix.family_breakdown : {}, representative_pages_by_family: fix.representative_pages_by_family && typeof fix.representative_pages_by_family === "object" ? fix.representative_pages_by_family : {}, sitewide_evidence: fix.sitewide_evidence && typeof fix.sitewide_evidence === "object" ? fix.sitewide_evidence : {}, primary_defect_class: fix.primary_defect_class || "", meta_rewrite_allowed: Boolean(fix.meta_rewrite_allowed), meta_regeneration_gate: fix.meta_regeneration_gate || "", page_value_score: Number(fix.page_value_score || 0), page_value_label: fix.page_value_label || "", evidence_confidence: Number(fix.evidence_confidence || 0), site_fit_score: Number(fix.site_fit_score || 0), business_impact_score: Number(fix.business_impact_score || 0), reach_score: Number(fix.reach_score || 0), overall_priority_score: Number(fix.overall_priority_score || 0), metadata_state_counts: normalizeMetadataStateCounts(fix.metadata_state_counts), combined_rules: firstArray([fix.combined_rules]).map(String).slice(0, 8), grouping_explanation: cleanString(fix.grouping_explanation), page_count: Number(fix.page_count || affectedPages.length || 1) };
}

function slimPage(page = {}) {
  return { url: page.url || page.final_url || "", final_url: page.final_url || page.url || "", path: page.path || "", source: page.source || "", discovered_from: firstArray([page.discovered_from]).slice(0, 8), source_pages: firstArray([page.source_pages]).slice(0, 12), link_text_samples: firstArray([page.link_text_samples]).slice(0, 8), url_confidence: page.url_confidence || "", url_suspicion_reasons: firstArray([page.url_suspicion_reasons]).slice(0, 8), route_boundary_candidate: Boolean(page.route_boundary_candidate), route_boundary_type: page.route_boundary_type || "", status_code: Number(page.status_code || 0), fetch_error: page.fetch_error || "", title: clampText(page.title || "", 160), meta_description: clampText(page.meta_description || "", 240), meta_description_state: page.meta_description_state || "", meta_description_element_count: Number(page.meta_description_element_count || 0), meta_description_values: firstArray([page.meta_description_values]).map(String).slice(0, 8), meta_description_duplicate: Boolean(page.meta_description_duplicate), metadata_evidence_version: page.metadata_evidence_version || "", title_evidence_version: page.title_evidence_version || "", title_evidence_context: page.title_evidence_context || {}, h1: clampText(page.h1 || "", 160), h1_count: Number(page.h1_count || 0), canonical: page.canonical || page.canonical_url || "", canonical_url: page.canonical_url || page.canonical || "", canonical_status: page.canonical_status || "", robots: page.robots || page.robots_meta || "", robots_meta: page.robots_meta || page.robots || "", robots_indexability_status: page.robots_indexability_status || "", word_count: Number(page.word_count || 0), html_size: Number(page.html_size || 0), image_count: Number(page.image_count || 0), image_missing_alt_count: Number(page.image_missing_alt_count || page.missing_alt_image_count || 0), missing_alt_image_count: Number(page.missing_alt_image_count || page.image_missing_alt_count || 0), schema_count: Number(page.schema_count || 0), schema_types: firstArray([page.schema_types]).slice(0, 20), has_schema: Boolean(page.has_schema), internal_link_count: Number(page.internal_link_count || 0), external_link_count: Number(page.external_link_count || 0), indexable: page.indexable !== false, in_sitemap: Boolean(page.in_sitemap), is_scanner_blocked: Boolean(page.is_scanner_blocked), client_rendering_suspected: Boolean(page.client_rendering_suspected), page_template_family: page.page_template_family || classifyTemplateFamily(page.url || page.final_url || ""), estimated_page_intent: page.estimated_page_intent || "", conversion_signals: firstArray([page.conversion_signals]).slice(0, 12), trust_signals: firstArray([page.trust_signals]).slice(0, 12) };
}

function slimAction(action = {}) {
  const developerOwned = needsDeveloperOwner(action);
  return { fix_id: action.fix_id || action.id || "", title: cleanString(action.title || action.issue_title || "Recommended action"), reason: cleanString(action.reason || action.why_it_matters || action.plain_english_summary || ""), priority: normalizeActionPriority(action.priority), plain_english_summary: cleanString(action.plain_english_summary || action.reason || ""), why_it_matters: cleanString(action.why_it_matters || action.reason || ""), what_to_do_steps: firstArray([action.what_to_do_steps, action.what_to_do, action.steps]).slice(0, 5).map(String), who_can_do_this: developerOwned ? "Your web person" : normalizeDisplayOwner(action.who_can_do_this || "You"), time_estimate: action.time_estimate || action.estimated_time || "", affected_pages: firstArray([action.affected_pages]).slice(0, 30) };
}

function slimTechnicalSummary(summary = {}, source = {}) {
  return { ...summary, audit_profile: summary.audit_profile || source?.audit_profile || "", scanner_version: summary.scanner_version || source?.scanner_version || source?.version || "", screaming_frog_lite_enabled: Boolean(summary.screaming_frog_lite_enabled || source?.screaming_frog_lite_enabled), pages_checked: Number(summary.pages_checked || summary.pages_crawled || source?.pages_crawled || 0), pages_crawled: Number(summary.pages_crawled || source?.pages_crawled || 0), pages_found: Number(summary.pages_found || source?.pages_found || 0), failed_pages: Number(summary.failed_pages || 0), verified_failed_pages: Number(summary.verified_failed_pages || source?.verified_failed_pages || source?.scan_summary?.verified_failed_pages || 0), suspicious_url_artifacts: Number(summary.suspicious_url_artifacts || source?.suspicious_url_artifacts || source?.scan_summary?.suspicious_url_artifacts || 0), route_boundary_risk: summary.route_boundary_risk || "", route_boundary_candidates_crawled: Number(summary.route_boundary_candidates_crawled || 0), duplicate_casing_routes: firstArray([summary.duplicate_casing_routes]).slice(0, 20), free_base44_subdomain: Boolean(summary.free_base44_subdomain), crawl_policy: summary.crawl_policy || source?.crawl_policy || {}, crawl_policy_source: source?.crawl_policy_source || summary.crawl_policy?.source || "", url_evidence_summary: summary.url_evidence_summary || source?.url_evidence_summary || {}, crawl_warnings: firstArray([summary.crawl_warnings, source?.crawl_warnings]).slice(0, 20) };
}

function slimScanSummary(summary = {}, healthScore = 0, pagesCrawled = 0, fixes = [], source = {}, summaryText = "") {
  return { ...summary, score: Number(summary.score || summary.health_score || healthScore || 0), health_score: Number(summary.health_score || summary.score || healthScore || 0), status_label: summary.status_label || scoreLabel(healthScore), plain_english_summary: normalizeCoverageSummary(summaryText || summary.plain_english_summary || summary.summary || "", pagesCrawled), pages_scanned: Number(summary.pages_scanned || pagesCrawled || 0), pages_failed: Number(summary.pages_failed || source?.technical_audit_summary?.failed_pages || 0), verified_failed_pages: Number(summary.verified_failed_pages || source?.verified_failed_pages || source?.technical_audit_summary?.verified_failed_pages || 0), suspicious_url_artifacts: Number(summary.suspicious_url_artifacts || source?.suspicious_url_artifacts || source?.technical_audit_summary?.suspicious_url_artifacts || 0), crawl_policy_source: summary.crawl_policy_source || source?.crawl_policy_source || source?.crawl_policy?.source || "", high_priority_count: fixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length, technical_issue_count: fixes.length };
}

function slimHealthReport(report = {}, summaryText = "", healthScore = 0) {
  return { scan_status: report.scan_status || "", review_confidence_state: report.review_confidence_state || "", score_is_provisional: Boolean(report.score_is_provisional), access_evidence_state: report.access_evidence_state || "", health_score: Number(report.health_score || report.score || healthScore || 0), health_grade: report.health_grade || report.grade || scoreLabel(healthScore), overall_explanation: summaryText || report.overall_explanation || report.summary || "", what_is_working: firstArray([report.what_is_working]).slice(0, 5), top_concerns: firstArray([report.top_concerns]).slice(0, 5), quick_wins: firstArray([report.quick_wins]).slice(0, 5), bigger_projects: firstArray([report.bigger_projects]).slice(0, 5), limitations: firstArray([report.limitations]).slice(0, 5), next_best_step: report.next_best_step || "" };
}

const META_DESCRIPTION_GAP_RULES = new Set(["missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable"]);
const META_DESCRIPTION_STATE_BY_RULE = {
  missing_meta_description: "missing",
  empty_meta_description: "empty",
  malformed_meta_description: "malformed",
};

function normalizeMetadataStateCounts(value = {}) {
  const input = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(input.missing || 0)),
    empty: Math.max(0, Number(input.empty || input.present_empty || 0)),
    malformed: Math.max(0, Number(input.malformed || 0)),
  };
}

function metadataStateCountsForFix(fix = {}) {
  const existing = normalizeMetadataStateCounts(fix.metadata_state_counts);
  if (existing.missing + existing.empty + existing.malformed > 0) return existing;
  const state = META_DESCRIPTION_STATE_BY_RULE[String(fix.rule || "").toLowerCase()];
  if (!state) return existing;
  const affectedCount = firstArray([fix.affected_pages]).length;
  const reportedCount = Math.max(Number(fix.page_count || 0), affectedCount, fix.page_url ? 1 : 0);
  return { ...existing, [state]: reportedCount };
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

function metaDescriptionGroupCopy(family) {
  const label = metaDescriptionFamilyLabel(family);
  return {
    title: `Add usable meta descriptions to ${label} pages`,
    explanation: "Some pages are missing the meta-description tag, while others output a blank or invalid value. Because these pages use the same page pattern, fix the shared template rather than editing every URL one by one.",
    why: "Meta descriptions often appear beneath page titles in search results. When one is missing or blank, search engines must create their own snippet from page content. That snippet may be less specific or persuasive, giving the site less control over how each page is presented and potentially reducing qualified clicks. Fixing the shared template improves many pages at once.",
    recommendation: "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
    grouping: `All affected URLs use the ${label} page pattern. One template correction may resolve the problem across the entire group.`,
  };
}

function groupAndSortFixes(fixes, options = {}) {
  const normalized = Array.isArray(fixes) ? fixes.map((fix) => applyBusinessPriorityRules(fix, options)) : [];
  const groups = new Map();
  const keep = [];
  for (const fix of normalized) {
    const affectedCount = firstArray([fix.affected_pages]).length;
    const family = fix.page_template_family || classifyTemplateFamily(fix.page_url || fix.affected_pages?.[0] || "");
    const isMetaDescriptionGap = META_DESCRIPTION_GAP_RULES.has(String(fix.rule || "").toLowerCase());
    const shouldGroup = isMetaDescriptionGap || affectedCount >= 3 || TEMPLATE_RULES.has(fix.rule) || (fix.is_low_value_page && isCosmeticRule(fix));
    if (!shouldGroup) { keep.push(fix); continue; }
    const groupedRule = isMetaDescriptionGap ? "meta_description_unusable" : (fix.rule || fix.category);
    const key = isMetaDescriptionGap ? `${groupedRule}|${family}` : `${groupedRule}|${family}|${fix.priority}`;
    const copy = isMetaDescriptionGap ? metaDescriptionGroupCopy(family) : null;
    const title = copy?.title || getTemplateGroupTitle(fix, family);
    const existing = groups.get(key) || { ...fix, id: stableId(`group_${key}`), fix_id: stableId(`group_${key}`), rule: groupedRule, page_url: "", title, issue_title: title, plain_english_explanation: copy?.explanation || getTemplateGroupExplanation(fix), plain_english_summary: copy?.explanation || getTemplateGroupExplanation(fix), why_it_matters: copy?.why || getTemplateGroupWhy(fix), recommendation: copy?.recommendation || getTemplateGroupRecommendation(fix), recommended_value: copy?.recommendation || getTemplateGroupRecommendation(fix), simple_next_step: copy?.recommendation || getTemplateGroupRecommendation(fix), grouping_explanation: copy?.grouping || "", combined_rules: [], metadata_state_counts: { missing: 0, empty: 0, malformed: 0 }, affected_pages: [], source_pages: [], link_text_samples: [], page_count: 0, difficulty: needsDeveloperOwner(fix) ? "developer" : fix.difficulty, status: needsDeveloperOwner(fix) ? "needs_developer" : fix.status, requires_developer: needsDeveloperOwner(fix) || fix.requires_developer, requires_approval: needsDeveloperOwner(fix) ? false : fix.requires_approval, who_can_do_this: needsDeveloperOwner(fix) ? "your_web_person" : fix.who_can_do_this };
    existing.affected_pages = unique([...existing.affected_pages, ...firstArray([fix.affected_pages]), fix.page_url].filter(Boolean).map(String)).slice(0, 150);
    existing.source_pages = unique([...firstArray([existing.source_pages]), ...firstArray([fix.source_pages])]).slice(0, 30);
    existing.link_text_samples = unique([...firstArray([existing.link_text_samples]), ...firstArray([fix.link_text_samples])]).slice(0, 20);
    existing.requires_developer = existing.requires_developer || needsDeveloperOwner(fix) || fix.requires_developer;
    if (existing.requires_developer) {
      existing.requires_approval = false;
      existing.difficulty = "developer";
      existing.status = "needs_developer";
      existing.who_can_do_this = "your_web_person";
    }
    if (isMetaDescriptionGap) {
      existing.priority = strongestPriority(existing.priority, fix.priority);
      existing.metadata_state_counts = addMetadataStateCounts(existing.metadata_state_counts, metadataStateCountsForFix(fix));
      existing.combined_rules = unique([...firstArray([existing.combined_rules]), ...firstArray([fix.combined_rules]), fix.rule].filter(Boolean).map(String));
      existing.page_count = Math.max(existing.affected_pages.length, metadataStateCountTotal(existing.metadata_state_counts));
    } else {
      existing.page_count = existing.affected_pages.length;
    }
    groups.set(key, existing);
  }
  return dedupeFixes([...keep, ...Array.from(groups.values())]).sort((a, b) => businessSortScore(b, options) - businessSortScore(a, options));
}

function applyBusinessPriorityRules(fix = {}, options = {}) {
  const url = fix.page_url || fix.affected_pages?.[0] || "";
  const lowValue = typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : isLowValuePage(url);
  const important = typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : isImportantBusinessPage(url, options);
  const developerOwned = needsDeveloperOwner(fix);
  let priority = normalizePriority(fix.priority);
  if (lowValue && isCosmeticRule(fix) && !important) priority = "low";
  if (important && priority === "low") priority = "medium";
  if (developerOwned && /route|index|canonical|schema|render|javascript|server|429|500|checkout|login|account/i.test(`${fix.rule} ${fix.title}`)) priority = priority === "low" ? "medium" : priority;
  return { ...fix, priority, requires_developer: developerOwned || fix.requires_developer, requires_approval: developerOwned ? false : fix.requires_approval, difficulty: developerOwned ? "developer" : fix.difficulty, status: developerOwned ? "needs_developer" : fix.status, who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this, business_importance: fix.business_importance || (important ? "important" : lowValue ? "low_value_archive" : "standard"), is_low_value_page: typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : lowValue, is_important_business_page: typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : important };
}

function buildTopActions({ finalFixes }) {
  const output = [];
  const seen = new Set();
  for (const fix of finalFixes) {
    const key = fix.fix_id || fix.id || fix.title;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(fixToAction(fix));
    if (output.length >= 5) break;
  }
  return output;
}

function hydrateActionWithFix(action = {}, fix = null) {
  const source = fix || action;
  const title = cleanString(action.title || action.issue_title || fix?.title || fix?.issue_title || "Recommended action");
  const steps = firstArray([action.what_to_do_steps, action.what_to_do, action.steps, fix?.what_to_do_steps, fix?.what_to_do]).slice(0, 5).map(String);
  const developerOwned = needsDeveloperOwner({ ...source, title, what_to_do_steps: steps, who_can_do_this: action.who_can_do_this });
  return { fix_id: action.fix_id || action.id || fix?.fix_id || fix?.id || "", title, reason: cleanString(action.reason || action.why_it_matters || action.plain_english_summary || fix?.why_it_matters || fix?.plain_english_explanation || ""), priority: normalizeActionPriority(action.priority || fix?.priority), plain_english_summary: cleanString(action.plain_english_summary || fix?.plain_english_explanation || action.reason || ""), why_it_matters: cleanString(action.why_it_matters || action.reason || fix?.why_it_matters || ""), what_to_do_steps: steps.length > 0 ? steps : firstArray([fix?.what_to_do_steps, fix?.what_to_do]).slice(0, 5).map(String), who_can_do_this: developerOwned ? "Your web person" : normalizeDisplayOwner(action.who_can_do_this || fix?.who_can_do_this || "You"), time_estimate: action.time_estimate || action.estimated_time || fix?.time_estimate || fix?.estimated_time || "", affected_pages: firstArray([action.affected_pages, fix?.affected_pages]).slice(0, 30) };
}

function findSimilarFix(action = {}, fixes = []) {
  const title = String(action.title || action.issue_title || "").toLowerCase();
  const affected = firstArray([action.affected_pages]).map(String);
  return fixes.find((fix) => affected.some((page) => firstArray([fix.affected_pages]).includes(page))) || fixes.find((fix) => title && String(fix.title || fix.issue_title || "").toLowerCase().includes(title.slice(0, 24)));
}

function fixToAction(fix = {}) {
  return hydrateActionWithFix({ fix_id: fix.fix_id || fix.id, title: fix.title || fix.issue_title, reason: fix.why_it_matters || fix.plain_english_explanation, priority: normalizePriority(fix.priority), affected_pages: fix.affected_pages || [] }, fix);
}

function dedupeFixes(fixes) { const seen = new Set(); const output = []; for (const fix of fixes || []) { const key = fix.fix_id || fix.id || `${fix.rule}|${fix.title}|${fix.page_url}|${firstArray([fix.affected_pages]).join(",")}`; if (seen.has(key)) continue; seen.add(key); output.push(fix); } return output; }
function normalizeCoverageSummary(summary, pagesCrawled) { const text = String(summary || ""); const count = Number(pagesCrawled || 0); if (!count || !text) return text; return text.replace(/The scanner reviewed\s+\d+\s+pages/gi, `The scanner reviewed ${count} pages`).replace(/scanner reviewed\s+\d+\s+pages/gi, `scanner reviewed ${count} pages`); }
function normalizeSiteFingerprint(fingerprint = {}, pages = []) { const pathText = pages.map((page) => `${page.url || ""} ${page.final_url || ""} ${page.estimated_page_intent || ""}`).join(" ").toLowerCase(); const bookingHits = countIncludes(pathText, "booking") + countIncludes(pathText, "reservation") + countIncludes(pathText, "ticket") + countIncludes(pathText, "checkout") + countIncludes(pathText, "voucher"); const energyHits = countIncludes(pathText, "energie") + countIncludes(pathText, "énergie") + countIncludes(pathText, "electricite") + countIncludes(pathText, "électricité") + countIncludes(pathText, "gaz") + countIncludes(pathText, "fournisseur"); if (energyHits >= 3 && (!fingerprint.primary_archetype || fingerprint.primary_archetype === "finance_insurance_lead_gen" || fingerprint.vertical === "insurance_finance")) return { ...fingerprint, primary_archetype: "utilities_comparison_lead_gen", vertical: "utilities_comparison_lead_gen", archetype_label: "utilities / energy comparison lead generation", vertical_label: "utilities / energy comparison lead generation", business_model: "quote_or_comparison_lead_gen", vertical_confidence: Math.max(Number(fingerprint.vertical_confidence || 0), 0.85) }; if (bookingHits >= 5 && (!fingerprint.vertical || fingerprint.vertical === "ecommerce")) return { ...fingerprint, primary_archetype: "booking_experiences_marketplace", vertical: "travel_booking", archetype_label: "booking / experiences marketplace", vertical_label: "booking / experiences marketplace", business_model: "booking_or_reservation", vertical_confidence: Math.max(Number(fingerprint.vertical_confidence || 0), 0.85) }; return fingerprint; }

function getTemplateGroupTitle(fix = {}, family = "template") {
  const rule = String(fix.rule || "").toLowerCase();
  const label = String(family || "template").replace(/_/g, " ");
  if (/rate_limited|blocked|429/.test(rule)) return `Check ${label} pages blocked by rate limiting`;
  if (/broken_page|404|410|server_error|5\d\d/.test(rule)) return fix.title || fix.issue_title || defaultTitle(fix.category);
  const value = `${fix.rule || ""} ${fix.category || ""} ${fix.title || ""}`.toLowerCase();
  if (value.includes("client") || value.includes("javascript") || value.includes("render")) return `Fix crawlable HTML for ${label} pages`;
  if (value.includes("route") || value.includes("index")) return `Review route-boundary indexing for ${label} pages`;
  if (value.includes("schema")) return `Add structured data to ${label} templates`;
  if (value.includes("h1")) return `Fix missing H1 headings on ${label} templates`;
  if (value.includes("alt")) return `Batch image descriptions on ${label} pages`;
  if (value.includes("description")) return `Batch meta descriptions on ${label} pages`;
  return `Fix repeated ${label} template issue`;
}

function getTemplateGroupExplanation(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Several similar business-critical pages appear to rely on JavaScript for their main content. Treat this as one template rendering issue, not many separate page edits."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Several checkout, login, account, cart, dashboard, or app-like routes need one route-boundary review."; return "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page."; }
function getTemplateGroupWhy(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Search engines and AI crawlers may not see the booking, listing, product, supplier, or comparison content if it only appears after JavaScript runs."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Private or checkout/app routes in search can create duplicate, low-trust, or sensitive public pages and can confuse crawlers about what should rank."; return "Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns."; }
function getTemplateGroupRecommendation(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to check whether the main content is visible in page source. Add server-side rendering, pre-rendering, or crawlable fallback HTML for the affected template."; if (/schema/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to add the right structured data once at the shared template level, then test a few affected pages."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to require login, add noindex, or keep private/checkout/account routes out of public search while leaving true public pages crawlable."; return "Fix one representative page/template first, then roll out the same rule across the affected group."; }

function businessSortScore(fix = {}, options = {}) { let score = Number(fix.overall_priority_score || 0); const priorityBonus = { critical: 1000, high: 800, medium: 500, low: 100 }[normalizePriority(fix.priority)] || 300; score += priorityBonus; if (fix.requires_developer && /client|render|javascript|schema|canonical|server|firewall|blocked|429|route|index|checkout|login|account/i.test(`${fix.rule} ${fix.title}`)) score += 130; if (fix.business_importance === "money_page" || fix.is_important_business_page) score += 120; if (isImportantBusinessPage(fix.page_url || fix.affected_pages?.[0] || "", options)) score += 100; if (fix.is_low_value_page || isLowValuePage(fix.page_url || fix.affected_pages?.[0] || "")) score -= 180; if (fix.url_confidence === "crawler_artifact") score -= 300; if ((fix.affected_pages || []).length > 3) score += Math.min(90, fix.affected_pages.length * 4); return score; }
function needsDeveloperOwner(item = {}) { const value = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.reason || ""} ${item.recommendation || ""} ${item.recommended_value || ""} ${firstArray([item.what_to_do_steps, item.what_to_do]).join(" ")} ${item.who_can_do_this || ""} ${item.primary_defect_class || ""}`.toLowerCase(); if (item.requires_developer || item.difficulty === "developer" || item.status === "needs_developer" || value.includes("your_web_person")) return true; return /developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard/.test(value); }
function normalizeOwner(value) { const owner = String(value || "").toLowerCase(); if (owner.includes("web") || owner.includes("developer") || owner === "your_web_person") return "your_web_person"; return "you"; }
function normalizeDisplayOwner(value) { return normalizeOwner(value) === "your_web_person" ? "Your web person" : "You"; }
function isCosmeticRule(fix = {}) { return /meta|title|description|thin_content|duplicate|image_alt|alt text|h1/.test(`${fix.rule || ""} ${fix.category || ""} ${fix.title || ""}`.toLowerCase()); }
function isImageAltTextIssue(fix = {}) { return /image_alt_text|image alt|alt text|missing alt|image description/i.test(`${fix.rule || ""} ${fix.category || ""} ${fix.title || ""} ${fix.issue_title || ""}`); }
function isLegalPagePath(url = "") { const path = String(url || "").toLowerCase().split("?")[0].split("#")[0]; return LEGAL_PAGE_RE.test(path); }
function isLowValuePage(url = "") { const value = String(url || "").toLowerCase(); const path = value.split("#")[0]; if (isLegalPagePath(path)) return false; if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; if (/\/page\/\d+(?:\/|$)/.test(path.split("?")[0])) return true; if (/[?&]page=\d+/.test(path)) return true; return LOW_VALUE_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }
function isImportantBusinessPage(url = "", options = {}) { const path = String(url || "").toLowerCase(); if (!path) return false; const requested = String(options.requestedPathPrefix || "").toLowerCase(); if (requested && (path === requested || path === `${requested}/` || path.endsWith(`${requested}/index.html`))) return true; return MONEY_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }
function classifyTemplateFamily(url = "") { const path = String(url || "").toLowerCase(); if (isLegalPagePath(path)) return "legal_info"; if (isRouteBoundaryPath(path)) return "route_boundary"; if (isLowValuePage(path)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/listing|show|category|categorie|collection|pass|ticket|stage|pilotage/.test(path)) return "category_listing"; if (/product|produit|\/p\//.test(path)) return "product_detail"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog/.test(path)) return "guide"; return "standard"; }
function inferCategory(rule = "", fix = {}) { const text = `${rule} ${fix.title || ""} ${fix.issue_title || ""}`.toLowerCase(); if (text.includes("schema") || text.includes("trust")) return "schema"; if (text.includes("canonical")) return "canonical"; if (text.includes("title")) return "meta_title"; if (text.includes("description") || text.includes("meta")) return "meta_description"; if (text.includes("alt")) return "image_alt_text"; if (text.includes("404") || text.includes("broken") || text.includes("blocked")) return "404_error"; if (text.includes("index") || text.includes("noindex")) return "indexability"; if (text.includes("render") || text.includes("javascript")) return "web_dev"; return "web_dev"; }
function defaultTitle(category = "") { const titles = { meta_title: "Improve search titles", meta_description: "Improve search descriptions", duplicate_content: "Review duplicate or repeated pages", canonical: "Review canonical URL setup", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", "404_error": "Fix pages that are not loading", web_dev: "Review website setup", image_alt_text: "Add useful image descriptions", indexability: "Review indexability settings" }; return titles[category] || "Review this recommendation"; }
function friendlyCustomerCategory(category = "") { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(priority)) return priority; return "medium"; }
function normalizeCmsValue(value) { const normalized = String(value || "custom").toLowerCase(); return CMS_OPTIONS.some((item) => item.value === normalized) ? normalized : "custom"; }
function createScanId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `scan_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
function normalizeWebsiteUrl(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).href; } catch { return ""; } }
function normalizeWebsiteKey(value) { try { const url = new URL(value); return `${url.hostname}${url.pathname}`.replace(/\/$/, "").toLowerCase(); } catch { return String(value || "").toLowerCase(); } }
function getRequestedPathPrefix(value) { try { const path = new URL(value).pathname || "/"; if (!path || path === "/") return ""; return path.replace(/\/$/, ""); } catch { return ""; } }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function splitLines(value) { return String(value || "").split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean).slice(0, 20); }
function firstArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function unique(values) { return Array.from(new Set((values || []).filter((value) => value !== undefined && value !== null && String(value).trim() !== ""))); }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function clampText(value, max) { const text = String(value || "").trim(); return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`; }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function scoreLabel(score) { const number = Number(score || 0); if (number >= 90) return "Excellent"; if (number >= 75) return "Good"; if (number >= 55) return "Fair"; return "Needs work"; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function getRecommendations(source = {}) { return firstArray([source?.cleaned_fixes, source?.recommendations, source?.fixes, source?.findings, source?.raw_fixes, source?.grouped_findings, source?.issues]); }
function getPages(source = {}) { return firstArray([source?.crawled_pages, source?.pages, source?.scanned_pages, source?.crawl_pages]); }
function getHealthScore(source = {}) { return getFirstNumber([source?.health_score, source?.seo_score, source?.scan_summary?.health_score, source?.scan_summary?.score, source?.website_health_report?.health_score, source?.website_health_report?.score]); }
function buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName }) { const label = scoreLabel(healthScore); const high = finalFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length; return `Your website health is currently rated as ${label}. FixList scanned ${pagesCrawled || 0} pages and found ${finalFixes.length} grouped recommendation${finalFixes.length === 1 ? "" : "s"}. ${high > 0 ? `${high} item${high === 1 ? "" : "s"} should be reviewed first.` : "Start with the first recommended fix."} CMS selected: ${cmsName}.`; }