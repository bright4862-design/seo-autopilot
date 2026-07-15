#!/usr/bin/env python3
"""Apply the narrow classifier v7 patch derived from focused production evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_CLASSIFIER = "archetype_classifier_v6_saas_business_identity"
NEW_CLASSIFIER = "archetype_classifier_v7_html_route_app_distribution"
OLD_FINGERPRINT = "fa1bfae405d970fa"
NEW_FINGERPRINT = "2dd346f90e64f94b"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


review_path = ROOT / "scanner-api/app/review.py"
review = review_path.read_text(encoding="utf-8")
review = replace_once(
    review,
    f'ARCHETYPE_CLASSIFIER_VERSION = "{OLD_CLASSIFIER}"',
    f'ARCHETYPE_CLASSIFIER_VERSION = "{NEW_CLASSIFIER}"',
    "classifier marker",
)
review = replace_once(
    review,
    '''SAAS_BUSINESS_FAMILY_PATTERNS = (
    ("product", ("/features", "/platform", "/apps", "/download")),
    ("commercial", ("/pricing", "/free-trial", "/trial", "/demo", "/contact-sales", "/enterprise")),
    ("adoption", ("/integrations", "/use-cases", "/solutions", "/customers", "/customer-stories", "/case-studies")),
    ("access", ("/login", "/signin", "/signup", "/register")),
    ("developer", ("/docs", "/api", "/developers")),
)
''',
    '''SAAS_BUSINESS_FAMILY_PATTERNS = (
    ("product", ("/features", "/platform", "/apps", "/download")),
    ("commercial", ("/pricing", "/free-trial", "/trial", "/demo", "/contact-sales", "/enterprise")),
    ("adoption", ("/integrations", "/use-cases", "/solutions", "/customers", "/customer-stories", "/case-studies")),
    ("access", ("/login", "/signin", "/signup", "/register")),
    ("developer", ("/docs", "/api", "/developers")),
)
APP_DISTRIBUTION_PLATFORM_PATTERNS = (
    "/download/android", "/download/ios", "/download/windows",
    "/download/macos", "/download/linux",
)
''',
    "app distribution patterns",
)
review = replace_once(
    review,
    '''def build_site_fingerprint(body: dict[str, Any], pages: list[dict[str, Any]], website_url: str) -> dict[str, Any]:
    text_parts: list[str] = [
''',
    '''def build_site_fingerprint(body: dict[str, Any], pages: list[dict[str, Any]], website_url: str) -> dict[str, Any]:
    # Only HTML evidence may define a business route family. Asset filenames such
    # as signup-form.png or demo-site.png are crawl evidence, not product routes.
    classifier_pages = [
        page for page in pages[:220]
        if not is_non_html_page_evidence(page)
    ]
    text_parts: list[str] = [
''',
    "classifier HTML pages",
)
review = replace_once(
    review,
    "    for page in pages[:220]:\n        text_parts.extend([",
    "    for page in classifier_pages:\n        text_parts.extend([",
    "classifier text pages",
)
review = replace_once(
    review,
    '''    homepage_text = ""
    if pages:
        homepage = min(pages[:220], key=lambda page: len(clean_path(page_evidence_url(page)) or "/"))
''',
    '''    homepage_text = ""
    if classifier_pages:
        homepage = min(classifier_pages, key=lambda page: len(clean_path(page_evidence_url(page)) or "/"))
''',
    "classifier homepage pages",
)
review = replace_once(
    review,
    '''    page_paths = [clean_path(page_evidence_url(page)).lower() for page in pages[:220]]
    path_text = " ".join(page_paths)
''',
    '''    page_paths = [clean_path(page_evidence_url(page)).lower() for page in classifier_pages]
    path_text = " ".join(page_paths)
''',
    "classifier route pages",
)
review = review.replace(
    'count_schema_pages(pages, ("product", "offer"))',
    'count_schema_pages(classifier_pages, ("product", "offer"))',
)
review = review.replace(
    'count_schema_pages(pages, ("article", "blogposting", "newsarticle"))',
    'count_schema_pages(classifier_pages, ("article", "blogposting", "newsarticle"))',
)
review = review.replace(
    'count_schema_pages(pages, ("softwareapplication", "mobileapplication", "webapplication"))',
    'count_schema_pages(classifier_pages, ("softwareapplication", "mobileapplication", "webapplication"))',
)
review = replace_once(
    review,
    '''    booking_listing_pages = sum(
        1 for page in pages[:220]
        if any(pattern in clean_path(page_evidence_url(page)).lower() for pattern in BOOKING_LISTING_PATTERNS)
    )
''',
    '''    booking_listing_pages = sum(
        1 for page in classifier_pages
        if any(pattern in clean_path(page_evidence_url(page)).lower() for pattern in BOOKING_LISTING_PATTERNS)
    )
''',
    "booking HTML routes",
)
review = replace_once(
    review,
    '''    saas_business_families = [
        family
        for family, patterns in SAAS_BUSINESS_FAMILY_PATTERNS
        if any(pattern in path_text for pattern in patterns)
    ]
''',
    '''    saas_business_families = [
        family
        for family, patterns in SAAS_BUSINESS_FAMILY_PATTERNS
        if any(pattern in path_text for pattern in patterns)
    ]
    app_distribution_platforms = [
        pattern
        for pattern in APP_DISTRIBUTION_PLATFORM_PATTERNS
        if any(pattern in path for path in page_paths)
    ]
''',
    "app distribution evidence",
)
review = replace_once(
    review,
    '''    saas_diverse_structure = bool(
        len(saas_core_structural) >= 3
        and len(saas_business_families) >= 2
        and saas_route_pages >= 3
    )
    saas_dominant = bool(
        saas_business_identity
        or saas_diverse_structure
        or software_schema_pages >= 2
    )
''',
    '''    saas_diverse_structure = bool(
        len(saas_core_structural) >= 3
        and len(saas_business_families) >= 2
        and saas_route_pages >= 3
    )
    saas_app_distribution_identity = bool(
        "/download" in saas_core_structural
        and "developer" in saas_business_families
        and len(app_distribution_platforms) >= 3
    )
    saas_dominant = bool(
        saas_business_identity
        or saas_diverse_structure
        or saas_app_distribution_identity
        or software_schema_pages >= 2
    )
''',
    "app distribution dominance",
)
review = replace_once(
    review,
    '''                if saas_homepage_identity:
                    score += 20.0
''',
    '''                if saas_homepage_identity:
                    score += 20.0
                if saas_app_distribution_identity:
                    score += 20.0
''',
    "app distribution score",
)
review = replace_once(
    review,
    '''            "saas_route_pages": saas_route_pages,
            "saas_business_families": saas_business_families,
''',
    '''            "classifier_html_route_pages": len(classifier_pages),
            "saas_route_pages": saas_route_pages,
            "saas_business_families": saas_business_families,
            "app_distribution_platforms": app_distribution_platforms,
''',
    "classifier route diagnostics",
)
review = replace_once(
    review,
    '''            "saas_diverse_structure": saas_diverse_structure,
            "finance_route_pages": finance_route_pages,
''',
    '''            "saas_diverse_structure": saas_diverse_structure,
            "saas_app_distribution_identity": saas_app_distribution_identity,
            "finance_route_pages": finance_route_pages,
''',
    "app distribution diagnostics",
)
review = replace_once(
    review,
    '''            f"dominance publisher={publisher_dominant}, retail={retail_dominant}, "
            f"saas={saas_dominant}, nonprofit={nonprofit_dominant}; "
''',
    '''            f"dominance publisher={publisher_dominant}, retail={retail_dominant}, "
            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "
            f"nonprofit={nonprofit_dominant}; "
''',
    "winning reason diagnostics",
)
review_path.write_text(review, encoding="utf-8")

# Update exact durable marker contracts and existing regression expectations.
marker_targets = [
    ROOT / "src/lib/scanRunModel.js",
    *sorted((ROOT / "tests/frontend").glob("*.mjs")),
    *sorted((ROOT / "scanner-api/tests").glob("*.py")),
]
for path in marker_targets:
    text = path.read_text(encoding="utf-8")
    text = text.replace(OLD_CLASSIFIER, NEW_CLASSIFIER)
    text = text.replace(OLD_FINGERPRINT, NEW_FINGERPRINT)
    path.write_text(text, encoding="utf-8")

revision_path = ROOT / "data/beta-crawler-revision.json"
revision = json.loads(revision_path.read_text(encoding="utf-8"))
revision["component_versions"]["archetype_classifier_version"] = NEW_CLASSIFIER
revision["fingerprint"] = NEW_FINGERPRINT
revision["git_commit"] = "5ee02d66416b2265b893a337ebc680e816be59c9"
revision["recorded_at"] = "2026-07-15T22:55:00+00:00"
revision["note"] = (
    "Classifier v7 candidate: non-HTML assets cannot define route families, and "
    "platform-specific app downloads plus developer documentation establish app identity. "
    "Focused nine-site production acceptance remains required before release freeze."
)
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"Applied {NEW_CLASSIFIER} with fingerprint {NEW_FINGERPRINT}.")
