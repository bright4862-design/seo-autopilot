#!/usr/bin/env python3
"""Apply the focused classifier v6 SaaS/content weighting patch."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_CLASSIFIER = "archetype_classifier_v5_business_representative_pages"
NEW_CLASSIFIER = "archetype_classifier_v6_saas_business_identity"
OLD_FINGERPRINT = "7fc00bb6c61a37ed"
NEW_FINGERPRINT = "fa1bfae405d970fa"
BASELINE_COMMIT = "319a3d675bb339ccdd8bf516e8f59a3ea9fadaa9"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


review_path = ROOT / "scanner-api/app/review.py"
replace_once(
    review_path,
    f'ARCHETYPE_CLASSIFIER_VERSION = "{OLD_CLASSIFIER}"',
    f'ARCHETYPE_CLASSIFIER_VERSION = "{NEW_CLASSIFIER}"',
)
replace_once(
    review_path,
    '''SAAS_STRUCTURAL_PATTERNS = (
    "/pricing", "/features", "/integrations", "/use-cases", "/solutions",
    "/customers", "/customer-stories", "/case-studies", "/login", "/signin",
    "/signup", "/register", "/demo", "/docs", "/api", "/developers",
    "/platform", "/apps", "/download",
)''',
    '''SAAS_STRUCTURAL_PATTERNS = (
    "/pricing", "/free-trial", "/trial", "/contact-sales", "/enterprise",
    "/features", "/integrations", "/use-cases", "/solutions",
    "/customers", "/customer-stories", "/case-studies", "/login", "/signin",
    "/signup", "/register", "/demo", "/docs", "/api", "/developers",
    "/platform", "/apps", "/download",
)''',
)
replace_once(
    review_path,
    '''SAAS_CORE_IDENTITY_PATTERNS = (
    "/pricing", "/features", "/integrations", "/use-cases", "/customers",
    "/customer-stories", "/case-studies", "/login", "/signin", "/signup",
    "/register", "/demo", "/api", "/developers", "/platform",
)''',
    '''SAAS_CORE_IDENTITY_PATTERNS = (
    "/pricing", "/free-trial", "/trial", "/contact-sales", "/enterprise",
    "/features", "/integrations", "/use-cases", "/solutions", "/customers",
    "/customer-stories", "/case-studies", "/login", "/signin", "/signup",
    "/register", "/demo", "/api", "/developers", "/platform", "/apps",
    "/download",
)
SAAS_BUSINESS_FAMILY_PATTERNS = (
    ("product", ("/features", "/platform", "/apps", "/download")),
    ("commercial", ("/pricing", "/free-trial", "/trial", "/demo", "/contact-sales", "/enterprise")),
    ("adoption", ("/integrations", "/use-cases", "/solutions", "/customers", "/customer-stories", "/case-studies")),
    ("access", ("/login", "/signin", "/signup", "/register")),
    ("developer", ("/docs", "/api", "/developers")),
)''',
)
replace_once(
    review_path,
    '''    nonprofit_structural = [pattern for pattern in NONPROFIT_STRUCTURAL_PATTERNS if pattern in path_text]
    saas_core_structural = [pattern for pattern in SAAS_CORE_IDENTITY_PATTERNS if pattern in path_text]
    ecommerce_marketplace_patterns = ("/itm/", "/sch/", "/b/", "/buy/", "/seller/", "/listing/")''',
    '''    nonprofit_structural = [pattern for pattern in NONPROFIT_STRUCTURAL_PATTERNS if pattern in path_text]
    saas_core_structural = [pattern for pattern in SAAS_CORE_IDENTITY_PATTERNS if pattern in path_text]
    saas_business_families = [
        family
        for family, patterns in SAAS_BUSINESS_FAMILY_PATTERNS
        if any(pattern in path_text for pattern in patterns)
    ]
    ecommerce_marketplace_patterns = ("/itm/", "/sch/", "/b/", "/buy/", "/seller/", "/listing/")''',
)
replace_once(
    review_path,
    '''    saas_homepage_identity = has_any(homepage_text, [
    "software", "saas", "platform", "app", "application", "workspace",
    "project management", "customer support", "helpdesk", "messaging",
    "commerce platform", "free trial", "start your trial",
])''',
    '''    saas_homepage_identity = has_any(homepage_text, [
        "software", "saas", "platform", "app", "application", "workspace",
        "project management", "customer support", "helpdesk",
        "social media management", "messaging app", "private messenger",
        "secure messaging", "website builder", "visual development",
        "web experience platform", "design platform", "commerce platform",
        "free trial", "start your trial",
    ])''',
)
replace_once(
    review_path,
    '''    saas_dominant = bool(
    (
        len(saas_core_structural) >= 2
        and saas_route_pages >= 3
        and (
            saas_route_pages >= max(3, round(article_route_pages * 0.50))
            or len(saas_core_structural) >= 4
            or saas_homepage_identity
        )
    )
    or software_schema_pages >= 2
)''',
    '''    saas_business_identity = bool(
        saas_homepage_identity
        and saas_route_pages >= 1
        and any(family in {"product", "commercial"} for family in saas_business_families)
    )
    saas_diverse_structure = bool(
        len(saas_core_structural) >= 3
        and len(saas_business_families) >= 2
        and saas_route_pages >= 3
    )
    saas_dominant = bool(
        saas_business_identity
        or saas_diverse_structure
        or software_schema_pages >= 2
    )''',
)
replace_once(
    review_path,
    '''            else:
                score += 12.0 * len(saas_core_structural)
                score += 2.0 * min(saas_route_pages, 15)''',
    '''            else:
                score += 12.0 * len(saas_core_structural)
                score += 8.0 * len(saas_business_families)
                score += 2.0 * min(saas_route_pages, 15)
                if saas_homepage_identity:
                    score += 20.0''',
)
replace_once(
    review_path,
    '''            "saas_route_pages": saas_route_pages,
            "finance_route_pages": finance_route_pages,''',
    '''            "saas_route_pages": saas_route_pages,
            "saas_business_families": saas_business_families,
            "saas_homepage_identity": saas_homepage_identity,
            "saas_business_identity": saas_business_identity,
            "saas_diverse_structure": saas_diverse_structure,
            "finance_route_pages": finance_route_pages,''',
)

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
revision["git_commit"] = BASELINE_COMMIT
revision["recorded_at"] = "2026-07-15T16:30:00+00:00"
revision["note"] = (
    "Classifier v6 candidate: strong SaaS homepage business identity plus product/commercial "
    "route families can outweigh large content libraries. Focused Signal, Buffer, Webflow, "
    "publisher-control, and SaaS-control acceptance remains required before release freeze."
)
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

(ROOT / "scanner-api/tests/test_classifier_v6_saas_weighting.py").write_text(
    '''"""Focused regression matrix for SaaS sites with large content libraries."""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint


def page(path, *, title="", description="", h1="", schema_types=None):
    return {
        "url": f"https://site.example.com{path}",
        "final_url": f"https://site.example.com{path}",
        "path": path,
        "title": title or path.strip("/").replace("-", " ").title() or "Home",
        "h1": h1 or title,
        "meta_description": description,
        "schema_types": schema_types or [],
        "status_code": 200,
    }


def content_pages(prefix, count, topic):
    return [
        page(
            f"/{prefix}/{topic}-{index}",
            title=f"{topic.title()} guide {index}",
            description=f"Articles, resources, tutorials and insights about {topic}.",
            schema_types=["Article"],
        )
        for index in range(count)
    ]


def classify(pages):
    result = build_site_fingerprint(
        {"website_url": "https://site.example.com", "pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        "https://site.example.com",
    )
    assert result["classification"]["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION
    assert result["classification"]["state"] == "classified"
    return result


def assert_saas(pages):
    result = classify(pages)
    assert result["primary_archetype"] == "saas_app_membership", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["saas_dominant"] is True
    return result


def assert_publisher(pages):
    result = classify(pages)
    assert result["primary_archetype"] == "content_blog", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["saas_dominant"] is False
    return result


def test_signal_shaped_app_beats_large_content_library():
    result = assert_saas([
        page(
            "/",
            title="Private messenger app",
            h1="Speak freely",
            description="Fast, simple and secure messaging app for private conversations.",
        ),
        page("/download", title="Download the app"),
        page("/apps/android", title="Android app"),
        page("/apps/desktop", title="Desktop app"),
    ] + content_pages("blog", 80, "privacy"))
    assert "product" in result["classification"]["structural_signals"]["saas_business_families"]


def test_buffer_shaped_platform_beats_large_resource_library():
    assert_saas([
        page(
            "/",
            title="Social media management platform",
            h1="Grow your audience",
            description="Social media management software for publishing, analytics and engagement.",
        ),
        page("/features/publishing"),
        page("/pricing"),
        page("/free-trial"),
    ] + content_pages("resources", 100, "social-media"))


def test_webflow_shaped_builder_beats_large_content_library():
    assert_saas([
        page(
            "/",
            title="Website builder and visual development platform",
            h1="Build extraordinary websites",
            description="A visual development and web experience platform for professional teams.",
        ),
        page("/features"),
        page("/enterprise"),
        page("/contact-sales"),
    ] + content_pages("resources", 100, "web-design"))


def test_nomadic_matt_shaped_publisher_with_small_shop_stays_publisher():
    assert_publisher([
        page(
            "/",
            title="Travel better, cheaper, longer",
            h1="Travel guides from an independent author",
            description="Destination guides, practical travel advice and stories.",
        ),
        page("/product/travel-book", title="Travel book"),
        page("/checkout", title="Checkout"),
    ] + content_pages("blog", 80, "travel"))


def test_wpbeginner_shaped_knowledge_publisher_stays_publisher():
    assert_publisher([
        page(
            "/",
            title="WordPress tutorials for beginners",
            h1="Beginner-friendly WordPress guides",
            description="Free tutorials, glossary articles and practical WordPress resources.",
        ),
        page("/solutions/hosting"),
        page("/glossary/dashboard"),
    ] + content_pages("beginners-guide", 80, "wordpress"))


def test_existing_saas_controls_remain_saas():
    controls = [
        [
            page("/", title="Project management software", description="A platform for teams."),
            page("/features"), page("/pricing"), page("/login"),
        ],
        [
            page("/", title="Issue tracking software", description="A product platform for modern teams."),
            page("/features"), page("/integrations"), page("/signup"),
        ],
        [
            page("/", title="Customer support platform", description="Helpdesk software for support teams."),
            page("/features"), page("/pricing"), page("/demo"),
        ],
        [
            page("/", title="Commerce platform", description="Software to build and run an online store."),
            page("/features/checkout"), page("/pricing"), page("/signup"),
        ],
    ]
    for pages in controls:
        assert_saas(pages + content_pages("blog", 50, "productivity"))
''',
    encoding="utf-8",
)

print(f"Applied classifier patch {NEW_CLASSIFIER} / {NEW_FINGERPRINT}")
