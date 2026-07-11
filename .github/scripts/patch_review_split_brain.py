from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
extract_path = ROOT / "scanner-api/app/extract.py"
review_path = ROOT / "scanner-api/app/review.py"
test_path = ROOT / "scanner-api/tests/test_page_classification.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


extract = extract_path.read_text()
extract = replace_once(
    extract,
    '''def is_support_content_path(path: str) -> bool:\n    clean = str(path or "").lower().split("?")[0].split("#")[0].rstrip("/") or "/"\n    return bool(SUPPORT_CONTENT_PREFIX_RE.match(clean) or SUPPORT_CONTENT_NESTED_RE.match(clean))\n\n\ndef classify_template(path: str) -> str:\n''',
    '''def is_support_content_path(path: str) -> bool:\n    clean = str(path or "").lower().split("?")[0].split("#")[0].rstrip("/") or "/"\n    return bool(SUPPORT_CONTENT_PREFIX_RE.match(clean) or SUPPORT_CONTENT_NESTED_RE.match(clean))\n\n\nLEGAL_PAGE_RE = re.compile(\n    # Bounded: multi-word legal slugs match anywhere, but short tokens (cgu/cgv/legal/terms)\n    # must be a complete path segment. Unbounded "cgu" matched "domaine-de-lo(cgu)enole".\n    r"(mentions-legales|mentions_legales|politique-de-confidentialite|privacy-policy|privacy_policy"\n    r"|conditions-generales|conditions-generales-de-vente|legal-notice|terms-of-service|terms-and-conditions"\n    r"|terms-of-use|privacy|impressum)"\n    r"|(^|/)(cgu|cgv|legal|terms|mentions|privacite)(/|$)"\n)\n\n\ndef is_legal_page_path(path: str) -> bool:\n    return bool(LEGAL_PAGE_RE.search(str(path or "").lower().split("?")[0]))\n\n\ndef classify_template(path: str) -> str:\n''',
    "insert bounded legal helper",
)
extract = replace_once(
    extract,
    '''    # Trust/legal documents, wherever the CMS puts them (/fr/page/mentions-legales, /cgu).\n    if re.search(r"mentions-legales|mentions_legales|cgu|cgv|privacy|privacite|politique-de-confidentialite|terms|conditions-generales|legal-notice|impressum", clean):\n        return "legal_info"\n    # Category/theme/collection LANDING pages win over money-keyword rules: /fr/category/simulateur\n    # is a listing of simulator experiences, not a calculator tool; /fr/theme/cadeau is a gift-ideas\n    # landing page, not a checkout route.\n    if re.search(r"^(/[a-z]{2}(-[a-z]{2})?)?/(category|categorie|catégorie|categories|theme|thème|collection|collections|marque|brand|univers)(/|$)", clean):\n        return "collection_page"\n    if re.search(r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", p):\n        return "activity_detail"\n''',
    '''    # Category/theme/collection LANDING pages win over money-keyword rules: /fr/category/simulateur\n    # is a listing of simulator experiences, not a calculator tool; /fr/theme/cadeau is a gift-ideas\n    # landing page, not a checkout route.\n    if re.search(r"^(/[a-z]{2}(-[a-z]{2})?)?/(category|categorie|catégorie|categories|theme|thème|collection|collections|marque|brand|univers)(/|$)", clean):\n        return "collection_page"\n    if re.search(r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", p):\n        return "activity_detail"\n    # Legal documents (bounded), checked AFTER structural activity routes so an activity slug\n    # containing legal-ish letters (domaine-de-locguenole) is never demoted to legal_info.\n    if is_legal_page_path(clean):\n        return "legal_info"\n''',
    "move bounded legal classification after structural routes",
)
extract_path.write_text(extract)

review = review_path.read_text()
review = replace_once(
    review,
    '''LOW_VALUE_PATTERNS = [\n    "/actualites/", "/news/", "/archive/", "/archives/", "/tag/", "/tags/",\n    "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag=",\n]\n''',
    '''LOW_VALUE_PATTERNS = [\n    "/actualites/", "/news/", "/archive/", "/archives/", "/tag/", "/tags/",\n    "/author/", "/feed/", "/rss/", "?tag=", "&tag=",\n]\n''',
    "remove generic page pagination patterns",
)
review = replace_once(
    review,
    '''    route_pages = [page for page in pages if (is_route_boundary_candidate(page_evidence_url(page)) or is_internal_app_route(page_evidence_url(page))) and page_is_indexable(page)]\n''',
    '''    def is_route_page(page: dict[str, Any]) -> bool:\n        # Trust the scanner's authoritative classification when it supplied one.\n        stamped = page.get("route_boundary_candidate")\n        if isinstance(stamped, bool):\n            return stamped\n        url = page_evidence_url(page)\n        return is_route_boundary_candidate(url) or is_internal_app_route(url)\n\n    route_pages = [page for page in pages if is_route_page(page) and page_is_indexable(page)]\n''',
    "prefer scanner route boundary boolean",
)
review = replace_once(
    review,
    '''def is_low_value_page(url: str = "") -> bool:\n    path = clean_path(url).lower()\n    if re.search(r"/(20\\d{2})([-/]\\d{1,2}|/|$)", path):\n        return True\n    return any(pattern in path for pattern in LOW_VALUE_PATTERNS)\n\n\ndef is_route_boundary_candidate(url: str = "") -> bool:\n    path = clean_path(url).lower()\n    return any(pattern in path for pattern in ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"])\n''',
    '''def is_low_value_page(url: str = "") -> bool:\n    path = clean_path(url).lower()\n    # Legal/trust documents are never low-value archives, wherever the CMS files them.\n    from .extract import is_legal_page_path\n    if is_legal_page_path(path) or path.startswith(tuple(TRUST_PATHS)):\n        return False\n    if re.search(r"/(20\\d{2})([-/]\\d{1,2}|/|$)", path):\n        return True\n    # "/page/" alone demoted CMS slugs like /fr/page/mentions-legales; only numbered\n    # pagination (/page/3, ?page=2) is genuinely a low-value archive.\n    if re.search(r"/page/\\d+(/|$)", path) or re.search(r"[?&]page=\\d+", path):\n        return True\n    return any(pattern in path for pattern in LOW_VALUE_PATTERNS)\n\n\ndef is_route_boundary_candidate(url: str = "") -> bool:\n    # Delegate to the canonical, token-bounded classifier. The old review-side substring list\n    # re-matched "/cart" inside the French word "carte", so public activity pages\n    # (/fr/carte-invitation-anniversaire) were flagged as private internal routes even after\n    # the scanner had correctly classified them. One classifier, not two.\n    from .extract import is_route_boundary\n    return is_route_boundary(clean_path(url))\n''',
    "delegate review route matcher and protect legal pages",
)
review_path.write_text(review)

tests = test_path.read_text()
marker = "# --- Scanner/review split-brain + unbounded-token leaks (Funbooker live scan) ---"
if marker in tests:
    raise RuntimeError("split-brain regressions already present")
tests += '''\n\n# --- Scanner/review split-brain + unbounded-token leaks (Funbooker live scan) ---\n\ndef test_locguenole_activity_page_is_not_legal():\n    """Unbounded 'cgu' matched the letters inside 'domaine-de-lo(cgu)enole', demoting a public\n    activity page to legal_info and spawning a 'Batch image descriptions on legal info pages' card."""\n    path = "/fr/annonce/domaine-de-locguenole-a-kervignac-56/voir"\n    assert classify_template(path) == "activity_detail"\n\n\ndef test_legal_tokens_must_be_bounded_segments():\n    from app.extract import is_legal_page_path\n    assert is_legal_page_path("/fr/page/cgu")\n    assert is_legal_page_path("/cgv")\n    assert is_legal_page_path("/mentions-legales")\n    assert not is_legal_page_path("/fr/annonce/domaine-de-locguenole-a-kervignac-56/voir")\n    assert not is_legal_page_path("/fr/annonce/legumes-du-terroir/voir")\n\n\ndef test_review_route_matcher_delegates_to_canonical_classifier():\n    """review.py kept a second, weaker substring matcher that re-matched /cart inside /carte\n    even after the scanner had correctly classified the page. One classifier, not two."""\n    from app.review import is_route_boundary_candidate\n    assert not is_route_boundary_candidate("/fr/carte-invitation-anniversaire")\n    assert is_route_boundary_candidate("/cart")\n    assert is_route_boundary_candidate("/checkout")\n    assert is_route_boundary_candidate("/login")\n\n\ndef test_legal_pages_are_not_low_value_archives():\n    """Generic '/page/' in LOW_VALUE_PATTERNS demoted /fr/page/cgu to a pagination archive."""\n    from app.review import is_low_value_page\n    assert not is_low_value_page("/fr/page/cgu")\n    assert not is_low_value_page("/fr/page/mentions-legales")\n    assert is_low_value_page("/blog/page/3")\n    assert is_low_value_page("/tag/x")\n\n\ndef test_scanner_route_boundary_boolean_is_authoritative():\n    """When the scanner supplies route_boundary_candidate, review must not recompute it."""\n    from app.review import run_review\n    pages = [{"final_url": "https://f.com/fr/carte-invitation-anniversaire", "status_code": 200,\n              "h1_count": 1, "meta_description": "d",\n              "canonical": "https://f.com/fr/carte-invitation-anniversaire",\n              "route_boundary_candidate": False, "page_template_family": "standard"}]\n    r = run_review({"website_url": "https://f.com", "pages": pages,\n                    "scan_coverage": {"pages_found": 50, "pages_crawled": 1, "sampled_pages_sent_to_ai": 1}})\n    titles = " ".join(str(f.get("issue_title", "")) for f in r["cleaned_fixes"]).lower()\n    assert "route-boundary" not in titles\n'''
test_path.write_text(tests)

print("Patched extract.py, review.py, and test_page_classification.py")
