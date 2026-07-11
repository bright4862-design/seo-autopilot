import asyncio
import hashlib
import re
import time
from urllib.parse import urldefrag, urlparse

import httpx

from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact
from .extract import classify_template, extract_links, extract_page
from .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls
from .security import is_public_http_url, safe_get
from .sitemap import load_sitemap_urls

VERSION = "python_scanner_v2_contract_parity"

# The Python crawler does not derive an AI crawl policy (no InvokeLLM here), but it
# still emits the policy contract so AI Review keeps provenance. source="disabled"
# mirrors the Deno path when policy derivation is off.
DEFAULT_POLICY = {
    "rendering_mode": "unknown",
    "platform_guess": "",
    "priority_boost_patterns": [],
    "priority_deprioritize_patterns": [],
    "skip_patterns": [],
    "source": "disabled",
    "error": "",
}

SCAN_BUDGETS = {
    "basic": {"max_pages": 25, "timeout": 35},
    "quick": {"max_pages": 40, "timeout": 45},
    "deep": {"max_pages": 85, "timeout": 75},
    "advanced": {"max_pages": 150, "timeout": 90},
}

SITEMAP_DISCOVERY_LIMIT = 5000

TRUST_PATHS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv"]


async def run_scan(website_url: str, path_prefix: str | None = None, scan_mode: str = "advanced", concurrency: int = 8, **kwargs) -> dict:
    budget = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    start_url = normalize_url(website_url)
    if not start_url:
        return {"success": False, "version": VERSION, "error": "Missing or invalid website_url."}
    if not is_public_http_url(start_url):
        return {"success": False, "version": VERSION, "error": "website_url must resolve to a public host."}

    parsed_start = urlparse(start_url)
    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"
    prefix = normalize_prefix(path_prefix or parsed_start.path or "/")

    pages: list[dict] = []
    queue: list[str] = []
    queued: set[str] = set()
    seen: set[str] = set()
    discovery: dict[str, dict] = {}
    artifacts: list[dict] = []

    def enqueue(url: str, source: str, source_page: str = "", link_text: str = "") -> None:
        clean = normalize_url(url)
        if not clean:
            if is_artifact_url(url):
                record_artifact(artifacts, url, source, source_page, link_text)
            return
        if is_artifact_url(clean):
            record_artifact(artifacts, clean, source, source_page, link_text)
            return
        if not same_origin(clean, origin):
            return
        if prefix and prefix != "/" and not (urlparse(clean).path or "/").startswith(prefix):
            return
        if clean in queued or clean in seen:
            merge_discovery(discovery.setdefault(clean, empty_discovery()), source, source_page, link_text)
            return
        queued.add(clean)
        queue.append(clean)
        merge_discovery(discovery.setdefault(clean, empty_discovery()), source, source_page, link_text)

    enqueue(start_url, "seed")

    async with httpx.AsyncClient(
        timeout=12,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"},
    ) as client:
        max_pages = budget["max_pages"]
        sitemap_urls = await load_sitemap_urls(client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts)
        family_of = lambda url: classify_template(urlparse(url).path or "/")
        path_of = lambda url: urlparse(url).path or "/"
        sampled_sitemap_urls = select_balanced_urls(sitemap_urls, family_of, path_of, max(0, max_pages - 1))
        sampling_evidence = sampling_report(sitemap_urls, sampled_sitemap_urls, family_of, path_of)
        for url in sampled_sitemap_urls:
            enqueue(url, "sitemap", "/sitemap.xml", "")

        deadline = time.monotonic() + budget["timeout"]
        state_lock = asyncio.Lock()
        crawl_state = {"claimed": 0, "in_flight": 0}

        async def worker() -> None:
            while True:
                target = None
                snapshot = None
                async with state_lock:
                    if time.monotonic() >= deadline or crawl_state["claimed"] >= max_pages:
                        return
                    while queue:
                        candidate = queue.pop(0)
                        queued.discard(candidate)
                        if candidate in seen:
                            continue
                        target = candidate
                        break
                    if target is None:
                        # Nothing queued: stop only when no other worker might enqueue more.
                        if crawl_state["in_flight"] == 0:
                            return
                    else:
                        seen.add(target)
                        crawl_state["claimed"] += 1
                        crawl_state["in_flight"] += 1
                        # Snapshot discovery lists so a concurrent merge can't mutate mid-read.
                        record = discovery.get(target, empty_discovery())
                        snapshot = {key: list(value) for key, value in record.items()}
                if target is None:
                    await asyncio.sleep(0.01)
                    continue

                page = None
                discovered = []
                try:
                    page = await fetch_and_extract(client, target, snapshot)
                    html = page.pop("_html", "")
                    # Parse links OUTSIDE the lock (CPU-bound) so workers don't block each other.
                    discovered = extract_links(html, page.get("final_url") or target) if (page.get("status_code") == 200 and html) else []
                except Exception:
                    page = extract_page("", target, target, 0, "", snapshot, fetch_error="worker_processing_failed")
                    discovered = []
                finally:
                    async with state_lock:
                        if page is not None:
                            pages.append(page)
                        crawl_state["in_flight"] -= 1
                        for link in discovered:
                            if len(queue) + len(seen) >= max_pages * 8:
                                break
                            enqueue(link["href"], "internal_link", page.get("path") or "", link.get("text") or "")

        workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]
        await asyncio.gather(*workers)

    findings = build_findings(pages)
    findings.extend(duplicate_casing_findings(pages))
    grouped = group_findings(findings)
    verified_failed = [page_evidence(page) for page in pages if is_verified_failed(page)]
    artifacts = dedupe_artifacts(artifacts)[:MAX_ARTIFACT_EVIDENCE]
    health_score = calculate_health_score(pages, grouped)
    pages_found = max(len(pages), len(pages) + len(queue), len(seen) + len(queue))

    return {
        "success": True,
        "version": VERSION,
        "scanner_version": VERSION,
        "scanner_profile": "python_screaming_frog_lite_v1",
        "sampling_version": SAMPLING_VERSION,
        "sampling_evidence": sampling_evidence,
        "screaming_frog_lite_enabled": True,
        "website_url": start_url,
        "normalized_url": start_url,
        "scan_mode": scan_mode,
        "pages_crawled": len(pages),
        "pages_found": pages_found,
        "queued_remaining": len(queue),
        "pages": pages,
        "crawled_pages": pages,
        "raw_findings": findings,
        "grouped_findings": grouped,
        "findings": grouped,
        "recommendations": grouped,
        "crawl_policy": DEFAULT_POLICY,
        "crawl_policy_source": DEFAULT_POLICY["source"],
        "health_score": health_score,
        "scan_summary": build_scan_summary(pages, grouped, health_score, pages_found, len(artifacts)),
        "verified_failed_pages": verified_failed,
        "suspicious_url_artifacts": artifacts,
        "verified_failed_page_count": len(verified_failed),
        "suspicious_url_artifact_count": len(artifacts),
        "url_evidence_summary": build_evidence_summary(pages, len(artifacts)),
        "technical_audit_summary": {
            "scanner_version": VERSION,
            "pages_crawled": len(pages),
            "pages_found": pages_found,
            "failed_pages": sum(1 for page in pages if page.get("status_code", 0) >= 400 or page.get("fetch_error")),
            "verified_failed_pages": len(verified_failed),
            "suspicious_url_artifacts": len(artifacts),
            "url_evidence_summary": build_evidence_summary(pages, len(artifacts)),
            "crawl_policy": DEFAULT_POLICY,
            "crawl_policy_source": DEFAULT_POLICY["source"],
            "duplicate_casing_routes": detect_duplicate_casing_routes(pages),
            "screaming_frog_lite_enabled": True,
        },
        "crawl_warnings": [],
    }


async def fetch_and_extract(client: httpx.AsyncClient, url: str, discovery: dict) -> dict:
    if not is_public_http_url(url):
        return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_host")
    try:
        response = await safe_get(client, url)
        if response is None:
            return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_redirect")
        content_type = response.headers.get("content-type", "")
        html = response.text if "html" in content_type or "xml" in content_type or not content_type else ""
        page = extract_page(html, url, str(response.url), response.status_code, content_type, discovery)
        page["_html"] = html
        return page
    except Exception as exc:
        return extract_page("", url, url, 0, "", discovery, fetch_error=str(exc)[:220])


def build_findings(pages: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for page in pages:
        path = page.get("path") or "/"
        if page.get("url_confidence") == "crawler_artifact":
            continue
        if str(page.get("fetch_error") or "").startswith("blocked_"):
            continue
        status_code = int(page.get("status_code") or 0)
        if status_code >= 400 or page.get("fetch_error"):
            findings.append(create_finding(
                rule="rate_limited_page" if status_code == 429 else "failed_page",
                category="web_dev" if status_code == 429 else "404_error",
                priority="high" if status_code == 429 or status_code >= 500 else "medium",
                title="Check pages blocked by rate limiting" if status_code == 429 else "Fix pages that are not loading",
                page_url=path,
                current_value=page.get("fetch_error") or f"HTTP {status_code}",
                explanation="The page did not load cleanly during the scan and has a real discovery source.",
                recommendation="Check whether the page should exist, redirect it, or fix the server/access issue.",
                difficulty="developer",
                source_pages=page.get("source_pages", []),
                link_text_samples=page.get("link_text_samples", []),
            ))
            continue
        if not page.get("title"):
            findings.append(create_finding("missing_title", "meta_title", "medium", "Add a clear search title", path, explanation="This page is missing a title.", recommendation="Add a short, specific page title."))
        if not page.get("meta_description") and page.get("estimated_page_intent") != "internal_or_auth":
            findings.append(create_finding("missing_meta_description", "meta_description", "medium", "Add a clear search description", path, explanation="This page is missing a meta description.", recommendation="Add a short description that explains the page and why someone should click."))
        if page.get("h1_count", 0) == 0 and page.get("estimated_page_intent") != "internal_or_auth":
            findings.append(create_finding("missing_h1", "thin_content", "medium", "Add one clear page heading", path, explanation="The page does not have a clear H1 heading.", recommendation="Add one main heading that matches the page purpose."))
        if page.get("h1_count", 0) > 1:
            findings.append(create_finding("multiple_h1", "thin_content", "low", "Use one main page heading", path, explanation="The page has more than one H1 heading.", recommendation="Keep one H1 as the main page heading and make the rest H2/H3 headings."))
        if not page.get("canonical") and page.get("indexable"):
            findings.append(create_finding("canonical_missing", "canonical", "medium", "Add a canonical URL", path, explanation="The page does not expose a canonical URL.", recommendation="Add a self-referencing canonical or point to the preferred version.", difficulty="developer"))
        missing_alt = int(page.get("image_missing_alt_count") or 0)
        if missing_alt > 0:
            findings.append(create_finding("image_alt_text", "image_alt_text", "medium" if missing_alt >= 10 else "low", "Add useful image descriptions", path, current_value=f"{missing_alt} images missing alt text", explanation="Some meaningful images may not have text descriptions.", recommendation="Add short, specific alt text to meaningful images."))
    return findings


def create_finding(rule: str, category: str, priority: str, title: str, page_url: str, current_value: str = "", explanation: str = "", recommendation: str = "", difficulty: str = "easy", source_pages: list[str] | None = None, link_text_samples: list[str] | None = None) -> dict:
    developer = difficulty == "developer" or any(token in f"{rule} {category} {title}" for token in ["429", "schema", "canonical", "web_dev"])
    finding_id = stable_id(f"{rule}|{page_url}|{title}")
    return {
        "id": finding_id,
        "fix_id": finding_id,
        "rule": rule,
        "category": category,
        "customer_category": friendly_category(category),
        "priority": priority,
        "difficulty": "developer" if developer else difficulty,
        "status": "needs_developer" if developer else "needs_approval",
        "title": title,
        "issue_title": title,
        "plain_english_explanation": explanation,
        "plain_english_summary": explanation,
        "why_it_matters": explanation,
        "current_value": current_value,
        "recommended_value": recommendation,
        "recommendation": recommendation,
        "ai_recommendation": recommendation,
        "page_url": page_url,
        "affected_pages": [page_url],
        "page_template_family": classify_template(page_url),
        "primary_defect_class": "blocked_access" if ("429" in rule or "blocked" in rule) else ("structural" if developer else "content"),
        "source_pages": list(dict.fromkeys(source_pages or [])),
        "link_text_samples": list(dict.fromkeys(link_text_samples or [])),
        "requires_developer": developer,
        "requires_approval": not developer,
        "can_auto_fix": False,
        "who_can_do_this": "your_web_person" if developer else "you",
        "confidence_score": 88,
    }


FAILURE_RULES = {"rate_limited_page", "failed_page", "server_error", "404_error", "410_error"}
TEMPLATE_RULES = {"client_rendering", "canonical_missing", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description"}
GROUP_MIN_AFFECTED = 3


def humanize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", str(value or "template"))).strip()


def grouping_key(finding: dict) -> str:
    family = classify_template(finding.get("page_url") or (finding.get("affected_pages") or [""])[0] or "")
    rule = finding.get("rule", "")
    if rule in FAILURE_RULES:
        return f"failure|{rule}|{family}"
    if rule in TEMPLATE_RULES:
        return f"template|{rule}|{family}"
    return ""


def group_template_title(rule: str, family: str) -> str:
    fam = humanize(family)
    if rule == "schema":
        return f"Add structured data to {fam} templates"
    if rule == "image_alt_text":
        return f"Batch image descriptions on {fam} pages"
    if rule == "missing_meta_description":
        return f"Batch meta descriptions on {fam} pages"
    if rule == "missing_h1":
        return f"Batch page headings on {fam} pages"
    if rule == "canonical_missing":
        return f"Add canonical URLs across {fam} templates"
    return f"Fix repeated {fam} template issue"


def group_findings(findings: list[dict]) -> list[dict]:
    direct: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        key = grouping_key(finding)
        if not key:
            direct.append(finding)
            continue
        groups.setdefault(key, []).append(finding)

    for key, members in groups.items():
        affected = _unique_nonempty([p for f in members for p in (f.get("affected_pages") or [f.get("page_url")])])[:150]
        # Only collapse into a template card when multiple pages share the issue.
        if len(affected) < GROUP_MIN_AFFECTED:
            direct.extend(members)
            continue
        sample = members[0]
        family = classify_template(sample.get("page_url") or "")
        blocked = key.startswith("failure|rate_limited_page") or sample.get("rule") == "rate_limited_page"
        if blocked:
            title = "Check pages blocked by rate limiting"
            explanation = "Several similar pages returned HTTP 429 or rate limiting. Treat this as one crawler-access problem."
            recommendation = "Ask your web person to check server, CDN, firewall, and rate-limit logs. Confirm Googlebot and normal users can access the affected URLs."
        else:
            title = group_template_title(sample.get("rule", ""), family)
            explanation = "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page."
            recommendation = "Fix one representative page/template first, then roll out the same rule across the affected group."
        group_id = stable_id(f"group|{key}")
        grouped = dict(sample)
        grouped.update({
            "id": group_id,
            "fix_id": group_id,
            "page_url": "",
            "title": title,
            "issue_title": title,
            "plain_english_explanation": explanation,
            "plain_english_summary": explanation,
            "why_it_matters": explanation,
            "recommended_value": recommendation,
            "recommendation": recommendation,
            "ai_recommendation": recommendation,
            "priority": "high" if blocked else ("medium" if sample.get("priority") == "high" else sample.get("priority")),
            "difficulty": "developer" if blocked else sample.get("difficulty"),
            "requires_developer": blocked or sample.get("requires_developer", False),
            "who_can_do_this": "your_web_person" if (blocked or sample.get("requires_developer")) else sample.get("who_can_do_this"),
            "affected_pages": affected,
            "page_count": len(affected),
            "source_pages": _unique_nonempty([p for f in members for p in (f.get("source_pages") or [])]),
            "link_text_samples": _unique_nonempty([t for f in members for t in (f.get("link_text_samples") or [])]),
        })
        direct.append(grouped)
    return direct


def _unique_nonempty(values: list) -> list:
    seen: set = set()
    out: list = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def detect_duplicate_casing_routes(pages: list[dict]) -> list[dict]:
    by_lower: dict[str, list[str]] = {}
    for page in pages:
        path = str(page.get("path") or "")
        if not path:
            continue
        by_lower.setdefault(path.lower(), [])
        if path not in by_lower[path.lower()]:
            by_lower[path.lower()].append(path)
    return [{"path": lower, "variants": variants} for lower, variants in by_lower.items() if len(variants) > 1][:20]


_CASING_HIGH_RISK = ("/dashboard", "/account", "/login", "/cart", "/checkout", "/admin")


def duplicate_casing_findings(pages: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for item in detect_duplicate_casing_routes(pages):
        variants = item["variants"]
        high_risk = any(part in path.lower() for path in variants for part in _CASING_HIGH_RISK)
        finding = create_finding(
            rule="duplicate_route_casing",
            category="indexability",
            priority="high" if high_risk else "medium",
            title="Fix duplicate URL casing variants",
            page_url="",
            current_value=", ".join(variants[:6]),
            explanation="The crawler found URLs that differ only by uppercase/lowercase letters. These can create duplicate crawlable pages or expose app-route variants.",
            recommendation="Ask your web person to choose one canonical casing, redirect the other variants, and make sure internal links use the preferred version.",
            difficulty="developer",
        )
        finding_id = stable_id("duplicate_route_casing|" + "|".join(variants))
        finding.update({
            "id": finding_id,
            "fix_id": finding_id,
            "why_it_matters": "Search engines may treat these as separate URLs, which can split ranking signals and create duplicate or indexable app routes.",
            "affected_pages": variants,
            "page_count": len(variants),
            "page_template_family": "route_boundary" if high_risk else "standard",
            "primary_defect_class": "structural",
        })
        findings.append(finding)
    return findings


def build_scan_summary(pages: list[dict], findings: list[dict], health_score: int, pages_found: int, artifact_count: int) -> dict:
    return {
        "health_score": health_score,
        "score": health_score,
        "pages_scanned": len(pages),
        "pages_crawled": len(pages),
        "pages_found": pages_found,
        "verified_failed_pages": sum(1 for page in pages if is_verified_failed(page)),
        "suspicious_url_artifacts": artifact_count,
        "high_priority_count": sum(1 for item in findings if item.get("priority") in ["critical", "high"]),
        "technical_issue_count": len(findings),
        "duplicate_casing_routes": detect_duplicate_casing_routes(pages),
        "status_label": "Good" if health_score >= 75 else "Fair" if health_score >= 55 else "Needs work",
        "plain_english_summary": f"The Python scanner reviewed {len(pages)} pages and found {len(findings)} evidence-based issues.",
    }


def build_evidence_summary(pages: list[dict], artifact_count: int) -> dict:
    summary = {"confirmed_seed": 0, "confirmed_sitemap_and_linked": 0, "sitemap_listed": 0, "internally_linked": 0, "linked_but_failed": 0, "crawler_artifact": artifact_count, "unknown_discovery": 0}
    for page in pages:
        key = page.get("url_confidence") or "unknown_discovery"
        summary[key] = summary.get(key, 0) + 1
    return summary


def page_evidence(page: dict) -> dict:
    keys = ["url", "final_url", "path", "status_code", "fetch_error", "url_confidence", "url_suspicion_reasons", "discovered_from", "source_pages", "link_text_samples", "page_template_family", "estimated_page_intent", "title", "h1"]
    return {key: page.get(key) for key in keys}


def is_verified_failed(page: dict) -> bool:
    if str(page.get("fetch_error") or "").startswith("blocked_"):
        return False
    return bool((int(page.get("status_code") or 0) >= 400 or page.get("fetch_error")) and page.get("url_confidence") != "crawler_artifact")


def calculate_health_score(pages: list[dict], findings: list[dict]) -> int:
    score = 92
    score -= min(35, sum(1 for page in pages if is_verified_failed(page)) * 8)
    for finding in findings:
        score -= {"critical": 10, "high": 6, "medium": 2}.get(finding.get("priority"), 0)
    return max(20, min(98, round(score)))


def normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            return ""
        host = parsed.hostname or ""
        if any(ch.isspace() for ch in parsed.netloc):
            return ""
        if "." not in host and host != "localhost":
            return ""
        clean, _ = urldefrag(raw)
        return clean.rstrip("/") if parsed.path != "/" else clean
    except Exception:
        return ""


def normalize_prefix(value: str) -> str:
    path = urlparse(value).path if value.startswith(("http://", "https://")) else value
    path = f"/{path.strip('/')}" if path and path != "/" else "/"
    return path.rstrip("/") if path != "/" else "/"


def same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" == origin


def empty_discovery() -> dict:
    return {"discovered_from": [], "source_pages": [], "link_text_samples": []}


def merge_discovery(record: dict, source: str, source_page: str, link_text: str) -> None:
    if source and source not in record["discovered_from"]:
        record["discovered_from"].append(source)
    if source_page and source_page not in record["source_pages"]:
        record["source_pages"].append(source_page)
    if link_text and link_text not in record["link_text_samples"]:
        record["link_text_samples"].append(link_text[:180])


def dedupe_artifacts(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for item in items:
        key = f"{item.get('url')}|{item.get('source_pages')}"
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def friendly_category(category: str) -> str:
    return {
        "meta_title": "Search appearance",
        "meta_description": "Search appearance",
        "canonical": "Website setup",
        "schema": "Trust signals",
        "thin_content": "Page content",
        "404_error": "Broken page",
        "web_dev": "Website setup",
        "image_alt_text": "Images",
        "indexability": "Indexability",
    }.get(category, "Website improvement")


def stable_id(value: str) -> str:
    return "finding_" + hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
