from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)

gate_module = r'''"Shared page-evidence classification for scanner and review finding gates."

from __future__ import annotations

import re
from typing import Any

PAGE_EVIDENCE_GATE_VERSION = "page_evidence_gate_v1"
PAGE_EVIDENCE_CLASSES = {
    "usable_html",
    "failed_access",
    "redirected_terminal",
    "non_html",
    "incomplete_html",
}

_CHALLENGE_MARKERS = (
    "cf-chl-",
    "cloudflare ray id",
    "checking your browser",
    "connection verification",
    "enable javascript and cookies to continue",
    "verify you are human",
    "access denied",
)

def _status(page_or_status: Any) -> int:
    if isinstance(page_or_status, dict):
        value = page_or_status.get("status_code") or page_or_status.get("status") or 0
    else:
        value = page_or_status or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def _looks_like_html(source: str) -> bool:
    return bool(re.search(r"<(?:!doctype\s+html|html|head|body)(?:\s|>)", source, re.I))

def _looks_like_challenge(source: str) -> bool:
    lowered = source.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)

def classify_page_evidence(
    *,
    status_code: int,
    content_type: str = "",
    fetch_error: str = "",
    html: str = "",
    body_truncated: bool = False,
) -> str:
    status = _status(status_code)
    error = str(fetch_error or "").strip()
    source = str(html or "")
    content_type_lower = str(content_type or "").lower()

    if error or status == 0 or status >= 400:
        return "failed_access"
    if 300 <= status < 400:
        return "redirected_terminal"
    if status != 200:
        return "incomplete_html"
    if content_type_lower and "html" not in content_type_lower and "xhtml" not in content_type_lower:
        return "non_html"
    if body_truncated or not source.strip():
        return "incomplete_html"
    if _looks_like_challenge(source):
        return "failed_access"
    if not content_type_lower and not _looks_like_html(source):
        return "non_html"
    return "usable_html"

def page_evidence_class(page: dict[str, Any]) -> str:
    stamped = str(page.get("page_evidence_class") or "")
    if stamped in PAGE_EVIDENCE_CLASSES:
        return stamped
    status = _status(page)
    error = str(page.get("fetch_error") or page.get("error") or "")
    content_type = str(page.get("content_type") or "")
    html_size = int(page.get("html_size") or 0)
    if error or status == 0 or status >= 400:
        return "failed_access"
    if 300 <= status < 400:
        return "redirected_terminal"
    if status != 200:
        return "incomplete_html"
    if content_type and "html" not in content_type.lower() and "xhtml" not in content_type.lower():
        return "non_html"
    if page.get("raw_html_truncated") is True or page.get("html_truncated") is True:
        return "incomplete_html"
    if html_size <= 0 and not any(page.get(key) for key in ("title", "h1", "meta_description", "canonical")):
        return "incomplete_html"
    return "usable_html"

def page_has_usable_html(page: dict[str, Any]) -> bool:
    return page_evidence_class(page) == "usable_html"
'''
write("scanner-api/app/page_evidence_gate.py", gate_module)

path = "scanner-api/app/extract.py"
text = read(path)
text = replace_once(text, "from .market_scope import strip_market_locale_prefix\n", "from .market_scope import strip_market_locale_prefix\nfrom .page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION, classify_page_evidence\n", "extract import")
text = replace_once(text, "    rendering_signals = client_rendering_signals(html, status_code, word_count)\n\n    return {\n", "    rendering_signals = client_rendering_signals(html, status_code, word_count)\n    page_evidence_class = classify_page_evidence(\n        status_code=status_code,\n        content_type=content_type,\n        fetch_error=fetch_error,\n        html=html,\n    )\n\n    return {\n", "extract classification")
text = replace_once(text, '        "content_type": content_type,\n', '        "content_type": content_type,\n        "page_evidence_class": page_evidence_class,\n        "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n', "extract fields")
write(path, text)

path = "scanner-api/app/scanner.py"
text = read(path)
text = replace_once(text, "from .market_scope import market_pair_prefix, path_within_scope\n", "from .market_scope import market_pair_prefix, path_within_scope\nfrom .page_evidence_gate import (\n    PAGE_EVIDENCE_GATE_VERSION,\n    page_evidence_class,\n    page_has_usable_html,\n)\n", "scanner gate import")
text = replace_once(text, '        "metadata_evidence_version": METADATA_EVIDENCE_VERSION,\n        "title_evidence_version": TITLE_EVIDENCE_VERSION,\n', '        "metadata_evidence_version": METADATA_EVIDENCE_VERSION,\n        "title_evidence_version": TITLE_EVIDENCE_VERSION,\n        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n', "scanner response marker")
text = replace_once(text, '            "metadata_evidence_version": METADATA_EVIDENCE_VERSION,\n            "title_evidence_version": TITLE_EVIDENCE_VERSION,\n', '            "metadata_evidence_version": METADATA_EVIDENCE_VERSION,\n            "title_evidence_version": TITLE_EVIDENCE_VERSION,\n            "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n', "scanner technical marker")
text = replace_once(text, '        if str(page.get("fetch_error") or "").startswith("blocked_"):\n            continue\n        status_code = int(page.get("status_code") or 0)\n        if status_code >= 400 or page.get("fetch_error"):\n            findings.append(create_finding(\n                rule="rate_limited_page" if status_code == 429 else "failed_page",\n                category="web_dev" if status_code == 429 else "404_error",\n                priority="high" if status_code == 429 or status_code >= 500 else "medium",\n                title="Check pages blocked by rate limiting" if status_code == 429 else "Fix pages that are not loading",\n                page_url=path,\n                current_value=page.get("fetch_error") or f"HTTP {status_code}",\n                explanation="The page did not load cleanly during the scan and has a real discovery source.",\n                recommendation="Check whether the page should exist, redirect it, or fix the server/access issue.",\n                difficulty="developer",\n                source_pages=page.get("source_pages", []),\n                link_text_samples=page.get("link_text_samples", []),\n            ))\n            continue\n', '        if str(page.get("fetch_error") or "").startswith("blocked_"):\n            continue\n        status_code = int(page.get("status_code") or 0)\n        evidence_class = page_evidence_class(page)\n        if evidence_class == "failed_access":\n            is_seed = "seed" in set(page.get("discovered_from") or [])\n            rule = "site_access_limited" if is_seed else ("rate_limited_page" if status_code == 429 else "failed_page")\n            title = "We could not fully check your site this time" if is_seed else ("Check pages blocked by rate limiting" if status_code == 429 else "Verify a page that did not load during the scan")\n            explanation = ("Your site redirected or responded in a way the scanner could not safely verify. This does not necessarily mean anything is wrong for visitors or Google." if is_seed else "The scanner could not retrieve usable HTML for this URL. This is access evidence, not proof that page elements are missing.")\n            recommendation = ("Try again later. If it keeps happening, ask your web person to check hosting, CDN, firewall, bot-protection, DNS, and redirect logs." if is_seed else "Check server, CDN, firewall, bot-protection, and redirect logs before changing page content.")\n            finding = create_finding(\n                rule=rule,\n                category="web_dev",\n                priority="medium" if is_seed or status_code in {0, 429} else "high" if status_code >= 500 else "medium",\n                title=title,\n                page_url=path,\n                current_value=page.get("fetch_error") or f"HTTP {status_code}",\n                explanation=explanation,\n                recommendation=recommendation,\n                difficulty="developer",\n                source_pages=page.get("source_pages", []),\n                link_text_samples=page.get("link_text_samples", []),\n            )\n            finding.update({\n                "evidence_status": "needs_verification" if status_code in {0, 429} or is_seed else "confirmed",\n                "verification_state": "needs_verification",\n                "non_scoring": True,\n                "score_impact": 0,\n                "page_evidence_class": evidence_class,\n                "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n                "confidence_score": 70 if status_code in {0, 429} or is_seed else 92,\n            })\n            findings.append(finding)\n            continue\n        if not page_has_usable_html(page):\n            continue\n', "scanner failure/html gate")
text = replace_once(text, '        if not title or not (200 <= status < 300) or page.get("indexable") is False:\n            continue\n        if not is_html_page_evidence(page):\n            continue\n', '        if not title or page.get("indexable") is False or not page_has_usable_html(page):\n            continue\n        if not is_html_page_evidence(page):\n            continue\n', "duplicate title gate")
text = replace_once(text, 'def build_scan_summary(pages: list[dict], findings: list[dict], health_score: int, pages_found: int, artifact_count: int) -> dict:\n', 'def build_scan_summary(pages: list[dict], findings: list[dict], health_score: int | None, pages_found: int, artifact_count: int) -> dict:\n', "scan summary annotation")
text = replace_once(text, '        "status_label": "Good" if health_score >= 75 else "Fair" if health_score >= 55 else "Needs work",\n', '        "status_label": "Score unavailable" if health_score is None else "Good" if health_score >= 75 else "Fair" if health_score >= 55 else "Needs work",\n        "health_score_status": "available" if health_score is not None else "insufficient_evidence",\n        "usable_page_count": sum(1 for page in pages if page_has_usable_html(page)),\n', "scan summary nullable")
text = replace_once(text, 'def calculate_health_score(pages: list[dict], findings: list[dict]) -> int:\n    score = 92\n', 'def calculate_health_score(pages: list[dict], findings: list[dict]) -> int | None:\n    if sum(1 for page in pages if page_has_usable_html(page)) < 4:\n        return None\n    score = 92\n', "scanner score gate")
text = replace_once(text, '    keys = ["url", "final_url", "path", "status_code", "fetch_error",', '    keys = ["url", "final_url", "path", "status_code", "fetch_error", "page_evidence_class", "evidence_gate_version",', "scanner evidence keys")
write(path, text)

path = "scanner-api/app/review.py"
text = read(path)
text = replace_once(text, "from urllib.parse import urlparse\n", "from urllib.parse import urlparse\n\nfrom .page_evidence_gate import (\n    PAGE_EVIDENCE_GATE_VERSION,\n    page_evidence_class,\n    page_has_usable_html,\n)\n", "review gate import")
text = replace_once(text, '    "rate_limited_page": "web_dev",\n', '    "rate_limited_page": "web_dev",\n    "site_access_limited": "web_dev",\n', "review category")
text = replace_once(text, '        + [page for page in pages if is_failed_page(page) or is_blocked_access_page(page)]\n', '        + [page for page in pages if is_failed_page(page) or is_blocked_access_page(page) or page_evidence_class(page) == "failed_access"]\n', "review access evidence collection")
text = replace_once(text, '    for bucket, group in grouped.items():\n        if bucket == "429":\n', '    for bucket, group in grouped.items():\n        if bucket == "access":\n            fixes.append(make_fix(\n                rule="site_access_limited",\n                category="web_dev",\n                priority="medium",\n                title="We could not fully check your site this time",\n                explanation="The site redirected or responded in a way the scanner could not safely verify. This is a scan limitation, not proof of an SEO defect.",\n                why="Without usable HTML, FixList cannot confirm titles, headings, canonical tags, metadata, schema, content, or image descriptions.",\n                recommendation="Try again later. If it keeps happening, ask your web person to check hosting, CDN, firewall, bot-protection, DNS, and redirect logs.",\n                affected_pages=[page_evidence_url(page) for page in group],\n                difficulty="developer",\n                source="scanner_access_evidence",\n                extra={\n                    **evidence_extra(group),\n                    "evidence_status": "needs_verification",\n                    "verification_state": "needs_verification",\n                    "limitation_code": "site_access_requires_retry_or_log_confirmation",\n                    "non_scoring": True,\n                    "score_impact": 0,\n                    "page_evidence_class": "failed_access",\n                    "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n                    "confidence_score": 70,\n                },\n            ))\n            continue\n        if bucket == "429":\n', "review access finding")
text = replace_once(text, '        if not url or is_non_html_page_evidence(page):\n            continue\n        if int_or_zero(page.get("status_code") or page.get("status")) >= 400 or is_blocked_access_page(page):\n            continue\n', '        if not url or is_non_html_page_evidence(page) or not page_has_usable_html(page):\n            continue\n', "review page pattern gate")
old_prepare = '''def prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = dedupe_fixes([normalize_fix(fix, index) for index, fix in enumerate(raw_fixes or []) if isinstance(fix, dict)])
    filtered = [filter_orphan_asset_evidence(fix, pages) for fix in normalized]
'''
new_prepare = '''HTML_DEPENDENT_RULES = {
    "canonical_missing", "missing_canonical", "missing_title", "generic_fallback_title",
    "title_over_pixel_limit", "duplicate_title", "duplicate_title_localized",
    "duplicate_title_query_variants", "duplicate_title_template",
    "missing_meta_description", "empty_meta_description", "malformed_meta_description",
    "duplicate_meta_description", "missing_h1", "multiple_h1", "schema",
    "structured_data", "thin_content", "image_alt_text", "missing_image_alt",
}


def filter_html_dependent_fix_evidence(fix: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    rule = str(fix.get("rule") or "").lower()
    if rule not in HTML_DEPENDENT_RULES:
        return fix
    lookup = {clean_path(page_evidence_url(page)): page for page in pages if clean_path(page_evidence_url(page))}
    affected = dedupe_strings([clean_path(url) for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"]) if clean_path(url)])
    usable = [url for url in affected if page_has_usable_html(lookup.get(url, {}))]
    if not usable:
        return None
    return {**fix, "affected_pages": usable, "page_url": usable[0], "page_count": len(usable), "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION}


def prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = dedupe_fixes([normalize_fix(fix, index) for index, fix in enumerate(raw_fixes or []) if isinstance(fix, dict)])
    normalized = [candidate for fix in normalized if (candidate := filter_html_dependent_fix_evidence(fix, pages)) is not None]
    filtered = [filter_orphan_asset_evidence(fix, pages) for fix in normalized]
'''
text = replace_once(text, old_prepare, new_prepare, "review defensive filter")
text = replace_once(text, '    usable_pages = sum(\n        1 for page in pages\n        if 200 <= int_or_zero(page.get("status_code")) < 300 and not is_blocked_access_page(page)\n    )\n', '    usable_pages = sum(1 for page in pages if page_has_usable_html(page))\n', "review usable page count")
text = replace_once(text, '    health_score = compute_health_score(fixes, site_fingerprint)\n    if insufficient:\n        health_score = min(55, health_score)\n', '    usable_page_count = int_or_zero(site_fingerprint.get("classification", {}).get("usable_pages"))\n    health_score_status = "available" if usable_page_count >= 4 else "insufficient_evidence"\n    health_score = compute_health_score(fixes, site_fingerprint) if health_score_status == "available" else None\n    if insufficient and health_score is not None:\n        health_score = min(55, health_score)\n', "review nullable score")
text = replace_once(text, '        "health_grade": "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Insufficient evidence" if insufficient else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",\n', '        "health_grade": "Score unavailable" if health_score is None else "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Insufficient evidence" if insufficient else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",\n        "health_score_status": health_score_status,\n        "usable_page_count": usable_page_count,\n', "review report score state")
text = replace_once(text, '        "health_score": health_score,\n        "site_fingerprint": {**site_fingerprint, "review_input_quality": quality},\n', '        "health_score": health_score,\n        "health_score_status": health_score_status,\n        "usable_page_count": usable_page_count,\n        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n        "site_fingerprint": {**site_fingerprint, "review_input_quality": quality},\n', "review top score state")
text = replace_once(text, '            "health_score": health_score,\n            "score": health_score,\n', '            "health_score": health_score,\n            "score": health_score,\n            "health_score_status": health_score_status,\n            "usable_page_count": usable_page_count,\n', "review summary score state")
text = replace_once(text, 'def status_bucket_from_page(page: dict[str, Any]) -> str:\n    status = int_or_zero(page.get("status_code") or page.get("status"))\n', 'def status_bucket_from_page(page: dict[str, Any]) -> str:\n    status = int_or_zero(page.get("status_code") or page.get("status"))\n    if page_evidence_class(page) == "failed_access" and status not in {404, 410, 429} and status < 500:\n        return "access"\n', "review access bucket")
write(path, text)

path = "scanner-api/app/beta_revision.py"
text = read(path)
text = replace_once(text, '    from .metadata_title_evidence import METADATA_EVIDENCE_VERSION, TITLE_EVIDENCE_VERSION\n', '    from .metadata_title_evidence import METADATA_EVIDENCE_VERSION, TITLE_EVIDENCE_VERSION\n    from .page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION\n', "beta gate import")
text = replace_once(text, '        "title_evidence_version": TITLE_EVIDENCE_VERSION,\n', '        "title_evidence_version": TITLE_EVIDENCE_VERSION,\n        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,\n', "beta gate component")
write(path, text)

revision_path = ROOT / "data/beta-crawler-revision.json"
revision = json.loads(revision_path.read_text(encoding="utf-8"))
revision["component_versions"]["page_evidence_gate_version"] = "page_evidence_gate_v1"
payload = json.dumps(revision["component_versions"], sort_keys=True, separators=(",", ":"))
revision["fingerprint"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision["status"] = "candidate"
revision["git_commit"] = ""
revision["recorded_at"] = "2026-07-18T00:00:00Z"
revision["acceptance_report"] = "docs/releases/page-evidence-gate-v1.md"
revision["note"] = "Page-evidence gate candidate: inaccessible, redirected, non-HTML and incomplete pages cannot create confirmed HTML-element findings; insufficient usable evidence produces no numeric health score."
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
fingerprint = revision["fingerprint"]
if fingerprint != "4a560c34a3d68c6b":
    raise RuntimeError(f"unexpected fingerprint {fingerprint}")

path = "src/lib/scanRunModel.js"
text = read(path).replace("52348dd1f3b77700", fingerprint)
write(path, text)

path = "src/components/scan/ScanWebsiteForm.jsx"
text = read(path)
text = replace_once(text, '  const healthScore = getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.score, scanData?.scan_summary?.health_score]);\n', '  const healthScoreStatus = aiData?.health_score_status || aiData?.website_health_report?.health_score_status || aiData?.scan_summary?.health_score_status || scanData?.health_score_status || scanData?.scan_summary?.health_score_status || "available";\n  const healthScore = healthScoreStatus === "insufficient_evidence" ? null : getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.score, scanData?.scan_summary?.health_score]);\n', "frontend score selection")
text = replace_once(text, '    health_score: healthScore || 0,\n    seo_score: healthScore || 0,\n', '    health_score: healthScore,\n    seo_score: healthScore,\n    health_score_status: healthScoreStatus,\n    usable_page_count: getFirstNumber([aiData?.usable_page_count, aiData?.website_health_report?.usable_page_count, aiData?.scan_summary?.usable_page_count, scanData?.usable_page_count, scanData?.scan_summary?.usable_page_count]),\n', "frontend nullable score fields")
write(path, text)

for path in ["tests/frontend/releaseAuthorityGate.test.mjs", "tests/frontend/scanRunPersistence.test.mjs"]:
    write(path, read(path).replace("52348dd1f3b77700", fingerprint))

test_module = r'''from app.extract import extract_page
from app.page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION, page_evidence_class
from app.review import build_page_pattern_findings, build_scanner_evidence_findings, build_site_fingerprint, prepare_fixes
from app.scanner import build_findings, calculate_health_score

HTML_RULES = {"canonical_missing", "missing_title", "generic_fallback_title", "title_over_pixel_limit", "missing_meta_description", "empty_meta_description", "malformed_meta_description", "missing_h1", "multiple_h1", "schema", "image_alt_text"}

def extracted(html="", *, status=0, error="redirect_validation_failed", content_type=""):
    return extract_page(html, "https://www.funbooker.com/fr", "https://www.funbooker.com/fr", status, content_type, {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []}, fetch_error=error)

def test_funbooker_redirect_validation_failure_only_emits_access_limitation():
    page = extracted()
    assert page["page_evidence_class"] == "failed_access"
    assert page["evidence_gate_version"] == PAGE_EVIDENCE_GATE_VERSION
    findings = build_findings([page])
    assert [finding["rule"] for finding in findings] == ["site_access_limited"]
    assert findings[0]["verification_state"] == "needs_verification"
    assert findings[0]["non_scoring"] is True
    assert not ({finding["rule"] for finding in findings} & HTML_RULES)
    assert calculate_health_score([page], findings) is None

def test_review_pattern_generator_suppresses_html_rules_for_failed_access():
    page = extracted()
    assert build_page_pattern_findings([page]) == []
    body = {"pages_crawled": 1, "pages_found": 1, "verified_failed_pages": [page]}
    fingerprint = build_site_fingerprint(body, [page], "https://www.funbooker.com/fr")
    findings = build_scanner_evidence_findings(body, [page], fingerprint)
    assert [finding["rule"] for finding in findings] == ["site_access_limited"]
    assert findings[0]["score_impact"] == 0

def test_review_drops_legacy_html_findings_when_underlying_page_is_unusable():
    page = extracted()
    body = {"pages_crawled": 1, "pages_found": 1}
    fingerprint = build_site_fingerprint(body, [page], "https://www.funbooker.com/fr")
    playbook = {"label": "general", "money_patterns": [], "priority_pages": [], "priority_issues": [], "demote": [], "owner_rule": ""}
    legacy = [{"rule": "canonical_missing", "category": "canonical", "priority": "high", "title": "Add canonical", "page_url": "/fr", "affected_pages": ["/fr"]}]
    assert prepare_fixes(legacy, fingerprint, body, playbook, [page]) == []

def test_healthy_html_still_generates_normal_findings():
    page = extracted("<html><head><title>Useful page</title></head><body><p>Text</p></body></html>", status=200, error="", content_type="text/html")
    assert page_evidence_class(page) == "usable_html"
    rules = {finding["rule"] for finding in build_findings([page])}
    assert {"missing_meta_description", "missing_h1", "canonical_missing"} <= rules

def test_non_html_and_empty_200_are_not_usable():
    non_html = extracted('{"ok":true}', status=200, error="", content_type="application/json")
    empty = extracted("", status=200, error="", content_type="text/html")
    assert page_evidence_class(non_html) == "non_html"
    assert page_evidence_class(empty) == "incomplete_html"
    assert not ({finding["rule"] for finding in build_findings([non_html, empty])} & HTML_RULES)
'''
write("scanner-api/tests/test_page_evidence_gate_v1.py", test_module)

doc = f'''# Page evidence gate v1 candidate

This candidate prevents fetch failures, redirects, non-HTML responses and incomplete HTML from being interpreted as missing page elements.

- HTML-dependent findings require `page_evidence_class: usable_html`.
- A failed seed request emits one non-scoring `site_access_limited` finding with `needs_verification`.
- Fewer than four usable HTML pages produces `health_score: null`.
- Candidate fingerprint: `{fingerprint}`.

Deployment order: Cloud Run first, verify `/health` and `/revision`, then publish Base44 and rerun Funbooker plus a successful control.
'''
write("docs/releases/page-evidence-gate-v1.md", doc)

print(f"Applied page evidence gate; fingerprint={fingerprint}")
