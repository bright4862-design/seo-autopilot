from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old[:100]!r}")
    file_path.write_text(text.replace(old, new, 1))


# 1. Require structural SaaS evidence instead of allowing incidental words such
# as subscription, report, account, or app to classify a corporate website.
replace_once(
    "scanner-api/app/review.py",
    '''        if key == "saas_app_membership" and saas_paths >= 2:\n            score += 12\n        adjusted_scores.append((key, score))''',
    '''        if key == "saas_app_membership":\n            if saas_paths < 2:\n                score = min(score, 1.0)\n            else:\n                score += 12\n        adjusted_scores.append((key, score))''',
)

# 2. Extend final review calibration with non-HTML/utility suppression and
# harmless trailing-slash redirect calibration.
replace_once(
    "scanner-api/app/review_calibration.py",
    '''from copy import deepcopy\nfrom typing import Any''',
    '''from copy import deepcopy\nimport re\nfrom typing import Any''',
)
replace_once(
    "scanner-api/app/review_calibration.py",
    '''CALIBRATION_VERSION = "review_evidence_calibration_v4_legal_page_scope"''',
    '''CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect"''',
)
replace_once(
    "scanner-api/app/review_calibration.py",
    '''SITEMAP_REDIRECT_RULES = {"sitemap_redirect"}\nMISSING_META_DESCRIPTION_RULES = {"missing_meta_description"}\nPRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}''',
    '''SITEMAP_REDIRECT_RULES = {"sitemap_redirect"}\nTRAILING_SLASH_REDIRECT_RULES = {"sitemap_redirect", "internal_link_redirect"}\nMISSING_META_DESCRIPTION_RULES = {"missing_meta_description"}\nPAGE_SEMANTIC_RULES = {\n    "canonical_missing",\n    "missing_canonical",\n    "missing_h1",\n    "multiple_h1",\n    "missing_meta_description",\n    "missing_title",\n    "image_alt_text",\n    "missing_image_alt",\n}\nPAGE_SEMANTIC_CATEGORIES = {"canonical", "thin_content", "meta_description", "meta_title", "image_alt_text"}\nUTILITY_PATH_MARKERS = ("/cdn-cgi/",)\nNON_HTML_SUFFIXES = (\n    ".pdf", ".xml", ".json", ".csv", ".txt", ".zip",\n    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",\n    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",\n)\nPRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}''',
)

old_evidence_map = '''def _page_evidence_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:\n    evidence: dict[str, dict[str, Any]] = {}\n    for page in _pages_from_payload(payload):\n        stats = image_alt_evidence(page)\n        for value in (page.get("url"), page.get("final_url"), page.get("path"), page.get("page_url")):\n            key = _path(value)\n            if key:\n                evidence[key] = stats\n    return evidence\n\n\n'''
new_evidence_map = '''def _content_type(page: dict[str, Any]) -> str:\n    headers = page.get("headers") if isinstance(page.get("headers"), dict) else {}\n    return str(\n        page.get("content_type")\n        or page.get("mime_type")\n        or headers.get("content-type")\n        or headers.get("Content-Type")\n        or ""\n    ).split(";", 1)[0].strip().lower()\n\n\ndef _is_non_html_or_utility_path(value: Any) -> bool:\n    path = _path(value).lower()\n    return bool(\n        path\n        and (\n            any(marker in path for marker in UTILITY_PATH_MARKERS)\n            or path.endswith(NON_HTML_SUFFIXES)\n        )\n    )\n\n\ndef _is_non_html_or_utility_page(page: dict[str, Any]) -> bool:\n    values = (page.get("url"), page.get("final_url"), page.get("path"), page.get("page_url"))\n    if any(_is_non_html_or_utility_path(value) for value in values if value):\n        return True\n    content_type = _content_type(page)\n    return bool(content_type and content_type not in {"text/html", "application/xhtml+xml"})\n\n\ndef _page_evidence_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:\n    evidence: dict[str, dict[str, Any]] = {}\n    for page in _pages_from_payload(payload):\n        stats = {\n            **image_alt_evidence(page),\n            "content_type": _content_type(page),\n            "non_html_or_utility": _is_non_html_or_utility_page(page),\n        }\n        for value in (page.get("url"), page.get("final_url"), page.get("path"), page.get("page_url")):\n            key = _path(value)\n            if key:\n                evidence[key] = stats\n    return evidence\n\n\ndef _is_page_semantic_fix(fix: dict[str, Any]) -> bool:\n    rule = str(fix.get("rule") or "")\n    category = str(fix.get("category") or "")\n    return rule in PAGE_SEMANTIC_RULES or category in PAGE_SEMANTIC_CATEGORIES\n\n\ndef _calibrate_page_semantic_fix(\n    fix: dict[str, Any],\n    evidence: dict[str, dict[str, Any]],\n) -> dict[str, Any] | None:\n    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []\n    if not affected:\n        affected = [fix.get("page_url") or "/"]\n\n    retained: list[str] = []\n    suppressed: list[str] = []\n    for value in affected:\n        key = _path(value)\n        if not key:\n            continue\n        stats = evidence.get(key, {})\n        unsupported = bool(stats.get("non_html_or_utility")) or _is_non_html_or_utility_path(key)\n        if unsupported:\n            suppressed.append(key)\n        else:\n            retained.append(key)\n\n    if not retained:\n        return None\n    if not suppressed:\n        return fix\n\n    source_pages = fix.get("source_pages") if isinstance(fix.get("source_pages"), list) else []\n    retained_set = set(retained)\n    filtered_sources = [value for value in source_pages if _path(value) in retained_set]\n    return {\n        **fix,\n        "affected_pages": retained,\n        "page_url": retained[0],\n        "page_count": len(retained),\n        "source_pages": filtered_sources[:30] or retained[:30],\n        "non_html_or_utility_pages_suppressed": len(suppressed),\n        "page_semantic_calibration_version": CALIBRATION_VERSION,\n    }\n\n\n'''
replace_once("scanner-api/app/review_calibration.py", old_evidence_map, new_evidence_map)

redirect_anchor = '''def _is_single_healthy_sitemap_redirect(fix: dict[str, Any]) -> bool:\n'''
redirect_helpers = '''def _redirect_endpoint_urls(fix: dict[str, Any]) -> tuple[str, str]:\n    source = str(fix.get("redirect_source_url") or fix.get("source_url") or "").strip()\n    destination = str(fix.get("redirect_destination_url") or fix.get("destination_url") or "").strip()\n    chain = fix.get("redirect_chain") if isinstance(fix.get("redirect_chain"), list) else []\n    if not source and chain:\n        source = str(chain[0] or "").strip()\n    if not destination and len(chain) >= 2:\n        destination = str(chain[-1] or "").strip()\n    if not source or not destination:\n        text = str(fix.get("current_value") or "")\n        urls = [value.rstrip(".,;)") for value in re.findall(r"https?://[^\\s→—]+", text)]\n        if not source and urls:\n            source = urls[0]\n        if not destination and len(urls) >= 2:\n            destination = urls[1]\n    return source, destination\n\n\ndef _url_identity_without_trailing_slash(value: str) -> tuple[str, str, str, str] | None:\n    try:\n        parsed = urlparse(value)\n    except Exception:\n        return None\n    if parsed.scheme not in {"http", "https"} or not parsed.netloc:\n        return None\n    path = parsed.path or "/"\n    normalized_path = path.rstrip("/") or "/"\n    return parsed.scheme.lower(), parsed.netloc.lower(), normalized_path, parsed.query\n\n\ndef _is_trailing_slash_only_healthy_redirect(fix: dict[str, Any]) -> bool:\n    if str(fix.get("rule") or "") not in TRAILING_SLASH_REDIRECT_RULES:\n        return False\n    state = str(fix.get("redirect_state") or "").lower()\n    if state and state not in {"single_redirect", "redirect", "redirected"}:\n        return False\n    if _int(fix.get("redirect_hop_count")) > 1:\n        return False\n    chain = fix.get("redirect_chain") if isinstance(fix.get("redirect_chain"), list) else []\n    if chain and len(chain) != 2:\n        return False\n\n    text = " ".join(\n        str(fix.get(key) or "")\n        for key in (\n            "current_value",\n            "redirect_destination_status",\n            "redirect_destination_indexability",\n            "redirect_destination_state",\n        )\n    ).lower()\n    if any(marker in text for marker in (\n        "loop", "chain", "failed", "failure", "blocked", "noindex",\n        "non-public", "invalid location", "missing location", "too many redirects",\n    )):\n        return False\n    status_is_healthy = (\n        "destination http 200" in text\n        or _int(fix.get("redirect_destination_status")) == 200\n        or _int(fix.get("destination_status_code")) == 200\n    )\n    destination_is_indexable = (\n        "destination: indexable" in text\n        or str(fix.get("redirect_destination_indexability") or "").lower() == "indexable"\n        or fix.get("redirect_destination_indexable") is True\n    )\n    if not status_is_healthy or not destination_is_indexable:\n        return False\n\n    source, destination = _redirect_endpoint_urls(fix)\n    source_identity = _url_identity_without_trailing_slash(source)\n    destination_identity = _url_identity_without_trailing_slash(destination)\n    if not source_identity or source_identity != destination_identity:\n        return False\n    source_path = urlparse(source).path or "/"\n    destination_path = urlparse(destination).path or "/"\n    return source_path != destination_path and source_path.rstrip("/") == destination_path.rstrip("/")\n\n\n'''
replace_once("scanner-api/app/review_calibration.py", redirect_anchor, redirect_helpers + redirect_anchor)

replace_once(
    "scanner-api/app/review_calibration.py",
    '''    if _is_single_healthy_sitemap_redirect(fix):\n        return _cap_priority(''',
    '''    if _is_trailing_slash_only_healthy_redirect(fix):\n        return _cap_priority(\n            fix,\n            "medium",\n            67,\n            "trailing_slash_only_healthy_redirect",\n        )\n\n    if _is_single_healthy_sitemap_redirect(fix):\n        return _cap_priority(''',
)

replace_once(
    "scanner-api/app/review_calibration.py",
    '''        rule = str(item.get("rule") or item.get("category") or "")\n        if rule in IMAGE_ALT_RULES or str(item.get("category") or "") == "image_alt_text":''',
    '''        rule = str(item.get("rule") or item.get("category") or "")\n        if _is_page_semantic_fix(item):\n            item = _calibrate_page_semantic_fix(item, evidence)\n            if item is None:\n                continue\n        if rule in IMAGE_ALT_RULES or str(item.get("category") or "") == "image_alt_text":''',
)

# 3. Add regressions based on the IKEA production scan.
test_path = Path("scanner-api/tests/test_review_calibration.py")
test_text = test_path.read_text()
test_text = test_text.replace(
    'assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v4_legal_page_scope"',
    'assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v5_utility_redirect"',
)
append = r'''


def test_ikea_corporate_site_is_not_saas_from_incidental_subscription_and_report_words():
    pages = [
        {"url": "https://www.ikea.com/", "status_code": 200, "title": "IKEA", "h1": "IKEA", "meta_description": "Home", "page_template_family": "homepage"},
        {"url": "https://www.ikea.com/global/en/stories", "status_code": 200, "title": "Stories", "h1": "Stories", "meta_description": "Ideas", "page_template_family": "standard"},
        {"url": "https://www.ikea.com/global/en/newsroom/subscription", "status_code": 200, "title": "Newsroom subscription", "h1": "Subscribe", "meta_description": "News", "page_template_family": "standard"},
        {"url": "https://www.ikea.com/global/en/jobs/me-and-ikea", "status_code": 200, "title": "Me and IKEA", "h1": "Jobs", "meta_description": "Careers", "page_template_family": "standard"},
        {"url": "https://www.ikea.com/global/en/our-business/reports", "status_code": 200, "title": "Business reports", "h1": "Reports", "meta_description": "Company reports", "page_template_family": "guide_article"},
    ]
    body = {
        "website_url": "https://www.ikea.com/",
        "business_name": "IKEA",
        "pages_found": 216,
        "pages_crawled": len(pages),
        "pages": pages,
    }
    result = run_review(body)
    fingerprint = result["site_fingerprint"]
    assert fingerprint["primary_archetype"] != "saas_app_membership"
    assert fingerprint["business_model"] != "saas_or_member_app"


def test_large_trailing_slash_internal_redirect_group_is_medium_not_critical():
    body = payload([page("/global/en/stories", 4, 0, "standard")])
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "ikea-slash-redirects",
            "fix_id": "ikea-slash-redirects",
            "rule": "internal_link_redirect",
            "category": "indexability",
            "priority": "critical",
            "overall_priority_score": 94,
            "page_count": 128,
            "affected_pages": [f"/global/en/story-{index}" for index in range(128)],
            "redirect_state": "single_redirect",
            "redirect_hop_count": 1,
            "redirect_source_url": "https://www.ikea.com/global/en/stories",
            "redirect_destination_url": "https://www.ikea.com/global/en/stories/",
            "destination_status_code": 200,
            "redirect_destination_indexable": True,
            "current_value": "https://www.ikea.com/global/en/stories → https://www.ikea.com/global/en/stories/ — destination HTTP 200 — destination: Indexable",
            "issue_title": "Update internal links that pass through redirects",
        }
    ]
    result = apply_review_evidence_calibration(reviewed, body)
    fix = result["recommendations"][0]
    assert fix["priority"] == "medium"
    assert fix["overall_priority_score"] <= 67
    assert fix["severity_calibration_reason"] == "trailing_slash_only_healthy_redirect"
    assert result["health_score"] == 88


def test_pdf_and_cloudflare_utility_targets_do_not_create_page_semantic_tasks():
    body = {
        "website_url": "https://www.ikea.com/",
        "pages_crawled": 3,
        "pages_found": 3,
        "pages": [
            {
                "url": "https://www.ikea.com/global/en/images/report.pdf",
                "final_url": "https://www.ikea.com/global/en/images/report.pdf",
                "status_code": 200,
                "content_type": "application/pdf",
            },
            {
                "url": "https://www.ikea.com/cdn-cgi/l/email-protection",
                "final_url": "https://www.ikea.com/cdn-cgi/l/email-protection",
                "status_code": 200,
                "content_type": "text/html",
            },
            {
                "url": "https://www.ikea.com/global/en/newsroom/subscription",
                "final_url": "https://www.ikea.com/global/en/newsroom/subscription/",
                "status_code": 200,
                "content_type": "text/html",
                "title": "Subscribe",
                "h1": "Subscribe",
                "h1_count": 1,
                "canonical": "https://www.ikea.com/global/en/newsroom/subscription/",
                "meta_description": "",
                "image_count": 0,
                "image_missing_alt_count": 0,
            },
        ],
    }
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "canonical-utility",
            "rule": "canonical_missing",
            "category": "canonical",
            "priority": "high",
            "affected_pages": ["/cdn-cgi/l/email-protection", "/global/en/images/report.pdf"],
            "page_url": "/cdn-cgi/l/email-protection",
            "issue_title": "Add canonical URLs to standard pages",
        },
        {
            "id": "h1-utility",
            "rule": "missing_h1",
            "category": "thin_content",
            "priority": "medium",
            "affected_pages": ["/global/en/images/report.pdf"],
            "page_url": "/global/en/images/report.pdf",
            "issue_title": "Add an H1",
        },
        {
            "id": "title-utility",
            "rule": "missing_title",
            "category": "meta_title",
            "priority": "medium",
            "affected_pages": ["/global/en/images/report.pdf"],
            "page_url": "/global/en/images/report.pdf",
            "issue_title": "Add a title",
        },
        {
            "id": "mixed-meta",
            "rule": "missing_meta_description",
            "category": "meta_description",
            "priority": "medium",
            "affected_pages": ["/global/en/images/report.pdf", "/global/en/newsroom/subscription"],
            "page_url": "/global/en/images/report.pdf",
            "source_pages": ["/global/en/images/report.pdf", "/global/en/newsroom/subscription"],
            "issue_title": "Add meta descriptions",
        },
    ]
    result = apply_review_evidence_calibration(reviewed, body)
    fixes = result["recommendations"]
    assert len(fixes) == 1
    assert fixes[0]["rule"] == "missing_meta_description"
    assert fixes[0]["affected_pages"] == ["/global/en/newsroom/subscription"]
    assert fixes[0]["page_url"] == "/global/en/newsroom/subscription"
    assert fixes[0]["non_html_or_utility_pages_suppressed"] == 1
'''
if "test_ikea_corporate_site_is_not_saas" in test_text:
    raise RuntimeError("IKEA regressions already present")
test_path.write_text(test_text.rstrip() + append + "\n")
