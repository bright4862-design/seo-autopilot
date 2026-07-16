from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "scanner-api/app/review.py"
REVISION = ROOT / "data/beta-crawler-revision.json"
SCAN_RUN_MODEL = ROOT / "src/lib/scanRunModel.js"
TEST_FILE = ROOT / "scanner-api/tests/test_focused_acceptance_followup_v8.py"

OLD_CLASSIFIER = "archetype_classifier_v7_html_route_app_distribution"
NEW_CLASSIFIER = "archetype_classifier_v8_platform_product_routes"
OLD_REPRESENTATIVE = "business_representative_page_v2_archetype_route_families"
NEW_REPRESENTATIVE = "business_representative_page_v3_sitewide_archetype_ranking"
OLD_PAGE_ASSET = "page_level_asset_evidence_v2_html_only"
NEW_PAGE_ASSET = "page_level_asset_evidence_v3_markdown"
OLD_FINGERPRINT = "561db6e131da53a9"
NEW_FINGERPRINT = "430813f2b15afa8f"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def replace_all_checked(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} matches, found {count}")
    return text.replace(old, new)


review = REVIEW.read_text(encoding="utf-8")
review = replace_once(review, f'ARCHETYPE_CLASSIFIER_VERSION = "{OLD_CLASSIFIER}"', f'ARCHETYPE_CLASSIFIER_VERSION = "{NEW_CLASSIFIER}"', "classifier marker")
review = replace_once(review, f'REPRESENTATIVE_PAGE_VERSION = "{OLD_REPRESENTATIVE}"', f'REPRESENTATIVE_PAGE_VERSION = "{NEW_REPRESENTATIVE}"', "representative marker")
review = replace_once(review, f'PAGE_LEVEL_ASSET_EVIDENCE_VERSION = "{OLD_PAGE_ASSET}"', f'PAGE_LEVEL_ASSET_EVIDENCE_VERSION = "{NEW_PAGE_ASSET}"', "asset marker")

review = replace_once(
    review,
    '    ".ico", ".jpeg", ".jpg", ".js", ".json", ".map", ".mp3", ".mp4",\n',
    '    ".ico", ".jpeg", ".jpg", ".js", ".json", ".map", ".md", ".markdown", ".mp3", ".mp4",\n',
    "markdown asset extensions",
)

review = replace_all_checked(
    review,
    '    "/platform", "/apps", "/download",\n',
    '    "/platform", "/apps", "/download", "/payments", "/billing",\n'
    '    "/connect", "/radar", "/terminal", "/issuing", "/treasury",\n'
    '    "/tax", "/identity", "/atlas", "/financial-connections",\n',
    2,
    "SaaS structural product routes",
)
review = replace_once(
    review,
    '    ("product", ("/features", "/platform", "/apps", "/download")),\n',
    '    ("product", ("/features", "/platform", "/apps", "/download", "/payments",\n'
    '                 "/billing", "/connect", "/radar", "/terminal", "/issuing",\n'
    '                 "/treasury", "/tax", "/identity", "/atlas",\n'
    '                 "/financial-connections")),\n',
    "SaaS product family",
)
review = replace_once(
    review,
    'APP_DISTRIBUTION_PLATFORM_PATTERNS = (\n'
    '    "/download/android", "/download/ios", "/download/windows",\n'
    '    "/download/macos", "/download/linux",\n'
    ')\n',
    'APP_DISTRIBUTION_PLATFORM_PATTERNS = (\n'
    '    "/download/android", "/download/ios", "/download/windows",\n'
    '    "/download/macos", "/download/linux",\n'
    ')\n'
    'PLATFORM_PRODUCT_PATTERNS = (\n'
    '    "/payments", "/billing", "/connect", "/radar", "/terminal",\n'
    '    "/issuing", "/treasury", "/tax", "/identity", "/atlas",\n'
    '    "/financial-connections",\n'
    ')\n',
    "platform product pattern constant",
)
review = replace_once(
    review,
    '    app_distribution_platforms = [\n'
    '        pattern\n'
    '        for pattern in APP_DISTRIBUTION_PLATFORM_PATTERNS\n'
    '        if any(pattern in path for path in page_paths)\n'
    '    ]\n',
    '    app_distribution_platforms = [\n'
    '        pattern\n'
    '        for pattern in APP_DISTRIBUTION_PLATFORM_PATTERNS\n'
    '        if any(pattern in path for path in page_paths)\n'
    '    ]\n'
    '    platform_product_routes = [\n'
    '        pattern\n'
    '        for pattern in PLATFORM_PRODUCT_PATTERNS\n'
    '        if any(path == pattern or path.startswith(pattern + "/") for path in page_paths)\n'
    '    ]\n',
    "platform route evidence",
)
review = replace_once(
    review,
    '    saas_app_distribution_identity = bool(\n'
    '        "/download" in saas_core_structural\n'
    '        and "developer" in saas_business_families\n'
    '        and len(app_distribution_platforms) >= 3\n'
    '    )\n'
    '    saas_dominant = bool(\n'
    '        saas_business_identity\n'
    '        or saas_diverse_structure\n'
    '        or saas_app_distribution_identity\n'
    '        or software_schema_pages >= 2\n'
    '    )\n',
    '    saas_app_distribution_identity = bool(\n'
    '        "/download" in saas_core_structural\n'
    '        and "developer" in saas_business_families\n'
    '        and len(app_distribution_platforms) >= 3\n'
    '    )\n'
    '    saas_platform_infrastructure_identity = bool(\n'
    '        len(platform_product_routes) >= 3\n'
    '        and "developer" in saas_business_families\n'
    '        and saas_route_pages >= 4\n'
    '    )\n'
    '    saas_dominant = bool(\n'
    '        saas_business_identity\n'
    '        or saas_diverse_structure\n'
    '        or saas_app_distribution_identity\n'
    '        or saas_platform_infrastructure_identity\n'
    '        or software_schema_pages >= 2\n'
    '    )\n',
    "platform infrastructure identity",
)
review = replace_once(
    review,
    '                if saas_app_distribution_identity:\n'
    '                    score += 20.0\n',
    '                if saas_app_distribution_identity:\n'
    '                    score += 20.0\n'
    '                if saas_platform_infrastructure_identity:\n'
    '                    score += 24.0\n',
    "platform score boost",
)
review = replace_once(
    review,
    '            "app_distribution_platforms": app_distribution_platforms,\n'
    '            "saas_homepage_identity": saas_homepage_identity,\n',
    '            "app_distribution_platforms": app_distribution_platforms,\n'
    '            "platform_product_routes": platform_product_routes,\n'
    '            "saas_platform_infrastructure_identity": saas_platform_infrastructure_identity,\n'
    '            "saas_homepage_identity": saas_homepage_identity,\n',
    "platform diagnostics",
)
review = replace_once(
    review,
    '            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "\n'
    '            f"nonprofit={nonprofit_dominant}; "\n',
    '            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "\n'
    '            f"platform_infrastructure={saas_platform_infrastructure_identity}, "\n'
    '            f"nonprofit={nonprofit_dominant}; "\n',
    "platform winning reason",
)

review = replace_once(
    review,
    'def collapse_sitewide_template_findings(\n'
    '    fixes: list[dict[str, Any]],\n'
    '    pages: list[dict[str, Any]],\n'
    '    site_fingerprint: dict[str, Any],\n'
    ') -> list[dict[str, Any]]:\n',
    'def collapse_sitewide_template_findings(\n'
    '    fixes: list[dict[str, Any]],\n'
    '    pages: list[dict[str, Any]],\n'
    '    site_fingerprint: dict[str, Any],\n'
    '    body: dict[str, Any],\n'
    '    playbook: dict[str, Any],\n'
    ') -> list[dict[str, Any]]:\n',
    "sitewide signature",
)
review = replace_once(
    review,
    '    if len(usable_pages) < SITEWIDE_MIN_PAGES:\n'
    '        return fixes\n\n'
    '    output = list(fixes)\n',
    '    if len(usable_pages) < SITEWIDE_MIN_PAGES:\n'
    '        return fixes\n\n'
    '    page_lookup = {\n'
    '        clean_path(page_evidence_url(page)): page\n'
    '        for page in pages\n'
    '        if clean_path(page_evidence_url(page))\n'
    '    }\n'
    '    output = list(fixes)\n',
    "sitewide page lookup",
)
review = replace_once(
    review,
    '        representative_pages = dedupe_strings([\n'
    '            pages_for_family[0]\n'
    '            for _, pages_for_family in sorted(representative_pages_by_family.items())\n'
    '            if pages_for_family\n'
    '        ])\n'
    '        base = max(candidates, key=fix_sort_key)\n',
    '        representative_pages = dedupe_strings([\n'
    '            pages_for_family[0]\n'
    '            for _, pages_for_family in sorted(representative_pages_by_family.items())\n'
    '            if pages_for_family\n'
    '        ])\n'
    '        base = max(candidates, key=fix_sort_key)\n'
    '        original_position = {url: index for index, url in enumerate(affected_usable)}\n'
    '        ranked_affected = sorted(\n'
    '            affected_usable,\n'
    '            key=lambda url: (\n'
    '                representative_page_score(url, {**base, "rule": rule}, page_lookup, body, playbook),\n'
    '                -original_position[url],\n'
    '            ),\n'
    '            reverse=True,\n'
    '        )\n'
    '        ranked_source_pages = dedupe_strings(ranked_affected[:5] + representative_pages)\n',
    "sitewide ranking",
)
review = replace_once(
    review,
    '            "page_url": representative_pages[0] if representative_pages else affected_usable[0],\n'
    '            "affected_pages": affected_usable[:150],\n'
    '            "source_pages": representative_pages[:30],\n',
    '            "page_url": ranked_affected[0],\n'
    '            "representative_page_url": ranked_affected[0],\n'
    '            "representative_page_version": REPRESENTATIVE_PAGE_VERSION,\n'
    '            "representative_page_reason": "Highest archetype-aware business-value page in the site-wide affected evidence.",\n'
    '            "affected_pages": ranked_affected[:150],\n'
    '            "source_pages": ranked_source_pages[:30],\n',
    "sitewide selected fields",
)
review = replace_once(
    review,
    '    scored = collapse_sitewide_template_findings(scored, pages, site_fingerprint)\n',
    '    scored = collapse_sitewide_template_findings(scored, pages, site_fingerprint, body, playbook)\n',
    "sitewide call",
)
REVIEW.write_text(review, encoding="utf-8")

revision = json.loads(REVISION.read_text(encoding="utf-8"))
components = revision["component_versions"]
components["archetype_classifier_version"] = NEW_CLASSIFIER
components["representative_page_version"] = NEW_REPRESENTATIVE
components["page_level_asset_evidence_version"] = NEW_PAGE_ASSET
revision["fingerprint"] = NEW_FINGERPRINT
revision["git_commit"] = "82bc4c41aa5b74238fa068f99507b2d0726e1180"
revision["recorded_at"] = "2026-07-17T00:00:00+00:00"
revision["note"] = (
    "Focused v8 acceptance follow-up candidate: platform-product route identity for infrastructure SaaS; "
    "Markdown excluded from page-level HTML evidence; site-wide representatives use archetype-aware ranking."
)
REVISION.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

model = SCAN_RUN_MODEL.read_text(encoding="utf-8")
model = replace_once(model, OLD_CLASSIFIER, NEW_CLASSIFIER, "frontend classifier marker")
model = replace_once(model, OLD_FINGERPRINT, NEW_FINGERPRINT, "frontend fingerprint")
SCAN_RUN_MODEL.write_text(model, encoding="utf-8")

for root in (ROOT / "scanner-api/tests", ROOT / "tests/frontend"):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".js", ".mjs", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        updated = (
            text.replace(OLD_CLASSIFIER, NEW_CLASSIFIER)
            .replace(OLD_REPRESENTATIVE, NEW_REPRESENTATIVE)
            .replace(OLD_PAGE_ASSET, NEW_PAGE_ASSET)
            .replace(OLD_FINGERPRINT, NEW_FINGERPRINT)
        )
        if updated != text:
            path.write_text(updated, encoding="utf-8")

TEST_FILE.write_text('''"""Production-shaped regressions from the focused representative-evidence acceptance."""\n\nfrom app.review import build_site_fingerprint, get_playbook, prepare_fixes\n\n\ndef page(url, title="", h1="", meta="", schema=None, status=200, family="standard", content_type="text/html"):\n    return {\n        "url": url,\n        "status_code": status,\n        "title": title,\n        "h1": h1,\n        "meta_description": meta,\n        "schema_types": schema or [],\n        "page_template_family": family,\n        "content_type": content_type,\n        "indexable": status == 200,\n    }\n\n\ndef test_platform_product_routes_keep_docs_heavy_infrastructure_site_saas():\n    pages = [page("https://platform.example/", "Financial infrastructure for the internet", "Build financial products", "APIs and infrastructure for businesses")]\n    for index in range(45):\n        pages.append(page(\n            f"https://platform.example/docs/guide-{index}",\n            f"Developer guide {index}",\n            "Developer documentation",\n            "API integration guide",\n            ["TechArticle"],\n            family="guide_article",\n        ))\n    for route in ("payments", "billing", "connect", "radar", "terminal", "issuing"):\n        pages.append(page(\n            f"https://platform.example/{route}",\n            route.title(),\n            f"{route.title()} platform",\n            "Build and operate financial products",\n            family="product_page",\n        ))\n    pages.extend([\n        page("https://platform.example/docs/api", "API reference", "Developer API", family="guide_article"),\n        page("https://platform.example/developers", "Developers", "Developer platform", family="guide_article"),\n    ])\n    fingerprint = build_site_fingerprint(\n        {"pages_found": len(pages), "pages_crawled": len(pages)},\n        pages,\n        "https://platform.example",\n    )\n    assert fingerprint["primary_archetype"] == "saas_app_membership", fingerprint["classification"]["winning_reason"]\n    signals = fingerprint["classification"]["structural_signals"]\n    assert signals["saas_platform_infrastructure_identity"] is True\n    assert len(signals["platform_product_routes"]) >= 3\n\n\ndef test_markdown_failed_page_is_removed_from_page_level_broken_evidence():\n    pages = [\n        page("https://shop.example/llms/pages/measure-your-pd.md", status=404, content_type="text/markdown"),\n        page("https://shop.example/sunglasses/metallic", "Metallic sunglasses", status=404, family="collection_page"),\n        page("https://shop.example/", "Eyewear", "Shop eyewear", "Glasses and sunglasses"),\n    ]\n    fingerprint = build_site_fingerprint(\n        {"pages_found": len(pages), "pages_crawled": len(pages)},\n        pages,\n        "https://shop.example",\n    )\n    fixes = prepare_fixes(\n        [{\n            "rule": "broken_page",\n            "category": "404_error",\n            "source": "scanner_verified_failed_pages:404",\n            "affected_pages": ["/llms/pages/measure-your-pd.md", "/sunglasses/metallic"],\n            "page_url": "/llms/pages/measure-your-pd.md",\n        }],\n        fingerprint,\n        {},\n        get_playbook(fingerprint["primary_archetype"]),\n        pages,\n    )\n    assert len(fixes) == 1\n    assert fixes[0]["page_url"] == "/sunglasses/metallic"\n    assert fixes[0]["affected_pages"] == ["/sunglasses/metallic"]\n    assert fixes[0]["page_level_asset_evidence_version"] == "page_level_asset_evidence_v3_markdown"\n\n\ndef test_sitewide_canonical_uses_finance_business_page_not_contact():\n    pages = [\n        page("https://lender.example/", "Private lending", "Real estate loans", "Bridge and investor lending", family="homepage"),\n        page("https://lender.example/contact", "Contact", "Contact us", family="contact"),\n        page("https://lender.example/apply-now", "Apply now", "Apply for financing", family="conversion"),\n        page("https://lender.example/loan-overview", "Loan overview", "Loan programs", family="loan_program"),\n        page("https://lender.example/bridge-loans", "Bridge loans", "Bridge financing", family="loan_program"),\n        page("https://lender.example/dscr-loans", "DSCR loans", "DSCR financing", family="loan_program"),\n        page("https://lender.example/fix-and-flip", "Fix and flip", "Fix and flip loans", family="loan_program"),\n        page("https://lender.example/blog/bridge-loan-guide", "Bridge loan guide", "Bridge loan guide", family="guide_article"),\n        page("https://lender.example/blog/dscr-guide", "DSCR guide", "DSCR guide", family="guide_article"),\n        page("https://lender.example/locations/california", "California loans", "California lending", family="location_landing"),\n        page("https://lender.example/locations/texas", "Texas loans", "Texas lending", family="location_landing"),\n        page("https://lender.example/about", "About", "About the lender", family="standard"),\n    ]\n    body = {"pages_found": len(pages), "pages_crawled": len(pages)}\n    fingerprint = build_site_fingerprint(body, pages, "https://lender.example")\n    playbook = get_playbook(fingerprint["primary_archetype"])\n    raw_fixes = [\n        {\n            "rule": "canonical_missing",\n            "category": "canonical",\n            "source": "page_pattern:canonical_missing",\n            "page_template_family": family,\n            "affected_pages": urls,\n            "issue_title": "Add canonical URLs",\n        }\n        for family, urls in (\n            ("contact", ["/contact", "/about", "/"]),\n            ("conversion", ["/apply-now", "/locations/california", "/locations/texas"]),\n            ("loan_program", ["/loan-overview", "/bridge-loans", "/dscr-loans", "/fix-and-flip"]),\n            ("guide_article", ["/blog/bridge-loan-guide", "/blog/dscr-guide"]),\n        )\n    ]\n    fixes = prepare_fixes(raw_fixes, fingerprint, body, playbook, pages)\n    sitewide = next(fix for fix in fixes if fix.get("page_scope") == "sitewide")\n    assert sitewide["page_url"] in {"/apply-now", "/loan-overview", "/bridge-loans", "/dscr-loans", "/fix-and-flip"}\n    assert sitewide["page_url"] != "/contact"\n    assert sitewide["representative_page_version"] == "business_representative_page_v3_sitewide_archetype_ranking"\n''', encoding="utf-8")

print("Applied focused acceptance follow-up patch")
