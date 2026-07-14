from pathlib import Path


def replace_once(path, old, new):
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one match in {path}, found {text.count(old)} for {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once("scanner-api/app/scanner.py", 'VERSION = "python_scanner_v2_contract_parity"', 'VERSION = "python_scanner_v3_bounded_request"')
replace_once("scanner-api/app/scanner.py", '''SCAN_BUDGETS = {
    "basic": {"max_pages": 25, "timeout": 35},
    "quick": {"max_pages": 40, "timeout": 45},
    "deep": {"max_pages": 85, "timeout": 75},
    "advanced": {"max_pages": 150, "timeout": 90},
}''', '''SCAN_BUDGETS = {
    # timeout covers robots, sitemap discovery, crawling and post-processing.
    "basic": {"max_pages": 25, "timeout": 28, "fetch_timeout": 5, "max_sitemap_fetches": 4},
    "quick": {"max_pages": 40, "timeout": 40, "fetch_timeout": 6, "max_sitemap_fetches": 10},
    "deep": {"max_pages": 85, "timeout": 58, "fetch_timeout": 8, "max_sitemap_fetches": 24},
    "advanced": {"max_pages": 150, "timeout": 75, "fetch_timeout": 10, "max_sitemap_fetches": 40},
}''')
replace_once("scanner-api/app/scanner.py", '''async def run_scan(website_url: str, path_prefix: str | None = None, scan_mode: str = "advanced", concurrency: int = 8, **kwargs) -> dict:
    budget = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    start_url = normalize_url(website_url)''', '''async def run_scan(website_url: str, path_prefix: str | None = None, scan_mode: str = "advanced", concurrency: int = 8, **kwargs) -> dict:
    budget = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    scan_started_at = time.monotonic()
    deadline = scan_started_at + budget["timeout"]
    start_url = normalize_url(website_url)''')
replace_once("scanner-api/app/scanner.py", '''    async with httpx.AsyncClient(
        timeout=12,''', '''    async with httpx.AsyncClient(
        timeout=budget["fetch_timeout"],''')
replace_once("scanner-api/app/scanner.py", '''        sitemap_urls = await load_sitemap_urls(
            client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts, scope_evidence=scope_evidence
        )''', '''        sitemap_urls = await load_sitemap_urls(
            client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts,
            scope_evidence=scope_evidence, deadline=deadline,
            max_fetches=budget["max_sitemap_fetches"],
        )''')
replace_once("scanner-api/app/scanner.py", '''        deadline = time.monotonic() + budget["timeout"]
        state_lock = asyncio.Lock()''', '''        state_lock = asyncio.Lock()''')
replace_once("scanner-api/app/scanner.py", '''    crawl_warnings = []
    if scope_evidence.get("market_scope_required"):''', '''    elapsed_ms = round((time.monotonic() - scan_started_at) * 1000)
    deadline_reached = time.monotonic() >= deadline
    crawl_warnings = []
    if deadline_reached:
        crawl_warnings.append(f"The {scan_mode} scan reached its bounded {budget['timeout']}-second backend budget and returned collected evidence.")
    if scope_evidence.get("market_scope_required"):''')
replace_once("scanner-api/app/scanner.py", '''        "scan_mode": scan_mode,
        "pages_crawled": len(pages),''', '''        "scan_mode": scan_mode,
        "scanner_elapsed_ms": elapsed_ms,
        "scanner_total_budget_seconds": budget["timeout"],
        "scan_deadline_reached": deadline_reached,
        "pages_crawled": len(pages),''')
replace_once("scanner-api/app/scanner.py", '''            "scanner_version": VERSION,
            "scanner_profile": "python_screaming_frog_lite_v1",''', '''            "scanner_version": VERSION,
            "scanner_profile": "python_screaming_frog_lite_v1",
            "scanner_elapsed_ms": elapsed_ms,
            "scanner_total_budget_seconds": budget["timeout"],
            "scan_deadline_reached": deadline_reached,''')

replace_once("scanner-api/app/sitemap.py", "import gzip\nimport re", "import asyncio\nimport gzip\nimport re\nimport time")
replace_once("scanner-api/app/sitemap.py", '''async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None) -> list[str]:''', '''async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None, *, deadline: float | None = None, max_fetches: int | None = None) -> list[str]:''')
replace_once("scanner-api/app/sitemap.py", '''    roots: list[str] = []
    robots_url = f"{origin}/robots.txt"''', '''    fetch_limit = max(1, min(MAX_SITEMAP_FETCHES, int(max_fetches or MAX_SITEMAP_FETCHES)))
    roots: list[str] = []
    robots_url = f"{origin}/robots.txt"''')
replace_once("scanner-api/app/sitemap.py", '''        robots = await safe_get(client, robots_url)''', '''        robots = await _safe_get_before_deadline(client, robots_url, deadline)''')
replace_once("scanner-api/app/sitemap.py", '''        if len(fetched) >= MAX_SITEMAP_FETCHES:
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts)''', '''        if len(fetched) >= fetch_limit or _deadline_reached(deadline):
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts, deadline=deadline)''')
replace_once("scanner-api/app/sitemap.py", '''        if len(fetched) >= MAX_SITEMAP_FETCHES:
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts)''', '''        if len(fetched) >= fetch_limit or _deadline_reached(deadline):
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts, deadline=deadline)''')
replace_once("scanner-api/app/sitemap.py", '''async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict]) -> list[str]:''', '''async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict], *, deadline: float | None = None) -> list[str]:''')
replace_once("scanner-api/app/sitemap.py", '''        response = await safe_get(client, sitemap_url)''', '''        response = await _safe_get_before_deadline(client, sitemap_url, deadline)''')
replace_once("scanner-api/app/sitemap.py", '''def decode_sitemap_body(response: httpx.Response, sitemap_url: str) -> str:''', '''def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


async def _safe_get_before_deadline(client: httpx.AsyncClient, url: str, deadline: float | None):
    if deadline is None:
        return await safe_get(client, url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        return await asyncio.wait_for(safe_get(client, url), timeout=max(0.05, remaining))
    except asyncio.TimeoutError:
        return None


def decode_sitemap_body(response: httpx.Response, sitemap_url: str) -> str:''')

replace_once("scanner-api/app/main.py", "import os\nfrom typing", "import asyncio\nimport os\nfrom typing")
replace_once("scanner-api/app/main.py", 'SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")', 'SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")\nTRUST_DISCOVERY_TIMEOUTS = {"basic": 2.0, "quick": 3.0, "deep": 5.0, "advanced": 7.0}')
replace_once("scanner-api/app/main.py", '''        result = await enrich_scan_with_trust_pages(result)
        result = apply_indexability_quality_to_result(result)''', '''        trust_timeout = TRUST_DISCOVERY_TIMEOUTS.get(str(payload.scan_mode or "advanced").lower(), 7.0)
        try:
            result = await asyncio.wait_for(enrich_scan_with_trust_pages(result), timeout=trust_timeout)
        except asyncio.TimeoutError:
            warnings = list(result.get("crawl_warnings") or [])
            warnings.append("Bounded trust-page discovery timed out; existing crawl evidence was preserved.")
            result["crawl_warnings"] = warnings
            result["trust_page_discovery"] = {"version": "trust_page_discovery_v1", "attempted": True, "conclusive": False, "timed_out": True, "checked": 0, "responses_received": 0, "found": [], "found_urls": [], "evidence": []}
        result = apply_indexability_quality_to_result(result)''')

replace_once("scanner-api/app/review.py", 'REVIEW_VERSION = "python_review_v1_archetype_templates"', 'REVIEW_VERSION = "python_review_v2_structural_marketplace"')
replace_once("scanner-api/app/review.py", '''    ecommerce_paths = sum(count_includes(path_text, pattern) for pattern in ("/products/", "/product/", "/collections/", "/collection/", "/cart", "/checkout"))
    saas_paths = sum(count_includes(path_text, pattern) for pattern in ("/pricing", "/features", "/use-cases", "/solutions", "/login", "/signup", "/docs", "/api"))
    adjusted_scores = []
    for key, score in scores:
        if key == "ecommerce_specialty_retail" and ecommerce_paths < 2:
            score = min(score, 1.0)
        if key == "saas_app_membership" and saas_paths >= 2:
            score += 12
        adjusted_scores.append((key, score))''', '''    ecommerce_paths = sum(count_includes(path_text, pattern) for pattern in ("/products/", "/product/", "/collections/", "/collection/", "/cart", "/checkout", "/itm/", "/sch/", "/b/", "/buy/", "/shop/", "/seller/", "/listing/"))
    marketplace_signals = sum(count_includes(text, signal) for signal in ("ebay", "buy it now", "auction", "seller", "item number", "shop by category"))
    saas_paths = sum(count_includes(path_text, pattern) for pattern in ("/pricing", "/features", "/use-cases", "/solutions", "/login", "/signup", "/docs", "/api"))
    adjusted_scores = []
    for key, score in scores:
        if key == "ecommerce_specialty_retail":
            if ecommerce_paths < 2 and marketplace_signals < 2:
                score = min(score, 1.0)
            else:
                score += min(60, ecommerce_paths * 4 + marketplace_signals * 8)
        if key == "saas_app_membership":
            if saas_paths < 2:
                score = min(score, 1.0)
            else:
                score += 12
        adjusted_scores.append((key, score))''')

replace_once("base44/functions/runAdvancedScan/entry.ts", 'const VERSION = "runAdvancedScan_v21_python_first";', 'const VERSION = "runAdvancedScan_v22_python_required";')
replace_once("base44/functions/runAdvancedScan/entry.ts", 'const PYTHON_SCANNER_VERSION = "python_scanner_v2_contract_parity";', 'const PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request";')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''    const pythonAttempt = await tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs: pythonTimeoutMs });
    if (pythonAttempt.ok) return jsonResponse(toPythonAdvancedScanResponse(pythonAttempt.result, scanMode));

    const fallbackReason = pythonAttempt.reason || "Python scanner unavailable; used Deno fallback.";''', '''    const pythonAttempt = await tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs: pythonTimeoutMs });
    if (pythonAttempt.ok) return jsonResponse(toPythonAdvancedScanResponse(pythonAttempt.result, scanMode, body.scan_id || body.scan_run_id || ""));

    const fallbackReason = pythonAttempt.reason || "Python scanner unavailable.";
    const allowDenoFallback = body.allow_deno_fallback === true && body.require_python_scanner !== true;
    if (!allowDenoFallback) {
      return jsonResponse({ success: false, version: VERSION, error: "The Python scanner is unavailable, so FixList did not save a fallback result.", detail: fallbackReason, retryable: true, advanced_scan_backend: "python_scanner_api_unavailable", deno_fallback_used: false, release_gate_eligible: false, scanner_api_url_configured: pythonAttempt.configured, python_scanner_failure_code: pythonAttempt.failureCode || "unknown", scan_id: body.scan_id || body.scan_run_id || "", elapsed_ms: Date.now() - functionStartedAt }, 503);
    }''')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''      deno_fallback_used: true,
      scanner_api_url_configured: pythonAttempt.configured,''', '''      deno_fallback_used: true,
      scan_status: "incomplete_evidence",
      review_confidence_state: "deno_fallback_limited",
      score_is_provisional: true,
      release_gate_eligible: false,
      limitation: "The Python scanner was unavailable. This explicit Deno fallback is a limited diagnostic sample and must not be treated as a completed production audit.",
      scan_id: body.scan_id || body.scan_run_id || "",
      scanner_api_url_configured: pythonAttempt.configured,''')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''  if (!scannerUrl) return { ok: false, configured: false, reason: "SCANNER_API_URL/cloud_api is not configured." };
  if (!scannerKey) return { ok: false, configured: true, reason: "SCANNER_API_KEY is not configured." };''', '''  if (!scannerUrl) return { ok: false, configured: false, failureCode: "url_not_configured", reason: "SCANNER_API_URL/cloud_api is not configured." };
  if (!scannerKey) return { ok: false, configured: true, failureCode: "key_not_configured", reason: "SCANNER_API_KEY is not configured." };''')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''    if (!response.ok) return { ok: false, configured: true, reason: `Python scanner HTTP ${response.status}: ${String(result.detail || result.error || "request failed").slice(0, 180)}` };
    if (result.success === false) return { ok: false, configured: true, reason: `Python scanner returned success=false: ${String(result.error || "unknown error").slice(0, 180)}` };
    if (result.scanner_version !== PYTHON_SCANNER_VERSION) return { ok: false, configured: true, reason: `Python scanner version ${result.scanner_version || "missing"} did not match ${PYTHON_SCANNER_VERSION}.` };''', '''    if (!response.ok) return { ok: false, configured: true, failureCode: `http_${response.status}`, reason: `Python scanner HTTP ${response.status}: ${String(result.detail || result.error || "request failed").slice(0, 180)}` };
    if (result.success === false) return { ok: false, configured: true, failureCode: "scanner_success_false", reason: `Python scanner returned success=false: ${String(result.error || "unknown error").slice(0, 180)}` };
    if (result.scanner_version !== PYTHON_SCANNER_VERSION) return { ok: false, configured: true, failureCode: "version_mismatch", reason: `Python scanner version ${result.scanner_version || "missing"} did not match ${PYTHON_SCANNER_VERSION}.` };''')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''  } catch (error) {
    return { ok: false, configured: true, reason: `Python scanner request failed: ${String(error?.message || error || "unknown error").slice(0, 180)}` };
  }
}

function toPythonAdvancedScanResponse(result, scanMode) {''', '''  } catch (error) {
    const message = String(error?.message || error || "unknown error");
    const failureCode = error?.name === "AbortError" || /abort|timeout/i.test(message) ? "timeout" : "network_error";
    return { ok: false, configured: true, failureCode, reason: `Python scanner request failed: ${message.slice(0, 180)}` };
  }
}

function toPythonAdvancedScanResponse(result, scanMode, scanId = "") {''')
replace_once("base44/functions/runAdvancedScan/entry.ts", '''    audit_profile: result.audit_profile || result.scan_mode || scanMode || "advanced",
    technical_audit_summary: {''', '''    audit_profile: result.audit_profile || result.scan_mode || scanMode || "advanced",
    scan_id: scanId || result.scan_id || "",
    release_gate_eligible: true,
    technical_audit_summary: {''')

replace_once("src/components/scan/ScanWebsiteForm.jsx", 'const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";', 'const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";\nconst SCAN_RECORD_PREFIX = "seo_autopilot:scan:";')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''    let scanData = null;
    let aiData = null;
    let mergedFinal = null;
    setSubmitting(true);
    clearPreviousDashboardScan(normalizedUrl);
    // Durable scan history (ScanRun lifecycle) records in the background; it
    // resolves to null when persistence is unavailable and never blocks the scan.
    const scanRunPromise = beginScanRun({ websiteUrl: normalizedUrl, pathPrefix: requestedPathPrefix, scanMode, scanSource: "scan_website_page" }).catch(() => null);''', '''    let scanData = null;
    let aiData = null;
    let mergedFinal = null;
    let scanRunHandle = null;
    const localScanId = createScanId();
    let scanId = localScanId;
    setSubmitting(true);
    markDashboardScanStarted(normalizedUrl, localScanId);
    scanRunHandle = await beginScanRun({ websiteUrl: normalizedUrl, pathPrefix: requestedPathPrefix, scanMode, scanSource: "scan_website_page" }).catch(() => null);
    scanId = scanRunHandle?.id || localScanId;''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''        requested_at: new Date().toISOString(),
      };''', '''        requested_at: new Date().toISOString(),
        scan_id: scanId,
        scan_run_id: scanRunHandle?.id || "",
        require_python_scanner: true,
        allow_deno_fallback: false,
      };''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '      scanRunPromise.then((handle) => markScanRunReviewing(handle)).catch(() => {});', '      markScanRunReviewing(scanRunHandle).catch(() => {});')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix });
      saveScanForDashboard(mergedFinal);
      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      scanRunPromise.then((handle) => completeScanRun(handle, durableRecord)).catch(() => {});''', '''      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, scanId, scanRunId: scanRunHandle?.id || "" });
      saveScanForDashboard(mergedFinal, scanId);
      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      await completeScanRun(scanRunHandle, durableRecord).catch(() => null);''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '      navigate("/dashboard?scan=complete");', '      navigate(`/dashboard?scan=complete&scan_id=${encodeURIComponent(scanId)}`);')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '      scanRunPromise.then((handle) => failScanRun(handle, err)).catch(() => {});', '      failScanRun(scanRunHandle, err).catch(() => {});')
replace_once("src/components/scan/ScanWebsiteForm.jsx", 'function mergeScanAndAiReview({ scanData, aiData, websiteUrl, businessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix }) {', 'function mergeScanAndAiReview({ scanData, aiData, websiteUrl, businessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, scanId, scanRunId }) {')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''    id: `scan_${Date.now()}`,
    created_at: new Date().toISOString(),''', '''    id: scanId || createScanId(),
    scan_id: scanId || "",
    scan_run_id: scanRunId || "",
    created_at: new Date().toISOString(),''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''function saveScanForDashboard(scanRecord) {
  try {
    const normalizedRecord = slimScanRecord(normalizeScanRecordForStorage(scanRecord));
    const serialized = JSON.stringify(normalizedRecord);
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY].forEach((key) => window.localStorage.setItem(key, serialized));''', '''function saveScanForDashboard(scanRecord, scanId) {
  try {
    const normalizedRecord = slimScanRecord(normalizeScanRecordForStorage({ ...scanRecord, id: scanId || scanRecord?.id }));
    const serialized = JSON.stringify(normalizedRecord);
    const stableScanId = normalizedRecord.scan_id || normalizedRecord.scan_run_id || normalizedRecord.id;
    if (stableScanId) window.localStorage.setItem(`${SCAN_RECORD_PREFIX}${stableScanId}`, serialized);
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY].forEach((key) => window.localStorage.setItem(key, serialized));''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '      const nextHistory = [normalizedRecord, ...history.filter((item) => item?.website_key !== normalizedRecord.website_key)].slice(0, 8).map(slimScanRecord);', '      const nextHistory = [normalizedRecord, ...history.filter((item) => (item?.scan_id || item?.scan_run_id || item?.id) !== stableScanId)].slice(0, 20).map(slimScanRecord);')
replace_once("src/components/scan/ScanWebsiteForm.jsx", '''function clearPreviousDashboardScan(activeUrl) {
  try {
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY, DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY, SCAN_DEBUG_KEY].forEach((key) => window.localStorage.removeItem(key));
    if (activeUrl) {
      window.localStorage.setItem(ACTIVE_SCAN_URL_KEY, activeUrl);
      window.localStorage.setItem(ACTIVE_SCAN_STARTED_AT_KEY, new Date().toISOString());
    }
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not clear previous dashboard scan.", storageError);
  }
}''', '''function markDashboardScanStarted(activeUrl, scanId) {
  try {
    if (activeUrl) window.localStorage.setItem(ACTIVE_SCAN_URL_KEY, activeUrl);
    window.localStorage.setItem(ACTIVE_SCAN_STARTED_AT_KEY, new Date().toISOString());
    if (scanId) window.localStorage.setItem("seo_autopilot:active_scan_id", scanId);
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not mark the dashboard scan as started.", storageError);
  }
}''')
replace_once("src/components/scan/ScanWebsiteForm.jsx", 'function normalizeWebsiteUrl(value) {', '''function createScanId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `scan_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
function normalizeWebsiteUrl(value) {''')

replace_once("src/pages/FixList.jsx", 'import { useNavigate } from "react-router-dom";', 'import { useNavigate, useSearchParams } from "react-router-dom";')
replace_once("src/pages/FixList.jsx", 'const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";', 'const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";\nconst SCAN_RECORD_PREFIX = "seo_autopilot:scan:";')
replace_once("src/pages/FixList.jsx", '''export default function FixList() {
  const navigate = useNavigate();
  const [scanRecord, setScanRecord] = useState(() => readBestScanRecord());''', '''export default function FixList() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedScanId = searchParams.get("scan_id") || "";
  const [scanRecord, setScanRecord] = useState(() => readBestScanRecord(requestedScanId));''')
replace_once("src/pages/FixList.jsx", '''  function reloadScan() {
    const next = readBestScanRecord();''', '''  function reloadScan() {
    const next = readBestScanRecord(requestedScanId);''')
replace_once("src/pages/FixList.jsx", '''  }, []);''', '''  }, [requestedScanId]);''')
replace_once("src/pages/FixList.jsx", '''function readBestScanRecord() {
  const candidates = [];''', '''function readBestScanRecord(requestedScanId = "") {
  if (requestedScanId) {
    const direct = safeParseLocalStorage(`${SCAN_RECORD_PREFIX}${requestedScanId}`);
    if (isUsefulScanCandidate(direct)) return normalizeStoredScanCandidate(direct);
  }
  const candidates = [];''')
replace_once("src/pages/FixList.jsx", '''  const valid = candidates.filter(Boolean).map(normalizeStoredScanCandidate).filter(isUsefulScanCandidate).sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
  return valid[0] || null;''', '''  const valid = candidates.filter(Boolean).map(normalizeStoredScanCandidate).filter(isUsefulScanCandidate).sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
  if (requestedScanId) {
    const exact = valid.find((item) => (item.scan_id || item.scan_run_id || item.id) === requestedScanId);
    if (exact) return exact;
  }
  return valid[0] || null;''')

Path("scanner-api/tests/test_production_release_recovery.py").write_text('''from app.review import run_review
from app.scanner import SCAN_BUDGETS, VERSION


def test_quick_budget_leaves_time_for_base44_response_reserve():
    assert VERSION == "python_scanner_v3_bounded_request"
    assert SCAN_BUDGETS["quick"]["timeout"] <= 40
    assert SCAN_BUDGETS["quick"]["fetch_timeout"] <= 6
    assert SCAN_BUDGETS["quick"]["max_sitemap_fetches"] <= 10


def test_ebay_marketplace_structure_is_not_classified_as_saas():
    pages = [
        {"url": "https://www.ebay.com/itm/123456", "status_code": 200, "title": "Buy it now", "h1": "Vintage camera", "meta_description": "Seller listing", "canonical": "https://www.ebay.com/itm/123456", "h1_count": 1},
        {"url": "https://www.ebay.com/sch/i.html?_nkw=camera", "status_code": 200, "title": "Shop by category", "h1": "Camera auctions", "meta_description": "Items from sellers", "canonical": "https://www.ebay.com/sch/i.html?_nkw=camera", "h1_count": 1},
        {"url": "https://www.ebay.com/b/Electronics/293", "status_code": 200, "title": "Electronics", "h1": "Electronics", "meta_description": "Buy products", "canonical": "https://www.ebay.com/b/Electronics/293", "h1_count": 1},
    ]
    result = run_review({"website_url": "https://www.ebay.com/", "pages_found": 900, "pages_crawled": 3, "pages": pages})
    fingerprint = result["site_fingerprint"]
    assert fingerprint["primary_archetype"] == "ecommerce_specialty_retail"
    assert fingerprint["business_model"] == "catalog_or_ecommerce"
''', encoding="utf-8")

Path("tests/frontend/production-release-recovery.test.mjs").write_text('''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const advanced = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");
const scannerForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

test("normal scans require Python and do not silently save Deno fallback", () => {
  assert.match(scannerForm, /require_python_scanner: true/);
  assert.match(scannerForm, /allow_deno_fallback: false/);
  assert.match(advanced, /did not save a fallback result/);
  assert.match(advanced, /python_scanner_failure_code/);
  assert.match(advanced, /release_gate_eligible: false/);
});

test("scan results are stored and routed by stable scan ID", () => {
  assert.match(scannerForm, /const SCAN_RECORD_PREFIX = "seo_autopilot:scan:"/);
  assert.match(scannerForm, /scan_id: scanId/);
  assert.match(scannerForm, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
  assert.match(scannerForm, /localStorage\.setItem\(`\$\{SCAN_RECORD_PREFIX\}\$\{stableScanId\}`/);
  assert.doesNotMatch(scannerForm, /function clearPreviousDashboardScan/);
  assert.match(fixList, /searchParams\.get\("scan_id"\)/);
  assert.match(fixList, /readBestScanRecord\(requestedScanId\)/);
});
''', encoding="utf-8")
