"""Bounded raw-HTML structural observations, never claims of AI visibility.

No fetching; retained observations are versioned separately from the evaluator.
Missing semantic applicability is unknown, not a failure or an exclusion.
"""
from dataclasses import asdict
from datetime import date, datetime
from hashlib import sha256
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .geo_readiness import CHECKS, Observation, evaluate_geo
from .page_evidence_gate import classify_page_evidence, page_evidence_class

VERSION = "geo_evidence_v1"
MAX_HTML = 2_000_000
MAX_SAMPLES = 5
TEMPLATE = re.compile(r"\{\{\s*[A-Za-z_][\w. -]{0,60}\s*\}\}|\[\[\s*[A-Za-z_][\w. -]{0,60}\s*\]\]|#(?:location|city|state|country|business_name)#", re.I)
# Labels promise only what retained structure establishes.
LABELS = {
    "search_policy": "OAI-SearchBot robots directive",
    "indexability": "Observed search indexing directives",
    "discovery": "Discovery in the sampled link graph",
    "main_text": "Extractable text in a main content landmark",
    "page_identity": "Nonempty page title and primary heading",
    "template_integrity": "Template token syntax in ordinary text",
    "subject_identity": "Explicitly labelled subject name",
    "entity_details": "Visible semantic contact address",
    "schema_agreement": "Page-linked structured name agrees with primary heading",
    "accountability": "Article contains an identified author link",
    "date_context": "Article contains a labelled machine-readable date",
    "source_attribution": "Article quotation links its declared source",
}
ACTIONS = {
    "search_policy": ("Review whether the OAI-SearchBot restriction matches intended search access.", "Recheck the robots directive for the affected page after any intended change."),
    "indexability": ("Reconcile the observed noindex directive with sitemap inclusion or explicit search intent.", "Inspect the response and HTML directives after publication."),
    "template_integrity": ("Review the token syntax in ordinary page text and replace any unintended placeholder.", "Confirm the published main text no longer contains the unintended token."),
}


def _text(node):
    return " ".join(node.stripped_strings) if node else ""


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
    signals = {
        "main_text": bool(main and _text(main)),
        "page_identity": bool(_text(soup.title) and _text(h1)),
        "template_integrity": not bool(TEMPLATE.search(_text(main))) if main else None,
        "subject_identity": False, "entity_details": False,
        "schema_agreement": False, "accountability": False,
        "date_context": False, "source_attribution": False,
    }
    # Explicit microdata supplies subject/detail semantics; arbitrary strings do not.
    if main:
        # Native landmark labelling and address semantics work without schema.
        label_id = main.get("aria-labelledby")
        if isinstance(label_id, str) and h1 and h1.get("id") == label_id and _text(h1):
            signals["subject_identity"] = True
        signals["entity_details"] = bool(_text(main.find("address")))
        entity = main.find(attrs={"itemscope": True, "itemtype": re.compile(r"^https?://schema\.org/(?:Organization|LocalBusiness|Person|Product)$")})
        if entity:
            name = entity.find(attrs={"itemprop": "name"})
            signals["subject_identity"] = signals["subject_identity"] or bool(_text(name) and _text(name) == _text(h1))
            address = entity.find(attrs={"itemprop": "address"})
            signals["entity_details"] = signals["entity_details"] or bool(address and _text(address))
    if not soup.find("script", attrs={"type": "application/ld+json"}) and not soup.find(attrs={"itemscope": True}) and not soup.select_one("[typeof], [vocab], [property], [itemprop]"):
        signals["schema_agreement"] = None
    final_url = page.get("final_url") or page.get("url")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}, limit=25):
        raw = script.string or ""
        if len(raw) > 100_000:
            continue
        try:
            value = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        # Deliberately no arbitrary nested graph traversal or guessed subject.
        entries = value if isinstance(value, list) else [value]
        for entity in entries[:25]:
            if not isinstance(entity, dict):
                continue
            if entity.get("url") == final_url and isinstance(entity.get("name"), str) and _text(h1):
                if entity["name"].strip() == _text(h1):
                    signals["schema_agreement"] = True
    if article:
        author = article.find("a", rel=lambda value: isinstance(value, str) and "author" in value.lower().split())
        signals["accountability"] = bool(author and _text(author) and _http_url(author.get("href")))
        for node in article.find_all("time", datetime=True, limit=25):
            if (node.get("itemprop") not in {"datePublished", "dateModified"} and node.get("aria-label", "").lower() not in {"published", "updated", "publication date", "last updated"}) or not _text(node):
                continue
            try:
                raw_date = node["datetime"]
                if len(raw_date) == 10:
                    date.fromisoformat(raw_date)
                else:
                    datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                signals["date_context"] = True
            except (ValueError, TypeError):
                pass
        for quote in article.find_all("blockquote", cite=True, limit=25):
            cite = quote.get("cite")
            if _http_url(cite) and _text(quote) and article.find("a", href=cite, string=True):
                signals["source_attribution"] = True
    result.update(accepted=True, signals=signals, content_digest=sha256(html.encode()).hexdigest())
    return result


def _http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


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
    if any((v is None and key not in {"template_integrity", "schema_agreement"}) or (v is not None and type(v) is not bool) for key, v in signals.items()):
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
