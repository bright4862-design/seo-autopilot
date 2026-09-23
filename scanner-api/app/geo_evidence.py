"""Bounded raw-HTML structural observations, never claims of AI visibility.

No fetching; retained observations are versioned separately from the evaluator.
Missing semantic applicability is unknown, not a failure or an exclusion.
"""
from dataclasses import asdict
from datetime import date, datetime
from hashlib import sha256
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .geo_readiness import CHECKS, Observation, evaluate_geo
from .page_evidence_gate import classify_page_evidence, page_evidence_class

VERSION = "geo_evidence_v1"
MAX_HTML = 2_000_000
MAX_SAMPLES = 5
MAX_JSONLD_ENTRIES = 50
TEMPLATE = re.compile(r"\{\{\s*[A-Za-z_][\w. -]{0,60}\s*\}\}|\[\[\s*[A-Za-z_][\w. -]{0,60}\s*\]\]|#(?:location|city|state|country|business_name)#", re.I)
ARTICLE_TYPES = frozenset({"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle", "Report"})
CLEAR_NON_ARTICLE_TYPES = frozenset({"Product", "Offer", "Event", "LocalBusiness", "Organization", "Place", "Service", "ItemList", "CollectionPage"})
SUBJECT_TYPES = ARTICLE_TYPES | CLEAR_NON_ARTICLE_TYPES | frozenset({"Person"})
SUPPORT_CHECKS = frozenset({"accountability", "date_context", "source_attribution"})
# Labels promise only what retained structure establishes.
LABELS = {
    "search_policy": "OAI-SearchBot robots directive",
    "indexability": "Observed search indexing directives",
    "discovery": "Discovery in the sampled link graph",
    "main_text": "Extractable text in a main content landmark",
    "page_identity": "Nonempty page title and primary heading",
    "template_integrity": "Template token syntax in ordinary text",
    "subject_identity": "Explicitly labelled subject name",
    "entity_details": "Retained semantic contact address",
    "schema_agreement": "Page-linked structured name agrees with primary heading",
    "accountability": "Article contains an identified author",
    "date_context": "Article contains a labelled machine-readable date",
    "source_attribution": "Article identifies a supporting source URL",
}
ACTIONS = {
    "search_policy": ("Review whether the OAI-SearchBot restriction matches intended search access.", "Recheck the robots directive for the affected page after any intended change."),
    "indexability": ("Reconcile the observed noindex directive with sitemap inclusion or explicit search intent.", "Inspect the response and HTML directives after publication."),
    "template_integrity": ("Review the token syntax in ordinary page text and replace any unintended placeholder.", "Confirm the published main text no longer contains the unintended token."),
}


def _text(node):
    return " ".join(node.stripped_strings) if node else ""


def _norm_text(value):
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _page_id(page):
    value = page.get("page_id") or page.get("url")
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError("Expected bounded page_id or URL")
    # Opaque identifiers avoid leaking query strings, credentials or page content.
    return "p_" + sha256(value.encode()).hexdigest()[:24]


def _ref(page_id, check, digest):
    return f"{VERSION}:raw_html:{page_id}:{check}:{digest[:24]}"


def _uncertain(page):
    return (page_evidence_class(page) != "usable_html"
            or page.get("status_code") != 200
            or any(page.get(key) for key in ("fetch_error", "raw_html_truncated", "html_truncated", "client_rendering_suspected", "render_error", "rendering_failed")))


def _schema_types(entity):
    raw = entity.get("@type") if isinstance(entity, dict) else None
    values = raw if isinstance(raw, list) else [raw]
    result = set()
    for value in values:
        if not isinstance(value, str) or len(value) > 200:
            continue
        token = value.rsplit("/", 1)[-1].rsplit("#", 1)[-1].strip()
        if token:
            result.add(token)
    return result


def _structured_entries(soup):
    """Return bounded top-level and @graph JSON-LD objects only; no deep guessing."""
    entries = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}, limit=25):
        raw = script.string or ""
        if not raw or len(raw) > 100_000:
            continue
        try:
            value = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        roots = value if isinstance(value, list) else [value]
        for root in roots[:25]:
            if len(entries) >= MAX_JSONLD_ENTRIES:
                return entries
            if not isinstance(root, dict):
                continue
            entries.append(root)
            graph = root.get("@graph")
            if isinstance(graph, list):
                for entity in graph[:25]:
                    if len(entries) >= MAX_JSONLD_ENTRIES:
                        return entries
                    if isinstance(entity, dict):
                        entries.append(entity)
    return entries


def _canonical_public_url(value, base=""):
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        return ""
    try:
        absolute = urljoin(base, value.strip()) if base else value.strip()
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower()
        port = parsed.port
        if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
            host = f"{host}:{port}"
        path = parsed.path or "/"
        return parsed._replace(scheme=parsed.scheme.lower(), netloc=host, path=path, fragment="").geturl()
    except ValueError:
        return ""


def _entity_urls(entity):
    values = []
    for key in ("url", "@id"):
        if isinstance(entity.get(key), str):
            values.append(entity[key])
    main = entity.get("mainEntityOfPage")
    if isinstance(main, str):
        values.append(main)
    elif isinstance(main, dict):
        for key in ("url", "@id"):
            if isinstance(main.get(key), str):
                values.append(main[key])
    return values


def _entity_page_bound(entity, final_url):
    target = _canonical_public_url(final_url)
    if not target:
        return False
    return any(_canonical_public_url(value, final_url) == target for value in _entity_urls(entity))


def _entity_name(entity):
    for key in ("name", "headline"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _address_present(value):
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict):
        return False
    for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
            return True
    return False


def _author_present(value, base):
    values = value if isinstance(value, list) else [value]
    for author in values[:25]:
        if not isinstance(author, dict):
            continue
        name = author.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        for key in ("url", "@id"):
            if _canonical_public_url(author.get(key), base):
                return True
    return False


def _valid_iso_date(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        return False
    try:
        raw = value.strip()
        if len(raw) == 10:
            date.fromisoformat(raw)
        else:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def _citation_present(value, base):
    values = value if isinstance(value, list) else [value]
    for citation in values[:25]:
        if isinstance(citation, str) and _canonical_public_url(citation, base):
            return True
        if isinstance(citation, dict):
            for key in ("url", "@id"):
                if _canonical_public_url(citation.get(key), base):
                    return True
    return False


def extract_geo_evidence(html, page):
    """Return a bounded structural capability record without changing ``page``."""
    if not isinstance(page, dict) or not isinstance(html, str):
        raise ValueError("Expected HTML string and page object")
    _page_id(page)
    result = {"version": VERSION, "origin": "raw_html", "accepted": False, "signals": {}, "content_digest": ""}
    if len(html) > MAX_HTML or _uncertain(page):
        return result
    if classify_page_evidence(status_code=page.get("status_code"), content_type=page.get("content_type", ""), html=html,
                              response_headers=page.get("access_block_headers")) != "usable_html":
        return result
    soup = BeautifulSoup(html, "lxml")
    # Scripts, examples and explicitly hidden elements are not visible content.
    for node in soup.select("script:not([type='application/ld+json']), style, template, noscript, code, pre, [hidden], [aria-hidden='true']"):
        node.decompose()
    for node in reversed(soup.select("[style]")):
        if re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", node.get("style", ""), re.I):
            node.decompose()
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    h1 = main.find("h1") if main else None
    article = soup.find("article")
    h1_text = _text(h1)
    final_url = page.get("final_url") or page.get("url")
    entries = _structured_entries(soup)
    signals = {
        "main_text": bool(main and _text(main)),
        "page_identity": bool(_text(soup.title) and h1_text),
        "template_integrity": not bool(TEMPLATE.search(_text(main))) if main else None,
        "subject_identity": False, "entity_details": False,
        "schema_agreement": False, "accountability": False,
        "date_context": False, "source_attribution": False,
    }
    # Explicit microdata supplies subject/detail semantics; arbitrary strings do not.
    if main:
        # Native landmark labelling and address semantics work without schema.
        label_id = main.get("aria-labelledby")
        if isinstance(label_id, str) and h1 and h1.get("id") == label_id and h1_text:
            signals["subject_identity"] = True
        signals["entity_details"] = bool(_text(main.find("address")))
        entity = main.find(attrs={"itemscope": True, "itemtype": re.compile(r"^https?://schema\.org/(?:Organization|LocalBusiness|Person|Product)$")})
        if entity:
            name = entity.find(attrs={"itemprop": "name"})
            signals["subject_identity"] = signals["subject_identity"] or bool(_text(name) and _norm_text(_text(name)) == _norm_text(h1_text))
            address = entity.find(attrs={"itemprop": "address"})
            signals["entity_details"] = signals["entity_details"] or bool(address and _text(address))

    schema_supplied = bool(soup.find("script", attrs={"type": "application/ld+json"}) or soup.find(attrs={"itemscope": True}) or soup.select_one("[typeof], [vocab], [property], [itemprop]"))
    if not schema_supplied:
        signals["schema_agreement"] = None

    # JSON-LD positive evidence is deliberately bounded to top-level/@graph objects.
    named_subjects = [entity for entity in entries if _schema_types(entity) & SUBJECT_TYPES and _norm_text(_entity_name(entity)) == _norm_text(h1_text) and h1_text]
    bound_named_subjects = [entity for entity in named_subjects if _entity_page_bound(entity, final_url)]
    trusted_named_subjects = bound_named_subjects or (named_subjects if len(named_subjects) == 1 else [])
    if trusted_named_subjects:
        signals["subject_identity"] = True
        if any(_address_present(entity.get("address")) for entity in trusted_named_subjects):
            signals["entity_details"] = True
    if schema_supplied and bound_named_subjects:
        signals["schema_agreement"] = True

    article_entities = [entity for entity in entries if _schema_types(entity) & ARTICLE_TYPES]
    matching_articles = [entity for entity in article_entities if _entity_page_bound(entity, final_url)]
    if not matching_articles and len(article_entities) == 1 and _norm_text(_entity_name(article_entities[0])) == _norm_text(h1_text) and h1_text:
        matching_articles = article_entities

    # Article-only support checks become N/A only when explicit structured page
    # typing proves a clearly non-article subject and no article semantics exist.
    clear_non_article = [entity for entity in trusted_named_subjects if _schema_types(entity) & CLEAR_NON_ARTICLE_TYPES]
    if not article and not article_entities and clear_non_article:
        for check in SUPPORT_CHECKS:
            signals[check] = None

    if article:
        author = article.find("a", rel=lambda value: isinstance(value, str) and "author" in value.lower().split())
        signals["accountability"] = bool(author and _text(author) and _http_url(author.get("href")))
        for node in article.find_all("time", datetime=True, limit=25):
            if (node.get("itemprop") not in {"datePublished", "dateModified"} and node.get("aria-label", "").lower() not in {"published", "updated", "publication date", "last updated"}) or not _text(node):
                continue
            if _valid_iso_date(node.get("datetime")):
                signals["date_context"] = True
        for quote in article.find_all("blockquote", cite=True, limit=25):
            cite = quote.get("cite")
            if _http_url(cite) and _text(quote) and article.find("a", href=cite, string=True):
                signals["source_attribution"] = True

    for entity in matching_articles[:25]:
        if _author_present(entity.get("author"), final_url):
            signals["accountability"] = True
        if _valid_iso_date(entity.get("datePublished")) or _valid_iso_date(entity.get("dateModified")):
            signals["date_context"] = True
        if _citation_present(entity.get("citation"), final_url):
            signals["source_attribution"] = True

    result.update(accepted=True, signals=signals, content_digest=sha256(html.encode()).hexdigest())
    return result


def _http_url(value):
    return bool(_canonical_public_url(value))


def _validate_retained(value):
    keys = set(CHECKS) - {"search_policy", "indexability", "discovery"}
    if (not isinstance(value, dict) or set(value) != {"version", "origin", "accepted", "signals", "content_digest"}
            or value["version"] != VERSION or value["origin"] != "raw_html"
            or type(value["accepted"]) is not bool or not isinstance(value["signals"], dict)):
        raise ValueError("Malformed retained GEO evidence")
    if not isinstance(value["content_digest"], str) or (value["accepted"] and not re.fullmatch(r"[0-9a-f]{64}", value["content_digest"])) or (not value["accepted"] and value["content_digest"]):
        raise ValueError("Malformed GEO content digest")
    signals = value["signals"]
    if (value["accepted"] and set(signals) != keys) or (not value["accepted"] and signals):
        raise ValueError("Incomplete retained GEO evidence")
    nullable = {"template_integrity", "schema_agreement"} | SUPPORT_CHECKS
    if any((v is None and key not in nullable) or (v is not None and type(v) is not bool) for key, v in signals.items()):
        raise ValueError("Malformed GEO signal")
    return value


def assess_geo_pages(pages, *, parent_authoritative=False, entry_verified=False, access_limited=False):
    """Assess accepted retained evidence; malformed/duplicate input raises ValueError."""
    if not isinstance(pages, (list, tuple)) or len(pages) > 150 or any(not isinstance(p, dict) for p in pages):
        raise ValueError("Expected at most 150 page objects")
    indexed = [(_page_id(page), page) for page in pages]
    if len({key for key, _ in indexed}) != len(indexed):
        raise ValueError("Duplicate GEO page")
    rows = []
    for page_id, page in sorted(indexed):
        retained = _validate_retained(page["geo_evidence"]) if "geo_evidence" in page else None
        for field in ("discovered_from", "source_pages"):
            values = page.get(field, [])
            if not isinstance(values, list) or len(values) > 2000 or any(not isinstance(v, str) or len(v) > 8192 for v in values):
                raise ValueError("Malformed discovery evidence")
        policy = page.get("robots_txt_oai_searchbot_allowed")
        if policy is not None and type(policy) is not bool:
            raise ValueError("Malformed OAI search directive")
        unknown_reason = ("GEO extraction failed; content not verified" if page.get("geo_evidence_error") == "extraction_error" else "Required evidence or applicability not retained")
        states = {key: ("not_verified", unknown_reason) for key in CHECKS}
        accepted = not _uncertain(page) and retained is not None and retained["accepted"] and not access_limited
        directives = page.get("effective_search_robots_directives")
        if directives is not None and (not isinstance(directives, list) or len(directives) > 100 or any(not isinstance(x, str) or len(x) > 200 for x in directives)):
            raise ValueError("Malformed search directives")
        noindex = isinstance(directives, list) and bool({"noindex", "none"}.intersection(directives))
        search_intent = page.get("geo_search_intent") is True or "sitemap" in page.get("discovered_from", [])
        excluded = accepted and noindex and page.get("geo_scope") == "intentional_utility" and isinstance(page.get("geo_scope_reason"), str) and bool(page["geo_scope_reason"].strip()) and not search_intent
        if excluded:
            states = {key: ("not_applicable", "Explicit intentional utility scope with observed noindex") for key in CHECKS}
        elif accepted:
            if type(policy) is bool and page.get("robots_txt_rules_known") is True:
                states["search_policy"] = ("pass" if policy else "fail", "Observed OAI-SearchBot directive; not proof of provider access")
            if directives is not None:
                if not noindex:
                    states["indexability"] = ("pass", "No noindex observed in retained search directives; indexing not guaranteed")
                elif search_intent:
                    states["indexability"] = ("fail", "Observed noindex conflicts with sitemap inclusion or declared search intent")
            if page.get("source_pages") and "internal_link" in page.get("discovered_from", []):
                states["discovery"] = ("pass", "Observed incoming link in the sampled graph")
            # Noindex with unresolved intent and canonical variants are not independent content samples.
            if (not noindex or search_intent) and page.get("canonical_status") in {"missing", "self_or_equivalent"}:
                for check, signal in retained["signals"].items():
                    if check == "schema_agreement" and signal is None:
                        states[check] = ("not_applicable", "No supplied JSON-LD, microdata or RDFa structure to compare in accepted HTML")
                    elif check in SUPPORT_CHECKS and signal is None:
                        states[check] = ("not_applicable", "Explicit structured page type establishes a clearly non-article page")
                    elif signal is True:
                        states[check] = ("pass", LABELS[check])
                    elif check == "template_integrity" and signal is False:
                        states[check] = ("fail", LABELS[check])
        for check in CHECKS:
            state, reason = states[check]
            rows.append(Observation(page_id, check, state, _ref(page_id, check, retained["content_digest"]) if state in {"pass", "fail"} else "", reason))
    result = evaluate_geo([key for key, _ in indexed], rows, parent_authoritative=parent_authoritative, entry_verified=entry_verified, access_limited=access_limited)
    page_urls = {key: _safe_page_url(page.get("final_url") or page.get("url")) for key, page in indexed}
    findings = []
    for check in sorted(ACTIONS):
        affected = [row for row in rows if row.check_id == check and row.state == "fail"]
        if not affected:
            continue
        action, verification = ACTIONS[check]
        findings.append({"rule_id": "geo_" + check, "root_cause_id": "geo_" + check,
                         "check_id": check, "label": LABELS[check],
                         "affected_page_count": len(affected), "page_ids": [r.page_id for r in affected],
                         "evidence_samples": [dict(asdict(row), page_url=page_urls[row.page_id]) for row in affected[:MAX_SAMPLES]],
                         "sample_truncated": len(affected) > MAX_SAMPLES,
                         "suggested_action": action, "verification_step": verification})
    result.update(evidence_adapter_version=VERSION, observations=[asdict(row) for row in rows], findings=findings)
    return result


def _safe_page_url(value):
    # No existing scanner URL redactor: retain only a bounded public URL without
    # credentials, query or fragment. Never interpolate HTML or arbitrary fields.
    if not _http_url(value) or len(value) > 2048:
        return ""
    parsed = urlparse(value)
    return parsed._replace(query="", fragment="").geturl()
