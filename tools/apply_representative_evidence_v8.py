#!/usr/bin/env python3
"""Apply representative evidence v8 from the 20-site production audit."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "scanner-api/app/review.py"
BETA = ROOT / "scanner-api/app/beta_revision.py"
REVISION = ROOT / "data/beta-crawler-revision.json"
OLD_FP = "2dd346f90e64f94b"
NEW_FP = "561db6e131da53a9"
NEW_REP = "business_representative_page_v2_archetype_route_families"
NEW_ASSET = "page_level_asset_evidence_v2_html_only"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


text = REVIEW.read_text(encoding="utf-8")
text = replace_once(
    text,
    'REPRESENTATIVE_PAGE_VERSION = "business_representative_page_v1"\n',
    f'REPRESENTATIVE_PAGE_VERSION = "{NEW_REP}"\nPAGE_LEVEL_ASSET_EVIDENCE_VERSION = "{NEW_ASSET}"\n',
    "representative version",
)
text = replace_once(
    text,
    'ROUTE_BOUNDARY_RULES = {"route_boundary_candidate_indexable", "internal_route_indexable"}\n',
    '''ROUTE_BOUNDARY_RULES = {"route_boundary_candidate_indexable", "internal_route_indexable"}\nPAGE_LEVEL_HTML_ONLY_RULES = {\n    "broken_page", "404_error", "410_error", "server_error", "rate_limited_page",\n    "blocked_page", "missing_canonical", "canonical_to_other_url",\n    "canonical_to_other_domain", "canonical_loop", "missing_h1",\n    "missing_meta_description", "duplicate_title", "duplicate_meta_description",\n}\nUTILITY_ROUTE_PATTERNS = (\n    "/contact", "/contact-us", "/about", "/privacy", "/terms", "/cookie",\n    "/legal", "/ccpa", "/login", "/signin", "/signup", "/register",\n    "/account", "/cart", "/checkout", "/basket", "/reservation/edit",\n    "/reservation/manage", "/booking/edit", "/booking/manage",\n)\nARCHETYPE_REPRESENTATIVE_PATTERNS = {\n    "saas": ("/features", "/pricing", "/product", "/platform", "/integrations", "/use-cases", "/solutions", "/enterprise", "/payments", "/billing", "/connect", "/radar", "/terminal"),\n    "ecommerce": ("/collections/", "/collection/", "/category/", "/categories/", "/shop/", "/products/", "/product/", "/eyeglasses", "/sunglasses", "/contacts"),\n    "publisher": ("/category/", "/categories/", "/topic/", "/topics/", "/guides/", "/reviews/", "/news/", "/resources/"),\n    "finance": ("/mortgage", "/loan", "/loans", "/credit-cards", "/banking", "/insurance", "/calculator"),\n    "nonprofit": ("/projects", "/impact", "/programs", "/donate", "/fundraise"),\n    "education": ("/courses", "/subjects", "/learn", "/math", "/science"),\n    "booking": ("/activities", "/activity", "/experiences", "/events", "/category", "/collections"),\n}\n''',
    "ranking constants",
)

insert_anchor = '\n\ndef representative_page_score(\n'
filter_code = '''\n\ndef filter_page_level_asset_evidence(\n    fix: dict[str, Any],\n    pages: list[dict[str, Any]],\n) -> dict[str, Any] | None:\n    """Keep generic page-level findings on HTML documents only."""\n    rule = str(fix.get("rule") or "").lower()\n    if rule not in PAGE_LEVEL_HTML_ONLY_RULES:\n        return fix\n    page_lookup = {\n        clean_path(page_evidence_url(page)): page\n        for page in pages\n        if clean_path(page_evidence_url(page))\n    }\n    candidates = dedupe_strings([\n        clean_path(url)\n        for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"])\n        if clean_path(url)\n    ])\n    html_pages = [\n        url for url in candidates\n        if not is_non_html_page_evidence({**page_lookup.get(url, {}), "url": url})\n    ]\n    if not html_pages:\n        return None\n    selected = clean_path(fix.get("page_url") or "")\n    if selected not in html_pages:\n        selected = html_pages[0]\n    return {\n        **fix,\n        "page_url": selected,\n        "representative_page_url": selected,\n        "affected_pages": html_pages,\n        "page_count": len(html_pages),\n        "asset_urls_excluded": int_or_zero(fix.get("asset_urls_excluded")) + max(0, len(candidates) - len(html_pages)),\n        "page_level_asset_evidence_version": PAGE_LEVEL_ASSET_EVIDENCE_VERSION,\n    }\n\n\ndef representative_archetype_key(playbook: dict[str, Any]) -> str:\n    label = str(playbook.get("label") or "").lower()\n    if any(token in label for token in ("saas", "software", "app", "platform")):\n        return "saas"\n    if any(token in label for token in ("ecommerce", "retail", "commerce")):\n        return "ecommerce"\n    if any(token in label for token in ("publisher", "content", "blog")):\n        return "publisher"\n    if any(token in label for token in ("finance", "insurance", "lending")):\n        return "finance"\n    if any(token in label for token in ("nonprofit", "fundraising", "charity")):\n        return "nonprofit"\n    if any(token in label for token in ("education", "learning")):\n        return "education"\n    if any(token in label for token in ("booking", "experience", "marketplace")):\n        return "booking"\n    return ""\n\n'''
if insert_anchor not in text:
    raise SystemExit("representative score anchor missing")
text = text.replace(insert_anchor, filter_code + insert_anchor, 1)

start = text.index("def representative_page_score(\n")
end = text.index("\n\ndef select_representative_page(\n", start)
new_score = '''def representative_page_score(\n    url: str,\n    fix: dict[str, Any],\n    page_lookup: dict[str, dict[str, Any]],\n    body: dict[str, Any],\n    playbook: dict[str, Any],\n) -> int:\n    path = clean_path(url) or "/"\n    lower = path.lower()\n    page = page_lookup.get(path, {})\n    rule = str(fix.get("rule") or "").lower()\n    direct_evidence = rule in DIRECT_EVIDENCE_RULES\n    requested = clean_path(\n        body.get("requested_path_prefix")\n        or body.get("crawl_path_prefix")\n        or body.get("path_prefix")\n        or ""\n    )\n    family = normalize_template_family(\n        page.get("page_template_family") or fix.get("page_template_family"),\n        path,\n    )\n    archetype = representative_archetype_key(playbook)\n\n    score = 20\n    if path in {"/", "/index.html"}:\n        score += 75\n    if requested and path.rstrip("/") == requested.rstrip("/"):\n        score += 70\n    if any(pattern in lower for pattern in playbook.get("money_patterns", [])):\n        score += 35\n    if family in {\n        "homepage", "loan_program", "conversion", "calculator", "comparison_page",\n        "product_page", "collection_page", "activity_detail", "location_landing",\n        "guide_article",\n    }:\n        score += 25\n    if family in {"collection_page", "category", "archive"} and archetype in {"ecommerce", "publisher", "booking"}:\n        score += 25\n    for pattern in ARCHETYPE_REPRESENTATIVE_PATTERNS.get(archetype, ()):\n        if pattern in lower:\n            score += 55\n            break\n    if clean_str(page.get("title")) or clean_str(page.get("h1")):\n        score += 8\n    if page_is_indexable(page):\n        score += 5\n    if any(pattern in lower for pattern in UTILITY_ROUTE_PATTERNS):\n        score -= 95\n    if is_low_value_page(path):\n        score -= 65\n    if is_non_html_page_evidence({**page, "url": path}):\n        score -= 250\n    if is_route_boundary_candidate(path) or is_internal_app_route(path):\n        score += 15 if rule in ROUTE_BOUNDARY_RULES else -100\n    status = int_or_zero(page.get("status_code") or page.get("status"))\n    if status >= 400 or is_blocked_access_page(page):\n        score += 15 if direct_evidence else -60\n    elif direct_evidence:\n        score += 5\n    return score\n'''
text = text[:start] + new_score + text[end:]

text = replace_once(
    text,
    '''    filtered = [filter_orphan_asset_evidence(fix, pages) for fix in normalized]\n    normalized = [fix for fix in filtered if fix is not None]\n    normalized = [select_representative_page(fix, pages, body, playbook) for fix in normalized]\n''',
    '''    filtered = [filter_orphan_asset_evidence(fix, pages) for fix in normalized]\n    normalized = [fix for fix in filtered if fix is not None]\n    filtered = [filter_page_level_asset_evidence(fix, pages) for fix in normalized]\n    normalized = [fix for fix in filtered if fix is not None]\n    normalized = [select_representative_page(fix, pages, body, playbook) for fix in normalized]\n''',
    "prepare filters",
)
REVIEW.write_text(text, encoding="utf-8")

beta = BETA.read_text(encoding="utf-8")
beta = replace_once(
    beta,
    '''        ARCHETYPE_CLASSIFIER_VERSION,\n        ORPHAN_ASSET_EVIDENCE_VERSION,\n        QUALITY_GATE_VERSION,\n''',
    '''        ARCHETYPE_CLASSIFIER_VERSION,\n        ORPHAN_ASSET_EVIDENCE_VERSION,\n        PAGE_LEVEL_ASSET_EVIDENCE_VERSION,\n        REPRESENTATIVE_PAGE_VERSION,\n        QUALITY_GATE_VERSION,\n''',
    "beta imports",
)
beta = replace_once(
    beta,
    '''        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,\n        "orphan_asset_evidence_version": ORPHAN_ASSET_EVIDENCE_VERSION,\n''',
    '''        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,\n        "representative_page_version": REPRESENTATIVE_PAGE_VERSION,\n        "page_level_asset_evidence_version": PAGE_LEVEL_ASSET_EVIDENCE_VERSION,\n        "orphan_asset_evidence_version": ORPHAN_ASSET_EVIDENCE_VERSION,\n''',
    "beta versions",
)
BETA.write_text(beta, encoding="utf-8")

revision = json.loads(REVISION.read_text(encoding="utf-8"))
revision["component_versions"]["representative_page_version"] = NEW_REP
revision["component_versions"]["page_level_asset_evidence_version"] = NEW_ASSET
revision["fingerprint"] = NEW_FP
revision["git_commit"] = "3f47c52347b02a0f688632db5dbc6bf592e53e66"
revision["recorded_at"] = "2026-07-16T15:00:00+00:00"
revision["note"] = "Representative evidence v8 candidate: archetype-aware category, collection, product, feature and topic-hub ranking; utility and transaction routes demoted; generic page-level findings restricted to HTML evidence. Focused production acceptance required before freeze."
REVISION.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

for path in [ROOT / "src/lib/scanRunModel.js", *sorted((ROOT / "tests/frontend").glob("*.mjs")), *sorted((ROOT / "scanner-api/tests").glob("*.py"))]:
    value = path.read_text(encoding="utf-8")
    value = value.replace(OLD_FP, NEW_FP)
    value = value.replace("business_representative_page_v1", NEW_REP)
    path.write_text(value, encoding="utf-8")

print(f"Applied representative evidence v8 with fingerprint {NEW_FP}")
