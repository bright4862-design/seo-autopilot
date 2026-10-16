"""Search-metadata applicability from retained, accepted page evidence.

This producer-side decision does not reconstruct historical reports or change
URL identities. Visitor-facing and access rules keep their existing gates.
"""

from __future__ import annotations

from .page_evidence_gate import page_has_usable_html


SEARCH_APPLICABILITY_VERSION = "search_applicability_v1_evidence_relevance"

# These rules optimize an independent search result. Headings, image alt,
# canonical-target failures and visible-content correctness are deliberately
# outside this set: noindex does not make those observations irrelevant.
SEARCH_METADATA_RULES = frozenset({
    "canonical_missing",
    "missing_canonical",
    "missing_title",
    "generic_fallback_title",
    "title_over_pixel_limit",
    "duplicate_title",
    "duplicate_title_localized",
    "duplicate_title_query_variants",
    "duplicate_title_template",
    "missing_meta_description",
    "empty_meta_description",
    "malformed_meta_description",
    "meta_description_unusable",
    "duplicate_meta_description",
})

_VALID_TARGET_STATES = {"valid", "canonical_chain"}


def _validated_canonical_away(page: dict) -> bool:
    status = str(page.get("canonical_status") or "")
    target = str(page.get("canonical_target_state") or "")
    if status == "canonical_to_different_url" and target in _VALID_TARGET_STATES:
        return True
    # A retained validation stamp is useful when a reduced page record omits
    # the target details, but cannot override contradictory current evidence.
    return (
        page.get("canonicalized_by_valid_target") is True
        and status in {"", "canonical_to_different_url"}
        and target in {"", *_VALID_TARGET_STATES}
    )


def search_applicability(page: dict) -> dict:
    """Return one versioned decision; never infer intent from a URL path.

    ``index_or_drop`` is an observed noindex/search-intent conflict, not proof
    of an indexing failure. It is one decision even when both intent sources
    are present. Invalid or inaccessible content cannot support that decision.
    """
    sources = page.get("discovered_from")
    intent_sources = []
    if isinstance(sources, (list, tuple)) and "sitemap" in sources:
        intent_sources.append("sitemap")
    if page.get("geo_search_intent") is True:
        intent_sources.append("declared_search_intent")

    accepted = (
        page_has_usable_html(page)
        and str(page.get("status_code") or "") == "200"
        and not any(page.get(key) for key in (
            "fetch_error", "raw_html_truncated", "html_truncated",
        ))
    )
    decision = {
        "version": SEARCH_APPLICABILITY_VERSION,
        "state": "not_verified",
        "reason": "accepted_html_not_available",
        "accepted_html": accepted,
        "search_metadata_applicable": False,
        "index_or_drop": False,
        "intent_sources": intent_sources,
    }
    if not accepted:
        return decision

    directives = page.get("effective_search_robots_directives")
    if directives is not None and (
        not isinstance(directives, (list, tuple))
        or any(not isinstance(value, str) for value in directives)
    ):
        return {**decision, "reason": "search_directives_not_verified"}
    effective = {value.strip().lower() for value in (directives or [])}
    noindex = bool(effective & {"noindex", "none"}) or page.get("indexability_state") == "Noindexed"
    explicit_utility = (
        page.get("geo_scope") == "intentional_utility"
        and isinstance(page.get("geo_scope_reason"), str)
        and bool(page["geo_scope_reason"].strip())
    )
    if noindex:
        reason = (
            "noindex_search_intent_conflict" if intent_sources
            else "intentional_utility_noindex" if explicit_utility
            else "noindex_intent_unresolved"
        )
        return {
            **decision,
            "state": "not_applicable",
            "reason": reason,
            "index_or_drop": bool(intent_sources),
        }
    if _validated_canonical_away(page):
        return {**decision, "state": "not_applicable", "reason": "validated_canonical_away"}
    return {
        **decision,
        "state": "applicable",
        "reason": "independent_search_metadata",
        "search_metadata_applicable": True,
    }


def search_metadata_applicable(page: dict) -> bool:
    return search_applicability(page)["search_metadata_applicable"]


def rule_is_applicable(page: dict, rule: str) -> bool:
    """Apply only this module's search gate; other evidence gates still apply."""
    if str(rule or "").strip().lower() not in SEARCH_METADATA_RULES:
        return True
    return search_metadata_applicable(page)


def filter_search_findings(findings: list[dict], pages: list[dict]) -> list[dict]:
    """Remove only observed inapplicable members before regrouping new repairs."""
    from .repair_coverage import published_evidence_url_key
    from urllib.parse import urlsplit
    lookup = {}
    for page in pages:
        for value in (page.get('url'), page.get('final_url')):
            key = published_evidence_url_key(value)
            if not key:
                continue
            parts = urlsplit(key)
            relative = (parts.path or '/') + ('?' + parts.query if parts.query else '')
            for observed in (key, relative):
                lookup.setdefault(observed, []).append(page)
    output=[]
    for finding in findings:
        rule=str(finding.get('rule') or '')
        if rule not in SEARCH_METADATA_RULES:
            output.append(finding)
            continue
        affected=finding.get('affected_pages') or [finding.get('page_url')]
        retained=[url for url in affected if url and (
            url not in lookup or any(rule_is_applicable(page,rule) for page in lookup[url]))]
        if not retained:
            continue
        if retained==affected:
            output.append(finding)
            continue
        retained_set=set(retained)
        output.append({**finding,'affected_pages':retained,'page_url':retained[0],'page_count':len(retained),
                       'source_pages':[url for url in finding.get('source_pages',[]) if url in retained_set],
                       'search_applicability_version':SEARCH_APPLICABILITY_VERSION})
    return output
