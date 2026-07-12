from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one anchor in {path}: {old[:120]!r}; found {text.count(old)}")
    path.write_text(text.replace(old, new, 1))


market_scope = '''import re
from urllib.parse import urlparse


MARKET_SEGMENT_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def normalize_scope_prefix(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith(("http://", "https://")):
        raw = urlparse(raw).path or "/"
    clean = "/" + raw.strip("/") if raw and raw != "/" else "/"
    return clean.rstrip("/") if clean != "/" else "/"


def path_within_scope(path: str, scope_prefix: str) -> bool:
    prefix = normalize_scope_prefix(scope_prefix)
    if prefix == "/":
        return True
    candidate = normalize_scope_prefix(path)
    return candidate == prefix or candidate.startswith(prefix + "/")


def market_pair_prefix(value: str) -> str:
    raw = str(value or "")
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    segments = [segment.lower() for segment in str(path or "").split("/") if segment]
    if len(segments) >= 2 and MARKET_SEGMENT_RE.fullmatch(segments[0]) and MARKET_SEGMENT_RE.fullmatch(segments[1]):
        return f"/{segments[0]}/{segments[1]}"
    return ""


def strip_market_locale_prefix(value: str) -> str:
    raw = str(value or "")
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    segments = [segment for segment in str(path or "").split("/") if segment]
    remove = 0
    if len(segments) >= 2 and MARKET_SEGMENT_RE.fullmatch(segments[0]) and MARKET_SEGMENT_RE.fullmatch(segments[1]):
        remove = 2
    elif segments and MARKET_SEGMENT_RE.fullmatch(segments[0]):
        remove = 1
    remaining = segments[remove:]
    return "/" + "/".join(remaining) if remaining else "/"
'''
(ROOT / "scanner-api/app/market_scope.py").write_text(market_scope)

scanner = ROOT / "scanner-api/app/scanner.py"
replace_once(
    scanner,
    'from .extract import classify_template, extract_links, extract_page\nfrom .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls\n',
    'from .extract import classify_template, extract_links, extract_page\nfrom .market_scope import market_pair_prefix, path_within_scope\nfrom .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls\n',
)
replace_once(
    scanner,
    '''    parsed_start = urlparse(start_url)\n    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"\n    prefix = normalize_prefix(path_prefix or parsed_start.path or "/")\n\n    pages: list[dict] = []\n''',
    '''    parsed_start = urlparse(start_url)\n    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"\n    prefix = normalize_prefix(path_prefix or parsed_start.path or "/")\n    prefix_source = "explicit_path_prefix" if path_prefix else ("requested_url_path" if prefix != "/" else "origin_root")\n    scope_evidence = {\n        "requested_path_prefix": normalize_prefix(path_prefix or parsed_start.path or "/"),\n        "effective_path_prefix": prefix,\n        "scope_source": prefix_source,\n        "multimarket_detected": False,\n        "market_scope_required": False,\n        "market_prefixes_detected": [],\n        "sitemap_urls_excluded_outside_scope": 0,\n        "internal_urls_excluded_outside_scope": 0,\n    }\n\n    pages: list[dict] = []\n''',
)
replace_once(
    scanner,
    '''        if not same_origin(clean, origin):\n            return\n        if prefix and prefix != "/" and not (urlparse(clean).path or "/").startswith(prefix):\n            return\n''',
    '''        if not same_origin(clean, origin):\n            return\n        clean_path = urlparse(clean).path or "/"\n        if not path_within_scope(clean_path, prefix):\n            if source == "internal_link":\n                scope_evidence["internal_urls_excluded_outside_scope"] += 1\n            return\n        if prefix == "/" and scope_evidence.get("market_scope_required") and market_pair_prefix(clean_path):\n            if source == "internal_link":\n                scope_evidence["internal_urls_excluded_outside_scope"] += 1\n            return\n''',
)
replace_once(
    scanner,
    '''    ) as client:\n        max_pages = budget["max_pages"]\n        sitemap_urls = await load_sitemap_urls(client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts)\n''',
    '''    ) as client:\n        if not path_prefix and prefix == "/":\n            try:\n                landing = await safe_get(client, start_url)\n                final_landing_url = str(getattr(landing, "url", start_url) or start_url) if landing is not None else start_url\n                redirected_market = market_pair_prefix(final_landing_url)\n                if redirected_market:\n                    prefix = redirected_market\n                    scope_evidence["effective_path_prefix"] = prefix\n                    scope_evidence["scope_source"] = "redirect_market_path"\n            except Exception:\n                pass\n\n        max_pages = budget["max_pages"]\n        sitemap_urls = await load_sitemap_urls(\n            client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts, scope_evidence=scope_evidence\n        )\n''',
)
replace_once(
    scanner,
    '''        sampling_evidence = sampling_report(sitemap_urls, sampled_sitemap_urls, family_of, path_of)\n        for url in sampled_sitemap_urls:\n''',
    '''        sampling_evidence = sampling_report(sitemap_urls, sampled_sitemap_urls, family_of, path_of)\n        scope_evidence["effective_path_prefix"] = prefix\n        sampling_evidence["crawl_scope"] = dict(scope_evidence)\n        for url in sampled_sitemap_urls:\n''',
)
replace_once(
    scanner,
    '''    crawl_warnings = []\n    if render_evidence["evidence_state"] == "material_client_rendering_risk":\n''',
    '''    crawl_warnings = []\n    if scope_evidence.get("market_scope_required"):\n        crawl_warnings.append(\n            "Multiple country/language markets were detected on the global root. Submit one market URL, such as /fr/fr/, for a coherent audit."\n        )\n    if render_evidence["evidence_state"] == "material_client_rendering_risk":\n''',
)
replace_once(
    scanner,
    '''        "normalized_url": start_url,\n        "scan_mode": scan_mode,\n''',
    '''        "normalized_url": start_url,\n        "requested_path_prefix": scope_evidence.get("requested_path_prefix", "/"),\n        "crawl_scope": dict(scope_evidence),\n        "scan_mode": scan_mode,\n''',
)
replace_once(
    scanner,
    '''            "crawl_policy_source": DEFAULT_POLICY["source"],\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n''',
    '''            "crawl_policy_source": DEFAULT_POLICY["source"],\n            "crawl_scope": dict(scope_evidence),\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n''',
)

sitemap = ROOT / "scanner-api/app/sitemap.py"
replace_once(
    sitemap,
    'from .artifact_filter import is_artifact_url, record_artifact\nfrom .security import safe_get\n',
    'from .artifact_filter import is_artifact_url, record_artifact\nfrom .market_scope import market_pair_prefix, path_within_scope\nfrom .security import safe_get\n',
)
replace_once(
    sitemap,
    'async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict]) -> list[str]:\n',
    'async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None) -> list[str]:\n',
)
replace_once(
    sitemap,
    '''    roots: list[str] = []\n    robots_url = f"{origin}/robots.txt"\n''',
    '''    scope_evidence = scope_evidence if scope_evidence is not None else {}\n    scope_evidence.setdefault("sitemap_urls_excluded_outside_scope", 0)\n    scope_evidence.setdefault("market_prefixes_detected", [])\n    scope_evidence.setdefault("multimarket_detected", False)\n    scope_evidence.setdefault("market_scope_required", False)\n\n    roots: list[str] = []\n    robots_url = f"{origin}/robots.txt"\n''',
)
replace_once(
    sitemap,
    '''            elif len(bucket) < limit and is_same_prefix(loc, path_prefix):\n                bucket.append(normalize_sitemap_page_url(loc, origin))\n''',
    '''            elif len(bucket) < limit:\n                normalized = normalize_sitemap_page_url(loc, origin)\n                record_market_prefix(scope_evidence, normalized)\n                if is_same_prefix(normalized, path_prefix):\n                    bucket.append(normalized)\n                else:\n                    scope_evidence["sitemap_urls_excluded_outside_scope"] += 1\n''',
)
replace_once(
    sitemap,
    '''            if not is_sitemap_url(loc) and is_same_prefix(loc, path_prefix):\n                bucket.append(normalize_sitemap_page_url(loc, origin))\n''',
    '''            if not is_sitemap_url(loc):\n                normalized = normalize_sitemap_page_url(loc, origin)\n                record_market_prefix(scope_evidence, normalized)\n                if is_same_prefix(normalized, path_prefix):\n                    bucket.append(normalized)\n                else:\n                    scope_evidence["sitemap_urls_excluded_outside_scope"] += 1\n''',
)
replace_once(
    sitemap,
    '''    # Round-robin root and child urlsets together. Root pages keep deterministic\n    # first position, but cannot starve later child families at the global cap.\n    return dedupe(interleave_url_families(family_urls))[:limit]\n''',
    '''    # Round-robin root and child urlsets together. Root pages keep deterministic\n    # first position, but cannot starve later child families at the global cap.\n    output = dedupe(interleave_url_families(family_urls))\n    detected = sorted(set(scope_evidence.get("market_prefixes_detected", [])))\n    scope_evidence["market_prefixes_detected"] = detected[:50]\n    if (not path_prefix or path_prefix == "/") and len(detected) > 1:\n        market_urls = [url for url in output if market_pair_prefix(url)]\n        scope_evidence["multimarket_detected"] = True\n        scope_evidence["market_scope_required"] = True\n        scope_evidence["sitemap_urls_excluded_outside_scope"] += len(market_urls)\n        output = [url for url in output if not market_pair_prefix(url)]\n    elif len(detected) > 1:\n        scope_evidence["multimarket_detected"] = True\n    return output[:limit]\n''',
)
replace_once(
    sitemap,
    '''def is_same_prefix(url: str, path_prefix: str) -> bool:\n    if not path_prefix or path_prefix == "/":\n        return True\n    try:\n        return (urlparse(url).path or "/").startswith(path_prefix.rstrip("/"))\n    except Exception:\n        return False\n''',
    '''def is_same_prefix(url: str, path_prefix: str) -> bool:\n    try:\n        return path_within_scope(urlparse(url).path or "/", path_prefix)\n    except Exception:\n        return False\n\n\ndef record_market_prefix(scope_evidence: dict, url: str) -> None:\n    prefix = market_pair_prefix(url)\n    if prefix and prefix not in scope_evidence["market_prefixes_detected"]:\n        scope_evidence["market_prefixes_detected"].append(prefix)\n''',
)

extract = ROOT / "scanner-api/app/extract.py"
replace_once(
    extract,
    'from bs4 import BeautifulSoup\n\n\ndef clean_text',
    'from bs4 import BeautifulSoup\n\nfrom .market_scope import strip_market_locale_prefix\n\n\ndef clean_text',
)
replace_once(
    extract,
    '''    p = str(path or "").lower()\n    clean = p.split("?")[0].split("#")[0].rstrip("/") or "/"\n    if clean in ("", "/") or clean.count("/") == 0:\n        return "homepage"\n''',
    '''    p = str(path or "").lower()\n    clean = p.split("?")[0].split("#")[0].rstrip("/") or "/"\n    localized = strip_market_locale_prefix(clean).rstrip("/") or "/"\n    if localized in ("", "/") or localized.count("/") == 0:\n        return "homepage"\n''',
)
replacements = [
    ('if is_support_content_path(clean):', 'if is_support_content_path(localized):'),
    ('r"^(/[a-z]{2}(-[a-z]{2})?)?/(category|categorie|catégorie|categories|theme|thème|collection|collections|marque|brand|univers)(/|$)", clean', 'r"^/(category|categorie|catégorie|categories|cat|theme|thème|collection|collections|marque|brand|univers)(/|$)", localized'),
    ('r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", p', 'r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", localized'),
    ('if is_legal_page_path(clean):', 'if is_legal_page_path(localized):'),
    ('if STRONG_LOAN_PATH_RE.search(clean):', 'if STRONG_LOAN_PATH_RE.search(localized):'),
    ('r"/apply-now|/apply(?:/|$)|/request-a-payoff|/document-exchange|/souscription|/devis|/quote|/signup|/demo|/contact-sales", p', 'r"/apply-now|/apply(?:/|$)|/request-a-payoff|/document-exchange|/souscription|/devis|/quote|/signup|/demo|/contact-sales", localized'),
    ('r"/comparateur|/compare|/comparer|/versus|/vs-", p', 'r"/comparateur|/compare|/comparer|/versus|/vs-", localized'),
    ('r"/products?/|/produit/|/p/", p', 'r"/products?/|/produit/|/p/", localized'),
    ('r"/collections?/|/category/|/categorie/|/catégorie/|/marque/|/brand/|listing", p', 'r"/collections?/|/category/|/categorie/|/catégorie/|/cat/|/marque/|/brand/|listing", localized'),
    ('r"/locations?/|/agence|/ville/|/region/|/store-locator", p', 'r"/locations?/|/agence|/ville/|/region/|/store-locator", localized'),
    ('r"(^|/)(contact|nous-contacter|contactez-nous)(/|$)", clean', 'r"(^|/)(contact|nous-contacter|contactez-nous)(/|$)", localized'),
    ('if BROAD_LOAN_SEGMENT_RE.search(clean):', 'if BROAD_LOAN_SEGMENT_RE.search(localized):'),
    ('r"/calcul|/calculator|/simulateur|/simulation", p', 'r"/calcul|/calculator|/simulateur|/simulation", localized'),
    ('if BOOKING_SEGMENT_RE.search(clean) or re.search(r"ticket[_-]order|gift[_-]voucher", clean):', 'if BOOKING_SEGMENT_RE.search(localized) or re.search(r"ticket[_-]order|gift[_-]voucher", localized):'),
    ('if any(x in p for x in ["guide", "blog", "article", "conseils", "actualites", "/faq", "question"]):', 'if any(x in localized for x in ["guide", "blog", "article", "conseils", "actualites", "/faq", "question"]):'),
]
for old, new in replacements:
    replace_once(extract, old, new)

market_tests = '''from app.extract import classify_template, estimate_intent
from app.market_scope import market_pair_prefix, path_within_scope, strip_market_locale_prefix


def test_scope_prefix_is_segment_bounded():
    assert path_within_scope("/fr", "/fr")
    assert path_within_scope("/fr/page", "/fr")
    assert not path_within_scope("/france/page", "/fr")


def test_market_pair_and_locale_stripping():
    assert market_pair_prefix("https://www.ikea.com/fr/fr/cat/chairs") == "/fr/fr"
    assert strip_market_locale_prefix("/fr/fr/cat/chairs") == "/cat/chairs"
    assert strip_market_locale_prefix("/fr/page/cgu") == "/page/cgu"


def test_ikea_localized_routes_are_classified_by_template():
    assert classify_template("/fr/fr/") == "homepage"
    assert classify_template("/fr/fr/cat/canapes-10661") == "collection_page"
    assert classify_template("/us/en/p/billy-bookcase-00263850") == "product_page"
    assert classify_template("/fr/fr/customer-service/contact-us/") == "contact"
    assert estimate_intent("/fr/fr/cat/canapes-10661", "", "", 200) == "money_or_conversion"
'''
(ROOT / "scanner-api/tests/test_market_scope.py").write_text(market_tests)

test_sitemap = ROOT / "scanner-api/tests/test_sitemap.py"
with test_sitemap.open("a") as handle:
    handle.write('''\n\ndef test_market_scoped_sitemap_excludes_other_country_language_pairs(monkeypatch):\n    origin = "https://www.ikea.com"\n    pages = [\n        f"{origin}/fr/fr/cat/canapes-10661",\n        f"{origin}/de/de/cat/sofas-fu003",\n        f"{origin}/us/en/p/billy-bookcase-00263850",\n    ]\n    responses = {\n        f"{origin}/robots.txt": FakeResponse(status_code=404),\n        f"{origin}/sitemap.xml": FakeResponse(sitemap_xml(pages)),\n    }\n\n    async def fake_safe_get(client, url):\n        return responses.get(url, FakeResponse(status_code=404))\n\n    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)\n    scope = {}\n    urls = asyncio.run(load_sitemap_urls(object(), origin, "/fr/fr", 20, [], scope_evidence=scope))\n\n    assert urls == [pages[0]]\n    assert scope["sitemap_urls_excluded_outside_scope"] == 2\n    assert scope["multimarket_detected"] is True\n    assert set(scope["market_prefixes_detected"]) == {"/fr/fr", "/de/de", "/us/en"}\n\n\ndef test_global_multimarket_root_requires_an_explicit_market(monkeypatch):\n    origin = "https://www.ikea.com"\n    pages = [\n        f"{origin}/fr/fr/cat/canapes-10661",\n        f"{origin}/de/de/cat/sofas-fu003",\n        f"{origin}/us/en/p/billy-bookcase-00263850",\n    ]\n    responses = {\n        f"{origin}/robots.txt": FakeResponse(status_code=404),\n        f"{origin}/sitemap.xml": FakeResponse(sitemap_xml(pages)),\n    }\n\n    async def fake_safe_get(client, url):\n        return responses.get(url, FakeResponse(status_code=404))\n\n    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)\n    scope = {}\n    urls = asyncio.run(load_sitemap_urls(object(), origin, "/", 20, [], scope_evidence=scope))\n\n    assert urls == []\n    assert scope["multimarket_detected"] is True\n    assert scope["market_scope_required"] is True\n    assert scope["sitemap_urls_excluded_outside_scope"] == 3\n''')

print("multimarket patch applied")
